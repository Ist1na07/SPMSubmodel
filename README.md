# SPM RC and long-note difficulty

[简体中文](README.zh-CN.md) · [Research and evaluation](docs/research.md)

Score the same osu!mania 4K, 6K or 7K chart three ways: the original SPM score, RC difficulty for the tap pattern at note heads, and LN difficulty for play involving holds. The branches use the same difficulty engine and log-logistic row aggregation as SPM. They change how much each row contributes to the score.

The submodule pins [SPM Rating v1.3.0, revision 2](https://github.com/Ist1na07/SPMRating/tree/4cbccb5de77e592d201d475041c67aa339ba544a). The branch scorer uses its native engine interfaces.

## Run

Use Python 3.13 from this directory:

```bash
git submodule update --init --recursive
python -m pip install -r SPMRating/requirements.txt
python -m unittest discover -s tests -v
```

```python
from rcln import rate_file, rate_content

scores = rate_file("chart.osu", model="detail", rate=1.0, scale="raw")
print(scores["spm"], scores["rc"], scores["ln"], scores["ln_coverage"])

with open("chart.osu", encoding="utf-8-sig") as f:
    same = rate_content(f.read(), model="detail", scale="reference")
```

`rate_notes` also accepts an upstream parsed Notes object. Choose `detail`, `compact` or `detail-4k`. Dataset metrics use `detail`. A chart needs at least two physical note heads and follows upstream rules for duplicate and conflicting objects.

The default `raw` scale matches the upstream Python API. `reference` applies the upstream calibration for the selected key count to all three scores. On a pure tap chart, RC equals SPM and raw LN is zero; the reference scale maps that zero to its calibrated value.

On a pure hold chart, RC is generally close to the SPM score of its heads played as taps. On a mixed chart, difficult tap passages can score higher than whole-chart SPM. `ln_coverage` is a diagnostic between 0 and 1: the effective number of long-note heads divided by the total number of heads. Each long-note head counts according to local hold demand; tap-only charts return exactly `0.0`. The fraction is reported separately from the score.

The interface currently scores whole charts. It supports the upstream shared-phase treatment of fractional original timestamps; charts with many distinct fractional times may require many passes. Segment scoring is a separate research task.

## Reproduce the evaluation

The datasets and course maps are not distributed in this repository. To reproduce the evaluation, place the corresponding inputs under `dataset/` and `maps/`. Results are checkpointed as JSON Lines in the local `results/` directory; remove or move the relevant result file before a clean rerun. Each input failure is recorded rather than silently skipped.

```bash
python evaluation/run.py 7k
python evaluation/run.py 4k
python evaluation/run.py 6k
python evaluation/run.py courses
python evaluation/report.py
```

Use `--workers 4` to score files in parallel. The report summarizes the `detail` profile; add `--model compact` to a scoring command to generate a separate set of `compact` results. The [research report](docs/research.md) lists the dataset versions, scoring rules and measured results. The upstream source retains its MIT license and notices in `SPMRating/`.
