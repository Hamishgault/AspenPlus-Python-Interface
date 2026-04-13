
"""
Load and display saved Economics_eSAF outputs without re-running the model.
"""

from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from matplotlib.ticker import FuncFormatter


INPUT_LABELS = {
    "EE": "Electricity Price",
    "BRENT": "Brent Crude Price",
    "ETS1": "ETS Scenario 1",
    "ETS2": "ETS Scenario 2",
    "CAPEX": "Capital Expenditure Multiplier",
    "ReFuel": "ReFuel Price",
    "Electrolyzer_eff": "Electrolyser Efficiency",
    "Stack_life": "Stack Lifetime",
    "CO2_capture_cost": "CO2 Capture Cost",
    "OPEX_mult": "Operating Expenditure Multiplier",
    "WACC": "Weighted Average Cost of Capital",
    "Plant_life": "Plant Lifetime",
    "Utilization": "Plant Utilization",
    "H2_compr_energy": "Hydrogen Compression Energy",
}

PLOT_STYLE = {
    "figure_facecolor": "#d9d9d9",
    "axes_facecolor": "#d9d9d9",
    "axes_edgecolor": "#000000",
    "axes_linewidth": 2.0,
    "tick_width": 2.0,
    "tick_length": 6.0,
}


def _display_metric(metric):
    return "NPV" if metric == "VAN" else metric


def _display_name(name: str) -> str:
    return str(INPUT_LABELS.get(name, name))


def _resolve_metric_column(df, metric):
    if metric in df.columns:
        return metric
    if metric == "NPV" and "VAN" in df.columns:
        return "VAN"
    if metric == "VAN" and "NPV" in df.columns:
        return "NPV"
    return None


def _style_axes(ax):
    ax.set_facecolor(PLOT_STYLE["axes_facecolor"])
    ax.figure.patch.set_facecolor(PLOT_STYLE["figure_facecolor"])
    for spine in ax.spines.values():
        spine.set_linewidth(PLOT_STYLE["axes_linewidth"])
        spine.set_color(PLOT_STYLE["axes_edgecolor"])
    ax.tick_params(
        width=PLOT_STYLE["tick_width"],
        length=PLOT_STYLE["tick_length"],
        direction="out",
        colors="#000000",
    )
    ax.xaxis.label.set_color("#000000")
    ax.yaxis.label.set_color("#000000")


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


def _monte_carlo_correlations(df, metric="NPV"):
    metric_col = _resolve_metric_column(df, metric)
    if metric_col is None:
        return []

    metric_std = float(df[metric_col].std(skipna=True))
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
        if col in df.columns and df[col].notna().sum() >= 3 and df[metric_col].notna().sum() >= 3:
            col_std = float(df[col].std(skipna=True))
            if col_std == 0 or np.isnan(col_std):
                continue
            corr = df[col].corr(df[metric_col])
            if pd.notna(corr):
                pairs.append((col, float(corr)))

    pairs.sort(key=lambda item: abs(item[1]), reverse=True)
    return pairs


def _plot_tornado(corr_pairs, metric="NPV"):
    if not corr_pairs:
        return

    labels = [_display_name(item[0]) for item in corr_pairs]
    values = np.array([item[1] for item in corr_pairs], dtype=float)

    colors = np.where(values >= 0, "#4c72b0", "#c44e52")
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(labels) + 2))
    ax.barh(labels, values, color=colors, edgecolor="#000000", linewidth=0.8)
    ax.set_xlabel("Correlation")
    ax.set_ylabel("Input Variable")
    ax.axvline(0, color="#000000", linewidth=2.0)
    _style_axes(ax)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    plt.tight_layout()
    plt.show()


def _plot_top_scatter(df, corr_pairs, metric="NPV", top_n=3):
    if not corr_pairs:
        return

    metric_col = _resolve_metric_column(df, metric)
    if metric_col is None:
        return

    top_pairs = corr_pairs[:top_n]
    fig, axes = plt.subplots(1, len(top_pairs), figsize=(5 * len(top_pairs), 3.5))
    if len(top_pairs) == 1:
        axes = [axes]

    for ax, (col, _) in zip(axes, top_pairs):
        ax.scatter(
            df[col],
            df[metric_col],
            alpha=0.75,
            s=18,
            color="#4c72b0",
            edgecolors="#000000",
            linewidths=0.4,
        )
        ax.set_xlabel(_display_name(col))
        ax.set_ylabel(_display_metric(metric))
        _style_axes(ax)

    plt.tight_layout()
    plt.show()


