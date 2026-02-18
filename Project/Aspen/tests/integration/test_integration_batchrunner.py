"""Consolidated integration tests for BatchRunner & CustomSimualtion.

These tests are marked `integration` and are skipped by default; run with
`pytest -m integration` or `pytest --run-integration`.
"""
import pytest
pytestmark = pytest.mark.integration

from batch_runner import BatchConfig, BatchRunner
from typing import Any, cast

# ---- Fake sim for CO2 sweep + BatchRunner workflow ------------------------
class FakeSimSimple:
    def __init__(self):
        self.streams = {'1-CO2-MU': {'CO2': 38.0}}
        self.calls = []

    def STRM_Set_ComponentFlowRate(self, stream, value, comp):
        self.calls.append(('component', stream, float(value), comp))
        self.streams.setdefault(stream, {})[comp] = float(value)

    def STRM_GET_OUTPUTS(self, stream_name: str):
        if stream_name == '1-CO2-MU':
            names = ['CO2']
            flows = [float(self.streams.get('1-CO2-MU', {}).get('CO2', 38.0))]
            fracs = [1.0 if sum(flows) > 0 else 0.0]
            return {'CompoundNameList': names, 'MoleFlowList': flows, 'MoleFracList': fracs}
        if stream_name == '9-NAPHTA':
            return {'MoleFlowList': [2.0]}
        if stream_name == '9-KERO':
            return {'MoleFlowList': [1.0]}
        return {'CompoundNameList': [], 'MoleFlowList': []}

    def EngineRun(self):
        self.calls.append(('EngineRun',))


def test_run_co2_sweep_applies_rstoic_and_collects(monkeypatch):
    cfg = BatchConfig(visibility=False, hydrocracker=False)
    runner = BatchRunner(cfg)
    fake = FakeSimSimple()
    runner.sim = cast(Any, fake)

    called = {'ok': False}

    def fake_iter(sim, **kwargs):
        called['ok'] = True
        return {'co': 0.05, 'iterations': 2, 'converged': True}

    monkeypatch.setattr('batch_runner.iterate_rstoic_until_converged', fake_iter)

    results = runner.run_co2_sweep([40.0])

    assert called['ok'] is True
    assert isinstance(results, list) and len(results) == 1
    row = results[0]
    assert '_rstoic_iter' in row
    assert row.get('naphtha') == 2.0
    assert row.get('kero') == 1.0


# ---- Fake sim for component-flow unit behaviors --------------------------
class FakeSim:
    def __init__(self):
        self.calls = []
        # default baseline
        self.streams = {'1-CO2-MU': {'CO2': 38.0, 'H2': 0.0}}

    def STRM_Set_ComponentFlowRate(self, stream, value, comp):
        self.calls.append(('component', stream, float(value), comp))
        self.streams.setdefault(stream, {})[comp] = float(value)

    def STRM_Set_TotalFlowRate(self, stream, value):
        # record but do not alter component-driven behavior
        self.calls.append(('total', stream, float(value)))

    def STRM_GET_OUTPUTS(self, stream_name: str):
        if stream_name == '1-CO2-MU':
            names = ['CO2', 'H2']
            co = float(self.streams.get('1-CO2-MU', {}).get('CO2', 38.0))
            flows = [co, 0.0]
            fracs = [1.0 if sum(flows) > 0 else 0.0, 0.0]
            return {'CompoundNameList': names, 'MoleFlowList': flows, 'MoleFracList': fracs}
        if stream_name == '9-NAPHTA':
            return {'MoleFlowList': [2.0]}
        if stream_name == '9-KERO':
            return {'MoleFlowList': [1.0]}
        return {'CompoundNameList': [], 'MoleFlowList': []}

    def EngineRun(self):
        pass


def test_run_case_sets_component_flow_and_not_totflow():
    cfg = BatchConfig(visibility=False)
    runner = BatchRunner(cfg)
    fake = FakeSim()
    runner.sim = cast(Any, fake)

    res = runner.run_case({'CO2': 54.0})

    # component call recorded
    assert ('component', '1-CO2-MU', 54.0, 'CO2') in fake.calls

    # we should NOT be required to set TOTFLOW for the CO2 feed (component-driven)
    assert not any(c for c in fake.calls if c[0] == 'total' and c[1] == '1-CO2-MU')

    # run_case should not report a total-mismatch warning for CO2
    assert '_warn_set_CO2_total_mismatch' not in res
    # component readback should match the requested flow
    assert '_warn_set_CO2_component_mismatch' not in res


