# tests/test_session.py
import os, pytest
from tools import fr_session as fs
from tools.fr_gen import tbl
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _sample_rows():
    return [(op, dict(f)) for op, f in fc.self_test_samples()]

def _sample_session():
    return dict(width=640, height=480,
                sha=tbl.tbl_sha256(tbl.parse(open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read())),
                loglvl="base", seed=3056735, prec="full", delta=False,
                entries=[("cmnt", "录制于演示"), ("frame", _sample_rows()), ("cmnt", "尾注"),
                         ("frame", _sample_rows()[:3])])

def test_text_dump_parse_fixed_point():
    s = _sample_session()
    text = fs.dump_text(s)
    assert fs.parse_text(text) == s
    assert text == fs.dump_text(fs.parse_text(text))

def _strip_delta(s):
    """B15：二进制头无 +d 列——比对前剔除 parse_binary 侧的 delta 键。"""
    s = dict(s)
    s.setdefault("delta", False)
    return s


def test_binary_dump_parse_fixed_point():
    s = _sample_session()
    blob = fs.dump_binary(s)
    assert blob[:4] == b"FRB1"
    assert _strip_delta(fs.parse_binary(blob)) == s
    assert blob == fs.dump_binary(fs.parse_binary(blob))

def test_cross_form_roundtrip():
    s = _sample_session()
    assert _strip_delta(fs.parse_binary(fs.dump_text(s) and fs.dump_binary(s))) == s
    assert fs.parse_text(fs.dump_text(fs.parse_binary(fs.dump_binary(s)))) == s

def test_text_form_samples():
    text = fs.dump_text(_sample_session())
    lines = text.split("\n")
    assert lines[0].startswith("frb1 640 480 ")
    assert lines[0].split()[4] == "base"
    assert "cmnt 录制于演示" in lines
    assert "frame 0" in lines and "frame 1" in lines
    # self_test_samples 的 image 载荷为 16 字节（b"\x00\x01\x02\x03" * 4），规范形整行如下
    assert "asset image 1 2 2 00010203000102030001020300010203" in lines
    assert "err " in " ".join(lines)

def test_text_errors():
    s = fs.dump_text(_sample_session())
    # "frame 1" 所在行号 = 头1 + cmnt1 + frame0 1 + rows N + cmnt尾注1 + 1 = N + 5
    bad_no = 5 + len(_sample_rows())
    with pytest.raises(fs.SessionError, match="第 %d 行" % bad_no):
        fs.parse_text(s.replace("frame 1", "frame 7"))
    with pytest.raises(fs.SessionError):
        fs.parse_text("not-a-header\n")
    with pytest.raises(fs.SessionError):
        fs.parse_text(s.replace("base", "ultra"))

def test_binary_errors():
    blob = fs.dump_binary(_sample_session())
    with pytest.raises(fs.SessionError, match="magic"):
        fs.parse_binary(b"XRB1" + blob[4:])
    with pytest.raises(fs.SessionError, match="截断"):
        fs.parse_binary(blob[:-3])
    bad = bytearray(blob); bad[50] = 0x7F
    with pytest.raises(fs.SessionError, match="entry"):
        fs.parse_binary(bytes(bad))
    # 首 entry 是 cmnt：off 50=tag、51:55=len、55 起为 UTF-8 载荷；坏首字节须
    # SessionError 化（不得裸抛 UnicodeDecodeError）
    assert blob[50] == fs.TAG_CMNT
    bad = bytearray(blob); bad[55] = 0xFF
    with pytest.raises(fs.SessionError, match="UTF-8"):
        fs.parse_binary(bytes(bad))


def test_dump_validation():
    """dump 侧共享校验：loglvl/width 非法在文本与二进制两出口都 SessionError。"""
    s = _sample_session()
    bad = dict(s); bad["loglvl"] = "x"
    with pytest.raises(fs.SessionError, match="loglvl"):
        fs.dump_text(bad)
    with pytest.raises(fs.SessionError, match="loglvl"):
        fs.dump_binary(bad)
    bad = dict(s); bad["width"] = 70000
    with pytest.raises(fs.SessionError, match="width"):
        fs.dump_text(bad)
    with pytest.raises(fs.SessionError, match="width"):
        fs.dump_binary(bad)

