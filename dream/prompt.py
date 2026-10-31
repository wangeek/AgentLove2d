# dream/prompt.py
"""提示词工程（B18 → append-only messages；2026-10-31 缓存修正）。

结构：system（词汇表+目录单+几何，**永不改动**）+ 逐 chunk 追加的
user（指令+本次输出数+诊断回喂）/ assistant（上次原文）对。

**为什么放弃滑窗**：前缀缓存（DeepSeek/OpenAI/Anthropic 通例）按「从第 0
字节起逐字节相同」命中——滑窗每次改写 messages 中段，把可命中的前缀拦腰
打断，是反缓存优化。append-only 下每个新请求=上个请求的完整前缀+一条新
消息，除最新段外全部命中（DeepSeek 命中价约为未命中 1/5 以下）。上下文
增长的解法是 M2 前情提要（压缩历史），不是改写中段——与 D14「接续=读
聊天记录」、M2「ev 打断=user 消息」自然合流。

sliding_window 保留为投影工具（fr-check/诊断用），不进生成路径。
"""
import json
import os

_DREAM_DIR = os.path.dirname(os.path.abspath(__file__))


def load_vocab():
    with open(os.path.join(_DREAM_DIR, "vocab.txt"), encoding="utf-8") as f:
        return f.read().strip()


def load_catalog(kit_dir):
    """kit 目录单 → 目录单文本；kit 缺 assets.json 时如实声明无资产。"""
    p = os.path.join(kit_dir, "assets.json")
    if not os.path.isfile(p):
        return ("资产目录单：本次无可用资产——不要书写 draw/print 行（无可引用 id），"
                "只用矢量 op（rect/line/poly/circle/arc/points/clear）作画")
    with open(p, encoding="utf-8") as f:
        man = json.load(f)
    rows = ["资产目录单（引用只允许下列 id）："]
    for a in man["assets"]:
        if a["kind"] == "image":
            rows.append("%d = image %dx%d" % (a["id"], a.get("w", 0), a.get("h", 0)))
        elif a["kind"] == "font":
            rows.append("%d = font 字号 %s" % (a["id"], a.get("size", "?")))
        else:
            rows.append("%d = %s" % (a["id"], a["kind"]))
    return "\n".join(rows)


def build_system(vocab, catalog, width, height):
    """system 消息（静态件拼装，一次构建永不再动——前缀缓存的前提）。"""
    return ("%s\n\n%s\n\n会话几何：%dx%d（frame 内坐标域）。\n"
            "直接输出行文本，不要任何解释或围栏。" % (vocab, catalog, width, height))


def build_turn(directive, next_frame, n_frames, feedback=""):
    """user 消息（追加在尾部——只动尾部，前缀缓存不受影响）。"""
    turn = directive
    if feedback:
        turn += "；" + feedback
    turn += "\n请从 frame %d 开始，本次输出 %d 帧。" % (next_frame, n_frames)
    return turn


def sliding_window(stream_text, k):
    """canonical 流文本 → 最后 k 个 frame 块原文（投影/诊断工具，不进生成路径）。

    asset 行（hex 字节体）过滤——字节体不进任何 LLM 面。
    """
    lines = stream_text.split("\n")
    starts = [i for i, l in enumerate(lines) if l.startswith("frame ")]
    if not starts:
        return ""
    starts = starts[-k:]
    end = starts[-1]
    while end < len(lines) and lines[end] != "":
        end += 1
    body = [l for l in lines[starts[0]:end] if not l.startswith("asset ")]
    return "\n".join(body) + "\n"
