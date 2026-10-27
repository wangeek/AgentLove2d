# tests/test_capture.py —— B4-2 Task 2/3/4：fork（fr-capture 分支）捕获回归
#
# Task 2 遗产：clear 捕获 + Canvas 回读自证（capture-then-replay 实证）。
# Task 3 扩展：语义替代四件套（newImage/newFont/newCanvas/newQuad → 资产代理）
# + draw/print/rect 全帧捕获（getTransform 结算坐标）→ Canvas 多点像素回读
# （背景黑 / 方块白占位 / 红条）+ 会话行 qf 链复算断言。
# Task 4 扩展：tee₁ 会话写出（--out）——头行/首帧 qf 锚/fr_check/双向回转
# + 两次运行逐字节确定性。
#
# love.exe 是 GUI 子系统：stdout/stderr 用管道句柄继承（test_l0 同款纪律），
# 抓 bytes 后显式 decode("utf-8")，按 splitlines() 归一；超时守卫当场爆。
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORK_LOVE = os.path.join(_ROOT, "megasource", "build115", "love", "Release", "love.exe")
DEMO = os.path.join(_ROOT, "megasource", "libs", "love", "demo")
sys.path.insert(0, _ROOT)

from tools.fr_gen.quantize import qf  # noqa: E402  判据链：坐标按 %.6f 域复算


def _run_demo(env_capture, timeout=60, extra=None):
    env = os.environ.copy()
    if env_capture:
        env["FR_CAPTURE"] = "1"
    else:
        env.pop("FR_CAPTURE", None)
    return subprocess.run([FORK_LOVE, DEMO] + (extra or []), capture_output=True,
                          timeout=timeout, env=env, cwd=_ROOT)


def _out_lines(r):
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    return r.stdout.decode("utf-8").splitlines()


# 验证帧三点（640x480 画布）：背景 / 方块区（hero 首帧 11,20 起 32x32） / 红条。
_POINTS = [(400, 100, 0, 0, 0), (20, 30, 255, 255, 255), (320, 468, 255, 0, 0)]


def _pixel_map(lines):
    """PIXEL x y r g b 行 → {(x,y): (r,g,b)}。"""
    m = {}
    for ln in lines:
        t = ln.split()
        if len(t) == 6 and t[0] == "PIXEL":
            m[(int(t[1]), int(t[2]))] = (int(t[3]), int(t[4]), int(t[5]))
    return m


def _assert_pixels(lines):
    """三点逐点断言 + demo 侧 PIXELS n pass 汇总行断言。"""
    got = _pixel_map(lines)
    for x, y, r, g, b in _POINTS:
        assert got.get((x, y)) == (r, g, b), (f"PIXEL {(x, y)}", got.get((x, y)), lines)
    assert "PIXELS 3 3" in lines, (lines, "PIXELS 汇总不符")


def test_capture_replay_full_frame_pixels():
    """测试 1：FR_CAPTURE=1 → 全帧捕获回放，Canvas 多点像素：背景黑/方块白占位/红条。"""
    r = _run_demo(env_capture=True)
    lines = _out_lines(r)
    _assert_pixels(lines)


def test_capture_off_real_draw_regression():
    """测试 2：开关未设 → 真执行（真 Image/Font/rectangle），三点像素同捕获版（行为等价）；会话缓冲为空。"""
    r = _run_demo(env_capture=False)
    lines = _out_lines(r)
    _assert_pixels(lines)
    assert not any(ln.startswith("draw 1 0") for ln in lines), lines
    assert not any(ln.startswith("clear") for ln in lines), lines


def test_capture_take_session_rows():
    """测试 3：开关开 → 会话行（3 帧 × clear/draw/print/rect），坐标 qf 链复算锚定。"""
    r = _run_demo(env_capture=True)
    lines = _out_lines(r)

    # 资产行（L0 口径：image 32x32 / font 14；ImageData 假数据模式 hex 记 "-"）
    assert "asset image 1 32 32 -" in lines, (lines, r.stderr)
    assert "asset font 2 14.000000 -" in lines, (lines, r.stderr)

    dt = 0.016667
    for k in (1, 2, 3):
        # kernel 固定 dt：hero.x = 10 + 60*dt*k，qf 域（%.6f）复算后锚整行
        x = qf(10.0 + 60.0 * dt * k)
        assert f"clear 0 0 0 255" in lines
        assert ("draw 1 0 %.6f 20.000000 0.000000 1.000000 1.000000 "
                "0.000000 0.000000 255 255 255 255" % x) in lines, (lines, r.stderr)
    assert ('print 2 "L0" 12.000000 340.000000 0.000000 1.000000 1.000000 '
            "255 255 0 255") in lines, (lines, r.stderr)
    assert ("rect 0 0.000000 456.000000 640.000000 24.000000 0.000000 0.000000 "
            "1.000000 255 0 0 255") in lines, (lines, r.stderr)

    # 计数：3 帧 × 4 op（会话行缓冲全会话累积）
    for prefix, n in (("clear ", 3), ("draw 1 0 ", 3), ("print 2 ", 3), ("rect 0 ", 3)):
        assert sum(1 for ln in lines if ln.startswith(prefix)) == n, (prefix, lines)


