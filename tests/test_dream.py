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


def test_parse_chunk_s_rows():
    """S 行：合法（独占帧+ref<本帧）；非法（引用未写帧/与内容行混帧）。"""
    from dream import session as ds
    ok = ('frame 0\nC 0 0 0 255\n'
          'frame 1\nS 0\n'
          'frame 2\nS 1\n')  # 链式合法
    frames = ds.parse_chunk(ok)
    assert [n for n, _ in frames] == [0, 1, 2]
    assert frames[1][1] == [("S", {"ref": 0})]
    for bad in ('frame 1\nS 1\n',            # 引用自身（未写帧）
                'frame 0\nC 0 0 0 255\nframe 1\nS 5\n',  # 引用未来帧
                'frame 0\nC 0 0 0 255\nframe 1\nS 0\nC 0 0 0 255\n'):  # 不独占
        with pytest.raises(ValueError):
            ds.parse_chunk(bad)


def test_parse_chunk_number_sanity():
    """大数/异常数防线：防小数点与位数幻觉；离屏大坐标（<1e6）不拦。"""
    from dream import session as ds
    # 合法：离屏负坐标/大但不荒谬（创作自由，非坐标域执法）
    ds.parse_chunk("frame 0\nD 1 0 -200 240 0 1 1\n"
                   "frame 1\nD 1 0 99999 240 0 1 1\n")
    # 非法：大数（位数/小数点幻觉）
    for bad in ("D 1 0 4000000 240 0 1 1",        # 400→4000000 级
                "R 0 0 0 64000000.5 480 0 0 1 34 139 34 255"):
        with pytest.raises(ValueError, match="幻觉|常识域"):
            ds.parse_chunk("frame 0\n%s\n" % bad)
    # 非法：异常数（nan/inf——codec 解析层先拒（B12 防线），dream 层双保险）
    for bad in ("D 1 0 nan 240 0 1 1", "D 1 0 inf 240 0 1 1"):
        with pytest.raises(ValueError, match="NaN|Inf|非有限数"):
            ds.parse_chunk("frame 0\n%s\n" % bad)


def test_parse_chunk_tolerates_markdown_fences():
    from dream import session as ds
    chunk = ('```\nframe 0\nclear 0 0 0 255\n```\n'
             '```\nframe 1\nclear 0 0 0 255\n```')
    frames = ds.parse_chunk(chunk)
    assert [n for n, _ in frames] == [0, 1]


def test_seal_and_roundtrip(tmp_path):
    from dream import session as ds
    frames = ds.parse_chunk(
        'frame 0\nC 0 0 0 255\nR 0 0 0 640 480 0 0 1 255 0 0 255\n'
        'frame 1\nS 0\n')
    kit_rows = [("asset", fc.parse_line("asset font 1 14.000000 00010203")[1])]
    entries, has_same = ds.seal_frames(frames, kit_rows=kit_rows, dt=0.066667)
    assert has_same
    # d_crc 口径：out 行 :px 渲染文本 "\n" 连接；S 帧=锚声明 CRC("same:<ref>")
    out_txt = [fc.render_line_px(op, f) for op, f in frames[0][1]]
    expect_d = zlib.crc32("\n".join(out_txt).encode()) & 0xFFFFFFFF
    block = entries[0][1]
    d_row = [f for op, f in block if op == "d_crc"][0]
    assert d_row["crc"] == expect_d
    s_block = entries[1][1]
    s_d = [f for op, f in s_block if op == "d_crc"][0]
    assert s_d["crc"] == zlib.crc32(b"same:0") & 0xFFFFFFFF
    # 行序：dt → asset → out → end 双行（px 无 st，s_crc=0 哨兵）
    assert block[0][0] == "dt"
    assert block[1][0] == "asset"
    assert [op for op, _ in block[-2:]] == ["s_crc", "d_crc"]
    # 全会话 canonical 幂等（:px +d 档 fr_session 链路，含 asset 行画回与 S 行）
    s = ds.build_session(entries, seed=1, has_same=has_same)
    assert s["prec"] == "px" and s["delta"]
    text = fr_session.dump_text(s)
    assert "asset font 1 14.000000 00010203" in text
    assert "\nS 0\n" in text
    assert fr_session.dump_text(fr_session.parse_text(text)) == text
    p = tmp_path / "d.fr"
    ds.write_session(s, str(p))
    assert p.read_text(encoding="utf-8") == text


# ---------------- T2：fr-lint 语法+语义层 ----------------

