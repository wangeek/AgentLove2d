# tests/test_ctee_guard.py —— C 侧 tee 的写者护栏（缺陷 1/2/3，2026-11-18 事故事后修）
#
# 事故取证（docs/fr-agent-practice-report.md §6.1）：后启动的进程用 "wb" 截断了
# 另一个进程正在写的流，43,631 帧被静默抹掉，旧进程在 2.33GB 处续写，文件系统
# 补出 2.22GB 零区，最终 20.4GB 不可判定流。
#
# 三道护栏（本测试文件逐条钉死）：
#   1. FR_OUT 已存在 → 默认拒绝覆盖（需 FR_OVERWRITE=1）
#   2. 独占打开 → 同路径第二个写者打不开（共享冲突）
#   3. FR_MAX_MB → 体积封口（按 ftell 判定，支持小数便于测试）
import ctypes
import os
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORK_LOVE = os.path.join(_ROOT, "megasource", "build115", "love", "Release",
                         "love.exe")
DEMO = os.path.join(_ROOT, "megasource", "libs", "love", "demo")
sys.path.insert(0, _ROOT)


def _tbl_sha():
    from tools.fr_gen import tbl
    with open(os.path.join(_ROOT, "tables", "cmd.tbl"), encoding="utf-8") as f:
        return tbl.tbl_sha256(tbl.parse(f.read()))


def _run(out, extra_env=None, timeout=90):
    env = os.environ.copy()
    env.update(FR_CAPTURE="1", FR_OUT=out, FR_SHA=_tbl_sha(),
               FR_SEED="3056735", FR_HEADLESS="1")
    env.update(extra_env or {})
    return subprocess.run([FORK_LOVE, DEMO], capture_output=True,
                          timeout=timeout, env=env, cwd=_ROOT)


def _frames(path):
    if not os.path.isfile(path):
        return 0
    with open(path, "rb") as f:
        return sum(1 for ln in f if ln.startswith(b"frame "))


# ── 护栏 1：存在即拒绝覆盖 ──────────────────────────────────────────

def test_existing_stream_not_overwritten_by_default(tmp_path):
    """FR_OUT 已存在 → 不截断、不写入，stderr 明确告知（游戏照常跑）。"""
    out = tmp_path / "exists.fr"
    sentinel = b"SENTINEL-OLD-STREAM\n"
    out.write_bytes(sentinel)

    r = _run(str(out))
    assert r.returncode == 0, (r.returncode, r.stderr)
    assert out.read_bytes() == sentinel, "旧流被覆盖了（护栏 1 失效）"
    err = r.stderr.decode("utf-8", "replace")
    assert "拒绝覆盖" in err and "FR_OVERWRITE=1" in err, err


def test_overwrite_env_allows_truncation(tmp_path):
    """FR_OVERWRITE=1 → 显式允许覆盖（旧流被新流取代）。"""
    out = tmp_path / "ow.fr"
    out.write_bytes(b"OLD\n")

    r = _run(str(out), {"FR_OVERWRITE": "1"})
    assert r.returncode == 0, (r.returncode, r.stderr)
    data = out.read_bytes()
    assert data.startswith(b"frb1 "), data[:80]
    assert _frames(str(out)) >= 1


# ── 护栏 2：独占写者 ───────────────────────────────────────────────

def test_second_writer_rejected_by_exclusive_lock(tmp_path):
    """同路径已被独占打开时，第二个写者必须打不开并明确报错。

    用 CreateFileW(share=0) 在被测进程外占住文件，模拟"另一个写者正在写"。
    FR_OVERWRITE=1 放行覆盖判断，确保测到的是**锁**而不是护栏 1。"""
    out = tmp_path / "locked.fr"
    out.write_bytes(b"x")

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = ctypes.c_void_p
    GENERIC_WRITE, OPEN_ALWAYS, FILE_ATTR_NORMAL = 0x40000000, 4, 0x80
    handle = k32.CreateFileW(str(out), GENERIC_WRITE, 0, None, OPEN_ALWAYS,
                             FILE_ATTR_NORMAL, None)
    assert handle and handle != ctypes.c_void_p(-1).value, \
        "测试自身未能占住文件：%d" % ctypes.get_last_error()
    try:
        r = _run(str(out), {"FR_OVERWRITE": "1"})
    finally:
        k32.CloseHandle(ctypes.c_void_p(handle))

    assert r.returncode == 0, (r.returncode, r.stderr)
    err = r.stderr.decode("utf-8", "replace")
    assert "独占" in err or "已被其他进程" in err, err
    assert out.read_bytes() == b"x", "被拒绝的写者仍然改动了文件"


# ── 护栏 3：FR_MAX_MB 体积封口 ─────────────────────────────────────

def test_max_mb_caps_stream_size(tmp_path):
    """FR_MAX_MB=0.05（≈52KB）→ 远早于默认 4 帧就封口，且流仍可解析。"""
    out = tmp_path / "capped.fr"
    r = _run(str(out), {"FR_MAX_MB": "0.05"})
    assert r.returncode == 0, (r.returncode, r.stderr)
    err = r.stderr.decode("utf-8", "replace")
    assert "体积达上限" in err, err
    size = os.path.getsize(str(out))
    assert size < 300 * 1024, "体积封口未生效：%d 字节" % size
    assert _frames(str(out)) >= 1


def test_max_mb_absent_means_unlimited(tmp_path):
    """不设 FR_MAX_MB → 行为不变（回归：默认不封口，正常跑完）。"""
    out = tmp_path / "nolimit.fr"
    r = _run(str(out))
    assert r.returncode == 0, (r.returncode, r.stderr)
    assert "体积达上限" not in r.stderr.decode("utf-8", "replace")
    assert _frames(str(out)) >= 3
