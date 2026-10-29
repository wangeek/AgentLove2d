# tests/test_regen_and_c.py
import os
import re
import shutil
import subprocess

import pytest

from tools.fr_gen import tbl, gen_python, gen_c
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROWS = tbl.parse(open(os.path.join(_ROOT, "tables", "cmd.tbl"), encoding="utf-8").read())
H = open(os.path.join(_ROOT, "render", "fr_codec.h"), encoding="utf-8").read()
C = open(os.path.join(_ROOT, "render", "fr_codec.c"), encoding="utf-8").read()


def test_python_regen_no_drift(tmp_path):
    out = str(tmp_path / "fr_codec_gen.py")
    gen_python.generate(ROWS, out)
    assert open(out, encoding="utf-8").read() == open(
        os.path.join(_ROOT, "tools", "fr_codec_gen.py"), encoding="utf-8").read()


def test_c_regen_no_drift(tmp_path):
    d = tmp_path / "render"
    d.mkdir()
    gen_c.generate(ROWS, str(d))
    assert (d / "fr_codec.h").read_text(encoding="utf-8") == H
    assert (d / "fr_codec.c").read_text(encoding="utf-8") == C


def in_h_sha():
    """头文件内嵌的指纹（#define 行取值——全表 sha，含 ext）。"""
    for ln in H.splitlines():
        if ln.startswith("#define FR_CODEC_TBL_SHA256"):
            return ln.split('"')[1]
    return ""


def test_c_api_face():
    assert "FR_CODEC_GENERATED_H" in H and in_h_sha() == tbl.tbl_sha256(ROWS)
    # B15：C 目标过滤 ext 扩展行（S/pd/rdp/rdm 不进基座）；枚举序号
    # 按过滤后行序（0 起连续），指纹仍为全表 sha。
    base = [r for r in ROWS if r["status"] != "ext"]
    # B15：C 目标过滤 ext 扩展行（S/pd/rdp/rdm 不进基座）；枚举序号
    # 按过滤后行序（0 起连续），指纹仍为全表 sha。
    base = [r for r in ROWS if r["status"] != "ext"]
    for i, r in enumerate(base):
        assert "FR_OP_%s = 0x%02X" % (r["op"].upper(), i) in H
        if r["op"] == "asset":  # asset 四合一，C 侧拆四具名函数
            for kind in ("image", "canvas", "quad", "font"):
                assert "int fr_encode_asset_%s(" % kind in H
        else:
            assert "int fr_encode_%s(" % r["op"] in H
    assert "FR_OP_CMNT = 0xFF" in H


def test_cross_target_constants():
    # 结构性对拍：.h 全部 FR_ 口径 #define ↔ fr_codec_gen 同名属性（去 FR_ 前缀）
    # 整体相等——一侧加常量另一侧漏加即红
    h_def = {name[len("FR_"):]: int(val) for name, val in
             re.findall(r"#define (FR_(?:VARIANT_TAG|ASSET_KIND)_[A-Z_]+) (\d+)", H)}
    py_def = {name: getattr(fc, name) for name in dir(fc)
              if re.match(r"^(?:VARIANT_TAG|ASSET_KIND)_[A-Z_]+$", name)}
    assert h_def and py_def  # 收集为空 = 正则坏了，不许空对空假绿
    assert h_def == py_def


def test_c_compile_smoke(tmp_path):
    cc = shutil.which("gcc") or shutil.which("clang")
    if not cc:
        pytest.skip("no C compiler on PATH")
    tus = ("fr_codec.c", "fr_session.c", "fr_selftest.c")  # 生成 TU + 手写会话层 + 生成自检
    for name in tus:  # 全部 TU 零警告过 -Werror
        r = subprocess.run([cc, "-std=c99", "-Wall", "-Werror", "-c",
                            os.path.join(_ROOT, "render", name),
                            "-o", str(tmp_path / (name + ".o"))],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    # 链接并真跑 selftest：emit 字节对账 + golden 解码-重编码闭环（B4）
    exe = str(tmp_path / ("st.exe" if os.name == "nt" else "st"))
    r = subprocess.run([cc, "-std=c99", "-Wall", "-Werror"] +
                       [os.path.join(_ROOT, "render", name) for name in tus] +
                       ["-o", exe], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([exe], capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "C EMIT OK %d rows" % len(fc.self_test_samples()) in r.stdout
    assert "C DECODE OK" in r.stdout
