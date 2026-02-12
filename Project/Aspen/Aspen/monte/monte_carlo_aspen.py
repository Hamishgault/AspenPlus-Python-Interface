"""Monte Carlo driver for Aspen + hydrocracker reconciliation.

Workflow per run:
 1. vary CO2/H2 feed ratio (normal distribution)
 2. set pure-component feed flows on the Aspen model
 3. run Aspen
 4. call hydrocracker reconciliation (update_hydrocracking_streams_v2)
 5. run Aspen again
 6. record NAPHTA and KERO flows

Default test: N=3 (quick smoke test)
"""
from __future__ import annotations

import os
import sys
import csv
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple, cast

# ensure repo root on sys.path so `from CodeLibrary import Simulation` works
WORKDIR = Path(__file__).resolve().parent
# Find repository root by searching upward for CodeLibrary.py (more reliable than fixed relative path)
_search_dir = WORKDIR
REPO_ROOT = None
while True:
    if (_search_dir / "CodeLibrary.py").exists():
        REPO_ROOT = str(_search_dir)
        break
    if _search_dir.parent == _search_dir:
        break
    _search_dir = _search_dir.parent

if REPO_ROOT is None:
    # fallback to previous relative path
    REPO_ROOT = os.path.abspath(os.path.join(WORKDIR, "..", "..", "..", ".."))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Also ensure the Project/Aspen/Aspen module directory is on sys.path so local modules import
MODULE_DIR = str(WORKDIR.parent)  # Project/Aspen/Aspen
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

# Import CodeLibrary robustly (some environments modify sys.path)
try:
    from CodeLibrary import Simulation
except ModuleNotFoundError:
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    from CodeLibrary import Simulation

# Import local hydrocracker implementation
try:
    from hydrocracking_v2 import update_hydrocracking_streams_v2
except ModuleNotFoundError:
    # Try importing from module dir explicitly
    if MODULE_DIR not in sys.path:
        sys.path.insert(0, MODULE_DIR)
    from hydrocracking_v2 import update_hydrocracking_streams_v2


# --- Monte input ranges / base-case values (copy-friendly constants) -------
# CO2 / H2 feed baselines (units: kmol/hr)
CO2_BASE = 38.0
H2_BASE = 114.820896

# Sampling ranges (multiplier or absolute depending on feed_mode)
CO2_MULT_RANGE = (0.9, 1.1)         # multiplier range when using multiplier sampling
CO2_ABS_RANGE = (34.2, 41.8)        # absolute-range equivalent (±10%)

# Monte sampling defaults
MONTE_DEFAULT_SAMPLES = 200
MONTE_DEFAULT_SEED = 7

# Ratio sampling (used when feed_mode == 'preserve_total')
RATIO_MEAN = 1.0
RATIO_STD = 0.1

# Output / logging defaults
MONTE_RESULTS_CSV = "monte_results.csv"
MONTE_DEBUG_DIR = "monte_debug"

# Aspen stream identifiers (keep in sync with MonteConfig)
STREAM_CO2_NODE = "Application.Tree.Data.Streams.1-CO2-MU"
STREAM_H2_NODE = "Application.Tree.Data.Streams.1-H2-MU"
STREAM_INLET = "5-IN-EXC"
STREAM_OUTLET = "5-OUTEXC"
STREAM_NAPHTA = "Application.Tree.Data.Streams.9-NAPHTA"
STREAM_KERO = "Application.Tree.Data.Streams.9-KERO"


