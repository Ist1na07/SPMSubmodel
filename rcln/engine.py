"""Whole-chart RC and LN scores using SPM Rating v1.2.0-rc3 internals."""
from dataclasses import replace
import math
from pathlib import Path

import numpy as np
from spm_rating import clock, engine, geometry, hand, hand_cost, recovery, role, load_model

M = engine.model


def _tap(notes):
    return replace(notes, is_ln=np.zeros(len(notes.time), dtype=bool),
                   ln_end=notes.time.copy())


def _presence(notes, s, width=700.0, exponent=0.5):
    # Note-level heads plus active intervals avoid treating every member of a
    # mixed chord as a long note. Release times are mapped to the next row.
    present = (s.held > 0).astype(float)
    if np.any(notes.is_ln):
        head = np.searchsorted(s.t, notes.time[notes.is_ln])
        present[head] = 1.0
        tails = np.searchsorted(s.t, notes.ln_end[notes.is_ln])
        tails = tails[tails < len(s.t)]
        present[tails] = 1.0
    return np.clip(M._wmean(s, present, width), 0., 1.) ** exponent


def _ln_aggregate(s, field, g, p):
    """Apply LN presence to the upstream two-level engagement mass."""
    if int(p['agg_mode']) != 4:
        raise ValueError('LN aggregation requires the upstream two-level aggregation mode.')
    D = np.maximum(np.nan_to_num(field, nan=0., posinf=0., neginf=0.), 0.)
    env = float(p.get('env_w', 0.))
    if env:
        D = (1-env)*D + env*M._peak_envelope(s, D, max(float(p.get('env_ms', 800.)), 50.))
    dn = np.zeros(s.n); dn[:-1] = s.dt_diff
    dp = np.zeros(s.n); dp[1:] = dn[:-1]; dp[s.starts[:-1]] = 0.
    gp = np.maximum((dn+dp)*.5, 0.)
    cap = float(p.get('aggw_gap_cap', 0.))
    if cap > 0: gp = np.minimum(gp, cap)
    mass = M._aggc_mass(s, gp, p, True)
    weighted = mass*g
    cov = float(weighted.sum()/mass.sum()) if mass.sum() else 0.
    inv, chart, _, _, _ = M._aggc_windows(s, *M._aggc_geom(p))
    a = max(float(p['aggC_pw1']), .05); b = max(float(p['aggC_pw2']), .05)
    w = np.bincount(inv, weights=weighted, minlength=len(chart))
    v = np.bincount(inv, weights=weighted*D**a, minlength=len(chart))
    d = (v/np.maximum(w, 1e-9))**(1/a)
    raw = float((np.sum(w*d**b)/max(np.sum(w), 1e-9))**(1/b))
    # Same postprocess as SPM, with effective long-note engagement count.
    count = float(s.n_notes[0])*cov
    raw *= count/(count+max(float(p['pp_n0']), 1e-6))
    if raw > p['pp_thr']: raw = p['pp_thr']+(raw-p['pp_thr'])/max(p['pp_div'], .001)
    score = max(raw*p['pp_scale']*p['calib_a']+p['calib_b'], 0.)
    # Short isolated LN passages need less weight as a whole-chart skill.
    # Full weight is reached at 40% of the chart's engagement mass.
    return score*min(cov/0.40, 1.), cov


def _rc_aggregate(s, field, g, coverage, p, *, strength=0.95, taper=0.20):
    """Favor tap-oriented rows on mixed charts using SPM's two-level aggregate."""
    if int(p['agg_mode']) != 4:
        raise ValueError('RC aggregation requires the upstream two-level aggregation mode.')
    intensity = strength*np.clip((1.0-coverage)/taper, 0., 1.)
    if intensity <= 1e-12:
        return M.aggregate(s, field, p, hold_w=True)
    d = np.maximum(np.nan_to_num(field, nan=0., posinf=0., neginf=0.), 0.)
    env = float(p.get('env_w', 0.))
    if env:
        d = (1-env)*d + env*M._peak_envelope(s, d, max(float(p.get('env_ms', 800.)), 50.))
    dn = np.zeros(s.n); dn[:-1] = s.dt_diff
    dp = np.zeros(s.n); dp[1:] = dn[:-1]; dp[s.starts[:-1]] = 0.
    gp = np.maximum((dn+dp)*.5, 0.)
    cap = float(p.get('aggw_gap_cap', 0.))
    if cap > 0: gp = np.minimum(gp, cap)
    mass = M._aggc_mass(s, gp, p, True)*np.maximum(1.-intensity*g, 0.)
    inv, chart, _, _, _ = M._aggc_windows(s, *M._aggc_geom(p))
    a = max(float(p['aggC_pw1']), .05); b = max(float(p['aggC_pw2']), .05)
    w = np.bincount(inv, weights=mass, minlength=len(chart))
    v = np.bincount(inv, weights=mass*d**a, minlength=len(chart))
    window = (v/np.maximum(w, 1e-9))**(1/a)
    return np.array([(np.sum(w*window**b)/max(np.sum(w), 1e-9))**(1/b)])


