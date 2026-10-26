# tests/test_regen_and_c.py
import os
import re
import shutil
import subprocess

import pytest

from tools.fr_gen import tbl, gen_python, gen_c
from tools import fr_codec_gen as fc

ROWS = tbl.parse(open("tables/cmd.tbl", encoding="utf-8").read())
H = open("render/fr_codec.h", encoding="utf-8").read()
C = open("render/fr_codec.c", encoding="utf-8").read()


def test_python_regen_no_drift(tmp_path):
    out = str(tmp_path / "fr_codec_gen.py")
    gen_python.generate(ROWS, out)
    assert open(out, encoding="utf-8").read() == open("tools/fr_codec_gen.py", encoding="utf-8").read()


def test_c_regen_no_drift(tmp_path):
    d = tmp_path / "render"
    d.mkdir()
    gen_c.generate(ROWS, str(d))
    assert (d / "fr_codec.h").read_text(encoding="utf-8") == H
    assert (d / "fr_codec.c").read_text(encoding="utf-8") == C


def test_c_api_face():
    assert "FR_CODEC_GENERATED_H" in H and "FR_CODEC_TBL_SHA256" in H
    assert tbl.tbl_sha256(ROWS) in H
    for i, r in enumerate(ROWS):
        assert "FR_OP_%s = 0x%02X" % (r["op"].upper(), i) in H
        assert "int fr_encode_%s(fr_buf *b);" % r["op"] in H
    assert "FR_OP_CMNT = 0xFF" in H


def test_cross_target_constants():
    h_def = dict(re.findall(r"#define (FR_[A-Z_]+) (\d+)", H))
    assert int(h_def["FR_VARIANT_TAG_NUM"]) == fc.VARIANT_TAG_NUM
    assert int(h_def["FR_VARIANT_TAG_STR"]) == fc.VARIANT_TAG_STR
    assert int(h_def["FR_VARIANT_TAG_BOOL"]) == fc.VARIANT_TAG_BOOL
    assert int(h_def["FR_ASSET_KIND_IMAGE"]) == fc.ASSET_KIND_IMAGE
    assert int(h_def["FR_ASSET_KIND_CANVAS"]) == fc.ASSET_KIND_CANVAS
    assert int(h_def["FR_ASSET_KIND_QUAD"]) == fc.ASSET_KIND_QUAD
    assert int(h_def["FR_ASSET_KIND_FONT"]) == fc.ASSET_KIND_FONT


def test_c_compile_smoke(tmp_path):
    cc = shutil.which("gcc") or shutil.which("clang")
    if not cc:
        pytest.skip("no C compiler on PATH")
    r = subprocess.run([cc, "-std=c99", "-Wall", "-Werror", "-c", "render/fr_codec.c",
                        "-o", str(tmp_path / "fr_codec.o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
