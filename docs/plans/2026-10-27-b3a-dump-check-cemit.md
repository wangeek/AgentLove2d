# B3a 实施计划：fr-dump / fr-check / C 字段级 emit

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补全工具面（fr-dump 锚行素材 / fr-check 判据运行器）并兑现 B0 顺延记账的 C 字段级 emit，以 gyl 跨目标字节回归收口。

**Architecture:** 两个 CLI 都是 `fr_session`/`fr_codec_gen` 公共 API 上的薄壳（B1 范式：直跑入口 + sys.path 补正 + 异常元组）。C emit 在 gen_c 模板展开 per-op 类型化函数（静态顺序 put，非运行时表驱动）+ 生成 `render/fr_selftest.c`（嵌入 Python 编码的期望字节，gyl 上编译运行即跨目标字节布局回归）。本批不动行级/会话级格式——**spec 零变更**。

**Tech Stack:** Python 3.11 标准库 + pytest；C99（真验证在 gyl：gcc -std=c99 -Wall -Werror）。

**依据：** design.md §6（B3a 范围，本批 Task 4 拆分 B3 行）、§5 工具族地图；B0 计划对 C emit 的承诺（"与 Python 共用字节布局回归"）；B1 终审建议②③（fr-check 判据两内置项、异常面收口归 fr-check 批次——本批的 fr-check 即落点）。

**C emit 签名映射（封版于本计划）**：

| 表类型 | C 形参 |
|---|---|
| u8 / u32 | `uint8_t` / `uint32_t`（按值） |
| f32 | `float`（按值；emit 内 `fr_qf` 量化） |
| rgba8 | `fr_rgba8`（按值） |
| str | `const char *`（NUL 结尾；长度 strlen——含 NUL 的 str 不支持，注释注明） |
| f32[] pts | `const float *pts, uint32_t pts_n`（显式长度后缀 `_n`） |
| args...（ev/call） | `const fr_variant *args, uint32_t argc` |

```c
typedef struct { uint8_t tag; double num; const char *str; } fr_variant;
/* tag 取 FR_VARIANT_TAG_NUM/STR/BOOL；bool 以 tag=BOOL + num=0/1 表达 */

static float fr_qf(double v);  /* snprintf("%.6f") → strtod → (float)；非有限值返回 0 并由调用方判失败 */
```

- 函数命名：`int fr_encode_<op>(fr_buf *b, ...)`，返回 0 成功 / -1 失败（容量不足、非有限浮点）。asset 按 kind 拆四个具名函数（`fr_encode_asset_image/canvas/quad/font`——asset 本是四合一，C 侧拆开更诚实）。
- 量化一致性依据：CPython `float(f"{v:.6f}")` 与 glibc `snprintf("%.6f")+strtod` 均为十进制正确舍入（half-even），语义相同；由 gyl 上的 selftest 字节比对最终裁决。

---

### Task 1: fr-dump CLI（TDD）

**Files:**
- Create: `tools/fr_dump.py`
- Test: `tests/test_dump.py`

**定位（含与 fr-dis 的边界，写进 docstring）**：fr-dis 只吃 `.frb`、输出会话文本；fr-dump **双输入**（按 magic `FRB1` 自动识别），输出 canonical 文本 + `--stats` 结构摘要 + `--frames a-b` 选帧（选帧视图丢弃全部 cmnt——过滤视图用于锚行，注释属整会话；帧号重排连续）。锚行判据统一引用 canonical 文本行。

- [ ] **Step 1: 失败测试** `tests/test_dump.py`：

```python
# tests/test_dump.py
import os, subprocess, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _run(*args):
    return subprocess.run([sys.executable, os.path.join(_ROOT, "tools", "fr_dump.py"), *args],
                          capture_output=True, text=True, cwd=_ROOT)

def _golden_paths():
    return (os.path.join(_ROOT, "tests/golden/sample.fr"),
            os.path.join(_ROOT, "tests/golden/sample.frb"))

def test_dual_input_identical_dump(tmp_path):
    fr, frb = _golden_paths()
    r1 = _run(fr); r2 = _run(frb)
    assert r1.returncode == 0 and r2.returncode == 0, (r1.stderr, r2.stderr)
    assert r1.stdout == r2.stdout                       # 双输入同一 dump
    assert r1.stdout == open(fr, encoding="utf-8").read()  # 无 --stats 时 = canonical 原文

def test_stats_block():
    r = _run(_golden_paths()[0], "--stats")
    assert r.returncode == 0
    assert "# frames=2" in r.stdout and "# op draw: 1" in r.stdout

def test_frames_filter(tmp_path):
    fr, _ = _golden_paths()
    r = _run(fr, "--frames", "1-1")
    assert r.returncode == 0
    out = r.stdout.split("\n")
    assert "frame 0" in out and "frame 1" not in out    # 重排连续
    assert not any(l.startswith("cmnt ") for l in out)  # 过滤视图丢 cmnt

def test_bad_file():
    r = _run(os.path.join(str(tmp_path), "nope.fr"))
    assert r.returncode == 1
```

