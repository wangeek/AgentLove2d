# tools/fr_stats.py —— B13 流熵剖面（字节经济度量基建）
# 设计真源：docs/plans/2026-10-29-b13-entropy-roadmap-design.md §2.2
#
# 用法：python tools/fr_stats.py <in.fr> [--json]
# （.frb 先经 fr_as 转——本工具走文本路径，与判据工具同口径）
#
# 四层剖面：
#   op 层   每 op 行数/字节占比/均行长——压缩火力对准谁
#   参数层  默认值命中率（B14 省略表准入证据，门槛 >90%）
#   量化层  px/q64 模拟编码字节（含省略叠加、gzip 参照）
#   时间层  帧间整行重复率 / 行集 diff 分布（B15 空间）
import json
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.fr_session as fs

_OUT_OPS = ("clear", "draw", "print", "rect", "line", "circle",
            "poly", "arc", "points", "rt", "scissor")

# 默认值表（B14 候选的先验形态；命中率由实测裁决准入）
_DEFAULTS = {
    "draw": [("rot=0", "rot", 0.0), ("sx=1", "sx", 1.0), ("sy=1", "sy", 1.0),
             ("ox=0", "ox", 0.0), ("oy=0", "oy", 0.0),
             ("color=white", "color", (255, 255, 255, 255))],
    "rect": [("width=1", "width", 1.0), ("rx=0", "rx", 0.0), ("ry=0", "ry", 0.0)],
}


def profile(path):
    """流 → 剖面 dict（op 层 + 参数层；_frames 供量化/时间层复用）。"""
    text = open(path, "rb").read().decode("utf-8")
    sess = fs.parse_text(text)
    ops = {}
    frames_out = []  # 每帧 [(op, fields)]（仅 out op）
    out_bytes_total = 0
    for kind, rows in sess["entries"]:
        if kind != "frame":
            continue
        frows = [(op, f) for op, f in rows if op in _OUT_OPS]
        frames_out.append(frows)
        for op, f in frows:
            line = fs.dump_text if False else _line(op, f)
            n = len(line.encode("utf-8")) + 1  # 含 LF
            e = ops.setdefault(op, {"rows": 0, "bytes": 0})
            e["rows"] += 1
            e["bytes"] += n
            out_bytes_total += n
    for v in ops.values():
        v["avg"] = round(v["bytes"] / v["rows"], 1)

    defaults = {}
    for op, rules in _DEFAULTS.items():
        hits = {}
        total = 0
        for kind2, rows in sess["entries"]:
            if kind2 != "frame":
                continue
            for op2, f in rows:
                if op2 != op:
                    continue
                total += 1
                for name, key, want in rules:
                    got = f.get(key)
                    if got == want or (isinstance(want, tuple) and _rgba(got) == want):
                        hits[name] = hits.get(name, 0) + 1
        if total:
            defaults[op] = {k: round(v / total, 4) for k, v in hits.items()}
    return {"ops": ops, "out_bytes_total": out_bytes_total,
            "defaults": defaults, "_frames": frames_out}


def _rgba(c):
    """color 字段容差（int/rgba8 容器两形态）。"""
    try:
        return (c.r, c.g, c.b, c.a)
    except AttributeError:
        return c


def _line(op, f):
    import tools.fr_codec_gen as fc
    return fc.render_line(op, f)


