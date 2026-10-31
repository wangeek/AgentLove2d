# tests/test_dream.py
"""B18 dream runner 测试组（:px 档 + v1.5 双 Tier 增量词汇）。
--from-file 确定性模式全链，CI 零 token。"""
import os
import zlib

import pytest

from tools import fr_session
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------- T1：会话壳（词汇面 + 展开/降级） ----------------

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
    assert tuple(frames[0][1][1][1]["color"]) == (255, 255, 255, 255)


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


def test_parse_chunk_number_sanity():
    """大数/异常数防线：防小数点与位数幻觉；离屏大坐标（<1e6）不拦。"""
    from dream import session as ds
    ds.parse_chunk("frame 0\nD 1 0 -200 240 0 1 1\n"
                   "frame 1\nD 1 0 99999 240 0 1 1\n")
    for bad in ("D 1 0 4000000 240 0 1 1",
                "R 0 0 0 64000000.5 480 0 0 1 34 139 34 255"):
        with pytest.raises(ValueError, match="幻觉|常识域"):
            ds.parse_chunk("frame 0\n%s\n" % bad)
    for bad in ("D 1 0 nan 240 0 1 1", "D 1 0 inf 240 0 1 1"):
        with pytest.raises(ValueError, match="NaN|Inf|非有限数"):
            ds.parse_chunk("frame 0\n%s\n" % bad)


def test_parse_chunk_delta_vocab():
    """Tier1（含裸形回填）+ Tier2 词汇面解析。"""
    from dream import session as ds
    frames = ds.parse_chunk(
        'frame 0\nC 0 0 0 255\nD 7 0 100 200 0 1 1\nD 7 0 300 200 0 1 1\n'
        'frame 1\nCP\n'                       # 裸=上一帧
        'frame 2\nCP 0\n'                     # 显式 ref
        'frame 3\nMOVE 7 4 -2\n'              # Tier2 相对位移（k 缺省）
        'frame 4\nMOVE 7 1 4 -2\n'            # k=1 第二实例
        'frame 5\nPLACE 7 555 200\n'
        'frame 6\nEXIT 7\n'
        'frame 7\nENTER "D 9 0 40 40 0 1 1"\n')
    assert frames[1][1] == [("CP", {"ref": 0})]
    assert frames[2][1] == [("CP", {"ref": 0})]
    assert frames[3][1] == [("MOVE", {"asset": 7, "k": 0, "dx": 4.0, "dy": -2.0})]
    assert frames[4][1][0][1]["k"] == 1
    assert frames[7][1][0][0] == "ENTER"
    # 非法：CP 引用未写帧 / 增量与全量混帧 / frame0 增量
    for bad in ('frame 1\nCP 1\n', 'frame 1\nCP 5\n',
                'frame 1\nCP\nC 0 0 0 255\n',
                'frame 0\nCP 0\n'):
        with pytest.raises(ValueError):
            ds.parse_chunk('frame 0\nC 0 0 0 255\n' + bad if not bad.startswith("frame 0") else bad)


def test_resolve_tier2_downgrade():
    """Tier2 → Tier1 确定性降级 + 三口径 d_crc + 展开态正确性。"""
    from dream import session as ds
    frames = ds.parse_chunk(
        'frame 0\nC 0 0 0 255\nD 7 0 100 200 0 1 1\nD 7 0 300 200 0 1 1\n'
        'frame 1\nMOVE 7 4 -2\n'                    # → SET 7 0 x 104 / y 198
        'frame 2\nEXIT 7 1\n'                       # 删第二实例 → DEL 1
        'frame 3\nENTER "D 9 0 40 40 0 1 1"\n'      # → INS 1
        'frame 4\nCP\n'                             # → CP 3（锚）
        'frame 5\nPOSE 7 "D 8 0 104 198 0 1 1"\n')  # → DEL 0 + INS 0
    canon, expanded, dcrcs = ds.resolve_frames(frames)
    assert canon[1][1] == [("SET", {"asset": 7, "k": 0, "param": "x", "val": 104.0}),
                           ("SET", {"asset": 7, "k": 0, "param": "y", "val": 198.0})]
    assert canon[2][1] == [("DEL", {"pos": 2})]   # 帧2 基线 [C,D7,D7]——第二实例 idx2
    assert canon[3][1] == [("INS", {"pos": 2, "line": "D 9 0 40 40 0 1 1"})]  # 删后 [C,D7] 尾插
    assert canon[4][1] == [("CP", {"ref": 3})]
    assert canon[5][1] == [("DEL", {"pos": 1}),
                           ("INS", {"pos": 1, "line": "D 8 0 104 198 0 1 1"})]
    # 展开态：帧 1 两实例 (104,198)/(300,200)；帧 4 CP 后与帧 3 同
    assert expanded[1][1][1]["x"] == 104.0 and expanded[1][2][1]["x"] == 300.0
    assert expanded[4] == expanded[3]
    # d_crc 三口径：CP 帧=锚；编辑帧=展开态；全量帧=out 行
    assert dcrcs[4] == zlib.crc32(b"same:3") & 0xFFFFFFFF
    exp1 = zlib.crc32("\n".join(fc.render_line_px(o, f) for o, f in expanded[1]).encode()) & 0xFFFFFFFF
    assert dcrcs[1] == exp1
    # Tier2 永不进 canonical
    flat = {op for _n, rows in canon for op, _ in rows}
    assert flat <= ds.LLM_OPS | ds.TIER1
    # frame 0 增量禁 → 报错
    with pytest.raises(ValueError, match="帧 0"):
        ds.resolve_frames(ds.parse_chunk('frame 0\nCP 0\n'))


