# Prime-Parity Benchmark Report

- Suite ID: `<suite_id>`
- Suite Version: `<suite_version>`
- Generated At (UTC): `<generated_at>`

## Dataset

- Total seeds: `<seed_count>`
- Complexity coverage: `<complexity_breakdown>`

## Metric Definitions

- Review pass rate: `passed_reviews / (passed_reviews + failed_reviews)`
- Failed-task rate: `failed_tasks / total_tasks`
- Design agreement rate: `agreed_design_tasks / evaluated_design_tasks`
- Truncation incidence: `truncation_flagged_tasks / total_tasks`

## Per-Seed Comparison

| Seed | Complexity | Artisan Review Pass | Prime Review Pass | Delta | Artisan Failed-Task Rate | Prime Failed-Task Rate | Delta | Artisan Design Agreement | Prime Design Agreement | Delta | Artisan Truncation Incidence | Prime Truncation Incidence | Delta |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `<seed_id>` | `<complexity>` | `<a_review_pass>` | `<p_review_pass>` | `<delta_review_pass>` | `<a_failed_rate>` | `<p_failed_rate>` | `<delta_failed_rate>` | `<a_design_agreement>` | `<p_design_agreement>` | `<delta_design_agreement>` | `<a_truncation_incidence>` | `<p_truncation_incidence>` | `<delta_truncation_incidence>` |

## Aggregate Summary

- Artisan average review pass rate: `<artisan_avg_review_pass>`
- Prime average review pass rate: `<prime_avg_review_pass>`
- Artisan average failed-task rate: `<artisan_avg_failed_rate>`
- Prime average failed-task rate: `<prime_avg_failed_rate>`
- Artisan average design agreement rate: `<artisan_avg_design_agreement>`
- Prime average design agreement rate: `<prime_avg_design_agreement>`
- Artisan average truncation incidence: `<artisan_avg_truncation_incidence>`
- Prime average truncation incidence: `<prime_avg_truncation_incidence>`

## Notes

- Include raw benchmark JSON artifact path.
- Call out seeds where either route was missing a metric (reported as `n/a`).
