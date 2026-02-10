from pathlib import Path
import sys
from typing import Dict, List, Tuple
import random
import csv
import json

import numpy as np

import matplotlib.pyplot as plt

# ---------------------------------------------------------
# 1. Resolve paths cleanly
# ---------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from CodeLibrary import Simulation

# ---------------------------------------------------------
# 2. Configuration
# ---------------------------------------------------------
ASPEN_FILE = SCRIPT_DIR / "MEOH.bkp"
BLOCK_NAME = "PFR"  # change if your reactor block name differs
NUM_SAMPLES = 50
TEMP_STD = 10.0  # standard deviation for random temperature perturbation (°C)
RANDOM_SEED = 42
SMOOTH_WINDOW = 3  # moving average window for profile smoothing
TEMP_MIN = 700.0
TEMP_MAX = 1100.0
TOP_N_COMPOUNDS = 12  # reduce clutter on plots; set None to show all
RESULTS_CSV = SCRIPT_DIR / "composition_samples.csv"
RESULTS_JSON = SCRIPT_DIR / "composition_samples.json"
USE_SAVED_RESULTS = False
ONLY_CONVERGED = False


def list_stream_names(sim) -> List[str]:
    streams = sim.AspenSimulation.Tree.Elements("Data").Elements("Streams")
    names = []
    try:
        count = streams.Elements.Count
    except Exception:
        return names
    for i in range(1, count + 1):
        try:
            names.append(streams.Elements.Item(i).Name)
        except Exception:
            continue
    return names


def find_reactor_outlet_stream(sim, block_name: str) -> str:
    for stream_name in list_stream_names(sim):
        try:
            outputs = sim.STRM_GET_OUTPUTS(stream_name)
        except Exception:
            continue
        if outputs.get("Source") == block_name:
            return stream_name
    raise RuntimeError(
        f"No outlet stream found for block '{block_name}'. "
        f"Available streams: {list_stream_names(sim)}"
    )


def get_stream_composition(sim, stream_name: str) -> Tuple[List[str], List[float]]:
    outputs = sim.STRM_GET_OUTPUTS(stream_name)
    names = outputs.get("CompoundNameList", [])
    mole_fracs = outputs.get("MoleFracList", [])
    if not names or not mole_fracs:
        raise RuntimeError(
            f"Stream '{stream_name}' has no composition data. Check the stream name and run status."
        )
    return names, mole_fracs


def plot_composition_distributions(compounds: List[str], samples: List[List[float]]) -> None:
    # samples: list of mole-frac lists, one per run
    if TOP_N_COMPOUNDS is not None and len(compounds) > TOP_N_COMPOUNDS:
        means = [sum(vals[i] for vals in samples) / len(samples) for i in range(len(compounds))]
        top_idx = sorted(range(len(compounds)), key=lambda i: means[i], reverse=True)[:TOP_N_COMPOUNDS]
        compounds = [compounds[i] for i in top_idx]
        samples = [[vals[i] for i in top_idx] for vals in samples]

    # Transpose to get per-compound distributions
    per_compound = list(map(list, zip(*samples)))

    plt.figure(figsize=(12, 6))
    plt.boxplot(per_compound, tick_labels=compounds, showfliers=False)
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Mole Fraction")
    plt.title("Reactor outlet composition across random temperature samples")
    plt.tight_layout()
    plt.show()


def set_temperature_profile(sim, temps: List[float]) -> None:
    for i, T in enumerate(temps, start=1):
        path = fr"\Data\Blocks\{BLOCK_NAME}\Input\SPEC_TEMP\#{i}"
        node = sim.AspenSimulation.Tree.FindNode(path)
        if node is None:
            raise RuntimeError(f"Aspen path not found: {path}. Check block name and input path.")
        node.Value = float(T)


def get_temperature_profile(sim) -> List[float]:
    profile: List[float] = []
    for i in range(1, 50):
        path = fr"\Data\Blocks\{BLOCK_NAME}\Input\SPEC_TEMP\#{i}"
        node = sim.AspenSimulation.Tree.FindNode(path)
        if node is None:
            if i == 1:
                raise RuntimeError(f"Aspen path not found: {path}. Check block name and input path.")
            break
        profile.append(node.Value)
    return profile


