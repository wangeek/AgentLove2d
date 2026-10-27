# tests/test_dump.py
"""fr-dump CLI 薄壳回归（B3a Task 1）：子进程跑真脚本，验双输入一致、
--stats 摘要块、--frames 选帧（cmnt 丢弃 + 帧号重排连续）、坏文件 rc=1。

编码纪律：fr_dump 向 stdout 写 UTF-8 **字节**（字节精确是判据），_run 禁用
text=True——父进程按 cp936 解码 UTF-8 会把中文 cmnt 变 mojibake；
断言一律字节级比较，或显式 .decode("utf-8") 后做文本语义断言。
"""
import os, subprocess, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(*args):
    return subprocess.run([sys.executable, os.path.join(_ROOT, "tools", "fr_dump.py"), *args],
                          capture_output=True, cwd=_ROOT)


def _golden_paths():
    return (os.path.join(_ROOT, "tests", "golden", "sample.fr"),
            os.path.join(_ROOT, "tests", "golden", "sample.frb"))


def test_dual_input_identical_dump():
    fr, frb = _golden_paths()
    r1 = _run(fr)
    r2 = _run(frb)
    assert r1.returncode == 0 and r2.returncode == 0, (r1.stderr, r2.stderr)
    assert r1.stdout == r2.stdout                 # 双输入同一 dump（字节级）
    assert r1.stdout == open(fr, "rb").read()     # 无 --stats 时 = canonical 原文


def test_stats_block():
    r = _run(_golden_paths()[0], "--stats")
    assert r.returncode == 0, r.stderr
    out = r.stdout.decode("utf-8")
    assert "# frames=2" in out and "# op draw: 1" in out


def test_frames_filter():
    fr, _ = _golden_paths()
    r = _run(fr, "--frames", "1-1")
    assert r.returncode == 0, r.stderr
    out = r.stdout.decode("utf-8")
    lines = out.split("\n")
    assert "frame 0" in lines and "frame 1" not in lines  # 帧号重排连续
    assert not any(l.startswith("cmnt ") for l in lines)  # 过滤视图丢 cmnt
    # a-b 按 canonical 输出里的帧号（非 entry 索引——golden 首条 entry 是
    # cmnt，两种数法差 1）：内容必须确为原 frame 1 的 3 行（dt/ev/call）
    gold = open(fr, encoding="utf-8").read().split("\n")
    i1 = gold.index("frame 1")
    i_end = next(j for j in range(i1 + 1, len(gold)) if gold[j].startswith("cmnt "))
    expected = gold[0] + "\nframe 0\n" + "\n".join(gold[i1 + 1:i_end]) + "\n"
    assert out == expected


def test_bad_file(tmp_path):
    r = _run(os.path.join(str(tmp_path), "nope.fr"))
    assert r.returncode == 1
