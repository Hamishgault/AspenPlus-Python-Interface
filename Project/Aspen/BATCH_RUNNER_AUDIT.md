# Audit — `batch_runner.py` and related Aspen helpers

now make a new file which is similar to batch runner except this one we are testing somehting different we are going to change the amount of h20 feed to and report CO% before reactor the H2O/carbflow ratio kerosene mass flow (we want to maxmize kerosene) and naptha. as kero flow increases naptha should go down. 

Last reviewed: 2026-02-18

## Executive summary ✅
- File audited: `Project/Aspen/batch_runner.py` — purpose: orchestrate Aspen runs (CO2 sweeps or CSV-driven cases), apply RSTOIC → reactor conversions, run hydrocracker reconciliation, and write results to CSV.
- Key callers / dependencies inspected: `Simulation` (`CodeLibrary.py`), `BLK_Apply_Conversions_From_RSTOIC` (`AspenTester.py`), `update_hydrocracking_streams_v2` (`hydrocracking_v2.py`), `write_co_to_rstoic` & `iterate_rstoic_until_converged` (`CustomSimualtion.py`).
- Overall assessment: design is pragmatic, well-commented, and test-aware. Good defensive coding and fallbacks exist (dry-run modes, readback verification). Main gaps are: sparse logging, brittle COM/write-back assumptions, and missing explicit persistence of a few derived user properties (e.g. `PROP-1`).

---

## What `batch_runner.py` does (high level) 🔁
1. Loads/initializes an Aspen `Simulation` (via `CodeLibrary.Simulation`).
2. Runs the simulation engine and optionally runs the hydrocracker reconciliation (`update_hydrocracking_streams_v2`).
3. Supports two run modes:
   - `co2_sweep`: numeric sweep across CO2 component flows (kmol/hr)
   - `from_csv`: read rows from an input CSV (columns converted to numeric where possible) and run cases
4. For CO2 cases the script can:
   - write the CO% to Excel (`write_co_to_rstoic`) so RSTOIC interpolation uses the requested CO
   - call `BLK_Apply_Conversions_From_RSTOIC` to map Excel conversions into Aspen reaction conversions
   - optionally iterate the RSTOIC → reactor inlet CO (`iterate_rstoic_until_converged`) and re-apply conversions
5. Collects output totals (NAPHTA/KERO) via `sim.STRM_GET_OUTPUTS(...)` and writes aggregated results to `batch_results.csv`.

---

## Call graph & flow (key functions/files) 📚
- `batch_runner.py::BatchRunner.run_case`
  - writes CO via `write_co_to_rstoic` (if present)
  - calls `BLK_Apply_Conversions_From_RSTOIC` (via `CustomSimualtion` / `AspenTester`) when CO changes require conversion updates
  - calls `update_hydrocracking_streams_v2(sim, inlet_stream, outlet_stream)` to update outlet component flows
  - calls `sim.EngineRun()` / `sim.Run2()` to execute the model
  - reads product totals with `sim.STRM_GET_OUTPUTS(stream_id)` (sums `MoleFlowList`) and returns results
- `CustomSimualtion.iterate_rstoic_until_converged` — iterative convergence loop that:
  - runs sim, samples CO at reactor inlet, writes CO to `DATASET_update.xlsm`(RSTOIC!K1), calls `BLK_Apply_Conversions_From_RSTOIC`, re-runs, checks tolerance
- `AspenTester.BLK_Apply_Conversions_From_RSTOIC` — parses `DATASET_update.xlsm` (RSTOIC sheet), detects conversion columns, validates reaction IDs against Aspen block, and applies conversions via block-level setters
- `hydrocracking_v2.update_hydrocracking_streams_v2` — formula-driven stoichiometry for cracking: reads inlet `STRM_GET_OUTPUTS`, builds stoichiometric matrices, computes product flows and writes component flows to outlet stream nodes
- `CodeLibrary.STRM_GET_OUTPUTS` — returns per-stream lists: `CompoundNameList`, `MoleFlowList`, `MassFlowList`, `MoleFracList`, etc.

