# tests/test_codec_gen.py
import pytest
from tools.fr_gen import tbl
from tools import fr_codec_gen as fc

ROWS = tbl.parse(open("tables/cmd.tbl", encoding="utf-8").read())
BASE_SHA = "7f3427691b6e405a65cabe1d00709f3ee085b9e569d1b3764fb84b00c60bafa6"

def test_ops_match_table():
    assert fc.TBL_SHA256 == tbl.tbl_sha256(ROWS) == BASE_SHA
    assert [o["op"] for o in fc.OPS] == [r["op"] for r in ROWS]

def test_draw_roundtrip_bin():
    row = ("draw", dict(tex=1, quad=3, x=34.0, y=56.0, rot=0.0, sx=-1.0, sy=1.0,
                        ox=0.0, oy=0.0, color=(255, 255, 0, 255)))
    buf = fc.encode_row(*row)
    op, fields = fc.decode_row(memoryview(buf))
    assert op == "draw" and fields == row[1]

def test_text_render_parse():
    fields = dict(slot=0, type="keypressed", src=0, args=[("return",), (False,)])
    line = fc.render_line("ev", fields)
    assert line == 'ev 0 "keypressed" 0 2 str "return" bool 0'
    assert fc.parse_line(line) == ("ev", fields)

def test_str_escape():
    fields = dict(font=2, text='a"b\\c\nd', x=1.0, y=2.0, rot=0.0, sx=1.0, sy=1.0,
                  color=(0, 0, 0, 255))
    line = fc.render_line("print", fields)
    op, got = fc.parse_line(line)
    assert op == "print" and got == fields

def test_quantized_float_layout():
    buf = fc.encode_row("dt", dict(val=0.016667))
    assert buf[0] == fc._BY_OP["dt"]["opcode"] and len(buf) == 5  # opcode + f32

def test_every_op_roundtrips():
    samples = fc.self_test_samples()
    ops_with_sample = {op for op, _ in samples}
    assert ops_with_sample == {r["op"] for r in ROWS}  # 全覆盖
    for op, fields in samples:
        buf = fc.encode_row(op, fields)
        assert fc.decode_row(memoryview(buf)) == (op, fields)   # 二进制全员
        if op != "asset":
            assert fc.parse_line(fc.render_line(op, fields)) == (op, fields)  # 文本除 asset

def test_asset_text_not_implemented():
    with pytest.raises(NotImplementedError):
        fc.render_line("asset", dict(kind=1, id=2, w=640, h=480))