@dataclass
class MonteConfig:
    bkp_name: str = "FTS Alessio_CO_conv_Ref_20bar_11%.bkp"
    samples: int = 3
    # Interpretation of the sampled value depends on `feed_mode`:
    # - 'preserve_total'  (legacy): `ratio` is CO2/H2 and CO2+H2 baseline total is preserved
    # - 'fix_h2' (recommended): H2 is fixed at the baseline; `ratio` becomes a multiplier on CO2 base
    # - 'fix_co2'           : CO2 is fixed at the baseline; `ratio` becomes a multiplier on H2 base
    ratio_mean: float = 1.0
    ratio_std: float = 0.1
    feed_mode: str = "fix_h2"  # one of: 'preserve_total', 'fix_h2', 'fix_co2'

    # Optional explicit baseline overrides (if provided, they replace values read from Aspen)
    co2_base_override: float | None = None
    h2_base_override: float | None = None

    co2_node: str = "Application.Tree.Data.Streams.1-CO2-MU"
    h2_node: str = "Application.Tree.Data.Streams.1-H2-MU"
    inlet_stream: str = "5-IN-EXC"
    outlet_stream: str = "5-OUTEXC"
    naphtha_node: str = "Application.Tree.Data.Streams.9-NAPHTA"
    kero_node: str = "Application.Tree.Data.Streams.9-KERO"
    results_csv: str = "monte_results.csv"
    visibility: bool = False


# --- low-level COM helpers -------------------------------------------------

def _get_comp_flow(sim: Simulation, stream_node: str, comp_name: str) -> float | None:
    """Try common ways to read a component flow from Aspen; return None on failure."""
    try:
        outputs = sim.STRM_GET_OUTPUTS(stream_node.split('.')[-1])
        names = outputs.get("CompoundNameList", [])
        flows = outputs.get("MoleFlowList", [])
        if isinstance(names, (list, tuple)) and isinstance(flows, (list, tuple)):
            for n, f in zip(names, flows):
                if str(n).upper() == comp_name.upper():
                    return float(f)
    except Exception:
        pass
    # fallback: try reading tree node directly (best-effort)
    try:
        tree = cast(Any, sim).Tree
        node = tree.FindNode(stream_node) if getattr(tree, "FindNode", None) is not None else None
        if node is not None:
            return float(node.Value)
    except Exception:
        pass
    return None


def _set_comp_flow(sim: Simulation, stream_id: str, comp_name: str, value: float) -> bool:
    """Set component mole flow for a stream; return True on success."""
    try:
        sim.STRM_Set_ComponentFlowRate(stream_id, float(value), comp_name)
        return True
    except Exception:
        # best-effort fallback not implemented; return False
        return False


def _get_products(sim: Simulation, nap_node: str, ker_node: str) -> Tuple[float, float]:
    """Return total mole flow for product streams `nap_node` and `ker_node`.

    The product identifiers (e.g. 'Application.Tree.Data.Streams.9-NAPHTA')
    refer to entire Aspen streams; we sum the MoleFlowList returned by
    STRM_GET_OUTPUTS(stream_id) to get the stream total.
    """
    def _stream_total(stream_node: str) -> float:
        stream_id = stream_node.split('.')[-1]
        try:
            outputs = sim.STRM_GET_OUTPUTS(stream_id)
            flows = outputs.get("MoleFlowList", [])
            if isinstance(flows, (list, tuple)):
                return float(sum(float(f) for f in flows))
        except Exception:
            pass
        # fallback: try reading a single component named like stream (rare)
        val = _get_comp_flow(sim, stream_node, stream_id)
        return 0.0 if val is None else float(val)

    nap_total = _stream_total(nap_node)
    ker_total = _stream_total(ker_node)
    return nap_total, ker_total


# --- main driver -----------------------------------------------------------

