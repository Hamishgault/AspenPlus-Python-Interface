#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jul 24 14:56:03 2025

@author: Alessio
"""

from datetime import datetime
from pathlib import Path
import json
from typing import cast

import numpy as np
import numpy_financial as npf
import pandas as pd
import matplotlib.pyplot as plt

from scipy.optimize import minimize, brentq
from we_function import WE
from results_viewer import display_results

fileName = str(Path(__file__).with_name("Economics eSAF.xlsx"))
OUTPUT_DIR = Path(__file__).with_name("outputs") / "economics_esaf"

ECON_IDX = {
    "d_e": 0,
    "dr": 1,
    "dp": 2,
    "DeP_n": 3,
    "infl": 4,
    "tax": 5,
    "Py": 6,
    "WACC": 10,
}
REAL_IDX = {
    "EE": 0,
    "cambio": 1,
    "conv": 2,
    "BRENT": 3,
    "DIFF_LPG": 4,
    "DIFF_NAPTHA": 5,
    "DIFF_KERO": 6,
    "DIFF_DIESEL": 7,
    "DIFF_WAX": 8,
    "Met": 9,
    "ETS1": 10,
    "ETS2": 11,
    "CC": 12,
    "ReFuel": 16,
}
PLANT_IDX = {
    "CAPEX": 0,
    "CO2_feed": 1,
    "CO2_compr": 2,
    "H2_feed": 3,
    "H2_compr": 4,
    "Pwr": 5,
    "Heat": 6,
    "Operatori": 7,
    "Overhead": 8,
    "Manutenzione": 9,
    "CO2_out": 10,
    "Naptha_mass": 11,
    "Naptha_CO2": 12,
    "Naptha_GJ": 13,
    "Kero_mass": 14,
    "Kero_CO2": 15,
    "Kero_GJ": 16,
    "Diesel_mass": 17,
    "Diesel_CO2": 18,
    "Diesel_GJ": 19,
}


def get_scalar(data, section, key):
    idx_map = {
        "econ": ECON_IDX,
        "real": REAL_IDX,
        "plant": PLANT_IDX,
    }
    return data[section][idx_map[section][key]].item()


def build_input_summary(data):
    return {
        "econ": {
            "d_e": float(get_scalar(data, "econ", "d_e")),
            "dr": float(get_scalar(data, "econ", "dr")),
            "dp": int(get_scalar(data, "econ", "dp")),
            "DeP_n": int(get_scalar(data, "econ", "DeP_n")),
            "infl": float(get_scalar(data, "econ", "infl")),
            "tax": float(get_scalar(data, "econ", "tax")),
            "Py": int(get_scalar(data, "econ", "Py")),
            "WACC": float(get_scalar(data, "econ", "WACC")),
        },
        "real": {
            "EE": float(get_scalar(data, "real", "EE")),
            "cambio": float(get_scalar(data, "real", "cambio")),
            "conv": float(get_scalar(data, "real", "conv")),
            "BRENT": float(get_scalar(data, "real", "BRENT")),
            "DIFF_LPG": float(get_scalar(data, "real", "DIFF_LPG")),
            "DIFF_NAPTHA": float(get_scalar(data, "real", "DIFF_NAPTHA")),
            "DIFF_KERO": float(get_scalar(data, "real", "DIFF_KERO")),
            "DIFF_DIESEL": float(get_scalar(data, "real", "DIFF_DIESEL")),
            "DIFF_WAX": float(get_scalar(data, "real", "DIFF_WAX")),
            "Met": float(get_scalar(data, "real", "Met")),
            "ETS1": float(get_scalar(data, "real", "ETS1")),
            "ETS2": float(get_scalar(data, "real", "ETS2")),
            "CC": float(get_scalar(data, "real", "CC")),
        },
        "plant": {
            "CAPEX": float(get_scalar(data, "plant", "CAPEX")),
            "CO2_feed": float(get_scalar(data, "plant", "CO2_feed")),
            "CO2_compr": float(get_scalar(data, "plant", "CO2_compr")),
            "H2_feed": float(get_scalar(data, "plant", "H2_feed")),
            "H2_compr": float(get_scalar(data, "plant", "H2_compr")),
            "Pwr": float(get_scalar(data, "plant", "Pwr")),
            "Heat": float(get_scalar(data, "plant", "Heat")),
            "Operatori": float(get_scalar(data, "plant", "Operatori")),
            "Overhead": float(get_scalar(data, "plant", "Overhead")),
            "Manutenzione": float(get_scalar(data, "plant", "Manutenzione")),
        },
    }


def compute_irr(cash_flows):
    """Compute IRR for a cash flow series; return None if undefined."""
    cash_flows = np.asarray(cash_flows, dtype=float)
    if not (np.any(cash_flows > 0) and np.any(cash_flows < 0)):
        return None

    irr = npf.irr(cash_flows)
    if irr is not None and np.isfinite(irr):
        return float(irr)

    def npv(rate):
        return np.sum(cash_flows / (1 + rate) ** np.arange(cash_flows.size))

    try:
        root = brentq(npv, -0.99, 10.0)
    except ValueError:
        return None

    if isinstance(root, tuple):
        root = root[0]

    return float(cast(float, root))


def save_results(
    output_dir,
    IRR,
    BEP,
    err,
    VAN,
    T,
    COP,
    Kero,
    LCOH,
    Sell_Price_k,
    input_summary,
):
    output_dir.mkdir(parents=True, exist_ok=True)

    results_table_path = output_dir / "results_table.csv"
    results_table_xlsx_path = output_dir / "results_table.xlsx"
    arrays_path = output_dir / "arrays.npz"
    summary_path = output_dir / "summary.json"

    irr_value = np.nan if IRR is None else IRR

    T.to_csv(results_table_path, index=False)
    T.to_excel(results_table_xlsx_path, index=False)
    np.savez(
        arrays_path,
        COP=COP,
        Kero=Kero,
        LCOH=LCOH,
        Sell_Price_k=Sell_Price_k,
        IRR=irr_value,
        BEP=BEP,
        err=err,
        VAN=VAN,
    )

    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "outputs": {
            "results_table": results_table_path.name,
            "arrays": arrays_path.name,
            "results_table_xlsx": results_table_xlsx_path.name,
            "plot": "market_price.png",
        },
        "metrics": {
            "IRR": None if IRR is None else float(IRR),
            "BEP": float(np.atleast_1d(BEP)[0]),
            "err": float(np.atleast_1d(err)[0]),
            "VAN": float(np.atleast_1d(VAN)[0]),
        },
        "inputs": input_summary,
    }

    summary_path.write_text(json.dumps(summary, indent=2))
    return output_dir


data = {
    "econ": pd.read_excel(fileName, "eSAF Matlab", usecols="C", skiprows=1, nrows=11).to_numpy(),
    "real": pd.read_excel(fileName, "eSAF Matlab", usecols="F", skiprows=1, nrows=17).to_numpy(),
    "plant": pd.read_excel(fileName, "eSAF Matlab", usecols="J", skiprows=1, nrows=20).to_numpy(),
    "we_matrix": pd.read_excel(fileName, "Electrolyzer", usecols="J:L", skiprows=3, nrows=6).to_numpy(),
    "we": pd.read_excel(fileName, "Electrolyzer", usecols="C", skiprows=3, nrows=3).to_numpy(),
    "we_type": str(pd.read_excel(fileName, "Electrolyzer", usecols="C", skiprows=12, nrows=1)),
}


def val(data, DF=None, ReFuel=None):
    """Compute TEA outputs for given discount factor and ReFuel value."""
    if DF is None:
        DF = get_scalar(data, "econ", "WACC")
    if ReFuel is None:
        ReFuel = get_scalar(data, "real", "ReFuel")

    LCOH, TOC, SR, ACC, H2_p, Mtn, H2_pwr = WE(data)

    TOC_FT = 150e3
    TOC_AtJ = 240e3

    CAPEX = get_scalar(data, "plant", "CAPEX")

    d_e = get_scalar(data, "econ", "d_e")
    dr = get_scalar(data, "econ", "dr")
    dp = int(get_scalar(data, "econ", "dp"))
    DeP_n = int(get_scalar(data, "econ", "DeP_n"))
    infl = get_scalar(data, "econ", "infl")
    tax = get_scalar(data, "econ", "tax")

    EE = get_scalar(data, "real", "EE")
    cambio = get_scalar(data, "real", "cambio")
    conv = get_scalar(data, "real", "conv")
    BRENT = get_scalar(data, "real", "BRENT")
    ETS1 = get_scalar(data, "real", "ETS1")
    ETS2 = get_scalar(data, "real", "ETS2")
    DIFF_LPG = get_scalar(data, "real", "DIFF_LPG")
    DIFF_NAPTHA = get_scalar(data, "real", "DIFF_NAPTHA")
    DIFF_KERO = get_scalar(data, "real", "DIFF_KERO")
    DIFF_DIESEL = get_scalar(data, "real", "DIFF_DIESEL")
    DIFF_WAX = get_scalar(data, "real", "DIFF_WAX")
    Met = get_scalar(data, "real", "Met")
    CC = get_scalar(data, "real", "CC")

    CO2_feed = get_scalar(data, "plant", "CO2_feed")
    CO2_compr = get_scalar(data, "plant", "CO2_compr")
    H2_feed = get_scalar(data, "plant", "H2_feed")
    H2_compr = get_scalar(data, "plant", "H2_compr")
    Pwr = get_scalar(data, "plant", "Pwr")
    Heat = get_scalar(data, "plant", "Heat")
    Operatori = get_scalar(data, "plant", "Operatori")
    Overhead = get_scalar(data, "plant", "Overhead")
    Manutenzione = get_scalar(data, "plant", "Manutenzione")
    CO2_out = get_scalar(data, "plant", "CO2_out")
    Naptha_mass = get_scalar(data, "plant", "Naptha_mass")
    Naptha_CO2 = get_scalar(data, "plant", "Naptha_CO2")
    Naptha_GJ = get_scalar(data, "plant", "Naptha_GJ")
    Kero_mass = get_scalar(data, "plant", "Kero_mass")
    Kero_CO2 = get_scalar(data, "plant", "Kero_CO2")
    Kero_GJ = get_scalar(data, "plant", "Kero_GJ")
    Diesel_mass = get_scalar(data, "plant", "Diesel_mass")
    Diesel_CO2 = get_scalar(data, "plant", "Diesel_CO2")
    Diesel_GJ = get_scalar(data, "plant", "Diesel_GJ")

    Py = int(get_scalar(data, "econ", "Py"))

    N = 2050 - Py

    n = np.arange(N + 1)
    y = np.arange(Py, 2051)

    DF_n = (1 + DF) ** n

    def replicate(val):
        return np.ones(N + 1) * val

    def safe_divide(numer, denom):
        if denom == 0:
            return np.full_like(numer, np.nan, dtype=float)
        return numer / denom

    def payper(rate, nper, pv):
        if rate == 0:
            return pv / nper
        return pv * rate * (1 + rate) ** nper / ((1 + rate) ** nper - 1)

    EE_n = replicate(EE)
    cambio_n = replicate(cambio)
    BRENT_n = replicate(BRENT)

    ETS1_n = replicate(ETS1)
    ETS2_n = replicate(ETS2)
    DIFF_LPG_n = replicate(DIFF_LPG)
    DIFF_NAPTHA_n = replicate(DIFF_NAPTHA)
    DIFF_KERO_n = replicate(DIFF_KERO)
    DIFF_DIESEL_n = replicate(DIFF_DIESEL)
    DIFF_WAX_n = replicate(DIFF_WAX)
    Met_n = replicate(Met)
    CC_n = replicate(CC)
    ReFuel_n = replicate(ReFuel)

    Exp = np.zeros((13, N + 1))
    Rev = np.zeros((10, N + 1))
    Loan = np.zeros((4, N + 1))
    Dep = np.zeros(N + 1)
    Tax = np.zeros((2, N + 1))

    x = int(np.where(y == 2030)[0][0])

    RED_b = LCOH[-1] * 1000 / 3 - (BRENT_n[x] + DIFF_NAPTHA_n[x]) * conv
    RED_d = LCOH[-1] * 1000 / 3 - (BRENT_n[x] + DIFF_DIESEL_n[x]) * conv
    RED_k = LCOH[-1] * 1000 / 2 - (BRENT_n[x] + DIFF_KERO_n[x]) * conv * 1.5

    RED_k_n = replicate(RED_k)
    RED_b_n = replicate(RED_b)
    RED_d_n = replicate(RED_d)

    Exp[0, x:] = H2_p * CO2_feed * CC_n[x:]
    Exp[1, x:] = H2_p * CO2_feed * CO2_compr * EE_n[x:]
    Exp[2, x:] = H2_pwr * EE_n[x:]
    Exp[3, x:] = H2_p * H2_compr * EE_n[x:]
    Exp[4, x:] = H2_p * Pwr * EE_n[x:]
    Exp[5, x:] = H2_p * Heat * Met_n[x:]

    Exp[8, x:] = Operatori
    Exp[9, x:] = Manutenzione * TOC_FT + SR / (N - 1) / 1e3 + TOC * Mtn / 1e3
    Exp[10, x:] = Overhead
    Exp[11, x:] = H2_p * CO2_out * ETS1_n[x:]
    Exp[12, x - 1] = (1 - d_e) * CAPEX

    Tot_Exp = np.sum(Exp, axis=0)

    Rev[0, x:] = Naptha_mass * H2_p * (BRENT_n[x:] + DIFF_NAPTHA_n[x:]) * conv
    Rev[1, x:] = Naptha_CO2 * H2_p * ETS2_n[x:]
    Rev[2, x:] = Naptha_mass * H2_p * RED_b_n[x:]

    Rev[3, x:] = Kero_mass * H2_p * (BRENT_n[x:] + DIFF_KERO_n[x:]) * conv
    Rev[4, x:] = Kero_CO2 * H2_p * ETS1_n[x:]
    Rev[5, x:] = Kero_mass * H2_p * RED_k_n[x:]
    Rev[6, x:] = Kero_mass * H2_p * ReFuel_n[x:]

    Rev[7, x:] = Diesel_mass * H2_p * (BRENT_n[x:] + DIFF_DIESEL_n[x:]) * conv
    Rev[8, x:] = Diesel_CO2 * H2_p * ETS2_n[x:]
    Rev[9, x:] = Diesel_mass * H2_p * RED_d_n[x:]

    Tot_Rev = np.sum(Rev, axis=0)

    Loan[0, x:x + dp] = payper(dr, dp, CAPEX * d_e)
    Loan[1, :] = CAPEX * d_e

    for j in range(x, N + 1):
        if Loan[1, j - 1] > 0:
            Loan[2, j] = Loan[1, j - 1] * dr
            Loan[3, j] = Loan[0, j] - Loan[2, j]
            Loan[1, j] = Loan[1, j - 1] - Loan[3, j]

    Dep[x:x + DeP_n] = CAPEX / DeP_n

    Tax[0, :] = Tot_Rev - Tot_Exp - Dep - Loan[2, :]
    Tax[0, Tax[0, :] < 0] = 0
    Tax[1, x:] = Tax[0, x:] * tax

    OCF = Tot_Rev - Tot_Exp - Loan[0, :] - Tax[1, :]
    DCF = OCF / DF_n

    CCF = np.zeros(N + 1)
    CCF[0] = DCF[0]
    for j in range(1, N + 1):
        CCF[j] = CCF[j - 1] + DCF[j]

    VAN = CCF[-1]

    RES = np.vstack([
        Exp,
        Rev,
        Loan,
        Dep[np.newaxis],
        Tax,
        DF_n[np.newaxis],
        OCF[np.newaxis],
        DCF[np.newaxis],
        CCF[np.newaxis],
    ])

    Kero_k = safe_divide(Rev[3:7, x], Kero_mass * H2_p)
    Naphta_k = safe_divide(Rev[0:3, x], Naptha_mass * H2_p)
    Diesel_k = safe_divide(Rev[7:10, x], Diesel_mass * H2_p)

    Ex = np.zeros(10)
    Ex[0] = np.sum(RES[0:2, 1])
    Ex[1] = np.sum(RES[2:4, 1])
    Ex[2] = RES[4, 1]
    Ex[3] = RES[5, 1]
    Ex[4] = np.sum(RES[[8, 10], 1])
    Ex[5] = RES[9, 1]
    Ex[6] = RES[11, 1]

    ACC = (np.sum(Kero_k) + np.sum(Naphta_k) + np.sum(Diesel_k) - np.sum(Ex[0:7]) / (Kero_mass * H2_p)) * Kero_mass * H2_p
    Ex[7] = ACC
    Ex[8] = np.sum(RES[0:13, 1]) + ACC

    COP = Ex / (Kero_mass * H2_p)
    Sell_Price_k = np.array([np.sum(Kero_k), np.sum(Naphta_k), np.sum(Diesel_k)])
    err = abs(VAN)

    str_labels = [
        "n", "year", "CO2 feed", "CO2 compression", "H2 production", "H2 compression",
        "Power", "Heating", "CW", "Steam", "Operator", "Maintenance", "Overhead",
        "CO2 ETS", "FCI", "Naphta Fossil", "Naphtha ETS", "Naphtha RED", "Kero Fossil",
        "Kero ETS", " Kero RED", "Kero ReFuel", "Diesel Fossil", "Diesel ETS",
        "Diesel RED", "Loan Annuity", "Residual Debt", "Interests", "Principal Rep",
        "Dep", "Profit", "Tax", "DF", "OCF", "DCF", "CCF",
    ]

    T = pd.DataFrame(data=np.vstack([n, y, RES]), index=str_labels).T

    cash_flows = np.zeros(N + 1)
    cash_flows[0] = -CAPEX
    cash_flows[1:] = OCF[1:]

    product_breakdown = {
        "Kerosene": np.nan_to_num(Kero_k, nan=0.0),
        "Naphtha": np.nan_to_num(np.append(Naphta_k, 0.0), nan=0.0),
        "Diesel": np.nan_to_num(np.append(Diesel_k, 0.0), nan=0.0),
    }

    return err, VAN, T, COP, Kero_k, LCOH, Sell_Price_k, cash_flows, OCF, CCF, product_breakdown


def report_results(irr, bep, van, lcoh, cop, breakdown):
    irr_display = "undefined" if irr is None else f"{irr:.6f}"
    print("\nResults summary")
    print("IRR:", irr_display)
    print("BEP:", bep)
    print("VAN:", van)
    print("LCOH (CAPEX, EE, Stack, OPEX, Total):", lcoh)
    print("COP (components):", cop)

    print("\nPrice breakdown per product (Fossil, ETS, RED, ReFuel)")
    for product, values in breakdown.items():
        print(f"{product}: {values}")

    print("\nCOP per product")
    for product, values in breakdown.items():
        print(f"{product}: {np.sum(values)}")


def main():
    DF_default = get_scalar(data, "econ", "WACC")
    r_BEP = minimize(
        lambda ReFuel: val(data, DF_default, ReFuel[0])[0],
        x0=[5000],
        method="L-BFGS-B",
        bounds=[(0, 10000)],
    )

    BEP = float(r_BEP.x[0])

    err, VAN, T, COP, Kero_k, LCOH, Sell_Price_k, cash_flows, OCF, CCF, product_breakdown = val(
        data,
        ReFuel=BEP,
    )

    IRR = compute_irr(cash_flows)

    products = ["Kerosene", "Naphtha", "Diesel"]
    components = ["Fossil", "ETS", "RED", "ReFuel"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

    bottom = np.zeros(len(products))
    for i, comp in enumerate(components):
        values = np.array([
            product_breakdown["Kerosene"][i],
            product_breakdown["Naphtha"][i],
            product_breakdown["Diesel"][i],
        ])
        values = np.nan_to_num(values, nan=0.0)
        plt.bar(products, values, bottom=bottom, color=colors[i], label=comp)
        bottom += values

    plt.ylabel("Price EUR/ton")
    plt.title("Market Price")
    plt.legend()

    output_dir = save_results(
        OUTPUT_DIR,
        IRR,
        BEP,
        err,
        VAN,
        T,
        COP,
        Kero_k,
        LCOH,
        Sell_Price_k,
        build_input_summary(data),
    )

    plt.savefig(output_dir / "market_price.png", dpi=150, bbox_inches="tight")
    plt.close()

    report_results(IRR, BEP, VAN, LCOH, COP, product_breakdown)
    display_results(output_dir, show_plot=False)


if __name__ == "__main__":
    main()
