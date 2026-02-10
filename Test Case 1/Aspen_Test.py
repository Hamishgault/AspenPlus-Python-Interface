from pathlib import Path
import sys

# ---------------------------------------------------------
# 1. Resolve paths cleanly
# ---------------------------------------------------------

# Folder where THIS script lives
SCRIPT_DIR = Path(__file__).resolve().parent

# Project root = the root of your fork (one level up)
PROJECT_ROOT = SCRIPT_DIR.parent

# Add project root to sys.path so CodeLibrary can be imported
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------
# 2. Import the Simulation class
# ---------------------------------------------------------
from CodeLibrary import Simulation

# ---------------------------------------------------------
# 3. Point to your Aspen file
# ---------------------------------------------------------
aspen_file = SCRIPT_DIR / "MEOH.bkp"

# ---------------------------------------------------------
# 4. Launch Aspen
# ---------------------------------------------------------
sim = Simulation(
    AspenFileName=str(aspen_file),
    WorkingDirectoryPath=str(PROJECT_ROOT),
    VISIBILITY=False,
)

BLOCK_NAME = "PFR"


def list_block_names(sim):
    blocks = sim.AspenSimulation.Tree.Elements("Data").Elements("Blocks")
    names = []
    try:
        count = blocks.Elements.Count
    except Exception:
        return names
    for i in range(1, count + 1):
        try:
            names.append(blocks.Elements.Item(i).Name)
        except Exception:
            continue
    return names

def set_temperature_profile(sim, temps):
    for i, T in enumerate(temps, start=1):
        path = fr"\Data\Blocks\{BLOCK_NAME}\Input\SPEC_TEMP\#{i}"
        node = sim.AspenSimulation.Tree.FindNode(path)
        if node is None:
            blocks = list_block_names(sim)
            raise RuntimeError(
                f"Aspen path not found: {path}. Check block name and input path. "
                f"Available blocks: {blocks}"
            )
        node.Value = float(T)


def get_temperature_profile(sim):
    profile = []
    for i in range(1, 50):  # discover available points
        path = fr"\Data\Blocks\{BLOCK_NAME}\Input\SPEC_TEMP\#{i}"
        node = sim.AspenSimulation.Tree.FindNode(path)
        if node is None:
            if i == 1:
                blocks = list_block_names(sim)
                raise RuntimeError(
                    f"Aspen path not found: {path}. Check block name and input path. "
                    f"Available blocks: {blocks}"
                )
            break
        val = node.Value
        profile.append(val)
    return profile


# --- MAIN TEST -----------------------------------------------------

# 1. Read the baseline profile
baseline = get_temperature_profile(sim)

# 2. Create modified profiles
plus30  = [T + 30 for T in baseline]
minus30 = [T - 30 for T in baseline]

profiles_to_test = {
    "baseline": baseline,
    "plus30": plus30,
    "minus30": minus30,
}

results = {}

for label, temps in profiles_to_test.items():
    print(f"\nRunning profile: {label}")

    # Set the temperature profile
    set_temperature_profile(sim, temps)

    # Run Aspen
    sim.Run()

    # Extract a few example outputs via the library
    outputs = sim.BLK_RPLUG_GET_OUTPUTS(BLOCK_NAME)
    Tmax = outputs.get("MaximumReactorTemperature")
    heat_duty = outputs.get("Heatduty")

    results[label] = {
        "Max_Temperature": Tmax,
        "Heat_Duty": heat_duty,
    }

    print(f"{label}: Tmax = {Tmax}, Heat duty = {heat_duty}")

print("\nAll results:")
print(results)