def test_capture_placeholder_semantics_documented():
    """测试 4：占位渲染语义自证——draw 回放的方块白来自 id→伪色映射（id=1→白），与真版等价。"""
    # 该性质由测试 1/2 的 (20,30)=白 双向覆盖（捕获版=伪色占位，开关关版=真白纹理）。
    # 独立成测试名以固定验收语义：伪色映射变更须同时改 kernel/main.lua 的等价基准。
    r = _run_demo(env_capture=True)
    lines = _out_lines(r)
    got = _pixel_map(lines)
    assert got.get((20, 30)) == (255, 255, 255), (lines, "id=1 占位非白：伪色映射口径漂移")


# ---------------- Task 4：tee₁ 会话写出（--out） ----------------

def _tbl_sha():
    from tools.fr_gen import tbl  # noqa: E402  判据链：cmd.tbl 指纹现算
    with open(os.path.join(_ROOT, "tables", "cmd.tbl"), encoding="utf-8") as f:
        return tbl.tbl_sha256(tbl.parse(f.read()))


def _tee_args(out_path):
    """tee₁ 标准参数：固定 dt/kernel 内置、真表指纹、固定 seed（test_l0 同款）；帧数缺省 4。"""
    return ["--out", out_path, "--sha", _tbl_sha(), "--seed", "3056735"]


def test_fork_tee_session(tmp_path):
    """测试 5：--out tee₁——头行形态 + 首帧 qf 锚 + fr_check rc=0 + fr-as→fr-dis
    双向逐字节；验证帧（frame 3）Canvas 回读与 tee 并存（stdout PIXELS 3 3）。"""
    out = str(tmp_path / "fork.fr")
    r = _run_demo(env_capture=True, extra=_tee_args(out))
    assert "PIXELS 3 3" in r.stdout.decode("utf-8").splitlines(), \
        (r.stdout, r.stderr, "验证帧 Canvas 回读未发生")

    with open(out, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    lines = text.splitlines()
    # ① 头行形态（loglvl=base、seed 走参数）
    assert lines[0] == "frb1 640 480 %s base 3056735" % _tbl_sha(), lines[0]
    assert lines[1].startswith("cmnt "), lines[1]
    # ② 首帧 qf 锚（hero.x = 10 + 60*0.016667，%.6f 域）+ 帧块连续 0..3
    assert "draw 1 0 11.000020" in text, (lines, "首帧 qf 锚缺失")
    assert [ln for ln in lines if ln.startswith("frame ")] == \
        ["frame 0", "frame 1", "frame 2", "frame 3"], lines

    # ③ fr_check 内置校验（canonical 幂等 + sha 对账）rc=0
    chk = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "tools", "fr_check.py"), out],
        capture_output=True, timeout=60, cwd=_ROOT)
    assert chk.returncode == 0, (chk.stdout, chk.stderr)

    # ④ fr-as → fr-dis 双向与原产物逐字节一致
    frb, back = str(tmp_path / "fork.frb"), str(tmp_path / "fork_back.fr")
    asm = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "tools", "fr_as.py"), out, "-o", frb],
        capture_output=True, cwd=_ROOT)
    assert asm.returncode == 0, asm.stderr
    dis = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "tools", "fr_dis.py"), frb, "-o", back],
        capture_output=True, cwd=_ROOT)
    assert dis.returncode == 0, dis.stderr
    with open(back, "rb") as f:
        assert f.read() == raw


def test_fork_tee_deterministic(tmp_path):
    """测试 6：tee 确定性——FIXED_DT 固定 + cmnt 固定 + 无随机 → 两次运行产物逐字节一致。"""
    a, b = str(tmp_path / "a.fr"), str(tmp_path / "b.fr")
    for p in (a, b):
        r = _run_demo(env_capture=True, extra=_tee_args(p))
        assert r.returncode == 0, (r.returncode, r.stderr)
    with open(a, "rb") as fa, open(b, "rb") as fb:
        assert fa.read() == fb.read()
