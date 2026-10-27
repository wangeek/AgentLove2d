# tests/test_capture.py —— B4-2 Task 2/3/4：fork（fr-capture 分支）捕获回归
#
# Task 2 遗产：clear 捕获 + Canvas 回读自证（capture-then-replay 实证）。
# Task 3 扩展：语义替代四件套（newImage/newFont/newCanvas/newQuad → 资产代理）
# + draw/print/rect 全帧捕获（getTransform 结算坐标）→ Canvas 多点像素回读
# （背景黑 / 方块区真红物化 / 红条）+ 会话行 qf 链复算断言。
# Task 4 扩展：tee₁ 会话写出（--out）——头行/首帧 qf 锚/fr_check/双向回转
# + 两次运行逐字节确定性。
# B4 阶段三扩展（Task 1/2）：资产登记真字节（image=ImageData 像素 hex、
# font=内嵌 Vera.ttf 字节）+ 真纹理物化（draw 回放消费登记字节，Canvas
# 方块区像素 = 真 ImageData 色红，非占位白）。
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


def _run_demo(env_capture, timeout=60, extra=None, env_extra=None):
    env = os.environ.copy()
    if env_capture:
        env["FR_CAPTURE"] = "1"
    else:
        env.pop("FR_CAPTURE", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([FORK_LOVE, DEMO] + (extra or []), capture_output=True,
                          timeout=timeout, env=env, cwd=_ROOT)


def _out_lines(r):
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    return r.stdout.decode("utf-8").splitlines()


# 验证帧三点（640x480 画布）：背景 / 方块区（hero 首帧 11,20 起 32x32，真
# ImageData 全红——物化后回读同色）/ 红条。
_POINTS = [(400, 100, 0, 0, 0), (20, 30, 255, 0, 0), (320, 468, 255, 0, 0)]


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
    """测试 1：FR_CAPTURE=1 → 全帧捕获回放，Canvas 多点像素：背景黑/方块真红物化/红条。"""
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

    # 资产行（B4 阶段三真字节口径）：image = ImageData 像素 RGBA8 hex
    #（32x32x4=4096B，全红 ff0000ff×1024）；font = 内嵌 Vera.ttf（65932B，
    # 首字节 TTT sfnt 版本 00 01 00 00 → hex 前缀 00010000）。
    img_ln = next(ln for ln in lines if ln.startswith("asset image 1 "))
    t = img_ln.split()
    assert t[:5] == ["asset", "image", "1", "32", "32"], img_ln
    assert len(t) == 6 and t[5] == "ff0000ff" * 1024, (img_ln[:80], len(t) > 5 and len(t[5]))

    font_ln = next(ln for ln in lines if ln.startswith("asset font 2 "))
    t = font_ln.split()
    assert t[:4] == ["asset", "font", "2", "14.000000"], font_ln
    assert len(t) == 5 and len(t[4]) == 2 * 65932, (font_ln[:80], len(t) > 4 and len(t[4]))
    assert t[4].startswith("00010000"), font_ln[:80]

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


def test_capture_materialize_semantics_documented():
    """测试 4：真纹理物化语义自证——draw 回放的方块红来自登记 ImageData 字节的
    真物化（B4 阶段三），非占位伪色；占位路径仅未登记 id 回退时可达。"""
    # 该性质由测试 1/2 的 (20,30)=红 双向覆盖（捕获版=物化真纹理，开关关版=
    # 真 Image 同字节同色）。独立成测试名以固定验收语义：伪色映射仅为回退，
    # 变更登记字节口径须同时改 kernel/main.lua 的等价基准。
    r = _run_demo(env_capture=True)
    lines = _out_lines(r)
    got = _pixel_map(lines)
    assert got.get((20, 30)) == (255, 0, 0), (lines, "id=1 物化非真红：登记字节或物化链路漂移")


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


# ---------------- B6 Task 1/1b：状态 CRC 档（end 段 s_crc） ----------------

# 口径裁定（Task 1b，D8"内核 VM 唯一进堆镜像范围"）：s_crc = 注册状态根
#（demo 登记 kernel.state）可达子图的 CRC——录制/重演两进程的 args 表/解析
# 簿记表形态天然不同（Task 1 实证，曾 xfail），但 kernel.state 子图由同一
# 代码+同一事件序列构建，跨进程等值可达。子图外噪声不再进 s_crc。
import pytest

def _scrc_of_blocks(blocks):
    """帧块 → {帧号: crc}（每块恰一行 s_crc <u32十进制>）。"""
    m = {}
    for fi, rows in blocks.items():
        hits = [ln for ln in rows if ln.startswith("s_crc ")]
        assert len(hits) == 1, (fi, rows, "帧块应恰含一行 s_crc")
        t = hits[0].split()
        assert len(t) == 2, hits[0]
        crc = int(t[1])
        assert 0 <= crc <= 0xFFFFFFFF, (hits[0], "s_crc 应为 u32")
        m[fi] = crc
    return m


def test_state_crc_rows(tmp_path):
    """测试 11（B6 Task 1/1b）：注入 tee → 每帧块尾 `s_crc <u32十进制>` 行
    （out 行之后，end 段；口径 = kernel.state 可达子图 CRC）；帧 3 ≠ 帧 0
    （tick/hero.x/clicks 状态在变）；s_crc 行 canonical（fr_check 过）。"""
    out = str(tmp_path / "scrc.fr")
    r = _run_demo(env_capture=True,
                  extra=_tee_args(out) + ["--inject-click", "200,100",
                                          "--inject-key", "return"])
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    with open(out, "rb") as f:
        lines = f.read().decode("utf-8").splitlines()
    blocks = _frame_blocks(lines)
    m = _scrc_of_blocks(blocks)
    assert set(m) == {0, 1, 2, 3}, m
    for fi, rows in blocks.items():
        assert rows[-1].startswith("s_crc "), (fi, rows[-3:], "s_crc 应为帧块尾行")
    assert m[3] != m[0], (m, "帧 3 与帧 0 状态子图 CRC 应不同（内核状态在变）")

    chk = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "tools", "fr_check.py"), out],
        capture_output=True, timeout=60, cwd=_ROOT)
    assert chk.returncode == 0, (chk.stdout, chk.stderr)


