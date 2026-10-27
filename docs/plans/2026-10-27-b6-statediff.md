# B6 实施计划：log 段 A 方案——堆 CRC + 镜像 diff（st 物理行/s_crc/表重建）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补全帧五段的 log/end 段——present 时刻 C 侧遍历 LuaJIT 堆：常开产 s_crc（CRC 档），full 级（FR_LOGLEVEL=full）产 st 物理行与表重建事件（diff 档，影子副本 memcmp）。demo 会话从 out-only 升级为含 log/end 段的完整五段形态，B3b 样机口径（obj=0 点路径/序列化 CRC）退役。

**Architecture:** 新 C++ 模块 `fr_statediff.h/.cpp`（fork，include `lj_obj.h` 直读 LuaJIT 内部结构——LuaJIT 源码在 megasource 同仓、love.dll 为 JIT 构建均已实证）。present 钩调用 `fr::statediff_collect(L)`：沿 `G(L)->gc.root` 的 `nextgc` 链遍历全部 GCtab 对象；CRC 档=按确定性序（链序×槽位序）对 TValue 字节累加 CRC；diff 档=镜像 map（`Table* → 槽位副本`）memcmp 出脏槽 → st 行/表重建行。登记表（对象 id↔路径、epoch、首末帧）首批以最简形态随流行输出（id 分配=首次遍历序，路径=B3b walker 同款点路径从根可达推导——**从简：demo 阶段登记表仅 id+kind+几何，路径推导留 B6+**，fr-dis 消费端按 id 显示）。st 行接入 demo tee 组装与 s_crc/d_crc 进 end 段。

**Tech Stack:** fork C++（MSVC；`lj_obj.h` 是 LuaJIT 内部头——include 路径挂 LuaJIT/src，结构体只读访问不修改 VM 状态）。

**依据：** design.md §6 B6 行；docs/love2d-gap.md §四（A 方案主力/表重建事件/登记表 epoch/物理记录+逻辑解码分层）；fr-spec §4（log 段三档/end 段 s_crc d_crc——封版，本批兑现而非修改）；本轮拍板（2026-10-27：CRC 档必做常开、diff 档 full 级、数组下标+hash key、跨帧标识对象 id）。

**关键口径（拍板定案）：**
- **CRC 确定性序**：gc.root 链的对象序在无 GC 紧缩下稳定；槽位序=数组部后 hash 部（Node 数组线性）。**同输入同堆序 → 同 CRC**（demo 确定性链路已保证输入确定）。GC 紧缩改链序 → CRC 变——如实接受（重演对比两侧同为紧缩后序，仍然一致；跨紧缩的流间 CRC 对比不承诺，登记为已知边界）
- **st 行物理形态**：`st <objid> <slotkey> <variant>`；slotkey=数组部 `[i]`（i 为 0 基下标）、hash 部 `"keystr"`（Node.key 为字符串时；非字符串 key 如数字/布尔——读出 canonical 形态 `"num:3.000000"` 前缀记法，**首任务实测定形**）
- **表重建**：asize 或 hmask 变化 → `st <objid> *rehash* <asize> <hmask>`（值域 u32×2 的 variant 形态）+ 全槽位重发（不逐槽比）
- **新表/消失表**：链上首次出现=全槽重发；镜像里有而链上没有=GC 已回收，释放镜像（**不发行**——消失不是状态变更，s_crc 天然反映）；对象 id 复用 epoch：id 分配仅增不复用
- **值域**：TValue 五类可序列化（nil/true/false/number/string——**lightuserdata/udata/function/table 引用按 err 行记**（`err st-unsupported <objid> <slotkey> <tag>`），不中断遍历；table 引用值=子对象已在链上，其槽位值记 `ref <childid>`？——**从简：首版 table 引用槽按 err unsupported 记**，ref 形态留 B6+）
- **s_crc 与 st 同遍历**：CRC 档（full 之外）遍历但不产行只产 CRC；full 档同一次遍历既产行又产 CRC（封版 §4"同一次遍历的两种输出"）
- **d_crc**：保持 B4-3 的 Canvas 回读 CRC（end 段的另一行）——tee 会话写入时 demo 侧若无 Canvas（无头）则 d_crc 省略？**不省**——封版 end 段双行；无头时 d_crc=0 哨兵+注释行说明（首任务实测定形）

**风险与红线：**
- **只读红线**：statediff 绝不修改任何 VM 结构（marked 位都不碰——遍历不触发 GC、不置标记；纯读字节）
- GC 遍历期间对象被移动（增量 GC 步）：**present 时刻调用点本身在 Lua 代码边界外**（C 钩内无 Lua 执行），GC 不会在该窗口推进——安全前提成立，登记
- 性能：万槽级 <1ms（内存带宽）；profile 数据随批产出（B 方案触发判据）

---

### Task 1: fr_statediff 核心（CRC 档）+ lj_obj 集成（TDD）

