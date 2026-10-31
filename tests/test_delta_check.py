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
    assert r["warnings"] == []
    # pd 精确落位（2026-10-31 pd 回检补强：原断言 any("42" in row) 被 rdp
    # 插入行误满足——pd 写错位（rot）照样绿，潜伏至 dream 回检才暴露）
    # 帧 2 预期：rdm 删原 D 后 rdp 插新 D（:px 原样形，x=42）→ pd k=0 改其 x 位
    d_rows = [l for l in f2 if l.split(" ")[0] in ("draw", "D")]
    # rdp 内嵌行 denorm 短名→全名、token 原样（不回填缺省）；pd k=0 改其 x 位
    assert d_rows == ["draw 1 0 42.000000 20 0.000000 1.000000 1.000000"], f2
    assert any(row.startswith("rect 0 1 2 3 4") for row in f2), f2


def test_delta_check_pd_disambiguation():
    """pd (asset,k) 帧内出现序消歧：k=1 改第二实例；k 越界进报告不炸；
    rdp 改变帧内序后身份按当前序（React key=渲染序）。"""
    SHA1 = SHA
    text = (
        "frb1 640 480 " + SHA1 + " base 1 :px +d\n"
        "frame 0\ndt 0.016667\n"
        "D 7 0 100 200 0.000000 1.000000 1.000000\n"
        "D 7 0 300 200 0.000000 1.000000 1.000000\n"
        "frame 1\ndt 0.016667\n"
        "pd 7 1 x 555\n"
        "frame 2\ndt 0.016667\n"
        "pd 7 0 x 111\n"
    )
    r = fdc.expand_delta(text)
    assert r["warnings"] == []
    f1 = r["_rows"][1]
    t = f1[1].split()
    assert t[1] == "7" and t[3] == "555.000000", f1  # k=1 → 第二行 x 位
    assert f1[0].split()[3] == "100.000000"  # 第一行不动
    f2 = r["_rows"][2]
    assert f2[0].split()[3] == "111.000000" and f2[1].split()[3] == "555.000000"
    # k 越界 → 报告、不抛
    r2 = fdc.expand_delta(text.replace("pd 7 0 x 111", "pd 7 5 x 111"))
    assert any("身份未配对" in w for w in r2["warnings"])


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
