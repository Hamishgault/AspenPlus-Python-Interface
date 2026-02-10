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
from scipy.optimize import minimize

import Economics_eSAF as model

OUTPUT_DIR = Path(__file__).with_name("outputs") / "economics_esaf" / "monte_carlo"

EE_RANGE = (0.05, 0.15)
BRENT_RANGE = (60.0, 100.0)
ETS1_RANGE = (50.0, 150.0)
ETS2_RANGE = (25.0, 100.0)
CAPEX_MULT_RANGE = (0.8, 1.2)


def clone_data(base: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    return {key: np.array(value, copy=True) for key, value in base.items()}


def set_scalar(data: Dict[str, np.ndarray], section: str, key: str, value: float) -> None:
    idx_map = {
        "econ": model.ECON_IDX,
        "real": model.REAL_IDX,
        "plant": model.PLANT_IDX,
    }
    data[section][idx_map[section][key]] = value


def run_monte_carlo(n_samples: int = 200, seed: int = 7, compute_bep: bool = False) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)

    base_data = cast(Dict[str, np.ndarray], getattr(model, "data"))
    model_val = cast(Callable[..., Tuple[Any, ...]], getattr(model, "val"))
    model_irr = cast(Callable[[np.ndarray], Optional[float]], getattr(model, "compute_irr"))
    base_capex = model.get_scalar(base_data, "plant", "CAPEX")
    base_refuel = model.get_scalar(base_data, "real", "ReFuel")
    base_wacc = model.get_scalar(base_data, "econ", "WACC")

    rows: List[Dict[str, float]] = []

    for _ in range(n_samples):
        data_i = clone_data(base_data)

        set_scalar(data_i, "real", "EE", float(rng.uniform(*EE_RANGE)))
        set_scalar(data_i, "real", "BRENT", float(rng.uniform(*BRENT_RANGE)))
        set_scalar(data_i, "real", "ETS1", float(rng.uniform(*ETS1_RANGE)))
        set_scalar(data_i, "real", "ETS2", float(rng.uniform(*ETS2_RANGE)))
        set_scalar(data_i, "plant", "CAPEX", float(base_capex * rng.uniform(*CAPEX_MULT_RANGE)))

        if compute_bep:
            def objective(refuel_arr: np.ndarray) -> float:
                return float(model_val(data_i, base_wacc, refuel_arr[0])[0])

            result = minimize(
                objective,
                x0=[base_refuel],
                method="L-BFGS-B",
                bounds=[(0, 10000)],
            )
            refuel = float(result.x[0])
        else:
            refuel = float(base_refuel)

        result = cast(Tuple[Any, ...], model_val(data_i, ReFuel=refuel))
        err = float(result[0])
        van = float(result[1])
        lcoh = np.asarray(result[5], dtype=float)
        cash_flows = np.asarray(result[7], dtype=float)
        irr = model_irr(cash_flows)

        rows.append({
            "EE": model.get_scalar(data_i, "real", "EE"),
            "BRENT": model.get_scalar(data_i, "real", "BRENT"),
            "ETS1": model.get_scalar(data_i, "real", "ETS1"),
            "ETS2": model.get_scalar(data_i, "real", "ETS2"),
            "CAPEX": model.get_scalar(data_i, "plant", "CAPEX"),
            "ReFuel": refuel,
            "BEP": refuel if compute_bep else np.nan,
            "IRR": np.nan if irr is None else irr,
            "VAN": van,
            "err": err,
            "LCOH_total": float(lcoh[-1]),
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "monte_carlo_results.csv", index=False)

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
            "EE": EE_RANGE,
            "BRENT": BRENT_RANGE,
            "ETS1": ETS1_RANGE,
            "ETS2": ETS2_RANGE,
            "CAPEX_MULT": CAPEX_MULT_RANGE,
        },
        "IRR": {
            "p10": safe_percentile(df["IRR"], 10),
            "p50": safe_percentile(df["IRR"], 50),
            "p90": safe_percentile(df["IRR"], 90),
        },
        "VAN": {
            "p10": safe_percentile(df["VAN"], 10),
            "p50": safe_percentile(df["VAN"], 50),
            "p90": safe_percentile(df["VAN"], 90),
        },
        "BEP": {
            "p10": safe_percentile(df["BEP"], 10),
            "p50": safe_percentile(df["BEP"], 50),
            "p90": safe_percentile(df["BEP"], 90),
        },
    }

    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run_monte_carlo()
