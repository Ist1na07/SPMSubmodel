"""Reproducible dataset and course scoring; output is checkpointed JSON Lines."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rcln import rate_file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('collection', choices=['7k', '4k', '6k', 'courses'])
    ap.add_argument('--model', choices=['detail', 'compact'], default='detail')
    ap.add_argument('--out', type=Path, help='Output JSON Lines path (default: results/<collection>-<model>.jsonl)')
    args = ap.parse_args()
    folders = {'7k': 'spm_dataset-0.4.0', '4k': 'spm_dataset_4k-0.1.0',
               '6k': 'spm_dataset_6k-0.1.0'}
    if args.collection == 'courses':
        paths = sorted((ROOT/'maps').rglob('*.osu'))
    else:
        base = ROOT/'dataset'/folders[args.collection]
        records = json.loads((base/'labels.json').read_text(encoding='utf-8'))
        paths = sorted({base/row['file'] for row in records})
    out = args.out if args.out else ROOT/'results'/f'{args.collection}-{args.model}.jsonl'
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        previous = [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
        if any(row.get('algorithm') != 'rcln-1.2' for row in previous):
            raise ValueError(f'{out} contains results from a different algorithm; move or delete it before scoring.')
        done = {r['path'] for r in previous}
    start = time.perf_counter()
    with out.open('a', encoding='utf-8') as f:
        for i, path in enumerate(paths):
            key = path.relative_to(ROOT).as_posix()
            if key in done: continue
            try:
                row = {'path': key, 'algorithm': 'rcln-1.2', **rate_file(path, args.model, scale='reference')}
            except Exception as exc:
                row = {'path': key, 'algorithm': 'rcln-1.2', 'error': f'{type(exc).__name__}: {exc}'}
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n'); f.flush()
            if (i+1)%25 == 0 or i+1 == len(paths):
                print(f'{args.collection} {i+1}/{len(paths)} elapsed={time.perf_counter()-start:.0f}s', flush=True)

if __name__ == '__main__': main()