def run_monte_carlo(cfg: MonteConfig) -> list[Dict[str, object]]:
    results: list[Dict[str, object]] = []

    # locate the Aspen .bkp in the parent Aspen folder (script lives in monte/)
    script_dir = Path(__file__).resolve().parent
    project_aspen_dir = script_dir.parent  # Project/Aspen/Aspen

    # allow absolute path or repo-relative path
    candidate = Path(cfg.bkp_name)
    if candidate.is_file():
        bkp_path = candidate
    else:
        bkp_path = project_aspen_dir / cfg.bkp_name

    if not bkp_path.exists():
        raise FileNotFoundError(f"Aspen .bkp not found: {bkp_path}")

    sim = Simulation(AspenFileName=str(bkp_path), WorkingDirectoryPath=str(project_aspen_dir), VISIBILITY=cfg.visibility)

    # initial run to read baseline CO2/H2
    sim.EngineRun()
    co2_base = _get_comp_flow(sim, cfg.co2_node, "CO2")
    h2_base = _get_comp_flow(sim, cfg.h2_node, "H2")
    if co2_base is None or h2_base is None:
        raise RuntimeError("Failed to read baseline CO2/H2 from model streams")

    # apply optional baseline overrides (allow user to force specific base-case flows)
    co2_base = float(cfg.co2_base_override) if cfg.co2_base_override is not None else float(co2_base)
    h2_base = float(cfg.h2_base_override) if cfg.h2_base_override is not None else float(h2_base)
    baseline_total = float(co2_base) + float(h2_base)

    print(f"Baseline feeds read: CO2={co2_base:.6f} kmol/hr, H2={h2_base:.6f} kmol/hr -- feed_mode={cfg.feed_mode}")

    for i in range(cfg.samples):
        # sample a positive multiplier/value (re-interpretation depends on feed_mode)
        sample = -1.0
        attempts = 0
        while sample <= 0 and attempts < 10:
            sample = random.normalvariate(cfg.ratio_mean, cfg.ratio_std)
            attempts += 1
        if sample <= 0:
            sample = max(1e-6, cfg.ratio_mean)

        if cfg.feed_mode == "preserve_total":
            # legacy behavior: `sample` is CO2/H2 ratio and CO2+H2 total is preserved
            ratio = sample
            h2_flow = baseline_total / (1.0 + ratio)
            co2_flow = baseline_total - h2_flow
        elif cfg.feed_mode == "fix_h2":
            # keep H2 fixed at baseline; `sample` is a multiplier applied to CO2 base
            multiplier = sample
            h2_flow = float(h2_base)
            co2_flow = float(co2_base) * multiplier
            ratio = co2_flow / h2_flow if h2_flow != 0 else float("inf")
        elif cfg.feed_mode == "fix_co2":
            # keep CO2 fixed at baseline; `sample` is a multiplier applied to H2 base
            multiplier = sample
            co2_flow = float(co2_base)
            h2_flow = float(h2_base) * multiplier
            ratio = co2_flow / h2_flow if h2_flow != 0 else float("inf")
        else:
            raise ValueError(f"Unknown feed_mode: {cfg.feed_mode}")

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        print(f"[Run {i+1}/{cfg.samples}] ratio={ratio:.4f}  — setting feeds CO2={co2_flow:.4f}, H2={h2_flow:.4f}")

        # 1) set feed component flows
        ok_co2 = _set_comp_flow(sim, cfg.co2_node.split('.')[-1], "CO2", co2_flow)
        ok_h2 = _set_comp_flow(sim, cfg.h2_node.split('.')[-1], "H2", h2_flow)
        if not ok_co2 or not ok_h2:
            print(f"    ⚠️  Failed to set feed flows for run {i+1}")
            results.append({"run": i, "ratio": ratio, "co2": co2_flow, "h2": h2_flow, "naphtha": None, "kero": None, "status": "set_feed_failed", "time": timestamp})
            continue

        print("    ▶ Running Aspen (initial)")
        # 2) first Aspen run
        sim.EngineRun()
        print("    ✅ Aspen initial run complete")

        # 3) reconcile hydrocracker (Primary -> Secondary)
        print("    ▶ Reconciling hydrocracker (Primary -> Secondary)")
        try:
            update_hydrocracking_streams_v2(sim, inlet_stream=cfg.inlet_stream, outlet_stream=cfg.outlet_stream)
            print("    ✅ Hydrocracker updated")
        except Exception as exc:
            print(f"    ⚠️  Hydrocracker reconciliation failed: {exc}")
            results.append({"run": i, "ratio": ratio, "co2": co2_flow, "h2": h2_flow, "naphtha": None, "kero": None, "status": f"hydrocracker_failed: {exc}", "time": timestamp})
            continue

        print("    ▶ Running Aspen (post-hydrocracker)")
        # 4) run Aspen again
        sim.EngineRun()
        print("    ✅ Aspen post-hydrocracker run complete")

        # 5) collect outputs
        nap, ker = _get_products(sim, cfg.naphtha_node, cfg.kero_node)
        print(f"    Results: NAPHTA={nap:.6f}, KERO={ker:.6f}")

        debug_file_path = None
        # Capture diagnostics when either product is zero
        if (nap == 0.0) or (ker == 0.0):
            try:
                dbg_lines = []
                dbg_lines.append(f"Timestamp: {timestamp}")
                dbg_lines.append(f"run: {i}, ratio: {ratio:.6g}, co2: {co2_flow:.6g}, h2: {h2_flow:.6g}")
                dbg_lines.append("\n[Stream 5-IN-EXC outputs]")
                try:
                    in_out = sim.STRM_GET_OUTPUTS(cfg.inlet_stream)
                    dbg_lines.append(str(in_out))
                except Exception as _err:
                    dbg_lines.append(f"Failed to read {cfg.inlet_stream}: {_err}")
                dbg_lines.append("\n[Hydrocracker OUT (5-OUTEXC) outputs]")
                try:
                    out_out = sim.STRM_GET_OUTPUTS(cfg.outlet_stream)
                    dbg_lines.append(str(out_out))
                except Exception as _err:
                    dbg_lines.append(f"Failed to read {cfg.outlet_stream}: {_err}")
                dbg_lines.append(f"\n[Product stream outputs: {cfg.naphtha_node.split('.')[-1]}]")
                try:
                    prod_out = sim.STRM_GET_OUTPUTS(cfg.naphtha_node.split('.')[-1])
                    dbg_lines.append(str(prod_out))
                except Exception as _err:
                    dbg_lines.append(f"Failed to read product stream: {_err}")

                # Try reading tree nodes for raw values
                dbg_lines.append("\n[Tree nodes read (best-effort)]")
                try:
                    tree = cast(Any, sim).Tree
                    for node_path in (cfg.co2_node, cfg.h2_node, cfg.naphtha_node, cfg.kero_node):
                        try:
                            node = tree.FindNode(node_path)
                            dbg_lines.append(f"{node_path}: {getattr(node, 'Value', 'N/A')}")
                        except Exception:
                            dbg_lines.append(f"{node_path}: node read failed")
                except Exception:
                    dbg_lines.append("Tree access failed")

                # Write debug file
                debug_file_path = project_aspen_dir / f"monte_debug_run_{i}.log"
                debug_file_path.write_text("\n".join(dbg_lines), encoding="utf-8")
                print(f"    ⚠️  Debug log written: {debug_file_path}")
            except Exception as _e:
                print(f"    ⚠️  Failed to write debug log: {_e}")

        results.append({"run": i, "ratio": ratio, "co2": co2_flow, "h2": h2_flow, "naphtha": nap, "kero": ker, "status": "ok", "time": timestamp, "debug_file": str(debug_file_path) if debug_file_path is not None else ""})

    # write results CSV (place in parent Aspen folder)
    out_path = project_aspen_dir / cfg.results_csv
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["run", "ratio", "co2", "h2", "naphtha", "kero", "status", "time", "debug_file"])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    return results


if __name__ == "__main__":
    # Default smoke test: keep H2 fixed at the user's baseline and vary CO2 around 38
    cfg = MonteConfig(
        samples=3,
        ratio_mean=1.0,
        ratio_std=0.1,
        feed_mode="fix_h2",
        co2_base_override=38.0,
        h2_base_override=114.820896,
    )
    out = run_monte_carlo(cfg)
    for row in out:
        print(row)
