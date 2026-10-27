# tests/test_check.py
"""fr-check CLI 判据运行器回归（B3a Task 2）：子进程跑真脚本，验内置
canonical 幂等 + sha 对账（默认 WARNING 不失败 / --strict 升 FAIL）与
FileCheck 式判据（CHECK / CHECK-NEXT / CHECK-NOT，'#' 注释；无法解析
的判据行 rc=2）。

编码纪律（同 test_dump.py）：fr_check 向 stdout/stderr 都写 UTF-8 **字节**
（失败消息含中文："幂等"/"行"定位），_run 禁用 text=True——断言一律
字节级比较，或 "…".encode("utf-8") 后做字节 in 断言。
"""
import os, subprocess, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD_FR = os.path.join(_ROOT, "tests", "golden", "sample.fr")
GOLD_FRB = os.path.join(_ROOT, "tests", "golden", "sample.frb")


def _run(*args):
    return subprocess.run([sys.executable, os.path.join(_ROOT, "tools", "fr_check.py"), *args],
                          capture_output=True, cwd=_ROOT)


def test_builtin_ok_on_golden():
    r = _run(GOLD_FR)
    assert r.returncode == 0, r.stderr
    assert b"CHECK OK (0 directives)" in r.stdout
    assert r.stderr == b""        # golden sha 与当前表一致：内置校验全静默


def test_builtin_ok_on_frb():
    r = _run(GOLD_FRB)
    assert r.returncode == 0, r.stderr
    assert b"CHECK OK (0 directives)" in r.stdout


def test_directives_pass(tmp_path):
    cf = tmp_path / "checks.txt"
    cf.write_text("# 判据\n"
                  "CHECK: draw 1 3\n"
                  "CHECK-NEXT: print\n"
                  "CHECK: s_crc \n"          # 尾随空格不进模式（pattern strip）
                  "CHECK-NOT: op nosuch\n", encoding="utf-8")
    r = _run(GOLD_FR, str(cf))
    assert r.returncode == 0, r.stderr
    assert b"CHECK OK (4 directives)" in r.stdout   # NOT 也计入指令数


def test_check_fail_reports(tmp_path):
    cf = tmp_path / "checks.txt"
    cf.write_text("CHECK: draw 1 3\nCHECK: op nosuchop\n", encoding="utf-8")
    r = _run(GOLD_FR, str(cf))
    assert r.returncode == 1
    assert "CHECK: op nosuchop".encode("utf-8") in r.stderr   # 报指令
    assert "行".encode("utf-8") in r.stderr                    # 报定位


def test_check_not_fail(tmp_path):
    cf = tmp_path / "checks.txt"
    cf.write_text("CHECK-NOT: draw\n", encoding="utf-8")
    r = _run(GOLD_FR, str(cf))
    assert r.returncode == 1


def test_unparseable_directive(tmp_path):
    cf = tmp_path / "checks.txt"
    cf.write_text("CHECK: draw 1 3\nFOO: bar\n", encoding="utf-8")
    r = _run(GOLD_FR, str(cf))
    assert r.returncode == 2
    assert "无法解析".encode("utf-8") in r.stderr


def test_sha_mismatch_strict(tmp_path):
    from tools.fr_gen import tbl
    from tools import fr_codec_gen as fc
    from tools import fr_session as fs
    sha = "0" * 64
    rows = [(op, dict(f)) for op, f in fc.self_test_samples()[:2]]   # dt + asset image
    s = dict(width=1, height=1, sha=sha, loglvl="base", seed=0, entries=[("frame", rows)])
    bad = tmp_path / "wrongsha.frb"
    bad.write_bytes(fs.dump_binary(s))
    r = _run(str(bad))                                  # 默认：警告不失败
    assert r.returncode == 0, r.stderr
    assert b"sha" in r.stdout + r.stderr                # WARNING 提及 sha
    assert b"WARNING" in r.stderr
    r = _run(str(bad), "--strict")                      # strict：升级失败
    assert r.returncode == 1


def test_idempotency_fail(tmp_path):
    raw = open(GOLD_FR, "rb").read()
    # 破坏 canonical：非规范浮点拼写（可解析、parse→dump ≠ 原文）。
    # 注：计划原构造 raw[:-2] + b"\n\n" 会把行尾"注"字砍成非法 UTF-8
    #（实测 UnicodeDecodeError，走输入失败而非幂等分支）；尾加空行则被
    # parse_text"空行禁入 canonical"挡住，同样到不了幂等比较。取末帧
    # call 行的浮点多补一位小数，正中 dump_text(parse_text(x)) != x。
    head, tail = raw.rsplit(b"num 88.000000", 1)
    broken = head + b"num 88.0000000" + tail
    f = tmp_path / "broken.fr"
    f.write_bytes(broken)
    r = _run(str(f))
    assert r.returncode == 1
    assert "幂等".encode("utf-8") in r.stdout + r.stderr


def test_next_fail_message_precise(tmp_path):
    # NEXT 失败必须报"第 N 行未含该续行"（非"全文未命中"）——锁死失败消息分支
    cf = tmp_path / "checks.txt"
    cf.write_text("CHECK-NEXT: draw 1 3\n", encoding="utf-8")   # dump 第 1 行是头行，必不命中
    r = _run(GOLD_FR, str(cf))
    assert r.returncode == 1
    assert "第 1 行未含该续行".encode("utf-8") in r.stderr
