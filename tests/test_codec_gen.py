# tests/test_codec_gen.py
import os

import pytest
from tools.fr_gen import tbl
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROWS = tbl.parse(open(os.path.join(_ROOT, "tables", "cmd.tbl"), encoding="utf-8").read())
BASE_SHA = "1bd74035c2e8e25e4a6ab54bbb32c8ff59bfc3b16e21cf5b84c6d0094ec11292"

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
    # B15：ext 扩展行型（S/pd/rdp/rdm）不进 selftest（C emit 不产增量，
    # 先例=font 引用形态）；round-trip 归专项测试 + 真流实测。
    base_ops = {r["op"] for r in ROWS if r["status"] != "ext"}
    assert ops_with_sample == base_ops  # 基座全覆盖
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


# ---------------- B14 :px 紧凑档（短名+尾部默认省略+像素量化） ----------------

def test_px_render_omit_and_quantize():
    """:px 渲染：短名 D、坐标整数量化、尾部默认省略（color=white/oy/ox）。"""
    f = {"tex": 7, "quad": 0, "x": 100.0, "y": 200.0, "rot": 0.0, "sx": 1.0,
         "sy": 1.0, "ox": 0.0, "oy": 0.0, "color": (255, 255, 255, 255)}
    assert fc.render_line_px("draw", f) == "D 7 0 100 200 0 1 1"


def test_px_parse_roundtrip_equiv():
    """:px 解析回填默认后与 full fields 等价（含手工最短行与显式色两形态）。"""
    _, g = fc.parse_line_px("D 7 0 100 200 0.000000 1.000000 1.000000")
    assert g["ox"] == 0.0 and g["oy"] == 0.0 and tuple(g["color"]) == (255, 255, 255, 255)
    _, g2 = fc.parse_line_px("D 7 0 100 200 0.000000 1.000000 1.000000 0 0 255 0 0 255")
    assert tuple(g2["color"]) == (255, 0, 0, 255) and g2["ox"] == 0.0


def test_px_rect_and_passthrough():
    """rect 短名+量化（无省略）；段行（rt）同形直通。"""
    f4 = {"mode": 0, "x": 50.0, "y": 150.5, "w": 200.0, "h": 200.0,
          "rx": 0.0, "ry": 0.0, "width": 1.0, "color": (255, 0, 255, 255)}
    px = fc.render_line_px("rect", f4)
    assert px == "R 0 50 150.500000 200 200 0 0 1 255 0 255 255", px
    _, g4 = fc.parse_line_px(px)
    assert g4["y"] == 150.5 and tuple(g4["color"]) == (255, 0, 255, 255)
    assert fc.render_line_px("rt", {"target": 3}) == "rt 3"


# ---------------- B15 增量扩展行型（S/pd/rdp/rdm） ----------------

def test_delta_rows_roundtrip():
    """扩展行型 render/parse round-trip（基座样本豁免的补充覆盖）。"""
    cases = [
        ("S", {"ref": 3}, "S 3"),
        ("pd", {"asset": 7, "k": 2, "param": "x", "val": 102.0}, "pd 7 2 x 102.000000"),
        ("rdm", {"pos": 5}, "rdm 5"),
    ]
    for op, fields, line in cases:
        assert fc.render_line(op, fields) == line, (op, fields)
        got_op, got = fc.parse_line(line)
        assert got_op == op and got == fields, (line, got_op, got)


def test_delta_rdp_embeds_px_line():
    """rdp 内嵌 :px 行（递归 token——line 是带引号 str，含空格不撕行）。"""
    fields = {"pos": 4, "line": "D 7 0 100 200 0 1 1"}
    line = fc.render_line("rdp", fields)
    assert line == 'rdp 4 "D 7 0 100 200 0 1 1"', line
    got_op, got = fc.parse_line(line)
    assert got_op == "rdp" and got == fields


def test_delta_pd_param_whitelist():
    """pd param 白名单（x/y/rot/sx/sy/ox/oy）外的参数拒收。"""
    import pytest as _pytest
    with _pytest.raises(ValueError, match="param"):
        fc.parse_line("pd 7 2 bogus 1.000000")
