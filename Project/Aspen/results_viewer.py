"""Results viewer for Aspen batch runs.

- Loads a results CSV (default: `Project/Aspen/batch_results.csv`).
- Prints a textual (ASCII) histogram and summary stats for CO inputs.
- Prints a textual histogram and summary stats for each numeric product column
  (e.g. `naphtha`, `kero`).
- Saves visual histogram PNGs to an output directory (default: `plots/`).

Usage examples:
  python Project/Aspen/results_viewer.py
  python Project/Aspen/results_viewer.py --file Project/Aspen/batch_results.csv --out-dir Project/Aspen/plots --bins 20

"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DEFAULT_CSV = Path(__file__).resolve().parent / "batch_results.csv"
DEFAULT_OUTDIR = Path(__file__).resolve().parent / "plots"


def _ascii_hist(values: np.ndarray, bins: int = 10, width: int = 40) -> List[str]:
    counts, edges = np.histogram(values, bins=bins)
    maxc = counts.max() if len(counts) else 0
    lines: List[str] = []
    for i, c in enumerate(counts):
        left = edges[i]
        right = edges[i + 1]
        bar_len = int((c / maxc) * width) if maxc > 0 else 0
        bar = "#" * bar_len
        lines.append(f"{left:>8.4g} - {right:<8.4g} | {c:>6d} | {bar}")
    return lines


def _print_summary(name: str, ser: pd.Series) -> None:
    vals = ser.dropna().astype(float)
    if vals.empty:
        print(f"{name}: no numeric data")
        return
    cnt = len(vals)
    mean = vals.mean()
    std = vals.std()
    mn = vals.min()
    mx = vals.max()
    print(f"\n{name} — n={cnt}  mean={mean:.6g}  std={std:.6g}  min={mn:.6g}  max={mx:.6g}")


def plot_and_save_hist(values: np.ndarray, title: str, out_path: Path, bins: int = 20, xlabel: str | None = None, ylabel: str | None = None) -> None:
    plt.figure(figsize=(6, 4))
    plt.hist(values, bins=bins, edgecolor='black')
    plt.title(title)
    # allow explicit axis labels (include units when provided)
    plt.xlabel(xlabel if xlabel is not None else title)
    if ylabel is not None:
        plt.ylabel(ylabel)
    plt.grid(axis='y', alpha=0.3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(str(out_path))
    plt.close()


def plot_and_save_scatter(x: np.ndarray, y: np.ndarray, title: str, xlabel: str, ylabel: str, out_path: Path) -> None:
    """Create and save a simple scatter plot with labels and grid."""
    plt.figure(figsize=(6, 4))
    plt.scatter(x, y, c='tab:blue', edgecolor='k', alpha=0.8)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(alpha=0.3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(str(out_path))
    plt.close()


def view_results(csv_path: Path, out_dir: Path, bins: int = 20, show_plots: bool = False) -> None:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Results CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)

    # detect reactor CO (mole-fraction) column (common names: 'co', 'x_co', 'CO', 'CO%')
    co_col = None
    for candidate in ['co', 'x_co', 'CO', 'CO%']:
        if candidate in df.columns:
            co_col = candidate
            break

    # attempt to extract reactor CO from the text _rstoic_iter cell if present
    if co_col is None:
        for rcol in ['_rstoic_iter', 'rstoic_iter', 'rstoic']:
            if rcol in df.columns:
                import re

                def _extract_co_from_rstoic_cell(s):
                    if s is None or (isinstance(s, float) and pd.isna(s)):
                        return None
                    txt = str(s)
                    m = re.search(r"['\"]co['\"]\s*:\s*([0-9eE+\-.]+)", txt)
                    if m:
                        try:
                            return float(m.group(1))
                        except Exception:
                            return None
                    return None

                df['_rstoic_co'] = df[rcol].apply(_extract_co_from_rstoic_cell)
                if df['_rstoic_co'].notna().any():
                    co_col = '_rstoic_co'
                    break

    # fallback: look for a numeric column with values inside 0..1 (mole fraction)
    if co_col is None:
        for c in df.columns:
            if pd.api.types.is_numeric_dtype(df[c]):
                vals = df[c].dropna()
                if not vals.empty and vals.between(0, 1).all():
                    co_col = c
                    break

    # detect CO2 feed column (use for scatter x-axis and separate histogram)
    feed_col = None
    for candidate in ['CO2', 'co2', 'CO_2', 'Co2']:
        if candidate in df.columns:
            feed_col = candidate
            break

    # Report / plot reactor CO if available
    if co_col is None:
        print("No reactor-CO column detected in CSV — skipping CO histogram.")
    else:
        ser = df[co_col].dropna().astype(float)
        _print_summary('CO (reactor inlet mole fraction)', ser)
        print('\nCO ASCII histogram:')
        for ln in _ascii_hist(ser.to_numpy(), bins=bins, width=50):
            print(ln)
        png = out_dir / 'co_hist.png'
        plot_and_save_hist(ser.to_numpy(), 'CO (reactor inlet mole fraction)', png, bins=bins, xlabel='CO (mole fraction)')
        print(f"Saved CO histogram to: {png}")

    # Report / plot CO2 feed if available
    if feed_col is not None:
        ser_feed = pd.to_numeric(df[feed_col].dropna(), errors='coerce')
        if not ser_feed.empty:
            _print_summary('CO2 feed', ser_feed)
            print('\nCO2 feed ASCII histogram:')
            for ln in _ascii_hist(ser_feed.to_numpy(), bins=bins, width=50):
                print(ln)
            png = out_dir / 'co2_hist.png'
            plot_and_save_hist(ser_feed.to_numpy(), 'CO2 feed', png, bins=bins, xlabel='CO2 (kmol/hr)')
            print(f"Saved CO2 histogram to: {png}")

    # detect product columns: numeric columns excluding CO (reactor mole-fraction), CO2 feed, run/status/debug fields
    exclude = {co_col, feed_col, 'run_index', 'status', 'debug_file', None}
    product_cols = [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]

    if not product_cols:
        print('\nNo numeric product columns detected (nothing to plot).')
        return

    print('\nDetected product columns: ' + ', '.join(product_cols))
    for c in product_cols:
        ser = df[c].dropna().astype(float)

        # determine pretty title + units for known products
        low = c.lower()
        if 'kero' in low or 'keros' in low:
            pretty = 'Kerosene Product'
            xlabel_unit = 'Kerosene Product (kmol/hr)'
        elif 'naph' in low or 'nap' in low:
            pretty = 'Naphtha Product'
            xlabel_unit = 'Naphtha Product (kmol/hr)'
        elif 'co2' in low:
            pretty = 'CO2 feed'
            xlabel_unit = 'CO2 (kmol/hr)'
        else:
            pretty = c.capitalize()
            xlabel_unit = f"{pretty} (kmol/hr)"

        _print_summary(pretty, ser)
        print(f'\nASCII histogram for {pretty}:')
        for ln in _ascii_hist(ser.to_numpy(), bins=bins, width=50):
            print(ln)
        png = out_dir / f'{c}_hist.png'
        plot_and_save_hist(ser.to_numpy(), pretty, png, bins=bins, xlabel=xlabel_unit)
        print(f"Saved {c} histogram to: {png}")

        # scatter vs reactor CO if available
        if co_col is not None and co_col in df.columns:
            try:
                paired = df[[co_col, c]].dropna()
                if not paired.empty:
                    x = paired[co_col].astype(float).to_numpy()
                    y = paired[c].astype(float).to_numpy()
                    scatter_png = out_dir / f'co_vs_{c}.png'
                    plot_and_save_scatter(x, y, f"CO vs {pretty}", 'CO (mole fraction)', xlabel_unit, scatter_png)
                    print(f"Saved scatter plot: {scatter_png}")
            except Exception:
                pass

        # scatter vs CO2 feed if available
        if feed_col is not None and feed_col in df.columns:
            try:
                paired2 = df[[feed_col, c]].dropna()
                if not paired2.empty:
                    x2 = paired2[feed_col].astype(float).to_numpy()
                    y2 = paired2[c].astype(float).to_numpy()
                    scatter_png2 = out_dir / f'{feed_col}_vs_{c}.png'
                    plot_and_save_scatter(x2, y2, f"CO2 feed vs {pretty}", 'CO2 (kmol/hr)', xlabel_unit, scatter_png2)
                    print(f"Saved scatter plot: {scatter_png2}")
            except Exception:
                pass

    if show_plots:
        # Open each saved PNG (matplotlib) so user can inspect interactively
        import glob
        imgs = list(out_dir.glob('*.png'))
        for p in imgs:
            img = plt.imread(str(p))
            plt.figure(figsize=(6, 4))
            plt.imshow(img)
            plt.axis('off')
        plt.show()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='View batch results: CO + product histograms')
    p.add_argument('--file', type=str, default=str(DEFAULT_CSV), help='Results CSV path')
    p.add_argument('--out-dir', type=str, default=str(DEFAULT_OUTDIR), help='Directory to save PNG histograms')
    p.add_argument('--bins', type=int, default=20, help='Number of histogram bins')
    p.add_argument('--show', action='store_true', help='Also open plots interactively')
    args = p.parse_args()

    view_results(Path(args.file), Path(args.out_dir), bins=args.bins, show_plots=args.show)
