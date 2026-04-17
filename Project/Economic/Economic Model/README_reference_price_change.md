# Reference Price Scenario Change Log

## What was changed

A new standalone scenario runner was added:

- Project/Economic/Economic Model/Economics_eSAF_reference_price.py

This file keeps the original model code in Project/Economic/Economic Model/Economics_eSAF.py unchanged and introduces fixed ReFuel reference-price scenarios.

Implemented reference-price table values (EUR/t):

- CAF: 640
- SAF: 1925
- Synthetic aviation fuels: 7520
- Aviation fuels: 666

Default category in the new file is synthetic aviation fuels.

## Why this was added

The goal was to test a policy/reference-price setup without modifying the original economics model, so old behavior can be preserved if the new setup is not suitable.

## How synthetic-only Monte Carlo was run

Synthetic ReFuel price was set to 7520 EUR/t, then Monte Carlo was run with:

- normal: 20000 samples
- bep: 2000 samples
- seed: 6

The run used the existing Monte Carlo engine and viewer.

## Observed effect on results

### Current synthetic run (ReFuel = 7520 EUR/t)

From Project/Economic/Economic Model/outputs/economics_esaf/monte_carlo/normal/summary.json:

- VAN p10: 812118.67 EUR
- VAN p50: 938830.73 EUR
- VAN p90: 1080979.61 EUR
- IRR p50: 0.11154

From Project/Economic/Economic Model/outputs/economics_esaf/monte_carlo/bep/summary.json:

- BEP p10: 4725.41 EUR/t
- BEP p50: 4927.72 EUR/t
- BEP p90: 5135.07 EUR/t

### Prior baseline run (before synthetic reference-price overwrite)

Previously observed normal-run VAN distribution (ReFuel baseline setup) was:

- VAN p10: -2069125.51 EUR
- VAN p50: -1848291.11 EUR
- VAN p90: -1645549.32 EUR

### Net impact (synthetic minus prior baseline)

- VAN p10 improvement: +2881244.18 EUR
- VAN p50 improvement: +2787121.84 EUR
- VAN p90 improvement: +2726528.93 EUR

Interpretation: using the synthetic reference price moved the NPV/VAN distribution from strongly negative to strongly positive.

## Important note about outputs

The synthetic Monte Carlo run was executed into the standard folders:

- Project/Economic/Economic Model/outputs/economics_esaf/monte_carlo/normal
- Project/Economic/Economic Model/outputs/economics_esaf/monte_carlo/bep

So those folders now reflect the synthetic-price run. If strict side-by-side reproducibility is needed, future runs should use dedicated output subfolders (for example, synthetic_ref and baseline_ref).

## Re-run commands

Run fixed-price single scenario using the new standalone file:

```powershell
& "c:/Users/Hamish/OneDrive - Politecnico di Torino/Fabio  Salomone's files - Gault Hamish/Code/AspenPlus-Python-Interface/.venv/Scripts/python.exe" "Project/Economic/Economic Model/Economics_eSAF_reference_price.py"
```

Run viewer on saved outputs:

```powershell
& "c:/Users/Hamish/OneDrive - Politecnico di Torino/Fabio  Salomone's files - Gault Hamish/Code/AspenPlus-Python-Interface/.venv/Scripts/python.exe" "Project/Economic/Economic Model/results_viewer.py"
```