**Files:** fork 新 `src/modules/graphics/fr/fr_statediff.h/.cpp`、改 `CMakeLists.txt`（注册+LuaJIT include 路径——查 love 目标已有的 luajit 头包含链，复用之）、`fr_capture.cpp`（present 钩调用 + `_frStateCRC` Lua 出口）、`demo/main.lua`（tee 组装 end 段 s_crc 行）

- [ ] 失败测试（tests/test_capture.py 追加 test_state_crc）：
  - 跑 demo（事件注入）tee → 会话含 `s_crc <n> <crc32>` 行（每帧 end 段）；帧 3 的 s_crc ≠ 帧 0 的（状态在变：tick/hp/clicks）
  - 同参数双跑 → 全部 s_crc 逐帧一致（确定性）
  - --sim 重演该流 → 重演侧收集的 s_crc 与录制逐帧一致（**内核状态重演全对——用途 3 兑现**；sim 模式需同样调 statediff——demo 侧 sim 循环补 s_crc 行进 SIM 输出或比对集）
- [ ] 实现：遍历（GCtab 过滤 `gct == ~LJ_TTAB`）、CRC 序、Lua 出口、demo end 段行
- [ ] 构建验证（ZERO_CHECK；lj_obj.h include 冲突处理——LuaJIT 头需 `LUAJIT_OS/LJ_ARCH` 等宏环境，复用 love 构建 LuaJIT 时的定义链）→ 绿灯（88+3=91）→ fork 提交 `feat(fr): 堆 CRC 档——present 遍历 s_crc（确定性序）`

### Task 2: diff 档（影子镜像 + st 物理行 + 表重建）（TDD）

**Files:** fork `fr_statediff.cpp` 扩展、`demo/main.lua`（FR_LOGLEVEL=full 时 log 段行进 tee 组装；帧序 dt→asset→ev→**st 行**→out→s_crc/d_crc）

- [ ] 失败测试（追加 test_state_diff_rows）：
  - FR_LOGLEVEL=full 跑注入 demo tee → 帧 1 含 `st <id> "[i]"` 或 `st <id> "keystr"` 形态行（clicks 数组部出现新槽 `[0]`；hero.hp 等 hash 部变更——具体行随 demo 状态实况断言）；表重建行在 demo 触发不了（无 rehash 场景）——**测试构造**：kernel 增加 clicks 上限触发的表操作？不——首版以实况断言为准，rehash 用例登记 B6+（诚实边界）
  - 双跑确定性；--sim 重演 st 行逐帧一致（SIM 比对集扩含 st）
- [ ] 实现：镜像 map、memcmp、脏槽→行、asize/hmask 检出、值域序列化（五类+err unsupported）、新表全发/回收释放
- [ ] 绿灯（91+2=93）→ fork 提交 `feat(fr): 堆 diff 档——影子镜像 st 物理行/表重建（full 级）`

### Task 3: 收尾——demo 五段形态 + 文档 + 终审

- [ ] demo 会话终态核对：无注入+full → 五段齐全（dt/asset/ev/st/out/s_crc+d_crc）；fr_check 过；fr-as/dis 双向；golden 更新（**l0_session golden 不动**——那是 L0 样机；fork demo 若有 golden 则更新，没有则建 tests/golden/fork_session.fr）
- [ ] cmd.tbl：st 行 notes 更新（物理形态已实现，样机口径注记转正）；s_crc/d_crc notes 同步
- [ ] design.md §6 B6 行 ✅；gap §四落地记录；AGENTS（FR_LOGLEVEL 用法/测试计数）；fr-spec §13 v1.2.4（log 段物理形态定稿注记——不改 §4 封版语义，落"实现形态登记"）
- [ ] 全量 + 提交 → 终审（验收线：五段齐全会话 fr-check 过；s_crc 重演一致；st 行确定性+重演一致；已知边界登记）

---

## Self-Review 记录

- **验收覆盖**：design B6 行"s_crc 跨运行稳定；st 行噪声实测可控（rehash→表重建）"——Task 1（s_crc 双跑+重演）、Task 2（st 行确定性+重演）；rehash 场景 demo 构造不出，如实登记 B6+（不造假用例）。
- **拍板决策已内化**：CRC 常开/diff full/数组下标+hash key/对象 id/epoch 不复用——全部落入口径节；B 方案维持"A profiling 超预算才启动"。
- **风险**：①lj_obj.h 的 include 宏环境（LuaJIT 构建定义链）——Task 1 首个构建探针即验，失败则退"最小结构副本"路线（把 lj_obj.h 里我们用的三个结构定义拷进 fr_statediff.cpp 并静态断言 sizeof 对齐——运行时用 love.dll 实测验证，如实登记）；②非字符串 hash key 的 canonical 形态——首任务实测定形；③d_crc 无头哨兵——首任务定形。
- **不动**：fr-spec §4 封版语义（本批是兑现）；L0 样机（golden 保留为 B3b 历史）；sim/offline 已有行为。
