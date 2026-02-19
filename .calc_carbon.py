from pathlib import Path
from CodeLibrary import Simulation

BKP = Path('Project/Aspen/Aspen/FTS copy.bkp').resolve()
print('Opening', BKP)
try:
    sim = Simulation(AspenFileName=str(BKP), WorkingDirectoryPath=str(BKP.parent), VISIBILITY=False)
except Exception as e:
    print('Failed to open Simulation:', e)
    raise

sid = '9-NAPHTA'
outs = sim.STRM_GET_OUTPUTS(sid)
names = outs.get('CompoundNameList', [])
moles = outs.get('MoleFlowList', [])

def carbon_count(name: str) -> int:
    if not name:
        return 0
    n = str(name).upper()
    if n.startswith('C') and len(n) > 1 and n[1:].isdigit():
        try:
            return int(n[1:])
        except Exception:
            return 0
    if n in ('CO', 'CO2', 'CH4', 'MEOH', 'METHANOL'):
        return 1
    return 0

total_carbon_kmol_per_hr = 0.0
if isinstance(names, (list, tuple)) and isinstance(moles, (list, tuple)):
    for nm, mf in zip(names, moles):
        try:
            mfv = float(mf)
        except Exception:
            mfv = 0.0
        total_carbon_kmol_per_hr += mfv * carbon_count(nm)

print(f"Stream {sid} carbon-atom flow = {total_carbon_kmol_per_hr:.6f} kmol/hr")
print('raw totals: total_mole=', sum(float(x) for x in moles))

try:
    sim.Close()
except Exception:
    pass
