# tests/test_l0.py —— L0（原版 LÖVE 11.5 headless）骨架 + fr.lua 跨语言对拍
# love.exe 是 GUI 子系统：stdout/stderr 用管道句柄继承（B0 已实验验证），
# 抓 bytes 后显式 decode("utf-8")；print 输出走 CRT 文本模式（实测 CRLF），
# 故按 splitlines() 归一。30s 超时守卫：headless 卡死（如错误弹窗）当场爆。
import os
import subprocess

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOVE = os.path.join(_ROOT, "love2d", "love-11.5-win64", "love.exe")


def _run_love(args, timeout=30):
    return subprocess.run([LOVE, os.path.join(_ROOT, "l0")] + args,
                          capture_output=True, timeout=timeout, cwd=_ROOT)


def _expected_lines():
    from tools import fr_codec_gen as fc
    return [fc.render_line(op, dict(f)) for op, f in fc.self_test_samples()]


def test_fr_ops_lua_generated():
    src = open(os.path.join(_ROOT, "l0", "fr_ops.lua"), encoding="utf-8").read()
    assert "draw" in src and "s_crc" in src          # 生成物存在且含首尾 op


def test_selftest_cross_language():
    r = _run_love(["--selftest"])
    assert r.returncode == 0, (r.returncode, r.stderr)
    got = [l for l in r.stdout.decode("utf-8").splitlines() if l.strip()]
    want = _expected_lines()
    assert len(got) == len(want), (len(got), len(want), r.stderr)
    for i, (g, w) in enumerate(zip(got, want)):
        assert g == w, "第 %d 行首差异:\n  love:   %r\n  python: %r" % (i, g, w)


def _run_demo(args, timeout=30):
    r = _run_love(args, timeout=timeout)
    assert r.returncode == 0, (r.returncode, r.stderr)
    return [l for l in r.stdout.decode("utf-8").splitlines() if l.strip()]


def test_demo_single_frame():
    # --demo = 行级验证模式：产出行文本逐行 print（会话组装随 Task 3）
    from tools.fr_gen.quantize import qf

    lines = _run_demo(["--demo", "--frames", "1", "--fixed-dt", "0.016667"])

    # 资产行仅首帧重放（frame 0 = checkpoint）：image → font 有序
    assert "asset image 1 32 32 00010203" in lines
    assert "asset font 2 14.000000 00010203" in lines
    assert lines.index("asset image 1 32 32 00010203") < \
        lines.index("asset font 2 14.000000 00010203")

    # dt 每帧一条；out 段首行 clear
    assert lines.count("dt 0.016667") == 1
    assert "clear 0 0 0 255" in lines

    # draw：坐标为变换栈就地结算值——Python 侧按 qf 链路复算，不手抄。
    # hero.x = 10.0 + 60.0*dt（update 一步）；qf 域上 token 解析值与期望精确相等。
    draw = [l for l in lines if l.startswith("draw ")]
    assert len(draw) == 1
    toks = draw[0].split(" ")            # draw tex quad x y rot sx sy ox oy r g b a
    want_x = qf(10.0 + qf(60.0 * qf(0.016667)))
    assert float(toks[3]) == want_x, (toks[3], want_x)

    # print：text 字段 = L0（引号内字面量，token[2]）
    prints = [l for l in lines if l.startswith("print ")]
    assert len(prints) == 1 and prints[0].split(" ")[2] == '"L0"', prints

    # rectangle → 规范 op 名 rect（fr_ops 单一真源）
    assert sum(1 for l in lines if l.startswith("rect ")) == 1
