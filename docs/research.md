# Model design and evaluation

[简体中文](research.zh-CN.md) · [Usage](../README.md)

## One SPM engine for all three scores

Submodel uses [SPM Rating v1.3.0, revision 2](https://github.com/Ist1na07/SPMRating/tree/4cbccb5de77e592d201d475041c67aa339ba544a). It uses the upstream feature builder and forward pass, including the selected profile's mirror handling, release and coordination demand, jack-versus-technique interaction, and stamina. The native row-mass calculation applies the upstream peak envelope and supplies a difficulty and an engagement weight for each row.

All three scores use the upstream log-logistic row sigmoid solver. It finds the skill value at which predicted accuracy over the weighted rows reaches the profile's target. The branches then use the same native length correction, high-end compression and calibration as SPM. The full-chart pass supplies both SPM and LN, and RC uses a second pass with each long note replaced by a tap at its head. Pure tap charts can reuse the full pass.

## How each branch weights rows

Define the long-note presence `g` by measuring the fraction of a centered 700 ms window covered by the union of long-note intervals. Each interval extends 75 ms before the head and after the tail so that nearby press and release actions count. Take the square root of the fraction. Overlapping holds share the same time coverage, and gaps without holds remain empty. This signal is evaluated at the native row times, including the support row that SPM adds for a sustained chord.

- **LN:** Multiply the full chart's row weights by `g` and solve the same accuracy equation. The fraction `c` of engagement weight that remains is reported as `ln_coverage`. Use `head_count × c` for the native length correction, then multiply the raw result by `c / (c + 0.15 × (1 − c))`. This makes the contribution of sparse LN content tend smoothly to zero and approaches the native SPM calculation as coverage approaches one.
- **RC:** Start with the head-only field and row weights. At each head row, divide the full chart's local demand weighted by `g` by the head-only demand (with a small numerical floor). For this local ratio `r`, multiply the RC row weight by `0.10 + 0.90 / (1 + 4r²)`. Rows with substantial local LN demand contribute less, and every row retains a positive share of its weight. The solver uses the original head count.

The same formulas run on all charts. There is no chart label, classifier, or whole-chart ratio used to select a branch or disable RC modulation. Key count comes from the parsed chart and is used by the upstream geometry and calibration. Category labels are read only by the offline evaluation.

Each upstream clock phase computes the branch scores before averaging the raw results. The optional reference output applies the same monotone, piecewise-linear calibration to all three raw scores for that key count. In particular, reference LN on a pure tap chart is the calibration's value at raw zero.

## Evaluation

The table uses the `detail` profile and 7K reference units. Spearman measures agreement in ordering; MAE is the mean absolute difference to the supplied numerical label. Missing branch labels and LN labels marked `below_range` are excluded from the corresponding numerical comparisons. These are development-set results, so independent mixed-chart labels would help assess generalization.

| 7K comparison | Label records | Spearman | MAE |
|---|---:|---:|---:|
| SPM vs overall | 334 | 0.98595 | 0.2295 |
| RC vs RC | 200 | 0.98423 | 0.2313 |
| LN vs LN | 180 | 0.98140 | 0.2844 |
| RC vs RC on hybrid charts | 49 | 0.98375 | 0.2235 |

For the 146 RC-labeled charts in the RC category, the absolute gap from SPM has a median of 0.000 and a 90th percentile of 0.016. For the 130 charts in the LN category, the LN-to-SPM gap is 0.007 at the median and 0.047 at the 90th percentile. On those same LN charts, RC differs from independently scored head-only SPM by 0.063 at the median and 0.201 at the 90th percentile.

The 4K and 6K datasets supply overall labels. SPM's Spearman correlation is 0.98550 on 741 valid 4K labels and 0.95926 on 2,343 scored 6K charts. The upstream parser rules reject one 6K chart, `bm6k_1460`, because simultaneous objects on the same key have conflicting tails.

For a branch-level check, scores were fitted linearly against dan for each RC and LN course ladder. The mean absolute gap between the fitted ladders at shared dan levels is **0.242 dan** for 4K (1–15) and **0.507 lv** for 6K (0–9). These are separate reference scales. The 4K REFORM alpha through epsilon courses correspond to 11–15 dan. The 7K labels use the supplied numerical conversion; gamma, azimuth, zenith and stellium refer to dan 11–14.

Run the commands in the [README](../README.md#reproduce-the-evaluation) to generate individual scores, ranking statistics and course fits. Automated tests check native SPM parity for all supported profiles and key counts, tap-only behavior, mirror symmetry, speed changes, fractional timing, static sustain and reference calibration.
