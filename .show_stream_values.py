from pathlib import Path
from CodeLibrary import Simulation

bkp = Path('Project/Aspen/Aspen/FTS copy.bkp').resolve()
print('Opening', bkp)
sim = Simulation(AspenFileName=str(bkp), WorkingDirectoryPath=str(bkp.parent), VISIBILITY=False)

for sid in ('9-NAPHTA','9-KERO'):
    print('\n--- STREAM:', sid, '---')
    try:
        outs = sim.STRM_GET_OUTPUTS(sid)
    except Exception as e:
        print(' STRM_GET_OUTPUTS failed:', type(e).__name__, e)
        continue
    names = outs.get('CompoundNameList', [])
    mass = outs.get('MassFlowList', [])
    mole = outs.get('MoleFlowList', [])
    print('  components count =', len(names) if isinstance(names,(list,tuple)) else 'scalar')
    if isinstance(names, (list,tuple)):
        for i, nm in enumerate(names):
            m = mass[i] if isinstance(mass,(list,tuple)) and i < len(mass) else None
            f = mole[i] if isinstance(mole,(list,tuple)) and i < len(mole) else None
            print(f"   {i:03d}: {str(nm):20s}  mass={m!s:>14s}  mole={f!s:>12s}")
    else:
        print('  Names scalar:', names)
    # print totals
    try:
        total_mass = sum(float(x) for x in mass) if isinstance(mass,(list,tuple)) else float(mass) if mass is not None else None
    except Exception:
        total_mass = mass
    try:
        total_mole = sum(float(x) for x in mole) if isinstance(mole,(list,tuple)) else float(mole) if mole is not None else None
    except Exception:
        total_mole = mole
    print('  total_mass=', total_mass)
    print('  total_mole=', total_mole)

sim.Close()
print('\nDone')