def test_state_crc_deterministic(tmp_path):
    """测试 12（B6 Task 1/1b）：同参双跑（不同 out 路径——路径串不进状态
    子图）→ 逐帧 s_crc 一致：子图递归记忆化序（数组部保序 + hash 部
    multiset）+ GC 载荷规范化（str/tab 槽只计 tag，地址位清零——ASLR
    不破确定性）。"""
    crcs = []
    for p in (str(tmp_path / "a.fr"), str(tmp_path / "b.fr")):
        r = _run_demo(env_capture=True,
                      extra=_tee_args(p) + ["--inject-click", "200,100",
                                            "--inject-key", "return"])
        assert r.returncode == 0, (r.returncode, r.stderr)
        with open(p, "rb") as f:
            blocks = _frame_blocks(f.read().decode("utf-8").splitlines())
        crcs.append(_scrc_of_blocks(blocks))
    assert crcs[0] == crcs[1], (crcs, "同参双跑 s_crc 不一致")


def test_state_crc_sim_replay(tmp_path):
    """测试 13（B6 Task 1b）：--sim 严格档重演 → 重演侧逐帧 s_crc 与录制
    一致（SIM_CRC <f> ok 全 ok——内核状态重演全对，用途 3）。s_crc 口径 =
    注册状态根（kernel.state）可达子图 CRC：子图由同一代码+事件序列构建，
    跨进程等值可达（全堆口径曾 xfail，Task 1 实证 argv/簿记噪声不可消除）。"""
    out = str(tmp_path / "sim_src.fr")
    r = _run_demo(env_capture=True,
                  extra=_tee_args(out) + ["--inject-click", "200,100",
                                          "--inject-key", "return"])
    assert r.returncode == 0, (r.returncode, r.stderr)
    rr = subprocess.run([sys.executable,
                         os.path.join(_ROOT, "tools", "fr_render.py"),
                         "--sim", out], capture_output=True, timeout=120,
                        cwd=_ROOT)
    assert rr.returncode == 0, (rr.returncode, rr.stdout, rr.stderr)
    got = [ln for ln in rr.stdout.decode("utf-8").splitlines()
           if ln.startswith("SIM_CRC ")]
    assert len(got) == 4, (got, "SIM_CRC 帧行数应 = 帧数 4")
    for i, ln in enumerate(got):
        assert ln == "SIM_CRC %d ok" % i, (ln, "帧 %d 重演 s_crc 不一致" % i)


