"""Generic batch-runner for Aspen workflows (CO2 feed sweep, CSV-driven experiments).

Goals:
- Reuse existing helpers: `BLK_Apply_Conversions_From_RSTOIC`, `update_hydrocracking_streams_v2`, `STRM_GET_OUTPUTS`, etc.
- Provide a simple CLI to run a CO2 sweep or run parameter sets from CSV.
- Record key outputs to CSV for downstream analysis.

Usage examples:
  python batch_runner.py --mode co2_sweep --co2-start 34.2 --co2-stop 41.8 --steps 6    # sweep CO2 feed (kmol/hr)
  python batch_runner.py --mode from_csv --input params.csv                              # CSV may contain `CO2` (kmol/hr) or other stream parameters
  # To sweep CO2 component flow use a CSV with a `CO2` column (units: kmol/hr) or call BatchRunner.run_case({'CO2': value}) programmatically.

Notes:
- This script is intentionally conservative: it opens ONE Aspen `Simulation` and iterates.
- BatchRunner uses the `CO2` parameter (absolute component flow in kmol/hr) for CO2 feed updates via `STRM_Set_ComponentFlowRate` to `1-CO2-MU`.

"""
from __future__ import annotations

import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Robust imports so script works when invoked from any working directory.
# Search upward for repository root by locating CodeLibrary.py (same approach used elsewhere in repo).
MODULE_DIR = Path(__file__).resolve().parent
_search_dir = MODULE_DIR
REPO_ROOT = None
while True:
    if (_search_dir / "CodeLibrary.py").exists():
        REPO_ROOT = str(_search_dir)
        break
    if _search_dir.parent == _search_dir:
        break
    _search_dir = _search_dir.parent

# Fallback: assume repo root is 3 levels up (Project/Aspen/Aspen -> repo root)
if REPO_ROOT is None:
    try:
        REPO_ROOT = str(MODULE_DIR.parents[3])
    except Exception:
        REPO_ROOT = str(MODULE_DIR)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))
# also ensure the inner `Aspen` module directory (Project/Aspen/Aspen) is on sys.path
aspensub = MODULE_DIR / 'Aspen'
if aspensub.exists() and str(aspensub) not in sys.path:
    sys.path.insert(0, str(aspensub))

# now import helpers (CodeLibrary must be on sys.path)
from CodeLibrary import Simulation
# import from the `Aspen` subpackage so Pylance/pyright can resolve these statically
from Aspen.AspenTester import BLK_Apply_Conversions_From_RSTOIC
from Aspen.hydrocracking_v2 import update_hydrocracking_streams_v2
# reuse Excel helper from CustomSimualtion.py (inside Aspen subpackage)
from Aspen.CustomSimualtion import write_co_to_rstoic


DEFAULT_BKP = "FTS Alessio_CO_conv_Ref_20bar_11%.bkp"
DEFAULT_RESULTS_CSV = "batch_results.csv"

# Default CO2 feed (component flow, kmol/hr) and sweep range (±10%)
DEFAULT_CO2_FLOW = 38.0
DEFAULT_CO2_SWEEP_PCT = 0.10

# NOTE: CO (mole-fraction → RSTOIC) workflow is supported via `run_case({'co': ...})`.
# Explicit sweep functionality and strict bounds were removed from this module.


@dataclass
class BatchConfig:
    bkp_name: str = DEFAULT_BKP
    visibility: bool = False
    inlet_stream: str = "5-IN-EXC"
    outlet_stream: str = "5-OUTEXC"
    blockname: str = "FTS-REAC"
    results_csv: str = DEFAULT_RESULTS_CSV
    hydrocracker: bool = True
    save_each: bool = False


