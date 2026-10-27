# tests/test_render.py —— B4 阶段三 Task 3：拓扑 B 离线回放（fr-render）
#
# B4-2 验收线第二分句闭环判据：live tee 会话验证帧的 Canvas CRC（stdout
# `D_CRC 3 <crc>`）与同一流文件离线回放（fr_render 驱动 fork love.exe 的
# --offline-replay：读流 → C 解码/解析 → capture_replay 同路径执行 →
# Canvas 回读 CRC）一致；.fr/.frb 双形态一致；坏流（截断 .frb）rc≠0 且
# 错误含偏移；末帧三采样像素 == live 验证帧。
#
# D_CRC 口径：`D_CRC n <crc>` = 前 n 个帧块执行后画布 ImageData 的
# CRC32（0xEDB88320，l0/walker.lua 同构）——live 验证发生在第 3 帧
# （帧计数与 tee 会话 0 起帧块的 n=blocks 对齐：前 3 块 = counters 1..3）。
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORK_LOVE = os.path.join(_ROOT, "megasource", "build115", "love", "Release", "love.exe")
DEMO = os.path.join(_ROOT, "megasource", "libs", "love", "demo")
FR_RENDER = os.path.join(_ROOT, "tools", "fr_render.py")
FR_AS = os.path.join(_ROOT, "tools", "fr_as.py")


def _tbl_sha():
    from tools.fr_gen import tbl  # noqa: E402  判据链：cmd.tbl 指纹现算
    with open(os.path.join(_ROOT, "tables", "cmd.tbl"), encoding="utf-8") as f:
        return tbl.tbl_sha256(tbl.parse(f.read()))


def _run_live_tee(out_path):
    """live tee₁ 会话（真字节资产链，test_capture 同款参数）。"""
    env = os.environ.copy()
    env["FR_CAPTURE"] = "1"
    return subprocess.run(
        [FORK_LOVE, DEMO, "--out", str(out_path), "--sha", _tbl_sha(), "--seed", "3056735"],
        capture_output=True, timeout=60, env=env, cwd=_ROOT)


def _fr_render(path, timeout=120):
    """python tools/fr_render.py <path>（bytes 纪律由 CLI 内部执行）。"""
    return subprocess.run([sys.executable, FR_RENDER, str(path)],
                          capture_output=True, timeout=timeout, cwd=_ROOT)


def _d_crc_map(text):
    """stdout 文本 → {frame: crc}（D_CRC n crc 行）。"""
    m = {}
    for ln in text.splitlines():
        t = ln.split()
        if len(t) == 3 and t[0] == "D_CRC":
            m[int(t[1])] = t[2]
    return m


def _pixel_lines(text):
    return [ln for ln in text.splitlines() if ln.startswith("PIXEL ")]


def test_topology_b_d_crc_match(tmp_path):
    """闭环判据：live tee 的 D_CRC 3 == fr_render(.fr) 的 D_CRC 3（拓扑 B 与
    tee₂ 一致）；fr-as 转 .frb 后 fr_render 同 CRC（双形态一致）。"""
    live_fr = tmp_path / "live.fr"
    r = _run_live_tee(live_fr)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    live_map = _d_crc_map(r.stdout.decode("utf-8"))
    assert live_map.get(3) is not None, (r.stdout, r.stderr, "live 验证帧缺 D_CRC 3")

    rr = _fr_render(live_fr)
    assert rr.returncode == 0, (rr.returncode, rr.stdout, rr.stderr)
    off_map = _d_crc_map(rr.stdout.decode("utf-8"))
    assert off_map.get(3) == live_map[3], \
        (off_map, live_map, "离线（拓扑 B）与 live（tee₂）第 3 帧画布 CRC 不一致")

    live_frb = tmp_path / "live.frb"
    asm = subprocess.run([sys.executable, FR_AS, str(live_fr), "-o", str(live_frb)],
                         capture_output=True, cwd=_ROOT)
    assert asm.returncode == 0, asm.stderr
    rr2 = _fr_render(live_frb)
    assert rr2.returncode == 0, (rr2.returncode, rr2.stdout, rr2.stderr)
    assert _d_crc_map(rr2.stdout.decode("utf-8")).get(3) == live_map[3], \
        "二进制形态（.frb）与文本形态（.fr）离线回放 CRC 不一致"


def test_render_bad_stream(tmp_path):
    """坏流：截断 .frb → rc≠0 且错误信息含偏移（off）。"""
    live_fr = tmp_path / "live.fr"
    r = _run_live_tee(live_fr)
    assert r.returncode == 0, (r.returncode, r.stderr)
    frb = tmp_path / "live.frb"
    asm = subprocess.run([sys.executable, FR_AS, str(live_fr), "-o", str(frb)],
                         capture_output=True, cwd=_ROOT)
    assert asm.returncode == 0, asm.stderr

    bad = tmp_path / "bad.frb"
    bad.write_bytes(frb.read_bytes()[:-10])
    rr = _fr_render(bad)
    assert rr.returncode != 0, (rr.returncode, rr.stdout, "截断流不得 rc=0")
    err = rr.stderr.decode("utf-8", "replace")
    assert "off" in err, (err, "错误信息缺偏移（off）")


def test_render_pixel_samples(tmp_path):
    """离线末帧三采样像素 == live 验证帧（黑底/红方块/红条）。"""
    live_fr = tmp_path / "live.fr"
    r = _run_live_tee(live_fr)
    assert r.returncode == 0, (r.returncode, r.stderr)
    live_px = _pixel_lines(r.stdout.decode("utf-8"))
    assert len(live_px) == 3, (live_px, "live 验证帧应有三条 PIXEL 行")

    rr = _fr_render(live_fr)
    assert rr.returncode == 0, (rr.returncode, rr.stdout, rr.stderr)
    assert _pixel_lines(rr.stdout.decode("utf-8")) == live_px, \
        (rr.stdout, "离线采样像素与 live 验证帧不一致")
