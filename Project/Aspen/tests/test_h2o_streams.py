import importlib.util
import pathlib
import sys

_mod_path = pathlib.Path(__file__).resolve().parents[1] / 'h2o_sweep_runner.py'
_spec = importlib.util.spec_from_file_location('h2o_sweep_runner', _mod_path)
_h2o = importlib.util.module_from_spec(_spec)
_loader = getattr(_spec, 'loader')
sys.modules['h2o_sweep_runner'] = _h2o
_loader.exec_module(_h2o)


def test_stream_total_prefers_mass():
    runner = object.__new__(_h2o.H2OSweepRunner)
    class FakeSim:
        def STRM_GET_OUTPUTS(self, sid):
            return {'MassFlowList': [10.0, 20.0], 'MoleFlowList': [1.0, 2.0]}
    runner.sim = FakeSim()
    assert _h2o.H2OSweepRunner._stream_total(runner, 'any') == 30.0


def test_stream_total_falls_back_to_mole():
    runner = object.__new__(_h2o.H2OSweepRunner)
    class FakeSim2:
        def STRM_GET_OUTPUTS(self, sid):
            return {'MoleFlowList': [1.5, 0.5]}
    runner.sim = FakeSim2()
    assert _h2o.H2OSweepRunner._stream_total(runner, 'any') == 2.0


def test_run_case_includes_mole_flow_keys():
    # ensure run_case exposes mole-flow keys when _stream_details provides them
    runner = object.__new__(_h2o.H2OSweepRunner)

    class FakeSim3:
        def STRM_Set_ComponentFlowRate(self, *a, **k):
            pass
        def EngineRun(self):
            pass
        def STRM_GET_OUTPUTS(self, sid):
            if sid == runner.cfg.kero_node if hasattr(runner, 'cfg') else '9-KERO':
                return {'MassFlowList': [1.0], 'MoleFlowList': [0.5], 'CompoundNameList': ['C1']}
            if sid == runner.cfg.naphtha_node if hasattr(runner, 'cfg') else '9-NAPHTA':
                return {'MassFlowList': [2.0], 'MoleFlowList': [1.0], 'CompoundNameList': ['C1']}
            if sid == '2-IN-FT':
                return {'CompoundNameList': ['CO'], 'MoleFracList': [0.01], 'MoleFlowList': [0.1]}
            return {}

    runner.sim = FakeSim3()
    # minimal cfg required by run_case
    runner.cfg = _h2o.H2OSweepConfig(bkp_name='FTS copy.bkp', visibility=False)

    out = _h2o.H2OSweepRunner.run_case(runner, 1500.0, apply_rstoic=False)
    assert 'kerosene_mole_flow' in out
    assert 'naphtha_mole_flow' in out
    assert out['kerosene_mole_flow'] == 0.5
    assert out['naphtha_mole_flow'] == 1.0
