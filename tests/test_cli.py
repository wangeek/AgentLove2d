# tests/test_cli.py
"""fr-as / fr-dis CLI 薄壳回归（B1 Task 4）：子进程跑真脚本，验用法、
双形态 round-trip 与错误口径（SessionError 行号 / 缺 -o 用法错误）。"""
import os, subprocess, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _run(script, *args):
    return subprocess.run([sys.executable, os.path.join(_ROOT, "tools", script), *args],
                          capture_output=True, text=True, cwd=_ROOT)

def _sample_fr():
    # 测试进程由 python -m pytest 从仓库根启动，tools 包可直接 import
    from tools.fr_gen import tbl
    from tools import fr_codec_gen as fc
    from tools import fr_session as fs
    sha = tbl.tbl_sha256(tbl.parse(open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read()))
    rows = [(op, dict(f)) for op, f in fc.self_test_samples()]
    s = dict(width=640, height=480, sha=sha, loglvl="base", seed=1,
             entries=[("cmnt", "cli sample"), ("frame", rows)])
    return fs.dump_text(s)

def test_as_and_dis_roundtrip(tmp_path):
    src = tmp_path / "s.fr"; frb = tmp_path / "s.frb"; back = tmp_path / "s.back.fr"
    src.write_text(_sample_fr(), encoding="utf-8")
    r = _run("fr_as.py", str(src), "-o", str(frb))
    assert r.returncode == 0, r.stderr
    r = _run("fr_dis.py", str(frb), "-o", str(back))
    assert r.returncode == 0, r.stderr
    assert back.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")

def test_dis_stdout(tmp_path):
    src = tmp_path / "s.fr"; frb = tmp_path / "s.frb"
    src.write_text(_sample_fr(), encoding="utf-8")
    assert _run("fr_as.py", str(src), "-o", str(frb)).returncode == 0
    r = _run("fr_dis.py", str(frb))
    assert r.returncode == 0 and r.stdout == src.read_text(encoding="utf-8")

def test_as_bad_file_reports_line(tmp_path):
    bad = tmp_path / "bad.fr"
    bad.write_text("frb1 640 480 " + "0" * 64 + " base 1\nframe 0\ngarbage\n", encoding="utf-8")
    r = _run("fr_as.py", str(bad))
    assert r.returncode == 1 and "行" in r.stderr and "fr-as:" in r.stderr

def test_as_requires_o(tmp_path):
    src = tmp_path / "s.fr"
    src.write_text(_sample_fr(), encoding="utf-8")
    r = _run("fr_as.py", str(src))
    assert r.returncode == 2
