from pathlib import Path
from CodeLibrary import Simulation
p = Path('Project/Aspen/Aspen/FTS copy.bkp').resolve()
print('Opening', p)
sim = Simulation(AspenFileName=str(p), WorkingDirectoryPath=str(p.parent), VISIBILITY=False)
print('EngineRun()')
sim.EngineRun()
for s in ['1-H2O-MU','1-CO2-MU','2-IN-FT','9-KERO','9-NAPHTA']:
    try:
        outs = sim.STRM_GET_OUTPUTS(s)
    except Exception as e:
        print(s,'-> STRM_GET_OUTPUTS failed:', type(e).__name__, e)
        continue
    print('\nStream:',s)
    for k in ('CompoundNameList','MoleFlowList','MoleFracList','MassFlowList','MassFracList'):
        print('  ',k,':', type(outs.get(k)).__name__)
    print('  keys:', list(outs.keys())[:10])
print('CLOSING')
try:
    sim.Close()
except Exception:
    pass