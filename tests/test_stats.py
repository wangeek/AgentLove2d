# tests/test_stats.py —— B13 fr-stats 四层熵剖面（设计真源
# docs/plans/2026-10-29-b13-entropy-roadmap-design.md §2.2）
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from tools import fr_stats  # noqa: E402


@pytest.fixture(scope="module")
def demo_fr(tmp_path_factory):
    """demo 主 tee 流（4 帧，已知 op 形态：draw rot=0/sx=sy=1 恒定）。"""
    from tests.test_capture import _run_demo, _tee_args  # 复用既有 rig 助手
    out = str(tmp_path_factory.mktemp("stats") / "s.fr")
    r = _run_demo(env_capture=True, extra=_tee_args(out))
    assert r.returncode == 0, (r.returncode, r.stderr)
    return out


def test_op_profile(demo_fr):
    p = fr_stats.profile(demo_fr)
    ops = p["ops"]
    assert ops["rect"]["rows"] > 0 and ops["draw"]["rows"] > 0
    assert sum(v["bytes"] for v in ops.values()) <= p["out_bytes_total"] + p["out_bytes_total"] // 2
    for v in ops.values():
        assert v["avg"] > 0


def test_param_default_hit(demo_fr):
    p = fr_stats.profile(demo_fr)
    d = p["defaults"]
    # demo draw 行 rot 恒 0 / sx sy 恒 1（已知形态）→ 命中率 1.0
    assert d["draw"].get("rot=0", 0) == 1.0
    assert d["draw"].get("sx=1", 0) == 1.0
    # color 白在 draw 行过半（hero 白色，print N8 绿除外）
    assert d["draw"].get("color=white", 0) > 0.5


def test_quant_layer(demo_fr):
    p = fr_stats.profile(demo_fr)
    q = fr_stats.quant_layer(p)
    # px 档模拟必小于全精度（%.6f 定长 → 整数/省略）
    assert q["px_bytes"] < p["out_bytes_total"]
    assert q["gzip_bytes"] < p["out_bytes_total"]


def test_time_layer(demo_fr):
    p = fr_stats.profile(demo_fr)
    t = fr_stats.time_layer(p)
    assert t["frames"] > 0
    assert 0.0 <= t["same_ratio"] <= 1.0
    assert t["avg_diff_rows"] >= 0
