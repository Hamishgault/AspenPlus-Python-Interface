import importlib.util
import pathlib
import pandas as pd

# load CustomSimualtion from the package folder by file path (avoid importing package __init__)
_mod_dir = pathlib.Path(__file__).resolve().parent / 'Aspen'
_mod_path = _mod_dir / 'CustomSimualtion.py'
# ensure the module's directory is on sys.path so absolute imports inside it (e.g. FTS_Reactor)
import sys
if str(_mod_dir) not in sys.path:
    sys.path.insert(0, str(_mod_dir))

_spec = importlib.util.spec_from_file_location('CustomSimualtion', _mod_path)
CustomSimualtion = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CustomSimualtion)

iterate_rstoic_until_converged = CustomSimualtion.iterate_rstoic_until_converged


class FakeSim:
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

    sim = FakeSim(responses)

    written = []

    def fake_write_co(path, value):
        written.append(float(value))

    monkeypatch.setattr(CustomSimualtion, 'write_co_to_rstoic', fake_write_co)

    def fake_blk_apply(sim_arg, blockname, excel_path, dry_run, save_after=False):
        return pd.DataFrame([{'reaction': 1, 'source': 'CO', 'conversion': 0.1}])

    monkeypatch.setattr(CustomSimualtion, 'BLK_Apply_Conversions_From_RSTOIC', fake_blk_apply)

    res = iterate_rstoic_until_converged(sim, reactor_inlet_stream='2-IN-FT', blockname='FTS-REAC', dry_run=True)

    assert res['converged'] is True
    assert res['iterations'] == 2
    assert abs(res['co'] - 0.050000003) < 1e-7

    assert len(written) >= 2
    assert abs(written[0] - 0.0) < 1e-12
    assert abs(written[1] - 0.05) < 1e-12