
"""
Load and display saved Economics_eSAF outputs without re-running the model.
"""

from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


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


if __name__ == "__main__":
    default_dir = Path(__file__).with_name("outputs") / "economics_esaf"
    display_results(default_dir, show_plot=True)
