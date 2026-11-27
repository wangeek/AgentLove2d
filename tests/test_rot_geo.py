# tests/test_rot_geo.py —— draw.rot 语义与判据粒度（规格 §7.1，v1.6）
#
# 覆盖提案 §8 的验收清单：
#   1. 算例 A/B（旋转梯队）作为 golden：四角/边长/正交残差逐值硬编码
#   2. 算例 C（剪切）作为负例：流内必须出现 err "affine:shear …"，判据可命中
#   3. 三个注入缺陷（度当弧度、符号取反、支点用左上角）+ 一个"该转没转"
#      ——每条都必须让判据变红（判据能红才算判据）
#   4. fr_dump --geo 对 rot=0 的 rect= 行逐字节不变（既有 golden 不受影响）
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import fr_check, fr_dump
from tools.fr_gen import tbl

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sha():
    return tbl.tbl_sha256(tbl.parse(
        open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read()))


def _sess(rows):
    """单帧会话（rows 是 canonical 文本行列表，dt/s_crc/d_crc 自动补）。"""
    body = "".join(r + "\n" for r in rows)
    return fr_dump.fs.parse_text(
        "frb1 640 480 " + _sha() + " base 1\nframe 0\ndt 0.016000\n"
        + body + "s_crc 0\nd_crc 7\n")


def _geo(text):
    s = fr_dump.fs.parse_text(text)
    imgs, quads = fr_dump._asset_table(s)
    return fr_dump._geo_annotate(fr_dump.fs.dump_text(s), imgs, quads)


# ---- 算例 A/B：手算数字（提案 §4.3，与 fr_dump 的实现互相独立）-----------

def test_case_a_rotation_45():
    """48×48、支点 (24,24)、锚点 (100,100)、rot=π/4、无缩放。
    四角 (100,66.0589)(133.9411,100)(100,133.9411)(66.0589,100)；
    e0 长 48 且方向 45°（= rot）、e3 长 48 且方向 135°（= rot+90°）、正交残差 0。"""
    s = _sess(["asset image 1 48 48 00",
               "draw 1 0 100 100 0.785398 1 1 24 24 255 255 255 255"])
    line = [l for l in fr_dump._geo_annotate(
        fr_dump.fs.dump_text(s), *_asset(s)).split("\n") if l.startswith("# geo:")][0]
    assert "at=100.000000,100.000000 rot=0.785398" in line
    assert "deg=45.0000" in line
    # 四角（%.2f）——与提案 §4.3 算例 A 的四个坐标逐点相同
    assert "c=(100.00,66.06)(133.94,100.00)(100.00,133.94)(66.06,100.00)" in line
    assert "len=48.00,48.00" in line
    assert "ortho=0.000000" in line
    # I1：支点落在锚点——p=(ox,oy) 时 du=dv=0，投影恰为 (x,y)
    px, py = 24, 24               # 这里取的就是 (ox,oy)，故 du=dv=0
    cs = sn = math.cos(math.pi / 4)
    du, dv = px - 24, py - 24
    qx = cs * 1 * du - sn * 1 * dv + 100
    qy = sn * 1 * du + cs * 1 * dv + 100
    assert abs(qx - 100) < 1e-12 and abs(qy - 100) < 1e-12


def test_case_b_nonuniform_scale_keeps_axis():
    """非等比缩放 sx=2：边长翻倍但 e0 方向仍是 rot（= π/2）——缩放不污染轴向。"""
    s = _sess(["asset image 1 48 48 00",
               "draw 1 0 200 100 1.570796 2 1 24 24 255 255 255 255"])
    line = [l for l in fr_dump._geo_annotate(
        fr_dump.fs.dump_text(s), *_asset(s)).split("\n") if l.startswith("# geo:")][0]
    assert "deg=90.0000" in line
    assert "c=(224.00,52.00)(224.00,148.00)(176.00,148.00)(176.00,52.00)" in line
    assert "len=96.00,48.00" in line          # ‖e0‖=qw·sx=48·2、‖e3‖=qh·sy=48·1
    assert "ortho=0.000000" in line


def _asset(s):
    return fr_dump._asset_table(s)


# ---- 算例 C：剪切必须留痕 ------------------------------------------------

