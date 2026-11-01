# tools/fr_diff.py
"""fr-diff：两会话流帧对齐 diff——行为对拍（改前 vs 改后）与首分歧帧定位。

用法:
    python tools/fr_diff.py <a.fr|a.frb> <b.fr|b.frb> [--frames a-b] [--context N]
                            [--first-only]

  --frames      只比对帧号区间（含端点）；缺省全帧
  --context N   分歧帧处输出前后帧的行级 diff 上下文（缺省 1：只报首分歧帧
                的行 diff）
  --first-only  只报首分歧帧号与该帧行 diff（fr-bisect 语义：定位回归起点）

比对口径：canonical 文本逐字节（字节相等律——dt 浮点文本、行序全部敏感）。
头行（frb1…）与 cmnt/asset 行先比对（帧 0 前缀），再帧块对齐比对。

输出（stdout，UTF-8）:
    HEAD <same|diff>                  头行是否一致（diff 时打印两行）
    FRAMES a=<n> b=<m>                双方帧数
    FIRST-DIVERGENCE <idx|-1>         首分歧帧号（-1=全同）
    帧 <idx> 行 diff:                 '- '仅 A 有 / '+ '仅 B 有（按行对齐）

退出码：0 双流全同；1 存在分歧（定位信息已打印）；2 用法/解析错误。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import fr_session as fs


def _dump_lines(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:4] == fs.MAGIC:
        return fs.dump_text(fs.parse_binary(raw)).split("\n")
    # CRLF 容忍（fr-as 同规矩：读入即归一 LF——write_text 在 Windows 产 CRLF）
    return fs.dump_text(
        fs.parse_text(raw.decode("utf-8").replace("\r\n", "\n"))).split("\n")


def _split_frames(lines):
    """canonical 行列表 → (前缀行, {帧号: 块行列表}, 帧号序列)。"""
    prefix, frames, order, cur = [], {}, [], None
    for ln in lines:
        if ln.startswith("frame "):
            cur = int(ln.split()[1])
            frames[cur] = []
            order.append(cur)
        elif cur is None:
            prefix.append(ln)
        else:
            frames[cur].append(ln)
    return prefix, frames, order


def _row_diff(a_rows, b_rows):
    """两行集的行级 diff（保持顺序的集合差——对齐 out 行序敏感）。"""
    from collections import OrderedDict
    seen_b = OrderedDict.fromkeys(b_rows)
    seen_a = OrderedDict.fromkeys(a_rows)
    out = []
    for r in a_rows:
        if r not in seen_b:
            out.append("- " + r)
    for r in b_rows:
        if r not in seen_a:
            out.append("+ " + r)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fr-diff")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--frames")
    ap.add_argument("--context", type=int, default=1)
    ap.add_argument("--first-only", action="store_true")
    a = ap.parse_args(argv)

    try:
        la, lb = _dump_lines(a.a), _dump_lines(a.b)
    except (fs.SessionError, ValueError, OSError) as e:
        print("fr-diff: %s" % e, file=sys.stderr)
        return 2
    pa, fa, oa = _split_frames(la)
    pb, fb, ob = _split_frames(lb)
    print("HEAD %s" % ("same" if pa == pb else "diff"))
    if pa != pb:
        for r in pa:
            if r not in pb:
                print("- " + r)
        for r in pb:
            if r not in pa:
                print("+ " + r)
    print("FRAMES a=%d b=%d" % (len(oa), len(ob)))

    lo, hi = 0, max(len(oa), len(ob)) - 1
    if a.frames:
        parts = a.frames.split("-")
        lo, hi = int(parts[0]), int(parts[-1])

    first = -1
    n = min(len(oa), len(ob))
    for i in range(n):
        if not (lo <= i <= hi):
            continue
        if fa[oa[i]] != fb[ob[i]]:
            first = i
            break
    if first == -1 and len(oa) != len(ob) and hi >= min(len(oa), len(ob)):
        first = min(len(oa), len(ob))  # 公共前缀全同，一方多帧=帧数分歧
    print("FIRST-DIVERGENCE %d" % first)
    if first == -1:
        return 0
    shown = 1 if a.first_only else max(1, a.context)
    for i in range(first, min(first + shown, n)):
        d = _row_diff(fa[oa[i]], fb[ob[i]])
        if d:
            print("帧 %d 行 diff:" % i)
            for r in d[:40]:
                print(r)
    if len(oa) != len(ob):
        print("（帧数分歧：a=%d b=%d）" % (len(oa), len(ob)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
