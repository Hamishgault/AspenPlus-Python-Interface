
"""
Load and display saved Economics_eSAF outputs without re-running the model.
"""

from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _load_monte_carlo(output_dir):
    mc_dir = Path(output_dir) / "monte_carlo"
    summary_path = mc_dir / "summary.json"
    results_path = mc_dir / "monte_carlo_results.csv"
    if not summary_path.exists() or not results_path.exists():
        return None, None
    summary = json.loads(summary_path.read_text())
    df = pd.read_csv(results_path)
    return summary, df


def _monte_carlo_correlations(df, metric="VAN"):
    if metric not in df.columns:
        return []

    metric_std = float(df[metric].std(skipna=True))
    if metric_std == 0 or np.isnan(metric_std):
        return []

    input_cols = [
        "EE",
        "BRENT",
        "ETS1",
        "ETS2",
        "CAPEX",
        "ReFuel",
        "Electrolyzer_eff",
        "Stack_life",
        "CO2_capture_cost",
        "OPEX_mult",
        "WACC",
        "Plant_life",
        "Utilization",
        "H2_compr_energy",
    ]

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


def _plot_tornado(corr_pairs, metric="VAN"):
    if not corr_pairs:
        return

    labels = [item[0] for item in corr_pairs]
    values = np.array([item[1] for item in corr_pairs], dtype=float)

    colors = np.where(values >= 0, "#4c72b0", "#c44e52")
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(labels) + 2))
    ax.barh(labels, values, color=colors)
    ax.set_xlabel("Correlation")
    ax.set_title(f"Tornado Plot: {metric} Sensitivity")
    ax.axvline(0, color="#333333", linewidth=0.8)
    plt.tight_layout()
    plt.show()


def _plot_top_scatter(df, corr_pairs, metric="VAN", top_n=3):
    if not corr_pairs:
        return

    top_pairs = corr_pairs[:top_n]
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


def _regression_sensitivity(df, metric="VAN"):
    if metric not in df.columns:
        return []

    input_cols = [
        "EE",
        "BRENT",
        "ETS1",
        "ETS2",
        "CAPEX",
        "ReFuel",
        "Electrolyzer_eff",
        "Stack_life",
        "CO2_capture_cost",
        "OPEX_mult",
        "WACC",
        "Plant_life",
        "Utilization",
        "H2_compr_energy",
    ]

    cols = [col for col in input_cols if col in df.columns]
    if not cols:
        return []

    data = df[cols + [metric]].dropna()
    if len(data) < 3:
        return []

    x = data[cols].to_numpy(dtype=float)
    y = data[metric].to_numpy(dtype=float)

    x_mean = x.mean(axis=0)
    x_std = x.std(axis=0, ddof=0)
    y_mean = y.mean()
    y_std = y.std(ddof=0)

    valid_mask = x_std > 0
    if not np.any(valid_mask) or y_std == 0:
        return []

    x = x[:, valid_mask]
    cols = [col for col, keep in zip(cols, valid_mask) if keep]

    x_stdized = (x - x_mean[valid_mask]) / x_std[valid_mask]
    y_stdized = (y - y_mean) / y_std

    x_design = np.column_stack([np.ones(x_stdized.shape[0]), x_stdized])
    coef, _, _, _ = np.linalg.lstsq(x_design, y_stdized, rcond=None)
    betas = coef[1:]

    pairs = list(zip(cols, betas))
    pairs.sort(key=lambda item: abs(item[1]), reverse=True)
    return pairs


def _plot_regression_tornado(beta_pairs, metric="VAN"):
    if not beta_pairs:
        return

    labels = [item[0] for item in beta_pairs]
    values = np.array([item[1] for item in beta_pairs], dtype=float)

    colors = np.where(values >= 0, "#4c72b0", "#c44e52")
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(labels) + 2))
    ax.barh(labels, values, color=colors)
    ax.set_xlabel("Standardized beta")
    ax.set_title(f"Regression-Based Sensitivity: {metric}")
    ax.axvline(0, color="#333333", linewidth=0.8)
    plt.tight_layout()
    plt.show()


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
        corr_pairs = _monte_carlo_correlations(mc_df, metric="VAN")
        if show_plot:
            _plot_tornado(corr_pairs, metric="VAN")
            _plot_top_scatter(mc_df, corr_pairs, metric="VAN", top_n=3)

        beta_pairs = _regression_sensitivity(mc_df, metric="VAN")
        if beta_pairs:
            rows = [
                {
                    "Variable": name,
                    "beta": float(beta),
                    "abs_beta": float(abs(beta)),
                }
                for name, beta in beta_pairs
            ]
            beta_table = pd.DataFrame(rows)
            print("\nRegression-Based Sensitivity (VAN)")
            print(beta_table.to_string(index=False))

        if show_plot:
            _plot_regression_tornado(beta_pairs, metric="VAN")


if __name__ == "__main__":
    default_dir = Path(__file__).with_name("outputs") / "economics_esaf"
    display_results(default_dir, show_plot=True)
