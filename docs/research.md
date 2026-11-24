# Model design and evaluation

[简体中文](research.zh-CN.md) · [Usage](../README.md)

## One SPM engine for all three scores

Submodel uses [SPM Rating v1.3.0, revision 2](https://github.com/Ist1na07/SPMRating/tree/4cbccb5de77e592d201d475041c67aa339ba544a). It uses the upstream feature builder and forward pass, including the selected profile's mirror handling, release and coordination demand, jack-versus-technique interaction, and stamina. The native row-mass calculation applies the upstream peak envelope and supplies a difficulty and an engagement weight for each row.

All three scores use the upstream log-logistic row sigmoid solver. It finds the skill value at which predicted accuracy over the weighted rows reaches the profile's target. The branches then use the same native length correction, high-end compression and calibration as SPM. The full-chart pass supplies both SPM and LN, and RC uses a second pass with each long note replaced by a tap at its head. Pure tap charts can reuse the full pass.

## How each branch weights rows

Long-note demand starts with the upstream release, coordination and finger-role terms. The upstream support row also supplies demand for a sustained chord with a single head time. A positive difference between the full chart and its head-only version contributes in proportion to the physical hold demand already present. This comparison uses difficulty before the stamina multiplier.

Average that load and the full difficulty in a triangular window whose width is the upstream release span. Call the means `L` and `D`. The local physical share is `s = cL / hypot(cL, D)`, with zero for empty rows. A second local measure `h` combines nearby sustained heads with occupied fingers. The resulting hold membership is `w = s × h`. These are continuous weights derived from the chart; category labels are used only in evaluation.

- **LN:** Multiply the full-chart row difficulty by `s` and the row weight by `w`. This branch uses the upstream row weights without the penalty for fingers already held down. Apply the native accuracy solver, then multiply its skill estimate `u₀` by `N² / (N² + N₀²)`, where `N` is the sum of `w` over long-note heads. Use `N` in the native length correction. At the end, reintroduce the native additive offset in proportion to `u / (u + 0.35)`, where `u` is the skill after the exposure adjustment. Raw LN tends to zero as effective exposure disappears.
- **RC:** Score the original note heads as taps. Start with that head-only field and its row weights. Average `w²` in a triangular window set by the upstream stamina time constant to get `nearby`. At each head row, multiply its weight by `1 + ((1 − α) / α) × nearby × (1 − h)² × (1 − w²)`. This gives extra weight to relatively clean tap rows near sustained hold passagework. Apply the native solver and length correction with the original head count. The RC score can exceed whole-chart SPM when the tap passages are harder.

`ln_coverage` is the effective long-note head count `N` divided by the total number of heads. It is an output diagnostic; the LN exposure formula uses the absolute count `N`.

The fixed settings are `c = 16` for local LN demand, `N₀ = 30` effective heads for half exposure, and `α = 0.16` for RC weighting.

Each upstream clock phase computes the branch scores before averaging the raw results. The optional reference output applies the same monotone, piecewise-linear calibration to all three raw scores for that key count. In particular, reference LN on a pure tap chart is the calibration's value at raw zero.

## Evaluation

The table uses the `detail` profile and 7K reference units. Spearman measures agreement in ordering; MAE is the mean absolute difference to the supplied numerical label. Missing branch labels and LN labels marked `below_range` are excluded from the corresponding numerical comparisons. These are development-set results, so independent mixed-chart labels would help assess generalization.

| 7K comparison | Label records | Spearman | MAE |
|---|---:|---:|---:|
| SPM vs overall | 334 | 0.98595 | 0.2295 |
| RC vs RC | 200 | 0.98139 | 0.2544 |
| LN vs LN | 180 | 0.98298 | 0.2453 |
| RC vs RC on hybrid charts | 49 | 0.98478 | 0.3168 |
| LN vs LN on hybrid charts | 48 | 0.98152 | 0.2049 |

Across the 144 records marked `below_range`, LN has a median of 0.6557, a 90th percentile of 0.8418 and a maximum of 6.9984.

For the 146 records in the RC category, the absolute difference between RC and SPM has a median of 0.000 and a 90th percentile of 0.021. For the 130 records in the LN category, the absolute difference between LN and SPM has a median of 0.077 and a 90th percentile of 0.145. In that same group, the absolute difference between RC and head-only SPM has a median of 0.012 and a 90th percentile of 0.087.

The 4K and 6K datasets supply overall labels. SPM's Spearman correlation is 0.98550 on 741 valid 4K labels and 0.95926 on 2,343 scored 6K charts. On the 102 4K records in the LN category, LN scores compared with overall labels give a Spearman correlation of 0.98085 and a mean absolute error of 0.7034. The upstream parser rejects `bm6k_1460` because simultaneous objects on the same key have conflicting tails.

For a branch-level check, scores were fitted linearly against dan for each RC and LN course ladder. The mean absolute gap between the fitted ladders at shared dan levels is **0.2363 dan** for 4K (1–15) and **0.6165 lv** for 6K (0–9). These are separate reference scales. The 4K REFORM alpha through epsilon courses correspond to 11–15 dan. The 7K labels use the supplied numerical conversion; gamma, azimuth, zenith and stellium refer to dan 11–14.

Run the commands in the [README](../README.md#reproduce-the-evaluation) to generate individual scores, ranking statistics and course fits. Automated tests check native SPM parity for all supported profiles and key counts, tap-only behavior, mirror symmetry, speed changes, fractional timing, static sustain and reference calibration.
