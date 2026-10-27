# Model design and evaluation

[简体中文](research.zh-CN.md) · [Usage](../README.md)

## Components

The model uses SPM Rating 1.2.0-rc3 at commit `a914a405d8e9a77f94c0518567c37511b0b7ac05`. The parser embeds 4K and 6K charts in the seven-column frame; the scorer evaluates both the original and mirror views, combines their release demand, and includes shared-hand and finger-occupation costs. Recovery, cross-column transitions, the two-level section/window aggregate, and the fractional-time shared-phase extension are supplied by SPM Rating. The default `detail` model retains a conditional hold-duration component; the `compact` model disables it.

SPM, RC and LN share parsing, the head-based hand-contact and recovery calculations, and the full-chart difficulty field. RC also computes a difficulty field from a copy of the notes in which each long note is replaced by a tap at its head. A tap-only chart reuses its SPM score for RC. Input validation follows upstream physical-object rules.

## LN difficulty

For each row, the presence indicator marks an active long-note body, a long-note head, or the first row at or after a long-note tail. A tail later than the final row has no next row to mark. The indicator is smoothed with a 700 ms centered window, then square-rooted to give `g` between zero and one.

The original SPM two-level aggregate multiplies the engagement mass of each row by `g`, preserving the section and window geometry and the difficulty curve. Coverage `c` is the ratio of weighted to original engagement mass. SPM postprocessing uses `head_count × c` as its effective count, and the raw LN score is multiplied by `min(c / 0.40, 1)`. Reference-scale output uses the upstream per-key-count alignment. A chart with no long notes has zero LN difficulty. The LN score includes ordinary-note demand in long-note regions alongside release, coordination and finger-occupation demand.

## RC difficulty

The head-only difficulty field is aggregated using the same two-level windows as SPM. Each window's contribution is adjusted using its **local LN and RC difficulty estimates**, both measured in native difficulty-field units:

1. The RC estimate is the window's engagement-weighted power mean of the head-only field.
2. The LN estimate uses the full field, with engagement mass weighted by `g`. The window's LN coverage, defined using that same mass, supplies an exposure factor `min(window_coverage / 0.40, 1)`. This mirrors the LN branch's focus on long-note regions while keeping the two local estimates on comparable units.
3. The local ratio is `q = clamp(local_LN / max(local_RC, 1e-9), 0, 1)`.
4. The whole-chart ratio is `r = LN_score / max(head_only_score, 1e-9)`, using native postprocessed scores before reference alignment. Modulation strength is `0.90 × clamp((1.60 − r) / 0.40, 0, 1)`.
5. Multiply the window's RC engagement mass by `1 − strength × q`, then aggregate the window difficulties using SPM's second-level power mean and postprocessing.

The minimum window weight is 10% of its original mass. A high local LN-to-RC difficulty ratio reduces that window's contribution; an LN-dominated whole chart receives less modulation. The weights can either raise or lower the final RC score depending on the distribution of difficulty. All three outputs use the same selected `raw` or `reference` scale. The reference alignments are specific to each key count.

For fractional original timestamps, each shared rounding phase computes the fields, local ratios and branch scores separately. Raw scores are averaged over phases before reference alignment. Coverage is also averaged over phases.

## Parameter selection

The 7K development set supplied the full branch labels used to choose RC parameters. The parameter grid compared strengths 0.75, 0.90 and 0.97, and whole-chart ratio limits 1.40, 1.60, 1.80 and 2.00, with fade width 0.40. The chosen strength 0.90 and limit 1.60 provide a balance between label agreement on mixed charts and a gradual fade on LN-dominated charts. `python evaluation/experiment_rc.py` reproduces the grid on the supplied integer-time charts. The window and whole-chart LN exposure threshold is 0.40.

These parameters were selected on the available data. New independently labeled mixed charts and full 4K/6K branch labels would help assess transfer and whether different difficulty distributions need further treatment. The compact model has consistency tests; the numerical evaluation below uses the detailed model.

## Evaluation

Scores use the corresponding upstream `reference` scale. Spearman correlation measures ordering. MAE is the direct mean absolute difference against the labels, with no fitted regression. Missing branch labels are omitted; LN labels marked `below_range` are omitted from the numerical LN comparison. The 7K set has 332 charts and 334 label records, with two charts each having two label records. The data was available during development, so these results are in-sample.

| 7K comparison | Records | Spearman | Direct MAE |
|---|---:|---:|---:|
| SPM and overall labels | 334 | 0.98989 | 0.2303 |
| RC and RC labels | 200 | 0.98436 | 0.2561 |
| LN and valid LN labels | 180 | 0.98515 | 0.2664 |
| RC and RC labels on HB charts | 49 | 0.98329 | 0.3171 |

The HB RC mean signed error is −0.1512. Among 144 records with `below_range` LN labels, the LN score has median 0, 90th percentile 0.475 and maximum 8.105. Chart `bm_0204` is one example with a high LN score despite a `below_range` label; it is useful for investigating how local long-note passages relate to the annotation.

For 4K and 6K the available labels are overall difficulty labels, so they cannot directly validate individual branches. On 4K, SPM and overall labels have Spearman 0.98833 across 741 labeled records. RC and overall labels have correlations 0.98615, 0.98738, 0.98221 and 0.99070 for the jack, speed, stamina and tech subsets; LN and overall labels have correlation 0.98477 in the LN subset. On 2,343 scored 6K records, SPM and overall labels have Spearman 0.95722. The remaining chart, `bm6k_1460`, has conflicting simultaneous objects on one physical key and is rejected by the upstream input rules.

For the course checks, score is fitted linearly against dan on each RC and LN ladder. Over the overlapping integer dan range, the mean absolute difference of the fitted ladders is 0.235 on 4K dan 1–15 and 0.672 on 6K dan 0–9, in each key count's own reference scale. The 4K REFORM alpha through epsilon courses are interpreted as dan 11–15. For 7K, gamma, azimuth, zenith and stellium correspond to dan 11–14; the numerical `sr` labels are used as supplied and retain their dataset conversion.

## Checks and research directions

The test suite checks SPM against independent upstream scoring, pure taps, symmetry, speed changes, fractional time, scale conversion and invalid input. A controlled test varies the LN difficulty field while keeping the presence pattern and RC field fixed, and checks the resulting RC weighting. Dataset results and failure records can be generated locally with `evaluation/run.py` and summarized with `evaluation/report.py`.

Useful follow-up work includes fresh mixed-chart branch labels, matched examples with similar long-note quantities but different coordination difficulty, and segment-level validation. Charts with many distinct fractional timestamps can require many shared-phase passes. Headless holding segments and segment scoring are not provided by this whole-chart interface.
