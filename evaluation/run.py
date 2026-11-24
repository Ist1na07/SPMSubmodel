"""Reproducible dataset and course scoring; output is checkpointed JSON Lines."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from functools import lru_cache
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rcln import rate_file
from spm_rating import load_model

ALGORITHM = 'spm-v130-local-branch'


@lru_cache(maxsize=2)
def model_for(name):
    return load_model(name)


def score(job):
    path, name = job
    row = {'path': path.relative_to(ROOT).as_posix(), 'algorithm': ALGORITHM}
    try:
        return {**row, **rate_file(path, model_for(name), scale='reference')}
    except Exception as exc:
        return {**row, 'error': f'{type(exc).__name__}: {exc}'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('collection', choices=['7k', '4k', '6k', 'courses'])
    ap.add_argument('--model', choices=['detail', 'compact'], default='detail')
    ap.add_argument('--workers', type=int, choices=range(1, 5), default=1)
    ap.add_argument('--out', type=Path, help='Output JSON Lines path (default: results/<collection>-<model>-v130.jsonl)')
    args = ap.parse_args()
    folders = {'7k': 'spm_dataset-0.4.0', '4k': 'spm_dataset_4k-0.1.0',
               '6k': 'spm_dataset_6k-0.1.0'}
    if args.collection == 'courses':
        paths = sorted((ROOT/'maps').rglob('*.osu'))
    else:
        base = ROOT/'dataset'/folders[args.collection]
        records = json.loads((base/'labels.json').read_text(encoding='utf-8'))
        paths = sorted({base/row['file'] for row in records})
    out = args.out if args.out else ROOT/'results'/f'{args.collection}-{args.model}-v130.jsonl'
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        previous = [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
        if any(row.get('algorithm') != ALGORITHM for row in previous):
            raise ValueError(f'{out} contains results from a different algorithm; move or delete it before scoring.')
        done = {r['path'] for r in previous}
    start = time.perf_counter()
    jobs = [(path, args.model) for path in paths if path.relative_to(ROOT).as_posix() not in done]
    pool = ProcessPoolExecutor(max_workers=args.workers) if args.workers > 1 else nullcontext()
    with pool as workers, out.open('a', encoding='utf-8') as f:
        rows = workers.map(score, jobs, chunksize=3) if workers is not None else map(score, jobs)
        for i, row in enumerate(rows, 1):
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n'); f.flush()
            if i%25 == 0 or i == len(jobs):
                print(f'{args.collection} {i}/{len(jobs)} elapsed={time.perf_counter()-start:.0f}s', flush=True)

if __name__ == '__main__': main()
