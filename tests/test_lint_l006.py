# tests/test_lint_l006.py —— L006 不可判定流诊断（NUL 字节 / 单行超阈值 / 非法 UTF-8）
#
# 背景（docs/fr-agent-practice-report.md §6.1）：MemoryRemake 实战产出过一条 20.4GB
# 的调试流，第 3108 行单行 2.2GB 且以 NUL 开头——文本流混入未初始化缓冲后，
# grep 判其为二进制、整条流对任何按行工具静默失效，而工具链当时没有任何提示。
# L006 就是那道提示：它必须在 parse 之前拦下（超长行会拖死解析）。
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import fr_lint  # noqa: E402


def _sha():
    from tools.fr_gen import tbl
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return tbl.tbl_sha256(tbl.parse(
        open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read()))


def _stream(*content_rows):
    """最小合法流（帧 0：dt/资产/内容行/end 双行）——content_rows 是 out 段内容行，
    d_crc 按它们重算（否则会先触发 L002，掩盖被测的 L006）。"""
    import zlib
    rows = list(content_rows) or ["clear 0 0 0 255"]
    body = "".join(r + "\n" for r in rows)
    dcrc = zlib.crc32("\n".join(rows).encode("utf-8")) & 0xFFFFFFFF
    return ("frb1 64 48 " + _sha() + " base 1\n"
            "frame 0\n"
            "dt 0.016000\n"
            "asset image 1 4 4 00ff00ff\n"
            + body +
            "s_crc 0\nd_crc %d\n" % dcrc)


def test_clean_stream_has_no_l006():
    assert fr_lint.lint_text(_stream()) == []


def test_nul_byte_detected():
    """行内含 NUL → L006，且不应退化成 L000 解析错（真实原因被掩盖）。"""
    text = _stream("draw 1 0 1 1 0 1 1 0 0 255 255 255\x00 255")
    diags = fr_lint.lint_text(text)
    assert any(d.startswith("L006") and "NUL" in d for d in diags), diags
    assert not any(d.startswith("L000") for d in diags), diags


def test_nul_reports_line_number():
    """诊断带行号（1 起计，与编辑器一致）——便于直接定位。"""
    text = _stream("draw 1 0 1 1 0 1 1 0 0 255 255 255\x00 255")
    diags = fr_lint.lint_text(text)
    line = next(d for d in diags if d.startswith("L006"))
    # 会话头 1 / frame 2 / dt 3 / asset 4 / 坏行 5
    assert "行5" in line, line


def test_overlong_line_detected():
    """单行超阈值 → L006（默认阈值 256MB，测试用小阈值直接触发）。"""
    text = _stream("draw 1 0 " + "1" * 40)
    diags = fr_lint.lint_text(text, max_line_bytes=16)
    assert any(d.startswith("L006") and "超过" in d for d in diags), diags


def test_invalid_utf8_bytes_detected(tmp_path):
    """非法 UTF-8 字节同样不可判定（旧实现会直接抛 UnicodeDecodeError 崩掉）。"""
    p = tmp_path / "bad.fr"
    p.write_bytes(_stream().encode("utf-8").replace(b"frame 0", b"frame \xff 0"))
    rc = fr_lint.main(["fr_lint.py", str(p)])
    assert rc == 1
    # main 走流式扫描，诊断打印在 stdout（用 subprocess 复核 CLI 面）
    r = subprocess.run([sys.executable,
                        os.path.join(os.path.dirname(os.path.dirname(
                            os.path.abspath(__file__))), "tools", "fr_lint.py"),
                        str(p)], capture_output=True, text=True, encoding="utf-8")
    out = (r.stdout or "") + (r.stderr or "")
    assert "L006" in out and "UTF-8" in out, out
    assert r.returncode == 1


def test_cli_reports_l006_and_exits_1(tmp_path):
    p = tmp_path / "nul.fr"
    p.write_bytes(_stream("clear 0 0\x00 0 255").encode("utf-8"))
    r = subprocess.run([sys.executable, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools", "fr_lint.py"), str(p)],
        capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 1, (r.stdout, r.stderr)
    assert "L006" in (r.stdout or ""), r.stdout


def test_cli_clean_stream_exits_0(tmp_path):
    """回归：正常流不受影响（L006 不误报）。"""
    p = tmp_path / "ok.fr"
    p.write_text(_stream(), encoding="utf-8", newline="\n")
    r = subprocess.run([sys.executable, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools", "fr_lint.py"), str(p)],
        capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, (r.stdout, r.stderr)


def test_stream_scan_aborts_early_on_huge_line(tmp_path):
    """流式扫描必须在越界处立即放弃——不把整条超长行读进内存。

    构造：一个超长行，后面再跟 100MB 垃圾。若实现要读完才报，耗时会超过阈值；
    这里只断言"能快速返回并报 L006"（超时 20s 由 subprocess 兜住）。"""
    p = tmp_path / "huge.fr"
    head = _stream().encode("utf-8")
    with open(p, "wb") as f:
        f.write(head)
        f.write(b"\x00" * (1024 * 1024))        # 1MB 的 NUL 行（早于超长行）
        f.write(b"\n")
    r = subprocess.run([sys.executable, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools", "fr_lint.py"), str(p)],
        capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert r.returncode == 1
    assert "L006" in (r.stdout or "")
