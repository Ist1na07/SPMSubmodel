"""Local tap and hold projections of SPM Rating v1.3.0 (revision 2)."""
from dataclasses import dataclass, replace
import math
from pathlib import Path

import numpy as np
from spm_rating import clock, engine, load_model, v130_engine as core, v130_rev2 as scorer
from spm_rating.api import align
from spm_rating._core.parser import parse_content, parse_file

LN_LOAD_GAIN = 16.
LN_HALF_EXPOSURE = 30.
LN_EXPOSURE_POWER = 2
RC_ALPHA = .16
LN_BIAS_RAMP = .35  # Skill units; restores the native offset smoothly at zero.


def _tap(notes):
    return replace(notes, is_ln=np.zeros_like(notes.is_ln), ln_end=notes.time.copy())


def _divide(a, b):
    return np.divide(a, b, out=np.zeros_like(a), where=b > 0.)


def _local_mean(t, values, query, half):
    """Centered triangular mean on sorted rows, evaluated with prefix sums."""
    query, t = query-t[0], t-t[0]
    lo, mid, hi = (np.searchsorted(t, x) for x in (query-half, query, query+half))

    def weighted_sum(x):
        s = np.r_[0., np.cumsum(x)]
        st = np.r_[0., np.cumsum(x*t)]
        left, right = s[mid]-s[lo], s[hi]-s[mid]
        return left+right+(st[mid]-st[lo]-query*left+query*right-st[hi]+st[mid])/half

    return _divide(np.maximum(weighted_sum(values), 0.), weighted_sum(np.ones(len(t))))


def _hold_support(notes, query, radius, tau):
    """Combine the local share of sustained heads and occupied fingers."""
    t = (notes.time-notes.time[0])*notes.rate
    end = (notes.ln_end-notes.time[0])*notes.rate
    q = (query-notes.time[0])*notes.rate
    duration = np.maximum(end-t, 0.)
    strength = duration/(duration+tau)
    head = np.clip(_local_mean(t, strength, q, radius), 0., 1.)
    h, e, a = t[notes.is_ln], end[notes.is_ln], strength[notes.is_ln]
    points, slots = np.unique(np.r_[h, e], return_inverse=True)
    jump = np.bincount(slots, weights=np.r_[a, -a], minlength=len(points))
    area = np.r_[0., np.cumsum(np.cumsum(jump)[:-1]*np.diff(points))]
    occupied = (np.interp(q+radius, points, area)-np.interp(q-radius, points, area))/(2*radius)
    return np.sqrt(head*(-np.expm1(-np.maximum(occupied, 0.)**2)))


def _ln_share(load, full, gain):
    load = gain*load
    return _divide(load, np.hypot(load, full))


def _rc_weight(time, membership, hold, tau, alpha):
    witness = membership**2
    nearby = _local_mean(time, witness, time, tau)
    return 1.+((1.-alpha)/alpha)*nearby*(1.-hold)**2*(1.-witness)


def _postprocess(u, heads, v, n0):
    # Match the length, compression and scale steps of scorer.aggregate.
    u *= heads/(heads+n0)
    threshold = v[scorer.I_PP_THR]
    if u > threshold:
        u = threshold+(u-threshold)/v[scorer.I_PP_DIV]
    return u*v[scorer.I_PP_SCALE]+v[scorer.I_PP_BIAS]


def _fresh(field, diag, v):
    stamina = diag[:, 9]
    return field/(1.+v[scorer.I_C_STAM]*stamina/(stamina+v[scorer.I_STAM_HALF]))


def _ln_load(state, diag, v):
    """Price native release, coordination, roles and the static support row."""
    stream_power = 1./v[scorer.I_S_P]
    action = np.maximum(diag[:, 4], 1e-4)
    amount = np.maximum(state.a[:, 13], 0.)
    release = v[scorer.I_A_R_4K if state.key == 4 else scorer.I_A_R]
    coordination = v[scorer.I_A_CB_4K if state.key == 4 else scorer.I_A_CB]
    price = v[scorer.I_D_B2]*v[scorer.I_C_S]**stream_power*action**v[scorer.I_AP]
    load = price*(release*diag[:, 5]/(amount+v[scorer.I_A_C])
                  +coordination*diag[:, 6]/(amount+v[scorer.I_A_CBC]))
    load += (v[scorer.I_D_B2]*v[scorer.I_C_JM]**stream_power
             * action**(v[scorer.I_AJ]/state.a[:, 11])*diag[:, 7])
    return load+v[scorer.I_HOLD_FLOOR]*state.a[:, -1]


@dataclass(frozen=True)
class _Rows:
    v: np.ndarray
    beta: float
    gamma: float
    n0: float
    heads: int
    z: np.ndarray
    ln_mass: np.ndarray
    load: np.ndarray
    full: np.ndarray
    hold: np.ndarray
    ln_heads: np.ndarray
    tc: np.ndarray
    tz: np.ndarray
    tm: np.ndarray
    td: np.ndarray
    tap_rows: np.ndarray

    def relative(self, d, m):
        return scorer.relative(d, m, self.beta, self.gamma)

    def post(self, u, heads):
        return _postprocess(u, heads, self.v, self.n0)


