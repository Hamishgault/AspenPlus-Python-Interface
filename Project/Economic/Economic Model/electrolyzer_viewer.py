"""
Load Monte Carlo outputs and visualize electrolyzer LCOH sensitivity.
"""

from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _load_monte_carlo(output_dir, subdir=None):
    mc_dir = Path(output_dir) / "monte_carlo"
    if subdir:
        mc_dir = mc_dir / subdir
    summary_path = mc_dir / "summary.json"
    results_path = mc_dir / "monte_carlo_results.csv"
    if not summary_path.exists() or not results_path.exists():
        return None, None
    summary = json.loads(summary_path.read_text())
    df = pd.read_csv(results_path)
    return summary, df


def _percentiles(values):
    arr = np.asarray(values, dtype=float)
    if arr.size == 0 or np.all(np.isnan(arr)):
        return {"p10": None, "p50": None, "p90": None}
    return {
        "p10": float(np.nanpercentile(arr, 10)),
        "p50": float(np.nanpercentile(arr, 50)),
        "p90": float(np.nanpercentile(arr, 90)),
    }


def _correlations(df, metric, input_cols):
    if metric not in df.columns:
        return []

    metric_std = float(df[metric].std(skipna=True))
    if metric_std == 0 or np.isnan(metric_std):
        return []

    pairs = []
    for col in input_cols:
        if col in df.columns and df[col].notna().sum() >= 3 and df[metric].notna().sum() >= 3:
            col_std = float(df[col].std(skipna=True))
            if col_std == 0 or np.isnan(col_std):
                continue
            corr = df[col].corr(df[metric])
            if pd.notna(corr):
                pairs.append((col, float(corr)))

    pairs.sort(key=lambda item: abs(item[1]), reverse=True)
    return pairs


def _plot_tornado(pairs, metric):
    if not pairs:
        return

    labels = [item[0] for item in pairs]
    values = np.array([item[1] for item in pairs], dtype=float)

    colors = np.where(values >= 0, "#4c72b0", "#c44e52")
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(labels) + 2))
    ax.barh(labels, values, color=colors)
    ax.set_xlabel("Correlation")
    ax.set_title(f"Electrolyzer Sensitivity: {metric}")
    ax.axvline(0, color="#333333", linewidth=0.8)
    plt.tight_layout()
    plt.show()


def _plot_top_scatter(df, pairs, metric, top_n=3):
    if not pairs:
        return

    top_pairs = pairs[:top_n]
    fig, axes = plt.subplots(1, len(top_pairs), figsize=(5 * len(top_pairs), 3.5))
    if len(top_pairs) == 1:
        axes = [axes]

    for ax, (col, _) in zip(axes, top_pairs):
        ax.scatter(df[col], df[metric], alpha=0.6, s=12, color="#4c72b0")
        ax.set_xlabel(col)
        ax.set_ylabel(metric)
        ax.set_title(f"{metric} vs {col}")

    plt.tight_layout()
    plt.show()


def display_electrolyzer_results(output_dir, show_plot=True):
    mc_root = Path(output_dir) / "monte_carlo"
    subdir = "normal" if (mc_root / "normal").exists() else None
    summary, df = _load_monte_carlo(output_dir, subdir=subdir)
    if summary is None or df is None:
        raise FileNotFoundError("Missing Monte Carlo outputs in outputs/economics_esaf/monte_carlo")

    metric = "LCOH_total"
    input_cols = [
        "Electrolyzer_eff",
        "Stack_life",
        "Utilization",
        "H2_compr_energy",
        "EE",
    ]

    print("\nElectrolyzer LCOH Summary")
    stats = _percentiles(df[metric])
    print("LCOH_total p10/p50/p90:", stats.get("p10"), stats.get("p50"), stats.get("p90"))

    pairs = _correlations(df, metric, input_cols)
    if pairs:
        rows = [{"Variable": name, "corr": float(corr), "abs_corr": float(abs(corr))} for name, corr in pairs]
        table = pd.DataFrame(rows)
        print("\nElectrolyzer Sensitivity (Correlation)")
        print(table.to_string(index=False))

    if show_plot:
        _plot_tornado(pairs, metric)
        _plot_top_scatter(df, pairs, metric, top_n=3)


if __name__ == "__main__":
    default_dir = Path(__file__).with_name("outputs") / "economics_esaf"
    display_electrolyzer_results(default_dir, show_plot=True)
