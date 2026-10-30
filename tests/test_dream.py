# tests/test_dream.py
"""B18 dream runner 测试组（M1:px 档）。--from-file 确定性模式全链，CI 零 token。"""
import os
import zlib

import pytest

from tools import fr_session
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _row(line):
    return fc.parse_line_px(line)


# ---------------- T1：会话壳 ----------------

def test_parse_chunk_accepts_content_rows():
    from dream import session as ds
    chunk = ('frame 0\n'
             'C 0 0 0 255\n'
             'D 1 0 10 20 0 1 1\n'
             '\n'
             'frame 1\n'
             'C 0 0 0 255\n')
    frames = ds.parse_chunk(chunk)
    assert [n for n, _ in frames] == [0, 1]
    assert frames[0][1][0][0] == "clear"
    assert frames[0][1][1][0] == "draw"
    # px 省略回填：color=white、ox/oy=0
    assert tuple(frames[0][1][1][1]["color"]) == (255, 255, 255, 255)
    assert frames[0][1][1][1]["ox"] == 0.0


def test_parse_chunk_rejects_runner_rows():
    from dream import session as ds
    for bad in ('dt 0.066667', 'asset image 9 32 32 00', 's_crc 1', 'd_crc 1',
                'st 0 "hero.x" num 40'):
        chunk = 'frame 0\n%s\nclear 0 0 0 255\n' % bad
        with pytest.raises(ValueError):
            ds.parse_chunk(chunk)


def test_parse_chunk_tolerates_markdown_fences():
    from dream import session as ds
    chunk = ('```\nframe 0\nclear 0 0 0 255\n```\n'
             '```\nframe 1\nclear 0 0 0 255\n```')
    frames = ds.parse_chunk(chunk)
    assert [n for n, _ in frames] == [0, 1]


def test_seal_and_roundtrip(tmp_path):
    from dream import session as ds
    frames = ds.parse_chunk(
        'frame 0\nC 0 0 0 255\nR 0 0 0 640 480 0 0 1 255 0 0 255\n')
    kit_rows = [("asset", fc.parse_line("asset font 1 14.000000 00010203")[1])]
    entries = ds.seal_frames(frames, kit_rows=kit_rows, dt=0.066667)
    # d_crc 口径：out 行 :px 渲染文本 "\n" 连接的 zlib crc32（与 seal 同源渲染器）
    out_txt = [fc.render_line_px(op, f) for op, f in frames[0][1]]
    expect_d = zlib.crc32("\n".join(out_txt).encode()) & 0xFFFFFFFF
    block = entries[0][1]
    d_row = [f for op, f in block if op == "d_crc"][0]
    assert d_row["crc"] == expect_d
    # 行序：dt → asset → out → end 双行（px 无 st，s_crc=0 哨兵）
    assert block[0][0] == "dt"
    assert block[1][0] == "asset"
    assert [op for op, _ in block[-2:]] == ["s_crc", "d_crc"]
    s_row = [f for op, f in block if op == "s_crc"][0]
    assert s_row["crc"] == 0
    # 全会话 canonical 幂等（:px 档 fr_session 链路，含 asset 行画回）
    s = ds.build_session(entries, seed=1)
    assert s["prec"] == "px"
    text = fr_session.dump_text(s)
    assert "asset font 1 14.000000 00010203" in text
    assert fr_session.dump_text(fr_session.parse_text(text)) == text
    p = tmp_path / "d.fr"
    ds.write_session(s, str(p))
    assert p.read_text(encoding="utf-8") == text


# ---------------- T2：fr-lint 语法+语义层 ----------------

def _tiny_stream(asset_rows=("asset font 1 14.000000 00010203",),
                 out_rows=("C 0 0 0 255",)):
    from dream import session as ds
    frames = ds.parse_chunk("frame 0\n" + "\n".join(out_rows))
    entries = ds.seal_frames(frames, kit_rows=[("asset", fc.parse_line(a)[1]) for a in asset_rows],
                             dt=0.066667)
    return fr_session.dump_text(ds.build_session(entries, seed=1))


def test_lint_clean_on_valid_stream():
    from tools import fr_lint
    assert fr_lint.lint_text(_tiny_stream()) == []


