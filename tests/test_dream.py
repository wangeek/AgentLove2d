# tests/test_dream.py
"""B18 dream runner 测试组（M1）。--from-file 确定性模式全链，CI 零 token。"""
import os
import zlib

import pytest

from tools import fr_session
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _row(line):
    return fc.parse_line(line)


def test_parse_chunk_accepts_content_rows():
    from dream import session as ds
    chunk = ('frame 0\n'
             'st 0 "hero.x" num 10.000000\n'
             'clear 0 0 0 255\n'
             'draw 1 0 10.000000 20.000000 0.000000 1.000000 1.000000 0.000000 0.000000 255 255 255 255\n'
             '\n'
             'frame 1\n'
             'st 0 "hero.x" num 11.000000\n'
             'clear 0 0 0 255\n')
    frames = ds.parse_chunk(chunk)
    assert [n for n, _ in frames] == [0, 1]
    assert frames[0][1][0][0] == "st"
    assert frames[0][1][1][0] == "clear"


def test_parse_chunk_rejects_runner_rows():
    from dream import session as ds
    for bad in ('dt 0.066667', 'asset image 9 32 32 00', 's_crc 1', 'd_crc 1'):
        chunk = 'frame 0\n%s\nclear 0 0 0 255\n' % bad
        with pytest.raises(ValueError):
            ds.parse_chunk(chunk)


def test_seal_and_roundtrip(tmp_path):
    from dream import session as ds
    frames = ds.parse_chunk(
        'frame 0\nst 0 "hero.x" num 10.000000\n'
        'clear 0 0 0 255\n'
        'rect 0 0.000000 0.000000 640.000000 480.000000 0.000000 0.000000 1.000000 255 0 0 255\n')
    entries = ds.seal_frames(frames, kit_rows=[], dt=0.066667)
    # d_crc 口径：out 行文本 "\n" 连接的 zlib crc32
    out_txt = ["clear 0 0 0 255",
               "rect 0 0.000000 0.000000 640.000000 480.000000 0.000000 0.000000 1.000000 255 0 0 255"]
    expect_d = zlib.crc32("\n".join(out_txt).encode()) & 0xFFFFFFFF
    block = entries[0][1]
    d_row = [f for op, f in block if op == "d_crc"][0]
    assert d_row["crc"] == expect_d
    # 行序：dt 首行、end 双行殿后
    assert block[0][0] == "dt"
    assert [op for op, _ in block[-2:]] == ["s_crc", "d_crc"]
    # 全会话 canonical 幂等（fr_session 链路）
    s = ds.build_session(entries, seed=1)
    text = fr_session.dump_text(s)
    assert fr_session.dump_text(fr_session.parse_text(text)) == text
    p = tmp_path / "d.fr"
    ds.write_session(s, str(p))
    assert p.read_text(encoding="utf-8") == text
