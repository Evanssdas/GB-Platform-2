# Daily V2-R experiment candidate

**Unverified prototype; no new accuracy claims.**

To integrate into the GB-Platform-2 repository, put `rolling_v2r.py` under `src/gb_platform_v2/` and `paper-rolling-v2r.yml` under `.github/workflows/`. Test in a feature branch before dispatch. The module uses 5 expanding out-of-fold component folds, an independently re-fitted six-component model each delivery day, and a separately trained price model with the pre-selected identity transform. All daily refits use only settlement periods ending before the D-1 13:00 Europe/London issue time. This is **retrospective** and must not be described as prospective.

**Needs validation prior to paper use:** test DST dates, lag observability, no unobserved forecast inputs, price features and consistent comparable rows; check CPU duration and rerun end-to-end before referring to scores. The frozen evidence dataset is obtained using the workflow's recorded source run.
