#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Load and display saved Economics_eSAF outputs without re-running the model.
"""

from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _percentiles(values):
    arr = np.asarray(values, dtype=float)
    if arr.size == 0 or np.all(np.isnan(arr)):
        return {"p10": None, "p50": None, "p90": None}
    return {
        "p10": float(np.nanpercentile(arr, 10)),
        "p50": float(np.nanpercentile(arr, 50)),
        "p90": float(np.nanpercentile(arr, 90)),
    }


def _load_monte_carlo(output_dir):
    mc_dir = Path(output_dir) / "monte_carlo"
    summary_path = mc_dir / "summary.json"
    results_path = mc_dir / "monte_carlo_results.csv"
    if not summary_path.exists() or not results_path.exists():
        return None, None
    summary = json.loads(summary_path.read_text())
    df = pd.read_csv(results_path)
    return summary, df


def _print_monte_carlo_summary(summary, df):
    print("\nMonte Carlo Summary")
    print("Samples:", summary.get("n_samples"))
    print("Seed:", summary.get("seed"))
    print("Compute BEP:", summary.get("compute_bep"))

    ranges = summary.get("ranges", {})
    if ranges:
        print("Ranges:")
        for key, value in ranges.items():
            print(f"- {key}: {value}")

    metrics = {}
    for key in ("IRR", "VAN", "BEP"):
        if key in summary:
            metrics[key] = summary.get(key, {})
        elif key in df.columns:
            metrics[key] = _percentiles(df[key])

    for key, stats in metrics.items():
        print(f"{key} p10/p50/p90:", stats.get("p10"), stats.get("p50"), stats.get("p90"))

    if metrics:
        rows = []
        for key, stats in metrics.items():
            rows.append({
                "Metric": key,
                "p10": stats.get("p10"),
                "p50": stats.get("p50"),
                "p90": stats.get("p90"),
            })
        table = pd.DataFrame(rows)
        print("\nMonte Carlo Percentiles")
        print(table.to_string(index=False))


def _print_monte_carlo_sensitivity(df):
    metric = "VAN" if "VAN" in df.columns else None
    if metric is None or df[metric].notna().sum() < 3:
        return

    input_cols = ["EE", "BRENT", "ETS1", "ETS2", "CAPEX_MULT", "CAPEX"]
    pairs = []
    for col in input_cols:
        if col in df.columns and df[col].notna().sum() >= 3:
            corr = df[col].corr(df[metric])
            if pd.notna(corr):
                pairs.append((col, float(corr)))

    if not pairs:
        return

    pairs.sort(key=lambda item: abs(item[1]), reverse=True)
    print("\nMonte Carlo Sensitivity (correlation with VAN)")
    for col, corr in pairs:
        print(f"- {col}: {corr:.3f}")


def display_results(output_dir, show_plot=True):
    output_dir = Path(output_dir)
    summary_path = output_dir / "summary.json"
    arrays_path = output_dir / "arrays.npz"
    results_table_path = output_dir / "results_table.csv"
    plot_path = output_dir / "market_price.png"

    if not summary_path.exists():
        raise FileNotFoundError(f"Missing summary.json in {output_dir}")

    summary = json.loads(summary_path.read_text())
    arrays = np.load(arrays_path)
    table = pd.read_csv(results_table_path)

    metrics = summary.get("metrics", {})
    inputs = summary.get("inputs", {})

    print("\nEconomics eSAF - Saved Results")
    print("Timestamp:", summary.get("timestamp", ""))
    print("IRR:", metrics.get("IRR"))
    print("BEP:", metrics.get("BEP"))
    print("VAN:", metrics.get("VAN"))
    print("err:", metrics.get("err"))

    print("\nImportant inputs")
    for section, values in inputs.items():
        print(f"- {section}")
        for key, value in values.items():
            print(f"  {key}: {value}")

    print("\nArrays available:", ", ".join(arrays.files))
    print("Results table shape:", table.shape)

    if show_plot and plot_path.exists():
        img = plt.imread(plot_path)
        plt.imshow(img)
        plt.axis("off")
        plt.title("Market Price")
        plt.show()

    mc_summary, mc_df = _load_monte_carlo(output_dir)
    if mc_summary is not None and mc_df is not None:
        _print_monte_carlo_summary(mc_summary, mc_df)
        _print_monte_carlo_sensitivity(mc_df)

        if show_plot:
            fig, axes = plt.subplots(1, 3, figsize=(12, 3.5))
            axes[0].hist(mc_df["VAN"].dropna(), bins=25, color="#55a868")
            axes[0].set_title("VAN")

            if "IRR" in mc_df.columns and mc_df["IRR"].notna().any():
                axes[1].hist(mc_df["IRR"].dropna(), bins=25, color="#4c72b0")
                axes[1].set_title("IRR")
            else:
                axes[1].axis("off")

            if "BEP" in mc_df.columns and mc_df["BEP"].notna().any():
                axes[2].hist(mc_df["BEP"].dropna(), bins=25, color="#c44e52")
                axes[2].set_title("BEP")
            else:
                axes[2].axis("off")

            plt.tight_layout()
            plt.show()


if __name__ == "__main__":
    default_dir = Path(__file__).with_name("outputs") / "economics_esaf"
    display_results(default_dir, show_plot=True)
