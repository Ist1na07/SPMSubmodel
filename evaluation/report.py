"""Summarize available score files without interpreting missing labels as zero."""
import json
import argparse
import re
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {'7k': 'spm_dataset-0.4.0', '4k': 'spm_dataset_4k-0.1.0', '6k': 'spm_dataset_6k-0.1.0'}
SUFFIX = ''


def read(name):
    path = ROOT/'results'/f'{name}-detail{SUFFIX}.jsonl'
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def metric(name, points):
    if len(points) < 3: return
    x, y = np.array(points, float).T
    rho = spearmanr(x, y).statistic
    print(f'{name}: n={len(x)} rho={rho:.5f} MAE={np.mean(abs(x-y)):.4f} bias={np.mean(x-y):+.4f}')


def dataset(mode):
    base = ROOT/'dataset'/DATASETS[mode]
    labels = json.loads((base/'labels.json').read_text(encoding='utf-8'))
    scored = read(mode); scores = {x['path']: x for x in scored if 'error' not in x}
    print(f'\n{mode}: files scored={len(scores)} errors={len(scored)-len(scores)} label records={len(labels)}')
    for row in scored:
        if 'error' in row: print('  ERROR', row['path'], row['error'])
    joined = [(r, scores.get((base/r['file']).relative_to(ROOT).as_posix())) for r in labels]
    joined = [(r, s) for r, s in joined if s]
    for out, lab in [('spm', 'overall'), ('rc', 'rc'), ('ln', 'ln')]:
        pairs = []
        for r, s in joined:
            v = r['labels'].get(lab) or {}
            if v.get('sr') is not None and not v.get('below_range'): pairs.append((s[out], v['sr']))
        metric(f'{out} vs {lab}', pairs)
        if lab in ('rc', 'ln'):
            metric(f'spm vs {lab}', [(s['spm'], r['labels'][lab]['sr']) for r,s in joined
                   if r['labels'].get(lab) and r['labels'][lab].get('sr') is not None
                   and not r['labels'][lab].get('below_range')])
    for group, field in [('rc', 'rc'), ('ln', 'ln'), ('hb', 'rc'), ('hb', 'ln')]:
        subset = [(r, s) for r, s in joined if r.get('sort') == group]
        pairs = [(s[field], r['labels'][field]['sr']) for r,s in subset
                 if r['labels'].get(field) and r['labels'][field].get('sr') is not None and not r['labels'][field].get('below_range')]
        metric(f'{group} {field}', pairs)
        if group in ('rc', 'ln') and subset:
            diff = [abs(s[field]-s['spm']) for r,s in subset]
            print(f'  {group} |branch-spm| median={np.median(diff):.4f} p90={np.percentile(diff,90):.4f}')
    if mode == '7k' and joined and 'rc_head_only' in joined[0][1]:
        for group in ('rc', 'hb', 'ln', 'mix'):
            subset = [(r,s) for r,s in joined if r.get('sort') == group]
            change = np.array([s['rc']-s['rc_head_only'] for r,s in subset])
            pairs = [(s['rc_head_only'],r['labels']['rc']['sr']) for r,s in subset
                     if r['labels'].get('rc') and r['labels']['rc'].get('sr') is not None]
            if len(change):
                print(f'  {group} RC change n={len(change)} median={np.median(change):+.4f} '
                      f'p90_abs={np.percentile(abs(change),90):.4f} max_abs={max(abs(change)):.4f}')
            metric(f'{group} head-only vs rc', pairs)
            if group == 'hb':
                improvements = [abs(s['rc_head_only']-r['labels']['rc']['sr'])-abs(s['rc']-r['labels']['rc']['sr'])
                                for r,s in subset if r['labels'].get('rc') and r['labels']['rc'].get('sr') is not None]
                print(f'  hb absolute-error changes: improved={sum(x>1e-9 for x in improvements)} '
                      f'worse={sum(x < -1e-9 for x in improvements)} '
                      f'unchanged={sum(abs(x)<=1e-9 for x in improvements)}')
    below = [s['ln'] for r,s in joined if (r['labels'].get('ln') or {}).get('below_range')]
    if below: print(f'  below_range n={len(below)} LN median={np.median(below):.4f} p90={np.percentile(below,90):.4f} max={max(below):.4f}')
    if mode in ('4k', '6k') and scores and all('rc_head_only' in s for s in scores.values()):
        delta = np.array([s['rc']-s['rc_head_only'] for s in scores.values()])
        print(f'  chart RC change n={len(delta)} median={np.median(delta):+.4f} '
              f'p90_abs={np.percentile(abs(delta),90):.4f} max_abs={max(abs(delta)):.4f}')
    if mode == '4k':
        for group in ('jack', 'speed', 'stamina', 'tech', 'course', 'ln'):
            points = [(s['ln' if group == 'ln' else 'rc'],r['labels']['overall']['sr'])
                      for r,s in joined if r.get('subset') == group and r['labels'].get('overall')]
            metric(f'{group} branch vs overall', points)


def courses():
    groups = {}
    for row in read('courses'):
        if 'error' in row: print('COURSE ERROR', row); continue
        path = ROOT/row['path']; name = path.parent.name.lower()
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        version = next((line.split(':',1)[1].strip() for line in text.splitlines() if line.startswith('Version:')), '')
        low = version.lower()
        extra = {'extra-alpha':11, 'extra-beta':12, 'extra-gamma':13, 'extra-delta':14, 'extra-epsilon':15}
        dan = next((v for k,v in extra.items() if k in low), None)
        m = re.search(r'~\s*(\d+)(?:st|nd|rd|th)\s*~', low) or re.search(r'(\d+)(?:st|nd|rd|th)\s*dan', low)
        if dan is None and m: dan = int(m.group(1))
        if dan is None and 'start dan' in low: dan = 0
        if dan is None: print('UNRECOGNIZED', row['path'], version); continue
        mode = str(row['key_count'])+'k'; kind = 'ln' if 'ln dan' in name else 'rc'
        groups.setdefault((mode,kind), []).append((dan,row[kind]))
    for mode in ('4k','6k'):
        fits = {}
        for kind in ('rc','ln'):
            v = sorted(groups.get((mode,kind), [])); x,y = np.array(v).T
            fits[kind] = np.polyfit(x,y,1)
            print(f'{mode} {kind} courses n={len(x)} rho={spearmanr(x,y).statistic:.5f} fit={fits[kind][0]:.5f}*dan+{fits[kind][1]:.5f} range={int(min(x))}-{int(max(x))}')
            print('  nodes:', ', '.join(f'{int(a)}:{b:.3f}' for a,b in v))
        rc, ln = groups[(mode,'rc')], groups[(mode,'ln')]
        lo = int(max(min(x for x,_ in rc),min(x for x,_ in ln)))
        hi = int(min(max(x for x,_ in rc),max(x for x,_ in ln)))
        delta = np.polyval(fits['ln'],np.arange(lo,hi+1))-np.polyval(fits['rc'],np.arange(lo,hi+1))
        print(f'{mode} same-dan fitted LN-RC mean abs={np.mean(abs(delta)):.4f} ends={delta[0]:+.4f},{delta[-1]:+.4f}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--suffix', default='', help='Suffix after detail in result filenames, such as -rc11')
    SUFFIX = ap.parse_args().suffix
    for mode in DATASETS: dataset(mode)
    courses()
