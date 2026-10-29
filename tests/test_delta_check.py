import io
import os
import subprocess
import sys

sys.path.insert(0, ".")
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from tools import fr_delta_check as fdc  # noqa: E402
import tools.fr_session as fs  # noqa: E402

SHA = "1bd74035c2e8e25e4a6ab54bbb32c8ff59bfc3b16e21cf5b84c6d0094ec11292"


def _mini():
    return (
        "frb1 64 48 " + SHA + " base 1 :px +d\n"
        "frame 0\ndt 0.016667\n"
        "C 0 0 0 255\n"
        "D 1 0 10 20 0.000000 1.000000 1.000000\n"
        "R 0 5 6 7 8 0 0 1.000000 255 0 0 255\n"
        "frame 1\ndt 0.016667\n"
        "S 0\n"
        "frame 2\ndt 0.016667\n"
        "S 0\n"
        "pd 1 0 x 42\n"
        'rdp 2 "R 0 1 2 3 4 0 0 1.000000 0 255 0 255"\n'
        "rdm 1\n"
    )


def test_delta_check_expand(tmp_path):
    """扩展行型展开：S 引用、rdm 删除（pos=应用时刻行序，先删后插规范序）、
    rdp 插入、pd 改写叠加（mini 流手写=规范序：先删后插）。"""
    src = tmp_path / "delta.fr"
    src.write_bytes(_mini().encode("utf-8"))
    expanded = str(tmp_path / "expanded.fr")

    rc = fdc.main([str(src), "-o", expanded])
    assert rc == 0
    text = open(expanded, encoding="utf-8").read()

    # 帧数 3；无增量行残留
    assert text.count("frame ") == 3
    assert not any(ln.startswith(("S ", "pd ", "rdp ", "rdm ")) for ln in text.splitlines())


def test_delta_check_pd_overlay():
    """pd 叠加 rdp 插入：rdp 插入的行 + pd 改写既有行同帧共存。"""
    mini = (
        "frb1 64 48 " + SHA + " base 1 :px +d\n"
        "frame 0\ndt 0.016667\n"
        "C 0 0 0 255\n"
        "D 1 0 10 20 0.000000 1.000000 1.000000\n"
        "R 0 5 6 7 8 0 0 1.000000 255 0 0 255\n"
        "frame 1\ndt 0.016667\n"
        "S 0\n"
        "frame 2\ndt 0.016667\n"
        "S 0\n"
        "rdm 1\n"
        'rdp 1 "D 1 0 42 20 0.000000 1.000000 1.000000"\n'
        'rdp 2 "R 0 1 2 3 4 0 0 1.000000 0 255 0 255"\n'
        "pd 1 0 x 42\n"
    )
    r = fdc.expand_delta(mini)
    f2 = r["_rows"][2]
    assert any("42" in row for row in f2), f2
    assert any(row.startswith("rect 0 1 2 3 4") for row in f2), f2
    assert r["warnings"] == []


def test_delta_check_c_cross(tmp_path):
    """py 展开 vs C 展开（fr_render 离线回放）双实现交叉：D_CRC 逐帧一致。"""
    src = tmp_path / "delta.fr"
    src.write_bytes(_mini().encode("utf-8"))
    expanded = str(tmp_path / "expanded.fr")
    assert fdc.main([str(src), "-o", expanded]) == 0

    def dcrcs(p):
        rr = subprocess.run([sys.executable, os.path.join(_ROOT, "tools", "fr_render.py"), p],
                            capture_output=True, timeout=120,
                            env=dict(os.environ, FR_RENDER_TIMEOUT="120"))
        return [l.split()[2] for l in rr.stdout.decode("utf-8", "replace").splitlines()
                if l.startswith("D_CRC")]

    d_py = dcrcs(expanded)      # py 展开后的全量流
    d_c = dcrcs(str(src))       # C 展开器直读增量流
    assert d_py == d_c and len(d_py) == 3, (d_py, d_c)
