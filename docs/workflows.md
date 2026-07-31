# Canonical GitHub Actions workflows

The repository uses one canonical workflow for each stage of the GB core platform.

## 1. CI

**Use:** automatic checks on every push and pull request.

Checks package compilation, the installed CLI and the complete test suite. A
manual run also executes the synthetic demonstration and uploads its outputs.

## 2. Validate one training month V4

**Use:** validate external data contracts over a window of at most 62 days.

Recommended window: `2025-07-01` to `2025-08-01`, using `embedded_2025`,
`inertia_2025_26` and no B1610 units. Elexon core, NESO embedded, NESO inertia and
all three weather groups are critical. ENTSO-E and B1610 are advisory.

## 3. Build core model smoke test V1

**Use:** prove that real-data table assembly and leakage-safe training work.

This is a software smoke test, not a production model. The core profile excludes
battery output until the BM-unit classification is independently verified.

## 4. Collect historical data V4

**Use:** collect audited training history with archive-compatible NESO inputs.

The validated twelve-month period uses:

1. `2025-04-01` to `2026-01-01`: `embedded_2025`, `inertia_2025_26`.
2. `2026-01-01` to `2026-04-01`: `embedded_2026_h1`, `inertia_2025_26`.

## 5. Train production candidate V2

**Use:** merge the two audited historical artifacts, reconstruct D-1 point-in-time
forecasts, build the core table and train with a 90-day chronological holdout.

The validated candidate has 17,472 leakage-safe rows. The complete settlement day
`2026-01-01` is explicitly excluded because neither annual embedded archive
contained a revision available by the configured D-1 issue time. No future value
is substituted.

## 6. Publish operational core bundle V1

**Use:** freeze the successful production candidate as the release
`operational-core-v1`.

This workflow evaluates exact D-7 fallbacks for demand and nuclear, selects them
only when they beat the component model on the chronological holdout, rebuilds the
matching uncertainty distribution and publishes a versioned release archive. The
release remains marked `shadow_only`.

## 7. Shadow day-ahead forecast V1

**Use:** generate tomorrow's probabilistic forecast without operational trading.

The workflow runs at approximately 12:50 Europe/London, creates the correct
46/48/50 settlement periods, retrieves current Open-Meteo forecasts over the full
UTC settlement span, collects any exact D-7 Elexon fallback profile, runs the
frozen release and appends forecasts to `live/forecasts.csv`. Every issue time and
delivery period is immutable.

## 8. Daily APXMIDP grading V3

**Use:** collect the previous complete GB settlement day's APXMIDP actuals, grade
all matching immutable forecasts, calculate timestamp-aligned D-1 persistence and
update `live/deployment_gate.json`.

The deployment gate requires:

- at least 30 consecutive complete shadow delivery days;
- every expected 46/48/50 settlement period;
- all forecasts issued at least eight hours before delivery;
- price MAE at least 5% better than persistence;
- P10-P90 empirical coverage between 70% and 90%.

Passing the gate means eligible for controlled human operational review. It does
not authorise autonomous trading and is not financial advice.

## 9. Collect ENTSO-E neighbours V3

**Use:** diagnose or recollect ENTSO-E products independently using the
`ENTSOE_TOKEN` repository secret.

## Completion definition

The `core_without_battery` engineering platform is technically complete when:

1. CI is green.
2. Historical collection, production-candidate training and audits are green.
3. The operational release publishes successfully.
4. One manual shadow forecast succeeds and writes a complete immutable day.
5. One grading run succeeds and writes actuals, scores and the deployment-gate
   report.

The statistical deployment qualification is intentionally time-based. It cannot
be truthfully declared complete until 30 real consecutive delivery days have been
forecast and graded. Battery/B1610 classification is a separate `full` profile
extension and must not be represented as complete without a verified BM-unit map.
