from pathlib import Path
from batch_runner import BatchConfig, BatchRunner
from Aspen.CustomSimualtion import iterate_rstoic_until_converged

# Configuration: visible Aspen and do NOT auto-save
cfg = BatchConfig(visibility=True, save_each=False)
runner = BatchRunner(cfg)

try:
    runner.open()
    print('Opened Aspen model (visible).')

    # 1) set CO2 feed to 54 kmol/hr and run one case
    params = {'CO2': 54.0}
    print(f"Setting CO2 feed to {params['CO2']} kmol/hr and running...")
    out = runner.run_case(params)
    print('Run result:', out)

    # 2) iterate RSTOIC <-> reactor inlet to converge CO at reactor inlet (applies conversions)
    print('Running RSTOIC ↔ reactor-inlet sync (will apply conversions)')
    res = iterate_rstoic_until_converged(runner.sim, co2_feed_stream='1-CO2-MU', reactor_inlet_stream='2-IN-FT', blockname=runner.cfg.blockname, dry_run=False, run_after_apply=True, verbose=True)
    print('Iteration result:', res)

    # Keep Aspen open so you can inspect it manually
    input('\nSimulation is open in Aspen. Press Enter here to close Aspen and exit script...')

finally:
    print('Closing Aspen...')
    runner.close()
    print('Closed.')
