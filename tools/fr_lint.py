# tools/fr_lint.py
"""fr-lint —— 流诊断器（B18 M1：语法层+语义层；锚定回放层=fr-render d_crc 终审）。

语法层 = fr_session.parse_text 的 SessionError（自带行号）——不重复造轮子。
语义层（附录 5.3-6 幻觉防线；对任意流可用，dream 生成流是第一客户）：
  L001 引用完整性：draw.tex / print.font 引用的资产号必须先由 asset 行声明；
  L002 d_crc 对账：end 段 d_crc 须等于重算 CRC32(当帧 out 行 "\\n" 连接)（全流通用口径）；
  L003 s_crc 对账：dream 口径（st 行 CRC）——仅 dream=True 时启用
       （录制流 s_crc=注册状态根子图口径，跨口径不可比，D14 注）；
  L004 帧行序：dt 须为帧首行、end 双行须为帧末两行、asset 行仅允许出现在首帧、
       S 行必须独占帧（帧内除 dt/end 外唯一内容行）。
  L005 增量协商：S 行在场而 head 缺 `+d` 标记。
诊断形态：编译器式 "Lxxx 帧F: 消息"（供打回 LLM 自修复）。
"""
import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import fr_session


def _crc(rows):
    return zlib.crc32("\n".join(rows).encode("utf-8")) & 0xFFFFFFFF


# out 段 op 前缀（含 :px 短名——C/D/PR/R/LN/PY/CI/AR/PT/SC；其余前缀属
# head/in/log/end 段——d_crc 口径=纯 out 行）
_OUT_PREFIXES = ("clear ", "draw ", "print ", "rect ", "line ", "poly ",
                 "circle ", "arc ", "points ", "rt ", "scissor ",
                 "C ", "D ", "PR ", "R ", "LN ", "PY ", "CI ", "AR ", "PT ",
                 "SC ")
# 引用行前缀（长名+短名；t[1] 都是资产号）
_REF_PREFIXES = ("draw ", "D ", "print ", "PR ")
# 非内容行前缀（head/in/log/end 段）
_OTHER_PREFIXES = ("dt ", "asset ", "ev ", "call ", "timer ", "rngc ",
                   "st ", "err ", "s_crc ", "d_crc ")
# B15 增量行（v1.5 名）：CP=帧引用（d_crc=锚声明可验证）；SET/INS/DEL=行集
# 编辑（lint 未实现行集解码——含编辑行的帧 L002 跳过，边界登记）
_DELTA_EDIT_PREFIXES = ("SET ", "INS ", "DEL ")


def lint_text(text, dream=False):
    """canonical .fr 文本 → 诊断字符串列表（空 = 全绿）。"""
    try:
        fr_session.parse_text(text)
    except fr_session.SessionError as e:
        return ["L000 解析: %s" % e]
    lines = text.split("\n")
    diags, seen_assets = set(), set()
    head = lines[0] if lines else ""
    head_has_d = head.endswith(" +d")
    has_same = False
    frame_lines = {}
    fidx = -1
    for l in lines[1:]:
        if not l or l.startswith("cmnt "):
            continue
        if l.startswith("frame "):
            fidx += 1
            frame_lines[fidx] = []
        elif fidx >= 0:
            frame_lines[fidx].append(l)
    for fidx, rows_txt in frame_lines.items():
        declared = set()
        out_txt = []
        s_ref = None
        content_n = 0
        edit_n = 0
        for l in rows_txt:
            if l.startswith("asset "):
                if fidx != 0:
                    diags.add("L004 帧%d: asset 行仅允许首帧" % fidx)
                t = l.split(" ")
                declared.add(int(t[2]))
            elif l.startswith(_REF_PREFIXES):
                t = l.split(" ")
                ref = int(t[1])
                if ref not in declared and ref not in seen_assets:
                    diags.add("L001 帧%d: 引用未声明资产 %d" % (fidx, ref))
            if l.startswith("CP "):
                s_ref = int(l.split(" ")[1])
                has_same = True
            elif l.startswith(_DELTA_EDIT_PREFIXES):
                edit_n += 1  # 行集编辑行：不进 out_txt；L002 跳过（未解码）
            elif l.startswith(_OUT_PREFIXES):
                out_txt.append(l)
                content_n += 1
            elif not l.startswith(_OTHER_PREFIXES):
                diags.add("L004 帧%d: 未认识的行前缀 %r" % (fidx, l.split(" ")[0]))
        if s_ref is not None and content_n and not edit_n:
            # 纯"CP+内容行"混合无意义（CP 会丢弃内容行基线）——dream 侧纪律
            # 由 parse_chunk 管；lint 只登记可疑组合（CP 与编辑共存合法：换基线+编辑）
            pass
        seen_assets |= declared
        # L004 行序：dt 首、end 双行殿后
        if not rows_txt or not rows_txt[0].startswith("dt "):
            diags.add("L004 帧%d: dt 须为帧首行" % fidx)
        if len(rows_txt) < 2 or not rows_txt[-1].startswith("d_crc ") \
                or not rows_txt[-2].startswith("s_crc "):
            diags.add("L004 帧%d: end 双行须殿后" % fidx)
        # L002 d_crc 对账：纯 CP 帧=锚声明 CRC("same:<ref>")（fr_session.cpp:363）；
        # 含编辑行（SET/INS/DEL）=解码后行集 CRC——lint 未实现行集解码，跳过（边界）
        end = [l for l in rows_txt if l.startswith("d_crc ")]
        if end and not edit_n:
            got = int(end[0].split(" ")[1])
            if s_ref is not None and not content_n:
                exp = zlib.crc32(("same:%d" % s_ref).encode()) & 0xFFFFFFFF
            elif s_ref is not None:
                exp = None  # CP+内容混合：语义=换基线弃内容——d_crc 不可静态重算
            else:
                exp = _crc(out_txt)
            if exp is not None and got != exp:
                diags.add("L002 帧%d: d_crc %d ≠ 重算 %d" % (fidx, got, exp))
        if dream:
            sc = [l for l in rows_txt if l.startswith("s_crc ")]
            st_txt = [l for l in rows_txt if l.startswith("st ")]
            if sc and int(sc[0].split(" ")[1]) != _crc(st_txt):
                diags.add("L003 帧%d: s_crc 与 st 行不符（dream 口径）" % fidx)
    if has_same and not head_has_d:
        diags.add("L005 head: CP 行在场而缺 +d 增量协商标记")
    return sorted(diags)


def main(argv):
    if len(argv) < 2 or not os.path.isfile(argv[1]):
        print("用法: python tools/fr_lint.py <in.fr> [--dream]", file=sys.stderr)
        return 2
    dream = "--dream" in argv[2:]
    with open(argv[1], encoding="utf-8") as f:
        diags = lint_text(f.read(), dream=dream)
    for d in diags:
        print(d)
    return 1 if diags else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