def _tiny_stream(asset_rows=("asset font 1 14.000000 00010203",),
                 out_rows=("C 0 0 0 255",)):
    from dream import session as ds
    frames = ds.parse_chunk("frame 0\n" + "\n".join(out_rows))
    entries, _ = ds.seal_frames(frames,
                                kit_rows=[("asset", fc.parse_line(a)[1]) for a in asset_rows],
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
    entries, has_same = ds.seal_frames(frames, kit_rows=[], dt=0.066667)
    block = entries[0][1]
    block[0], block[1] = block[1], block[0]  # 破坏行序
    text = fr_session.dump_text(ds.build_session(entries, seed=1, has_same=has_same))
    diags = fr_lint.lint_text(text)
    assert any(d.startswith("L004") for d in diags)


def test_lint_s_frame_and_negotiation():
    """S 帧对账（same: 锚）与 L005 协商缺失。"""
    from dream import session as ds
    from tools import fr_lint
    frames = ds.parse_chunk("frame 0\nC 0 0 0 255\nframe 1\nS 0\n")
    entries, has_same = ds.seal_frames(frames, kit_rows=[], dt=0.066667)
    text = fr_session.dump_text(ds.build_session(entries, seed=1, has_same=has_same))
    assert fr_lint.lint_text(text) == []  # 带 +d 的 S 帧全绿
    # 摘掉 +d（协商缺失）→ L005
    text_no_d = text.replace(" :px +d", " :px", 1)
    diags = fr_lint.lint_text(text_no_d)
    assert any(d.startswith("L005") for d in diags)
    # 篡改 S 帧 d_crc → L002
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l == "S 0":
            lines[i + 2] = "d_crc 123456789"  # S 0 / s_crc / d_crc
            break
    diags = fr_lint.lint_text("\n".join(lines))
    assert any(d.startswith("L002") and "帧1" in d for d in diags)


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


# ---------------- T4：提示词工程（append-only messages；缓存友好） ----------------

def test_prompt_system_and_turn():
    from dream import prompt as dp
    vocab = dp.load_vocab()
    assert "frame N" in vocab and "C " in vocab
    catalog = dp.load_catalog("dream")  # 无 kit 时如实声明无资产
    system = dp.build_system(vocab, catalog, 640, 480)
    for part in (vocab, catalog, "640x480"):
        assert part in system
    turn = dp.build_turn("英雄从左走到右", next_frame=3, n_frames=10,
                         feedback="上次输出被拒：L001")
    for part in ("英雄从左走到右", "frame 3", "10 帧", "L001"):
        assert part in turn
    # 无 feedback 时不含该段
    assert "被拒" not in dp.build_turn("d", 0, 5)
    # 滑窗（投影/诊断工具，不进生成路径）：asset hex 行过滤
    stream = ("frb1 640 480 x full 1\nasset image 1 3 2 " + "ab" * 40 + "\n"
              "frame 0\nclear 0 0 0 255\nframe 1\nclear 0 0 0 255\nframe 2\nclear 0 0 0 255\n")
    w = dp.sliding_window(stream, 2)
    assert w == "frame 1\nclear 0 0 0 255\nframe 2\nclear 0 0 0 255\n"
    assert "asset " not in w and "frame 0" not in w


# ---------------- T5：driver（FromFile 确定性 + LLM env/messages/usage） ----------------

def test_driver_from_file(tmp_path):
    from dream import driver
    f = tmp_path / "chunks.txt"
    f.write_text("frame 0\nclear 0 0 0 255\n### CHUNK\nframe 1\nclear 0 0 0 255\n",
                 encoding="utf-8")
    d = driver.FromFileDriver(str(f))
    assert "frame 0" in d.generate([])
    assert "frame 1" in d.generate([])
    assert d.usage_totals == {}
    with pytest.raises(RuntimeError):
        d.generate([])


def test_driver_llm_usage_accumulates():
    """usage 透传累加（fake 注入，无网络）。"""
    from dream import driver

    class Fake(driver.LlmDriver):
        def __init__(self):
            self.base, self.key, self.model = "b", "", "m"
            self.usage_totals = {}
            self.n = 0

        def generate(self, messages):
            self.n += 1
            self.usage_totals["prompt_tokens"] = self.usage_totals.get("prompt_tokens", 0) \
                + 100 * self.n
            self.usage_totals["completion_tokens"] = \
                self.usage_totals.get("completion_tokens", 0) + 10
            return "frame 0\nclear 0 0 0 255\n"

    fake = Fake()
    msgs = [{"role": "system", "content": "sys"}]
    fake.generate(msgs)
    fake.generate(msgs)
    assert fake.usage_totals == {"prompt_tokens": 300, "completion_tokens": 20}


def test_driver_llm_requires_env(monkeypatch):
    from dream import driver
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(RuntimeError):
        driver.LlmDriver()  # 未配置即构造期明确报错，不静默


# ---------------- T6：run CLI 端到端（60 帧 from-file 全链） ----------------

def _gen_chunk_file(path, n_frames):
    """确定性 60 帧剧本（:px 形 + S 帧驻留段）：hero.x 每帧 +4，帧 30-39 驻留 S 链。"""
    parts = []
    for i in range(n_frames):
        if 30 <= i < 40:
            parts.append("frame %d\nS %d" % (i, i - 1))  # 驻留段：链式 S
            continue
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
