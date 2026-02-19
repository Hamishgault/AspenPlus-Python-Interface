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
