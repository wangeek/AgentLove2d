# tests/test_codec_gen.py
import os

import pytest
from tools.fr_gen import tbl
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROWS = tbl.parse(open(os.path.join(_ROOT, "tables", "cmd.tbl"), encoding="utf-8").read())
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
    fields = dict(font=2, text='a  b"c\\d\ne', x=1.0, y=2.0, rot=0.0, sx=1.0, sy=1.0,
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
        assert fc.parse_line(fc.render_line(op, fields)) == (op, fields)  # 文本全员

def test_asset_text_form():
    cases = [
        ("asset", dict(kind=0, id=1, w=2, h=2, data=b"\x00\x01\x02\x03")),
        ("asset", dict(kind=0, id=5, w=2, h=2, data=b"")),
        ("asset", dict(kind=1, id=2, w=640, h=480)),
        ("asset", dict(kind=2, id=3, x=0.0, y=0.0, w=16.0, h=16.0, sw=256.0, sh=256.0)),
        ("asset", dict(kind=3, id=4, size=12.0, data=b"fake-ttf")),
    ]
    assert fc.render_line(*cases[0]) == "asset image 1 2 2 00010203"
    assert fc.render_line(*cases[1]) == "asset image 5 2 2 -"
    for op, fields in cases:
        assert fc.parse_line(fc.render_line(op, fields)) == (op, fields)

def test_asset_text_bad_kind_name():
    with pytest.raises(ValueError):
        fc.parse_line("asset sound 1")

def test_cr_escape_single_line():
    # I-1：\r 转义后整行不被撕裂（splitlines 也切 \r），文本/二进制双往返
    fields = dict(font=2, text="a\rb", x=1.0, y=2.0, rot=0.0, sx=1.0, sy=1.0,
                  color=(0, 0, 0, 255))
    line = fc.render_line("print", fields)
    assert len(line.splitlines()) == 1
    assert fc.parse_line(line) == ("print", fields)
    buf = fc.encode_row("print", fields)
    assert fc.decode_row(memoryview(buf)) == ("print", fields)

def test_control_chars_rejected():
    # I-1：\n\r\t 之外的 C0 与 U+2028/U+2029 文本侧拒收，信息含码位
    with pytest.raises(ValueError, match=r"U\+0000"):
        fc.render_line("err", dict(what="a\x00b"))
    with pytest.raises(ValueError, match=r"U\+2028"):
        fc.render_line("err", dict(what="a\u2028b"))

def test_truncated_rows_value_error():
    # I-3：截断（struct.error/IndexError）统一 ValueError，信息含 op 名
    draw = dict(tex=1, quad=3, x=34.0, y=56.0, rot=0.0, sx=-1.0, sy=1.0,
                ox=0.0, oy=0.0, color=(255, 255, 0, 255))
    with pytest.raises(ValueError, match="op draw"):
        fc.decode_row(memoryview(fc.encode_row("draw", draw)[:-1]))
    ev = dict(slot=0, type="keypressed", src=0, args=[("return",), (False,)])
    with pytest.raises(ValueError, match="op ev"):
        fc.decode_row(memoryview(fc.encode_row("ev", ev)[:-3]))

def test_negative_paths():
    # M-5：未知 opcode / 行尾冗余字节 / 未闭合字符串 / 未知转义
    with pytest.raises(ValueError, match="opcode"):
        fc.decode_row(memoryview(b"\x99"))
    with pytest.raises(ValueError, match="冗余"):
        fc.decode_row(memoryview(fc.encode_row("dt", dict(val=1.0)) + b"\x00"))
    with pytest.raises(ValueError, match="未闭合"):
        fc.parse_line('err "abc')
    with pytest.raises(ValueError, match="转义"):
        fc.parse_line('err "a\\qb"')