def _rows(notes, model, cancel):
    """One full forward; mixed and hold charts also share one head-only forward."""
    p = model.parameters
    profile = scorer.variant(model.compact)
    v, v4, support4 = profile.native(p)
    beta, gamma, mix, n0 = profile.shape(p)
    v, support = (v4, support4) if notes.key_count == 4 else (v, 0.)
    mirror = engine.mirror(notes)
    notes = min((notes, mirror), key=lambda n: (n.col.tobytes(), n.ln_end.tobytes()))

    def forward(nt, diagnostics):
        core.check_cancel(cancel)
        s = scorer.state_from_notes(nt, profile, p)
        core.check_cancel(cancel)
        d, diag = scorer.field(s.a, s.b, s.t, s.key, v, profile.compact,
                               profile.hill, profile.xsoft, diagnostics, support)
        core.check_cancel(cancel)
        m, z = scorer.row_mass(d, s.gp, s.amount, s.held, s.env_half, v)
        return s, d, diag, m, z

    s, d, diag, m, z = forward(notes, bool(notes.n_ln))
    u = scorer.relative(z, m, beta, gamma) if np.any(m > 0.) else .50*d.max()
    if mix < 1. and np.any(m > 0.):
        ph, sl, nb, ev = scorer.phase_structure(s)
        u = mix*u+(1.-mix)*scorer.pooled_shared(z, m, ph, sl, ev, nb, s.win_ms, v)
    spm = _postprocess(u, notes.n_notes, v, n0)
    if not notes.n_ln:
        return spm, None

    tap, td, tap_diag, tm, tz = forward(_tap(notes), True)
    fb = _fresh(d, diag, v)
    delta = np.maximum(fb-np.interp(s.t, tap.t, _fresh(td, tap_diag, v)), 0.)
    load = _ln_load(s, diag, v)
    # The counterfactual field difference only contributes with physical LN load.
    load += _divide(load*delta, load+.5*delta)
    half = .5*p['w_r']
    hold = _hold_support(notes, s.t, half, p['r_sim_tau'])
    ln_heads = s.head_pos[notes.is_ln]
    if len(s.t) > len(tap.t):
        # A static chord's single virtual row belongs to its physical heads,
        # even when its offset lies outside the ordinary release window.
        hold[-1] = hold[ln_heads[0]]
        ln_heads = np.full_like(ln_heads, len(s.t)-1)
    v_unheld = v.copy()
    v_unheld[scorer.I_HOLD_MASS] = 0.
    unheld, _ = scorer.row_mass(d, s.gp, s.amount, s.held, s.env_half, v_unheld)
    tap_rows = np.searchsorted(s.t, tap.t)
    return spm, _Rows(v, beta, gamma, n0, notes.n_notes, z, unheld,
                      _local_mean(s.t, load, s.t, half), _local_mean(s.t, fb, s.t, half),
                      hold, ln_heads, tap.t, tz, tm, td, tap_rows)


def _ln_root(rows, share, membership):
    mass = rows.ln_mass*membership
    return rows.relative(rows.z*share, mass) if np.any(mass > 0.) else 0.


def _ln_score(rows, root, exposed, half_exposure):
    if root <= 0. or exposed <= 0.:
        return 0.
    count = exposed**LN_EXPOSURE_POWER
    u = root*count/(count+half_exposure**LN_EXPOSURE_POWER)
    bias = rows.v[scorer.I_PP_BIAS]
    return rows.post(u, exposed)-bias+bias*u/(u+LN_BIAS_RAMP)


def _rc_score(rows, membership, alpha):
    w = _rc_weight(rows.tc, membership[rows.tap_rows], rows.hold[rows.tap_rows],
                   rows.v[scorer.I_TAU_STAM], alpha)
    u = rows.relative(rows.tz, rows.tm*w) if np.any(rows.tm > 0.) else .50*rows.td.max()
    return rows.post(u, rows.heads)


def _phase(notes, model, cancel):
    spm, rows = _rows(notes, model, cancel)
    if rows is None:
        return np.array([spm, spm, 0., 0.])
    core.check_cancel(cancel)
    share = _ln_share(rows.load, rows.full, LN_LOAD_GAIN)
    membership = share*rows.hold
    exposed = float(membership[rows.ln_heads].sum())
    ln = _ln_score(rows, _ln_root(rows, share, membership), exposed, LN_HALF_EXPOSURE)
    rc = _rc_score(rows, membership, RC_ALPHA)
    return np.array([spm, rc, ln, exposed])


def rate_notes(notes, model='detail', *, scale='raw', cancel=None):
    """Return whole-chart SPM, tap and long-note scores and head diagnostics."""
    core.check_cancel(cancel)
    if isinstance(model, str):
        model = load_model(model)
    if scale not in ('raw', 'reference'):
        raise ValueError('Choose raw or reference.')
    if model.engine != 'v130' or model.revision != 2:
        raise ValueError('This submodel requires an SPM Rating v1.3.0-rev2 profile.')
    physical = core.physical_notes(notes)
    _check_rate(physical.rate)
    plan = clock.plan(physical)
    if plan is None:
        values = _phase(physical, model, cancel)
    else:
        values = np.zeros(4)
        for weight, state, _, _ in clock.states(physical, plan):
            core.check_cancel(cancel)
            values += weight*_phase(core.physical_notes(state), model, cancel)

    if scale == 'reference':
        calibration = model.alignment[str(physical.key_count)]
        values[:3] = [align(calibration, raw) for raw in values[:3]]
    return dict(spm=float(values[0]), rc=float(values[1]), ln=float(values[2]),
                ln_coverage=float(values[3]/physical.n_notes), key_count=physical.key_count,
                rate=physical.rate, scale=scale, model=model.name, model_identity=model.identity,
                heads=physical.n_notes)


def _check_rate(rate):
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError('Positive finite speed rate required.')


def rate_file(path, model='detail', *, rate=1., **options):
    _check_rate(rate)
    return rate_notes(parse_file(str(Path(path)), rate=rate), model, **options)


def rate_content(text, model='detail', *, rate=1., **options):
    _check_rate(rate)
    return rate_notes(parse_content(text, rate=rate), model, **options)