def _plot_histogram(df, metric="NPV", label=None, bins=60000):
    metric_col = _resolve_metric_column(df, metric)
    if metric_col is None or df[metric_col].notna().sum() == 0:
        return
    
    data = df[metric_col].dropna()
    p5 = float(data.quantile(0.05))
    p10 = float(data.quantile(0.10))
    p50 = float(data.quantile(0.50))
    p90 = float(data.quantile(0.90))
    p95 = float(data.quantile(0.95))
    
    fig, ax = plt.subplots(figsize=(7, 5), dpi=200)
    
    # Clean histogram styling
    ax.hist(data, bins=60, density=True, color="#7BAFDE", edgecolor="none", alpha=0.65)
    
    # Fit normal distribution and plot curve
    mu, sigma = data.mean(), data.std()
    x = np.linspace(data.min(), data.max(), 300)
    pdf = stats.norm.pdf(x, mu, sigma)
    ax.plot(x, pdf, color="#000000", linewidth=1.5, label="Normal Fit")
    
    # Simple vertical markers (no labels on plot)
    ax.axvline(mu, color="#d62728", linestyle="--", linewidth=1.5, label=f"Mean")
    ax.axvline(p50, color="#2ca02c", linestyle="--", linewidth=1.3, label=f"Median")
    # Only show break-even line for NPV, not for BEP
    if metric != "BEP":
        ax.axvline(0, color="#000000", linestyle=":", linewidth=1.5, label=f"Break-even")
    
    # Formatting
    xlabel = _display_metric(metric) if label is None else label
    if xlabel == "BEP":
        xlabel = "Break Even Price"
    ax.set_xlabel(f"{xlabel} (EUR)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Probability Density (×10⁻⁶)", fontsize=12, fontweight="bold")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{x*1e6:.1f}'))
    
    # Clean styling: white background, complete box frame
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")
    ax.spines["top"].set_visible(True)
    ax.spines["right"].set_visible(True)
    ax.spines["left"].set_linewidth(1.4)
    ax.spines["bottom"].set_linewidth(1.4)
    ax.spines["top"].set_linewidth(1.4)
    ax.spines["right"].set_linewidth(1.4)
    
    # Set x-axis limits for BEP to zoom into the data range
    if metric == "BEP":
        ax.set_xlim(4400, 5500)
    
    # Legend with frame, positioned in upper left area
    ax.legend(frameon=True, fontsize=11, loc="upper center", framealpha=0.95, edgecolor="black", 
              bbox_to_anchor=(0.75, 0.9))
    ax.grid(False)
    plt.tight_layout()
    plt.show()
    
    # Print percentile summary
    print(f"\n{_display_metric(metric)} Distribution Statistics:")
    print(f"  Mean (μ): {mu:,.2f} €")
    print(f"  Std Dev (σ): {sigma:,.2f} €")
    print(f"  5th percentile: {p5:,.2f} €")
    print(f"  P10: {p10:,.2f} €")
    print(f"  P50 (Median): {p50:,.2f} €")
    print(f"  P90: {p90:,.2f} €")
    print(f"  95th percentile: {p95:,.2f} €")


def _regression_sensitivity(df, metric="NPV"):
    metric_col = _resolve_metric_column(df, metric)
    if metric_col is None:
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

    data = df[cols + [metric_col]].dropna()
    if len(data) < 3:
        return []

    x = data[cols].to_numpy(dtype=float)
    y = data[metric_col].to_numpy(dtype=float)

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


def _plot_regression_tornado(beta_pairs, metric="NPV"):
    if not beta_pairs:
        return

    labels = [_display_name(item[0]) for item in beta_pairs]
    values = np.array([item[1] for item in beta_pairs], dtype=float)

    colors = np.where(values >= 0, "#4c72b0", "#c44e52")
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(labels) + 2))
    ax.barh(labels, values, color=colors, edgecolor="#000000", linewidth=0.8)
    ax.set_xlabel("Standardized beta")
    ax.set_ylabel("Input Variable")
    ax.axvline(0, color="#000000", linewidth=2.0)
    _style_axes(ax)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    plt.tight_layout()
    plt.show()


