#!/usr/bin/env python3
# tools/fr_dump.py
"""fr-dump：会话 → canonical 文本 + 结构摘要（锚行判据素材）。

用法:
    python tools/fr_dump.py <in.fr|in.frb> [--frames a-b] [--stats]
                           [--strip-assets]

  input       输入会话文件，双输入按 magic 自动识别（FRB1=二进制，否则按
              UTF-8 文本解析）
  --frames    选帧视图 "a-b"（含端点；"a" 等价 "a-a"）：丢弃全部 cmnt
              （注释属整会话，过滤视图用于锚行），帧号重排连续
  --stats     在 canonical 文本后追加 '#' 注释摘要块（帧/行总数 + 按 op
              计数，op 字典序）
  --strip-assets
              asset 行 hex 体剥离成 '# … (+NB hex)' 摘要行（B=真字节数；
              观察面省流量，全量字节体不带本参数走 CLI 管道级消费）

输出走 stdout（UTF-8 字节、单 LF 结尾）：无 --stats 时即 canonical 原文
（.fr 输入 = 文件原文字节）。锚行判据统一引用 canonical 文本行。
与 fr-dis 的边界：fr-dis 只吃 .frb 且只出会话文本；本工具双输入 + 选帧 +
摘要。

退出码：0 成功；1 输入失败（SessionError / ValueError / OSError，
消息前缀 "fr-dump: " 到 stderr）；2 用法错误。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import fr_session as fs


def _load(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:4] == fs.MAGIC:
        return fs.parse_binary(raw)
    # CRLF 容忍（fr-as 同规矩：读入即归一 LF——Windows write_text 产 CRLF）
    return fs.parse_text(raw.decode("utf-8").replace("\r\n", "\n"))


def _filter_frames(s, spec):
    """--frames a-b：按帧号（canonical 输出里的 frame N，0 起计）留 [a,b] 区间
    的帧；cmnt 全丢，帧号由 dump_text 重排连续。注意帧号 ≠ entry 索引
    （cmnt 可出现在帧前），必须数帧本身。"""
    a, _, b = spec.partition("-")
    lo = int(a)
    hi = int(b) if b else lo
    frames = [e[1] for e in s["entries"] if e[0] == "frame"]
    entries = [("frame", rows) for no, rows in enumerate(frames) if lo <= no <= hi]
    return dict(s, entries=entries)


_ASSET_RES = (
    # 结构锚定（fr_codec_gen _render_asset 形态）：image=<id> <w> <h> <hex>、
    # font=<id> <size:%.6f> <hex>，空载荷记 '-'；canvas/quad 行无 hex 体不匹配
    re.compile(r"(asset image \d+ \d+ \d+ )([0-9a-fA-F]+|-)\n"),
    re.compile(r"(asset font \d+ \d+\.\d{6} )([0-9a-fA-F]+|-)\n"),
)


def _strip_assets(s):
    """dump 文本后处理：asset 行 hex 体剥离（文本级替换——Session 结构不动，
    dump_text 只认规范 entry 形态，cmnt 载体进不了帧块）。

    asset image 7 4 4 <hex…> → # asset image 7 4 4 (+16B hex)
    （'#' 前缀=注释形态——不参与再 parse，与 --stats 摘要块同构；参数 token
    原样保留，只有 hex 体换成字节数摘要。）
    全量字节体获取走本工具不带本参数（CLI 管道级消费：转 .frb/抽资产/重渲染）。
    """
    text = fs.dump_text(s)

    def _sum(m):
        head, hexbody = m.group(1), m.group(2)
        n = 0 if hexbody == "-" else len(hexbody) // 2
        return "# %s(+%dB hex)\n" % (head, n)

    for rex in _ASSET_RES:
        text = rex.sub(_sum, text)
    return text


def _stats(s):
    """'#' 注释摘要块：帧/行总数 + 按 op 计数（op 字典序）。"""
    counts = {}
    rows_total = 0
    for kind, payload in s["entries"]:
        if kind != "frame":
            continue
        for op, _ in payload:
            counts[op] = counts.get(op, 0) + 1
            rows_total += 1
    nframes = sum(1 for k, _ in s["entries"] if k == "frame")
    lines = ["", "# frames=%d rows=%d" % (nframes, rows_total)]
    for op in sorted(counts):
        lines.append("# op %s: %d" % (op, counts[op]))
    return "\n".join(lines) + "\n"


def main(argv):
    path, rng, stats, strip = None, None, False, False
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--frames":
            rng = args.pop(0) if args else None
        elif a == "--stats":
            stats = True
        elif a == "--strip-assets":
            strip = True
        else:
            path = a
    if not path:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        s = _load(path)
        if rng is not None:
            s = _filter_frames(s, rng)
        out = _strip_assets(s) if strip else fs.dump_text(s)
        if stats:
            out += _stats(s)
        sys.stdout.buffer.write(out.encode("utf-8"))
    except (fs.SessionError, ValueError, OSError) as e:
        print("fr-dump: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
