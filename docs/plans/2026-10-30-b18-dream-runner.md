# B18 dream runner 实施计划（M1 离线短片）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLM 直出 canonical FR 行，runner 当会话后勤——`python -m dream.run` 产一条 ≥60 帧、fr-check 全绿、fr-render 可回放的 dream 流。

**Architecture:** 设计真源 `docs/plans/2026-10-30-b18-dream-runner-design.md`（D14 裁决链）。新代码两处：`dream/`（runner 四单元）+ `tools/fr_lint.py`、`tools/fr_assets.py`（工具族缺口回流）。芯全复用：fr_session（Session dict/canonical dump）、fr_codec_gen（行级 parse/render）、fr_check/fr_as/fr_dis/fr_render。职责切分：LLM 写内容行（st+out），runner 写封装行（header/asset/dt/end）。

**Tech Stack:** Python 3.x 标准库（zlib/json/urllib——零新依赖）；pytest；fork love.exe（仅离线回放验收用，缺失则跳过该测试）。

**关键口径（实现前必读）：**
- `d_crc = zlib.crc32("\n".join(当帧 out 行文本).encode()) & 0xFFFFFFFF`（与 l0/main.lua:134、fork C 同参：poly 0xEDB88320、init/xorout 0xFFFFFFFF）；`s_crc` 同法对 **st 行**（dream 口径，无内核）。
- 帧内行序（l0/main.lua:136-148 同构）：`dt → asset(仅首帧) → in → st → out → s_crc → d_crc`。
- Session dict 形：`dict(width, height, sha, loglvl="full", seed, prec="full", delta=False, entries)`，entries 元素 `("cmnt", str) | ("frame", [(op, fields), ...])`（fr_session.py:4-7）。
- 表指纹：`from tools.fr_gen import tbl; tbl.tbl_sha256(tbl.parse(open("tables/cmd.tbl", encoding="utf-8").read()))`（fr_check 会做 sha 对账，必须写真指纹）。
- canonical .fr：LF 结尾、无空行、无 \r——写文件用 `open(path, "w", newline="\n", encoding="utf-8")`。
- 测试跑法一律 Git Bash：`& 'D:\Program Files\Git\bin\bash.exe' -lc 'cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v'`（PowerShell 有引号剥离坑，下文命令均为 bash 形）。

---

### Task 1: dream 会话壳（session.py：parse_chunk / seal / build / write）

**Files:**
- Create: `dream/__init__.py`（空文件）
- Create: `dream/session.py`
- Test: `tests/test_dream.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_dream.py
"""B18 dream runner 测试组（M1）。--from-file 确定性模式全链，CI 零 token。"""
import os
import zlib

import pytest

from tools import fr_session
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _row(line):
    return fc.parse_line(line)


def test_parse_chunk_accepts_content_rows():
    from dream import session as ds
    chunk = ('frame 0\n'
             'st 0 "hero.x" num 10.000000\n'
             'clear 0 0 0 255\n'
             'draw 1 0 10.000000 20.000000 0.000000 1.000000 1.000000 0.000000 0.000000 255 255 255 255\n'
             '\n'
             'frame 1\n'
             'st 0 "hero.x" num 11.000000\n'
             'clear 0 0 0 255\n')
    frames = ds.parse_chunk(chunk)
    assert [n for n, _ in frames] == [0, 1]
    assert frames[0][1][0][0] == "st"
    assert frames[0][1][1][0] == "clear"


def test_parse_chunk_rejects_runner_rows():
    from dream import session as ds
    for bad in ('dt 0.066667', 'asset image 9 32 32 00', 's_crc 1', 'd_crc 1'):
        chunk = 'frame 0\n%s\nclear 0 0 0 255\n' % bad
        with pytest.raises(ValueError):
            ds.parse_chunk(chunk)


def test_seal_and_roundtrip(tmp_path):
    from dream import session as ds
    frames = ds.parse_chunk(
        'frame 0\nst 0 "hero.x" num 10.000000\n'
        'clear 0 0 0 255\n'
        'rect 0 0.000000 0.000000 640.000000 480.000000 0.000000 0.000000 1.000000 255 0 0 255\n')
    entries = ds.seal_frames(frames, kit_rows=[], dt=0.066667)
    # d_crc 口径：out 行文本 "\n" 连接的 zlib crc32
    out_txt = ["clear 0 0 0 255",
               "rect 0 0.000000 0.000000 640.000000 480.000000 0.000000 0.000000 1.000000 255 0 0 255"]
    expect_d = zlib.crc32("\n".join(out_txt).encode()) & 0xFFFFFFFF
    block = entries[0][1]
    d_row = [f for op, f in block if op == "d_crc"][0]
    assert d_row["crc"] == expect_d
    # 行序：dt 首行、end 双行殿后
    assert block[0][0] == "dt"
    assert [op for op, _ in block[-2:]] == ["s_crc", "d_crc"]
    # 全会话 canonical 幂等（fr_session 链路）
    s = ds.build_session(entries, seed=1)
    text = fr_session.dump_text(s)
    assert fr_session.dump_text(fr_session.parse_text(text)) == text
    p = tmp_path / "d.fr"
    ds.write_session(s, str(p))
    assert p.read_text(encoding="utf-8") == text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'dream'`）

