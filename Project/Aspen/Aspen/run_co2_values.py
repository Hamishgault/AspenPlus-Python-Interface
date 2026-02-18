from batch_runner import BatchConfig, BatchRunner

cfg = BatchConfig(visibility=False)
runner = BatchRunner(cfg)

try:
    runner.open()
    vals = [36.0, 38.0, 40.0]
    all_results = []
    for v in vals:
        print(f"--- Running CO2 = {v} kmol/hr ---")
        res = runner.run_case({'CO2': v}, apply_rstoic=True)
        res['CO2'] = v
        print(res)
        all_results.append(res)
finally:
    runner.close()

print('\nBatch finished')