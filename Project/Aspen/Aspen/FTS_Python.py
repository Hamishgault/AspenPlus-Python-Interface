import os
import sys

WORKDIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(WORKDIR, "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from CodeLibrary import Simulation


def main() -> int:
    workdir = WORKDIR
    bkp_name = "FTS Alessio_CO_conv_Ref_20bar_11%.bkp"
    bkp_path = os.path.join(workdir, bkp_name)

    if not os.path.isfile(bkp_path):
        print(f".bkp file not found: {bkp_path}")
        return 1

    try:
        Simulation(
            AspenFileName=bkp_path,
            WorkingDirectoryPath=workdir,
            VISIBILITY=True,
        )
    except Exception as exc:  # noqa: BLE001 - show COM load failures
        print("Failed to load Aspen Plus .bkp file.")
        print(str(exc))
        return 1

    print("Loaded Aspen Plus case successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
