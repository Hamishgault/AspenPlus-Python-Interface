#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Apr 15 11:41:40 2026

@author: Alessio
"""

import numpy as np
import matplotlib.pyplot as plt

def compute_asf_distribution(alpha_values: np.ndarray, carbon_numbers: np.ndarray) -> np.ndarray:
    """Return ASF mass fraction matrix with shape (len(alpha_values), len(carbon_numbers))."""
    w = np.zeros((len(alpha_values), len(carbon_numbers)), dtype=float)
    positive_mask = carbon_numbers >= 1

    a = alpha_values[:, None]
    c = carbon_numbers[positive_mask][None, :]
    w[:, positive_mask] = c * (1 - a) ** 2 * a ** (c - 1)

    return w


def grouped_fractions(w: np.ndarray, carbon_numbers: np.ndarray) -> dict:
    """Compute grouped product fractions from the ASF matrix."""
    mask_c1 = carbon_numbers == 1
    mask_c2_4 = (carbon_numbers >= 2) & (carbon_numbers <= 4)
    mask_c5_11 = (carbon_numbers >= 5) & (carbon_numbers <= 11)
    mask_c12_20 = (carbon_numbers >= 12) & (carbon_numbers <= 20)
    mask_c21_plus = carbon_numbers >= 21
    mask_kero = (carbon_numbers >= 6) & (carbon_numbers <= 16)

    return {
        r"$C_1$": np.sum(w[:, mask_c1], axis=1),
        r"$C_2$-$C_4$": np.sum(w[:, mask_c2_4], axis=1),
        r"$C_5$-$C_{11}$": np.sum(w[:, mask_c5_11], axis=1),
        r"$C_{12}$-$C_{20}$": np.sum(w[:, mask_c12_20], axis=1),
        r"$C_{21+}$": np.sum(w[:, mask_c21_plus], axis=1),
        r"Kero ($C_6$-$C_{16}$)": np.sum(w[:, mask_kero], axis=1),
    }


def smooth_series(y: np.ndarray, window: int = 3) -> np.ndarray:
    """Apply light moving-average smoothing while preserving endpoints."""
    if window <= 1:
        return y
    kernel = np.ones(window, dtype=float) / window
    y_smooth = np.convolve(y, kernel, mode="same")
    y_smooth[0] = y[0]
    y_smooth[-1] = y[-1]
    return y_smooth


def main() -> None:
    # Parameter definitions
    alpha = np.arange(0, 1.001, 0.001)
    carbon_numbers = np.arange(0, 26)

    # Compute full ASF matrix (vectorized)
    w = compute_asf_distribution(alpha, carbon_numbers)
    groups = grouped_fractions(w, carbon_numbers)

    # Alpha values to compare directly on the product distribution curve.
    alpha_samples = np.array([0.30, 0.50, 0.70, 0.90])
    sample_idx = [np.argmin(np.abs(alpha - a)) for a in alpha_samples]

    # 16:9 PowerPoint slide is typically 13.33 in x 7.5 in.
    # Use one-third width and full height for this figure.
    fig, axes = plt.subplots(2, 1, figsize=(13.33 / 3, 7.5), sharex=False)

    # Left: grouped fractions as a function of alpha.
    for label, values in groups.items():
        axes[0].plot(alpha, values, label=label, linewidth=2)
    axes[0].set_xlabel("Alpha (-)")
    axes[0].set_ylabel("Mass Fraction (-)")
    axes[0].set_title("Grouped Product Fractions vs Alpha")
    axes[0].minorticks_on()
    axes[0].legend(framealpha=0.35)

    # Right: full product distribution for selected alpha values.
    for idx in sample_idx:
        a_val = alpha[idx]
        y_raw = w[idx, :]
        y_plot = smooth_series(y_raw, window=3)
        axes[1].plot(
            carbon_numbers,
            y_plot,
            linewidth=2,
            label=f"alpha={a_val:.2f}",
        )
    axes[1].set_xlabel("Carbon Number (-)")
    axes[1].set_ylabel("Mass Fraction at Carbon Number (-)")
    axes[1].set_title("Shift in Product Distribution with Alpha")
    axes[1].set_xlim(0, 25)
    axes[1].set_xticks(np.arange(0, 26, 5))
    axes[1].set_xticks(np.arange(0, 26, 1), minor=True)
    axes[1].tick_params(which="minor", length=3)
    axes[1].legend(framealpha=0.35)

    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()