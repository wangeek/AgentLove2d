# dream/session.py
"""dream 会话壳（B18 :px 档 + v1.5 双 Tier 增量词汇）。

**词汇面**（LLM 可写）：
- 全量 op（LLM_OPS，:px 短名/省略/整数量化）
- Tier1 增量（编辑器动词）：CP/SET/INS/DEL——可裸形（CP=上一帧、SET k=0、
  INS pos=行尾），parse 层有帧上下文直接回填
- Tier2 增量（舞台动词，对象编辑）：MOVE/PLACE/POSE/ENTER/EXIT——融合语义，
  resolve 时确定性降级为 Tier1（MOV→SET×2、POSE→DEL+INS、ENTER→INS、
  EXIT→DEL），**Tier2 永不进 canonical 流**

**dream 帧纪律**（比流语义收紧，保 lint 全可锚验）：一帧 = 全量行 | 纯 CP |
编辑行组（基线=上一帧展开态）。帧 0 必须全量。

**CRC 口径**：全量帧=CRC(out :px 行)；CP 帧=CRC("same:<ref>")（锚声明，
fr_session.cpp:363 同参，字面量 same: 不随改名变）；编辑帧=CRC(展开态行)。
s_crc 恒 0（px 生成档无 st——D14：回放不消费）。
"""
import os
import zlib

from tools import fr_session
from tools import fr_codec_gen as _rc
from tools.fr_gen import tbl

# 全量 op
LLM_OPS = {"clear", "draw", "print", "rect", "line", "poly", "circle",
           "arc", "points", "rt", "scissor"}
# Tier1 增量（编辑器动词——canonical 增量行）
TIER1 = {"CP", "SET", "INS", "DEL"}
# Tier2 增量（舞台动词——对象编辑，seal 前降级为 Tier1）
TIER2 = {"MOVE", "PLACE", "POSE", "ENTER", "EXIT"}
# 封装行白名单——出现在 chunk 里即职责越界
_RUNNER_OPS = {"dt", "asset", "ev", "call", "timer", "rngc", "err", "s_crc", "d_crc"}
_SET_PARAMS = ("x", "y", "rot", "sx", "sy", "ox", "oy")

# 数值常识域（防小数点/位数幻觉，非坐标域限制——离屏坐标合法，4000→4000000 不合法）
_ABS_MAX = 1e6


def table_sha():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "tables", "cmd.tbl"), encoding="utf-8") as f:
        return tbl.tbl_sha256(tbl.parse(f.read()))


def crc32_rows(row_texts):
    return zlib.crc32("\n".join(row_texts).encode("utf-8")) & 0xFFFFFFFF


def _check_sane_numbers(no, desc, fields):
    """递归查行内全部浮点：nan/inf 与 |v|>1e6 即拒（只防荒谬量级，不执法几何域）。"""
    stack = [(fields, "")]
    while stack:
        obj, path = stack.pop()
        if isinstance(obj, float):
            import math
            if not math.isfinite(obj):
                raise ValueError("第 %d 行：%s%s 值 %r 非有限数（nan/inf 异常数）"
                                 % (no, desc, path, obj))
            if abs(obj) > _ABS_MAX:
                raise ValueError("第 %d 行：%s%s 值 %r 超常识域 |v|>1e6"
                                 "（疑似小数点/位数幻觉）" % (no, desc, path, obj))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                stack.append((v, "%s.%s" % (path, k)))
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                stack.append((v, "%s[%d]" % (path, i)))


