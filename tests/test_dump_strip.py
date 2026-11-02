# tests/test_dump_strip.py —— fr_dump --strip-assets（资产 hex 剥离）
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import fr_dump


def _stream_with_assets():
    s = fr_dump.fs.parse_text(
        "frb1 64 48 " + _sha() + " base 1\n"
        "cmnt t\n"
        "frame 0\n"
        "dt 0.016000\n"
        "asset image 7 4 4 00ff00ff00ff00ff\n"
        "asset font 9 14.000000 0001\n"
        "clear 0 0 0 255\n"
        "s_crc 0\nd_crc 7\n")
    return s


def _sha():
    from tools.fr_gen import tbl
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return tbl.tbl_sha256(tbl.parse(
        open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read()))


def test_strip_assets(monkeypatch, capsys):
    s = _stream_with_assets()
    monkeypatch.setattr(fr_dump, "_load", lambda p: s)
    rc = fr_dump.main(["x.fr", "--strip-assets"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# asset image 7 4 4 (+8B hex)" in out
    assert "# asset font 9 14.000000 (+2B hex)" in out
    assert "00ff00ff" not in out          # hex 体不在
    assert "clear 0 0 0 255" in out       # 帧内容完好


def test_strip_assets_no_hex_kinds(monkeypatch, capsys):
    """canvas/quad 行无 hex 体——原样保留，不剥不错剥。"""
    s = fr_dump.fs.parse_text(
        "frb1 64 48 " + _sha() + " base 1\n"
        "frame 0\n"
        "dt 0.016000\n"
        "asset canvas 2 640 480\n"
        "asset quad 3 0.000000 0.000000 16.000000 16.000000 64.000000 64.000000\n"
        "asset image 8 4 4 -\n"           # 空载荷 '-'
        "clear 0 0 0 255\n"
        "s_crc 0\nd_crc 7\n")
    monkeypatch.setattr(fr_dump, "_load", lambda p: s)
    rc = fr_dump.main(["x.fr", "--strip-assets"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "asset canvas 2 640 480\n" in out          # 无 hex 体：原样
    assert "asset quad 3 0.000000" in out             # 无 hex 体：原样
    assert "# asset image 8 4 4 (+0B hex)" in out     # 空载荷：剥成 0 字节摘要