class BatchRunner:
    def __init__(self, cfg: BatchConfig) -> None:
        self.cfg = cfg
        # locate bkp path (allow absolute or module-relative). Try several plausible locations.
        candidate = Path(cfg.bkp_name)
        if candidate.is_file():
            self.bkp_path = candidate
        else:
            p_local = MODULE_DIR / cfg.bkp_name
            p_aspensub = MODULE_DIR / 'Aspen' / cfg.bkp_name
            # prefer exact matches if present
            if p_local.exists():
                self.bkp_path = p_local
            elif p_aspensub.exists():
                self.bkp_path = p_aspensub
            else:
                # default to local path (will raise below if not found)
                self.bkp_path = p_local
        if not self.bkp_path.exists():
            raise FileNotFoundError(f"Aspen .bkp not found: {self.bkp_path}")
        self.sim: Optional[Simulation] = None

    def open(self) -> None:
        if self.sim is None:
            self.sim = Simulation(AspenFileName=str(self.bkp_path), WorkingDirectoryPath=str(self.bkp_path.parent), VISIBILITY=self.cfg.visibility)

    def close(self) -> None:
        if self.sim is not None:
            close_fn = getattr(self.sim, 'Close', None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            self.sim = None

    def _run_and_collect(self) -> Dict[str, Any]:
        """Run Aspen and collect a small set of diagnostics (NAPHTA/KERO totals)."""
        assert self.sim is not None
        sim = self.sim  # narrow type for static checkers (Pylance/pyright)

        # initial run
        try:
            sim.EngineRun()
        except Exception as e:
            return {"_error": f"EngineRun_failed_initial: {e}"}

        # optionally run hydrocracker reconciliation
        if self.cfg.hydrocracker:
            try:
                update_hydrocracking_streams_v2(sim, inlet_stream=self.cfg.inlet_stream, outlet_stream=self.cfg.outlet_stream)
            except Exception as e:
                return {"_error": f"hydrocracker_failed: {e}"}

            # run again after hydrocracker
            try:
                sim.EngineRun()
            except Exception as e:
                return {"_error": f"EngineRun_failed_post_hydro: {e}"}

        # collect product totals (best-effort)
        def _stream_total(stream_id: str) -> Optional[float]:
            try:
                outs = sim.STRM_GET_OUTPUTS(stream_id)
                # STRM_GET_OUTPUTS may return either a list (MoleFlowList/MoleFractionList)
                # or a single numeric value. Handle both deterministically so static
                # type-checkers (Pylance) can reason about the types.
                flows = outs.get("MoleFlowList")
                if flows is None:
                    flows = outs.get("MoleFractionList")

                if isinstance(flows, (list, tuple)):
                    return float(sum(float(x) for x in flows))

                # single numeric value
                if flows is not None:
                    return float(flows)
            except Exception:
                return None
            return None

        nap = _stream_total('9-NAPHTA')
        ker = _stream_total('9-KERO')
        return {"naphtha": nap, "kero": ker}

    def run_case(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Apply `params` then run and return dict of inputs+outputs.

        Supported params (best-effort):
          - 'CO2' : Absolute CO2 component mole flow in kmol/hr (e.g. 38.0). BatchRunner writes this to `1-CO2-MU` using `STRM_Set_ComponentFlowRate` (component-driven feed).
          - Other stream component flows by name (e.g. 'H2') with float values — will attempt to write to reasonable default streams.
        """
        assert self.sim is not None
        res: Dict[str, Any] = {}
        res.update({k: params.get(k) for k in params})



        # 1) if CO provided: write Excel cell then apply RSTOIC conversions
        # (no strict bounds enforced here — callers may still pass CO for the
        # RSTOIC workflow; Excel interpolation / BLK_Apply_Conversions_From_RSTOIC
        # contains the authoritative behavior.)
        if 'co' in params and params['co'] is not None:
            co_val = float(params['co'])
            # normalize percent like CustomSimualtion does (accept 6.6 or 0.066)
            if co_val > 1.5:
                co_val = co_val / 100.0
            # write Excel cell (Aspen workbook lives in the inner 'Aspen' folder)
            excel_path = MODULE_DIR / 'Aspen' / 'DATASET_update.xlsm'
            write_co_to_rstoic(excel_path, co_val)
            # apply conversions from RSTOIC
            try:
                BLK_Apply_Conversions_From_RSTOIC(self.sim, self.cfg.blockname, excel_path=str(excel_path), dry_run=False, save_after=False)
            except Exception as e:
                res['_error'] = f'apply_conversions_failed: {e}'
                return res

        # 2) set component flows if present in params (best-effort mapping)
        # Typical Aspen stream nodes for CO2/H2 in this project are '1-CO2-MU' and '1-H2-MU' — use STRM_Set_ComponentFlowRate
        for comp in ('CO2', 'H2'):
            if comp in params and params[comp] is not None:
                try:
                    # try the stream nodes used elsewhere in the repo
                    if comp == 'CO2':
                        stream_id = '1-CO2-MU'
                    elif comp == 'H2':
                        stream_id = '1-H2-MU'
                    else:
                        stream_id = None
                    if stream_id is not None:
                        flow_val = float(params[comp])
                        # Write the absolute component flow (best-effort). For the CO2
                        # feed stream this project uses a component-driven input, so we
                        # only set the component mole flow (do NOT attempt to override
                        # the stream TOTFLOW which may be computed by the flowsheet).
                        self.sim.STRM_Set_ComponentFlowRate(stream_id, flow_val, comp)

                        # For the CO2 feed stream also try to update the tree node so
                        # the Aspen UI composition table shows the absolute mole flow.
                        if stream_id == '1-CO2-MU':
                            try:
                                tree = getattr(self.sim, 'AspenSimulation').Tree
                                comp_node = tree.FindNode(r"\Data\Streams\1-CO2-MU\Input\FLOW\MIXED\CO2")
                                if comp_node is not None:
                                    comp_node.Value = flow_val
                            except Exception:
                                # ignore tree write failures (we already used the API)
                                pass

                        # verify component flow read-back (find CO2 in CompoundNameList)
                        try:
                            outs = self.sim.STRM_GET_OUTPUTS(stream_id)
                            names = outs.get('CompoundNameList', [])
                            flows = outs.get('MoleFlowList', [])
                            if isinstance(names, (list, tuple)) and isinstance(flows, (list, tuple)):
                                # case-insensitive match
                                idx = None
                                for i, n in enumerate(names):
                                    if str(n).upper() == comp.upper():
                                        idx = i
                                        break
                                if idx is not None:
                                    observed_comp_flow = float(flows[idx])
                                    if abs(observed_comp_flow - float(flow_val)) > 1e-6:
                                        # primary write did not take effect — attempt safe fallbacks
                                        res[f"_warn_set_{comp}_component_mismatch"] = {
                                            'requested': flow_val,
                                            'observed': observed_comp_flow,
                                            'stream': stream_id,
                                        }

                                        # Try fallback candidate streams where the model may actually
                                        # take the component flow (best-effort): reactor inlet and
                                        # configured inlet_stream. Stop on first success.
                                        fallback_candidates = [self.cfg.inlet_stream, '2-IN-FT']
                                        for candidate in fallback_candidates:
                                            if candidate == stream_id:
                                                continue
                                            try:
                                                # attempt component write on candidate
                                                self.sim.STRM_Set_ComponentFlowRate(candidate, flow_val, comp)
                                                # read back
                                                outs_cand = self.sim.STRM_GET_OUTPUTS(candidate)
                                                names_c = outs_cand.get('CompoundNameList', [])
                                                flows_c = outs_cand.get('MoleFlowList', [])
                                                if isinstance(names_c, (list, tuple)) and isinstance(flows_c, (list, tuple)):
                                                    idx_c = None
                                                    for j, nc in enumerate(names_c):
                                                        if str(nc).upper() == comp.upper():
                                                            idx_c = j
                                                            break
                                                    if idx_c is not None:
                                                        observed_c = float(flows_c[idx_c])
                                                        if abs(observed_c - float(flow_val)) <= 1e-6:
                                                            # success — record and clear mismatch warning
                                                            res[f"_fixed_set_{comp}_on"] = candidate
                                                            res.pop(f"_warn_set_{comp}_component_mismatch", None)
                                                            break
                                            except Exception:
                                                # try next candidate
                                                continue
                        except Exception as e:
                            # readback failed for primary stream; try fallbacks anyway
                            res[f"_warn_check_{comp}"] = str(e)
                            fallback_candidates = [self.cfg.inlet_stream, '2-IN-FT']
                            for candidate in fallback_candidates:
                                if candidate == stream_id:
                                    continue
                                try:
                                    self.sim.STRM_Set_ComponentFlowRate(candidate, flow_val, comp)
                                    outs_cand = self.sim.STRM_GET_OUTPUTS(candidate)
                                    names_c = outs_cand.get('CompoundNameList', [])
                                    flows_c = outs_cand.get('MoleFlowList', [])
                                    if isinstance(names_c, (list, tuple)) and isinstance(flows_c, (list, tuple)):
                                        idx_c = None
                                        for j, nc in enumerate(names_c):
                                            if str(nc).upper() == comp.upper():
                                                idx_c = j
                                                break
                                        if idx_c is not None:
                                            observed_c = float(flows_c[idx_c])
                                            if abs(observed_c - float(flow_val)) <= 1e-6:
                                                res[f"_fixed_set_{comp}_on"] = candidate
                                                break
                                except Exception:
                                    continue
                except Exception as e:
                    res[f"_warn_set_{comp}"] = str(e)
        # 4) optional save
        if self.cfg.save_each:
            try:
                self.sim.Save()
            except Exception:
                pass

        return res

    def run_co2_sweep(self, co2_values: Iterable[float], out_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        # Resolve output path up-front (Simulation may change cwd) and materialize values
        out_path_resolved = Path(out_path).resolve() if out_path is not None else None
        co2_list = list(co2_values)
        self.open()
        results: List[Dict[str, Any]] = []
        for i, co2 in enumerate(co2_list):
            print(f"[Run {i+1}/{len(co2_list)}] CO2={co2} kmol/hr")
            row = self.run_case({'CO2': co2})
            row['CO2'] = co2
            row['run_index'] = i
            results.append(row)
        if out_path_resolved:
            self._write_results(results, out_path_resolved)
        return results



    def run_from_csv(self, csv_path: Path, out_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        # Resolve paths before opening Aspen (Simulation.open() may change cwd)
        csv_path = Path(csv_path).resolve()
        out_path_resolved = Path(out_path).resolve() if out_path is not None else None
        self.open()
        results = []
        with csv_path.open('r', newline='') as fh:
            reader = csv.DictReader(fh)
            for i, r in enumerate(reader):
                # coerce numeric values where possible
                params: Dict[str, Any] = {}
                for k, v in r.items():
                    if v is None or v == '':
                        params[k] = None
                        continue
                    try:
                        params[k] = float(v)
                    except Exception:
                        params[k] = v

                print(f"[Run {i+1}] params={params}")
                out = self.run_case(params)
                out['run_index'] = i
                out.update(params)
                results.append(out)
        if out_path_resolved:
            self._write_results(results, out_path_resolved)
        return results

    def _write_results(self, rows: List[Dict[str, Any]], out_path: Path) -> None:
        if len(rows) == 0:
            return
        keys = sorted({k for r in rows for k in r.keys()})
        with out_path.open('w', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=keys)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)


# ---- CLI ---------------------------------------------------------------
if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser(description='Batch-run Aspen simulations (CO2 sweep or CSV-driven).')
    p.add_argument('--mode', choices=['co2_sweep', 'from_csv'], default='co2_sweep')

    # CO2 sweep (component flow, kmol/hr)
    p.add_argument('--co2-start', type=float, default=DEFAULT_CO2_FLOW * (1 - DEFAULT_CO2_SWEEP_PCT), help='Start CO2 component flow (kmol/hr) for sweep — absolute flow (kmol/hr)')
    p.add_argument('--co2-stop', type=float, default=DEFAULT_CO2_FLOW * (1 + DEFAULT_CO2_SWEEP_PCT), help='Stop CO2 component flow (kmol/hr) for sweep — absolute flow (kmol/hr)')

    p.add_argument('--steps', type=int, default=6, help='Number of sweep steps (default: 6)')
    p.add_argument('--input', type=str, default=None, help='Path to input CSV for mode=from_csv')
    p.add_argument('--out', type=str, default=DEFAULT_RESULTS_CSV, help='Output CSV path')
    p.add_argument('--bkp', type=str, default=None, help='Alternate .bkp filename/path')
    p.add_argument('--visibility', action='store_true', help='Open Aspen with visible UI')
    p.add_argument('--no-hydro', dest='hydro', action='store_false', help='Do not run hydrocracker reconciliation')
    p.add_argument('--save-each', action='store_true', help='Call sim.Save() after each case')
    args = p.parse_args()

    cfg = BatchConfig(
        bkp_name=args.bkp if args.bkp is not None else DEFAULT_BKP,
        visibility=args.visibility,
        hydrocracker=args.hydro,
        save_each=args.save_each,
        results_csv=args.out,
    )

    runner = BatchRunner(cfg)
    # Validate supplied co2-start / co2-stop
    if not (args.co2_start > 0 and args.co2_stop > 0):
        raise SystemExit("--co2-start and --co2-stop must be positive")
    if not (args.co2_start < args.co2_stop):
        raise SystemExit("--co2-start must be less than --co2-stop")

    try:
        import numpy as _np
        if args.mode == 'co2_sweep':
            co2_vals = list(_np.linspace(args.co2_start, args.co2_stop, args.steps))
            out = runner.run_co2_sweep(co2_vals, out_path=Path(args.out).resolve())
        else:
            if args.input is None:
                raise SystemExit('Error: --input CSV is required for mode=from_csv')
            out = runner.run_from_csv(Path(args.input).resolve(), out_path=Path(args.out).resolve())

        print(f"Done — wrote results to {args.out}")
    finally:
        runner.close()