- [ ] **Step 3: 最小实现**

```python
# dream/session.py
"""dream 会话壳（B18 M1）：LLM 内容行 → Session → canonical .fr。

职责切分（设计 §4）：LLM 写内容行（st + out op），runner 写封装行
（header/asset/dt/end）。CRC 口径与 l0/main.lua:132-134 及 fork C 侧同参：
d_crc=CRC32(out 行文本 "\\n" 连接)，s_crc=CRC32(st 行文本 "\\n" 连接)
——s_crc 是 dream 口径（LLM 自述账本），与录制流"注册状态根子图 CRC"
语义不同（D14 注记），回放不依赖。
"""
import os
import zlib

from tools import fr_session
from tools import fr_codec_gen as _rc
from tools.fr_gen import tbl

# LLM 可书写的 out op（cmd.tbl out 段全集中 dream M1 开放面）
LLM_OPS = {"clear", "draw", "print", "rect", "line", "poly", "circle",
           "arc", "points", "rt", "scissor"}
# 封装行白名单——出现在 chunk 里即职责越界
_RUNNER_OPS = {"dt", "asset", "ev", "call", "timer", "rngc", "err", "s_crc", "d_crc"}


def table_sha():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "tables", "cmd.tbl"), encoding="utf-8") as f:
        return tbl.tbl_sha256(tbl.parse(f.read()))


def crc32_rows(row_texts):
    """CRC32(行文本 "\\n" 连接)；空列表 = 0（zlib 空串口径）。"""
    return zlib.crc32("\n".join(row_texts).encode("utf-8")) & 0xFFFFFFFF


def parse_chunk(chunk_text):
    """LLM chunk → [(帧号, [(op, fields), ...]), ...]。

    chunk 形态：`frame N` 块序列，每块 st + out 内容行；块间空行宽松。
    dt/asset/ev/end 行属 runner，出现即 ValueError（职责切分纪律）。
    """
    frames, cur = [], None
    for no, line in enumerate(chunk_text.split("\n"), start=1):
        if not line.strip():
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
            op, fields = _rc.parse_line(line)
            if op in _RUNNER_OPS:
                raise ValueError("第 %d 行：%s 行属 runner 职责，LLM 不得书写" % (no, op))
            if op != "st" and op not in LLM_OPS:
                raise ValueError("第 %d 行：op %r 不在 dream 内容行白名单" % (no, op))
            cur[1].append((op, fields))
    if cur is not None:
        frames.append(cur)
    if not frames:
        raise ValueError("chunk 无 frame 块")
    return frames


def seal_frames(frames, kit_rows, dt):
    """[(帧号, rows)] → Session entries。行序：dt → asset(仅首帧) → st → out → end 双行。"""
    entries, first = [], True
    for _no, rows in frames:
        st_rows = [(op, f) for op, f in rows if op == "st"]
        out_rows = [(op, f) for op, f in rows if op != "st"]
        block = [("dt", {"val": dt})]
        if first:
            block += list(kit_rows)
            first = False
        block += st_rows + out_rows
        st_txt = [_rc.render_line(op, f) for op, f in st_rows]
        out_txt = [_rc.render_line(op, f) for op, f in out_rows]
        block.append(("s_crc", {"crc": crc32_rows(st_txt)}))
        block.append(("d_crc", {"crc": crc32_rows(out_txt)}))
        entries.append(("frame", block))
    return entries


def build_session(entries, seed, width=640, height=480):
    return dict(width=width, height=height, sha=table_sha(), loglvl="full",
                seed=seed, prec="full", delta=False,
                entries=[("cmnt", "dream runner session (B18 M1)")] + entries)


def write_session(s, path):
    text = fr_session.dump_text(s)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(text)
    return text
```

`dream/__init__.py` 建空文件。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add dream/__init__.py dream/session.py tests/test_dream.py
git commit -m "feat(dream): 会话壳——chunk 解析/封帧 CRC/Session 组装（B18 M1 T1）"
```

---

### Task 2: fr-lint（语法+语义层，tools/fr_lint.py）

**Files:**
- Create: `tools/fr_lint.py`
- Test: `tests/test_dream.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_dream.py 追加
def _tiny_stream(asset_rows=("asset font 1 14.000000 00010203",), out_rows=("clear 0 0 0 255",)):
    from dream import session as ds
    frames = ds.parse_chunk("frame 0\nst 0 \"t\" num 1.000000\n" + "\n".join(out_rows))
    entries = ds.seal_frames(frames, kit_rows=[fc.parse_line(a) for a in asset_rows], dt=0.066667)
    return fr_session.dump_text(ds.build_session(entries, seed=1))


def test_lint_clean_on_valid_stream():
    from tools import fr_lint
    assert fr_lint.lint_text(_tiny_stream()) == []


def test_lint_phantom_asset():
    from tools import fr_lint
    # draw 引用不存在的资产 7（kit 只有 font 1）
    text = _tiny_stream(out_rows=("clear 0 0 0 255",
        "draw 7 0 10.000000 20.000000 0.000000 1.000000 1.000000 0.000000 0.000000 255 255 255 255"))
    diags = fr_lint.lint_text(text)
    assert any(d.startswith("L001") and "7" in d for d in diags)


