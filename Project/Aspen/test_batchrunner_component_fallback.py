from batch_runner import BatchConfig, BatchRunner


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
    runner.sim = fake

    res = runner.run_case({'CO2': 40.0})

    # primary stream was attempted
    assert ('component', '1-CO2-MU', 40.0, 'CO2') in fake.calls

    # fallback should have been attempted on a candidate stream
    assert ('component', '2-IN-FT', 40.0, 'CO2') in fake.calls or ('component', cfg.inlet_stream, 40.0, 'CO2') in fake.calls
    # ensure one of the fallback streams shows the requested value in the fake sim
    assert fake.streams['2-IN-FT']['CO2'] == 40.0 or fake.streams[cfg.inlet_stream]['CO2'] == 40.0
    # result should record which candidate succeeded (best-effort)
    assert any(k.startswith('_fixed_set_') for k in res.keys())