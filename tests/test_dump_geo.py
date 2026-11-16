# tests/test_dump_geo.py —— fr_dump --geo 屏幕有效矩形派生视图（D15 方案一）
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import fr_dump


def _sha():
    from tools.fr_gen import tbl
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return tbl.tbl_sha256(tbl.parse(
        open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read()))


def _hdr():
    return "frb1 640 480 " + _sha() + " base 1\n"


def _frame(no, rows):
    body = "".join(rows)
    return ("frame %d\ndt 0.016000\n%ss_crc 0\nd_crc 7\n" % (no, body))


def test_geo_scale_and_offset(monkeypatch, capsys):
    """整图缩放：128 画 32（sx=sy=0.25）+ ox oy 偏移参与左上角。"""
    s = fr_dump.fs.parse_text(
        _hdr() + _frame(0, [
            "asset image 1 128 128 00\n",
            "draw 1 0 40 40 0 0.25 0.25 0 0 255 255 255 255\n",
            "draw 1 0 40 40 0 0.25 0.25 8 8 255 255 255 255\n",
        ]))
    monkeypatch.setattr(fr_dump, "_load", lambda p: s)
    assert fr_dump.main(["x.fr", "--geo"]) == 0
    out = capsys.readouterr().out
    assert "# geo: d1 tex=1 rect=40.00,40.00 32.00x32.00（img 128x128 @0.25）" in out
    assert "# geo: d2 tex=1 rect=38.00,38.00 32.00x32.00（img 128x128 @0.25）" in out


def test_geo_quad_slice_and_rot(monkeypatch, capsys):
    """quad 切片（atlas）与 rot≠0 注记。"""
    s = fr_dump.fs.parse_text(
        _hdr() + _frame(0, [
            "asset image 1 128 128 00\n",
            "asset quad 3 16 16 32 32 128 128\n",
            "draw 1 3 10 10 0 1 1 0 0 255 255 255 255\n",
            "draw 1 0 40 40 0.500000 1 1 0 0 255 255 255 255\n",
        ]))
    monkeypatch.setattr(fr_dump, "_load", lambda p: s)
    assert fr_dump.main(["x.fr", "--geo"]) == 0
    out = capsys.readouterr().out
    assert "# geo: d1 tex=1 rect=10.00,10.00 32.00x32.00（q3 16,16 32x32 @1）" in out
    # rot≠0：at/rot 取原文 token（%.6f），不展开矩形
    assert "# geo: d2 tex=1 at=40.000000,40.000000 rot=0.500000（非轴对齐不展开）" in out


def test_geo_unregistered_and_frame_reset(monkeypatch, capsys):
    """幻 tex 如实注记；帧间计数重置。"""
    s = fr_dump.fs.parse_text(
        _hdr() + _frame(0, ["draw 9 0 1 1 0 1 1 0 0 255 255 255 255\n"])
        + _frame(1, ["draw 1 0 2 2 0 2 2 0 0 255 255 255 255\n"])
        + _frame(2, ["asset image 1 64 64 00\n",
                     "draw 1 0 3 3 0 0.5 0.5 0 0 255 255 255 255\n"]))
    monkeypatch.setattr(fr_dump, "_load", lambda p: s)
    assert fr_dump.main(["x.fr", "--geo"]) == 0
    out = capsys.readouterr().out
    assert "# geo: d1 tex=9（未登记，不展开）" in out
    assert "# geo: d1 tex=1 rect=2.00,2.00 128.00x128.00（未登记，不展开）" not in out
    # 后登记（此处不合法但工具如实按出现序）后命中
    assert "# geo: d1 tex=1 rect=3.00,3.00 32.00x32.00（img 64x64 @0.5）" in out


def test_geo_frames_filter_uses_full_table(monkeypatch, capsys):
    """--frames 过滤丢掉 frame 0 的 asset 行后，登记表仍须来自过滤前。"""
    s = fr_dump.fs.parse_text(
        _hdr() + _frame(0, ["asset image 1 128 128 00\n",
                            "clear 0 0 0 255\n"])
        + _frame(1, ["draw 1 0 40 40 0 0.25 0.25 0 0 255 255 255 255\n"]))
    monkeypatch.setattr(fr_dump, "_load", lambda p: s)
    assert fr_dump.main(["x.fr", "--frames", "1-1", "--geo"]) == 0
    out = capsys.readouterr().out
    assert "asset image" not in out          # 原 frame 0 的 asset 行已滤
    # 原 frame 1 重排为输出 frame 0，登记表仍命中（来自过滤前）
    assert "# geo: d1 tex=1 rect=40.00,40.00 32.00x32.00（img 128x128 @0.25）" in out


def test_geo_deterministic_and_zero_drift(monkeypatch, capsys):
    """同流两次 --geo 逐字节一致；不开 --geo 输出不含 geo 行（零漂移）。"""
    s = fr_dump.fs.parse_text(
        _hdr() + _frame(0, ["asset image 1 128 128 00\n",
                            "draw 1 0 40 40 0 0.25 0.25 0 0 255 255 255 255\n"]))
    monkeypatch.setattr(fr_dump, "_load", lambda p: s)
    assert fr_dump.main(["x.fr", "--geo"]) == 0
    first = capsys.readouterr().out
    assert fr_dump.main(["x.fr", "--geo"]) == 0
    assert capsys.readouterr().out == first
    assert fr_dump.main(["x.fr"]) == 0
    plain = capsys.readouterr().out
    assert "# geo" not in plain
    assert "draw 1 0 40.000000 40.000000" in plain


def test_geo_names_join(monkeypatch, capsys, tmp_path):
    """--names join（D15 方案四）：assets.json src → geo 行与 strip 摘要行
    附语义名；无名字条目不受影响。"""
    import json
    (tmp_path / "assets.json").write_text(json.dumps({"assets": [
        {"id": 1, "kind": "image", "w": 128, "h": 128, "src": "icon_01.png"},
        {"id": 3, "kind": "quad", "x": 16.0, "y": 16.0, "w": 32.0, "h": 32.0,
         "sw": 128.0, "sh": 128.0},
    ]}), encoding="utf-8")
    s = fr_dump.fs.parse_text(
        _hdr() + _frame(0, [
            "asset image 1 128 128 00\n",
            "asset quad 3 16 16 32 32 128 128\n",
            "draw 1 3 10 10 0 1 1 0 0 255 255 255 255\n",
            "draw 2 0 40 40 0 0.25 0.25 0 0 255 255 255 255\n",
        ]))
    monkeypatch.setattr(fr_dump, "_load", lambda p: s)
    np = str(tmp_path / "assets.json")
    assert fr_dump.main(["x.fr", "--geo", "--strip-assets", "--names", np]) == 0
    out = capsys.readouterr().out
    assert "# asset image 1(icon_01.png) 128 128 (+1B hex)" in out
    assert "# geo: d1 tex=1(icon_01.png) rect=10.00,10.00 32.00x32.00" \
           "（q3 16,16 32x32 @1）" in out
    assert "tex=2" in out and "(icon_01.png)" not in \
        out.split("tex=2")[1].split("\n")[0]   # 无名条目不误附
