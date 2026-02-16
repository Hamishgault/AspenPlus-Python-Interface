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
    """Write CO to `RSTOIC!K1`.

    - Accepts either a fraction (e.g. 0.066) or a percentage (e.g. 6.6).
    - Values > 1.5 are interpreted as percent and converted to a fraction.
    - Writes the value into `K1` rounded to two decimal places (e.g. 0.06).
    - If the workbook is locked by Excel, fall back to using COM to set the cell and save.
    """
    # normalize input: accept fraction (0.066) or percent (6.6) and store as fraction
    val = float(co_value)
    if val > 1.5:
        val = val / 100.0
    rounded = round(val, 2)

    # Prefer openpyxl write (keeps VBA) but fall back to Excel COM if file is locked.
    try:
        wb = openpyxl.load_workbook(excel_path, keep_vba=True)
        ws = wb['RSTOIC']
        ws['K1'].value = rounded
        wb.save(excel_path)
        return
    except PermissionError:
        # workbook is likely open/locked by Excel — try COM on Windows
        try:
            import sys
            if sys.platform == 'win32':
                import win32com.client as win32
                xl_path = Path(excel_path).resolve()
                excel = None
                try:
                    excel = win32.DispatchEx('Excel.Application')
                except Exception:
                    excel = win32.Dispatch('Excel.Application')
                prev_vis = getattr(excel, 'Visible', False)
                prev_alerts = getattr(excel, 'DisplayAlerts', True)
                excel.Visible = False
                excel.DisplayAlerts = False
                wb_xl = None
                try:
                    wb_xl = excel.Workbooks.Open(str(xl_path), UpdateLinks=False)
                    ws_xl = wb_xl.Worksheets('RSTOIC')
                    ws_xl.Range('K1').Value = rounded
                    wb_xl.Save()
                finally:
                    if wb_xl is not None:
                        try:
                            wb_xl.Close(SaveChanges=True)
                        except Exception:
                            pass
                    excel.DisplayAlerts = prev_alerts
                    excel.Visible = prev_vis
                    try:
                        excel.Quit()
                    except Exception:
                        pass
                return
        except Exception as e:
            print('Warning: failed to write CO to Excel via COM fallback:', e)
            raise
    except Exception:
        # re-raise unexpected errors from openpyxl
        raise


def run_for_co(co: float, apply: bool, save: bool, inspect: bool, dry_run: bool) -> None:
    # print CO as percentage for clarity (co is a mole fraction internally)
    print(f"Running FTS workflow for CO={co*100:.6g}% (apply={apply}, save={save}, inspect={inspect}, dry_run={dry_run})")

    # 1) write CO% to Excel so RSTOIC conversions are consistent
    write_co_to_rstoic(EXCEL_PATH, co)
    print(f"Wrote CO%={co} to {EXCEL_PATH} (RSTOIC!K2)")

    # 2) open Aspen simulation
    sim = Simulation(AspenFileName=str(BKP_PATH), WorkingDirectoryPath=str(BKP_PATH.parent), VISIBILITY=True)

    try:
        # 3) compute/apply conversions from RSTOIC (dry_run option supported)
        try:
            df = BLK_Apply_Conversions_From_RSTOIC(sim, 'FTS-REAC', excel_path=str(EXCEL_PATH), dry_run=dry_run, save_after=False)
        except Exception as e:
            # don't fail the whole script on a preview error during dry-run; surface error otherwise
            print('Warning: BLK_Apply_Conversions_From_RSTOIC failed:', e)
            df = None
            if not dry_run:
                raise

        if df is not None:
            print('\nConversions (preview):')
            try:
                print(df.head(12).to_string(index=False))
            except Exception:
                # fallback in case df isn't a typical DataFrame
                print(df)
        else:
            print('No conversions preview available.')

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
    def parse_co(value: str) -> float:
        """Parse CO input as fraction or percent and validate.

        Accepts '0.066', '6.6', or '6.6%'. Returns a mole fraction (0 < x < 1).
        """
        v = str(value).strip()
        if v.endswith('%'):
            v = v[:-1]
        try:
            f = float(v)
        except ValueError:
            raise argparse.ArgumentTypeError("CO must be a number (e.g. 0.066, 6.6, or '6.6%')")
        # treat values > 1.5 as percentage (e.g. 6.6 -> 0.066)
        if f > 1.5:
            f = f / 100.0
        if not (0 < f < 1):
            raise argparse.ArgumentTypeError("CO must be a positive fraction (<1) or a percentage (0-100).")
        return f

    p = argparse.ArgumentParser(description='Run FTS reactor for a specific CO% and run hydrocracker')
    p.add_argument('--co', type=parse_co, required=False, default=None,
                   help="CO mole fraction or percent (e.g. 0.066, 6.6 or '6.6%'). If omitted you will be prompted interactively when running in a terminal.")
    p.add_argument('--apply', action='store_true', help='Apply conversions and run Aspen/hydrocracker')
    p.add_argument('--save', action='store_true', help='Save Aspen model after applying')
    p.add_argument('--inspect', action='store_true', help='Keep Aspen open for manual inspection (pauses until Enter)')
    p.add_argument('--dry-run', action='store_true', help='Do everything up to apply but do not write to Aspen')
    args = p.parse_args()

    # If --co was omitted, prompt the user when running interactively; otherwise fail fast.
    if args.co is None:
        if sys.stdin is not None and sys.stdin.isatty():
            raw = input("CO not provided. Enter CO (e.g. 0.066 or 6.6%): ").strip()
            try:
                args.co = parse_co(raw)
            except argparse.ArgumentTypeError as e:
                p.error(str(e))
        else:
            p.error("--co is required when running non-interactively")

    run_for_co(args.co, apply=args.apply, save=args.save, inspect=args.inspect, dry_run=args.dry_run)