def _native(notes, model, *, rc_probe=None):
    e = engine.get(); p = dict(model.parameters); local = {**p, 'x_jump_w': 0.}
    other = engine.mirror(notes)
    if (other.col.tobytes(), other.ln_end.tobytes()) < (notes.col.tobytes(), notes.ln_end.tobytes()):
        notes, other = other, notes
    full, rice = [], []
    extra = None
    for nt in (notes, other):
        s = e.build(nt, local)
        cur = geometry.compute_curves(s.batch, s, {**local, 'd_rec': 0.})
        rec = recovery.curve(nt.time, s.t, local['recov_w'], local['recov_wl'])
        cur = {**cur, 'Recov': rec}
        rates = hand.field(hand.extract(nt, 30.), s.t, float(local['w_jm']))
        unit = hand_cost.price(hand_cost.state(rates), s.x[0], p)
        if extra is None: extra = model.role_price*role.field(notes, p, s.t)
        full.append((s, cur, unit))
        if np.any(nt.is_ln):
            ts = e.build(_tap(nt), local)
            tc = geometry.compute_curves(ts.batch, ts, {**local, 'd_rec': 0.})
            rice.append((ts, {**tc, 'Recov': rec}, unit))
    def field(sources, role_extra):
        release = .5*(sources[0][1]['Rbar']+sources[1][1]['Rbar'])
        parts = [M.combine(s, {**cur, 'Rbar': release, 'Jm_context': cur['Jm'],
                               'Jm': cur['Jm']+unit+role_extra}, p)
                 for s, cur, unit in sources]
        return .5*(parts[0]+parts[1])
    s = full[0][0]; d = field(full, extra)
    star = float(M.postprocess(s, M.aggregate(s, d, p, hold_w=True), p)[0])
    g = _presence(notes, s)
    ln, coverage = _ln_aggregate(s, d, g, p)
    if rice:
        sr = rice[0][0]; dr = field(rice, 0.)
        rc_head_only = float(M.postprocess(sr, M.aggregate(sr, dr, p, hold_w=True), p)[0])
        rc = float(M.postprocess(sr, _rc_aggregate(sr, dr, g, coverage, p), p)[0])
        if rc_probe is not None:
            rc_probe(sr, dr, g, coverage, p)
    else:
        rc = rc_head_only = star
    return np.array([star, rc, ln, coverage, rc_head_only])


def rate_notes(notes, model='detail', *, scale='raw', cancel=None):
    if isinstance(model, str): model = load_model(model)
    if scale not in ('raw', 'reference'): raise ValueError('scale must be raw or reference')
    if notes is None or notes.n_notes < 2: raise ValueError('A chart requires at least two physical heads.')
    if notes.key_count not in (4, 6, 7): raise ValueError('Only 4K, 6K and 7K are supported.')
    if not np.all(np.isfinite(notes.time)) or not np.all(np.isfinite(notes.ln_end)):
        raise ValueError('Finite note times required.')
    if not math.isfinite(notes.rate) or notes.rate <= 0: raise ValueError('Positive finite rate required.')
    if cancel is not None and cancel(): raise InterruptedError('Calculation stopped.')
    physical = role.canonical(notes) if model.physical_objects else notes
    if physical.n_notes < 2: raise ValueError('A chart requires at least two physical heads.')
    plan = clock.plan(physical)
    if plan is None:
        values = _native(physical, model)
    else:
        values = np.zeros(5)
        for weight, state, _, _ in clock.states(physical, plan):
            if cancel is not None and cancel(): raise InterruptedError('Calculation stopped.')
            values += weight*_native(role.canonical(state) if model.physical_objects else state, model)
    alignment = model.alignment.get(str(notes.key_count))
    if scale == 'reference':
        if alignment is None: raise ValueError('No reference alignment for this key count.')
        values[:3] = alignment['scale']*values[:3]**alignment['power']
        values[4] = alignment['scale']*values[4]**alignment['power']
    return dict(spm=float(values[0]), rc=float(values[1]), ln=float(values[2]),
                ln_coverage=float(values[3]), rc_head_only=float(values[4]),
                key_count=notes.key_count, rate=notes.rate,
                scale=scale, model=model.name, model_identity=model.identity, heads=physical.n_notes)


def rate_file(path, model='detail', *, rate=1., **options):
    if not math.isfinite(rate) or rate <= 0: raise ValueError('Positive finite rate required.')
    return rate_notes(engine.get().parser.parse_file(str(Path(path)), rate=rate), model, **options)


def rate_content(text, model='detail', *, rate=1., **options):
    if not math.isfinite(rate) or rate <= 0: raise ValueError('Positive finite rate required.')
    return rate_notes(engine.get().parser.parse_content(text, rate=rate), model, **options)
