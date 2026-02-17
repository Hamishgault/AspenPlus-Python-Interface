"""Generic batch-runner for Aspen workflows (CO sweeps, CSV-driven experiments).

Goals:
- Reuse existing helpers: `BLK_Apply_Conversions_From_RSTOIC`, `update_hydrocracking_streams_v2`, `STRM_GET_OUTPUTS`, etc.
- Provide a simple CLI to run a CO sweep or run parameter sets from CSV.
- Record key outputs to CSV for downstream analysis.

Usage examples:
  python batch_runner.py --mode co_sweep --co-start 0.03 --co-stop 0.08 --steps 6
  python batch_runner.py --mode from_csv --input params.csv

Notes:
- This script is intentionally conservative: it opens ONE Aspen `Simulation` and iterates (same pattern as the repo's `monte_carlo_aspen.py`).
- It uses `BLK_Apply_Conversions_From_RSTOIC` when a `co` value is provided (writes Excel → applies conversions).

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

# Allowed CO range (mole fraction). Enforced as strict inequality: MIN_CO < co < MAX_CO
MIN_CO = 0.04
MAX_CO = 0.11


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
                flows = outs.get("MoleFlowList", []) or outs.get("MoleFractionList", [])
                if isinstance(flows, (list, tuple)):
                    return float(sum(float(x) for x in flows))
                # single value
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
          - 'co' : CO mole fraction (0-1) or percent (e.g. 6.6)
          - stream component flows by name (e.g. 'CO2', 'H2') with float values — will attempt to write to reasonable default streams.
        """
        assert self.sim is not None
        res: Dict[str, Any] = {}
        res.update({k: params.get(k) for k in params})

        # 1) if CO provided: validate, write Excel cell then apply RSTOIC conversions
        if 'co' in params and params['co'] is not None:
            co_val = float(params['co'])
            # normalize percent like CustomSimualtion does (accept 6.6 or 0.066)
            if co_val > 1.5:
                co_val = co_val / 100.0
            # enforce strict allowed range
            if not (MIN_CO < co_val < MAX_CO):
                res['_error'] = f'co_out_of_range: {co_val} not in ({MIN_CO}, {MAX_CO})'
                return res
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
                        self.sim.STRM_Set_ComponentFlowRate(stream_id, float(params[comp]), comp)
                except Exception as e:
                    res[f"_warn_set_{comp}"] = str(e)

        # 3) run & collect
        collected = self._run_and_collect()
        res.update(collected)

        # 4) optional save
        if self.cfg.save_each:
            try:
                self.sim.Save()
            except Exception:
                pass

        return res

    def run_co_sweep(self, co_values: Iterable[float], out_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        # Resolve output path up-front (Simulation may change cwd) and materialize co_values
        out_path_resolved = Path(out_path).resolve() if out_path is not None else None
        co_list = list(co_values)
        self.open()
        results: List[Dict[str, Any]] = []
        for i, co in enumerate(co_list):
            print(f"[Run {i+1}/{len(co_list)}] CO={co}")
            row = self.run_case({'co': co})
            row['co'] = co
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
                # validate CO if present (do not abort full run; record error per-row)
                if 'co' in params and params['co'] is not None:
                    try:
                        co_tmp = float(params['co'])
                        if co_tmp > 1.5:
                            co_tmp = co_tmp / 100.0
                        if not (MIN_CO < co_tmp < MAX_CO):
                            err_row = {'run_index': i, 'co': params['co'], '_error': f'co_out_of_range: {co_tmp} not in ({MIN_CO}, {MAX_CO})'}
                            print(f"    ⚠️  Skipping row {i+1}: {err_row['_error']}")
                            results.append(err_row)
                            continue
                    except Exception:
                        results.append({'run_index': i, '_error': 'invalid_co_format'})
                        continue
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

    p = argparse.ArgumentParser(description='Batch-run Aspen simulations (CO sweep or CSV-driven).')
    p.add_argument('--mode', choices=['co_sweep', 'from_csv'], default='co_sweep')
    p.add_argument('--co-start', type=float, default=0.05, help=f'Start CO (fraction) for sweep — must satisfy {MIN_CO} < co < {MAX_CO}')
    p.add_argument('--co-stop', type=float, default=0.10, help=f'Stop CO (fraction) for sweep — must satisfy {MIN_CO} < co < {MAX_CO}')
    p.add_argument('--steps', type=int, default=6, help='Number of CO steps')
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
    # Validate supplied co-start / co-stop are inside allowed exclusive bounds
    if not (MIN_CO < args.co_start < MAX_CO) or not (MIN_CO < args.co_stop < MAX_CO):
        raise SystemExit(f"--co-start and --co-stop must be inside exclusive range ({MIN_CO}, {MAX_CO})")
    if not (args.co_start < args.co_stop):
        raise SystemExit("--co-start must be less than --co-stop")

    try:
        if args.mode == 'co_sweep':
            import numpy as _np
            co_vals = list(_np.linspace(args.co_start, args.co_stop, args.steps))
            out = runner.run_co_sweep(co_vals, out_path=Path(args.out).resolve())
        else:
            if args.input is None:
                raise SystemExit('Error: --input CSV is required for mode=from_csv')
            out = runner.run_from_csv(Path(args.input).resolve(), out_path=Path(args.out).resolve())

        print(f"Done — wrote results to {args.out}")
    finally:
        runner.close()