---

## Important behaviors, assumptions & invariants ⚠️
- Units: CO feed in `batch_runner` / CSV is interpreted as absolute component mole flow in **kmol/hr**; `write_co_to_rstoic` accepts CO as fraction or percent (internally normalized to fraction). `STRM_GET_OUTPUTS` returns mole flows in model units (used as-is).
- `iterate_rstoic_until_converged` assumes `STRM_GET_OUTPUTS` returns `CompoundNameList` and `MoleFlowList` (both lists) and that CO is present in the reactor inlet stream components.
- `BLK_Apply_Conversions_From_RSTOIC` relies on Excel layout heuristics (detects RSTOIC columns by header tokens, falls back to fixed columns). This is robust but depends on workbook structure.
- `update_hydrocracking_streams_v2` will only set the outlet total when all expected components are present in Aspen’s outlet stream (avoids Aspen errors).
- ASPEN COM interactions are inherently brittle: tree node names and paths must match the flowsheet. Code defensively tries fallbacks and read-back verification.

---

## Strengths (what's done well) ✅
- Clear, well-documented workflows and CLI examples.
- Dry-run support and conservative save behavior (avoids accidental writes).
- Defensive readback/verification after writes (component flow set + read-back check).
- Reuse of helpers (single `Simulation` instance, modular helpers in `Aspen` package).
- Tests exist for many behaviors (see `Project/Aspen/tests/`), and `BatchRunner` integrates with those tests.

---

## Weaknesses / risks (observed) ⚠️
- Logging is ad-hoc (print statements). Hard to debug long runs or failures from CI logs.
- No explicit instrumentation for durations, retries, or transient COM errors.
- Aspen COM write-backs (user properties like `PROP-1`) are fragile and may fail silently — there is no guaranteed single API to persist user properties across all flowsheet versions.
- `batch_runner` currently does not persist `PROP-1` (mole flow of carbon atoms) into results CSV even though flowsheet defines the property (user asked earlier to set it and COM write failed).
- Limited telemetry on failures: exceptions may be captured but only partially surfaced in results (e.g. `'_error'` keys); stack traces may be lost.

---

## Coverage of called functions — quick findings
- `CodeLibrary.STRM_GET_OUTPUTS` — returns expected lists; reliable for readback and aggregation.
- `CustomSimualtion.write_co_to_rstoic` — robust: prefers openpyxl, falls back to Excel COM if workbook locked.
- `CustomSimualtion.iterate_rstoic_until_converged` — well-implemented; uses multiple simulation-run fallbacks and has sensible defaults for tolerance and max iterations.
- `AspenTester.BLK_Apply_Conversions_From_RSTOIC` — robust Excel parsing with detection heuristics and fallback to `BLK_Apply_Conversions_From_Excel` if parsing fails.
- `hydrocracking_v2.update_hydrocracking_streams_v2` — numerically detailed (stoichiometric matrices), protects against missing components when writing flows.

---

## Concrete recommendations — prioritized (short → long term) ⚙️
1. Immediate / high value (low effort)
   - Add `logging` (module-level logger) to `batch_runner.py` and friends; replace critical `print()` calls with `logger.info/warn/error`. Improves debuggability and CI traceability. (Estimate: 0.5–1 day)
   - Persist `PROP-1` into results CSV (or add a `--export-props` flag) so derived properties are recorded even when Aspen tree writes fail. (Estimate: 0.5 day)
   - Add unit/format validation for CSV inputs (clear error messages for bad numeric formats). (Estimate: 0.5 day)

