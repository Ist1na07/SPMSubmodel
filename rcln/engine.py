"""RC and LN projections of the SPM Rating v1.3.0-rev2 row scorer."""
from dataclasses import replace
import math
from pathlib import Path

import numpy as np
from spm_rating import clock, load_model, role, v130_engine as core, v130_rev2 as scorer
from spm_rating.api import align
from spm_rating._core.parser import parse_content, parse_file

PRESENCE_MS = 700.
CONTACT_MARGIN_MS = 75.
LN_EXPOSURE = .15
RC_STRENGTH = 4.
RC_MIN_WEIGHT = .10


def _tap(notes):
    return replace(notes, is_ln=np.zeros_like(notes.is_ln), ln_end=notes.time.copy())


def _presence(notes, query):
    """Continuous local support from the union of expanded hold intervals."""
    heads = notes.time[notes.is_ln]
    tails = notes.ln_end[notes.is_ln]
    n = len(heads)
    times, slots = np.unique(
        np.r_[heads-CONTACT_MARGIN_MS, tails+CONTACT_MARGIN_MS], return_inverse=True)
    count = np.bincount(slots, weights=np.r_[np.ones(n), -np.ones(n)], minlength=len(times))
    occupied = (np.cumsum(count)[:-1] > 0).astype(float)
    return np.sqrt(np.clip(role.interval_mean(times, occupied, query, PRESENCE_MS), 0., 1.))


def _rc_weight(rc, ln):
    """Use only local demand; the same function runs at every row."""
    ratio = ln/np.maximum(rc, 1e-12)
    return RC_MIN_WEIGHT+(1.-RC_MIN_WEIGHT)/(1.+RC_STRENGTH*ratio**2)


def _postprocess(u, heads, v, n0):
    # Same effective length, high-end compression and scale as rev2.aggregate.
    u *= heads/(heads+n0)
    threshold = v[scorer.I_PP_THR]
    if u > threshold:
        u = threshold+(u-threshold)/v[scorer.I_PP_DIV]
    return u*v[scorer.I_PP_SCALE]+v[scorer.I_PP_BIAS]


def _native(notes, profile, p, v, support, shape, cancel):
    beta, gamma, _, n0 = shape

    def forward(nt):
        core.check_cancel(cancel)
        state = scorer.state_from_notes(nt, profile, p)
        field, _ = scorer.field(state.a, state.b, state.t, state.key, v,
                                profile.compact, profile.hill, profile.xsoft,
                                ln_support=support)
        mass, demand = scorer.row_mass(field, state.gp, state.amount, state.held,
                                       state.env_half, v)
        return state.t, field, mass, demand

    def pool(field, demand, mass):
        if np.any(mass > 0.):
            return scorer.relative(demand, mass, beta, gamma)
        return .50*np.max(field)  # Native fallback for a single tap row.

    query, field, mass, demand = forward(notes)
    heads = notes.n_notes
    spm = _postprocess(pool(field, demand, mass), heads, v, n0)
    if not notes.n_ln:  # Exact identity: the tap projection would be the same chart.
        return np.array([spm, spm, 0., 0.])

    g = _presence(notes, query)
    ln_mass = mass*g
    coverage = float(ln_mass.sum()/mass.sum()) if np.any(mass > 0.) else float(g.max())
    ln = _postprocess(pool(field*g, demand, ln_mass), heads*coverage, v, n0)
    ln *= coverage/(coverage+LN_EXPOSURE*(1.-coverage))

    rc_query, rc_field, rc_mass, rc_demand = forward(_tap(notes))
    # The original state can have an extra virtual sustain row; the tap
    # projection uses only physical head times, which are shared.
    ln_at_heads = (g*demand)[np.searchsorted(query, rc_query)]
    rc = _postprocess(pool(rc_field, rc_demand, rc_mass*_rc_weight(rc_demand, ln_at_heads)),
                      heads, v, n0)
    return np.array([spm, rc, ln, coverage])


def rate_notes(notes, model='detail', *, scale='raw', cancel=None):
    core.check_cancel(cancel)
    if isinstance(model, str):
        model = load_model(model)
    if scale not in ('raw', 'reference'):
        raise ValueError('Choose raw or reference.')
    if model.engine != 'v130' or model.revision != 2:
        raise ValueError('This submodel requires an SPM Rating v1.3.0-rev2 profile.')
    physical = core.physical_notes(notes)
    p = model.parameters
    profile = scorer.variant(model.compact)
    v, v4, support = profile.native(p)
    is4k = physical.key_count == 4
    shape = profile.shape(p)
    plan = clock.plan(physical)
    args = (profile, p, v4 if is4k else v, support if is4k else 0., shape, cancel)
    if plan is None:
        values = _native(physical, *args)
    else:
        values = np.zeros(4)
        for weight, state, _, _ in clock.states(physical, plan):
            core.check_cancel(cancel)
            values += weight*_native(core.physical_notes(state), *args)

    if scale == 'reference':
        calibration = model.alignment[str(physical.key_count)]
        values[:3] = [align(calibration, raw) for raw in values[:3]]
    return dict(spm=float(values[0]), rc=float(values[1]), ln=float(values[2]),
                ln_coverage=float(values[3]), key_count=physical.key_count, rate=physical.rate,
                scale=scale, model=model.name, model_identity=model.identity, heads=physical.n_notes)


def _check_rate(rate):
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError('Positive finite speed rate required.')


def rate_file(path, model='detail', *, rate=1., **options):
    _check_rate(rate)
    return rate_notes(parse_file(str(Path(path)), rate=rate), model, **options)


def rate_content(text, model='detail', *, rate=1., **options):
    _check_rate(rate)
    return rate_notes(parse_content(text, rate=rate), model, **options)
