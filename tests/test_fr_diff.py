# tests/test_fr_diff.py —— fr-diff 两流对拍与首分歧帧
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import fr_diff


def _stream(tmp_path, name, frames_rows):
    """造最小流：head + cmnt + 每帧块（dt + rows + s_crc/d_crc 哨兵）。"""
    from tools import fr_session as fs
    from tools.fr_gen import tbl
    sha = tbl.tbl_sha256(tbl.parse(
        open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "tables/cmd.tbl"), encoding="utf-8").read()))
    entries = []
    for rows in frames_rows:
        blk = [("dt", {"val": 0.016})] + rows + \
              [("s_crc", {"crc": 0}), ("d_crc", {"crc": 1})]
        entries.append(("frame", blk))
    s = dict(width=64, height=48, sha=sha, loglvl="base", seed=1, entries=entries)
    p = tmp_path / name
    p.write_text(fs.dump_text(s), encoding="utf-8")
    return str(p)


def test_diff_identical(tmp_path, capsys):
    rows = [[("clear", {"color": (0, 0, 0, 255)})]]
    a = _stream(tmp_path, "a.fr", rows)
    b = _stream(tmp_path, "b.fr", rows)
    assert fr_diff.main([a, b]) == 0
    out = capsys.readouterr().out
    assert "FIRST-DIVERGENCE -1" in out and "HEAD same" in out


def test_diff_first_divergence(tmp_path, capsys):
    r0 = [("clear", {"color": (0, 0, 0, 255)})]
    r2a = [("rect", {"mode": 0, "x": 10.0, "y": 0.0, "w": 5.0, "h": 5.0,
                     "rx": 0.0, "ry": 0.0, "width": 1.0, "color": (1, 2, 3, 4)})]
    r2b = [("rect", {"mode": 0, "x": 20.0, "y": 0.0, "w": 5.0, "h": 5.0,
                     "rx": 0.0, "ry": 0.0, "width": 1.0, "color": (1, 2, 3, 4)})]
    a = _stream(tmp_path, "a.fr", [r0, r0, r2a])
    b = _stream(tmp_path, "b.fr", [r0, r0, r2b])
    assert fr_diff.main([a, b]) == 1
    out = capsys.readouterr().out
    assert "FIRST-DIVERGENCE 2" in out
    assert "- rect 0 10.000000" in out and "+ rect 0 20.000000" in out


def test_diff_frame_count_mismatch(tmp_path, capsys):
    r0 = [("clear", {"color": (0, 0, 0, 255)})]
    a = _stream(tmp_path, "a.fr", [r0, r0])
    b = _stream(tmp_path, "b.fr", [r0, r0, r0])
    assert fr_diff.main([a, b, "--first-only"]) == 1
    out = capsys.readouterr().out
    assert "FRAMES a=2 b=3" in out and "帧数分歧" in out


def test_diff_frames_window_skips(tmp_path, capsys):
    r0 = [("clear", {"color": (0, 0, 0, 255)})]
    r1a = [("rect", {"mode": 1, "x": 1.0, "y": 1.0, "w": 2.0, "h": 2.0,
                     "rx": 0.0, "ry": 0.0, "width": 1.0, "color": (9, 9, 9, 9)})]
    r1b = [("rect", {"mode": 1, "x": 2.0, "y": 1.0, "w": 2.0, "h": 2.0,
                     "rx": 0.0, "ry": 0.0, "width": 1.0, "color": (9, 9, 9, 9)})]
    a = _stream(tmp_path, "a.fr", [r1a, r0])
    b = _stream(tmp_path, "b.fr", [r1b, r0])
    # 窗口只看帧 1（全同）→ 无分歧
    assert fr_diff.main([a, b, "--frames", "1-1"]) == 0
    assert "FIRST-DIVERGENCE -1" in capsys.readouterr().out
