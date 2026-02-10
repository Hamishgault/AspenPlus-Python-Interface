from pathlib import Path
import csv
from typing import Dict, List, Tuple

import numpy as np
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
CSV_PATH = SCRIPT_DIR / "composition_samples.csv"
OUT_DIR = SCRIPT_DIR / "analysis_outputs"
ONLY_CONVERGED = True
TOP_N_COMPOUNDS = 10


def load_csv(path: Path) -> Tuple[List[str], List[List[float]], List[List[float]], List[bool]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing results file: {path}")

    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)

        t_start = 2
        compound_start = None
        for i, col in enumerate(header):
            if i < t_start:
                continue
            if not col.startswith("T#"):
                compound_start = i
                break
        if compound_start is None:
            raise RuntimeError("Could not detect compound columns in CSV header.")

        temp_cols = header[t_start:compound_start]
        compounds = header[compound_start:]

        temps: List[List[float]] = []
        comps: List[List[float]] = []
        converged_flags: List[bool] = []

        for row in reader:
            if not row:
                continue
            converged_flags.append(bool(int(row[1])))
            temps.append([float(v) for v in row[t_start:compound_start]])
            comps.append([float(v) for v in row[compound_start:]])

    return compounds, temps, comps, converged_flags


def save_stats(compounds: List[str], comps: np.ndarray) -> None:
    stats_path = OUT_DIR / "composition_stats.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with stats_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["compound", "mean", "std", "min", "max", "p5", "p50", "p95"])
        for i, name in enumerate(compounds):
            col = comps[:, i]
            writer.writerow(
                [
                    name,
                    np.mean(col),
                    np.std(col, ddof=1),
                    np.min(col),
                    np.max(col),
                    np.percentile(col, 5),
                    np.percentile(col, 50),
                    np.percentile(col, 95),
                ]
            )


def save_correlations(temp_cols: int, compounds: List[str], temps: np.ndarray, comps: np.ndarray) -> None:
    corr_path = OUT_DIR / "temp_to_compound_correlations.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with corr_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["temp_index"] + compounds)
        for i in range(temp_cols):
            row = [f"T#{i+1}"]
            for j in range(comps.shape[1]):
                corr = np.corrcoef(temps[:, i], comps[:, j])[0, 1]
                row.append(corr)
            writer.writerow(row)


def plot_distributions(compounds: List[str], comps: np.ndarray) -> None:
    means = comps.mean(axis=0)
    idx = np.argsort(means)[::-1][:TOP_N_COMPOUNDS]
    selected = [compounds[i] for i in idx]
    data = [comps[:, i] for i in idx]

    plt.figure(figsize=(12, 6))
    plt.boxplot(data, tick_labels=selected, showfliers=False)
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Mole Fraction")
    plt.title("Top compound composition distributions")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "composition_boxplot.png", dpi=150)


def plot_temp_sensitivity(temps: np.ndarray, comps: np.ndarray, compounds: List[str]) -> None:
    avg_temp = temps.mean(axis=1)
    means = comps.mean(axis=0)
    idx = np.argsort(means)[::-1][:TOP_N_COMPOUNDS]

    plt.figure(figsize=(10, 6))
    for i in idx:
        plt.scatter(avg_temp, comps[:, i], s=12, alpha=0.6, label=compounds[i])
    plt.xlabel("Average Temperature (°C)")
    plt.ylabel("Mole Fraction")
    plt.title("Average temperature vs composition")
    plt.legend(ncol=2, fontsize=8)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "avg_temp_scatter.png", dpi=150)


def plot_input_profiles(temps: np.ndarray) -> None:
    plt.figure(figsize=(10, 6))
    x = np.arange(1, temps.shape[1] + 1)
    for row in temps:
        plt.plot(x, row, color="#4C78A8", alpha=0.25)
    plt.xlabel("Temperature segment index")
    plt.ylabel("Temperature (°C)")
    plt.title("Input temperature profiles (all samples)")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "input_temperature_profiles.png", dpi=150)


def main() -> None:
    compounds, temps, comps, converged = load_csv(CSV_PATH)

    temps_arr = np.array(temps, dtype=float)
    comps_arr = np.array(comps, dtype=float)

    if ONLY_CONVERGED:
        mask = np.array(converged, dtype=bool)
        temps_arr = temps_arr[mask]
        comps_arr = comps_arr[mask]

    if temps_arr.size == 0 or comps_arr.size == 0:
        raise RuntimeError("No samples available after filtering.")

    save_stats(compounds, comps_arr)
    save_correlations(temps_arr.shape[1], compounds, temps_arr, comps_arr)
    plot_distributions(compounds, comps_arr)
    plot_temp_sensitivity(temps_arr, comps_arr, compounds)
    plot_input_profiles(temps_arr)

    print(f"Saved analysis to {OUT_DIR}")


if __name__ == "__main__":
    main()
