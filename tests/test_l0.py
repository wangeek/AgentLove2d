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