def _parse_delta_line(no, line, frame_no):
    """Tier1/Tier2 增量行（含裸形）→ (op, fields)；帧上下文回填缺省。"""
    toks = line.split(" ")
    op = toks[0]
    if op == "CP":
        ref = int(toks[1]) if len(toks) > 1 else frame_no - 1  # 裸=上一帧
        if not (0 <= ref < frame_no):
            raise ValueError("第 %d 行：CP 引用 %d 非已写帧（< 本帧 %d）"
                             % (no, ref, frame_no))
        return op, {"ref": ref}
    if op == "SET":
        if len(toks) == 5:  # SET asset k param val
            asset, k, param, val = int(toks[1]), int(toks[2]), toks[3], float(toks[4])
        elif len(toks) == 4:  # 裸 k=0：SET asset param val
            asset, k, param, val = int(toks[1]), 0, toks[2], float(toks[3])
        else:
            raise ValueError("第 %d 行：SET token 数非法 %r" % (no, toks))
        param = param.strip('"')  # LLM 引号习惯（str 字段惯性）——canonical 裸 token
        if param not in _SET_PARAMS:
            raise ValueError("第 %d 行：SET param %r 不在白名单" % (no, param))
        _check_sane_numbers(no, op, {"val": val})
        return op, {"asset": asset, "k": k, "param": param, "val": val}
    if op == "INS":
        q1, q2 = line.index('"'), line.rindex('"')
        if q1 >= q2:
            raise ValueError("第 %d 行：INS 行载荷未闭合" % no)
        raw_line = line[q1 + 1:q2]
        pos = int(toks[1]) if not line[len("INS "):].startswith('"') else None
        sub_op, _sub = _rc.parse_line_px(raw_line)  # 载荷须是合法 :px 行
        if sub_op not in LLM_OPS:
            raise ValueError("第 %d 行：INS 载荷 %r 不在内容行白名单" % (no, sub_op))
        return op, {"pos": pos, "line": raw_line}  # pos=None=行尾（resolve 回填）
    if op == "DEL":
        return op, {"pos": int(toks[1])}
    # ---- Tier2（对象编辑，帧内融合语义）----
    if op in ("MOVE", "PLACE"):
        nums = toks[1:]
        if len(nums) == 3:  # 裸 k=0：asset dx dy / asset x y
            asset, k, a, b = int(nums[0]), 0, float(nums[1]), float(nums[2])
        elif len(nums) == 4:
            asset, k, a, b = int(nums[0]), int(nums[1]), float(nums[2]), float(nums[3])
        else:
            raise ValueError("第 %d 行：%s token 数非法 %r" % (no, op, toks))
        _check_sane_numbers(no, op, {"a": a, "b": b})
        key = "dx dy" if op == "MOVE" else "x y"
        return op, {"asset": asset, "k": k, key.split()[0]: a, key.split()[1]: b}
    if op == "POSE":
        q1, q2 = line.index('"'), line.rindex('"')
        raw_line = line[q1 + 1:q2]
        sub_op, sub = _rc.parse_line_px(raw_line)
        if sub_op != "draw":
            raise ValueError("第 %d 行：POSE 载荷须是 draw 行（对象形态）" % no)
        head = line[:q1].split()  # POSE [asset] [k]（引号前——载荷含空格不能整体 split）
        m = head[1:]
        asset = int(m[0]) if m else sub["tex"]
        k = int(m[1]) if len(m) > 1 else 0
        return op, {"asset": asset, "k": k, "line": raw_line}
    if op == "ENTER":
        q1, q2 = line.index('"'), line.rindex('"')
        raw_line = line[q1 + 1:q2]
        sub_op, _sub = _rc.parse_line_px(raw_line)
        if sub_op not in LLM_OPS:
            raise ValueError("第 %d 行：ENTER 载荷 %r 不在内容行白名单" % (no, sub_op))
        return op, {"line": raw_line}
    if op == "EXIT":
        nums = toks[1:]
        asset, k = int(nums[0]), (int(nums[1]) if len(nums) > 1 else 0)
        return op, {"asset": asset, "k": k}
    raise ValueError("第 %d 行：未知增量 op %r" % (no, op))


def parse_chunk(chunk_text):
    """LLM chunk → [(帧号, [(op, fields), ...]), ...]（:px 档；增量含缺省回填）。

    dream 帧纪律：一帧 = 全量行 | 纯 CP | 编辑行组（Tier1/Tier2 可混组）。
    dt/asset/ev/end/st 行属 runner 或 px 不支持——出现即 ValueError。
    防御纵深：畸形 token 流（点列/颜色分量不足等）统一 IndexError→ValueError，
    runner 打回重试通道只认 ValueError 语义；其余异常照常穿透（真 bug 该炸还炸）。
    """
    try:
        return _parse_chunk(chunk_text)
    except IndexError as e:
        raise ValueError("chunk 行 token 数不足（畸形点列/分量/参数）：%s" % e) from None


def _parse_chunk(chunk_text):
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
            first = line.split(" ")[0]
            if first in _RUNNER_OPS:
                raise ValueError("第 %d 行：%s 行属 runner 职责，LLM 不得书写" % (no, first))
            if first == "st":
                raise ValueError("第 %d 行：dream :px 档不写 st" % no)
            if first in TIER1 or first in TIER2:
                op, fields = _parse_delta_line(no, line, cur[0])
                if any(o not in TIER1 and o not in TIER2 for o, _ in cur[1]):
                    raise ValueError("第 %d 行：增量行不得与全量行混帧" % no)
                cur[1].append((op, fields))
            elif first in LLM_OPS or first in _rc._PX_SHORT_BY:
                if any(o in TIER1 or o in TIER2 for o, _ in cur[1]):
                    raise ValueError("第 %d 行：全量行不得与增量行混帧" % no)
                op, fields = _rc.parse_line_px(line)
                _check_sane_numbers(no, op, fields)
                cur[1].append((op, fields))
            else:
                raise ValueError("第 %d 行：op %r 不在 dream 内容行白名单" % (no, first))
    if cur is not None:
        frames.append(cur)
    if not frames:
        raise ValueError("chunk 无 frame 块")
    return frames


# ---- 展开与降级（Tier2 → Tier1；CP → 行集引用；d_crc 三口径） ----

def _find_draw(base, asset, k):
    """展开态中找 (asset,k) 的 draw 行 → 下标；未命中 ValueError。"""
    seen = 0
    for i, (op, f) in enumerate(base):
        if op == "draw" and f["tex"] == asset:
            if seen == k:
                return i
            seen += 1
    raise ValueError("对象 (%d,%d) 未配对——帧内无该资产的第 %d 个 draw 实例"
                     % (asset, k, k))