# ---------------- B6 Task 2：diff 档（影子镜像 st 物理行，FR_LOGLEVEL=full） ----------------

def _log_rows(rows):
    """帧块行 → log 段行（st/err，full 级堆 diff 档产出，按块内原序）。"""
    return [ln for ln in rows if ln.startswith("st ") or ln.startswith("err ")]


def test_state_diff_rows(tmp_path):
    """测试 14（B6 Task 2）：FR_LOGLEVEL=full 注入 tee → 帧 0 首见全发
    （kernel.state/hero 全槽 + table 引用槽 err unsupported）、帧 1 增量
    （tick 脏槽 + clicks 首插扩容 rehash 行 + 点击子表全发 + hero.x 脏槽）；
    档位隔离（FR_LOGLEVEL 未设 → 无 st/err 行）；双跑逐字节一致；fr_check 过。"""
    out = str(tmp_path / "diff.fr")
    r = _run_demo(env_capture=True, env_extra={"FR_LOGLEVEL": "full"},
                  extra=_tee_args(out) + ["--inject-click", "200,100",
                                          "--inject-key", "return"])
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    with open(out, "rb") as f:
        lines = f.read().decode("utf-8").splitlines()
    blocks = _frame_blocks(lines)

    # 头行 loglvl=full（会话声明档位，fr_session 三档域）
    assert lines[0].split()[4] == "full", lines[0]

    # 帧 0 首见全发（收集点 = update 后 present，tick 已 +1）：根表（id=1）
    # 四槽——tick/banner 可序列化发 st，hero/clicks 槽为 table 引用 → err
    # st-unsupported（拍板：table 引用槽首版按 err 记，ref 形态留 B6+）
    log0 = _log_rows(blocks[0])
    assert 'st 1 "tick" num 1.000000' in log0, log0
    assert 'st 1 "banner" str "L0"' in log0, log0
    assert 'err "st-unsupported 1 hero tab"' in log0, log0
    assert 'err "st-unsupported 1 clicks tab"' in log0, log0
    # hero（id=3，clicks id=2 先分但空表无行）：三数值槽全发
    assert 'st 3 "hp" num 87.000000' in log0, log0
    dt = 0.016667
    assert 'st 3 "x" num %.6f' % qf(10.0 + 60.0 * dt) in log0, log0
    assert 'st 3 "y" num 20.000000' in log0, log0

    # 帧 1 增量：tick/hero.x 脏槽（qf 域）
    log1 = _log_rows(blocks[1])
    assert 'st 1 "tick" num 2.000000' in log1, log1
    assert 'st 3 "x" num %.6f' % qf(10.0 + 60.0 * dt * 2) in log1, log1
    # clicks 首插 {x=200,y=100}：LuaJIT 空表首插走 rehashtab（asize 0→3，
    # lj_tab.c:452）→ 表重建行 + 全槽重发；数组部下标 = 整数键原值
    #（clicks[1] 物理落 [1]，1-based Lua 数组空置 [0]——实测定形），槽为
    # table → err + 子表（id=4）全发 x/y
    assert 'err "st-rehash 2 3 0"' in log1, log1
    assert 'err "st-unsupported 2 [1] tab"' in log1, log1
    assert 'st 4 "x" num 200.000000' in log1, log1
    assert 'st 4 "y" num 100.000000' in log1, log1
    # 增量语义：帧 1 的 log 行整体少于帧 0（脏槽子集 + 新表）
    assert len(log1) < len(log0), (len(log0), len(log1), log0, log1)

    # 帧 2：banner 切 "KEY"（keypressed 注入）——str 值内容变化须检出
    #（diff 槽指纹对 str 补内容 CRC；CRC 档的 tag 位口径逮不住，自审登记）
    log2 = _log_rows(blocks[2])
    assert 'st 1 "banner" str "KEY"' in log2, log2
    assert 'st 1 "tick" num 3.000000' in log2, log2

    # 帧 3：只 tick/hero.x 在变（clicks 稳定无行）
    log3 = _log_rows(blocks[3])
    assert 'st 1 "tick" num 4.000000' in log3, log3
    assert not any(ln.startswith('st 4 ') for ln in log3), log3

    # st/err 行 canonical（cmd.tbl 签名：st obj u32 / key str / val variant）
    chk = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "tools", "fr_check.py"), out],
        capture_output=True, timeout=60, cwd=_ROOT)
    assert chk.returncode == 0, (chk.stdout, chk.stderr)

    # 档位隔离：FR_LOGLEVEL 未设 → 无 st/err 行（base 档不产 diff 行）
    out_base = str(tmp_path / "base.fr")
    r_base = _run_demo(env_capture=True,
                       extra=_tee_args(out_base) + ["--inject-click", "200,100",
                                                    "--inject-key", "return"])
    assert r_base.returncode == 0, (r_base.returncode, r_base.stderr)
    with open(out_base, "rb") as f:
        base_lines = f.read().decode("utf-8").splitlines()
    assert not any(ln.startswith("st ") or ln.startswith("err ")
                   for ln in base_lines), "base 档不应有 st/err 行"
    assert base_lines[0].split()[4] == "base", base_lines[0]

    # 双跑确定性（含 st/err 行与对象 id 分配序）
    out2 = str(tmp_path / "diff2.fr")
    r2 = _run_demo(env_capture=True, env_extra={"FR_LOGLEVEL": "full"},
                   extra=_tee_args(out2) + ["--inject-click", "200,100",
                                            "--inject-key", "return"])
    assert r2.returncode == 0, (r2.returncode, r2.stderr)
    with open(out, "rb") as fa, open(out2, "rb") as fb:
        assert fa.read() == fb.read(), "full 档两次运行不逐字节一致"