def test_lint_bad_d_crc():
    from tools import fr_lint
    text = _tiny_stream()
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.startswith("d_crc "):
            lines[i] = "d_crc 123456789"
            break
    diags = fr_lint.lint_text("\n".join(lines))
    assert any(d.startswith("L002") for d in diags)


def test_lint_frame_order():
    from tools import fr_lint
    # dt 不在帧首（手工拼一条坏流：帧首塞 clear 再 dt）
    from dream import session as ds
    frames = ds.parse_chunk("frame 0\nclear 0 0 0 255")
    entries = ds.seal_frames(frames, kit_rows=[], dt=0.066667)
    block = entries[0][1]
    block[0], block[1] = block[1], block[0]  # 破坏行序
    text = fr_session.dump_text(ds.build_session(entries, seed=1))
    diags = fr_lint.lint_text(text)
    assert any(d.startswith("L004") for d in diags)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v -k lint`
Expected: FAIL（`No module named 'tools.fr_lint'`）

- [ ] **Step 3: 最小实现**

```python
# tools/fr_lint.py
"""fr-lint —— 流诊断器（B18 M1：语法层+语义层；锚定回放层=fr-render d_crc 终审）。

语法层 = fr_session.parse_text 的 SessionError（自带行号）——不重复造轮子。
语义层（附录 5.3-6 幻觉防线；对任意流可用，dream 生成流是第一客户）：
  L001 引用完整性：draw.tex / print.font 引用的资产号必须先由 asset 行声明；
  L002 d_crc 对账：end 段 d_crc 须等于重算 CRC32(当帧 out 行 "\\n" 连接)（全流通用口径）；
  L003 s_crc 对账：dream 口径（st 行 CRC）——仅 dream=True 时启用（录制流 s_crc=堆口径，不可比）；
  L004 帧行序：dt 须为帧首行、end 双行须为帧末两行、asset 行仅允许出现在首帧。
诊断形态：编译器式 "Lxxx 帧F 行N: 消息"（供打回 LLM 自修复）。
"""
import sys
import zlib

from tools import fr_session
from tools import fr_codec_gen as _rc


def _crc(rows):
    return zlib.crc32("\n".join(rows).encode("utf-8")) & 0xFFFFFFFF


def lint_text(text, dream=False):
    """canonical .fr 文本 → 诊断字符串列表（空 = 全绿）。"""
    try:
        s = fr_session.parse_text(text)
    except fr_session.SessionError as e:
        return ["L000 解析: %s" % e]
    lines = text.split("\n")
    line_no_of = {}  # 帧 idx → (首行号, dt/end 行号)
    diags, seen_assets, fidx, ln = set(), set(), -1, 1
    frame_lines = {}
    for l in lines[1:-1]:
        if l.startswith("frame "):
            fidx += 1
            frame_lines[fidx] = []
        elif fidx >= 0:
            frame_lines[fidx].append(l)
    for fidx, rows_txt in frame_lines.items():
        declared = set()
        out_txt = []
        for pos, l in enumerate(rows_txt):
            if l.startswith("asset "):
                if fidx != 0:
                    diags.add("L004 帧%d: asset 行仅允许首帧" % fidx)
                t = l.split(" ")
                declared.add(int(t[2]))
            elif l.startswith(("draw ", "print ")):
                t = l.split(" ")
                ref = int(t[1])
                if ref not in declared and ref not in seen_assets:
                    diags.add("L001 帧%d: 引用未声明资产 %d" % (fidx, ref))
            if not l.startswith(("dt ", "asset ", "ev ", "call ", "timer ", "st ", "err ", "s_crc ", "d_crc ")):
                out_txt.append(l)
        seen_assets |= declared
        # L004 行序：dt 首、end 双行殿后
        if not rows_txt or not rows_txt[0].startswith("dt "):
            diags.add("L004 帧%d: dt 须为帧首行" % fidx)
        if len(rows_txt) < 2 or not rows_txt[-1].startswith("d_crc ") or not rows_txt[-2].startswith("s_crc "):
            diags.add("L004 帧%d: end 双行须殿后" % fidx)
        # L002/L003 对账
        end = [l for l in rows_txt if l.startswith("d_crc ")]
        if end:
            got = int(end[0].split(" ")[1])
            if got != _crc(out_txt):
                diags.add("L002 帧%d: d_crc %d ≠ 重算 %d" % (fidx, got, _crc(out_txt)))
        if dream:
            sc = [l for l in rows_txt if l.startswith("s_crc ")]
            st_txt = [l for l in rows_txt if l.startswith("st ")]
            if sc and int(sc[0].split(" ")[1]) != _crc(st_txt):
                diags.add("L003 帧%d: s_crc 与 st 行不符（dream 口径）" % fidx)
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
```

（`import os` 置于文件头部与 json/zlib 并列——上面代码块中 main 引用前须已导入。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add tools/fr_lint.py tests/test_dream.py
git commit -m "feat(lint): fr-lint 语法+语义层（L001 引用/L002 d_crc/L004 行序；dream 口径 L003）"
```