def test_seal_and_roundtrip(tmp_path):
    from dream import session as ds
    frames = ds.parse_chunk(
        'frame 0\nC 0 0 0 255\nR 0 0 0 640 480 0 0 1 255 0 0 255\n'
        'frame 1\nCP 0\n')
    canon, expanded, dcrcs = ds.resolve_frames(frames)
    kit_rows = [("asset", fc.parse_line("asset font 1 14.000000 00010203")[1])]
    entries = ds.seal_frames(canon, kit_rows=kit_rows, dt=0.066667, dcrcs=dcrcs)
    block = entries[0][1]
    assert block[0][0] == "dt" and block[1][0] == "asset"
    assert [op for op, _ in block[-2:]] == ["s_crc", "d_crc"]
    s = ds.build_session(entries, seed=1, has_same=True)
    assert s["prec"] == "px" and s["delta"]
    text = fr_session.dump_text(s)
    assert "asset font 1 14.000000 00010203" in text
    assert "\nCP 0\n" in text
    assert fr_session.dump_text(fr_session.parse_text(text)) == text
    p = tmp_path / "d.fr"
    ds.write_session(s, str(p))
    assert p.read_text(encoding="utf-8") == text


# ---------------- T2：fr-lint 语法+语义层 ----------------

def _tiny_stream(asset_rows=("asset font 1 14.000000 00010203",),
                 out_rows=("C 0 0 0 255",)):
    from dream import session as ds
    frames = ds.parse_chunk("frame 0\n" + "\n".join(out_rows))
    canon, expanded, dcrcs = ds.resolve_frames(frames)
    entries = ds.seal_frames(canon,
                             kit_rows=[("asset", fc.parse_line(a)[1]) for a in asset_rows],
                             dt=0.066667, dcrcs=dcrcs)
    return fr_session.dump_text(ds.build_session(entries, seed=1))


def test_lint_clean_on_valid_stream():
    from tools import fr_lint
    assert fr_lint.lint_text(_tiny_stream()) == []


def test_lint_phantom_asset():
    from tools import fr_lint
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
    from dream import session as ds
    frames = ds.parse_chunk("frame 0\nclear 0 0 0 255")
    canon, expanded, dcrcs = ds.resolve_frames(frames)
    entries = ds.seal_frames(canon, kit_rows=[], dt=0.066667, dcrcs=dcrcs)
    block = entries[0][1]
    block[0], block[1] = block[1], block[0]  # 破坏行序
    text = fr_session.dump_text(ds.build_session(entries, seed=1))
    diags = fr_lint.lint_text(text)
    assert any(d.startswith("L004") for d in diags)


def test_lint_cp_frame_and_negotiation():
    """CP 帧锚对账与 L005 协商缺失。"""
    from dream import session as ds
    from tools import fr_lint
    frames = ds.parse_chunk("frame 0\nC 0 0 0 255\nframe 1\nCP 0\n")
    canon, expanded, dcrcs = ds.resolve_frames(frames)
    entries = ds.seal_frames(canon, kit_rows=[], dt=0.066667, dcrcs=dcrcs)
    text = fr_session.dump_text(ds.build_session(entries, seed=1, has_same=True))
    assert fr_lint.lint_text(text) == []
    text_no_d = text.replace(" :px +d", " :px", 1)
    diags = fr_lint.lint_text(text_no_d)
    assert any(d.startswith("L005") for d in diags)
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l == "CP 0":
            lines[i + 2] = "d_crc 123456789"
            break
    diags = fr_lint.lint_text("\n".join(lines))
    assert any(d.startswith("L002") and "帧1" in d for d in diags)