def _fit_bep_tree(df, input_cols, metric="BEP"):
    if metric not in df.columns:
        return None, None

    data = df[input_cols + [metric]].dropna()
    if len(data) < 10:
        return None, None

    x = data[input_cols].to_numpy(dtype=float)
    y = data[metric].to_numpy(dtype=float)

    try:
        from sklearn.tree import DecisionTreeRegressor
    except ImportError:
        print("\nDecision tree analysis skipped: scikit-learn not installed.")
        return None, None

    tree = DecisionTreeRegressor(max_depth=3, random_state=7)
    tree.fit(x, y)
    return tree, input_cols


def _print_tree_splits(tree, feature_names):
    tree_ = tree.tree_
    print("\nDecision Tree Split Thresholds")
    for idx in range(tree_.node_count):
        feature = tree_.feature[idx]
        if feature == -2:
            continue
        name = _display_name(feature_names[feature])
        threshold = tree_.threshold[idx]
        print(f"- {name} <= {threshold:.4f}")


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
    print("NPV:", metrics.get("NPV", metrics.get("VAN")))
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
        plt.show()

    mc_root = Path(output_dir) / "monte_carlo"
    subdirs = []
    if (mc_root / "normal").exists():
        subdirs.append("normal")
    if (mc_root / "bep").exists():
        subdirs.append("bep")
    if not subdirs:
        subdirs.append(None)

    for subdir in subdirs:
        mc_summary, mc_df = _load_monte_carlo(output_dir, subdir=subdir)
        if mc_summary is None or mc_df is None:
            continue

        title_suffix = "" if subdir is None else f" ({subdir})"
        metric = "BEP" if mc_summary.get("compute_bep") else "NPV"
        corr_pairs = _monte_carlo_correlations(mc_df, metric=metric)
        if show_plot:
            _plot_histogram(mc_df, metric=metric, bins=200)
            _plot_tornado(corr_pairs, metric=f"{metric}{title_suffix}")
            _plot_top_scatter(mc_df, corr_pairs, metric=metric, top_n=3)

        if metric == "BEP":
            input_cols = [
                "EE",
                "BRENT",
                "ETS1",
                "ETS2",
                "CAPEX",
                "Electrolyzer_eff",
                "Stack_life",
                "CO2_capture_cost",
                "OPEX_mult",
                "WACC",
                "Plant_life",
                "Utilization",
                "H2_compr_energy",
            ]
            input_cols = [col for col in input_cols if col in mc_df.columns]
            tree, tree_cols = _fit_bep_tree(mc_df, input_cols, metric="BEP")
            if tree is not None and tree_cols is not None:
                importances = tree.feature_importances_
                rows = [
                    {"Variable": _display_name(name), "importance": float(val)}
                    for name, val in zip(tree_cols, importances)
                    if val > 0
                ]
                if rows:
                    rows.sort(key=lambda item: item["importance"], reverse=True)
                    table = pd.DataFrame(rows)
                    print(f"\nDecision Tree Drivers (BEP{title_suffix})")
                    print(table.to_string(index=False))
                _print_tree_splits(tree, tree_cols)

        beta_pairs = _regression_sensitivity(mc_df, metric=metric)
        if beta_pairs:
            rows = [
                {
                    "Variable": _display_name(name),
                    "beta": float(beta),
                    "abs_beta": float(abs(beta)),
                }
                for name, beta in beta_pairs
            ]
            beta_table = pd.DataFrame(rows)
            print(f"\nRegression-Based Sensitivity ({_display_metric(metric)}{title_suffix})")
            print(beta_table.to_string(index=False))

        if show_plot:
            _plot_regression_tornado(beta_pairs, metric=f"{metric}{title_suffix}")


if __name__ == "__main__":
    default_dir = Path(__file__).with_name("outputs") / "economics_esaf"
    display_results(default_dir, show_plot=True)