---

### Task 3: fr-assets（流 → kit 抽取，tools/fr_assets.py）

**Files:**
- Create: `tools/fr_assets.py`
- Test: `tests/test_dream.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_dream.py 追加
def test_fr_assets_golden(tmp_path):
    from tools import fr_assets
    kit = tmp_path / "kit"
    n = fr_assets.extract("tests/golden/l0_session.fr", str(kit))
    assert n == 2  # golden: image 1 + font 2
    import json
    man = json.loads((kit / "assets.json").read_text(encoding="utf-8"))
    assert [a["id"] for a in man["assets"]] == [1, 2]
    assert man["assets"][0]["kind"] == "image" and man["assets"][0]["w"] == 32
    rows = (kit / "assets.txt").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("asset image 1 ") and rows[1].startswith("asset font 2 ")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v -k assets`
Expected: FAIL（`No module named 'tools.fr_assets'`）

- [ ] **Step 3: 最小实现**

```python
# tools/fr_assets.py
"""fr-assets —— 流 → 资产 kit 抽取（B18 M1 最小面；工具族地图挂名兑现）。

用法：python tools/fr_assets.py <in.fr|in.frb> -o <kit_dir>
产出：assets.json（目录单——id/kind/desc/尺寸，喂 LLM 的引用面，LLM 永不碰字节）
      assets.txt（canonical asset 行，renumber 后——runner 首帧原样回放）
renumber：按出现序重编 1..M（原流资产号只在本流内稳定，跨流须重编）。
image 行形 `asset image <id> <w> <h> <hex>`；font 行形 `asset font <id> <size> <hex>`（B12 池化引用形不在本面——kit 只收独立字节资产）。
"""
import json
import os
import sys

from tools import fr_session


def _read_text(path):
    with open(path, "rb") as f:
        head = f.read(4)
    if head == b"FRB1":
        with open(path, "rb") as f:
            return fr_session.dump_text(fr_session.parse_binary(f.read()))
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract(path, kit_dir):
    text = _read_text(path)
    os.makedirs(kit_dir, exist_ok=True)
    assets, new_id = [], 0
    for line in text.split("\n"):
        if not line.startswith("asset "):
            continue
        t = line.split(" ")
        kind, old_id = t[1], int(t[2])
        if kind == "image":
            desc = dict(kind="image", w=int(t[3]), h=int(t[4]))
        elif kind == "font":
            desc = dict(kind="font", size=t[3])
        else:  # canvas/quad 纯数据无字节——照收不描述
            desc = dict(kind=kind)
        new_id += 1
        t[2] = str(new_id)
        assets.append((new_id, " ".join(t), desc, old_id))
    with open(os.path.join(kit_dir, "assets.txt"), "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(a[1] for a in assets) + ("\n" if assets else ""))
    man = {"assets": [dict(id=i, desc="kind=%s src#%d" % (d["kind"], o), **d)
                      for i, _l, d, o in assets]}
    with open(os.path.join(kit_dir, "assets.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    return len(assets)


def main(argv):
    if len(argv) != 4 or argv[1] in ("-h", "--help") or argv[2] != "-o":
        print("用法: python tools/fr_assets.py <in.fr|in.frb> -o <kit_dir>", file=sys.stderr)
        return 2
    n = extract(argv[1], argv[3])
    print("fr-assets: %d 个资产 → %s（assets.json 目录单 + assets.txt 行）" % (n, argv[3]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: 跑测试确认通过 + golden 实跑**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v && python tools/fr_assets.py tests/golden/l0_session.fr -o /tmp/kit_probe`
Expected: 8 passed；stdout `fr-assets: 2 个资产 → …`

- [ ] **Step 5: Commit**

```bash
git add tools/fr_assets.py tests/test_dream.py
git commit -m "feat(assets): fr-assets 最小面——流抽取/renumber/目录单（B18 M1 T3）"
```

---

### Task 4: 词汇表 + 提示词工程（dream/vocab.txt + dream/prompt.py）

**Files:**
- Create: `dream/vocab.txt`（静态词汇速查——prompt 静态件，人可直接审）
- Create: `dream/prompt.py`
- Test: `tests/test_dream.py`（追加）

- [ ] **Step 1: 落词汇表文件（无测试——纯文本资产，测试在 prompt 组装处覆盖）**

