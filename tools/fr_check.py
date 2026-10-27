#!/usr/bin/env python3
# tools/fr_check.py
"""fr-check：会话校验器 + FileCheck 式判据运行器。

用法:
    python tools/fr_check.py <in.fr|in.frb> [checks.txt] [--strict]

  input       输入会话文件，双输入按 magic 自动识别（FRB1=二进制）
  checks.txt  可选 FileCheck 式判据文件（'#' 注释，空行跳过）
  --strict    sha 对账不一致从 WARNING 升级为 FAIL

内置校验（无判据文件也执行）：
  1. canonical 幂等——.fr 输入 dump_text(parse_text(raw))==raw，.frb 输入
     dump_binary(parse_binary(raw))==raw；不等即 FAIL（消息含"幂等"）
  2. sha 对账——流内 sha ≠ 当前 tables/cmd.tbl 指纹：默认 WARNING 到
     stderr（sha 是录制时元数据，不代表流非法），--strict 升级为 FAIL

判据指令（对 dump 的 canonical 文本行逐条求值）：
  CHECK: <子串>        dump 输出任意行含该子串即命中
  CHECK-NEXT: <子串>   恰为上一命中行的下一行才算命中
  CHECK-NOT: <子串>    上一命中行（不含）至本次命中行（不含）之间不得
                       出现；结尾悬空的 NOT 扫到 EOF

输出纪律：stdout/stderr 都写 UTF-8 字节（B1 教训——中文错误消息字节
精确是判据，测试不做 text=True）。
退出码：0 全过（stdout "CHECK OK (<n> directives)"，n 含 NOT）；1 校验/
判据失败（stderr "FAIL: …"，报指令 + 定位）；2 用法错误 / 判据行无法解析。
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import fr_session as fs
from tools.fr_gen import tbl

_TBL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "tables", "cmd.tbl")


def _out(msg):
    sys.stdout.buffer.write((msg + "\n").encode("utf-8"))


def _err(msg):
    sys.stderr.buffer.write((msg + "\n").encode("utf-8"))


def _load_raw(path):
    with open(path, "rb") as f:
        return f.read()


def _builtin(raw, strict):
    """内置校验：canonical 幂等 + sha 对账。

    返回 (session, 失败消息列表)；sha 不一致在非 strict 下只发 WARNING 到
    stderr（sha 是录制时元数据）。表指纹每次现算（表可被 fr-gen 再生）。
    """
    fails = []
    if raw[:4] == fs.MAGIC:
        s = fs.parse_binary(raw)
        if fs.dump_binary(s) != raw:
            fails.append("canonical 幂等失败（.frb）")
    else:
        text = raw.decode("utf-8")
        s = fs.parse_text(text)
        if fs.dump_text(s) != text:
            fails.append("canonical 幂等失败（.fr）")
    with open(_TBL_PATH, encoding="utf-8") as f:
        cur_sha = tbl.tbl_sha256(tbl.parse(f.read()))
    if s["sha"] != cur_sha:
        msg = "sha 对账：流内 sha %s ≠ 当前表指纹 %s（录制时元数据）" % (s["sha"], cur_sha)
        if strict:
            fails.append(msg)
        else:
            _err("WARNING: " + msg)
    return s, fails


def _run_checks(lines, directives):
    """FileCheck 式判据执行，返回失败消息列表（空 = 全过）。

    cursor = 上一命中行 +1（0 起计行索引）。CHECK 全文任意行命中（命中后
    cursor 仍推进到命中行+1，作 NEXT/NOT 的参照）；NEXT 恰为 cursor 行命中；
    NOT 扫 [cursor, 本次命中行)，悬空扫 [cursor, EOF)，NOT 不推进 cursor。
    任一 CHECK/CHECK-NEXT 失败即停（后续判据不再执行）。
    """
    fails = []
    cursor = 0
    pending_not = []     # [(pat, 判据行号), ...] 等下一次命中（或 EOF）定界
    for kind, pat, src_no in directives:
        if kind == "CHECK-NOT":
            pending_not.append((pat, src_no))
            continue
        if kind == "CHECK-NEXT":
            found = cursor if cursor < len(lines) and pat in lines[cursor] else None
        else:
            found = next((i for i in range(len(lines)) if pat in lines[i]), None)
        for p, pno in pending_not:
            hit = next((j for j in range(cursor, found if found is not None else len(lines))
                        if p in lines[j]), None)
            if hit is not None:
                fails.append("CHECK-NOT: %s（判据第 %d 行）— dump 第 %d 行禁含而命中"
                             % (p, pno, hit + 1))
        pending_not = []
        if found is None:
            if kind == "CHECK-NEXT":
                fails.append("%s: %s（判据第 %d 行）— dump 第 %d 行未含该续行"
                             % (kind, pat, src_no, cursor + 1))
            else:
                fails.append("%s: %s（判据第 %d 行）— dump 全文未命中" % (kind, pat, src_no))
            break
        cursor = found + 1
    for p, pno in pending_not:   # 结尾悬空 NOT：扫到 EOF
        hit = next((j for j in range(cursor, len(lines)) if p in lines[j]), None)
        if hit is not None:
            fails.append("CHECK-NOT: %s（判据第 %d 行）— dump 第 %d 行禁含而命中"
                         % (p, pno, hit + 1))
    return fails


def main(argv):
    args = list(argv)
    strict = "--strict" in args
    if strict:
        args.remove("--strict")
    path = args[0] if args else None
    checks = args[1] if len(args) > 1 else None
    if not path:
        sys.stderr.buffer.write(__doc__.strip().encode("utf-8") + b"\n")
        return 2
    n_directives = 0
    fails = []
    try:
        raw = _load_raw(path)
        s, bf = _builtin(raw, strict)
        fails += bf
        lines = fs.dump_text(s).split("\n")
        directives = []          # [(kind, pat, 判据文件行号), ...]
        if checks:
            with open(checks, encoding="utf-8") as f:
                for no, line in enumerate(f, start=1):
                    line = line.rstrip("\n")
                    if not line.strip() or line.startswith("#"):
                        continue
                    for kind in ("CHECK-NEXT", "CHECK-NOT", "CHECK"):   # 长前缀在前
                        if line.startswith(kind + ":"):
                            directives.append((kind, line[len(kind) + 1:].strip(), no))
                            break
                    else:
                        _err("fr-check: 判据第 %d 行无法解析: %s" % (no, line))
                        return 2
        fails += _run_checks(lines, directives)
        n_directives = len(directives)
    except (fs.SessionError, ValueError, OSError, tbl.TblError) as e:
        _err("fr-check: %s" % e)
        return 1
    if fails:
        for m in fails:
            _err("FAIL: " + m)
        return 1
    _out("CHECK OK (%d directives)" % n_directives)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