def resolve_frames(frames):
    """词汇面 frames → (canonical frames, 展开态, 每帧 d_crc)。

    canonical：CP/SET/INS/DEL（Tier2 已降级，全显式形）——落流文本。
    展开态：每帧全量 (op, fields) 行集——d_crc 与后续帧基线。
    """
    canon, expanded, dcrcs = [], [], []
    for fi, (no, rows) in enumerate(frames):
        kinds = {op for op, _ in rows}
        if fi == 0 and (kinds & TIER1 or kinds & TIER2):
            raise ValueError("帧 0 禁用增量（无基线）——首帧必须全量行")
        if kinds & TIER2 or (kinds & TIER1 and "CP" not in kinds):
            # 编辑帧：基线=上一帧展开态（或 CP 换基线）
            base_idx = no - 1
            if "CP" in kinds and len(rows) == 1:
                pass  # 纯 CP 帧走下行分支
            if not expanded:
                raise ValueError("帧 %d 编辑无基线" % no)
            base = [(r[0], dict(r[1])) for r in expanded[base_idx]]
            out_rows = []
            for op, f in rows:
                if op == "CP":
                    base = [(r[0], dict(r[1])) for r in expanded[f["ref"]]]
                    out_rows.append(("CP", {"ref": f["ref"]}))
                elif op == "SET":
                    i = _find_draw(base, f["asset"], f["k"])
                    base[i][1][f["param"]] = f["val"]
                    out_rows.append((op, f))
                elif op == "INS":
                    pos = f["pos"] if f["pos"] is not None else len(base)
                    sub_op, sub = _rc.parse_line_px(f["line"])
                    base.insert(pos, (sub_op, sub))
                    out_rows.append(("INS", {"pos": pos, "line": f["line"]}))
                elif op == "DEL":
                    if f["pos"] >= len(base):
                        raise ValueError("帧 %d DEL pos %d 越界（行数 %d）"
                                         % (no, f["pos"], len(base)))
                    del base[f["pos"]]
                    out_rows.append((op, f))
                elif op in ("MOVE", "PLACE"):
                    i = _find_draw(base, f["asset"], f["k"])
                    if op == "MOVE":
                        nx, ny = base[i][1]["x"] + f["dx"], base[i][1]["y"] + f["dy"]
                    else:
                        nx, ny = f["x"], f["y"]
                    for param, val in (("x", nx), ("y", ny)):
                        base[i][1][param] = val
                        out_rows.append(("SET", {"asset": f["asset"], "k": f["k"],
                                                 "param": param, "val": val}))
                elif op == "POSE":
                    i = _find_draw(base, f["asset"], f["k"])
                    sub_op, sub = _rc.parse_line_px(f["line"])
                    base[i] = (sub_op, sub)
                    out_rows.append(("DEL", {"pos": i}))
                    out_rows.append(("INS", {"pos": i, "line": f["line"]}))
                elif op == "ENTER":
                    sub_op, sub = _rc.parse_line_px(f["line"])
                    base.append((sub_op, sub))
                    out_rows.append(("INS", {"pos": len(base) - 1, "line": f["line"]}))
                elif op == "EXIT":
                    i = _find_draw(base, f["asset"], f["k"])
                    del base[i]
                    out_rows.append(("DEL", {"pos": i}))
            expanded.append(base)
            dcrcs.append(crc32_rows(_rc.render_line_px(op, f) for op, f in base))
            canon.append((no, out_rows))
        elif "CP" in kinds:
            ref = rows[0][1]["ref"]
            base = [(r[0], dict(r[1])) for r in expanded[ref]]
            expanded.append(base)
            dcrcs.append(zlib.crc32(("same:%d" % ref).encode()) & 0xFFFFFFFF)
            canon.append((no, [("CP", {"ref": ref})]))
        else:
            expanded.append([(op, dict(f)) for op, f in rows])
            dcrcs.append(crc32_rows(_rc.render_line_px(op, f) for op, f in rows))
            canon.append((no, rows))
    return canon, expanded, dcrcs


def seal_frames(canon_frames, kit_rows, dt, dcrcs):
    """canonical frames → Session entries。行序：dt → asset(仅首帧) → 行集 → end。"""
    entries, first = [], True
    for (_no, rows), d in zip(canon_frames, dcrcs):
        block = [("dt", {"val": dt})]
        if first:
            block += list(kit_rows)
            first = False
        block += rows
        block.append(("s_crc", {"crc": 0}))  # px 生成档无 st——哨兵（D14：回放不消费）
        block.append(("d_crc", {"crc": d}))
        entries.append(("frame", block))
    return entries


def build_session(entries, seed, width=640, height=480, has_same=False):
    return dict(width=width, height=height, sha=table_sha(), loglvl="full",
                seed=seed, prec="px", delta=has_same,  # CP/编辑行在场→head +d
                entries=[("cmnt", "dream runner session (B18 :px)")] + entries)


def write_session(s, path):
    text = fr_session.dump_text(s)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(text)
    return text
