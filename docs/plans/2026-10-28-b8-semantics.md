# B8 语义兼容完备批：捕获面全 API 覆盖（do尽做）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 捕获层语义覆盖从"demo 四件套"扩到 **LÖVE 11.5 graphics 全 API 面**——以真实游戏的调用清单为验收靶，先做尽必要语义，真对象委托仅作此后兜底（用户拍板 2026-10-28：不走捷径）。目标：FR_CAPTURE=1 对任意第三方游戏透明——不开开关行为零变化、开了开关捕获完整不崩溃。

**Architecture:** 三层推进：①**状态类 op 语义捕获**（setColor/setFont/setLineWidth/setCanvas/setScissor/setShader/origin/push/pop/translate/scale——demo 未覆盖的核心面，语义=折进行参数或状态行）；②**绘制类补全**（line/circle/polygon/arc/points 已在 cmd.tbl 有 op——挂捕获钩）；③**查询/对象类**（getWidth/getHeight/getFPS/newShader 等——查询透传真值、Shader 暂登记 id+err 边界）。真对象委托（透明代理方案）**本批不做**——待①②③闭环测试过后按需补。

**Tech Stack:** fork C++（w_* 边界挂钩，模式照 w_clear/w_draw 先例）。

**验收靶（newgame 实测调用清单，docs/plans/2026-10-28-b8-semantics.md 附录）**：setColor×54 rectangle×20 draw×12 setCanvas×7 getWidth×10 setLineWidth×6 setFont×5 print×5 line×5 circle×4 origin×4 newCanvas×4 clear×4 setShader×2 newImage×2 setBackgroundColor×1 polygon×1 newShader×1

**依据：** 用户指示（2026-10-28）；cmd.tbl v1.2（line/poly/circle/arc/points op 已封版）；B4-2 Task 3 登记"demo 恒 0/1"的 TODO 项本批清偿。

**关键设计口径：**
- **状态折进参数**（D2 行自描述准则）：setColor→后续行的 color 参数（demo 模式已实现；检查 demo 的 setircolor 适配 vs 游戏原生 setColor——**捕获钩在 w_setColor 记录"当前色"状态，绘制行的 color 参数从该状态取**——w_draw 里已经是这么读的吗？读现状定）；setFont→print 行的 font 参数来源；setLineWidth→rect/line 行 width 参数
- **状态行 op**（cmd.tbl 无对应 op 的）：setCanvas→`rt` op（已有！目标切换状态行）；setScissor→`scissor` op（已有）；**origin/push/pop/translate/scale**——变换栈结算已在 w_draw 挂钩（getTransform 复合），push/pop/origin 影响的是 Graphics 内部变换栈，**捕获侧不需要记**（结算发生在 draw/print/rect 挂钩时刻——天然正确）；setShader/newShader→**err 行登记 + 真执行不抑制**（Shader 无 IR 表达，v1 语义边界如实记）
- **setBackgroundColor**：真执行（不影响 out 行——clear 已显式记色）
- **查询类**：getWidth/getHeight/getFPS——无副作用，零挂钩（透传天然正确）
- **环境层家族**（2026-10-28 拍板）：`mouse.setCursor`、`window.setTitle/setMode/setFullscreen`、`mouse.setVisible/setGrabbed`——修改 OS 窗口属性不产生帧内容（光标在合成层，d_crc/out 均不含）。**v1 透明放行**（不挂钩不抑制不记录），家族清单入账 cmd.tbl 备注；判据需求出现时升格（独立环境行或 err）
- **崩溃防线**：语义替代返回的代理在**任何**被当作真对象用的路径上不得崩——本批先靠"语义做全"消灭崩溃面；残余崩溃点在闭环测试里抓到再逐个定（真对象委托是后续批的兜底，不是本批手段）

---

### Task 1: 状态类捕获（setColor/setFont/setLineWidth/setBackgroundColor）（TDD）

**Files:** fork `fr_capture.h/.cpp`、`wrap_Graphics.cpp`（w_setColor/w_setFont/w_setLineWidth/w_setBackgroundColor 挂钩）

- [ ] 失败测试：demo kernel 加原生 setColor/print/setFont 调用序列（不带 ir_graphics 适配层直调 love.graphics）→ tee 会话 print/rect 行 color/font 参数反映状态序列
- [ ] 实现：色状态缓存（捕获钩记录当前色，绘制行 emit 时读取）；font 同构；lineWidth 同构
- [ ] Commit `feat(fr): 状态类捕获——setColor/setFont/setLineWidth 状态折参数`

### Task 2: 绘制类补全（line/circle/polygon/arc/points 挂钩）（TDD）

- [ ] cmd.tbl 已有 op（line/poly/circle/arc/points 签名已封版）——w_line/w_circle/w_polygon/w_arc/w_points 挂捕获钩（模式照 w_rectangle：参数解析复用+结算坐标+emit 行+抑制真执行）
- [ ] 失败测试：demo kernel 画五图元 → tee 会话含五行
- [ ] Commit `feat(fr): 绘制类五 op 捕获钩（cmd.tbl 封版签名）`

### Task 3: 目标/裁剪/Shader 边界（setCanvas/setScissor/setShader）（TDD）

- [ ] setCanvas：切真执行（语义替代版仅登记）；`rt` 行 emit；setScissor 同构（`scissor` 行）
- [ ] setShader/newShader：err 行登记 + 真执行（语义边界如实）；getShader 透传
- [ ] 失败测试：demo 切 canvas 画两帧切回 → rt 行序正确
- [ ] Commit `feat(fr): rt/scissor 状态行 + Shader err 边界`

### Task 4: 自身闭环测试 + newgame 冒烟

- [ ] 全 API demo：kernel 直调 love.graphics.* 全清单（验收靶 20 API）跑 FR_CAPTURE=1 → 不崩溃、tee 会话完整、sim 重演 MATCH
- [ ] **newgame 冒烟**（挂起任务的复测点）：FR_CAPTURE=1 --scenario test_world --smoke 90 → rc=0（崩溃消失即语义面覆盖成功；残余问题逐个登记）
- [ ] 文档回写 + 终审

---

## Self-Review 记录

- **顺序依据**：用户拍板"语义做尽→闭环→兜底"——Task 1-3 语义，Task 4 闭环+冒烟；真对象委托不在本批。
- **验收线**：①demo 全 API 捕获不崩+会话完整+sim MATCH；②newgame 冒烟 rc=0。
- **风险**：newgame 残余崩溃点（API 面外——元表/Canvas 方法）在 Task 4 抓到则逐个登记定归属（可能引出真对象委托批）。
