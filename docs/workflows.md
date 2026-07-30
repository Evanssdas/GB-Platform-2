# Canonical GitHub Actions workflows

The repository uses the following workflows. Obsolete duplicate collectors have
been removed so the Actions tab has one clear workflow for each purpose.

## 1. CI

**Use:** automatic checks on every push and pull request.

Checks package compilation, the installed CLI and the complete test suite. A
manual run also executes the synthetic demonstration and uploads its outputs.

## 2. Validate one training month V4

**Use:** validate external data contracts over a window of at most 62 days.

Recommended first window:

- start: `2025-07-01`
- end: `2025-08-01` (exclusive)
- embedded: `embedded_2025`
- inertia: `inertia_2025_26`
- units: `false`

Critical sources are Elexon core, NESO embedded forecasts, NESO inertia and all
three weather groups. ENTSO-E and B1610 are advisory in this validation workflow.
The artifact always contains context, status and audit diagnostics.

## 3. Build core model smoke test V1

**Use:** prove that real-data table assembly and leakage-safe training work.

This is a software smoke test. The default one-month model is not a production
forecasting model. Its artifact contains the unified core dataset, fitted model
files, chronological diagnostic metrics and an audit report.

The core profile deliberately excludes battery output until the B1610 storage
classification is complete. It does not substitute unavailable battery data with
zero.

## 4. Collect historical data V4

**Use:** collect longer training history after the one-month validator and smoke
test have passed.

Each run is limited to 366 days and uses bounded source queries, monthly NESO
chunks and hard source timeouts. The workflow validates that the selected embedded
and inertia archives cover the requested period before collection begins. Elexon,
NESO, weather and the final audit are critical; ENTSO-E and B1610 are advisory
unless explicitly required by a later full-model workflow.

For the latest complete twelve-month core-training period, use two archive-compatible
runs:

1. `2025-04-01` to `2026-01-01`, with `embedded_2025` and `inertia_2025_26`.
2. `2026-01-01` to `2026-04-01`, with `embedded_2026_h1` and `inertia_2025_26`.

These artifacts must be audited and combined before production-candidate training.

## 5. Collect ENTSO-E neighbours V3

**Use:** diagnose or recollect ENTSO-E products independently.

Requires the repository secret `ENTSOE_TOKEN`. Inputs are an inclusive UTC start
and exclusive UTC end. The workflow validates inputs, runs ENTSO-E tests, applies
a hard timeout and uploads status diagnostics before enforcing success.

## 6. Daily APXMIDP grading V2

**Use:** append public APXMIDP actual prices and grade immutable forecast logs.

Runs daily at 09:30 UTC and resolves the previous delivery date in
`Europe/London`. A manual date may also be supplied. Concurrency is restricted to
one grading job to prevent overlapping repository pushes. Actuals and scores are
uploaded as an artifact before they are committed.

## Required order before genuine forecasts

1. CI is green.
2. One-month validation is green.
3. Core-model smoke test is green.
4. Historical collection is completed and audited for at least 12 months,
   preferably 24 months.
5. A production training workflow is run with a multi-month chronological
   holdout and the results are reviewed against persistence.
6. Only then should a live day-ahead forecast workflow be enabled.

A green one-month smoke test proves the software pipeline, not forecast quality.