def test_lint_phantom_asset():
    from tools import fr_lint
    # draw 引用不存在的资产 7（kit 只有 font 1）
    text = _tiny_stream(out_rows=("C 0 0 0 255", "D 7 0 10 20 0 1 1"))
    diags = fr_lint.lint_text(text)
    assert any(d.startswith("L001") and "7" in d for d in diags)


def test_lint_bad_d_crc():
    from tools import fr_lint
    text = _tiny_stream()
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.startswith("d_crc "):
            lines[i] = "d_crc 123456789"
            break
    diags = fr_lint.lint_text("\n".join(lines))
    assert any(d.startswith("L002") for d in diags)


def test_lint_frame_order():
    from tools import fr_lint
    # dt 不在帧首（手工拼一条坏流：帧首塞 clear 再 dt）
    from dream import session as ds
    frames = ds.parse_chunk("frame 0\nclear 0 0 0 255")
    entries = ds.seal_frames(frames, kit_rows=[], dt=0.066667)
    block = entries[0][1]
    block[0], block[1] = block[1], block[0]  # 破坏行序
    text = fr_session.dump_text(ds.build_session(entries, seed=1))
    diags = fr_lint.lint_text(text)
    assert any(d.startswith("L004") for d in diags)


# ---------------- T3：fr-assets kit 抽取 ----------------

def test_fr_assets_golden(tmp_path):
    from tools import fr_assets
    kit = tmp_path / "kit"
    n = fr_assets.extract("tests/golden/l0_session.fr", str(kit))
    assert n == 2  # golden: image 1 + font 2
    import json
    man = json.loads((kit / "assets.json").read_text(encoding="utf-8"))
    assert [a["id"] for a in man["assets"]] == [1, 2]
    assert man["assets"][0]["kind"] == "image" and man["assets"][0]["w"] == 32
    rows = (kit / "assets.txt").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("asset image 1 ") and rows[1].startswith("asset font 2 ")


def test_fr_assets_from_files(tmp_path):
    """从原始文件建 kit：PNG 头解析 w/h、字节原样登记（spec v1.2.6 路径资产口径）。"""
    import struct
    from tools import fr_assets

    # 手造最小合法 PNG（3x2 RGB）：签名 + IHDR + IDAT + IEND
    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 3, 2, 8, 2, 0, 0, 0)  # 3x2 RGB
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", b"\x00\x00") + chunk(b"IEND", b""))
    p = tmp_path / "tiny.png"
    p.write_bytes(png)
    f = tmp_path / "fake.ttf"
    f.write_bytes(b"\x00\x01\x00\x00FONT")
    kit = tmp_path / "kit"
    n = fr_assets.build_from_files(str(kit), [(str(p), "image"), (str(f), "font")])
    assert n == 2
    man = (kit / "assets.json").read_text(encoding="utf-8")
    assert '"w": 3' in man and '"h": 2' in man
    rows = (kit / "assets.txt").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("asset image 1 3 2 89504e47")  # PNG 魔数在 hex 头
    assert rows[1].startswith("asset font 2 14.000000 00010000")


# ---------------- T4：提示词工程 ----------------

def test_prompt_assembly_and_window():
    from dream import prompt as dp
    vocab = dp.load_vocab()
    assert "frame N" in vocab and "C " in vocab
    catalog = dp.load_catalog("dream")  # 无 kit 时如实声明无资产
    p = dp.build_prompt(vocab, catalog, window_text="frame 0\nclear 0 0 0 255",
                        directive="英雄从左走到右", next_frame=1)
    for part in (vocab, catalog, "frame 0", "英雄从左走到右", "frame 1"):
        assert part in p
    # 滑窗：取流文本最后 k 个 frame 块；asset hex 行过滤（不进 LLM 窗口）
    stream = ("frb1 640 480 x full 1\nasset image 1 3 2 " + "ab" * 40 + "\n"
              "frame 0\nclear 0 0 0 255\nframe 1\nclear 0 0 0 255\nframe 2\nclear 0 0 0 255\n")
    w = dp.sliding_window(stream, 2)
    assert w == "frame 1\nclear 0 0 0 255\nframe 2\nclear 0 0 0 255\n"
    assert "asset " not in w and "frame 0" not in w


# ---------------- T5：driver（FromFile 确定性 + LLM env） ----------------

