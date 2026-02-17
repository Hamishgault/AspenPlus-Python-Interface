FTS conversion — procedure, checks and next steps

Purpose
- Document the exact manual + programmatic workflow to read CO mole% (from Aspen), compute/interpolate the per-reaction conversion vector from the Excel calculator, and write those conversions into the `FTS-REAC.Input.CONV` table.

Quick summary
- Aspen inlet stream: `2-IN-FT` (read CO mole % from this stream).
- Excel workbook: `Project/Aspen/Aspen/DATASET_update.xlsm`.
  - CO input cell in sheet `RSTOIC`: cell `K1` (label `CO%` in `J1`; current example value ≈ 0.066).
  - Conversion source sheets: `Conv` (raw 5% / 10% tables) and `Interp` (interpolation table).
- Aspen block to update: `FTS-REAC` → `Input.CONV` (all reaction rows already exist in model).
- Code helpers available: `Project/Aspen/Aspen/FTS_Reactor.py` (BLK_Get_ReactionConversions, BLK_Apply_Conversion_Table, BLK_Conv_Table, etc.).

Goals for the automation
1. Read CO mol% (live) from Aspen stream `2-IN-FT`.
2. Use the Excel interpolation (sheet `Interp`) to compute per-reaction conversion values at that CO%.
3. Map interpolated column values to the reaction numbers in Aspen (verify order) and update `FTS-REAC.Input.CONV`.
4. Verify by reading `FTS-REAC.Input.CONV` back and printing a DataFrame.

Where data lives (important cells & sheets)
- Workbook: `Project/Aspen/Aspen/DATASET_update.xlsm`
  - Sheet `RSTOIC` — CO% input: `J1` = header "CO%", `K1` = numeric input (example 0.066). Use this to sanity-check the Aspen stream value.
  - Sheet `Conv` — raw conversion tables for 5% and 10% CO (rows correspond to reaction indices). Use only to inspect raw values.
  - Sheet `Interp` — contains interpolation rows (column labelled `xCO` and adjacent conversion columns). Use for interpolation between 5% and 10% when CO% is between those bounds.

How to read CO% from Aspen (recommended checks)
- Stream id: `2-IN-FT`.
- Use existing helper in `Project/Aspen/Aspen/monte/monte_carlo_aspen.py` (function `_get_comp_flow`) or call the Aspen COM API directly:
  - sim.STRM_GET_OUTPUTS('2-IN-FT') → returns `CompoundNameList` and `MoleFlowList` (or `MoleFractionList`).
  - Compute x_CO = flow_CO / sum(all component mole flows) (or read MoleFractionList if available).
- Sanity check: x_CO (Aspen) should be within Excel valid range (4%–11%). If outside, warn and clamp or abort.

How to get the conversion vector from Excel
- Preferred: read `Interp` sheet and:
  1. find `xCO` column and locate the two surrounding interpolation rows (e.g. 0.05 and 0.10) or use the workbook’s interpolation formula if present.
  2. linearly interpolate each reaction's conversion value between the 5% and 10% cases using measured x_CO.
- Fallback: use `Conv` sheet and do manual interpolation between the 5% and 10% columns.

Mapping Excel rows → Aspen reaction numbers (verification step)
- The Excel sheets list reactions row-by-row in the same order they appear in the Aspen Reaction list in this model — but this must be confirmed.
- Verification (must do once):
  - Run `BLK_List_Reactions_Details(sim)` (in `AspenTester.py`) — captures the Aspen reaction index → name → equation.
  - Compare the reaction names/equations to the Excel `Conv` / `Interp` rows (match by `Name` / `Equation` column).
  - If order differs, build an explicit mapping dictionary {excel_row_index: aspen_reac_no} and persist it.

Programmatic update steps (sequence)
1. Read live x_CO from stream `2-IN-FT`.
2. Read/compute conversion vector from Excel (`Interp` preferred).
3. (Verify) Print Excel row[1:10] vs. Aspen reaction list for first 10 reactions to confirm order.
4. Call `BLK_Apply_Conversion_Table(sim, 'FTS-REAC', table)` where `table` is {rxn_no: conversion} — uses existing `BLK_Set_ReactionConversions`.
5. Read back with `BLK_Get_ReactionConversions(sim, 'FTS-REAC')` and print DataFrame with `BLK_Conv_Table`.
6. Optional: run Aspen solve and check `STRM_GET_OUTPUTS('2-IN-FT')` / outlet stream to validate expected product shifts.

Key notes & constraints ⚠️
- Aspen COM can update existing `CONV` child elements but cannot create new `CONV` entries via the same COM call. You mentioned all rows already exist — that removes this blocker.
- Valid CO% range in the Excel calculator is 4%–11%; do not extrapolate outside this range without manual approval.
- Always create a model backup (save `.bkp`) before mass updates.

Validation checklist (quick)
- [ ] Confirm Aspen x_CO (from `2-IN-FT`) is within 4%–11%.
- [ ] Confirm Excel interpolation gives expected per-reaction conversions for a known test x_CO (e.g., 5% and 10%).
- [ ] Confirm Excel row order matches Aspen reaction order (or create explicit mapping).
- [ ] Run `BLK_Apply_Conversion_Table` and verify `BLK_Conv_Table` shows new values.
- [ ] Save Aspen `.apw`/`.bkp` after verification.

Commands / sample code (quick copy-paste)
- Read CO from Aspen stream (example):

```python
outs = sim.STRM_GET_OUTPUTS('2-IN-FT')
names = outs.get('CompoundNameList', [])
flows = outs.get('MoleFlowList', [])
co_flow = next((f for n,f in zip(names, flows) if n.upper()=='CO'), 0.0)
total = sum(flows)
x_co = co_flow / total
```

- Apply conversions (example using Excel-derived dict `conv_table`):

```python
from AspenTester import BLK_Apply_Conversion_Table
BLK_Apply_Conversion_Table(sim, 'FTS-REAC', conv_table)
```

- Verify & print:

```python
from AspenTester import BLK_Conv_Table, BLK_Get_ReactionConversions
print(BLK_Conv_Table(sim, 'FTS-REAC'))
```

What I suggest you do next (when you return)
1. Run the verification mapping once: compare `BLK_List_Reactions_Details(sim)` → Excel rows on `Conv` / `Interp` and confirm order. If any mismatch, I’ll add a persistent mapping helper.  
2. After confirmation, I will add a one-command helper in `AspenTester.py` that: reads `2-IN-FT` → reads Excel `Interp` → interpolates → applies conversions → prints verification and optionally saves the model.  
3. Optional: add a unit test / dry-run mode that writes conversions to a copy of the model and prints differences.

Files & helpers to check now
- Code: `Project/Aspen/Aspen/AspenTester.py` (BLK_Apply_Conversion_Table, BLK_Conv_Table)
- Excel: `Project/Aspen/Aspen/DATASET_update.xlsm` (`RSTOIC`, `Interp`, `Conv`)
- Stream helper: `Project/Aspen/Aspen/monte/monte_carlo_aspen.py` (stream read helpers)

If you want, I can implement the one-command helper and the Excel-to-CONV importer next time. Otherwise this document should give you the exact checklist and the cell/sheet locations to run the process manually.

Prepared by: GitHub Copilot — saved as `Project/Aspen/Aspen/FTS_CONV_WORKFLOW.md` for your reference.
