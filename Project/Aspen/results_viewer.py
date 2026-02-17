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

    # detect CO column (common names: 'co', 'x_co')
    co_col = None
    for candidate in ['co', 'x_co', 'CO', 'CO%']:
        if candidate in df.columns:
            co_col = candidate
            break
    if co_col is None:
        # fallback: look for a numeric column with values inside 0..1
        for c in df.columns:
            if pd.api.types.is_numeric_dtype(df[c]):
                vals = df[c].dropna()
                if not vals.empty and vals.between(0, 1).all():
                    co_col = c
                    break
    if co_col is None:
        print("No CO column detected in CSV — skipping CO histogram.")
    else:
        ser = df[co_col].dropna().astype(float)
        _print_summary('CO', ser)
        print('\nCO ASCII histogram:')
        for ln in _ascii_hist(ser.to_numpy(), bins=bins, width=50):
            print(ln)
        png = out_dir / 'co_hist.png'
        plot_and_save_hist(ser.to_numpy(), 'CO', png, bins=bins, xlabel='CO (mole fraction)')
        print(f"Saved CO histogram to: {png}")

    # detect product columns: numeric columns excluding co/run/status/debug fields
    exclude = {co_col, 'run_index', 'status', 'debug_file', None}
    product_cols = [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]

    if not product_cols:
        print('\nNo numeric product columns detected (nothing to plot).')
        return

    print('\nDetected product columns: ' + ', '.join(product_cols))
    for c in product_cols:
        if c == co_col:
            continue
        ser = df[c].dropna().astype(float)

        # determine pretty title + units for known products
        low = c.lower()
        if 'kero' in low or 'keros' in low:
            pretty = 'Kerosene Product'
            xlabel_unit = 'Kerosene Product (kmol/hr)'
        elif 'naph' in low or 'nap' in low:
            pretty = 'Naphtha Product'
            xlabel_unit = 'Naphtha Product (kmol/hr)'
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

        # scatter vs CO if CO exists
        if co_col is not None and co_col in df.columns:
            try:
                xvals = df[co_col].dropna().astype(float)
                # align lengths by dropping NA pairs
                paired = df[[co_col, c]].dropna()
                if not paired.empty:
                    x = paired[co_col].astype(float).to_numpy()
                    y = paired[c].astype(float).to_numpy()
                    scatter_name = 'co_vs_' + c
                    scatter_png = out_dir / f'{scatter_name}.png'
                    plot_title = f"CO vs {pretty}"
                    plot_and_save_scatter(x, y, plot_title, 'CO (mole fraction)', xlabel_unit, scatter_png)
                    print(f"Saved scatter plot: {scatter_png}")
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
