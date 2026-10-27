# tests/test_c_emit.py
import os

from tools.fr_gen import tbl, gen_c
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    return open(os.path.join(_ROOT, "render", name), encoding="utf-8").read()


def test_selftest_exists_and_covers_all_samples():
    src = _read("fr_selftest.c")
    assert "C EMIT OK" in src
    for op, fields in fc.self_test_samples():
        expect = fc.encode_row(op, fields)
        assert expect.hex() in src.replace(" ", "")     # 期望字节已嵌入（去空白比对）


def test_header_has_typed_signatures():
    h = _read("fr_codec.h")
    assert "typedef struct { uint8_t tag; double num; const char *str; } fr_variant;" in h
    assert "int fr_encode_draw(fr_buf *b, uint32_t tex, uint32_t quad, float x, float y, float rot, float sx, float sy, float ox, float oy, fr_rgba8 color);" in h
    assert "int fr_encode_line(fr_buf *b, const float *pts, uint32_t pts_n, float width, fr_rgba8 color);" in h
    assert "int fr_encode_ev(fr_buf *b, uint32_t slot, const char *type, uint8_t src, const fr_variant *args, uint32_t argc);" in h
    for kind in ("image", "canvas", "quad", "font"):
        assert "fr_encode_asset_%s(" % kind in h


def test_regen_deterministic_incl_selftest(tmp_path):
    d = tmp_path / "render"
    d.mkdir()
    rows = tbl.parse(open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read())
    gen_c.generate(rows, str(d))
    for name in ("fr_codec.h", "fr_codec.c", "fr_selftest.c"):
        assert (d / name).read_text(encoding="utf-8") == _read(name)
