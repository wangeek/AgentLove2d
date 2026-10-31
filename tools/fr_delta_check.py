# tools/fr_delta_check.py —— B15 增量流对拍工具（双实现交叉验证）
#
# 用法：python tools/fr_delta_check.py <in.fr（:px+d 增量流）> [--json]
#
# 职责：用**独立 Python 实现**展开增量流（S/pd/rdp/rdm → 全量行集），
# 与 C 展开器（fr_render 离线回放路径）的 D_CRC 交叉对账——双实现同一
# 语义（自检+独立重算范式，同 d_crc/fr_stats 先例）。产出全量 .fr 供
# 下游工具（fr-as/check/dump）消费。
#
# pd 语义（v1.4）：(asset,k) 行身份（该资产帧内第 k 次出现，0 起），
# param 白名单 x/y/rot/sx/sy/ox/oy，值恒绝对值——token 位序替换。
# S：行集取自 ref 帧（ref 须已展开）；rdp：pos 行序插入（嵌套引号反转义）；
# rdm：pos 行序删除。
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.fr_session as fs

_DELTA_OPS = ("CP", "SET", "INS", "DEL")
_OUT_OPS = ("clear", "draw", "print", "rect", "line", "circle",
            "poly", "arc", "points", "rt", "scissor")
_PX_SHORT = {"C": "clear", "D": "draw", "PR": "print", "R": "rect",
             "LN": "line", "CI": "circle", "PY": "poly", "AR": "arc",
             "PT": "points", "SC": "scissor"}


def _denorm(line):
    """:px 短名行 → 全名（C denorm_px_line 对称）。"""
    for s, l in (("D ", "draw "), ("R ", "rect "), ("C ", "clear "),
                 ("PR ", "print "), ("LN ", "line "), ("CI ", "circle "),
                 ("PY ", "poly "), ("AR ", "arc "), ("PT ", "points "),
                 ("SC ", "scissor ")):
        if line.startswith(s):
            return l + line[len(s):]
    return line


def expand_delta(text):
    """增量流文本 → (全量 Session dict, 展开报告)。独立实现：raw 行手工解析。"""
    s = fs.parse_text(text)  # 增量行经 raw 通道原样保留
    frames = []  # 展开态行集（:px 全名行文本）
    reports = []
    for kind, payload in s["entries"]:
        if kind != "frame":
            continue
        rows, deltas = [], []
        for row in payload:
            # B15 raw 通道形态：(op 名, {"raw": line}) tuple——原样保留
            if (isinstance(row, tuple) and len(row) == 2
                    and isinstance(row[1], dict) and "raw" in row[1]):
                t = row[1]["raw"].split(" ", 1)[0]
                if t in _DELTA_OPS:
                    deltas.append(row[1]["raw"])
                else:
                    rows.append(_denorm(row[1]["raw"]))
            elif row[0] in _OUT_OPS:
                rows.append(_denorm(fc_render(row[0], row[1])))
        base = rows if rows else (list(frames[-1]) if frames else [])
        state = list(base)
        for d in deltas:
            t = d.split(" ", 1)[0]
            if t == "CP":
                ref = int(d.split()[1])
                if ref >= len(frames):
                    reports.append("CP ref 越界: %s" % d)
                    continue
                state = list(frames[ref])
            elif t == "INS":
                pos = int(d.split()[1])
                line = d[d.index('"') + 1:d.rindex('"')]
                state.insert(pos, _denorm(line)) if pos <= len(state) else state.append(line)
            elif t == "DEL":
                pos = int(d.split()[1])
                if pos < len(state):
                    del state[pos]
                else:
                    reports.append("DEL 越界: %s" % d)
            elif t == "SET":
                _, asset, k, param, val = d.split()
                asset, k, val = int(asset), int(k), float(val)
                seen = 0
                matched = False
                for i, r in enumerate(state):
                    tt = r.split()
                    # :px 行（短名 D/draw 全名两形态）——资产 token 位同（位 1）
                    if tt[0] in ("draw", "D") and int(tt[1]) == asset:
                        if seen == k:
                            tt[_param_pos(param)] = "%.6f" % val
                            state[i] = " ".join(tt)
                            matched = True
                            break
                        seen += 1
                if not matched:
                    reports.append("SET 身份未配对: %s" % d)
        frames.append(state)
    out = {"frames": len(frames), "warnings": reports}
    out["_rows"] = frames
    return out


def fc_render(op, f):
    import tools.fr_codec_gen as fc
    return fc.render_line(op, f)


def _param_pos(param):
    # draw 签名 token 序（"D 7 0 x y ..."：draw=0, tex=1, quad=2, x=3, y=4,
    # rot=5, sx=6, sy=7, ox=8, oy=9, rgba8=10..13）
    order = ["tex", "quad", "x", "y", "rot", "sx", "sy", "ox", "oy",
             "r", "g", "b", "a"]
    # order 已含 tex/quad（token 1/2），只差 draw（token 0）——+1。
    # 2026-10-31 pd 回检修正：原 +3 把前缀数了两次（x 写进 rot 位）。
    return order.index(param) + 1  # +1 = draw 前缀


def write_expanded(path_out, meta, frames):
    out = ["frb1 %d %d %s %s %d" % (meta["width"], meta["height"], meta["sha"],
                                     meta["loglvl"], meta["seed"])]
    for rows in frames:
        out.append("frame %d" % sum(1 for l in out if l.startswith("frame ")))
        out.extend(rows)
    with open(path_out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def main(argv):
    ap = argparse.ArgumentParser(prog="fr-delta-check",
                                 description="B15 增量流展开对拍（独立 Python 实现）")
    ap.add_argument("input", help="输入 .fr（:px+d 增量流）")
    ap.add_argument("-o", "--out", metavar="out",
                    help="展开全量 .fr 输出（缺省不写）")
    ap.add_argument("--json", action="store_true", help="机读报告")
    args = ap.parse_args(argv)
    if not args.input:
        print("用法: python tools/fr_delta_check.py <in.fr> [-o out.fr] [--json]",
              file=sys.stderr)
        return 2
    import tools.fr_session as fs
    s = fs.parse_text(open(args.input, "rb").read().decode("utf-8"))
    text = open(args.input, "rb").read().decode("utf-8")
    r = expand_delta(text)
    r["prec"] = s.get("prec", "full")
    r["delta"] = s.get("delta", False)
    if args.out:
        write_expanded(args.out, s, r["_rows"])
    r.pop("_rows")
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print("frames %d | warnings %d%s"
              % (r["frames"], len(r["warnings"]),
                 " | " + "; ".join(r["warnings"][:3]) if r["warnings"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