# ---- Fake sim for fallback behavior -------------------------------------
class FakeSimFallback:
    def __init__(self):
        self.calls = []
        # initial values: 1-CO2-MU reports lower than what's requested
        self.streams = {
            '1-CO2-MU': {'CO2': 36.0},
            '2-IN-FT': {'CO2': 0.0},
            '5-IN-EXC': {'CO2': 0.0},
        }

    def STRM_Set_ComponentFlowRate(self, stream, value, comp):
        # record the attempt
        self.calls.append(('component', stream, float(value), comp))
        # simulate that writes to 1-CO2-MU are ignored (no change)
        if stream != '1-CO2-MU':
            self.streams.setdefault(stream, {})[comp] = float(value)

    def STRM_GET_OUTPUTS(self, stream_name: str):
        val = self.streams.get(stream_name, {})
        co = float(val.get('CO2', 0.0))
        return {'CompoundNameList': ['CO2'], 'MoleFlowList': [co], 'MoleFracList': [1.0 if co>0 else 0.0]}

    def EngineRun(self):
        pass


def test_fallback_writes_to_inlet_or_reactor_inlet():
    cfg = BatchConfig(visibility=False)
    runner = BatchRunner(cfg)
    fake = FakeSimFallback()
    runner.sim = cast(Any, fake)

    res = runner.run_case({'CO2': 40.0})

    # primary stream was attempted
    assert ('component', '1-CO2-MU', 40.0, 'CO2') in fake.calls

    # fallback should have been attempted on a candidate stream
    assert ('component', '2-IN-FT', 40.0, 'CO2') in fake.calls or ('component', cfg.inlet_stream, 40.0, 'CO2') in fake.calls
    # ensure one of the fallback streams shows the requested value in the fake sim
    assert fake.streams['2-IN-FT']['CO2'] == 40.0 or fake.streams[cfg.inlet_stream]['CO2'] == 40.0
    # result should record which candidate succeeded (best-effort)
    assert any(k.startswith('_fixed_set_') for k in res.keys())


# ---- CustomSimualtion iterate_rstoic test (uses a small fake response sim) --
import importlib.util
import pathlib

# load CustomSimualtion from the package folder by file path (avoid importing package __init__)
_mod_dir = pathlib.Path(__file__).resolve().parents[2] / 'Aspen'
_mod_path = _mod_dir / 'CustomSimualtion.py'
import sys
if str(_mod_dir) not in sys.path:
    sys.path.insert(0, str(_mod_dir))

_spec = importlib.util.spec_from_file_location('CustomSimualtion', _mod_path)
CustomSimualtion = importlib.util.module_from_spec(_spec)
_loader = getattr(_spec, 'loader', None)
_loader.exec_module(CustomSimualtion)

iterate_rstoic_until_converged = CustomSimualtion.iterate_rstoic_until_converged


class FakeSimResponses:
    def __init__(self, stream_responses):
        self._responses = list(stream_responses)
        self.run_count = 0

    def Run2(self):
        self.run_count += 1

    def STRM_GET_OUTPUTS(self, stream_name: str):
        if not self._responses:
            return {"CompoundNameList": [], "MoleFlowList": []}
        return self._responses.pop(0)


def make_stream(co_molefrac: float):
    total = 10.0
    co_flow = co_molefrac * total
    h2_flow = total - co_flow
    return {"CompoundNameList": ["CO", "H2"], "MoleFlowList": [co_flow, h2_flow]}


def test_iterate_rstoic_converges(monkeypatch):
    responses = [
        make_stream(0.0),
        make_stream(0.05),
        make_stream(0.05),
        make_stream(0.050000003),
    ]

    sim = FakeSimResponses(responses)

    written = []

    def fake_write_co(path, value):
        written.append(float(value))

    monkeypatch.setattr(CustomSimualtion, 'write_co_to_rstoic', fake_write_co)

    def fake_blk_apply(sim_arg, blockname, excel_path, dry_run, save_after=False):
        import pandas as pd
        return pd.DataFrame([{'reaction': 1, 'source': 'CO', 'conversion': 0.1}])

    monkeypatch.setattr(CustomSimualtion, 'BLK_Apply_Conversions_From_RSTOIC', fake_blk_apply)

    res = iterate_rstoic_until_converged(sim, reactor_inlet_stream='2-IN-FT', blockname='FTS-REAC', dry_run=True)

    assert res['converged'] is True
    assert res['iterations'] == 2
    assert abs(res['co'] - 0.050000003) < 1e-7

    assert len(written) >= 2
    assert abs(written[0] - 0.0) < 1e-12
    assert abs(written[1] - 0.05) < 1e-12