def test_state_diff_sim(tmp_path):
    """测试 15（B6 Task 2）：full 流 --sim（FR_LOGLEVEL=full 重演侧同档收集）
    → SIM 全 MATCH（st/err log 行纳入比对集后重演仍逐行一致——状态演化重演
    全对的强判据）；SIM_CRC ok；篡改 st 行 → MISMATCH（比对集确实含 st 的
    反向自证）。"""
    out = str(tmp_path / "sim.fr")
    r = _run_demo(env_capture=True, env_extra={"FR_LOGLEVEL": "full"},
                  extra=_tee_args(out) + ["--inject-click", "200,100",
                                          "--inject-key", "return"])
    assert r.returncode == 0, (r.returncode, r.stderr)

    env = os.environ.copy()
    env["FR_LOGLEVEL"] = "full"
    rr = subprocess.run([sys.executable,
                         os.path.join(_ROOT, "tools", "fr_render.py"),
                         "--sim", out], capture_output=True, timeout=120,
                        cwd=_ROOT, env=env)
    assert rr.returncode == 0, (rr.returncode, rr.stdout, rr.stderr)
    sim_lines = rr.stdout.decode("utf-8").splitlines()
    assert ("SIM %d MATCH" % 0) in sim_lines, sim_lines
    for i in range(4):
        assert ("SIM %d MATCH" % i) in sim_lines, sim_lines
        assert ("SIM_CRC %d ok" % i) in sim_lines, sim_lines
    assert "SIM SUMMARY 4 4 0 0" in sim_lines, sim_lines

    # 反向自证：篡改帧 0 的 st 行值 → 重演侧再生行与篡改行不符 → MISMATCH
    #（若 st 行不在比对集，篡改会被静默放过）
    with open(out, "rb") as f:
        raw = f.read().decode("utf-8")
    assert 'st 1 "tick" num 1.000000' in raw, raw[:400]
    mangled = raw.replace('st 1 "tick" num 1.000000', 'st 1 "tick" num 9.000000')
    mangled_path = str(tmp_path / "mangled.fr")
    with open(mangled_path, "wb") as f:
        f.write(mangled.encode("utf-8"))
    rm = subprocess.run([sys.executable,
                         os.path.join(_ROOT, "tools", "fr_render.py"),
                         "--sim", mangled_path], capture_output=True, timeout=120,
                        cwd=_ROOT, env=env)
    assert rm.returncode == 1, (rm.returncode, rm.stdout, rm.stderr)
    m_lines = rm.stdout.decode("utf-8").splitlines()
    assert any(ln.startswith("SIM 0 MISMATCH") for ln in m_lines), m_lines


