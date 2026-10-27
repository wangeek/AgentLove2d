# tests/test_l0.py —— L0（原版 LÖVE 11.5 headless）骨架 + fr.lua 跨语言对拍
# love.exe 是 GUI 子系统：stdout/stderr 用管道句柄继承（B0 已实验验证），
# 抓 bytes 后显式 decode("utf-8")；print 输出走 CRT 文本模式（实测 CRLF），
# 故按 splitlines() 归一。30s 超时守卫：headless 卡死（如错误弹窗）当场爆。
import os
import subprocess
import sys

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


def test_demo_single_frame(tmp_path):
    # Task 2 行级验证移植到会话产出（Task 3 起 --demo 写文件不打印）：
    # 断言全部落在 frame 0 块内。
    from tools.fr_gen.quantize import qf

    out = str(tmp_path / "one.fr")
    _run_demo_session(out, frames=1)
    lines = open(out, encoding="utf-8").read().splitlines()

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


# ---------------- Task 3：run loop（排干快照）+ 状态走查器 + 会话组装 ----------------

def _tbl_sha():
    from tools.fr_gen import tbl
    with open(os.path.join(_ROOT, "tables", "cmd.tbl"), encoding="utf-8") as f:
        return tbl.tbl_sha256(tbl.parse(f.read()))


def _run_demo_session(out_path, frames=4):
    """标准 demo 会话产出：固定 dt、真表指纹、固定 seed；帧数缺省 4（含注入）。"""
    r = _run_love(["--demo", "--frames", str(frames), "--fixed-dt", "0.016667",
                   "--sha", _tbl_sha(), "--seed", "3056735", "--out", out_path])
    assert r.returncode == 0, (r.returncode, r.stderr)


def test_demo_session_assembly(tmp_path):
    # 会话组装：头行 + cmnt + frame 块（帧内行序、注入事件、CALL 链、walker st、
    # CRC 交叉核对）；替换 Task 2 的行打印——demo 升级为文件产出。
    import zlib
    from tools.fr_gen import tbl

    with open(os.path.join(_ROOT, "tables", "cmd.tbl"), encoding="utf-8") as f:
        sec = {r["op"]: r["section"] for r in tbl.parse(f.read())}
    order = {"head": 0, "in": 1, "log": 2, "out": 3, "end": 4}

    out = str(tmp_path / "s.fr")
    _run_demo_session(out)
    lines = open(out, encoding="utf-8").read().splitlines()

    # 头行（loglvl=base、seed 走参数）+ cmnt 固定文本 + 帧号连续 0..3
    assert lines[0] == "frb1 640 480 %s base 3056735" % _tbl_sha(), lines[0]
    assert lines[1] == "cmnt L0 demo session"
    assert [l for l in lines if l.startswith("frame ")] == \
        ["frame 0", "frame 1", "frame 2", "frame 3"]

    # 帧 2：注入 keypressed（src=2）→ handler 直调 on_key 产 CALL 行（depth=1）
    assert 'ev 0 "keypressed" 2 3 str "return" str "return" bool 0' in lines
    calls = [l for l in lines if l.startswith("call ")]
    assert len(calls) == 1 and calls[0].startswith('call 1 "on_key" 1 3 '), calls

    # 帧 3：注入 quit（src=2、无实参）——帧照常闭合后循环终止
    assert 'ev 0 "quit" 2 0' in lines

    # st：obj=0 语义样机哨兵 + 点路径（含 hero.x）
    sts = [l for l in lines if l.startswith("st ")]
    assert sts and all(l.split(" ")[1] == "0" for l in sts), sts
    assert any('"hero.x"' in l for l in sts), sts

    # 帧内行序（拍平；段归属由元数据承载）：dt → asset(仅帧0) → in → log → out → end
    out_ops = {op for op, s in sec.items() if s == "out"}
    frames, i = [], 1
    while i < len(lines):
        if lines[i].startswith("cmnt "):    # cmnt 可驻留任意两帧之间，跳过
            i += 1
            continue
        assert lines[i] == "frame %d" % len(frames), lines[i]
        block, j = [], i + 1
        while j < len(lines) and not lines[j].startswith("frame "):
            block.append(lines[j])
            j += 1
        # dt 每帧首行；末两行恒 s_crc/d_crc；段序单调不回退；asset 仅帧 0
        assert block[0].startswith("dt "), block[0]
        assert block[-2].startswith("s_crc ") and block[-1].startswith("d_crc "), block[-2:]
        seq = [order[sec[b.split(" ")[0]]] for b in block]
        assert seq == sorted(seq), block
        n_asset = sum(1 for b in block if b.startswith("asset "))
        assert (n_asset == 2) if frames == [] else (n_asset == 0), block
        st_l = [b for b in block if b.startswith("st ")]
        out_l = [b for b in block if b.split(" ")[0] in out_ops]
        frames.append((st_l, out_l,
                       int(block[-2].split(" ")[1]), int(block[-1].split(" ")[1])))
        i = j
    assert len(frames) == 4

    # CRC32 跨语言对拍：s_crc=st 行文本拼接、d_crc=out 行文本拼接（Python zlib 权威）
    for st_l, out_l, s_crc, d_crc in frames:
        assert s_crc == zlib.crc32("\n".join(st_l).encode("utf-8")), (s_crc, st_l)
        assert d_crc == zlib.crc32("\n".join(out_l).encode("utf-8")), (d_crc, out_l)
        assert s_crc != 0 and d_crc != 0

    # 缺 --sha → rc=2（sha 是会话头必填元数据，不写死当前表指纹）
    r = _run_love(["--demo", "--frames", "1", "--fixed-dt", "0.016667",
                   "--out", str(tmp_path / "x.fr")])
    assert r.returncode == 2, (r.returncode, r.stderr)


def test_demo_check_and_roundtrip(tmp_path):
    # fr_check 内置校验（canonical 幂等 + sha 对账）rc=0；fr-as → fr-dis 双向回转
    # 与原产物逐字节一致（.frb 薄壳不破内容）。
    out = str(tmp_path / "s.fr")
    _run_demo_session(out)

    chk = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "tools", "fr_check.py"), out],
        capture_output=True, timeout=60, cwd=_ROOT)
    assert chk.returncode == 0, (chk.stdout, chk.stderr)

    frb, back = str(tmp_path / "s.frb"), str(tmp_path / "s_back.fr")
    asm = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "tools", "fr_as.py"), out, "-o", frb],
        capture_output=True, cwd=_ROOT)
    assert asm.returncode == 0, asm.stderr
    dis = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "tools", "fr_dis.py"), frb, "-o", back],
        capture_output=True, cwd=_ROOT)
    assert dis.returncode == 0, dis.stderr
    with open(back, "rb") as f1, open(out, "rb") as f2:
        assert f1.read() == f2.read()


def test_demo_deterministic(tmp_path):
    # 确定性：固定 dt + 固定 cmnt + 固定注入脚本 → 两次产物逐字节一致
    a, b = str(tmp_path / "a.fr"), str(tmp_path / "b.fr")
    _run_demo_session(a)
    _run_demo_session(b)
    with open(a, "rb") as fa, open(b, "rb") as fb:
        assert fa.read() == fb.read()