（`# op draw: 1` 的具体格式以实现为准，测试与实现同批定稿——断言只锁"frames 计数"与"按 op 计数存在"两个稳定事实。）

- [ ] **Step 2: 红灯**（ModuleNotFoundError / 文件不存在）。

- [ ] **Step 3: 实现** `tools/fr_dump.py`（薄壳，~90 行）：

```python
#!/usr/bin/env python3
"""fr-dump：会话 → canonical 文本 + 结构摘要（锚行判据素材）。

用法: fr_dump <in.fr|in.frb> [--frames a-b] [--stats]
双输入按 magic 自动识别（FRB1=二进制）。与 fr-dis 的边界：fr-dis 只吃 .frb 且
只出会话文本；本工具双输入，--frames 选帧（丢弃 cmnt，帧号重排连续），
--stats 追加 '#' 注释摘要块。锚行判据统一引用 canonical 文本行。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import fr_session as fs

def _load(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:4] == fs.MAGIC:
        return fs.parse_binary(raw)
    return fs.parse_text(raw.decode("utf-8"))

def _filter_frames(s, spec):
    a, _, b = spec.partition("-")
    lo = int(a)
    hi = int(b) if b else lo
    frames = [(i, e[1]) for i, e in enumerate(s["entries"]) if e[0] == "frame"]
    entries = [("frame", rows) for i, rows in frames if lo <= i <= hi]
    return dict(s, entries=entries)

def _stats(s):
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
    path, rng, stats = None, None, False
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--frames":
            rng = args.pop(0) if args else None
        elif a == "--stats":
            stats = True
        else:
            path = a
    if not path:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        s = _load(path)
        if rng is not None:
            s = _filter_frames(s, rng)
        out = fs.dump_text(s)
        if stats:
            out += _stats(s)
        sys.stdout.buffer.write(out.encode("utf-8"))
    except (fs.SessionError, ValueError, OSError) as e:
        print("fr-dump: %s" % e, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: 绿灯**（`python -m pytest tests/test_dump.py -v` → 4 passed；全量 49 passed, 1 skipped）。

- [ ] **Step 5: Commit** `feat(tools): fr-dump——双输入 canonical dump + stats/选帧（TDD）`

### Task 2: fr-check CLI（TDD）

**Files:**
- Create: `tools/fr_check.py`
- Test: `tests/test_check.py`

**定位**：判据运行器。**内置校验**（无需判据文件即执行）：①canonical 幂等——.fr 输入 `dump_text(parse_text(raw))==raw`，.frb 输入 `dump_binary(parse_binary(raw))==raw`；②sha 对账——流内 sha ≠ 当前 cmd.tbl 指纹 → 默认 WARNING（sha 是录制时元数据），`--strict` 升级为 FAIL。**判据文件**（FileCheck 式，`#` 注释）：`CHECK: <子串>`（dump 输出任意行命中）、`CHECK-NEXT: <子串>`（紧跟上一次命中行的下一行）、`CHECK-NOT: <子串>`（上一次命中行与本次命中行之间不得出现；结尾悬空的 NOT 扫到 EOF）。任一失败：stderr 报指令与上下文（前后各 2 行），exit 1；全过打印 `CHECK OK (<n> directives)`，exit 0。

- [ ] **Step 1: 失败测试** `tests/test_check.py`：