def test_driver_from_file(tmp_path):
    from dream import driver
    f = tmp_path / "chunks.txt"
    f.write_text("frame 0\nclear 0 0 0 255\n### CHUNK\nframe 1\nclear 0 0 0 255\n",
                 encoding="utf-8")
    d = driver.FromFileDriver(str(f))
    assert "frame 0" in d.generate("prompt-ignored")
    assert "frame 1" in d.generate("prompt-ignored")
    with pytest.raises(RuntimeError):
        d.generate("exhausted")


def test_driver_llm_requires_env(monkeypatch):
    from dream import driver
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(RuntimeError):
        driver.LlmDriver()  # 未配置即构造期明确报错，不静默


# ---------------- T6：run CLI 端到端（60 帧 from-file 全链） ----------------

def _gen_chunk_file(path, n_frames):
    """确定性 60 帧剧本（:px 形）：hero.x 每帧 +4，清屏+方块+顶栏；分 6 段 chunk。"""
    parts = []
    for i in range(n_frames):
        x = 40 + 4 * i
        parts.append("frame %d\nC 20 24 36 255\n"
                     "R 0 %d 240 48 48 0 0 1 255 255 255 255\n"
                     "R 0 0 0 640 24 0 0 1 90 90 120 255\n"
                     % (i, x))
    chunks = ["\n".join(parts[j * 10:(j + 1) * 10]) for j in range(6)]
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n### CHUNK\n".join(chunks) + "\n")


def test_end_to_end_from_file(tmp_path):
    import subprocess
    from tools import fr_lint
    src = tmp_path / "chunks.txt"
    _gen_chunk_file(str(src), 60)
    out = tmp_path / "dream.fr"
    r = subprocess.run(
        ["python", "-m", "dream.run", "--frames", "60", "--out", str(out),
         "--from-file", str(src), "--seed", "1"], capture_output=True, cwd=_ROOT)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    text = out.read_text(encoding="utf-8")
    assert text.count("\nframe ") == 60
    assert " :px" in text.split("\n")[0]  # 头档位
    # ① fr-lint 全绿（dream 口径）
    assert fr_lint.lint_text(text, dream=True) == []
    # ② fr-check（含 canonical 幂等 + sha 对账）
    r = subprocess.run(["python", "tools/fr_check.py", str(out), "--strict"],
                       capture_output=True, cwd=_ROOT)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")
    # ③ round-trip：.frb 不存档位（B14 设计——二进制档位自由），fr_dis 回 :full
    #    形态。判据 = 字段级语义等价（B14 跨档归一口径）；px 文本幂等已由 ② 覆盖。
    frb = tmp_path / "dream.frb"
    back = tmp_path / "back.fr"
    subprocess.run(["python", "tools/fr_as.py", str(out), "-o", str(frb)],
                   check=True, capture_output=True, cwd=_ROOT)
    subprocess.run(["python", "tools/fr_dis.py", str(frb), "-o", str(back)],
                   check=True, capture_output=True, cwd=_ROOT)
    t1 = fr_session.parse_text(out.read_text(encoding="utf-8"))
    t2 = fr_session.parse_text(back.read_text(encoding="utf-8"))
    assert t2["prec"] == "full"
    assert t1["entries"] == t2["entries"]
    # ④ render 双跑一致（fork 构建在场时；不在场跳过——CI 与无构建机不红）
    #    口径：回放 stdout D_CRC = 画布像素 CRC（fr_capture.cpp:2658，B4 验证锚），
    #    与流内 d_crc（B7a out 行文本 CRC）是两个域，不可互比——判据为：
    #    rc=0 + 60 帧出齐 + 双跑逐帧一致（确定性锚，B10 同口径）。
    love = os.path.join(_ROOT, "megasource", "build115", "love", "Release", "love.exe")
    if os.path.isfile(love):
        from tools import fr_render
        cp = fr_render.render(str(out), timeout=120)
        assert cp.returncode == 0, cp.stderr.decode("utf-8", "replace")
        got = [l for l in cp.stdout.decode().split("\n") if l.startswith("D_CRC ")]
        assert len(got) == 60
        cp2 = fr_render.render(str(out), timeout=120)
        got2 = [l for l in cp2.stdout.decode().split("\n") if l.startswith("D_CRC ")]
        assert got == got2  # 双跑逐帧一致（画布确定性）
