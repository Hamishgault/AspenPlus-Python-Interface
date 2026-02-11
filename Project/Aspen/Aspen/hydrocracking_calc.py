from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple, TypedDict

import math
import pandas as pd
import matplotlib.pyplot as plt

WORKDIR = Path(__file__).resolve().parent
BKP_NAME = "FTS Alessio_CO_conv_Ref_20bar_11%.bkp"
APPLY_TO_ASPEN = False

PRIMARY_BLOCK = "R-HC-P"
SECONDARY_BLOCK = "R-HC-S"
INTERHC_STREAM = "INTERHC"
INTERHC_PHASE = "VL1"

IGNORE_COLUMNS = {"In", "Out", "k", "n"}


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _to_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if value.strip() == "":
            return 0.0
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


class YieldRecord(TypedDict):
    reactant: str
    conversion: float
    in_flow: float
    factors: Dict[str, float]
    sum_factors: float


def load_yield_sheet(xlsx_path: Path, sheet_name: str) -> List[YieldRecord]:
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
    df = df.dropna(how="all")
    df = _clean_columns(df)

    columns = list(df.columns)
    if "Conversion" not in columns:
        raise ValueError(f"Missing 'Conversion' column in sheet '{sheet_name}'.")
    if "Prod. Factor" not in columns:
        raise ValueError(f"Missing 'Prod. Factor' column in sheet '{sheet_name}'.")

    reactant_col = columns[0]
    product_start = columns.index("Prod. Factor") + 1
    product_cols = [
        col
        for col in columns[product_start:]
        if col and col not in IGNORE_COLUMNS
    ]

    records: List[YieldRecord] = []
    for _, row in df.iterrows():
        reactant = str(row[reactant_col]).strip()
        if not reactant or reactant.lower() == "nan":
            continue
        conversion = _to_float(row.get("Conversion", 0.0))
        in_flow_raw = row.get("In")
        in_flow = _to_float(in_flow_raw) if pd.notna(in_flow_raw) else math.nan

        factors = {col: _to_float(row.get(col)) for col in product_cols}
        sum_factors = sum(factors.values())

        records.append(
            {
                "reactant": reactant,
                "conversion": conversion,
                "in_flow": in_flow,
                "factors": factors,
                "sum_factors": sum_factors,
            }
        )

    return records


def build_primary_feed(
    records: Iterable[YieldRecord], default_feed: float = 1.0
) -> Dict[str, float]:
    feed: Dict[str, float] = {}
    for rec in records:
        reactant = str(rec["reactant"])
        in_flow = rec["in_flow"]
        if not math.isnan(in_flow):
            feed[reactant] = in_flow
        else:
            feed[reactant] = default_feed
    return feed


def apply_ryield_stage(
    feed_flows: Dict[str, float],
    stage_name: str,
    yield_records: Iterable[YieldRecord],
) -> Tuple[Dict[str, float], List[Dict[str, object]]]:
    outlet: Dict[str, float] = dict(feed_flows)
    tidy_rows: List[Dict[str, object]] = []

    for rec in yield_records:
        reactant = str(rec["reactant"])
        if reactant not in outlet:
            in_flow = rec["in_flow"]
            if not math.isnan(in_flow):
                outlet[reactant] = in_flow
            else:
                continue

        feed = float(outlet.get(reactant, 0.0))
        conversion = rec["conversion"]
        consumed = feed * conversion
        outlet[reactant] = feed - consumed

        sum_factors = rec["sum_factors"] if rec["sum_factors"] else 0.0
        if sum_factors <= 0.0:
            continue

        factors = rec["factors"]
        for product, factor in factors.items():
            if factor == 0:
                continue
            yield_frac = factor / sum_factors
            f_product = consumed * yield_frac
            outlet[product] = outlet.get(product, 0.0) + f_product
            tidy_rows.append(
                {
                    "stage": stage_name,
                    "reactant": reactant,
                    "product": product,
                    "yield": yield_frac,
                    "F_product": f_product,
                    "F_consumed": consumed,
                }
            )

    return outlet, tidy_rows


