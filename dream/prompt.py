# dream/prompt.py
"""提示词工程（B18 M1 = 方案 1 滑窗原文；设计 §5）。

上下文 = 词汇速查（静态）+ 资产目录单（kit）+ 最近 K 帧原文（含 st/ev）
+ 导演指令。接续 = 机械读流尾；无副产物、无摘要（M2 才上前情提要）。
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


def sliding_window(stream_text, k):
    """canonical 流文本 → 最后 k 个 frame 块原文（含 frame 头行）。

    asset 行（hex 字节体）**过滤掉**——资产引用面已在目录单，字节进窗口会把
    请求撑爆（实测 3.1MB kit → 第二次请求 400；帧 0 在 K=8 窗内持续污染）。
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


def build_prompt(vocab, catalog, window_text, directive, next_frame):
    return ("你在为帧流 IR（FR）直接书写一帧帧的绘制决定。规则与词汇表：\n%s\n\n"
            "%s\n\n以下是最近帧（含你的世界账本 st 行，保持数值连续）：\n%s\n"
            "导演指令：%s\n请从 frame %d 继续，输出后续帧块（每块 frame 头 + st + 绘制行）。\n"
            % (vocab, catalog, window_text, directive, next_frame))