```python
# tests/test_check.py
import os, subprocess, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD_FR = os.path.join(_ROOT, "tests/golden/sample.fr")

def _run(*args):
    return subprocess.run([sys.executable, os.path.join(_ROOT, "tools", "fr_check.py"), *args],
                          capture_output=True, text=True, cwd=_ROOT)

def test_builtin_ok_on_golden():
    r = _run(GOLD_FR)
    assert r.returncode == 0 and "CHECK OK (0 directives)" in r.stdout

def test_builtin_ok_on_frb():
    r = _run(os.path.join(_ROOT, "tests/golden/sample.frb"))
    assert r.returncode == 0

def test_directives_pass(tmp_path):
    cf = tmp_path / "checks.txt"
    cf.write_text("# 判据\n"
                  "CHECK: draw 1 3\n"
                  "CHECK-NEXT: print\n"
                  "CHECK: s_crc \n"
                  "CHECK-NOT: op nosuch\n", encoding="utf-8")
    r = _run(GOLD_FR, str(cf))
    assert r.returncode == 0 and "CHECK OK (4 directives)" in r.stdout

def test_check_fail_reports(tmp_path):
    cf = tmp_path / "checks.txt"
    cf.write_text("CHECK: draw 1 3\nCHECK: op nosuchop\n", encoding="utf-8")
    r = _run(GOLD_FR, str(cf))
    assert r.returncode == 1
    assert "CHECK: op nosuchop" in r.stderr

def test_check_not_fail(tmp_path):
    cf = tmp_path / "checks.txt"
    cf.write_text("CHECK-NOT: draw\n", encoding="utf-8")
    r = _run(GOLD_FR, str(cf))
    assert r.returncode == 1

def test_sha_mismatch_strict(tmp_path):
    from tools.fr_gen import tbl
    from tools import fr_codec_gen as fc
    from tools import fr_session as fs
    sha = "0" * 64
    rows = [(op, dict(f)) for op, f in fc.self_test_samples()[:2]]
    s = dict(width=1, height=1, sha=sha, loglvl="base", seed=0, entries=[("frame", rows)])
    bad = tmp_path / "wrongsha.frb"
    bad.write_bytes(fs.dump_binary(s))
    r = _run(str(bad))                                  # 默认：警告不失败
    assert r.returncode == 0 and "sha" in (r.stdout + r.stderr)
    r = _run(str(bad), "--strict")                      # strict：失败
    assert r.returncode == 1

def test_idempotency_fail(tmp_path):
    raw = open(GOLD_FR, "rb").read()
    broken = raw[:-2] + b"\n\n"                          # 破坏 canonical（尾加空行）
    f = tmp_path / "broken.fr"
    f.write_bytes(broken)
    r = _run(str(f))
    assert r.returncode == 1 and "幂等" in (r.stdout + r.stderr)
```

- [ ] **Step 2: 红灯**。

- [ ] **Step 3: 实现** `tools/fr_check.py`（~140 行）：