def build_component_yields(
    feed_flows: Dict[str, float],
    yield_records: Iterable[YieldRecord],
) -> Tuple[Dict[str, float], Dict[str, float]]:
    outlet, _ = apply_ryield_stage(feed_flows, "stage", yield_records)
    total_feed = sum(feed_flows.values())
    if total_feed <= 0:
        return outlet, {}

    yields = {
        component: flow / total_feed
        for component, flow in outlet.items()
        if flow > 0
    }
    return outlet, yields


def apply_to_aspen(
    yield_map: Dict[str, float],
    block_name: str,
    set_interhc_phase: bool = False,
) -> None:
    from CodeLibrary import Simulation

    bkp_path = WORKDIR / BKP_NAME
    if not bkp_path.exists():
        raise FileNotFoundError(f".bkp file not found: {bkp_path}")

    sim = Simulation(
        AspenFileName=str(bkp_path),
        WorkingDirectoryPath=str(WORKDIR),
        VISIBILITY=True,
    )

    sim.BLK_RYIELD_Set_YieldCalcOption(block_name, "NO")
    for component, value in yield_map.items():
        sim.BLK_RYIELD_Set_ComponentYield_YieldPerFlow(block_name, value, component)
        sim.BLK_RYIELD_Set_ComponentYield_ChangeBasis(block_name, component, "MOLE")

    if set_interhc_phase:
        sim.BLK_RYIELD_Set_PhaseOfProductStream(
            block_name,
            INTERHC_PHASE,
            INTERHC_STREAM,
        )


def outlet_composition_table(outlet: Dict[str, float]) -> pd.DataFrame:
    data = [
        {"component": comp, "F_out": flow}
        for comp, flow in outlet.items()
        if flow > 0
    ]
    df = pd.DataFrame(data)
    total = df["F_out"].sum()
    df["y_out"] = df["F_out"] / total if total > 0 else 0.0
    return df.sort_values("F_out", ascending=False).reset_index(drop=True)


def plot_outlet_composition(df: pd.DataFrame, output_path: Path) -> None:
    if df.empty:
        return

    plt.figure(figsize=(10, 5))
    plt.bar(df["component"], df["y_out"], color="#2a6f8f")
    plt.ylabel("Mole fraction")
    plt.title("Outlet composition")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def main() -> int:
    workdir = WORKDIR
    xlsx_path = workdir / "hydrocracking.xlsx"
    if not xlsx_path.exists():
        print(f"Missing input file: {xlsx_path}")
        return 1

    primary = load_yield_sheet(xlsx_path, "Primary")
    secondary = load_yield_sheet(xlsx_path, "Secondary")

    feed_primary = build_primary_feed(primary, default_feed=1.0)
    outlet_primary, tidy_primary = apply_ryield_stage(
        feed_primary, "primary", primary
    )
    outlet_secondary, tidy_secondary = apply_ryield_stage(
        outlet_primary, "secondary", secondary
    )

    _, primary_yields = build_component_yields(feed_primary, primary)
    _, secondary_yields = build_component_yields(outlet_primary, secondary)

    tidy = pd.DataFrame(tidy_primary + tidy_secondary)
    outlet_df = outlet_composition_table(outlet_secondary)

    output_dir = workdir / "outputs" / "hydrocracking"
    output_dir.mkdir(parents=True, exist_ok=True)

    tidy_path = output_dir / "hydrocracking_yields_tidy.csv"
    outlet_path = output_dir / "hydrocracking_outlet_composition.csv"
    plot_path = output_dir / "hydrocracking_outlet_composition.png"

    tidy.to_csv(tidy_path, index=False)
    outlet_df.to_csv(outlet_path, index=False)
    plot_outlet_composition(outlet_df, plot_path)

    print("Saved:")
    print(f"- {tidy_path}")
    print(f"- {outlet_path}")
    print(f"- {plot_path}")

    if APPLY_TO_ASPEN:
        apply_to_aspen(primary_yields, PRIMARY_BLOCK, set_interhc_phase=True)
        apply_to_aspen(secondary_yields, SECONDARY_BLOCK, set_interhc_phase=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
