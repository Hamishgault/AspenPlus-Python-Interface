import argparse
from csv import DictReader
from math import isnan, sqrt
from pathlib import Path
from statistics import median, variance


LABELS = {
    "EE": "Electricity price",
    "BRENT": "Brent crude price",
    "ETS1": "ETS scenario 1",
    "ETS2": "ETS scenario 2",
    "CAPEX": "Capital expenditure (EUR)",
    "ReFuel": "ReFuel price",
    "Electrolyzer_eff": "Electrolyser efficiency",
    "Stack_life": "Stack lifetime",
    "CO2_capture_cost": "CO2 capture cost",
    "OPEX_mult": "Operating expenditure multiplier",
    "WACC": "Weighted average cost of capital",
    "Utilization": "Plant utilization",
    "H2_compr_energy": "Hydrogen compression energy",
    "BEP": "Break-even ReFuel",
    "IRR": "Internal rate of return",
    "VAN": "Net present value",
    "err": "Model residual",
    "LCOH_total": "Total LCOH",
}

INPUT_COLUMNS = [
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
    "Utilization",
    "H2_compr_energy",
]

OUTPUT_COLUMNS = ["BEP", "IRR", "VAN", "err", "LCOH_total"]

SCALES = {
    "CAPEX": 1e3,
}


def fmt(value: float) -> str:
    if isnan(value):
        return "n/a"
    return f"{value:.3g}"


def load_numeric_columns(csv_path: Path) -> dict[str, list[float]]:
    columns: dict[str, list[float]] = {name: [] for name in LABELS}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = DictReader(handle)
        for row in reader:
            for name in columns:
                raw_value = row.get(name, "")
                if raw_value is None or raw_value == "":
                    continue
                columns[name].append(float(raw_value))
    return columns


def build_table(df: dict[str, list[float]], run_mode: str) -> str:
    lines: list[str] = []
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"  \centering")
    lines.append(r"  \small")
    lines.append(r"  \begin{tabular}{lrr}")
    lines.append(r"    \toprule")
    lines.append(r"    Variable & Median & Standard deviation \\")
    lines.append(r"    \midrule")

    for title, columns in (("Sampled inputs", INPUT_COLUMNS), ("Outputs", OUTPUT_COLUMNS)):
        lines.append(rf"    \multicolumn{{3}}{{l}}{{\textbf{{{title}}}}} \\")
        for column in columns:
            scale = SCALES.get(column, 1.0)
            series = [value * scale for value in df[column]]
            med = median(series) if len(series) else float("nan")
            var = variance(series) if len(series) > 1 else float("nan")
            std = sqrt(var) if not isnan(var) else float("nan")
            lines.append(f"    {LABELS[column]} & {fmt(med)} & {fmt(std)} " + r"\\")
        if title == "Sampled inputs":
            lines.append(r"    \midrule")

    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(
        rf"  \caption{{Median and sample standard deviation for the economic Monte Carlo variables, based on the {run_mode} run results.}}"
    )
    lines.append(rf"  \label{{tab:economic-monte-carlo-variables-{run_mode}}}")
    lines.append(r"\end{table}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["normal", "bep"], default="normal")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    csv_path = root / "outputs" / "economics_esaf" / "monte_carlo" / args.mode / "monte_carlo_results.csv"
    out_path = root / "outputs" / "economics_esaf" / "monte_carlo" / args.mode / "monte_carlo_variables_table.tex"

    df = load_numeric_columns(csv_path)
    table = build_table(df, args.mode)
    out_path.write_text(table, encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
