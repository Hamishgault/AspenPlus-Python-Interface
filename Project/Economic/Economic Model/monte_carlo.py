#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run a Monte Carlo sweep of the TEA model without changing Economics_eSAF.py.
"""

from pathlib import Path
import json
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import numpy as np
import pandas as pd
from scipy.optimize import brentq

import Economics_eSAF as model

OUTPUT_DIR = Path(__file__).with_name("outputs") / "economics_esaf" / "monte_carlo"

EE_MULT_RANGE = (0.9, 1.1)
BRENT_MULT_RANGE = (0.9, 1.1)
ETS1_MULT_RANGE = (0.9, 1.1)
ETS2_MULT_RANGE = (0.9, 1.1)
CAPEX_MULT_RANGE = (0.9, 1.1)
ELECTROLYZER_EFF_MULT_RANGE = (0.9, 1.1)
STACK_LIFE_MULT_RANGE = (0.9, 1.1)
CO2_CAPTURE_COST_MULT_RANGE = (0.9, 1.1)
OPEX_MULT_RANGE = (0.9, 1.1)
WACC_MULT_RANGE = (0.9, 1.1)
UTILIZATION_MULT_RANGE = (0.9, 1.1)
H2_COMPR_MULT_RANGE = (0.9, 1.1)


def clone_data(base: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    return {key: np.array(value, copy=True) for key, value in base.items()}


def sample_trunc_normal(
    rng: np.random.Generator,
    mean: float = 1.0,
    sigma: float = 0.1,
    low: float = 0.8,
    high: float = 1.2,
) -> float:
    while True:
        value = float(rng.normal(mean, sigma))
        if low <= value <= high:
            return value


def set_scalar(data: Dict[str, np.ndarray], section: str, key: str, value: float) -> None:
    idx_map = {
        "econ": model.ECON_IDX,
        "real": model.REAL_IDX,
        "plant": model.PLANT_IDX,
    }
    data[section][idx_map[section][key]] = value


def set_we_value(data: Dict[str, np.ndarray], index: int, value: float) -> None:
    data["we"][index] = value


def set_we_matrix_value(data: Dict[str, np.ndarray], row: int, col: int, value: float) -> None:
    data["we_matrix"][row, col] = value


def solve_bep(
    data: Dict[str, np.ndarray],
    wacc: float,
    model_val: Callable[..., Tuple[Any, ...]],
    lower: float = 0.0,
    upper: float = 10000.0,
    max_expansions: int = 3,
) -> Optional[float]:
    def npv_at(price: float) -> float:
        result = cast(Tuple[Any, ...], model_val(data, wacc, price))
        return float(result[1])

    low = float(lower)
    high = float(upper)
    try:
        f_low = npv_at(low)
        f_high = npv_at(high)
    except Exception:
        return None

    expansions = 0
    while np.sign(f_low) == np.sign(f_high) and expansions < max_expansions:
        high *= 2.0
        try:
            f_high = npv_at(high)
        except Exception:
            return None
        expansions += 1

    if np.sign(f_low) == np.sign(f_high):
        return None

    try:
        root_value, _ = brentq(lambda price: npv_at(float(price)), low, high, full_output=True)
    except ValueError:
        return None

    return float(root_value)


def run_monte_carlo(
    n_samples: int = 200,
    seed: int = 7,
    compute_bep: bool = False,
    output_subdir: Optional[str] = None,
) -> None:
    output_dir = OUTPUT_DIR if output_subdir is None else OUTPUT_DIR / output_subdir
    output_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)

    base_data = cast(Dict[str, np.ndarray], getattr(model, "data"))
    model_val = cast(Callable[..., Tuple[Any, ...]], getattr(model, "val"))
    base_capex = model.get_scalar(base_data, "plant", "CAPEX")
    base_refuel = model.get_scalar(base_data, "real", "ReFuel")
    base_wacc = model.get_scalar(base_data, "econ", "WACC")
    base_ee = model.get_scalar(base_data, "real", "EE")
    base_brent = model.get_scalar(base_data, "real", "BRENT")
    base_ets1 = model.get_scalar(base_data, "real", "ETS1")
    base_ets2 = model.get_scalar(base_data, "real", "ETS2")
    base_cc = model.get_scalar(base_data, "real", "CC")
    base_h2_compr = model.get_scalar(base_data, "plant", "H2_compr")
    base_operatori = model.get_scalar(base_data, "plant", "Operatori")
    base_overhead = model.get_scalar(base_data, "plant", "Overhead")
    base_manutenzione = model.get_scalar(base_data, "plant", "Manutenzione")
    base_use = float(base_data["we"][2].item())
    base_specific_energy = float(base_data["we_matrix"][1, 1].item())
    base_stack_life = float(base_data["we_matrix"][2, 1].item())

    rows: List[Dict[str, float]] = []
    progress_step = max(1, n_samples // 10)
    next_progress = progress_step

    for idx in range(n_samples):
        data_i = clone_data(base_data)

        set_scalar(
            data_i,
            "real",
            "EE",
            float(base_ee * sample_trunc_normal(rng, 1.0, 0.1, *EE_MULT_RANGE)),
        )
        set_scalar(
            data_i,
            "real",
            "BRENT",
            float(base_brent * sample_trunc_normal(rng, 1.0, 0.1, *BRENT_MULT_RANGE)),
        )
        set_scalar(
            data_i,
            "real",
            "ETS1",
            float(base_ets1 * sample_trunc_normal(rng, 1.0, 0.1, *ETS1_MULT_RANGE)),
        )
        set_scalar(
            data_i,
            "real",
            "ETS2",
            float(base_ets2 * sample_trunc_normal(rng, 1.0, 0.1, *ETS2_MULT_RANGE)),
        )
        set_scalar(
            data_i,
            "plant",
            "CAPEX",
            float(base_capex * sample_trunc_normal(rng, 1.0, 0.1, *CAPEX_MULT_RANGE)),
        )

        set_scalar(
            data_i,
            "real",
            "CC",
            float(base_cc * sample_trunc_normal(rng, 1.0, 0.1, *CO2_CAPTURE_COST_MULT_RANGE)),
        )
        set_scalar(
            data_i,
            "plant",
            "H2_compr",
            float(base_h2_compr * sample_trunc_normal(rng, 1.0, 0.1, *H2_COMPR_MULT_RANGE)),
        )

        opex_mult = float(sample_trunc_normal(rng, 1.0, 0.1, *OPEX_MULT_RANGE))
        set_scalar(data_i, "plant", "Operatori", base_operatori * opex_mult)
        set_scalar(data_i, "plant", "Overhead", base_overhead * opex_mult)
        set_scalar(data_i, "plant", "Manutenzione", base_manutenzione * opex_mult)

        wacc_i = float(base_wacc * sample_trunc_normal(rng, 1.0, 0.1, *WACC_MULT_RANGE))
        set_scalar(data_i, "econ", "WACC", wacc_i)

        use_i = float(base_use * sample_trunc_normal(rng, 1.0, 0.1, *UTILIZATION_MULT_RANGE))
        use_i = min(max(use_i, 0.0), 1.0)
        set_we_value(data_i, 2, use_i)

        set_we_matrix_value(
            data_i,
            1,
            1,
            float(base_specific_energy * sample_trunc_normal(rng, 1.0, 0.1, *ELECTROLYZER_EFF_MULT_RANGE)),
        )
        set_we_matrix_value(
            data_i,
            2,
            1,
            float(base_stack_life * sample_trunc_normal(rng, 1.0, 0.1, *STACK_LIFE_MULT_RANGE)),
        )

        if compute_bep:
            refuel = solve_bep(data_i, wacc_i, model_val)
            van = np.nan
            irr = None
            lcoh = np.array([np.nan])
            err = np.nan
        else:
            refuel = float(base_refuel)
            result = cast(Tuple[Any, ...], model_val(data_i, ReFuel=refuel))
            err = float(result[0])
            van = float(result[1])
            lcoh = np.asarray(result[5], dtype=float)
            cash_flows = np.asarray(result[7], dtype=float)
            model_irr = cast(Callable[[np.ndarray], Optional[float]], getattr(model, "compute_irr"))
            irr = model_irr(cash_flows)

        refuel_value = float(refuel) if refuel is not None else float("nan")

        rows.append({
            "EE": model.get_scalar(data_i, "real", "EE"),
            "BRENT": model.get_scalar(data_i, "real", "BRENT"),
            "ETS1": model.get_scalar(data_i, "real", "ETS1"),
            "ETS2": model.get_scalar(data_i, "real", "ETS2"),
            "CAPEX": model.get_scalar(data_i, "plant", "CAPEX"),
            "ReFuel": np.nan if compute_bep else refuel_value,
            "Electrolyzer_eff": float(39.0 / (float(data_i["we_matrix"][1, 1]) + float(data_i["we_matrix"][2, 1]) / 2000.0 * float(data_i["we_matrix"][3, 1]) * float(data_i["we_matrix"][1, 1]))),
            "Stack_life": float(data_i["we_matrix"][2, 1]),
            "CO2_capture_cost": model.get_scalar(data_i, "real", "CC"),
            "OPEX_mult": opex_mult,
            "WACC": model.get_scalar(data_i, "econ", "WACC"),
            "Utilization": float(data_i["we"][2].item()),
            "H2_compr_energy": model.get_scalar(data_i, "plant", "H2_compr"),
            "BEP": refuel_value if compute_bep else np.nan,
            "IRR": np.nan if irr is None else irr,
            "VAN": van,
            "err": err,
            "LCOH_total": float(lcoh[-1]),
        })

        if (idx + 1) == next_progress or (idx + 1) == n_samples:
            percent = int(round((idx + 1) / n_samples * 100))
            print(f"Progress: {percent}% ({idx + 1}/{n_samples})")
            next_progress += progress_step

    df = pd.DataFrame(rows)
    df.to_csv(output_dir / "monte_carlo_results.csv", index=False)

    def safe_percentile(series: pd.Series, q: int) -> Optional[float]:
        arr = np.asarray(series, dtype=float)
        if np.all(np.isnan(arr)):
            return None
        return float(np.nanpercentile(arr, q))

    summary = {
        "n_samples": n_samples,
        "seed": seed,
        "compute_bep": compute_bep,
        "ranges": {
            "EE_MULT": EE_MULT_RANGE,
            "BRENT_MULT": BRENT_MULT_RANGE,
            "ETS1_MULT": ETS1_MULT_RANGE,
            "ETS2_MULT": ETS2_MULT_RANGE,
            "CAPEX_MULT": CAPEX_MULT_RANGE,
            "ELECTROLYZER_EFF_MULT": ELECTROLYZER_EFF_MULT_RANGE,
            "STACK_LIFE_MULT": STACK_LIFE_MULT_RANGE,
            "CO2_CAPTURE_COST_MULT": CO2_CAPTURE_COST_MULT_RANGE,
            "OPEX_MULT": OPEX_MULT_RANGE,
            "WACC_MULT": WACC_MULT_RANGE,
            "UTILIZATION_MULT": UTILIZATION_MULT_RANGE,
            "H2_COMPR_MULT": H2_COMPR_MULT_RANGE,
        },
        "IRR": None if compute_bep else {
            "p10": safe_percentile(df["IRR"], 10),
            "p50": safe_percentile(df["IRR"], 50),
            "p90": safe_percentile(df["IRR"], 90),
        },
        "VAN": None if compute_bep else {
            "p10": safe_percentile(df["VAN"], 10),
            "p50": safe_percentile(df["VAN"], 50),
            "p90": safe_percentile(df["VAN"], 90),
        },
        "BEP": {
            "p10": safe_percentile(df["BEP"], 10),
            "p50": safe_percentile(df["BEP"], 50),
            "p90": safe_percentile(df["BEP"], 90),
        },
        "sensitivity": {} if compute_bep else None,
        "plots": {} if compute_bep else None,
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))


def _prompt_samples(default_samples: int, label: str) -> int:
    raw = input(f"{label} [{default_samples}]: ").strip()
    if raw == "":
        return default_samples
    try:
        value = int(raw)
    except ValueError:
        raise ValueError("Number of samples must be an integer.")
    if value <= 0:
        raise ValueError("Number of samples must be positive.")
    return value


if __name__ == "__main__":
    default_samples = 20000
    default_bep_samples = 2000
    n_samples = _prompt_samples(default_samples, "Number of samples (normal)")
    bep_samples = _prompt_samples(default_bep_samples, "Number of samples (BEP)")
    print("Press Enter to start...")
    input()
    run_monte_carlo(n_samples=n_samples, seed=6, compute_bep=False, output_subdir="normal")
    run_monte_carlo(n_samples=bep_samples, seed=6, compute_bep=True, output_subdir="bep")