```text
# dream/vocab.txt —— LLM 书写 FR 的词汇速查（canonical :full 档；真源 tables/cmd.tbl）
会话几何与资产目录单由系统消息给出；你只写 frame 块。规则：
1. 每块以 `frame N` 开头（N 从上一帧 +1 连续递增）；
2. 块内先 st 行（世界账本，可省）后绘制行；只写内容行——
   dt/asset/ev/s_crc/d_crc 由 runner 书写，出现即拒绝；
3. f32 一律 %.6f 六位小数定长（如 12.500000）；rgba = 四个 0-255 整数；
4. 资产只引用目录单里的 id，不得发明不存在的号（fr-lint L001 拦截）。

st 行：`st 0 "<键>" num <f32>` 或 `str "<文本>"` —— 例：st 0 "hero.x" num 128.000000

绘制行（mode: 0=填充 1=描边；arctype: 0=pie 1=open 2=closed）：
  clear <r> <g> <b> <a>
  draw <tex资产号> 0 <x> <y> <rot> <sx> <sy> <ox> <oy> <r> <g> <b> <a>
  print <font资产号> "<文本>" <x> <y> <rot> <sx> <sy> <r> <g> <b> <a>
  rect <mode> <x> <y> <w> <h> <rx> <ry> <width> <r> <g> <b> <a>
  line <x1> <y1> <x2> <y2> [...] <width> <r> <g> <b> <a>
  poly <mode> <x1> <y1> <x2> <y2> [...] <r> <g> <b> <a>
  circle <mode> <x> <y> <r> <seg> <r> <g> <b> <a>
  arc <mode> <arctype> <x> <y> <r> <a1> <a2> <seg> <r> <g> <b> <a>
  points <x1> <y1> <x2> <y2> [...] <size> <r> <g> <b> <a>
  rt <目标canvas资产号|0=屏幕>
  scissor <x> <y> <w> <h>

示例帧（几何 640x480）：
frame 7
st 0 "hero.x" num 132.000000
clear 0 0 0 255
draw 1 0 132.000000 240.000000 0.000000 1.000000 1.000000 0.000000 0.000000 255 255 255 255
print 2 "HP 87" 12.000000 12.000000 0.000000 1.000000 1.000000 255 255 0 255
```

- [ ] **Step 2: 写失败测试**

```python
# tests/test_dream.py 追加
def test_prompt_assembly_and_window():
    from dream import prompt as dp
    vocab = dp.load_vocab()
    assert "frame N" in vocab and "clear" in vocab
    catalog = dp.load_catalog("dream")  # 无 kit 时内建最小目录单（1 font）
    p = dp.build_prompt(vocab, catalog, window_text="frame 0\nclear 0 0 0 255",
                        directive="英雄从左走到右", next_frame=1)
    for part in (vocab, catalog, "frame 0", "英雄从左走到右", "frame 1"):
        assert part in p
    # 滑窗：取流文本最后 k 个 frame 块
    stream = "frame 0\nclear 0 0 0 255\nframe 1\nclear 0 0 0 255\nframe 2\nclear 0 0 0 255\n"
    assert dp.sliding_window(stream, 2) == "frame 1\nclear 0 0 0 255\nframe 2\nclear 0 0 0 255\n"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v -k prompt`
Expected: FAIL（`No module named 'dream.prompt'`）

- [ ] **Step 4: 最小实现**

```python
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
    """kit 目录单 → 目录单文本；kit 缺 assets.json 时给最小内建目录单（font=size 形）。"""
    p = os.path.join(kit_dir, "assets.json")
    if not os.path.isfile(p):
        return "资产目录单（内建）：1 = font 字号 14.000000（print 用）"
    with open(p, encoding="utf-8") as f:
        man = json.load(f)
    rows = ["资产目录单（引用只允许下列 id）："]
    for a in man["assets"]:
        d = a.get("desc", "")
        if a["kind"] == "image":
            rows.append("%d = image %dx%d %s" % (a["id"], a.get("w", 0), a.get("h", 0), d))
        elif a["kind"] == "font":
            rows.append("%d = font 字号 %s %s" % (a["id"], a.get("size", "?"), d))
        else:
            rows.append("%d = %s %s" % (a["id"], a["kind"], d))
    return "\n".join(rows)


def sliding_window(stream_text, k):
    """canonical 流文本 → 最后 k 个 frame 块原文（含 frame 头行）。"""
    lines = stream_text.split("\n")
    starts = [i for i, l in enumerate(lines) if l.startswith("frame ")]
    if not starts:
        return ""
    starts = starts[-k:]
    end = starts[-1]
    while end < len(lines) and lines[end] != "":
        end += 1
    return "\n".join(lines[starts[0]:end]) + "\n"


def build_prompt(vocab, catalog, window_text, directive, next_frame):
    return ("你在为帧流 IR（FR）直接书写一帧帧的绘制决定。规则与词汇表：\n%s\n\n"
            "%s\n\n以下是最近帧（含你的世界账本 st 行，保持数值连续）：\n%s\n"
            "导演指令：%s\n请从 frame %d 继续，输出后续帧块（每块 frame 头 + st + 绘制行）。\n"
            % (vocab, catalog, window_text, directive, next_frame))
```

- [ ] **Step 5: 跑测试确认通过并提交**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v`
Expected: 9 passed

```bash
git add dream/vocab.txt dream/prompt.py tests/test_dream.py
git commit -m "feat(dream): 词汇速查 + 提示词工程（滑窗组装/目录单/导演指令）"
```

---

### Task 5: driver（FromFile 确定性 + LLM env 适配）

**Files:**
- Create: `dream/driver.py`
- Test: `tests/test_dream.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_dream.py 追加
def test_driver_from_file(tmp_path):
    from dream import driver
    f = tmp_path / "chunks.txt"
    f.write_text("frame 0\nclear 0 0 0 255\n### CHUNK\nframe 1\nclear 0 0 0 255\n",
                 encoding="utf-8")
    d = driver.FromFileDriver(str(f))
    assert "frame 0" in d.generate("prompt-ignored")
    assert "frame 1" in d.generate("prompt-ignored")
    with pytest.raises(RuntimeError):
        d.generate("exhausted")


