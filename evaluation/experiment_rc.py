"""Compare difficulty-ratio modulation parameters on 7K development labels."""
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rcln.engine import _native, _rc_windows, M
from spm_rating import engine, load_model, role, clock

STRENGTHS = (0.75, 0.90, 0.97)
LIMITS = (1.40, 1.60, 1.80, 2.00)


def candidates(full, rice, full_field, rice_field, g, ln_score, head_score, p):
    mass, rc, ln = _rc_windows(full, rice, full_field, rice_field, g, p)
    local_share = np.clip(ln/np.maximum(rc, 1e-9), 0., 1.)
    global_ratio = ln_score/max(head_score, 1e-9)
    power = max(float(p['aggC_pw2']), .05)
    out = {}
    for limit in LIMITS:
        for strength in STRENGTHS:
            intensity = strength*np.clip((limit-global_ratio)/.40, 0., 1.)
            weight = mass*(1.-intensity*local_share)
            raw = (np.sum(weight*rc**power)/max(np.sum(weight), 1e-9))**(1/power)
            out[f'{strength:.2f}_{limit:.2f}'] = float(M.postprocess(rice, np.array([raw]), p)[0])
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
        def probe(*args): picked.update(candidates(*args))
        scored = _native(notes, model, rc_probe=probe)
        align = model.alignment['7']
        factor = lambda x: align['scale']*x**align['power']
        results[name] = {'spm': factor(scored[0]), 'candidates': {k: factor(v) for k,v in picked.items()}}
        if index % 50 == 0: print(f'{index}/{len(files)} {time.perf_counter()-start:.0f}s', flush=True)
    dest = ROOT/'results'/'rc_ratio_experiment.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for limit in LIMITS:
        for strength in STRENGTHS:
            key = f'{strength:.2f}_{limit:.2f}'; parts = []
            for group in ('all','hb','rc'):
                pts=[]
                for r in labels:
                    lab = r['labels'].get('rc') or {}
                    if lab.get('sr') is None or (group != 'all' and r.get('sort') != group): continue
                    row = results[r['file']]; x = row['candidates'].get(key,row['spm'])
                    pts.append((x,lab['sr']))
                x,y=np.array(pts).T
                parts.append(f'{group} n={len(x)} rho={spearmanr(x,y).statistic:.4f} mae={np.mean(abs(x-y)):.3f} bias={np.mean(x-y):+.3f}')
            print(key, ' | '.join(parts))

if __name__ == '__main__': main()
