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

import csv
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple, cast

from CodeLibrary import Simulation
from hydrocracking_v2 import update_hydrocracking_streams_v2


@dataclass
class MonteConfig:
    bkp_name: str = "FTS Alessio_CO_conv_Ref_20bar_11%.bkp"
    samples: int = 3
    ratio_mean: float = 1.0  # CO2/H2
    ratio_std: float = 0.1
    co2_node: str = "Application.Tree.Data.Streams.1-CO2-MU"
    h2_node: str = "Application.Tree.Data.Streams.1-H2-MU"
    inlet_stream: str = "5-IN-EXC"
    outlet_stream: str = "5-OUTEXC"
    naphtha_node: str = "Application.Tree.Data.Streams.9-NAPHTA"
    kero_node: str = "Application.Tree.Data.Streams.9-KERO"
    results_csv: str = "monte_results.csv"
    visibility: bool = False
    # Optional overrides for baseline flows (use these instead of reading from Aspen)
    co2_base: float | None = None
    h2_base: float | None = None


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
    nap = _get_comp_flow(sim, nap_node, "NAPHTA")
    ker = _get_comp_flow(sim, ker_node, "KERO")
    return (0.0 if nap is None else nap), (0.0 if ker is None else ker)


# --- main driver -----------------------------------------------------------

def run_monte_carlo(cfg: MonteConfig) -> list[Dict[str, object]]:
    results: list[Dict[str, object]] = []

    workdir = Path(__file__).resolve().parent
    bkp_path = workdir / cfg.bkp_name
    if not bkp_path.exists():
        raise FileNotFoundError(f"Aspen .bkp not found: {bkp_path}")

    sim = Simulation(AspenFileName=str(bkp_path), WorkingDirectoryPath=str(workdir), VISIBILITY=cfg.visibility)

    # determine baseline CO2/H2 (allow overrides in config)
    if cfg.co2_base is not None and cfg.h2_base is not None:
        co2_base = float(cfg.co2_base)
        h2_base = float(cfg.h2_base)
    else:
        # initial run to read baseline CO2/H2 from Aspen
        sim.EngineRun()
        co2_base = _get_comp_flow(sim, cfg.co2_node, "CO2")
        h2_base = _get_comp_flow(sim, cfg.h2_node, "H2")
        if co2_base is None or h2_base is None:
            raise RuntimeError("Failed to read baseline CO2/H2 from model streams")

    baseline_total = float(co2_base) + float(h2_base)

    for i in range(cfg.samples):
        # sample ratio (positive)
        ratio = -1.0
        attempts = 0
        while ratio <= 0 and attempts < 10:
            ratio = random.normalvariate(cfg.ratio_mean, cfg.ratio_std)
            attempts += 1
        if ratio <= 0:
            ratio = max(1e-6, cfg.ratio_mean)

        # compute component flows preserving baseline total: CO2/H2 = ratio
        h2_flow = baseline_total / (1.0 + ratio)
        co2_flow = baseline_total - h2_flow

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        # 1) set feed component flows
        ok_co2 = _set_comp_flow(sim, cfg.co2_node.split('.')[-1], "CO2", co2_flow)
        ok_h2 = _set_comp_flow(sim, cfg.h2_node.split('.')[-1], "H2", h2_flow)
        if not ok_co2 or not ok_h2:
            results.append({"run": i, "ratio": ratio, "co2": co2_flow, "h2": h2_flow, "naphtha": None, "kero": None, "status": "set_feed_failed", "time": timestamp})
            continue

        # 2) first Aspen run
        sim.EngineRun()

        # 3) reconcile hydrocracker (Primary -> Secondary)
        try:
            update_hydrocracking_streams_v2(sim, inlet_stream=cfg.inlet_stream, outlet_stream=cfg.outlet_stream)
        except Exception as exc:
            results.append({"run": i, "ratio": ratio, "co2": co2_flow, "h2": h2_flow, "naphtha": None, "kero": None, "status": f"hydrocracker_failed: {exc}", "time": timestamp})
            continue

        # 4) run Aspen again
        sim.EngineRun()

        # 5) collect outputs
        nap, ker = _get_products(sim, cfg.naphtha_node, cfg.kero_node)

        results.append({"run": i, "ratio": ratio, "co2": co2_flow, "h2": h2_flow, "naphtha": nap, "kero": ker, "status": "ok", "time": timestamp})

    # write results CSV
    out_path = workdir / cfg.results_csv
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["run", "ratio", "co2", "h2", "naphtha", "kero", "status", "time"])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    return results


if __name__ == "__main__":
    # Use the baseline values you provided for a smoke test
    cfg = MonteConfig(samples=3, ratio_mean=1.0, ratio_std=0.1, co2_base=38.0, h2_base=114.8)
    out = run_monte_carlo(cfg)
    for row in out:
        print(row)