# ---------------- B4 阶段三：真字节登记 + 真纹理物化 ----------------

def test_asset_real_bytes(tmp_path):
    """测试 7（阶段三 Task 1）：tee 会话资产行登记真字节——image 行 hex =
    ImageData 像素（4096B 全红）；font 行 hex = 内嵌 Vera.ttf（65932B）。"""
    out = str(tmp_path / "real.fr")
    r = _run_demo(env_capture=True, extra=_tee_args(out))
    assert r.returncode == 0, (r.returncode, r.stderr)

    with open(out, "rb") as f:
        lines = f.read().decode("utf-8").splitlines()

    img_ln = next(ln for ln in lines if ln.startswith("asset image 1 "))
    t = img_ln.split()
    assert t[:5] == ["asset", "image", "1", "32", "32"], img_ln[:80]
    assert len(t) == 6 and len(t[5]) == 8192, "image hex 应为 32x32x4 字节 = 8192 字符"
    assert t[5] == "ff0000ff" * 1024, "image 真字节应全红 ff0000ff（demo 全红 ImageData）"

    font_ln = next(ln for ln in lines if ln.startswith("asset font 2 "))
    t = font_ln.split()
    assert t[:4] == ["asset", "font", "2", "14.000000"], font_ln[:80]
    assert len(t) == 5 and len(t[4]) == 2 * 65932, "font hex 应为 Vera.ttf 65932 字节"
    assert t[4].startswith("00010000"), "Vera.ttf 首字节锚（sfnt 版本 00 01 00 00）"


def test_materialized_pixel():
    """测试 8（阶段三 Task 2）：真纹理物化——draw 回放消费登记字节，Canvas
    回读方块区 = 真 ImageData 色（红 255 0 0），非占位伪色白。"""
    r = _run_demo(env_capture=True)
    lines = _out_lines(r)
    got = _pixel_map(lines)
    assert got.get((20, 30)) == (255, 0, 0), \
        (lines, "方块区非真红：物化未生效（占位伪色 id=1→白？）")


# ---------------- B4 阶段三 Task 4：null Graphics（拓扑 C 无头） ----------------

def test_headless_tee_identical(tmp_path):
    """测试 9（阶段三 Task 4）：FR_HEADLESS=1 无窗（t.window=false）跑同 demo
    ——tee .fr 与有窗版逐字节一致。捕获层与窗口解耦的实证：行记录/资产登记/
    会话缓冲全 GL-free，无头仅跳过 GL 依赖的回放与 Canvas 回读（stdout 诊断，
    不进 .fr）。无头依赖边界见 fr_capture.h 头注。"""
    win_out, headless_out = str(tmp_path / "win.fr"), str(tmp_path / "headless.fr")
    r_win = _run_demo(env_capture=True, extra=_tee_args(win_out))
    assert r_win.returncode == 0, (r_win.returncode, r_win.stderr)

    r_hd = _run_demo(env_capture=True, extra=_tee_args(headless_out),
                     env_extra={"FR_HEADLESS": "1"})
    assert r_hd.returncode == 0, (r_hd.returncode, r_hd.stdout, r_hd.stderr,
                                  "无头跑挂：捕获层仍有 GL 依赖点未解耦")

    with open(win_out, "rb") as fa, open(headless_out, "rb") as fb:
        a, b = fa.read(), fb.read()
    assert a == b, (a[:200], b[:200], "无头 tee 与有窗 tee 不逐字节一致")

    # 无头边界自证：GL 依赖的验证帧回读（PIXEL/D_CRC）在无头下不发生
    hd_lines = r_hd.stdout.decode("utf-8").splitlines()
    assert not any(ln.startswith("PIXEL") for ln in hd_lines), hd_lines
    assert not any(ln.startswith("D_CRC") for ln in hd_lines), hd_lines
    # 有窗版照常回读（对照：差异只在 stdout 诊断，不在 .fr 流）
    assert "PIXELS 3 3" in r_win.stdout.decode("utf-8").splitlines()


