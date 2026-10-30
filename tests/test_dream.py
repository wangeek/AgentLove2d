# tests/test_dream.py
"""B18 dream runner 测试组（M1）。--from-file 确定性模式全链，CI 零 token。"""
import os
import zlib

import pytest

from tools import fr_session
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _row(line):
    return fc.parse_line(line)


def test_parse_chunk_accepts_content_rows():
    from dream import session as ds
    chunk = ('frame 0\n'
             'st 0 "hero.x" num 10.000000\n'
             'clear 0 0 0 255\n'
             'draw 1 0 10.000000 20.000000 0.000000 1.000000 1.000000 0.000000 0.000000 255 255 255 255\n'
             '\n'
             'frame 1\n'
             'st 0 "hero.x" num 11.000000\n'
             'clear 0 0 0 255\n')
    frames = ds.parse_chunk(chunk)
    assert [n for n, _ in frames] == [0, 1]
    assert frames[0][1][0][0] == "st"
    assert frames[0][1][1][0] == "clear"


def test_parse_chunk_rejects_runner_rows():
    from dream import session as ds
    for bad in ('dt 0.066667', 'asset image 9 32 32 00', 's_crc 1', 'd_crc 1'):
        chunk = 'frame 0\n%s\nclear 0 0 0 255\n' % bad
        with pytest.raises(ValueError):
            ds.parse_chunk(chunk)


def test_seal_and_roundtrip(tmp_path):
    from dream import session as ds
    frames = ds.parse_chunk(
        'frame 0\nst 0 "hero.x" num 10.000000\n'
        'clear 0 0 0 255\n'
        'rect 0 0.000000 0.000000 640.000000 480.000000 0.000000 0.000000 1.000000 255 0 0 255\n')
    entries = ds.seal_frames(frames, kit_rows=[], dt=0.066667)
    # d_crc 口径：out 行文本 "\n" 连接的 zlib crc32
    out_txt = ["clear 0 0 0 255",
               "rect 0 0.000000 0.000000 640.000000 480.000000 0.000000 0.000000 1.000000 255 0 0 255"]
    expect_d = zlib.crc32("\n".join(out_txt).encode()) & 0xFFFFFFFF
    block = entries[0][1]
    d_row = [f for op, f in block if op == "d_crc"][0]
    assert d_row["crc"] == expect_d
    # 行序：dt 首行、end 双行殿后
    assert block[0][0] == "dt"
    assert [op for op, _ in block[-2:]] == ["s_crc", "d_crc"]
    # 全会话 canonical 幂等（fr_session 链路）
    s = ds.build_session(entries, seed=1)
    text = fr_session.dump_text(s)
    assert fr_session.dump_text(fr_session.parse_text(text)) == text
    p = tmp_path / "d.fr"
    ds.write_session(s, str(p))
    assert p.read_text(encoding="utf-8") == text


# ---------------- T2：fr-lint 语法+语义层 ----------------

def _tiny_stream(asset_rows=("asset font 1 14.000000 00010203",), out_rows=("clear 0 0 0 255",)):
    from dream import session as ds
    frames = ds.parse_chunk("frame 0\nst 0 \"t\" num 1.000000\n" + "\n".join(out_rows))
    entries = ds.seal_frames(frames, kit_rows=[fc.parse_line(a) for a in asset_rows], dt=0.066667)
    return fr_session.dump_text(ds.build_session(entries, seed=1))


def test_lint_clean_on_valid_stream():
    from tools import fr_lint
    assert fr_lint.lint_text(_tiny_stream()) == []


def test_lint_phantom_asset():
    from tools import fr_lint
    # draw 引用不存在的资产 7（kit 只有 font 1）
    text = _tiny_stream(out_rows=("clear 0 0 0 255",
        "draw 7 0 10.000000 20.000000 0.000000 1.000000 1.000000 0.000000 0.000000 255 255 255 255"))
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


# ---------------- T4：提示词工程 ----------------

def test_prompt_assembly_and_window():
    from dream import prompt as dp
    vocab = dp.load_vocab()
    assert "frame N" in vocab and "clear" in vocab
    catalog = dp.load_catalog("dream")  # 无 kit 时内建最小目录单（1 font）
    p = dp.build_prompt(vocab, catalog, window_text="frame 0\nclear 0 0 0 255",
                        directive="英雄从左走到右", next_frame=1)
    for part in (vocab, catalog, "frame 0", "英雄从左走到右", "frame 1"):
        assert part in p
    # 滑窗：取流文本最后 k 个 frame 块
    stream = "frame 0\nclear 0 0 0 255\nframe 1\nclear 0 0 0 255\nframe 2\nclear 0 0 0 255\n"
    assert dp.sliding_window(stream, 2) == "frame 1\nclear 0 0 0 255\nframe 2\nclear 0 0 0 255\n"


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
