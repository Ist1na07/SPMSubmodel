"""Inspect coverage-gate choices on the supplied integer-time 7K labels."""
import json
from pathlib import Path
import sys

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import rcln  # exposes the pinned upstream checkout
from spm_rating import load_model


def main():
    base = ROOT/'dataset'/'spm_dataset-0.4.0'
    labels = json.loads((base/'labels.json').read_text(encoding='utf-8'))
    rows = [json.loads(x) for x in (ROOT/'results'/'7k-detail.jsonl').read_text(encoding='utf-8').splitlines()]
    scores = {row['path']: row for row in rows if 'error' not in row}
    model = load_model('detail'); align = model.alignment['7']
    valid, below = [], []
    for rec in labels:
        score = scores.get((base/rec['file']).relative_to(ROOT).as_posix())
        label = rec['labels'].get('ln')
        if not score or not label: continue
        cov = score['ln_coverage']; gate = min(cov/.4, 1.)
        raw = (score['ln']/align['scale'])**(1./align['power'])/gate if gate else max(model.parameters['calib_b'], 0.)
        if label.get('below_range'): below.append((raw,cov))
        elif label.get('sr') is not None: valid.append((raw,cov,label['sr']))
    print(f'valid={len(valid)} below_range={len(below)}')
    for threshold in (.05,.10,.15,.20,.30,.40):
        for exponent in (.5,1.):
            def pred(raw,cov):
                return align['scale']*(raw*min(cov/threshold,1.)**exponent)**align['power']
            x = np.array([pred(raw,cov) for raw,cov,_ in valid]); y = np.array([y for _,_,y in valid])
            z = [pred(raw,cov) for raw,cov in below]
            print(f'threshold={threshold:.2f} exponent={exponent:.1f} rho={spearmanr(x,y).statistic:.5f} '
                  f'mae={np.mean(abs(x-y)):.4f} below_p90={np.percentile(z,90):.4f} below_max={max(z):.4f}')

if __name__ == '__main__': main()
