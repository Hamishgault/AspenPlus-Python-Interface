from pathlib import Path
from batch_runner import BatchConfig, BatchRunner

# Small interactive diagnostic used while debugging stream control behavior.
cfg = BatchConfig(visibility=True)
runner = BatchRunner(cfg)

try:
    runner.open()
    print('Opened Aspen (visible)')
    assert runner.sim is not None, "Simulation instance not available"
    sim = runner.sim

    # 1) run the normal BatchRunner case (this uses STRM_Set_ComponentFlowRate + tree writes)
    runner.run_case({'CO2': 54.0})

    # helper: safe tree-reader
    def read_node(path: str):
        try:
            node = sim.AspenSimulation.Tree.FindNode(path)
            return None if node is None else node.Value
        except Exception:
            return None

    paths = [
        r"\Data\Streams\1-CO2-MU\Input",
        r"\Data\Streams\1-CO2-MU\Input\TOTFLOW",
        r"\Data\Streams\1-CO2-MU\Input\FLOW\MIXED\CO2",
        r"\Data\Streams\1-CO2-MU\Input\FLOW\MIXED",
        r"\Data\Streams\1-CO2-MU\Output\MOLEFLOW",
        r"\Data\Streams\1-CO2-MU\Output\MOLEFRAC",
    ]

    print('\n--- Tree node snapshot (pre-EngineRun readback) ---')
    for p in paths:
        print(f"{p} -> {read_node(p)}")

    # Structured readback
    outs = sim.STRM_GET_OUTPUTS('1-CO2-MU')
    names = outs.get('CompoundNameList', [])
    moleflows = outs.get('MoleFlowList', None)
    molefracs = outs.get('MoleFracList', None)

    print('\n1-CO2-MU outputs (STRM_GET_OUTPUTS):')
    print('  CompoundNameList:', names)
    print('  MoleFlowList     :', moleflows)
    print('  MoleFracList     :', molefracs)

    # handle possible single-value or list return types safely
    if isinstance(moleflows, (list, tuple)):
        total = float(sum(float(x) for x in moleflows))
    elif moleflows is None:
        total = None
    else:
        total = float(moleflows)
    print('  Total mole flow  :', total)

    # Attempt explicit tree writes (TOTFLOW + FLOW\MIXED\CO2)
    print('\n--- Attempting explicit tree writes (TOTFLOW + FLOW\\MIXED\\CO2) ---')
    tn = sim.AspenSimulation.Tree.FindNode(r"\Data\Streams\1-CO2-MU\Input\TOTFLOW")
    fn = sim.AspenSimulation.Tree.FindNode(r"\Data\Streams\1-CO2-MU\Input\FLOW\MIXED\CO2")
    print('  before write: TOTFLOW=', None if tn is None else tn.Value, ' FLOW\\MIXED\\CO2=', None if fn is None else fn.Value)
    try:
        if tn is not None:
            tn.Value = 54.0
        if fn is not None:
            fn.Value = 54.0
    except Exception as e:
        print('  failed to write tree nodes:', e)
    print('  after write:  TOTFLOW=', None if tn is None else tn.Value, ' FLOW\\MIXED\\CO2=', None if fn is None else fn.Value)

    # Try a consistent spec: set component mole-fraction to 1.0 then TOTFLOW=54
    print('\n--- Trying consistent spec: set FLOW\\MIXED\\CO2 = 1.0 (100%) then TOTFLOW = 54 ---')
    try:
        if fn is not None:
            fn.Value = 1.0
        if tn is not None:
            tn.Value = 54.0
    except Exception as e:
        print('   consistent-spec failed:', e)
    print('   after consistent-write: TOTFLOW=', None if tn is None else tn.Value, ' FLOW\\MIXED\\CO2=', None if fn is None else fn.Value)

    # Read back after writes
    outs2 = sim.STRM_GET_OUTPUTS('1-CO2-MU')
    print('\nImmediate readback after tree writes:')
    print('  MoleFlowList     :', outs2.get('MoleFlowList', []))
    print('  MoleFracList     :', outs2.get('MoleFracList', []))

    # Run engine to surface model-driven overwrites
    try:
        sim.EngineRun()
    except Exception:
        pass
    outs3 = sim.STRM_GET_OUTPUTS('1-CO2-MU')
    print('\nPost-EngineRun readback:')
    print('  MoleFlowList     :', outs3.get('MoleFlowList', []))
    print('  MoleFracList     :', outs3.get('MoleFracList', []))

    # Try writing reactor-inlet TOTFLOW (2-IN-FT) as a workaround and inspect
    print('\n--- Attempt: set reactor-inlet TOTFLOW (2-IN-FT) = 54.0 ---')
    tn2 = sim.AspenSimulation.Tree.FindNode(r"\Data\Streams\2-IN-FT\Input\TOTFLOW")
    print('  before:', None if tn2 is None else tn2.Value)
    try:
        if tn2 is not None:
            tn2.Value = 54.0
            print('  after: ', tn2.Value)
        else:
            print('  node not found (2-IN-FT TOTFLOW)')
    except Exception as e:
        print('  failed to set 2-IN-FT TOTFLOW:', e)

    try:
        outs4 = sim.STRM_GET_OUTPUTS('2-IN-FT')
        print('  2-IN-FT MoleFlowList:', outs4.get('MoleFlowList', []))
        print('  2-IN-FT MoleFracList:', outs4.get('MoleFracList', []))
    except Exception:
        pass

    print('\n--- Done diagnostics ---')
    input('Press Enter to close Aspen...')
finally:
    runner.close()
    print('Closed.')
