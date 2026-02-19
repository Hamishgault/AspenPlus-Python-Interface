import math
import pandas as pd
import importlib.util
import pathlib
import sys

# load h2o_sweep_runner module by path (tests run from repo root)
_mod_path = pathlib.Path(__file__).resolve().parents[1] / 'h2o_sweep_runner.py'
_spec = importlib.util.spec_from_file_location('h2o_sweep_runner', _mod_path)
_h2o_mod = importlib.util.module_from_spec(_spec)
_loader = getattr(_spec, 'loader')
# ensure module is discoverable during dataclass/type introspection
sys.modules['h2o_sweep_runner'] = _h2o_mod
_loader.exec_module(_h2o_mod)

corr_sign = _h2o_mod.corr_sign


def test_corr_sign_positive():
    a = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    b = pd.Series([2.0, 4.0, 6.0, 8.0, 10.0])
    sign, r = corr_sign(a, b)
    assert sign == 1
    assert r > 0.99


def test_corr_sign_insufficient():
    a = pd.Series([1.0])
    b = pd.Series([2.0])
    sign, r = corr_sign(a, b)
    assert sign == 0
    assert math.isnan(r)


def test_corr_sign_constant_series():
    a = pd.Series([1.0, 1.0, 1.0])
    b = pd.Series([2.0, 3.0, 4.0])
    sign, r = corr_sign(a, b)
    assert sign == 0
    assert math.isnan(r)
