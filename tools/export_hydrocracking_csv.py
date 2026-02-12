import os
import sys

import win32com.client as win32


def main() -> int:
    xls = r"C:\Users\Hamis\Desktop\Masters Project\Economics Code\AspenPlus-Python-Interface\Project\Aspen\Aspen\hydrocracking.xls"
    if not os.path.exists(xls):
        print(f"Excel file not found: {xls}")
        return 1

    out_dir = os.path.dirname(xls)
    sheets = ["Inlet", "Primary", "Secondary", "Outlet"]

    excel = win32.Dispatch("Excel.Application")
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(xls)
        for name in sheets:
            ws = wb.Worksheets(name)
            csv_path = os.path.join(out_dir, f"{name}.csv")
            ws.SaveAs(csv_path, 6)
    finally:
        try:
            wb.Close(False)
        except Exception:
            pass
        excel.Quit()

    print("CSV export complete:", ", ".join(os.path.join(out_dir, f"{s}.csv") for s in sheets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