def test_driver_llm_skips_without_env():
    from dream import driver
    pytest.importorskip("urllib.request")
    import os
    if not os.environ.get("LLM_BASE_URL"):
        d = driver.LlmDriver()
        with pytest.raises(RuntimeError):
            d.generate("x")  # 未配置即明确报错，不静默
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v -k driver`
Expected: FAIL（`No module named 'dream.driver'`）

- [ ] **Step 3: 最小实现**

```python
# dream/driver.py
"""LLM 适配（B18 M1）：FromFile（确定性，CI 零 token）+ LlmDriver（OpenAI 兼容）。

LlmDriver 走标准库 urllib——零第三方依赖；配置全 env：
LLM_BASE_URL（如 https://api.x.com/v1）、LLM_API_KEY、LLM_MODEL。
"""
import json
import os
import urllib.request


class FromFileDriver:
    """按 `### CHUNK` 分隔的文本文件顺序吐 chunk——测试与离线确定性模式。"""

    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            self._chunks = [c for c in f.read().split("### CHUNK") if c.strip()]
        self._i = 0

    def generate(self, prompt):
        if self._i >= len(self._chunks):
            raise RuntimeError("from-file chunk 已耗尽（%d 段）" % len(self._chunks))
        c = self._chunks[self._i].strip() + "\n"
        self._i += 1
        return c


