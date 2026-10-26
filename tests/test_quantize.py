# tests/test_quantize.py
import random, struct
import pytest
from tools.fr_gen.quantize import qf

def test_qf_fixed():
    assert qf(0.123456789) == 0.123457
    assert qf(3.0) == 3.0
    assert qf(-2.5) == -2.5

def test_qf_roundtrip_bits():
    random.seed(42)
    for _ in range(2000):
        v = struct.unpack("<f", struct.pack("<f", random.uniform(-1e6, 1e6)))[0]
        q = qf(v)
        assert struct.pack("<f", q) == struct.pack("<f", float(f"{q:.6f}"))

def test_nan_inf_rejected():
    with pytest.raises(ValueError):
        qf(float("nan"))
    with pytest.raises(ValueError):
        qf(float("inf"))
    with pytest.raises(ValueError):
        qf(float("-inf"))
