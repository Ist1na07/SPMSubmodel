"""Compare mixed-chart RC aggregation candidates on the 7K development set."""
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rcln.engine import _native, M
from spm_rating import engine, load_model, role, clock

STRENGTHS = (0.50, 0.80, 0.95, 0.99)
TAPERS = (0.10, 0.20, 0.40)


def candidates(s, field, g, coverage, p):
    field = np.maximum(np.nan_to_num(field, nan=0., posinf=0., neginf=0.), 0.)
    env = float(p.get('env_w', 0.))
    if env:
        field = (1-env)*field + env*M._peak_envelope(s, field, max(float(p.get('env_ms', 800.)), 50.))
    dn = np.zeros(s.n); dn[:-1] = s.dt_diff
    dp = np.zeros(s.n); dp[1:] = dn[:-1]; dp[s.starts[:-1]] = 0.
    gp = np.maximum((dn+dp)*.5, 0.)
    cap = float(p.get('aggw_gap_cap', 0.))
    if cap > 0: gp = np.minimum(gp, cap)
    mass = M._aggc_mass(s, gp, p, True)
    inv, chart, _, _, _ = M._aggc_windows(s, *M._aggc_geom(p))
    a = max(float(p['aggC_pw1']), .05); b = max(float(p['aggC_pw2']), .05)
    mass0 = np.bincount(inv, weights=mass, minlength=len(chart))
    num0 = np.bincount(inv, weights=mass*field**a, minlength=len(chart))
    mass1 = np.bincount(inv, weights=mass*g, minlength=len(chart))
    num1 = np.bincount(inv, weights=mass*g*field**a, minlength=len(chart))
    out = {}
    for taper in TAPERS:
        for strength in STRENGTHS:
            k = strength*np.clip((1-coverage)/taper, 0., 1.)
            w = np.maximum(mass0-k*mass1, 0.)
            num = np.maximum(num0-k*num1, 0.)
            d = (num/np.maximum(w, 1e-9))**(1/a)
            raw = (np.sum(w*d**b)/max(np.sum(w),1e-9))**(1/b)
            score = float(M.postprocess(s, np.array([raw]), p)[0])
            out[f'{strength:.2f}_{taper:.2f}'] = score
    return out


def main():
    model = load_model('detail'); base = ROOT/'dataset'/'spm_dataset-0.4.0'
    labels = json.loads((base/'labels.json').read_text(encoding='utf-8'))
    files = sorted({r['file'] for r in labels}); results = {}
    start = time.perf_counter()
    for index, name in enumerate(files, 1):
        notes = role.canonical(engine.parser.parse_file(str(base/name)))
        if clock.plan(notes) is not None: raise ValueError(f'Integer times required: {name}')
        picked = {}
        def probe(s, field, g, coverage, p): picked.update(candidates(s, field, g, coverage, p))
        baseline = _native(notes, model, rc_probe=probe)
        align = model.alignment['7']
        factor = lambda x: align['scale']*x**align['power']
        results[name] = {'baseline': factor(baseline[4]), 'coverage': baseline[3],
                         'candidates': {k: factor(v) for k,v in picked.items()}}
        if index % 50 == 0: print(f'{index}/{len(files)} {time.perf_counter()-start:.0f}s', flush=True)
    dest = ROOT/'results'/'rc_experiment.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for key in ('baseline', *(f'{strength:.2f}_{taper:.2f}' for taper in TAPERS for strength in STRENGTHS)):
        parts = []
        for group in ('all','hb','rc','mix'):
            pts=[]
            for r in labels:
                lab = r['labels'].get('rc') or {}
                if lab.get('sr') is None or (group != 'all' and r.get('sort') != group): continue
                row=results[r['file']]; x=row['baseline'] if key=='baseline' else row['candidates'].get(key,row['baseline'])
                pts.append((x,lab['sr']))
            x,y=np.array(pts).T; parts.append(f'{group} n={len(x)} rho={spearmanr(x,y).statistic:.4f} mae={np.mean(abs(x-y)):.3f} bias={np.mean(x-y):+.3f}')
        print(key, ' | '.join(parts))

if __name__ == '__main__': main()
