# tests/test_gen_js.py —— JS 目标（gen_js）与跨实现一致性
#
# 三件事：
#   1. 生成物确定性：同表重复再生逐字节相等（无时间戳/随机）
#   2. 表数据面完整：op 集合 == cmd.tbl，指纹 == tbl_sha256，delta 标记只落在
#      status=ext 的那九个增量动词上
#   3. 跨实现验收：用 node 跑 render/js/conformance.mjs 吃 golden 流——
#      逐行 round-trip + 逐帧 d_crc 重算。没有 node 则跳过（与依赖分层一致）。
import pathlib
import shutil
import subprocess
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from tools.fr_gen import gen_js, tbl  # noqa: E402

NODE = shutil.which("node")


def _rows():
    return tbl.parse((_ROOT / "tables" / "cmd.tbl").read_text(encoding="utf-8"))


def test_gen_js_deterministic():
    """同表重复再生逐字节相等（生成物可 diff，是"重生成而非手改"的前提）。"""
    a = gen_js.render_module(_rows())
    b = gen_js.render_module(_rows())
    assert a == b
    assert a.endswith("\n")
    assert "\r" not in a


def test_gen_js_covers_table():
    """op 集合/指纹/delta 标记全部由表驱动，不漏不多。"""
    rows = _rows()
    text = gen_js.render_module(rows)
    for r in rows:
        assert f'  "{r["op"]}": {{' in text, r["op"]
    assert tbl.tbl_sha256(rows) in text
    # delta 只该落在 status=ext 的行上（CP/SET/INS/DEL/MOVE/PLACE/POSE/ENTER/EXIT）
    ext = [r["op"] for r in rows if r["status"] == "ext"]
    assert len(ext) == 9, ext
    for op in ext:
        line = next(l for l in text.split("\n") if l.startswith(f'  "{op}": {{'))
        assert "delta: true" in line, line
    sealed = [r["op"] for r in rows if r["status"] != "ext"]
    for op in sealed:
        line = next(l for l in text.split("\n") if l.startswith(f'  "{op}": {{'))
        assert "delta: false" in line, line


def test_gen_js_committed_copy_is_current():
    """入库的 render/js/fr_table.mjs 必须等于"现在重生成"的结果。

    这条防的是"改了表忘了重生成"——生成物入库就该是这个语义，
    否则两端指纹会悄悄分叉。
    """
    dst = _ROOT / "render" / "js" / "fr_table.mjs"
    assert dst.is_file(), "缺 render/js/fr_table.mjs（跑 python -m tools.fr_gen.gen_js）"
    assert dst.read_text(encoding="utf-8") == gen_js.render_module(_rows())


@pytest.mark.skipif(NODE is None, reason="无 node（JS 侧验收需要 node >= 18）")
def test_js_conformance_on_golden():
    """跨实现验收：JS codec 吃 Python 产的 golden 流。

    逐行 round-trip 必须逐字节相等；每帧 d_crc 必须与重算一致。
    """
    r = subprocess.run([NODE, str(_ROOT / "render" / "js" / "conformance.mjs"),
                        str(_ROOT / "tests" / "golden" / "l0_session.fr")],
                       capture_output=True, timeout=120, cwd=_ROOT)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    assert r.returncode == 0, out
    assert "CONFORMANCE OK" in out, out


@pytest.mark.skipif(NODE is None, reason="无 node")
def test_js_conformance_detects_corruption(tmp_path):
    """这条闸自己也得能红：改一个数值 → d_crc 失配；少写小数位 → round-trip 失配。

    （只验"会失败"的闸等于装饰——它在该静的时候静、该响的时候不响。）
    """
    src = (_ROOT / "tests" / "golden" / "l0_session.fr").read_text(encoding="utf-8")
    conf = str(_ROOT / "render" / "js" / "conformance.mjs")

    bad_crc = tmp_path / "bad_crc.fr"
    changed = src.replace("draw 1 0 11.000020", "draw 1 0 11.000030", 1)
    assert changed != src
    bad_crc.write_text(changed, encoding="utf-8", newline="\n")
    r1 = subprocess.run([NODE, conf, str(bad_crc)], capture_output=True, timeout=120)
    o1 = (r1.stdout + r1.stderr).decode("utf-8", "replace")
    assert r1.returncode != 0, o1
    assert "d_crc" in o1 and "≠ 重算" in o1, o1

    bad_row = tmp_path / "bad_row.fr"
    short = src.replace("11.000020", "11.00002", 1)
    assert short != src
    bad_row.write_text(short, encoding="utf-8", newline="\n")
    r2 = subprocess.run([NODE, conf, str(bad_row)], capture_output=True, timeout=120)
    o2 = (r2.stdout + r2.stderr).decode("utf-8", "replace")
    assert r2.returncode != 0, o2
    assert "round-trip 不一致" in o2, o2