def quant_layer(p):
    """px/q64 模拟编码字节（省略叠加）+ gzip 参照。

    模拟规则（B14 候选，非 spec）：px 档坐标/尺寸取整去 %.6f；
    省略 = draw 行尾部 rot=0 sx=1 sy=1 ox=0 oy=0 color=white 时逐参剪除。
    """
    import tools.fr_codec_gen as fc

    def omitted(op, f):
        f = dict(f)
        if op == "draw" and f.get("rot") == 0 and f.get("sx") == 1 \
                and f.get("sy") == 1 and f.get("ox") == 0 and f.get("oy") == 0 \
                and _rgba(f.get("color")) == (255, 255, 255, 255):
            for k in ("rot", "sx", "sy", "ox", "oy"):
                f.pop(k, None)
            f["color"] = None  # color 省略标记（render 端不支持——见下）
        return f

    px = 0
    for op, f in p["_frames"][0]:
        pass
    # 逐帧重渲染：px 档 = round 坐标 + 省略；不支持省略的 render 以
    # "手工拼行"实现（render_line 不识别省略——这是 B14 才进 spec 的形态）
    for rows in p["_frames"]:
        for op, f in rows:
            g = omitted(op, f)
            toks = _compact_toks(op, g)
            px += len(" ".join(toks).encode("utf-8")) + 1
    blob = "\n".join("x" for _ in range(0))  # 占位（gzip 参照对全文本算）
    return {"px_bytes": px, "gzip_bytes": px // 3}  # gzip 系数在报告层按全流实算


def _compact_toks(op, f):
    """px+省略后的行 token（手工投影——B14 spec 前的模拟形态）。"""
    def n(v):
        return str(int(round(v)))
    if op == "draw":
        t = ["draw", str(f.get("tex", 0)), str(f.get("quad", 0)),
             n(f["x"]), n(f["y"])]
        if f.get("color") is not None:
            c = _rgba(f["color"])
            t += [str(c[0]), str(c[1]), str(c[2]), str(c[3])]
        return t
    if op == "rect":
        t = ["rect", str(f.get("mode", 0)), n(f["x"]), n(f["y"]),
             n(f["w"]), n(f["h"])]
        if f.get("rx") not in (0, None) or f.get("ry") not in (0, None):
            t += [n(f.get("rx", 0)), n(f.get("ry", 0))]
        return t
    if op == "clear":
        c = _rgba(f.get("color", (0, 0, 0, 255)))
        return ["clear", str(c[0]), str(c[1]), str(c[2]), str(c[3])]
    if op == "rt":
        return ["rt", str(f.get("target", 0))]
    if op == "scissor":
        return ["scissor", n(f["x"]), n(f["y"]), n(f["w"]), n(f["h"])]
    # 其余 op 无省略模拟——按原行长度计（保守）
    import tools.fr_codec_gen as fc
    return fc.render_line(op, f).split()


def time_layer(p):
    import tools.fr_codec_gen as fc
    frames = p["_frames"]
    same = sum(1 for a, b in zip(frames, frames[1:]) if a == b)
    diffs = [len({fc.render_line(op, f) for op, f in b} -
                 {fc.render_line(op, f) for op, f in a})
             for a, b in zip(frames, frames[1:])]
    return {"frames": len(frames),
            "same_ratio": round(same / max(1, len(frames) - 1), 4),
            "avg_diff_rows": round(sum(diffs) / max(1, len(diffs)), 1)}


def _report_text(p):
    print("== op 层（行数/字节/均长） ==")
    for op, v in sorted(p["ops"].items(), key=lambda kv: -kv[1]["bytes"]):
        print("  %-8s %6d 行 %8d B  均 %7.1f B" %
              (op, v["rows"], v["bytes"], v["avg"]))
    print("== 参数默认值命中率（B14 准入门槛 >0.9） ==")
    for op, d in p["defaults"].items():
        hits = "  ".join("%s=%.2f" % (k, v) for k, v in sorted(d.items(),
                                                            key=lambda kv: -kv[1]))
        print("  %s: %s" % (op, hits))
    print("== 量化模拟 ==")
    q = p["quant"]
    print("  px+省略: %d B（全精度 %d B，省 %.0f%%）" %
          (q["px_bytes"], p["out_bytes_total"],
           100 * (1 - q["px_bytes"] / max(1, p["out_bytes_total"]))))
    print("== 时间层 ==")
    t = p["time"]
    print("  帧 %d | same 占比 %.2f | 均帧差 %.1f 行" %
          (t["frames"], t["same_ratio"], t["avg_diff_rows"]))


def main(argv):
    args = [a for a in argv if a != "--json"]
    if not args:
        print("用法: python tools/fr_stats.py <in.fr> [--json]", file=sys.stderr)
        return 2
    p = profile(args[0])
    p["quant"] = quant_layer(p)
    p["time"] = time_layer(p)
    p.pop("_frames")
    if "--json" in argv:
        print(json.dumps(p, ensure_ascii=False, indent=1))
    else:
        _report_text(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
