# tools/fr_prec.py —— B14 精度档转换器（:full → :px 单向量化）
# 设计：docs/plans/2026-10-29-b14-compact.md Task 3。
#
# 用法：python tools/fr_prec.py <in.fr> -o <out.fr> --px
#（本批仅 --px；:q64 档位名预留，渲染待动画域需求）
#
# 转换规则：
#   head    加 " :px" 尾标
#   out 段行 render_line_px 重渲染（短名+量化+尾部省略）
#   d_crc   重算（px 行文本变 → CRC 必然变；各档锚各的 d_crc——设计 §3.3）
#   其余行（frame/dt/asset/ev/st/err/s_crc/cmnt）full 渲染透传（状态与档位无关）
# 帧内行序保持 canonical：dt/asset/ev/st/err/out/s_crc → d_crc 恒帧尾。
import argparse
import sys
import zlib

import tools.fr_codec_gen as fc
import tools.fr_session as fs

_OUT_OPS = ("clear", "draw", "print", "rect", "line", "circle",
            "poly", "arc", "points", "rt", "scissor")


def convert(text):
    """canonical 文本（:full）→ canonical 文本（:px）。"""
    s = fs.parse_text(text)
    if s["prec"] != "full":
        raise fs.SessionError("输入流须为 :full 档（得 %r）" % s["prec"])
    out = ["frb1 %d %d %s %s %d :px" % (s["width"], s["height"], s["sha"],
                                         s["loglvl"], s["seed"])]
    fno = 0
    for kind, payload in s["entries"]:
        if kind == "cmnt":
            out.append("cmnt " + payload)
            continue
        out.append("frame %d" % fno)
        fno += 1
        frame_lines = []  # 除 d_crc 外的输出行（保 canonical 序）
        out_rows = []     # 本帧 px out 行（d_crc 载荷）
        for op, fields in payload:
            if op == "d_crc":
                continue  # 帧尾重算
            if op in _OUT_OPS:
                line = fc.render_line_px(op, fields)
                out_rows.append(line)
                frame_lines.append(line)
            else:
                frame_lines.append(fc.render_line(op, fields))
        out.extend(frame_lines)
        out.append("d_crc %d" % (zlib.crc32("\n".join(out_rows).encode("utf-8"))
                                 if out_rows else 0))
    return "\n".join(out) + "\n"


def main(argv):
    ap = argparse.ArgumentParser(prog="fr-prec",
                                 description=":full → :px 精度档转换（B14）")
    ap.add_argument("input", help="输入 .fr 文本流（:full）")
    ap.add_argument("-o", "--out", metavar="out", help="输出 .fr（缺省打印 stdout）")
    ap.add_argument("--px", action="store_true", help="转 :px 档（本批唯一档）")
    args = ap.parse_args(argv)
    if not args.px:
        print("fr-prec: 请指定 --px（q64 档待后续批）", file=sys.stderr)
        return 2
    try:
        text = open(args.input, "rb").read().decode("utf-8")
        result = convert(text)
        if args.out:
            with open(args.out, "wb") as f:
                f.write(result.encode("utf-8"))
        else:
            sys.stdout.buffer.write(result.encode("utf-8"))
    except (fs.SessionError, ValueError, OSError) as e:
        print("fr-prec: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
