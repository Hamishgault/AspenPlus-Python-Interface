#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run Economics_eSAF with fixed ReFuel reference prices from policy tables.
This keeps Economics_eSAF.py unchanged and writes outputs to separate folders.
"""

from pathlib import Path
from typing import Dict

import numpy as np

import Economics_eSAF as base_model
from results_viewer import display_results


# 2025 reference prices (EUR/tonne) from your table.
REFUEL_REFERENCE_PRICES: Dict[str, float] = {
    "CAF": 640.0,
    "SAF": 1925.0,
    "Synthetic_aviation_fuels": 7520.0,
    "Aviation_fuels": 666.0,
}

DEFAULT_CATEGORY = "Synthetic_aviation_fuels"
OUTPUT_ROOT = Path(__file__).with_name("outputs") / "economics_esaf_reference_price"


def clone_data(data):
    return {
        key: np.array(value, copy=True) if isinstance(value, np.ndarray) else value
        for key, value in data.items()
    }


def run_reference_price_case(category: str = DEFAULT_CATEGORY, show_plot: bool = False):
    if category not in REFUEL_REFERENCE_PRICES:
        valid = ", ".join(REFUEL_REFERENCE_PRICES.keys())
        raise ValueError(f"Unknown category '{category}'. Valid options: {valid}")

    refuel_price = REFUEL_REFERENCE_PRICES[category]
    data_i = clone_data(base_model.data)

    wacc = float(base_model.get_scalar(data_i, "econ", "WACC"))
    err, van, table, cop, kero_k, lcoh, sell_price_k, cash_flows, *_ = base_model.val(
        data_i,
        DF=wacc,
        ReFuel=refuel_price,
    )
    irr = base_model.compute_irr(cash_flows)

    input_summary = base_model.build_input_summary(data_i)
    input_summary.setdefault("real", {})["ReFuel_reference_price_EUR_per_t"] = float(refuel_price)
    input_summary["scenario"] = {
        "type": "reference_price",
        "category": category,
    }

    output_dir = OUTPUT_ROOT / category.lower().replace(" ", "_")
    base_model.save_results(
        output_dir,
        irr,
        np.nan,
        float(err),
        float(van),
        table,
        cop,
        kero_k,
        lcoh,
        sell_price_k,
        input_summary,
    )

    print(f"\nReference-price scenario completed: {category}")
    print(f"ReFuel price used: {refuel_price:,.2f} EUR/t")
    print(f"NPV (VAN): {float(van):,.2f} EUR")
    print(f"IRR: {'undefined' if irr is None else f'{irr:.6f}'}")
    print(f"Saved in: {output_dir}")

    display_results(output_dir, show_plot=show_plot)


def run_all_reference_cases(show_plot: bool = False):
    for category in REFUEL_REFERENCE_PRICES:
        run_reference_price_case(category=category, show_plot=show_plot)


if __name__ == "__main__":
    # Change DEFAULT_CATEGORY above if you prefer another default run.
    run_reference_price_case(category=DEFAULT_CATEGORY, show_plot=False)
