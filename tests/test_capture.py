# tests/test_capture.py —— B4-2 Task 2：fork（fr-capture 分支）捕获基础设施 + clear 端到端
# 首次 capture-then-replay 实证：FR_CAPTURE=1 时 w_clear 抑制真执行只记行，
# present 钩回放行缓冲上屏；Canvas 回读（render-to-texture，不依赖主屏交换）
# 断言像素=红。开关未设 → 同 demo 真 clear，行为等价回归。
#
# love.exe 是 GUI 子系统：stdout/stderr 用管道句柄继承（test_l0 同款纪律），
# 抓 bytes 后显式 decode("utf-8")，按 splitlines() 归一；超时守卫当场爆。
import os
import subprocess

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORK_LOVE = os.path.join(_ROOT, "megasource", "build115", "love", "Release", "love.exe")
DEMO = os.path.join(_ROOT, "megasource", "libs", "love", "demo")


def _run_demo(env_capture, timeout=60):
    env = os.environ.copy()
    if env_capture:
        env["FR_CAPTURE"] = "1"
    else:
        env.pop("FR_CAPTURE", None)
    return subprocess.run([FORK_LOVE, DEMO], capture_output=True,
                          timeout=timeout, env=env, cwd=_ROOT)


def _out_lines(r):
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    return r.stdout.decode("utf-8").splitlines()


def test_capture_replay_red_pixel():
    """测试 1：FR_CAPTURE=1 → 抑制+记录+回放，Canvas 像素=红（capture-then-replay 实证）。"""
    r = _run_demo(env_capture=True)
    lines = _out_lines(r)
    assert "PIXEL 1 0 0" in lines, (lines, r.stderr)


def test_capture_off_real_clear_regression():
    """测试 2：开关未设 → 真 clear 执行，像素同红（行为等价）；会话缓冲为空无行。"""
    r = _run_demo(env_capture=False)
    lines = _out_lines(r)
    assert "PIXEL 1 0 0" in lines, (lines, r.stderr)
    assert "clear 1 0 0 255" not in lines, lines


def test_capture_take_session_has_clear_row():
    """测试 3：开关开 → _frTakeSession 行缓冲含 `clear 1 0 0 255`（.fr 规范形，cmd.tbl:32）。"""
    r = _run_demo(env_capture=True)
    lines = _out_lines(r)
    assert "clear 1 0 0 255" in lines, (lines, r.stderr)
