from batch_runner import BatchConfig, BatchRunner


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
    runner.sim = fake

    res = runner.run_case({'CO2': 54.0})

    # component call recorded
    assert ('component', '1-CO2-MU', 54.0, 'CO2') in fake.calls

    # we should NOT be required to set TOTFLOW for the CO2 feed (component-driven)
    assert not any(c for c in fake.calls if c[0] == 'total' and c[1] == '1-CO2-MU')

    # run_case should not report a total-mismatch warning for CO2
    assert '_warn_set_CO2_total_mismatch' not in res
    # component readback should match the requested flow
    assert '_warn_set_CO2_component_mismatch' not in res
