# dream/session.py
"""dream 会话壳（B18 M1）：LLM 内容行 → Session → canonical .fr。

职责切分（设计 §4）：LLM 写内容行（st + out op），runner 写封装行
（header/asset/dt/end）。CRC 口径与 l0/main.lua:132-134 及 fork C 侧同参：
d_crc=CRC32(out 行文本 "\\n" 连接)，s_crc=CRC32(st 行文本 "\\n" 连接)
——s_crc 是 dream 口径（LLM 自述账本），与录制流"注册状态根子图 CRC"
语义不同（D14 注记），回放不依赖。
"""
import os
import zlib

from tools import fr_session
from tools import fr_codec_gen as _rc
from tools.fr_gen import tbl

# LLM 可书写的 out op（cmd.tbl out 段全集中 dream M1 开放面）
LLM_OPS = {"clear", "draw", "print", "rect", "line", "poly", "circle",
           "arc", "points", "rt", "scissor"}
# 封装行白名单——出现在 chunk 里即职责越界
_RUNNER_OPS = {"dt", "asset", "ev", "call", "timer", "rngc", "err", "s_crc", "d_crc"}


def table_sha():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "tables", "cmd.tbl"), encoding="utf-8") as f:
        return tbl.tbl_sha256(tbl.parse(f.read()))


def crc32_rows(row_texts):
    """CRC32(行文本 "\\n" 连接)；空列表 = 0（zlib 空串口径）。"""
    return zlib.crc32("\n".join(row_texts).encode("utf-8")) & 0xFFFFFFFF


def parse_chunk(chunk_text):
    """LLM chunk → [(帧号, [(op, fields), ...]), ...]。

    chunk 形态：`frame N` 块序列，每块 st + out 内容行；块间空行宽松；
    markdown 围栏（``` 行）宽容跳过（LLM 输出习惯包裹代码块）。
    dt/asset/ev/end 行属 runner，出现即 ValueError（职责切分纪律）。
    """
    frames, cur = [], None
    for no, line in enumerate(chunk_text.split("\n"), start=1):
        if not line.strip() or line.strip().startswith("```"):
            continue
        if line.startswith("frame "):
            n = line[6:]
            if not n.isdigit():
                raise ValueError("第 %d 行：frame 号非法 %r" % (no, n))
            if cur is not None:
                frames.append(cur)
            cur = (int(n), [])
        else:
            if cur is None:
                raise ValueError("第 %d 行：内容行必须位于 frame 块内" % no)
            op, fields = _rc.parse_line(line)
            if op in _RUNNER_OPS:
                raise ValueError("第 %d 行：%s 行属 runner 职责，LLM 不得书写" % (no, op))
            if op != "st" and op not in LLM_OPS:
                raise ValueError("第 %d 行：op %r 不在 dream 内容行白名单" % (no, op))
            cur[1].append((op, fields))
    if cur is not None:
        frames.append(cur)
    if not frames:
        raise ValueError("chunk 无 frame 块")
    return frames


def seal_frames(frames, kit_rows, dt):
    """[(帧号, rows)] → Session entries。行序：dt → asset(仅首帧) → st → out → end 双行。"""
    entries, first = [], True
    for _no, rows in frames:
        st_rows = [(op, f) for op, f in rows if op == "st"]
        out_rows = [(op, f) for op, f in rows if op != "st"]
        block = [("dt", {"val": dt})]
        if first:
            block += list(kit_rows)
            first = False
        block += st_rows + out_rows
        st_txt = [_rc.render_line(op, f) for op, f in st_rows]
        out_txt = [_rc.render_line(op, f) for op, f in out_rows]
        block.append(("s_crc", {"crc": crc32_rows(st_txt)}))
        block.append(("d_crc", {"crc": crc32_rows(out_txt)}))
        entries.append(("frame", block))
    return entries


def build_session(entries, seed, width=640, height=480):
    return dict(width=width, height=height, sha=table_sha(), loglvl="full",
                seed=seed, prec="full", delta=False,
                entries=[("cmnt", "dream runner session (B18 M1)")] + entries)


def write_session(s, path):
    text = fr_session.dump_text(s)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(text)
    return text