# ---------------- T3：fr-assets kit 抽取 ----------------

def test_fr_assets_golden(tmp_path):
    from tools import fr_assets
    kit = tmp_path / "kit"
    n = fr_assets.extract("tests/golden/l0_session.fr", str(kit))
    assert n == 2
    import json
    man = json.loads((kit / "assets.json").read_text(encoding="utf-8"))
    assert [a["id"] for a in man["assets"]] == [1, 2]
    assert man["assets"][0]["kind"] == "image" and man["assets"][0]["w"] == 32
    rows = (kit / "assets.txt").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("asset image 1 ") and rows[1].startswith("asset font 2 ")


def test_fr_assets_from_files(tmp_path):
    import struct
    from tools import fr_assets

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 3, 2, 8, 2, 0, 0, 0)
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
    assert rows[0].startswith("asset image 1 3 2 89504e47")
    assert rows[1].startswith("asset font 2 14.000000 00010000")


# ---------------- T4：提示词工程（append-only messages；缓存友好） ----------------

def test_prompt_system_and_turn():
    from dream import prompt as dp
    vocab = dp.load_vocab()
    assert "frame N" in vocab and "C " in vocab
    catalog = dp.load_catalog("dream")
    system = dp.build_system(vocab, catalog, 640, 480)
    for part in (vocab, catalog, "640x480"):
        assert part in system
    turn = dp.build_turn("英雄从左走到右", next_frame=3, n_frames=10,
                         feedback="上次输出被拒：L001")
    for part in ("英雄从左走到右", "frame 3", "10 帧", "L001"):
        assert part in turn
    assert "被拒" not in dp.build_turn("d", 0, 5)
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
        driver.LlmDriver()


# ---------------- T6：run CLI 端到端（60 帧 from-file 全链，含 CP/Tier2） ----------------

def _gen_chunk_file(path, n_frames):
    """确定性 60 帧剧本：全量段 / ENTER 入场段 / CP 驻留段交替。"""
    parts = []
    for i in range(n_frames):
        if 30 <= i < 40:
            parts.append("frame %d\nCP" % i)
        elif i == 20:
            parts.append('frame %d\nENTER "R 0 100 300 16 16 0 0 1 255 0 0 255"' % i)
        elif 21 <= i < 30:
            parts.append("frame %d\nCP" % i)
        else:
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
    assert " :px" in text.split("\n")[0]
    assert "\nCP 29\n" in text          # 驻留段锚
    assert "\nINS 3 \"R 0 100 300 16 16 0 0 1 255 0 0 255\"\n" in text  # ENTER 降级（尾插）
    assert fr_lint.lint_text(text, dream=True) == []
    r = subprocess.run(["python", "tools/fr_check.py", str(out), "--strict"],
                       capture_output=True, cwd=_ROOT)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")
    frb = tmp_path / "dream.frb"
    back = tmp_path / "back.fr"
    subprocess.run(["python", "tools/fr_as.py", str(out), "-o", str(frb)],
                   check=True, capture_output=True, cwd=_ROOT)
    subprocess.run(["python", "tools/fr_dis.py", str(frb), "-o", str(back)],
                   check=True, capture_output=True, cwd=_ROOT)
    t1 = fr_session.parse_text(out.read_text(encoding="utf-8"))
    t2 = fr_session.parse_text(back.read_text(encoding="utf-8"))
    assert t1["entries"] == t2["entries"]
    love = os.path.join(_ROOT, "megasource", "build115", "love", "Release", "love.exe")
    if os.path.isfile(love):
        from tools import fr_delta_check as fdc
        # 独立展开器吃同一条流：帧数/警告
        rep = fdc.expand_delta(text)
        assert rep["frames"] == 60 and rep["warnings"] == []
        from tools import fr_render
        cp = fr_render.render(str(out), timeout=120)
        assert cp.returncode == 0, cp.stderr.decode("utf-8", "replace")
        got = [l for l in cp.stdout.decode().split("\n") if l.startswith("D_CRC ")]
        assert len(got) == 60
        cp2 = fr_render.render(str(out), timeout=120)
        got2 = [l for l in cp2.stdout.decode().split("\n") if l.startswith("D_CRC ")]
        assert got == got2
