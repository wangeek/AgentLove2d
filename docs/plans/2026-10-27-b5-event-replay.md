# B5 实施计划：事件捕获 + 注入回放（严格档）——内核重演闭环

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 捕获 in 段事件行（OS 事件全参数，src=0），demo 内核事件驱动化；回放严格档——离线把录制事件注入队列重新驱动内核，再生 out 行与录制逐帧比对一致。B5 验收线：同一 .frb 重放 N 次全一致。

**Architecture:** 捕获侧挂 fork demo run loop 的 poll 快照点（现在丢弃事件，改为逐条记 ev 行——Lua 侧经新增 C 出口 `love.graphics._frCaptureEvent(name, ...)` 或直接 Lua 侧拼行后 `_frPushRow`；实测定形态，倾向 C 出口保持单一格式源）。注入侧 = fr-render 新增 `--sim` 模式：读 .frb/.fr 的 in 行 → `love.event.push(name, unpack(args))`（Lua 侧翻译 variant 回 Lua 值）→ 跑 kernel update/draw → 捕获再生 out 行 → 与录制 out 行逐帧 diff（锚行判据，agent 可直接读）。严格档口径：只注入 src=0 OS 事件；合成事件（src=1）由重演自然再生并与录制对拍（demo 不用合成器，登记边界即可）。

**Tech Stack:** fork C++（如走 C 出口）+ demo Lua + 根仓库测试。

**依据：** design.md §6 B5 行；fr-spec §8（ev 行签名=push 参数序、src 标记、严格档定义）；B4-3 交付的 fr_offline_replay 骨架（--sim 复用其容器解包与帧循环）。

**关键口径：**
- ev 行参数 variant 编码：number→`num %.6f`、string→`str "…"`（esc）、boolean→`bool 0|1`（fr.lua tok_variant 同构——C 出口若做则在 fr_capture.cpp 复用 render 格式源）
- 帧内行序更新：dt → asset(首帧) → **ev 行（in）** → out 行（此前无 in 段；与 L0 会话形态对齐）
- 注入的参数还原：文本行 variant → Lua 值（num→number、str→去引号反转义、bool→boolean）
- 事件驱动 demo：kernel.handlers = { mousepressed = 在点击处画 8x8 白色标记（state.clicks 列表，最多 5 个）；keypressed = banner 切换 "L0"/"KEY" }——**out 行随事件可变**，重演比对才有意义
- 确定性：mousemoved 不进 demo（连续事件难锚）；只用离散事件（click/key）

---

### Task 1: fork 事件捕获 + demo 事件驱动化（TDD）

**Files:** fork `demo/main.lua`（poll 循环记 ev 行 + kernel 分发）、`demo/kernel.lua`（handlers + click 状态 + banner 切换 → draw 反映）、`fr_capture.h/.cpp`（如走 C 出口：`_frCaptureEvent`/`_frPushInRow`）

- [ ] 失败测试（tests/test_capture.py 追加 test_event_capture）：跑 demo 传 `--inject-click 200,100 --inject-key return`（demo 参数：帧 1 注入合成 click、帧 2 注入 key，src=2——**先做注入脚本再捕获**，两件一起；事件注入走 `love.event.push` 队列=下一帧 poll 取出，与 OS 事件同路径）→ tee .fr 断言：帧 1 块含 `ev 0 "mousepressed" 0 5 num 200.000000 num 100.000000 num 1 bool 0 num 1`（src=0——push 进队列后 poll 取出记为 OS 路径；或按实现记 src=2，**测试跟实现定案走，但必须稳定**）+ 帧 1 out 含点击标记 rect 行 + 帧 2 banner 变化反映在 print 行
- [ ] 实现 → 构建验证 → 绿灯（全量 84+1=85）→ fork 提交 `feat(fr): in 段事件捕获 + demo 事件驱动化（注入脚本/点击标记/banner 切换）`

### Task 2: 严格档注入回放（--sim 内核重演，TDD）

**Files:** fork `demo/main.lua`（`--sim <path>` 模式：读流 → 逐帧 push in 事件 → 跑 kernel → 捕获再生 out → stdout 逐帧 `SIM <frame> MATCH|MISMATCH n_diff_rows`）、根 `tools/fr_render.py`（`--sim` 透传或独立分支）

- [ ] 失败测试（tests/test_render.py 追加 test_sim_replay）：
  1. live 产含事件 tee .fr（Task 1 链）→ fr_render --sim → 全帧 `SIM n MATCH`（**内核重演与录制逐帧一致——B5 验收线**）
  2. 同流再跑一次 → 结果逐字节一致（N 次重放稳定）
  3. 篡改流（删帧 1 的 ev 行）→ 帧 1 `SIM 1 MISMATCH`（重演对事件的因果依赖自证——删事件则标记不出现）
- [ ] 实现（in 行 variant→Lua 值还原；比对=再生 out 行列表 vs 录制 out 行列表逐行 diff，MISMATCH 时打印首 N 差异行）→ 绿灯（85+3=88）→ 双仓库提交 `feat(fr): 严格档注入回放——内核重演与录制逐帧一致（--sim）`

### Task 3: 收尾回写 + 终审

- [ ] design.md §6 B5 行 ✅（验收线证据：SIM MATCH/N 次稳定/因果篡改检测）；AGENTS 测试计数与 --sim 用法；plan 勾选
- [ ] 全量 + 提交 → 终审（整体评审：B5 验收线三判据 + 已知项）

---

## Self-Review 记录

- **验收覆盖**：design B5 验收线"同一 .frb 重放 N 次全一致；合成事件对拍零失配"——Task 2 三测试直接映射（MATCH/N 稳定/篡改检测）；"合成事件对拍"在 demo 无合成器形态下以注入脚本（src 标记）+ 重演再生对拍覆盖，边界如实登记。
- **风险**：①事件注入的落帧时序（push 后下一帧 poll 取出）——Task 1 测试锚定帧号，若实测差一帧则测试跟实测（帧号语义=poll 取出帧）；②Lua 侧拼行 vs C 出口——实现者按"单一格式源"原则定（C 出口更优但成本高，Lua 侧拼 + fr_check canonical 校验兜底亦可）；③mousepressed 参数序（x y button istouch presses）与 love 11.5 实测对齐。
- **不动**：fr-spec §8（ev 行签名已封版——本批是消费它，不是改它）。
