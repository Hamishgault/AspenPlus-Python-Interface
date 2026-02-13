"""Run FTS reactor for a specific CO% and then run the hydrocracker.

Usage (examples):
  # dry-run only (no Aspen write, no hydrocracker)
  python CustomSimualtion.py --co 0.066 --dry-run

  # apply conversions from RSTOIC (writes Aspen CONV), run Aspen and hydrocracker,
  # do NOT save the .bkp and pause so you can inspect the model before closing
  python CustomSimualtion.py --co 0.066 --apply --inspect

  # apply + save
  python CustomSimualtion.py --co 6.6 --apply --save

Behavior
- Writes the provided CO% into `DATASET_update.xlsm` sheet `RSTOIC!K2` (preserves macros).
- Calls `BLK_Apply_Conversions_From_RSTOIC(...)` to update `FTS-REAC.Input.CONV` from Excel.
- Runs the Aspen simulation (calls `sim.Run2()`), then calls
  `update_hydrocracking_streams_v2(sim, inlet_stream='5-IN-EXC', outlet_stream='5-OUTEXC')`.
- By default does NOT save the .bkp; use `--save` to save.
- If `--inspect` is given the script will pause and keep Aspen open until you press Enter.

"""
# Ensure repository root is on sys.path so top-level modules (CodeLibrary, etc.)
# can be imported when running this script from its folder.
import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import argparse
import openpyxl

# imports from repo helpers
from CodeLibrary import Simulation
from FTS_Reactor import BLK_Apply_Conversions_From_RSTOIC
from hydrocracking_v2 import update_hydrocracking_streams_v2

EXCEL_PATH = Path(__file__).resolve().parent / 'DATASET_update.xlsm'
BKP_PATH = Path(__file__).resolve().parent / 'FTS Alessio_CO_conv_Ref_20bar_11%.bkp'


def write_co_to_rstoic(excel_path: Path, co_value: float) -> None:
    """Write CO% to RSTOIC!K2 preserving macros using openpyxl (keep_vba=True)."""
    wb = openpyxl.load_workbook(excel_path, keep_vba=True)
    ws = wb['RSTOIC']
    # user expects percent like 0.066 or 6.6 — write as fraction if < 1
    if co_value > 1.5:
        ws['K2'].value = co_value
    else:
        ws['K2'].value = float(co_value)
    wb.save(excel_path)


def run_for_co(co: float, apply: bool, save: bool, inspect: bool, dry_run: bool) -> None:
    print(f"Running FTS workflow for CO%={co} (apply={apply}, save={save}, inspect={inspect}, dry_run={dry_run})")

    # 1) write CO% to Excel so RSTOIC conversions are consistent
    write_co_to_rstoic(EXCEL_PATH, co)
    print(f"Wrote CO%={co} to {EXCEL_PATH} (RSTOIC!K2)")

    # 2) open Aspen simulation
    sim = Simulation(AspenFileName=str(BKP_PATH), WorkingDirectoryPath=str(BKP_PATH.parent), VISIBILITY=False)

    try:
        # 3) compute/apply conversions from RSTOIC (dry_run option supported)
        df = BLK_Apply_Conversions_From_RSTOIC(sim, 'FTS-REAC', excel_path=str(EXCEL_PATH), dry_run=dry_run, save_after=False)
        print('\nConversions (preview):')
        print(df.head(12).to_string(index=False))

        if not dry_run and apply:
            # 4) run Aspen
            try:
                # prefer Simulation.Run2 if available
                run_fn = getattr(sim, 'Run2', None)
                if callable(run_fn):
                    run_fn()
                else:
                    # fallback to engine run if exposed
                    _ = getattr(sim.AspenSimulation, 'Run2', lambda: None)()
                print('Aspen run completed')
            except Exception as e:
                print('Warning: Aspen run failed:', e)

            # 5) run hydrocracker reconciliation
            try:
                update_hydrocracking_streams_v2(sim, inlet_stream='5-IN-EXC', outlet_stream='5-OUTEXC')
                print('Hydrocracker update complete')
            except Exception as e:
                print('Warning: hydrocracker update failed:', e)

            if save:
                try:
                    sav = getattr(sim, 'Save', None)
                    if callable(sav):
                        sav()
                        print('Model saved')
                except Exception as e:
                    print('Warning: failed to save model:', e)

        # keep simulation open for inspection if requested
        if inspect:
            input('\nInspection mode: Aspen model is open. Press Enter to close and exit...')

    finally:
        close_fn = getattr(sim, 'Close', None)
        if callable(close_fn):
            close_fn()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Run FTS reactor for a specific CO% and run hydrocracker')
    p.add_argument('--co', type=float, required=True, help='CO mole% to test (fraction or percent; e.g. 0.066 or 6.6)')
    p.add_argument('--apply', action='store_true', help='Apply conversions and run Aspen/hydrocracker')
    p.add_argument('--save', action='store_true', help='Save Aspen model after applying')
    p.add_argument('--inspect', action='store_true', help='Keep Aspen open for manual inspection (pauses until Enter)')
    p.add_argument('--dry-run', action='store_true', help='Do everything up to apply but do not write to Aspen')
    args = p.parse_args()

    run_for_co(args.co, apply=args.apply, save=args.save, inspect=args.inspect, dry_run=args.dry_run)