```python
#!/usr/bin/env python3
"""fr-check：会话校验器。内置 canonical 幂等 + sha 对账（--strict 升级）；
可选 FileCheck 式判据文件（CHECK / CHECK-NEXT / CHECK-NOT，'#' 注释）。
用法: fr_check <in.fr|in.frb> [checks.txt] [--strict]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import fr_session as fs
from tools.fr_gen import tbl
from tools import fr_codec_gen as fc

def _load_raw(path):
    with open(path, "rb") as f:
        return f.read()

def _builtin(raw, strict):
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
    if s["sha"] != tbl.tbl_sha256(tbl.parse(open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tables/cmd.tbl"), encoding="utf-8").read())):
        msg = "sha 对账：流内 sha 与当前表指纹不一致（录制时元数据）"
        if strict:
            fails.append(msg)
        else:
            print("WARNING: " + msg, file=sys.stderr)
    return s, fails

def _run_checks(lines, directives):
    fails, hits, pending_not, cursor = [], 0, [], 0
    for kind, pat in directives:
        if kind == "NOT":
            pending_not.append(pat)
            continue
        found = None
        i = cursor if kind == "NEXT" else 0
        while i < len(lines):
            if pat in lines[i]:
                if kind == "NEXT" and i != cursor:
                    break
                found = i
                break
            if kind == "NEXT":
                break
            i += 1
        for p in pending_not:
            hit = next((j for j in range(cursor, found if found is not None else len(lines))
                        if p in lines[j]), None)
            if hit is not None:
                fails.append("CHECK-NOT 失败（%d 行命中）：%s" % (hit + 1, p))
        pending_not = []
        if found is None:
            fails.append("%s 失败：%s" % (kind, pat))
            break
        cursor, hits = found + 1, hits + 1
        last = found
    for p in pending_not:
        hit = next((j for j in range(cursor, len(lines)) if p in lines[j]), None)
        if hit is not None:
            fails.append("CHECK-NOT 失败（%d 行命中）：%s" % (hit + 1, p))
    return fails, hits

def main(argv):
    args = list(argv)
    strict = "--strict" in args
    if strict:
        args.remove("--strict")
    path = args[0] if args else None
    checks = args[1] if len(args) > 1 else None
    if not path:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    fails = []
    try:
        raw = _load_raw(path)
        s, f = _builtin(raw, strict)
        fails += f
        lines = fs.dump_text(s).split("\n")
        directives = []
        if checks:
            for no, line in enumerate(open(checks, encoding="utf-8"), start=1):
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                for kind in ("CHECK-NEXT", "CHECK-NOT", "CHECK"):
                    if line.startswith(kind + ":"):
                        directives.append((kind, line[len(kind) + 1:].strip()))
                        break
                else:
                    print("fr-check: 判据第 %d 行无法解析" % no, file=sys.stderr)
                    return 2
        cf, n = _run_checks(lines, directives)
        fails += cf
    except (fs.SessionError, ValueError, OSError) as e:
        print("fr-check: %s" % e, file=sys.stderr)
        return 1
    if fails:
        for m in fails:
            print("FAIL: " + m, file=sys.stderr)
        return 1
    print("CHECK OK (%d directives)" % n)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

实现注记：`_run_checks` 的 NEXT 语义=「上一命中行的下一行」；NOT 扫描区间=[cursor, 本次命中行)。用例覆盖不了的边界以测试实跑为准微调，断言强度不减；`last` 变量若未用到即删。

- [ ] **Step 4: 绿灯**（6 passed；全量 55 passed, 1 skipped）。

- [ ] **Step 5: Commit** `feat(tools): fr-check——canonical 幂等/sha 对账内置 + FileCheck 式判据（TDD）`

### Task 3: C 字段级 emit（gen_c 模板展开 + fr_selftest.c 生成）

**Files:**
- Modify: `tools/fr_gen/gen_c.py`（emit 模板 + selftest 生成）
- Regenerate: `render/fr_codec.h`、`render/fr_codec.c`、`render/fr_selftest.c`（新）
- Test: `tests/test_c_emit.py`

**Step 1 失败测试** `tests/test_c_emit.py`：

```python
# tests/test_c_emit.py
import os, re
from tools.fr_gen import tbl, gen_c
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _read(name):
    return open(os.path.join(_ROOT, "render", name), encoding="utf-8").read()

def test_selftest_exists_and_covers_all_samples():
    src = _read("fr_selftest.c")
    assert "C EMIT OK" in src
    for op, fields in fc.self_test_samples():
        expect = fc.encode_row(op, fields)
        assert expect.hex() in src.replace(" ", "")     # 期望字节已嵌入（去空白比对）

def test_header_has_typed_signatures():
    h = _read("fr_codec.h")
    assert "typedef struct { uint8_t tag; double num; const char *str; } fr_variant;" in h
    assert "int fr_encode_draw(fr_buf *b, uint32_t tex, uint32_t quad, float x, float y, float rot, float sx, float sy, float ox, float oy, fr_rgba8 color);" in h
    assert "int fr_encode_line(fr_buf *b, const float *pts, uint32_t pts_n, float width, fr_rgba8 color);" in h
    assert "int fr_encode_ev(fr_buf *b, uint32_t slot, const char *type, uint8_t src, const fr_variant *args, uint32_t argc);" in h
    for kind in ("image", "canvas", "quad", "font"):
        assert "fr_encode_asset_%s(" % kind in h

def test_regen_deterministic_incl_selftest(tmp_path):
    d = tmp_path / "render"; d.mkdir()
    rows = tbl.parse(open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read())
    gen_c.generate(rows, str(d))
    for name in ("fr_codec.h", "fr_codec.c", "fr_selftest.c"):
        assert (d / name).read_text(encoding="utf-8") == _read(name)