def smooth_profile(profile: List[float], window: int) -> List[float]:
    if window <= 1:
        return profile
    arr = np.array(profile, dtype=float)
    kernel = np.ones(window) / window
    padded = np.pad(arr, (window // 2, window - 1 - window // 2), mode="edge")
    smoothed = np.convolve(padded, kernel, mode="valid")
    return smoothed.tolist()


def generate_smooth_random_profile(baseline: List[float]) -> List[float]:
    noise = np.random.normal(0.0, TEMP_STD, size=len(baseline))
    perturbed = (np.array(baseline, dtype=float) + noise).tolist()
    smoothed = smooth_profile(perturbed, SMOOTH_WINDOW)
    bounded = [min(max(t, TEMP_MIN), TEMP_MAX) for t in smoothed]
    return bounded


def load_samples_from_csv(csv_path: Path) -> Tuple[List[str], List[List[float]], List[bool]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Results file not found: {csv_path}")

    with csv_path.open("r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)

        # Identify where compound columns start
        compound_start = None
        for i, col in enumerate(header):
            if col not in ("sample_index", "converged") and not col.startswith("T#"):
                compound_start = i
                break
        if compound_start is None:
            raise RuntimeError("Could not detect compound columns in CSV header.")

        compounds = header[compound_start:]
        samples: List[List[float]] = []
        converged_flags: List[bool] = []

        for row in reader:
            if not row:
                continue
            converged = bool(int(row[1]))
            mole_fracs = [float(v) for v in row[compound_start:]]
            samples.append(mole_fracs)
            converged_flags.append(converged)

    return compounds, samples, converged_flags


def main() -> None:
    if USE_SAVED_RESULTS and RESULTS_CSV.exists():
        compounds, samples, converged_flags = load_samples_from_csv(RESULTS_CSV)
        if ONLY_CONVERGED:
            samples = [s for s, ok in zip(samples, converged_flags) if ok]
        if not samples:
            raise RuntimeError("No samples available after filtering.")
        plot_composition_distributions(compounds, samples)
        return

    sim = Simulation(
        AspenFileName=str(ASPEN_FILE),
        WorkingDirectoryPath=str(PROJECT_ROOT),
        VISIBILITY=False,
    )
    try:
        stream_name = find_reactor_outlet_stream(sim, BLOCK_NAME)

        baseline = get_temperature_profile(sim)
        random.seed(RANDOM_SEED)
        np.random.seed(RANDOM_SEED)

        samples: List[List[float]] = []
        compounds: List[str] = []
        sample_records: List[Dict[str, object]] = []

        for i in range(NUM_SAMPLES):
            temps = generate_smooth_random_profile(baseline)
            set_temperature_profile(sim, temps)
            converged = sim.Run()

            names, mole_fracs = get_stream_composition(sim, stream_name)
            if not compounds:
                compounds = names
            elif names != compounds:
                raise RuntimeError("Compound ordering changed between runs. Cannot plot consistently.")

            samples.append(mole_fracs)

            record = {
                "sample_index": i,
                "converged": bool(converged),
                "temperatures": temps,
                "mole_fractions": mole_fracs,
            }
            sample_records.append(record)

            # Incremental save after each run
            RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
            if i == 0:
                with RESULTS_CSV.open("w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["sample_index", "converged"] + [f"T#{j+1}" for j in range(len(temps))] + compounds)
            with RESULTS_CSV.open("a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([i, int(converged)] + temps + mole_fracs)

        # Save JSON summary
        RESULTS_JSON.write_text(
            json.dumps(
                {
                    "compounds": compounds,
                    "samples": sample_records,
                },
                indent=2,
            )
        )

        plot_composition_distributions(compounds, samples)
    finally:
        sim.CloseAspen()


if __name__ == "__main__":
    main()
