# SPM RC and long-note difficulty

[简体中文](README.zh-CN.md) · [Research and evaluation](docs/research.md)

This project provides two whole-chart difficulty scores for osu!mania 4K, 6K and 7K charts. RC describes the head-note pattern after turning every long note into a tap. LN describes the difficulty of sections containing long-note play, with a reduction when those sections occupy only a small part of the chart. The same call also returns the original SPM score.

The implementation uses the detailed or compact model of [SPM Rating](https://github.com/Ist1na07/SPMRating) at commit `a914a405d8e9a77f94c0518567c37511b0b7ac05`. At that commit the upstream version is **1.2.0-rc3**, a release candidate; a final 1.2.0 tag was not present when this project was evaluated. The checkout is in `SPMRating/`. The RC/LN code uses internal upstream interfaces, so replacing that checkout requires a new compatibility and evaluation pass.

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

`rate_notes` also accepts an upstream parsed Notes object. `model` can be `detail` or `compact`. The detailed model was used for the dataset evaluation and the LN coverage threshold; the compact model has passed the identity tests but has not been separately calibrated on these datasets. A `cancel` callback may be passed to stop between fractional-time phases. A score requires at least two valid physical heads and follows upstream duplicate and conflicting-object rules.

The default `raw` scale is the upstream Python API's native scale. `reference` applies the **same per-key-count upstream alignment** to all three scores. The 7K reference scale is aligned with the supplied 7K labels; 4K and 6K reference scores use their own label domains. Compare scores within the same key count, model, rate and scale. `ln_coverage` is the fraction of engagement mass covered by the smoothed LN presence signal, not a fraction of LN heads.

The interface currently scores whole charts. It supports the upstream shared-phase treatment of fractional original timestamps; charts with many distinct fractional times may require many passes. Segment scoring is a separate research task.

## Reproduce the evaluation

The datasets and course maps are not distributed in this repository. To reproduce the evaluation, place the corresponding inputs under `dataset/` and `maps/`. Results are checkpointed as JSON Lines in the local `results/` directory; remove or move the relevant result file before a clean rerun. Each input failure is recorded rather than silently skipped.

```bash
python evaluation/run.py 7k
python evaluation/run.py 4k
python evaluation/run.py 6k
python evaluation/run.py courses
python evaluation/report.py
python evaluation/calibrate.py
```

For compact results, add `--model compact` to each scoring command. The report currently summarizes the detailed model. See the research report for definitions, metrics, sample counts, limitations and the course comparison. The upstream source retains its own MIT license and notices in `SPMRating/`.
