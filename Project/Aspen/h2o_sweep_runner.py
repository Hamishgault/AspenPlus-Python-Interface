"""H2O sweep runner — mirrors `batch_runner.py` behaviour but varies H2O feed only.

Behavior notes (keeps the same Aspen execution model as `batch_runner.py`):
- Uses `CodeLibrary.Simulation` for Aspen control
- Uses `STRM_GET_OUTPUTS` for stream reads
- Calls `update_hydrocracking_streams_v2` for hydrocracker reconciliation
- Keeps optional RSTOIC → reactor conversion helpers available (lightweight / opt-in)

What this script does:
- Linearly sweep H2O feed (component mole flow on `1-H2O-MU` by default)
- For each point: set H2O, run Aspen, apply hydrocracker update, collect:
    - `CO_pct_pre_reactor` (from reactor-inlet stream — `2-IN-FT`)
    - `H2O_over_C` (molar basis; use PROP-1 if available, else compute from mole flows)
    - `kerosene_mass_flow`, `naphtha_mass_flow` (same streams used in `batch_runner`)
- Save CSV (ordered columns), optional plots, and print+store correlation signs

IMPORTANT: stream-name constants are defined near the top and can be adjusted by hand
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

# repo-root discovery / robust imports (same approach as batch_runner)
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

if REPO_ROOT is None:
    try:
        REPO_ROOT = str(MODULE_DIR.parents[3])
    except Exception:
        REPO_ROOT = str(MODULE_DIR)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))
aspensub = MODULE_DIR / 'Aspen'
if aspensub.exists() and str(aspensub) not in sys.path:
    sys.path.insert(0, str(aspensub))

# Aspen / helpers
from CodeLibrary import Simulation
from Aspen.AspenTester import BLK_Apply_Conversions_From_RSTOIC as _BLK_Apply_Conversions_From_RSTOIC  # imported for completeness; not referenced in this runner
from Aspen.hydrocracking_v2 import update_hydrocracking_streams_v2
from Aspen.CustomSimualtion import iterate_rstoic_until_converged

# plotting / data
import numpy as np
import pandas as pd
import matplotlib
# prefer non-interactive backend when running headless
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ----------------- Stream / file constants (replaceable by user) -----------------
# These IDs follow the same nodes used by `batch_runner.py` and other scripts
H2O_FEED_NODE = '1-H2O-MU'        # component-driven H2O feed node (placeholder)
REACTOR_INLET_NODE = '2-IN-FT'    # stream immediately before reactor (CO% taken from here)
KERO_NODE = '9-KERO'              # hydrocracker-adjusted kerosene stream
NAPHTA_NODE = '9-NAPHTA'          # hydrocracker-adjusted naphtha stream
CARBFLO_PROP1_TREE_NODE = r"\Data\Blocks\CARBFLO\Output\Prop Data\ANALPROP\PROP-1"

DEFAULT_BKP = "FTS copy.bkp"
DEFAULT_OUTNAME = "h2o_sweep_results.csv"

# sensible default sweep (user can override on CLI)
DEFAULT_H2O_FLOW = 2500
DEFAULT_H2O_PCT = 1000

# required CSV column ordering (must match user's spec)
CSV_COLUMNS = ['H2O_feed', 'H2O_over_C', 'CO_pct_pre_reactor', 'kerosene_mass_flow', 'naphtha_mass_flow']


def corr_sign(a: pd.Series, b: pd.Series) -> tuple[int, float]:
    """Return (sign, r) where sign in {-1,0,1} and r is Pearson r (or nan).

    - sign is 1 for positive correlation, -1 for negative, 0 for undefined/insufficient data.
    - r is the Pearson correlation coefficient (float) or nan when undefined.
    """
    paired = pd.concat([a, b], axis=1).dropna()
    if paired.shape[0] < 2:
        return 0, float('nan')
    x = paired.iloc[:, 0]
    y = paired.iloc[:, 1]
    if x.nunique() <= 1 or y.nunique() <= 1:
        return 0, float('nan')
    r = x.corr(y)
    if pd.isna(r):
        return 0, float('nan')
    r_f = float(r)
    return (int(np.sign(r_f)) if r_f != 0.0 else 0, r_f)


@dataclass
class H2OSweepConfig:
    bkp_name: str = DEFAULT_BKP
    visibility: bool = False
    inlet_stream: str = REACTOR_INLET_NODE
    kero_node: str = KERO_NODE
    naphtha_node: str = NAPHTA_NODE
    hydrocracker: bool = True
    # H2O sweep requires RSTOIC iteration by default (can be disabled with --no-rstoic)
    iterate_rstoic: bool = True
    results_csv: str = DEFAULT_OUTNAME
    save_each: bool = False
    # when True, print progress and diagnostic info to the terminal
    verbose: bool = True


class H2OSweepRunner:
    """Runner that mirrors BatchRunner behaviour but sweeps H2O component flow."""

    def __init__(self, cfg: H2OSweepConfig) -> None:
        self.cfg = cfg
        candidate = Path(cfg.bkp_name)
        if candidate.is_file():
            self.bkp_path = candidate
        else:
            p_local = MODULE_DIR / cfg.bkp_name
            p_aspensub = MODULE_DIR / 'Aspen' / cfg.bkp_name
            if p_local.exists():
                self.bkp_path = p_local
            elif p_aspensub.exists():
                self.bkp_path = p_aspensub
            else:
                self.bkp_path = p_local
        if not self.bkp_path.exists():
            raise FileNotFoundError(f"Aspen .bkp not found: {self.bkp_path}")
        self.sim: Optional[Simulation] = None

    def open(self) -> None:
        if self.sim is not None:
            return

        primary_err = None
        fallback_err = None

        # Primary attempt: use CodeLibrary.Simulation (normal path)
        try:
            self.sim = Simulation(
                AspenFileName=str(self.bkp_path.resolve()),
                WorkingDirectoryPath=str(self.bkp_path.parent.resolve()),
                VISIBILITY=self.cfg.visibility,
            )
            return
        except Exception as e:
            primary_err = e
            print(f"Warning: Simulation(...) failed: {primary_err}; attempting COM fallback")

        # Fallback 1: recreate the Aspen COM Document and retry Simulation()
        try:
            # use importlib + getattr so static analyzers (Pylance) don't flag `gencache`
            import importlib
            win32 = importlib.import_module('win32com.client')  # runtime-only import
            gencache = getattr(win32, 'gencache')  # type: ignore[attr-defined]
            doc = gencache.EnsureDispatch('Apwn.Document')

            # Replace class-level AspenSimulation in CodeLibrary.Simulation and retry
            setattr(Simulation, 'AspenSimulation', doc)
            self.sim = Simulation(
                AspenFileName=str(self.bkp_path.resolve()),
                WorkingDirectoryPath=str(self.bkp_path.parent.resolve()),
                VISIBILITY=self.cfg.visibility,
            )
            print("Fallback succeeded: opened .bkp after recreating Aspen COM Document")
            return
        except Exception as e:
            fallback_err = e
            print(f"Fallback open attempt failed: {fallback_err}")

        # If we reach here, re-raise an informative error
        raise RuntimeError(f"Unable to open Aspen .bkp: {self.bkp_path!s} (primary error: {primary_err}; fallback error: {fallback_err})")

    def close(self) -> None:
        if self.sim is not None:
            close_fn = getattr(self.sim, 'Close', None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            self.sim = None

    # --- low-level helpers -------------------------------------------------
    def _stream_total(self, stream_id: str) -> Optional[float]:
        """Best-effort total flow read from a stream.

        Prefers `MassFlowList` (mass units) when available; falls back to
        `MoleFlowList` (molar units) otherwise. Returns None on read errors.
        """
        assert self.sim is not None
        try:
            outs = self.sim.STRM_GET_OUTPUTS(stream_id)
            # prefer mass flows when available (report mass flow if Aspen provides it)
            mass_flows = outs.get('MassFlowList')
            if isinstance(mass_flows, (list, tuple)):
                return float(sum(float(x) for x in mass_flows))
            if isinstance(mass_flows, (int, float)):
                return float(mass_flows)

            # fallback to mole flows
            flows = outs.get('MoleFlowList')
            if isinstance(flows, (list, tuple)):
                return float(sum(float(x) for x in flows))
            if flows is not None:
                return float(flows)
        except Exception:
            return None
        return None

    def _safe_float(self, x: Any) -> Optional[float]:
        """Safe conversion to float for values coming from Aspen outputs.

        Returns None if value cannot be converted.
        """
        try:
            return float(x)
        except Exception:
            return None

    def _stream_details(self, stream_id: str) -> Dict[str, Any]:
        """Return details about a stream (mass/mole totals and raw outputs).

        Always safe to call for diagnostic printing; returns None-valued totals
        when the corresponding lists are absent or when a COM error occurs.
        """
        # narrow type for the language server / type checker
        assert self.sim is not None
        try:
            outs = self.sim.STRM_GET_OUTPUTS(stream_id)
        except Exception:
            return {'mass_total': None, 'mole_total': None, 'raw': None}

        mass = None
        mole = None
        mlist = outs.get('MassFlowList')
        if isinstance(mlist, (list, tuple)):
            try:
                mass = float(sum(float(x) for x in mlist))
            except Exception:
                mass = None
        elif isinstance(mlist, (int, float)):
            mass = float(mlist)

        flist = outs.get('MoleFlowList')
        if isinstance(flist, (list, tuple)):
            try:
                mole = float(sum(float(x) for x in flist))
            except Exception:
                mole = None
        elif isinstance(flist, (int, float)):
            mole = float(flist)

        return {'mass_total': mass, 'mole_total': mole, 'raw': outs}

    def _get_component_flow_from_outputs(self, outs: Dict[str, Any], comp_name: str) -> Optional[float]:
        """Return component mole flow (kmol/hr) if available from STRM_GET_OUTPUTS outputs."""
        # preferred: MoleFlowList with CompoundNameList
        names = outs.get('CompoundNameList', [])
        flows = outs.get('MoleFlowList', None)
        if isinstance(names, (list, tuple)) and isinstance(flows, (list, tuple)):
            for i, n in enumerate(names):
                if str(n).upper() == comp_name.upper():
                    try:
                        return float(flows[i])
                    except Exception:
                        return None
        # fallback: if only mole fractions are provided, try to use total moleflow
        frac = outs.get('MoleFracList', None)
        if isinstance(names, (list, tuple)) and isinstance(frac, (list, tuple)):
            # find comp idx
            idx = None
            for i, n in enumerate(names):
                if str(n).upper() == comp_name.upper():
                    idx = i
                    break
            if idx is not None:
                # try to get total moleflow scalar node
                total = outs.get('MoleFlowList')
                if isinstance(total, (int, float)):
                    try:
                        return float(total) * float(frac[idx])
                    except Exception:
                        return None
        return None

    def _compute_prop1_from_components(self, names: Sequence[str], moleflows: Sequence[Union[float, int, str]]) -> float:
        """Heuristic to compute carbon-atom flow (PROP-1) from component names and mole flows.
        This mirrors the simple approach used in the repository audit tests where names like
        'C10' -> 10 carbons and common species (CO, CO2, CH4, MEOH) map to 1 carbon.

        Accepts flexible sequence types (lists/tuples) and numeric-or-string moleflow entries
        because `STRM_GET_OUTPUTS` may return mixed-type sequences.
        """
        def carbon_count(name: str) -> int:
            if not name:
                return 0
            n = str(name).upper()
            # 'C12' style species: extract digits following 'C'
            if n.startswith('C') and len(n) > 1 and n[1:].isdigit():
                try:
                    return int(n[1:])
                except Exception:
                    return 0
            if n in ('CO', 'CO2', 'CH4', 'MEOH', 'METHANOL'):
                return 1
            # default: assume no carbon
            return 0

        total_c = 0.0
        for nm, f in zip(names, moleflows):
            total_c += float(f) * carbon_count(nm)
        return float(total_c)

    def _compute_h2o_over_c(self, stream_id: str) -> Optional[float]:
        """Compute H2O/C = H2O_molflow / carbon_atom_flow for `stream_id`.
        - If PROP-1 available via tree or stream outputs, use it.
        - Otherwise compute from component mole flows.
        Returns None when denominator is zero / data unavailable.
        """
        assert self.sim is not None
        try:
            outs = self.sim.STRM_GET_OUTPUTS(stream_id)
        except Exception:
            return None

        # 1) try to find PROP-1 in stream outputs (best-effort scanning)
        # look through numeric fields in `outs` for something labelled PROP-1
        for k, v in outs.items():
            if isinstance(k, str) and 'PROP' in k.upper() and '1' in k:
                # prefer robust conversion (v may be str/int/float or other ASPEN object)
                v_f = self._safe_float(v)
                if v_f is None or v_f == 0.0:
                    continue
                try:
                    h2o_flow = self._get_component_flow_from_outputs(outs, 'H2O') or 0.0
                    h2o_f = self._safe_float(h2o_flow)
                    if h2o_f is None:
                        continue
                    return h2o_f / v_f
                except Exception:
                    pass

        # 2) try global CARBFLO PROP-1 (tree node) via Simulation API if available
        try:
            tree_get = getattr(self.sim, 'TREE_Get_Node_Value', None)
            if callable(tree_get):
                raw = tree_get(CARBFLO_PROP1_TREE_NODE)
                prop1_val = self._safe_float(raw)
                if prop1_val is None:
                    return None
                # use reactor-inlet H2O molflow (preferred)
                h2o_mf = self._get_component_flow_from_outputs(outs, 'H2O')
                if h2o_mf is None:
                    return None
                if prop1_val == 0:
                    return None
                return float(h2o_mf) / float(prop1_val)
        except Exception:
            # ignore and fall through to computed method
            pass

        # 3) compute carbon-atom flow from per-component moleflows
        names = outs.get('CompoundNameList', [])
        moleflows = outs.get('MoleFlowList', None)
        if isinstance(names, (list, tuple)) and isinstance(moleflows, (list, tuple)):
            try:
                prop1_calc = self._compute_prop1_from_components(names, moleflows)
                if prop1_calc == 0:
                    return None
                h2o_mf = None
                # find H2O flow in the same output structure
                for i, n in enumerate(names):
                    if str(n).upper() == 'H2O':
                        h2o_mf = float(moleflows[i])
                        break
                if h2o_mf is None:
                    # if H2O not in list, try a dedicated component read
                    h2o_mf = self._get_component_flow_from_outputs(outs, 'H2O')
                if h2o_mf is None:
                    return None
                return float(h2o_mf) / float(prop1_calc)
            except Exception:
                return None

        # last-resort: try scalar moleflow nodes
        # attempt to compute H2O fraction * total
        h2o_mf = self._get_component_flow_from_outputs(outs, 'H2O')
        if h2o_mf is None:
            return None
        # denominator unknown → cannot compute
        return None

    # --- main run logic --------------------------------------------------
    def run_case(self, h2o_value: float, apply_rstoic: bool = False) -> Dict[str, Any]:
        """Set H2O (component mole flow), run Aspen, apply hydrocracker, collect outputs.

        Returns a dict with the exact keys required for CSV (plus optional _error).
        """
        assert self.sim is not None
        res: Dict[str, Any] = {
            'H2O_feed': float(h2o_value),
        }

        # 1) write H2O component mole flow to expected feed node
        try:
            self.sim.STRM_Set_ComponentFlowRate(H2O_FEED_NODE, float(h2o_value), 'H2O')
            # attempt tree write for UI visibility (best-effort)
            try:
                tree = getattr(self.sim, 'AspenSimulation').Tree
                comp_node = tree.FindNode(r"\Data\Streams\%s\Input\FLOW\MIXED\H2O" % H2O_FEED_NODE)
                if comp_node is not None:
                    comp_node.Value = float(h2o_value)
            except Exception:
                pass
        except Exception as e:
            res['_error'] = f"set_H2O_failed: {e}"
            return res

        # 2) run Aspen
        try:
            self.sim.EngineRun()
        except Exception as e:
            res['_error'] = f"EngineRun_failed_initial: {e}"
            return res

        # 3) optional RSTOIC iteration (must run after baseline run — H2O affects CO at reactor inlet)
        if apply_rstoic and self.cfg.iterate_rstoic:
            try:
                iter_res = iterate_rstoic_until_converged(
                    self.sim,
                    co2_feed_stream='1-CO2-MU',
                    reactor_inlet_stream=REACTOR_INLET_NODE,
                    blockname='FTS-REAC',
                    dry_run=False,
                    run_after_apply=True,
                    verbose=False,
                )
            except Exception as e:
                # record error but continue to hydrocracker step
                res['_error_rstoic_iter'] = str(e)
                res['rstoic_converged'] = False
                res['rstoic_iterations'] = 0
                res['rstoic_co'] = None
            else:
                res['_rstoic_iter'] = iter_res
                # expose convenient summary fields for CSV/debugging
                res['rstoic_converged'] = bool(iter_res.get('converged', False))
                res['rstoic_iterations'] = int(iter_res.get('iterations', 0))
                res['rstoic_co'] = float(iter_res.get('co', 0.0))

        # 4) hydrocracker reconciliation (run after RSTOIC convergence)
        if self.cfg.hydrocracker:
            # run synchronously on the main thread (COM requires thread initialization)
            try:
                update_hydrocracking_streams_v2(self.sim, inlet_stream=self.cfg.inlet_stream, outlet_stream=self.cfg.naphtha_node)
            except Exception as e:
                # record failure and continue (do not crash whole sweep)
                res['_error'] = f"hydrocracker_failed: {e}"
                return res

            # run engine again after hydrocracker adjustments
            try:
                self.sim.EngineRun()
            except Exception as e:
                res['_error'] = f"EngineRun_failed_post_hydro: {e}"
                return res

        # 5) collect outputs
        try:
            # CO% from reactor inlet — prefer MoleFracList, fallback to MoleFlowList fraction
            inlet_outs = None
            co_pct = None
            try:
                inlet_outs = self.sim.STRM_GET_OUTPUTS(REACTOR_INLET_NODE)
                names = inlet_outs.get('CompoundNameList', [])
                molefracs = inlet_outs.get('MoleFracList', None)
                moleflows = inlet_outs.get('MoleFlowList', None)
                if isinstance(names, (list, tuple)):
                    idx = next((i for i, n in enumerate(names) if str(n).upper() == 'CO'), None)
                    if idx is not None:
                        if isinstance(molefracs, (list, tuple)):
                            co_pct = float(molefracs[idx]) * 100.0
                        elif isinstance(moleflows, (list, tuple)):
                            total = float(sum(float(x) for x in moleflows)) if moleflows else None
                            if total and total > 0:
                                co_pct = float(moleflows[idx]) / float(total) * 100.0
            except Exception:
                co_pct = None

            # If CO% wasn't readable from the stream, fall back to the RSTOIC-sampled CO (if present)
            if co_pct is None:
                r_co = res.get('rstoic_co') or (res.get('_rstoic_iter', {}) or {}).get('co')
                try:
                    if r_co is not None:
                        co_pct = float(r_co) * 100.0
                except Exception:
                    co_pct = None

            res['CO_pct_pre_reactor'] = None if co_pct is None else float(co_pct)

            # H2O_over_C computed on reactor inlet (best-effort)
            h2o_over_c = self._compute_h2o_over_c(REACTOR_INLET_NODE)
            res['H2O_over_C'] = None if h2o_over_c is None else float(h2o_over_c)

            # product totals (use same aggregation logic as batch_runner)
            ker = self._stream_total(self.cfg.kero_node)
            nap = self._stream_total(self.cfg.naphtha_node)

            # determine which list supplied the values and add diagnostic flags
            kero_details = self._stream_details(self.cfg.kero_node)
            nap_details = self._stream_details(self.cfg.naphtha_node)

            kero_type = 'mass' if kero_details.get('mass_total') is not None else ('mole' if kero_details.get('mole_total') is not None else 'none')
            nap_type = 'mass' if nap_details.get('mass_total') is not None else ('mole' if nap_details.get('mole_total') is not None else 'none')

            # follow user's required key names (explicitly _mass_flow suffix) but record type
            res['kerosene_mass_flow'] = ker
            res['naphtha_mass_flow'] = nap
            res['kero_flow_type'] = kero_type
            res['naphtha_flow_type'] = nap_type

            # terminal notifications for suspicious magnitudes
            try:
                if self.cfg.verbose:
                    print(f"  [STREAM] {self.cfg.kero_node}: flow={ker!r} (type={kero_type})")
                    print(f"  [STREAM] {self.cfg.naphtha_node}: flow={nap!r} (type={nap_type})")

                if ker is not None and nap is not None and ker > 0:
                    ratio = nap / ker
                    if ratio > 100 or ratio < 0.01:
                        print("  ⚠️  Suspicious product ratio detected: naphtha/kerosene =", ratio)
                        print("  → Dumping raw STRM_GET_OUTPUTS for debugging:")
                        print(f"    {self.cfg.kero_node} ->", kero_details['raw'])
                        print(f"    {self.cfg.naphtha_node} ->", nap_details['raw'])
            except Exception:
                pass
        except Exception as e:
            res['_error'] = f"collect_failed: {e}"

        # 6) optional save
        if self.cfg.save_each:
            try:
                self.sim.Save()
            except Exception:
                pass

        return res

    def run_sweep(self, h2o_values: List[float], out_dir: Optional[Path] = None, save_csv: bool = True, save_plots: bool = True, show: bool = False) -> pd.DataFrame:
        out_dir_resolved = Path(out_dir).resolve() if out_dir is not None else Path('.').resolve()
        out_dir_resolved.mkdir(parents=True, exist_ok=True)

        self.open()
        rows: List[Dict[str, Any]] = []
        for i, h2o in enumerate(list(h2o_values)):
            print(f"[Run {i+1}/{len(h2o_values)}] H2O={h2o}")
            # enforce RSTOIC convergence per H2O point unless user explicitly disabled it
            row = self.run_case(h2o, apply_rstoic=True)
            row['run_index'] = i
            rows.append(row)

        # Build DataFrame with required columns and ordering
        df = pd.DataFrame(rows)
        # ensure columns exist and are in exact required order for CSV
        for col in CSV_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        df_out = df[CSV_COLUMNS].copy()

        # append helpful debug columns (kept after the required columns)
        for dbg in ('rstoic_converged', 'rstoic_iterations', 'rstoic_co', '_rstoic_iter', '_error', 'kero_flow_type', 'naphtha_flow_type'):
            if dbg in df.columns:
                df_out[dbg] = df[dbg]
            else:
                df_out[dbg] = pd.NA

        if save_csv:
            out_csv = out_dir_resolved / self.cfg.results_csv
            df_out.to_csv(out_csv, index=False)
            print(f"Saved CSV: {out_csv}")

        # compute & store correlation signs
        corr_info: Dict[str, Any] = {}
        try:
            # ensure numeric series (dropna for correlation calculation)
            s_h2o_c = pd.to_numeric(df_out['H2O_over_C'], errors='coerce')
            s_kero = pd.to_numeric(df_out['kerosene_mass_flow'], errors='coerce')
            s_nap = pd.to_numeric(df_out['naphtha_mass_flow'], errors='coerce')
            s_co = pd.to_numeric(df_out['CO_pct_pre_reactor'], errors='coerce')

            # use module-level `corr_sign` (typed and unit-tested)
            # previously this helper was nested with no annotations which confused the type-checker


            sign_kero_vs_nap, r_kn = corr_sign(s_kero, s_nap)
            sign_h2oc_kero, r_hk = corr_sign(s_h2o_c, s_kero)
            sign_h2oc_nap, r_hn = corr_sign(s_h2o_c, s_nap)
            sign_h2oc_co, r_hc = corr_sign(s_h2o_c, s_co)

            corr_info = {
                'kero_vs_nap_sign': int(sign_kero_vs_nap), 'kero_vs_nap_r': r_kn,
                'H2OoverC_vs_kero_sign': int(sign_h2oc_kero), 'H2OoverC_vs_kero_r': r_hk,
                'H2OoverC_vs_nap_sign': int(sign_h2oc_nap), 'H2OoverC_vs_nap_r': r_hn,
                'H2OoverC_vs_CO_sign': int(sign_h2oc_co), 'H2OoverC_vs_CO_r': r_hc,
            }
            # print concise summary
            print("Correlation signs:")
            print(f"  kerosene vs naphtha: {'+' if sign_kero_vs_nap>0 else ('-' if sign_kero_vs_nap<0 else '0')} (r={r_kn:.3f})")
            print(f"  H2O/C vs kerosene : {'+' if sign_h2oc_kero>0 else ('-' if sign_h2oc_kero<0 else '0')} (r={r_hk:.3f})")
            print(f"  H2O/C vs naphtha  : {'+' if sign_h2oc_nap>0 else ('-' if sign_h2oc_nap<0 else '0')} (r={r_hn:.3f})")
            print(f"  H2O/C vs CO%      : {'+' if sign_h2oc_co>0 else ('-' if sign_h2oc_co<0 else '0')} (r={r_hc:.3f})")

            # persist correlation summary
            corr_path = out_dir_resolved / 'h2o_sweep_correlations.txt'
            with corr_path.open('w') as fh:
                for k, v in corr_info.items():
                    fh.write(f"{k} = {v}\n")
            print(f"Saved correlation summary: {corr_path}")
        except Exception as e:
            print(f"Warning: failed to compute/store correlations: {e}")

        # plotting
        if save_plots:
            try:
                # plot H2O/C vs products (skip rows with NA)
                dfp = df_out.dropna(subset=['H2O_over_C', 'kerosene_mass_flow', 'naphtha_mass_flow'])
                fig, ax = plt.subplots(figsize=(8, 5))
                if not dfp.empty:
                    ax.scatter(dfp['H2O_over_C'], dfp['kerosene_mass_flow'], label='kerosene', marker='o')
                    ax.scatter(dfp['H2O_over_C'], dfp['naphtha_mass_flow'], label='naphtha', marker='s')
                ax.set_xlabel('H2O/C (molar)')
                ax.set_ylabel('Product flow (Aspen units)')
                ax.legend()
                ax.set_title('H2O/C vs product flows')
                fig.tight_layout()
                p1 = out_dir_resolved / 'h2o_c_vs_products.png'
                fig.savefig(p1)
                plt.close(fig)
                print(f"Saved plot: {p1}")

                # plot H2O/C vs CO% (skip rows with NA)
                dfc = df_out.dropna(subset=['H2O_over_C', 'CO_pct_pre_reactor'])
                fig2, ax2 = plt.subplots(figsize=(8, 4))
                if not dfc.empty:
                    ax2.scatter(dfc['H2O_over_C'], dfc['CO_pct_pre_reactor'], color='C2')
                ax2.set_xlabel('H2O/C (molar)')
                ax2.set_ylabel('CO % (pre-reactor)')
                ax2.set_title('H2O/C vs CO % pre-reactor')
                fig2.tight_layout()
                p2 = out_dir_resolved / 'h2o_c_vs_co_pct.png'
                fig2.savefig(p2)
                plt.close(fig2)
                print(f"Saved plot: {p2}")

                if show:
                    # only show if user explicitly requested (and running in an interactive env)
                    try:
                        import matplotlib.pyplot as _plt
                        _plt.show()
                    except Exception:
                        pass
            except Exception as e:
                print(f"Warning: plotting failed: {e}")

        return df_out


# ---- CLI ------------------------------------------------------------------
if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser(description='H2O sweep runner (mirror of batch_runner but varies H2O feed).')
    p.add_argument('--h2o-min', type=float, default=DEFAULT_H2O_FLOW * (1 - DEFAULT_H2O_PCT), help='Start H2O component flow (kmol/hr)')
    p.add_argument('--h2o-max', type=float, default=DEFAULT_H2O_FLOW * (1 + DEFAULT_H2O_PCT), help='Stop H2O component flow (kmol/hr)')
    p.add_argument('--n', type=int, default=6, help='Number of sweep points')

    p.add_argument('--out-dir', type=str, default='.', help='Directory to write CSV/plots')
    p.add_argument('--save-csv', action='store_true', help='Save CSV results')
    p.add_argument('--save-plots', action='store_true', help='Save PNG plots')
    p.add_argument('--no-show', action='store_true', help='Do not show plots interactively')

    # mirror batch_runner options
    p.add_argument('--bkp', type=str, default=None, help='Alternate .bkp filename/path')
    p.add_argument('--visibility', action='store_true', help='Open Aspen with visible UI')
    p.add_argument('--no-hydro', dest='hydro', action='store_false', help='Do not run hydrocracker reconciliation')
    p.add_argument('--no-rstoic', dest='rstoic', action='store_false', help='Do not attempt RSTOIC iteration')
    p.add_argument('--save-each', action='store_true', help='Call sim.Save() after each case')
    p.add_argument('--verbose', action='store_true', help='Print progress and diagnostics to the terminal')

    # Interactive prompt when the script is run without arguments (TTY required)
    def _interactive_build_argv(parser: argparse.ArgumentParser) -> list:
        import shlex
        print('\nInteractive mode — press Enter to accept defaults. Type HELP to show argparse help.\n')
        argv: list[str] = []
        for action in parser._actions:
            # skip help and positional actions
            if not action.option_strings or action.dest == 'help':
                continue
            opt = action.option_strings[-1]
            default = action.default
            help_text = (action.help or '').strip()

            # boolean flags (store_true / store_false)
            if isinstance(action, argparse._StoreTrueAction):
                resp = input(f"{opt} - {help_text} [y/N] (default: {'Y' if default else 'N'}): ").strip()
                if resp.lower() in ('y', 'yes'):
                    argv.append(opt)
                continue
            if isinstance(action, argparse._StoreFalseAction):
                # e.g. --no-hydro ; ask the positive question to be clearer
                resp = input(f"Enable {action.dest}? [Y/n] (default: {'Y' if action.default else 'N'}): ").strip()
                if resp.lower() in ('n', 'no'):
                    argv.append(opt)
                continue

            # other argument types
            choices = getattr(action, 'choices', None)
            if choices:
                prompt = f"{opt} - {help_text} choices={choices} [default: {default}]: "
            else:
                prompt = f"{opt} - {help_text} [default: {default}]: "

            val = input(prompt).strip()
            if val.lower() in ('help', 'h'):
                parser.print_help()
                val = input(prompt).strip()

            if val == '':
                # keep implicit default by not adding to argv
                continue

            try:
                parts = shlex.split(val)
            except Exception:
                parts = [val]
            argv.append(opt)
            argv.extend(parts)
        return argv

    # Use interactive prompts if script launched with no CLI args and a TTY is available
    if len(sys.argv) == 1 and sys.stdin is not None and sys.stdin.isatty():
        user_argv = _interactive_build_argv(p)
        print('\nRunning with:', ' '.join(user_argv) if user_argv else '(defaults)')
        args = p.parse_args(user_argv)
    else:
        args = p.parse_args()

    cfg = H2OSweepConfig(
        bkp_name=args.bkp if args.bkp is not None else DEFAULT_BKP,
        visibility=args.visibility,
        hydrocracker=args.hydro,
        iterate_rstoic=args.rstoic,
        save_each=args.save_each,
        results_csv=DEFAULT_OUTNAME,
        verbose=args.verbose,
    )

    runner = H2OSweepRunner(cfg)
    try:
        if not (args.h2o_min > 0 and args.h2o_max > 0):
            raise SystemExit("--h2o-min and --h2o-max must be positive")
        if not (args.h2o_min < args.h2o_max):
            raise SystemExit("--h2o-min must be less than --h2o-max")

        h2o_vals = list(np.linspace(args.h2o_min, args.h2o_max, args.n))
        df = runner.run_sweep(h2o_vals, out_dir=Path(args.out_dir), save_csv=args.save_csv, save_plots=args.save_plots, show=not args.no_show)
        if args.save_csv:
            print(f"Done — wrote results to {Path(args.out_dir) / cfg.results_csv}")
        else:
            print("Done — sweep completed (CSV not saved unless --save-csv is provided)")
    finally:
        runner.close()