class LlmDriver:
    def __init__(self):
        self.base = os.environ.get("LLM_BASE_URL")
        self.key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "")
        if not (self.base and self.model):
            raise RuntimeError("LLM_BASE_URL / LLM_MODEL 未配置（LLM_API_KEY 可空）")

    def generate(self, prompt):
        req = urllib.request.Request(
            self.base.rstrip("/") + "/chat/completions",
            data=json.dumps({"model": self.model, "temperature": 0,
                             "messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.key})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read().decode())
        return data["choices"][0]["message"]["content"]
```

- [ ] **Step 4: 跑测试确认通过并提交**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v`
Expected: 11 passed

```bash
git add dream/driver.py tests/test_dream.py
git commit -m "feat(dream): driver——FromFile 确定性 + LLM env 适配（stdlib urllib）"
```

---

### Task 6: run.py CLI 端到端（60 帧 → fr-check → round-trip → lint → render）

**Files:**
- Create: `dream/run.py`
- Test: `tests/test_dream.py`（追加端到端）

- [ ] **Step 1: 写失败测试（端到端，CI 安全）**

```python
# tests/test_dream.py 追加
def _gen_chunk_file(path, n_frames):
    """确定性 60 帧剧本：hero.x 每帧 +4，清屏+方块+顶栏；分 6 段 chunk。"""
    parts = []
    for i in range(n_frames):
        x = 40.0 + 4.0 * i
        parts.append("frame %d\nst 0 \"hero.x\" num %.6f\nclear 20 24 36 255\n"
                     "rect 0 %.6f 240.000000 48.000000 48.000000 0.000000 0.000000 1.000000 255 255 255 255\n"
                     "rect 0 0.000000 0.000000 640.000000 24.000000 0.000000 0.000000 1.000000 90 90 120 255\n"
                     % (i, x, x))
    chunks = ["\n".join(parts[j * 10:(j + 1) * 10]) for j in range(6)]
    open(path, "w", newline="\n", encoding="utf-8").write(
        "\n### CHUNK\n".join(chunks) + "\n")


def test_end_to_end_from_file(tmp_path):
    import subprocess
    from tools import fr_lint
    src = tmp_path / "chunks.txt"
    _gen_chunk_file(str(src), 60)
    out = tmp_path / "dream.fr"
    r = subprocess.run(
        ["python", "-m", "dream.run", "--frames", "60", "--out", str(out),
         "--from-file", str(src), "--seed", "1"], capture_output=True, cwd=_ROOT)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    text = out.read_text(encoding="utf-8")
    assert text.count("\nframe ") == 60
    # ① fr-lint 全绿（dream 口径）
    assert fr_lint.lint_text(text, dream=True) == []
    # ② fr-check（含 canonical 幂等 + sha 对账）
    r = subprocess.run(["python", "tools/fr_check.py", str(out), "--strict"],
                       capture_output=True, cwd=_ROOT)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")
    # ③ fr-as/fr-dis round-trip 逐字节相等
    frb = tmp_path / "dream.frb"
    back = tmp_path / "back.fr"
    subprocess.run(["python", "tools/fr_as.py", str(out), "-o", str(frb)],
                   check=True, capture_output=True, cwd=_ROOT)
    subprocess.run(["python", "tools/fr_dis.py", str(frb), "-o", str(back)],
                   check=True, capture_output=True, cwd=_ROOT)
    assert back.read_bytes() == out.read_bytes()
    # ④ render 对账（fork 构建在场时；不在场跳过——CI 与无构建机不红）
    love = os.path.join(_ROOT, "megasource", "build115", "love", "Release", "love.exe")
    if os.path.isfile(love):
        from tools import fr_render
        cp = fr_render.render(str(out), timeout=120)
        assert cp.returncode == 0, cp.stderr.decode("utf-8", "replace")
        d_lines = [l for l in text.split("\n") if l.startswith("d_crc ")]
        want = [int(l.split()[1]) for l in d_lines]
        got = [int(l.split()[2]) for l in cp.stdout.decode().split("\n")
               if l.startswith("D_CRC ")]  # D_CRC <n> <crc> —— crc 是第 3 列
        assert got == want
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v -k end_to_end`
Expected: FAIL（`No module named 'dream.run'`）

- [ ] **Step 3: 最小实现**

```python
# dream/run.py
"""dream runner CLI（B18 M1）。

用法：python -m dream.run --frames 60 --out dream_session.fr --kit <dir>
                       [--from-file <chunks.txt> | --llm]
                       [--dt 0.066667] [--seed 1] [--width 640] [--height 480]
                       [--window-k 8] [--directive "<剧本>"] [--max-retry 2]
"""
import argparse
import sys

from dream import driver as ddrv
from dream import prompt as dprompt
from dream import session as dsession
from tools import fr_assets
from tools import fr_codec_gen as _rc
from tools import fr_lint


def load_kit_rows(kit_dir):
    """kit assets.txt → [(op, fields)]（原样回放进首帧）。"""
    import os
    p = os.path.join(kit_dir, "assets.txt")
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [_rc.parse_line(l) for l in f.read().splitlines() if l.strip()]


def _semantic_guard(text):
    """chunk 级语义闸：对已 seal 的增量流全文跑 lint（dream 口径）。"""
    return fr_lint.lint_text(text, dream=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dream.run")
    ap.add_argument("--frames", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--kit", default="dream")
    ap.add_argument("--from-file")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--dt", type=float, default=1.0 / 15.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--window-k", type=int, default=8)
    ap.add_argument("--directive", default="一个方块从屏幕左侧匀速走到右侧，顶栏显示进度")
    ap.add_argument("--max-retry", type=int, default=2)
    a = ap.parse_args(argv)
    if bool(a.from_file) == a.llm:
        print("dream.run: --from-file 与 --llm 二选一", file=sys.stderr)
        return 2
    drv = ddrv.FromFileDriver(a.from_file) if a.from_file else ddrv.LlmDriver()
    kit_rows = load_kit_rows(a.kit)
    vocab = dprompt.load_vocab()
    catalog = dprompt.load_catalog(a.kit)
    frames, stream_text, retry = [], "", 0
    while len(frames) < a.frames:
        prompt = dprompt.build_prompt(vocab, catalog,
                                      dprompt.sliding_window(stream_text, a.window_k),
                                      a.directive, len(frames))
        try:
            chunk_frames = dsession.parse_chunk(drv.generate(prompt))
            if chunk_frames[0][0] != len(frames):
                raise ValueError("chunk 起始帧号 %d ≠ 期望 %d" % (chunk_frames[0][0], len(frames)))
            frames += chunk_frames
        except (ValueError, RuntimeError) as e:
            retry += 1
            if retry > a.max_retry:
                print("dream.run: 重试上限（%d）：%s" % (a.max_retry, e), file=sys.stderr)
                return 1
            continue
        # 增量 seal → 语义闸 → 通过才计入流文本（窗口/最终输出一致）
        probe = dsession.write_session(
            dsession.build_session(dsession.seal_frames(frames, kit_rows, a.dt), seed=a.seed),
            a.out)
        bad = _semantic_guard(probe)
        if bad:
            frames = frames[:len(frames) - len(chunk_frames)]
            retry += 1
            if retry > a.max_retry:
                print("dream.run: 语义闸重试上限：%s" % "; ".join(bad), file=sys.stderr)
                return 1
            continue
        stream_text = probe
        retry = 0
    frames = frames[:a.frames]
    text = dsession.write_session(
        dsession.build_session(dsession.seal_frames(frames, kit_rows, a.dt),
                               seed=a.seed, width=a.width, height=a.height), a.out)
    diags = fr_lint.lint_text(text, dream=True)
    for d in diags:
        print("lint:", d, file=sys.stderr)
    print("dream.run: %d 帧 → %s（lint %s）" % (len(frames), a.out,
          "全绿" if not diags else "%d 条诊断" % len(diags)))
    return 0 if not diags else 1


if __name__ == "__main__":
    sys.exit(main())
```

（注意：`--from-file` 60 帧剧本分 6 段 chunk，driver 逐段吐；重试路径对 FromFile 会顺序取下一段——测试剧本全合法，不触重试。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py -v`
Expected: 12 passed（fork 构建在场时含 render 对账；不在场该断言段跳过不红）

- [ ] **Step 5: 真实实跑一次（手动，非 CI）**

Run: `cd /d/Lab/AgentLove2d && python -m dream.run --frames 60 --out dream_session.fr --from-file <(python - <<'EOF' ...)` —— 简化为：
`cd /d/Lab/AgentLove2d && python -m pytest tests/test_dream.py::test_end_to_end_from_file -v`
Expected: PASS（即端到端真跑过一次）

- [ ] **Step 6: Commit**

```bash
git add dream/run.py tests/test_dream.py
git commit -m "feat(dream): run CLI——生成循环/帧号连续/语义闸/封帧出流（B18 M1 T6）"
```

---

### Task 7: 验收闭环 + 剑侠 kit + 文档同步

**Files:**
- Create: `dream/kit_jianxia/`（fr-assets 产物，入库）
- Modify: `docs/benchmarks.md`、`docs/design.md`（B18 行状态）、`AGENTS.md`（命令与测试数）

- [ ] **Step 1: 录 newgame 流并抽 kit（≥8 资产）**

```bash
# 游戏目录 = B9/B10 实测用的《剑侠无敌》目录（executor 按当次记录填入；这是本计划唯一的外部输入）
cd /d/Lab/AgentLove2d
FR_CAPTURE=1 FR_OUT=/tmp/newgame_src.fr FR_FRAMES=30 FR_SHA=$(python -c "from tools.fr_gen import tbl;print(tbl.tbl_sha256(tbl.parse(open('tables/cmd.tbl',encoding='utf-8').read())))") \
  megasource/build115/love/Release/love.exe <游戏目录>
python tools/fr_assets.py /tmp/newgame_src.fr -o dream/kit_jianxia
```
Expected: `fr-assets: N 个资产`（N ≥ 8；不足 8 则加大 FR_FRAMES 重录）

- [ ] **Step 2: 剑侠 kit 跑通端到端**

Run: `cd /d/Lab/AgentLove2d && python -m dream.run --frames 60 --out /tmp/dream_jx.fr --kit dream/kit_jianxia --from-file tests 固定剧本六段`（复用 Task 6 的 _gen_chunk_file 产 chunk 文件）+ `python tools/fr_check.py /tmp/dream_jx.fr --strict && python tools/fr_lint.py /tmp/dream_jx.fr --dream`
Expected: rc=0、lint 全绿

- [ ] **Step 3: FR_PLAY 视觉手验（人工，一次性）**

Run: `FR_PLAY=1 python tools/fr_render.py dream_session.fr`
Expected: 窗口播出连贯小动画（方块左→右 + 顶栏），播完停留 1s 退出，rc=0

- [ ] **Step 4: token 账 + benchmarks.md 对照行**

对 dream_session.fr 量：60 帧的 prompt 总字符（滑窗重喂）/4 粗估 token、生成侧 token（from-file 剧本字符/4）、:px 转换后体积（`python tools/fr_prec.py dream_session.fr -o /tmp/d.fr` 按其 CLI 实参）。在 `docs/benchmarks.md` 突破点表追加一行：
`| 2026-10-30 | B18 dream runner M1 | LLM 直出 60 帧 canonical（from-file 剧本实测）| 全流 X KB / 生成 Y tok / :px Z KB |`

- [ ] **Step 5: 文档同步**

- `docs/design.md` §6 追加 B18 行：`| B18 | dream runner M1（LLM 直出 FR）| 60 帧流 fr-check 全绿 + round-trip + fr-render 对账 ✅ …（摘要）|`
- `AGENTS.md`：Setup commands 增 `python -m dream.run …` 一条；测试行 117→117+13（按实际计数）；真源文件表 decisions 行已有 D14 不动
- `docs/plans/2026-10-30-b18-dream-runner-design.md` 头部状态改「已实施（M1）」

- [ ] **Step 6: 全量回归 + Commit**

Run: `cd /d/Lab/AgentLove2d && python -m pytest tests/ -q`
Expected: 全绿（原 117 + 新 dream 组）

```bash
git add dream/kit_jianxia docs/benchmarks.md docs/design.md AGENTS.md docs/plans/2026-10-30-b18-dream-runner-design.md
git commit -m "feat(b18): dream runner M1 验收闭环——剑侠 kit/token 账/文档同步"
```

---

## 自审记录（写完即时过）

1. **Spec 覆盖**：设计 §2 架构=T1/T6；§3 四单元=T1(session)/T4(prompt)/T5(driver)/T3(kit·fr_assets)；§4 契约=T1(parse_chunk 白名单+seal 行序)；§5 提示词工程=T4；§6 lint 三层=T2（锚定回放层=T6 render 对账）；§7 验收线=T6②③+T7（60帧/round-trip/D_CRC/剑侠≥8 资产/token 账）；§8 测试=T6 from-file；§9/§10 不做=M2 不在本计划。**无缺口**。
2. **占位扫描**：唯一外部输入=newgame 游戏目录（T7 Step1 显式标注 executor 填入——运行时参数非设计占位）；无 TBD/TODO。
3. **类型一致**：parse_chunk 返回 `[(帧号, [(op, fields)])]` 与 seal_frames/load_kit_rows 消费一致；`_rc.parse_line/render_line` 与 fr_session.py:109/177 同源；crc32_rows 与 lint _crc 同参。