# ---------------- B5 Task 1：事件捕获 + 事件驱动化（--inject-*） ----------------

def _frame_blocks(lines):
    """tee .fr 行列表 → {帧号: [帧块内行]}（frame N 定界）。"""
    blocks, cur = {}, None
    for ln in lines:
        if ln.startswith("frame "):
            cur = int(ln.split()[1])
            blocks[cur] = []
        elif cur is not None:
            blocks[cur].append(ln)
    return blocks


_CLICK_RECT = ("rect 0 196.000000 96.000000 8.000000 8.000000 0.000000 0.000000 "
               "1.000000 255 255 255 255")


def test_event_capture(tmp_path):
    """测试 10（B5 Task 1）：--inject-click 200,100 --inject-key return 注入 →
    tee .fr：帧 1 块 mousepressed ev 行（push 参数序 x y button istouch presses
    全 5 参、src=0、slot=0）+ 帧 1 out 点击标记 rect（左上 (x-4,y-4) 8x8 白）+
    帧 2 keypressed ev 行与 banner "KEY"；未注入帧 in 段为空（环境事件不混
    入）；ev 行 canonical（fr_check 过）；注入会话两次运行逐字节一致。"""
    out = str(tmp_path / "ev.fr")
    r = _run_demo(env_capture=True,
                  extra=_tee_args(out) + ["--inject-click", "200,100",
                                          "--inject-key", "return"])
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)

    with open(out, "rb") as f:
        lines = f.read().decode("utf-8").splitlines()
    blocks = _frame_blocks(lines)

    # 帧 1 in：mousepressed ev 行——注入 push 的 5 参在 poll 取出时全量落行
    assert ('ev 0 "mousepressed" 0 5 num 200.000000 num 100.000000 '
            "num 1.000000 bool 0 num 1.000000") in blocks[1], blocks[1]
    # 帧 1 out：点击标记 rect（8x8 白 fill，中心=点击点 → 左上 (196,96)）
    assert _CLICK_RECT in blocks[1], blocks[1]
    # 帧 1 banner 仍 "L0"（key 事件帧 2 才到——帧间因果时序锚）
    assert ('print 2 "L0" 12.000000 340.000000 0.000000 1.000000 1.000000 '
            "255 255 0 255") in blocks[1], blocks[1]

    # 帧 2 in：keypressed ev 行（镜像 OS 3 参形态 key scancode isrepeat）
    assert 'ev 0 "keypressed" 0 3 str "return" str "return" bool 0' in blocks[2], blocks[2]
    # 帧 2 out：banner 切 "KEY"；点击标记留存（clicks 状态跨帧）
    assert ('print 2 "KEY" 12.000000 340.000000 0.000000 1.000000 1.000000 '
            "255 255 0 255") in blocks[2], blocks[2]
    assert _CLICK_RECT in blocks[2], blocks[2]

    # 未注入帧（0/3）in 段为空：环境/连续事件（focus/visible/mousemoved…）
    # 不进流——tee 确定性口径（不注入则 in 段为空）
    for fi in (0, 3):
        assert not any(ln.startswith("ev ") for ln in blocks[fi]), blocks[fi]

    # ev 行 canonical：fr_check 全流校验（canonical 幂等 + sha 对账）过
    chk = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "tools", "fr_check.py"), out],
        capture_output=True, timeout=60, cwd=_ROOT)
    assert chk.returncode == 0, (chk.stdout, chk.stderr)

    # 注入确定性：同参数再跑一次，产物逐字节一致（注入帧号固定）
    out2 = str(tmp_path / "ev2.fr")
    r2 = _run_demo(env_capture=True,
                   extra=_tee_args(out2) + ["--inject-click", "200,100",
                                            "--inject-key", "return"])
    assert r2.returncode == 0, (r2.returncode, r2.stderr)
    with open(out, "rb") as fa, open(out2, "rb") as fb:
        assert fa.read() == fb.read(), "注入会话两次运行不逐字节一致"