2. Near term (medium effort)
   - Add robust retry/backoff and clearer exception reporting for COM operations (Excel and Aspen tree writes). Make transient failures recoverable. (Estimate: 1–2 days)
   - Add explicit `BatchRunner` method to persist arbitrary user properties (e.g. `persist_stream_property(sim, stream, prop_name, value)`) with safe fallbacks (tree write, user property mapping, external CSV). (Estimate: 1 day)
   - Improve CLI: add `--prop1` option to write `PROP-1` into results and optionally attempt Aspen write. (Estimate: 0.5 day)

3. Longer term (architectural)
   - Centralize Aspen I/O into a small `aspensim` wrapper that exposes typed operations (set component, set property, read stream, write property) and normalizes errors. Move fragile COM logic to that wrapper. (Estimate: 3–5 days)
   - Add structured logging + trace IDs for each run so multi-run traces can be correlated. (Estimate: 2 days)
   - Add integration tests that run a headless Aspen simulation in CI via a mock/fixture, exercising `BatchRunner.run_co2_sweep` and `iterate_rstoic_until_converged`. (Estimate: 2–3 days)

---

## Suggested code changes / examples (small, ready-to-apply)
- Persist `PROP-1` to results CSV (insert into `BatchRunner._run_and_collect`):

```py
# after ker = _stream_total('9-KERO')
# compute PROP-1 from 9-KERO by summing (mole_flow_i * carbon_count_i)
outs = sim.STRM_GET_OUTPUTS('9-KERO')
comp_names = outs.get('CompoundNameList', [])
mole_flows = outs.get('MoleFlowList', [])
# quick carbon-count helper (project can extend mapping)
carbon_count = lambda name: int(''.join(filter(str.isdigit, name)) or 1) if name.startswith('C') else (1 if name.upper() in ('CO','CO2','CH4','MEOH') else 0)
prop1 = sum(f * carbon_count(n) for n, f in zip(comp_names, mole_flows))
# store into returned dict
res['prop1_kmol_hr'] = float(prop1)
```

- Replace `print()`s in `batch_runner` with `logger` calls (and add a top-level `logger = logging.getLogger(__name__)`).

---

## Tests to add / strengthen ✅
- Unit tests for `BatchRunner.run_case` that:
  - mock `Simulation` and assert `STRM_Set_ComponentFlowRate` called with expected arguments
  - verify `iterate_rstoic_until_converged` is invoked when `apply_rstoic=True`
  - verify `PROP-1` persistence into results CSV when implemented
- Integration test that exercises the CO2 sweep end-to-end using the existing test harness and mocks (`Project/Aspen/tests/test_integration_batchrunner.py` already provides a good template).

---

## Security & safety notes 🔒
- Excel COM access runs on the host; ensure the Excel workbook macros are trusted—do not run untrusted workbooks.
- When adding file-write features, avoid writing secrets or injecting untrusted content into Excel cells.

---

## Next steps (recommended immediate 3-step plan) ▶️
1. Add `prop1` capture to `_run_and_collect` and include it in the CSV output (quick win; preserves user's requested metric).
2. Replace `print()` with `logging` in `batch_runner.py` and `CustomSimualtion.py` (improves observability).
3. Add an automated unit test that asserts `prop1_kmol_hr` appears in `BatchRunner.run_case` results and in the CSV output.

---

## Appendix — quick references
- `batch_runner.py::BatchRunner.run_case` — orchestrator for each case
- `CustomSimualtion.write_co_to_rstoic` — writes CO → `DATASET_update.xlsm` (openpyxl w/ COM fallback)
- `CustomSimualtion.iterate_rstoic_until_converged` — iteration loop for CO convergence
- `AspenTester.BLK_Apply_Conversions_From_RSTOIC` — Excel → Aspen reaction conversion apply
- `hydrocracking_v2.update_hydrocracking_streams_v2` — formula-based outlet flow calculation
- `CodeLibrary.STRM_GET_OUTPUTS` — stream read helper used throughout

---

If you want, I can:
- implement the `PROP-1` persistence into `batch_runner` + add unit test now, or
- add logging + a small PR with the retry/backoff wrapper for COM writes.

Which change should I implement first? 🔧
