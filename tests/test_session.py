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
                loglvl="base", seed=3056735,
                entries=[("cmnt", "录制于演示"), ("frame", _sample_rows()), ("cmnt", "尾注"),
                         ("frame", _sample_rows()[:3])])

def test_text_dump_parse_fixed_point():
    s = _sample_session()
    text = fs.dump_text(s)
    assert fs.parse_text(text) == s
    assert text == fs.dump_text(fs.parse_text(text))

def test_binary_dump_parse_fixed_point():
    s = _sample_session()
    blob = fs.dump_binary(s)
    assert blob[:4] == b"FRB1"
    assert fs.parse_binary(blob) == s
    assert blob == fs.dump_binary(fs.parse_binary(blob))

def test_cross_form_roundtrip():
    s = _sample_session()
    assert fs.parse_binary(fs.dump_text(s) and fs.dump_binary(s)) == s
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

def test_cmnt_rejected_control():
    s = _sample_session()
    s["entries"].insert(0, ("cmnt", "bad\rnote"))
    with pytest.raises(fs.SessionError):
        fs.dump_text(s)
