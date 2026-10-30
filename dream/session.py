# dream/session.py
"""dream 会话壳（B18 M1→:px 档）：LLM 内容行 → Session → canonical .fr。

token 经济修正（2026-10-30 用户纠偏）：LLM 直接书写 **:px 档**（短名+整数
坐标+尾部缺省省略）——%.6f 高精 float 是生成 token 的纯浪费；跨帧行身份
簿记（B15 paramdelta）才需要结算器，:px 静态全量帧与 :full 同等自描述。
连续性=滑窗里的 out 行（D 行坐标即世界账本），st 自述行取消（px codec
不支持 variant——codec 约束顺势落定语义：px 生成档无 st）。
CRC 口径与 l0/main.lua:132-134 同参：d_crc=CRC32(out 行文本 "\\n" 连接)；
s_crc 恒 0（px 档无 st，哨兵，回放不消费——D14 注）。
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
    """LLM chunk → [(帧号, [(op, fields), ...]), ...]（:px 档解析）。

    chunk 形态：`frame N` 块序列，每块 out 内容行（短名/省略/整数量化）；
    块间空行与 markdown 围栏宽松。dt/asset/ev/end 行属 runner、st 行 px 不
    支持——出现即 ValueError（职责切分纪律）。
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
            op, fields = _rc.parse_line_px(line)
            if op in _RUNNER_OPS:
                raise ValueError("第 %d 行：%s 行属 runner 职责，LLM 不得书写" % (no, op))
            if op == "st":
                raise ValueError("第 %d 行：dream :px 档不写 st（连续性靠滑窗 out 行）"
                                 % no)
            if op not in LLM_OPS:
                raise ValueError("第 %d 行：op %r 不在 dream 内容行白名单" % (no, op))
            cur[1].append((op, fields))
    if cur is not None:
        frames.append(cur)
    if not frames:
        raise ValueError("chunk 无 frame 块")
    return frames


def seal_frames(frames, kit_rows, dt):
    """[(帧号, rows)] → Session entries。行序：dt → asset(仅首帧) → out → end 双行。

    kit_rows 为 ("asset", {"raw": 行文本}) 形——raw 透传不受档位渲染影响。
    """
    entries, first = [], True
    for _no, rows in frames:
        block = [("dt", {"val": dt})]
        if first:
            block += list(kit_rows)
            first = False
        block += rows
        out_txt = [_rc.render_line_px(op, f) for op, f in rows]
        block.append(("s_crc", {"crc": 0}))  # px 生成档无 st——哨兵（D14：回放不消费）
        block.append(("d_crc", {"crc": crc32_rows(out_txt)}))
        entries.append(("frame", block))
    return entries


def build_session(entries, seed, width=640, height=480):
    return dict(width=width, height=height, sha=table_sha(), loglvl="full",
                seed=seed, prec="px", delta=False,
                entries=[("cmnt", "dream runner session (B18 M1 :px)")] + entries)


def write_session(s, path):
    text = fr_session.dump_text(s)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(text)
    return text