def test_cmnt_rejected_control():
    s = _sample_session()
    s["entries"].insert(0, ("cmnt", "bad\rnote"))
    with pytest.raises(fs.SessionError):
        fs.dump_text(s)


# ---------------- B14 :prec 档位头 + fr-prec 转换 ----------------

_MINI_FULL = (
    "frb1 8 8 %s base 7\n" % ("0" * 64)
    + "frame 0\n"
    + "dt 0.016667\n"
    + "draw 1 0 10.000000 20.000000 0.000000 1.000000 1.000000 0.000000 0.000000 255 255 255 255\n"
    + "rect 0 5.000000 6.000000 7.000000 8.000000 0.000000 0.000000 1.000000 255 0 0 255\n"
    + "s_crc 111\n"
    + "d_crc 222\n"
)


def test_prec_header_parse():
    """:prec 尾列可选（6 列=full 缺省；7 列校验域）；非法档拒收。"""
    s = fs.parse_text(_MINI_FULL)
    assert s["prec"] == "full"
    s2 = fs.parse_text(_MINI_FULL.replace(" base 7", " base 7 :px"))
    assert s2["prec"] == "px"
    with pytest.raises(fs.SessionError, match="头尾标记"):
        fs.parse_text(_MINI_FULL.replace(" base 7", " base 7 :zz"))
    # dump：full 头零变化（旧流兼容）；px 头带尾标
    assert fs.dump_text(s).splitlines()[0].endswith("7")
    assert fs.dump_text(s2).splitlines()[0].endswith("7 :px")


def test_px_roundtrip_byte_equal():
    """:px 流 parse→dump 逐字节相等（px 行短名/省略形往返保持）。"""
    px_text = fs.dump_text(fs.parse_text(_MINI_FULL.replace(" base 7", " base 7 :px")
                                         ).copy() | {})
    # 构造 px 形态行（parse_line_px 支持）后 dump 保形
    px_stream = (_MINI_FULL.replace(" base 7", " base 7 :px")
                 .replace("draw 1 0 10.000000 20.000000 0.000000 1.000000 1.000000 0.000000 0.000000 255 255 255 255",
                          "D 1 0 10 20 0 1 1")
                 .replace("rect 0 5.000000 6.000000 7.000000 8.000000 0.000000 0.000000 1.000000 255 0 0 255",
                          "R 0 5 6 7 8 0 0 1 255 0 0 255"))
    assert fs.dump_text(fs.parse_text(px_stream)) == px_stream


def test_fr_prec_convert(tmp_path):
    """full→px：out 行重渲染（短名+量化+省略）、d_crc 重算、段行透传。"""
    import tools.fr_prec as fp

    src = tmp_path / "in.fr"
    src.write_bytes(_MINI_FULL.encode("utf-8"))  # LF 定版（write_text 在 Windows 会 CRLF 污染尾列）
    out = str(tmp_path / "out.fr")
    rc = fp.main([str(src), "-o", out, "--px"])
    assert rc == 0
    text = open(out, encoding="utf-8").read()
    lines = text.splitlines()
    assert lines[0].endswith(":px")
    assert "D 1 0 10 20 0 1 1" in lines  # 短名+量化+省略尾
    assert "R 0 5 6 7 8 0 0 1 255 0 0 255" in lines
    assert "dt 0.016667" in lines and "s_crc 111" in lines    # 段行透传
    assert not any(l.startswith("d_crc 222") for l in lines)  # 旧 d_crc 替换
    # d_crc 独立重算对账（自检+独立重算范式）
    import zlib
    px_rows = [l for l in lines
               if l.split()[0] in ("D", "R", "C", "PR", "LN", "CI", "PY", "AR", "PT")]
    want = zlib.crc32("\n".join(px_rows).encode("utf-8"))
    got = [l for l in lines if l.startswith("d_crc ")]
    assert got == ["d_crc %d" % want]
    # 幂等：px 流再转报错（须 full 输入）
    assert fp.main([out, "-o", out + "2", "--px"]) == 1
