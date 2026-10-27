# Research and evaluation

[简体中文](research.zh-CN.md) · [Usage](../README.md)

## Design

The baseline is SPM Rating 1.2.0-rc3 at commit `a914a405d8e9a77f94c0518567c37511b0b7ac05`, using its `detail` parameters. The previous submodel was built on SPM 1.0.0: it rated the head-only chart for RC and reweighted the original difficulty curve for LN. It assumed a single-level power-mean aggregation and treated several curves as independent of long notes.

The new scorer evaluates both the chart and its mirror, shares their averaged release curve, and combines each view with shared-hand contact costs and a cost for actions after finger occupation. It also uses continuous recovery and cross-column transition fields, a two-level section/window aggregate, and a shared-phase extension for fractional times. These details are retained in the full score and both branches. SPM's detail model retains a conditional hold-duration component; its compact model disables that component. The implementation makes a separate head-only structure and recalculates the long-note-sensitive numerical curves, sharing the parsed notes, head-based hand-contact and recovery calculations, and the original difficulty field used for LN. Charts without long notes reuse the full score directly for RC. This avoids a third full model run while preserving the independent head-only definition.

### RC

Replace each long note with a tap at the same head time and physical column, then score the resulting chart with the same SPM model and scale. The score therefore equals SPM on a tap-only chart. The original chart is validated before transformation, including the upstream rules for duplicate and conflicting objects.

### LN

1. Mark rows with an active long-note body, a long-note head, or the next row at or after a long-note tail. Heads and tails come from individual objects. A tail after the final row has no next row to mark.
2. Smooth the presence signal with SPM's 700 ms centered window and take its square root, yielding a row weight `g` between zero and one.
3. Multiply the SPM two-level aggregation's row engagement mass by `g`, keeping its original section and window geometry, power means, difficulty field and hold-aware weighting. Coverage `c` is the sum of weighted mass divided by the original mass.
4. Apply the SPM postprocessing with an effective head count of `head_count × c`. Multiply the resulting raw LN score by `min(c / 0.40, 1)`. Finally apply the upstream reference alignment if requested.

On a fully covered chart, the weighting and count approach the SPM calculation. On a chart without long notes, coverage and LN difficulty are zero. A mixed section retains ordinary-note difficulty alongside its long-note coordination, release, and finger-occupation costs. The coverage reduction describes whole-chart exposure, and a difficult long-note passage can still score highly when it occupies a substantial fraction of the chart.

For fractional timestamps, each shared rounding phase computes these steps separately, and the raw branch scores are averaged before the reference alignment. Reported coverage is the phase-weighted average; applying the formula to that average alone need not reproduce the LN score.

## Parameter selection

The presence window and square-root smoothing were carried over from the previous submodel. On the supplied 7K development labels, coverage thresholds 0.05, 0.10, 0.15, 0.20, 0.30 and 0.40 and attenuation exponents 0.5 and 1 were compared. A linear reduction with threshold 0.40 reduced the 90th percentile of `below_range` scores from 6.95 to 0.48 on the reference scale; valid-LN Spearman changed from 0.98467 to 0.98515 and MAE from 0.2701 to 0.2664. `python evaluation/calibrate.py` reproduces the candidate comparison using the saved integer-time scores. The threshold is a practical choice within this panel, not a measurement of a universal boundary. The 4K and 6K courses provide a separate alignment check; they do not provide full branch labels. No per-key branch scale multiplier was fitted.

## Results

The tables use `detail` and upstream `reference` scores. Spearman correlation measures ordering; MAE is the direct mean absolute difference on the relevant reference label scale, without fitting a new regression. Labels marked `below_range` are excluded from numerical LN-label metrics. A missing branch label is not treated as zero. The two records sharing a 7K beatmap are retained as separate labels. All supplied labels and maps were available during development, so the results are in-sample rather than an independent estimate of generalization.

The saved scores were initially computed without the final coverage reduction; their LN values were then converted to the selected reduction using saved coverage and the upstream alignment. All supplied charts use integer original-clock times, so this conversion is equivalent to applying the reduction during scoring, up to floating-point rounding. Sampled results were checked against fresh scoring.

| 7K comparison | Labels | Spearman | Direct MAE |
|---|---:|---:|---:|
| SPM vs overall | 334 | 0.98989 | 0.2303 |
| RC vs RC | 200 | 0.98305 | 0.2698 |
| SPM vs RC, comparison | 200 | 0.98004 | 0.3239 |
| LN vs valid LN | 180 | 0.98515 | 0.2664 |
| SPM vs valid LN, comparison | 180 | 0.98789 | 0.2424 |

Among 146 RC-type labels, the median and 90th percentile of `abs(RC − SPM)` are 0.0000 and 0.0217. Among 130 LN-type labels, the corresponding `abs(LN − SPM)` values are 0.0035 and 0.0694. The 144 `below_range` records have median LN 0, 90th percentile 0.475, and maximum 8.105. For example, `bm_0204` has coverage 0.373 and LN 8.105 despite a `below_range` annotation. It is a useful counterexample for refining how short LN passages and label semantics interact.

For 4K, SPM vs overall has correlation 0.98833 on 741 labeled records. The RC branch correlates 0.98605, 0.98859, 0.98349 and 0.99026 with the overall labels for the jack, speed, stamina and tech subsets respectively; the LN branch correlates 0.98477 with overall labels in the LN subset. These are subset-level checks because 4K lacks complete branch labels.

For 6K, SPM vs overall has correlation 0.95722 on 2,343 scored records. One additional chart, `bm6k_1460`, has conflicting simultaneous objects on the same physical key and is rejected by the upstream input rules; its failure is recorded in the results file.

The courses use independent per-mode reference units. A linear fit of score against dan is compared over the overlapping integer dan range; duplicate course levels remain separate observations. The fitted mean absolute difference between LN and RC ladders is 0.247 for 4K dan 1–15 and 0.672 for 6K dan 0–9. The fitted difference changes from +0.561 to −0.284 in 4K, and from +1.147 to −1.271 in 6K. Course ladders are approximate anchors and their differing slopes remain visible. Individual nodes and fits can be regenerated with `evaluation/report.py`.

4K REFORM alpha through epsilon are interpreted as dan 11–15. For 7K, gamma, azimuth, zenith and stellium refer to dan 11–14. The 7K branch comparison uses the numerical `sr` values already supplied in `labels.json`; its dataset metadata records the separate conversion used to produce those values. The course-name numbering is not substituted into those numeric labels.

## Verification and further work

Automated tests compare SPM and RC against independent upstream calls across 4K, 6K, 7K, both models, taps, mixed patterns, long notes and speed changes. They also check mirror symmetry, fractional-time averaging, scale conversion, cancellation and invalid input. On 30 selected 7K charts after warm-up, this implementation took 3.016 seconds versus 3.351 seconds for two independent upstream scores of parsed original and head-only notes; this small sample includes no parsing and is hardware-dependent. LN is obtained from the already computed full field.

The LN threshold and old smoothing parameters need validation on fresh, independently labeled mixed charts. Full RC/LN labels for 4K and 6K would clarify transfer across modes. Fractional charts with many phase breakpoints, headless holds and segments need dedicated performance or interface work. Tests cover compact model consistency, while its branch calibration and dataset quality remain to be studied. The evaluation scripts generate chart-level scores and failure records locally in `results/`.
