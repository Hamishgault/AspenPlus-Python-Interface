import csv
from pathlib import Path

import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_PATH = SCRIPT_DIR.parent / "monte_results.csv"
OUTPUT_DIR = SCRIPT_DIR / "outputs"
OUTPUT_PATH = OUTPUT_DIR / "sensitivity_ratio_vs_flows.png"


def main() -> None:
    rows = []
    with DATA_PATH.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status", "").strip().lower() != "ok":
                continue
            rows.append(
                (
                    float(row["ratio"]),
                    float(row["naphtha"]),
                    float(row["kero"]),
                )
            )

    if not rows:
        raise SystemExit("No rows with status=ok found.")

    rows.sort(key=lambda r: r[0])
    ratios = [r[0] for r in rows]
    naphtha = [r[1] for r in rows]
    kero = [r[2] for r in rows]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(ratios, naphtha, marker="o", label="Naphtha flowrate")
    ax.plot(ratios, kero, marker="s", label="Kero flowrate")
    ax.set_xlabel("Ratio")
    ax.set_ylabel("Flowrate")
    ax.set_title("Sensitivity: Ratio vs Naphtha/Kero Flowrates")
    ax.grid(True, alpha=0.3)
    ax.legend()

    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"Saved plot to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()