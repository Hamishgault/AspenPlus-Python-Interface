"""
Load and display saved Monte Carlo outputs without re-running the model.
"""

from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def display_monte_carlo_results(output_dir, show_plot=True):
    output_dir = Path(output_dir)
    summary_path = output_dir / "summary.json"
    results_path = output_dir / "monte_carlo_results.csv"

    if not summary_path.exists():
        raise FileNotFoundError(f"Missing summary.json in {output_dir}")
    if not results_path.exists():
        raise FileNotFoundError(f"Missing monte_carlo_results.csv in {output_dir}")

    summary = json.loads(summary_path.read_text())
    df = pd.read_csv(results_path)

    print("\nMonte Carlo Results")
    print("Samples:", summary.get("n_samples"))
    print("Seed:", summary.get("seed"))
    print("Compute BEP:", summary.get("compute_bep"))

    def show_quantiles(label, key):
        stats = summary.get(key, {})
        print(f"{label} p10/p50/p90:", stats.get("p10"), stats.get("p50"), stats.get("p90"))

    show_quantiles("IRR", "IRR")
    show_quantiles("VAN", "VAN")
    show_quantiles("BEP", "BEP")

    print("\nColumns:", ", ".join(df.columns))
    print("Rows:", len(df))

    if show_plot:
        fig, axes = plt.subplots(1, 3, figsize=(12, 3.5))
        axes[0].hist(df["IRR"].dropna(), bins=30, color="#4c72b0")
        axes[0].set_title("IRR")
        axes[1].hist(df["VAN"].dropna(), bins=30, color="#55a868")
        axes[1].set_title("VAN")

        if "BEP" in df.columns and df["BEP"].notna().any():
            axes[2].hist(df["BEP"].dropna(), bins=30, color="#c44e52")
            axes[2].set_title("BEP")
        else:
            axes[2].axis("off")

        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    default_dir = Path(__file__).with_name("outputs") / "economics_esaf" / "monte_carlo"
    display_monte_carlo_results(default_dir, show_plot=True)
