from pathlib import Path
from CodeLibrary import Simulation
from Aspen.CustomSimualtion import iterate_rstoic_until_converged
from Aspen.hydrocracking_v2 import update_hydrocracking_streams_v2

bkp = Path('Project/Aspen/Aspen/FTS copy.bkp').resolve()
print('Opening', bkp)
sim = Simulation(AspenFileName=str(bkp), WorkingDirectoryPath=str(bkp.parent), VISIBILITY=False)

try:
    print('Set H2O -> 1500 on 1-H2O-MU')
    sim.STRM_Set_ComponentFlowRate('1-H2O-MU', 1500.0, 'H2O')
    print('EngineRun()')
    sim.EngineRun()

    print('\nRunning iterate_rstoic_until_converged...')
    r = iterate_rstoic_until_converged(sim, reactor_inlet_stream='2-IN-FT', dry_run=False, run_after_apply=True, verbose=True)
    print('\nRSTOIC result:', r)

    print('\nAttempt hydrocracker reconciliation...')
    try:
        update_hydrocracking_streams_v2(sim, inlet_stream='2-IN-FT', outlet_stream='9-OUT')
        print('Hydrocracker succeeded')
    except Exception as e:
        print('Hydrocracker exception:', type(e).__name__, e)

    def dump_stream(sid):
        print('\n--- STREAM:', sid, '---')
        try:
            outs = sim.STRM_GET_OUTPUTS(sid)
        except Exception as e:
            print(' STRM_GET_OUTPUTS failed:', type(e).__name__, e)
            return
        for k, v in outs.items():
            if isinstance(v, (list, tuple)):
                print(f'  {k}: list(len={len(v)}) sample=', v[:8])
            else:
                print(f'  {k}:', v)

    for s in ('2-IN-FT', '9-KERO', '9-NAPHTA', '1-H2O-MU'):
        dump_stream(s)

finally:
    try:
        sim.Close()
    except Exception:
        pass
    print('\nDone')