```

（签名断言与实现的实际参数序一致——以 cmd.tbl signature 列与"签名映射"为准；实现时若发现断言里的参数序写错，修正的是**测试**，参数序必须跟表。）

**Step 2 红灯** → **Step 3 实现**。gen_c 展开要点：

1. `.h`：`fr_variant` typedef、每 op 类型化声明（签名映射见计划头）、asset 四函数声明。emit 相关 `#include <stddef.h>` 已有。
2. `.c`：辅助族 `fr_put_u8/u32/f32(量化)/fr_put_str/fr_put_rgba8/fr_put_pts/fr_put_variant`（全部返回 int 0/-1，失败短路）；per-op 函数体 = 按表字段序的静态 put 序列（**生成期展开，非运行时表驱动**）；`fr_qf`：
```c
static int fr_qf(double v, float *out) {
    if (v != v || v > 1.7976931348623157e308 || v < -1.7976931348623157e308) return -1;
    char buf[64];
    snprintf(buf, sizeof buf, "%.6f", v);
    *out = (float)strtod(buf, NULL);
    return 0;
}
```
（`#include <stdio.h>` `<stdlib.h>` `<math.h>` 按需补——但 C99 -Werror 下保持零警告。）
3. `fr_selftest.c` 生成：对 `self_test_samples()` 每条——嵌入字段值 C 字面量（字符串经 C 转义）与期望字节 hex 数组；`main()` 逐条调用对应 `fr_encode_*` 到栈缓冲 → `memcmp` 期望字节（长度同比）；失败打印 op 与首差异偏移 return 1；全过打印 `"C EMIT OK <n> rows"` return 0。期望字节由 `fc.encode_row(op, fields).hex()` 注入。
4. 生成期自检（`_self_check`）扩展：.h 回读断言新增 fr_variant/fr_encode_draw 签名存在。
5. 横幅更新：`render/fr_codec.h/.c` 与 `gen_c.py` docstring 中的"字段级 emit 顺延至 B3"字样改为"已实现（B3a）"——记账闭环。

**Step 4 再生 + 绿灯**：`python -m tools.fr_gen.gen_c`；`python -m pytest -q` → 全量 + 3 新测试全绿（C 编译冒烟仍 SKIP）。

**Step 5 Commit** `feat(fr-gen): C 字段级 emit——类型化签名 + fr_selftest 期望字节嵌入（B0 顺延账清偿）`

### Task 4: gyl 跨目标回归 + 文档同步（控制器执行 + 收尾）

- [ ] **Step 1（控制器）**: scp `render/fr_codec.h/.c/fr_selftest.c` 至 gyl `/tmp/frsmoke`；`gcc -std=c99 -Wall -Werror fr_codec.c fr_selftest.c -o st && ./st` → 期望输出 `C EMIT OK 24 rows`（24 = self_test_samples 行数）。失败则回 Task 3 修。
- [ ] **Step 2**: design.md §6：B3 行拆分——`B3a 工具面补全（fr-dump/fr-check）+ C 字段级 emit ✅（2026-10-27，gyl 跨目标字节回归通过）`；新增 `B3b L0 纯 Lua 产流：代理 shim + 排干快照 run loop + 状态走查器（st 语义样机）`（验收线沿用原 B3：产出五段齐全会话文件；fr-dis 可读；fr-check 通过）。§4 fr-gen 机制卡 emit 表述同步（"字段级 emit 已实现（B3a，跨目标字节回归）"）。
- [ ] **Step 3**: AGENTS.md Setup 增补 `python tools/fr_dump.py <流> [--stats]` 与 `python tools/fr_check.py <流> [判据]`；测试计数更新。
- [ ] **Step 4**: 全量 + 提交 `docs: B3a 收尾——design 路线 B3 拆分 B3a/B3b，C emit 记账闭环`

---

## Self-Review 记录

- **验收覆盖**：本计划无独立验收线（属 B3 拆分的 B3a 半批），B3b 承接原 B3 验收线"fr-dis 可读；fr-check 通过"——fr-check 本批交付使该线可执行。
- **依赖顺序**：Task 3 的 gyl 验证在 Task 4——因为本机无编译器；若 gyl 不可达，Task 4 Step 1 阻塞上报（不许静默跳过——这是本批唯一的真实验证）。
- **类型一致性**：fr_variant 三字段（tag/num/str）与 Python variant 三态（num 裸数/str 单元组/bool）映射在 Task 3 selftest 构造中体现；签名映射表与 cmd.tbl signature 一一核对过（ev/call 的 args... 在签名末位——C 侧置于参数表末位）。
- **无占位符**：C emit 模板要点已给全（fr_qf 实现、辅助族清单、selftest 结构）；断言参数序若与表不符修测试不修表——已写明。