def test_case_c_shear_requires_err():
    """剪切不可表达 → 产出端发 err "affine:shear <残差>"，且判据能命中它。
    残差按 §5.1 的公式算：A=[[1,0.3],[0,1]] → |col0·col1| / (‖col0‖‖col1‖)。"""
    col0, col1 = (1.0, 0.0), (0.3, 1.0)
    ortho = abs(col0[0] * col1[0] + col0[1] * col1[1]) / (
        math.hypot(*col0) * math.hypot(*col1))
    # 0.3/√1.09 = 0.28734789（提案 §4.3 写的 0.287326 是手算的近似值）
    assert abs(ortho - 0.28734789) < 1e-8
    s = _sess(['err "affine:shear %.6f"' % ortho])
    lines = fr_dump.fs.dump_text(s).split("\n")
    # err 属 log 段：不进 d_crc（d_crc 仍是建流时的 7），也不影响 out 行集
    assert any(l.startswith('err "affine:shear 0.287348"') for l in lines)
    ok = fr_check._run_checks(lines, [("CHECK", 'err "affine:shear', 1)])
    assert ok == []
    # 反例：同一帧若把 err 静默吞掉，判据必须红
    bad = fr_check._run_checks([l for l in lines if not l.startswith("err")],
                               [("CHECK", 'err "affine:shear', 1)])
    assert bad and "未命中" in bad[0]


# ---- 三个注入缺陷：判据必须会红（§3.3）----------------------------------

_PAT_ROT = "draw 3 0 100.000000 100.000000 0.785398"
_PAT_PIVOT = "24.000000 24.000000"


def _draw(rot="0.785398", ox="24", oy="24"):
    return "draw 3 0 100 100 %s 1 1 %s %s 255 255 255 255" % (rot, ox, oy)


def test_defect_degrees_instead_of_radians_turns_red():
    lines = fr_dump.fs.dump_text(_sess(["asset image 3 48 48 00",
                                       _draw(rot="45.000000")])).split("\n")
    assert fr_check._run_checks(lines, [("CHECK", _PAT_ROT, 1)])


def test_defect_sign_flip_turns_red():
    lines = fr_dump.fs.dump_text(_sess(["asset image 3 48 48 00",
                                       _draw(rot="-0.785398")])).split("\n")
    assert fr_check._run_checks(lines, [("CHECK", _PAT_ROT, 1)])


def test_defect_pivot_top_left_turns_red():
    lines = fr_dump.fs.dump_text(_sess(["asset image 3 48 48 00",
                                       _draw(ox="0", oy="0")])).split("\n")
    assert fr_check._run_checks(lines, [("CHECK", _PAT_PIVOT, 1)])


def test_defect_missing_rotation_turns_red():
    """该转的没转：rot 恒 0 → 判据不命中。"""
    lines = fr_dump.fs.dump_text(_sess(["asset image 3 48 48 00",
                                       _draw(rot="0.000000")])).split("\n")
    assert fr_check._run_checks(lines, [("CHECK", _PAT_ROT, 1)])


def test_good_stream_passes_same_criteria():
    """同一条判据对正确流必须全绿——否则上面的"红"只是判据写错了。"""
    lines = fr_dump.fs.dump_text(_sess(["asset image 3 48 48 00",
                                       _draw()])).split("\n")
    assert fr_check._run_checks(lines, [("CHECK", _PAT_ROT, 1),
                                        ("CHECK", _PAT_PIVOT, 1)]) == []


# ---- fr_check --geo：判据可引用 # geo: 行 --------------------------------

def test_fr_check_geo_flag_binds_geo_line(monkeypatch, capsys, tmp_path):
    """--geo 让判据能锚 CHECK-NEXT 的 # geo: 行（不开则那行不存在）。"""
    s = _sess(["asset image 1 48 48 00",
               "draw 1 0 100 100 0.785398 1 1 24 24 255 255 255 255"])
    monkeypatch.setattr(fr_check, "_load_raw", lambda p: b"stub")
    monkeypatch.setattr(fr_check, "_builtin", lambda raw, strict: (s, []))
    checks = tmp_path / "c.txt"
    checks.write_text("CHECK: draw 1 0 100.000000 100.000000 0.785398\n"
                      "CHECK-NEXT: # geo: d1 tex=1 at=100.000000,100.000000\n"
                      "CHECK: len=48.00,48.00 ortho=0.000000\n",
                      encoding="utf-8")
    assert fr_check.main(["x.fr", str(checks), "--geo"]) == 0
    out = capsys.readouterr().out
    assert "CHECK OK" in out
    # 不开 --geo：# geo: 行不在判据面 → CHECK-NEXT 必须落空
    assert fr_check.main(["x.fr", str(checks)]) == 1


def test_geo_rot0_line_unchanged():
    """rot=0 的 rect= 行形态保持逐字节不变（既有判据与 golden 不受影响）。"""
    s = _sess(["asset image 1 128 128 00",
               "draw 1 0 40 40 0 0.25 0.25 0 0 255 255 255 255"])
    line = [l for l in fr_dump._geo_annotate(
        fr_dump.fs.dump_text(s), *_asset(s)).split("\n") if l.startswith("# geo:")][0]
    assert line == "# geo: d1 tex=1 rect=40.00,40.00 32.00x32.00（img 128x128 @0.25）"