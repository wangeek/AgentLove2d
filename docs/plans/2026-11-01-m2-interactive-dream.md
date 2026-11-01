# M2 交互式 dream：ev 事件驱动生成（设计定稿）

> 状态：**设计定稿，虚拟验证完毕（2026-11-01 三轮 ev 实验），待实施交互式 Runner**。
> 上游：B18 dream runner M1（docs/plans/2026-10-30-b18-dream-runner-design.md）、
> D14（ev 双生产者）、v1.5 词汇面（CP/SET/INS/DEL + Tier2）。

## 0. 一句话

把 dream 从"批处理生成动画"升级为"事件驱动的可交互世界"：观众输入（点击/按键）
作为 ev 行落流 in 段（打断事实，D14 第二生产者），同时以协议行原文注入提示词，
LLM 续写事件后的世界——打断 = 分叉 + append，会话全程可回放可判据。

## 1. 虚拟验证结论（三轮实验，2026-10-31 ~ 11-01）

同一事件（frame 10 mousepressed 320,300）注入《渔舟》轻剧本，三种注入哲学对照：

| 轮 | vocab 有 ev 语义 | 注入形态 | 响应 | completion |
|---|---|---|---|---|
| 一 | ✗（零教学） | 自然语言+响应处方 | 静态圆 1 个 2 帧消失 | 20,094 |
| 二 | ✓（含创作引导） | "世界对它作何反应，由你创作" | 扩散涟漪（物理正确） | 12,420 |
| 三（**定案**） | ✓（纯协议：参数表+时序+示例） | **ev 行原文** | Qwen：持久涟漪标记（SET 体系，2,025）；DeepSeek：双环扩散生灭（INS/DEL 生命周期，10,711） | |

**定案原则**：教学 = 目的 + 完整参数表 + 示例 + 流内时序（协议事实）；
注入 = ev 行原文（协议行），零创作处方。输入与输出同构（都是 FR 协议行），
响应方式是模型模拟协议后的自由——跨模型方差留在创作面，协议面严格一致。
第三轮 Qwen 自发走编辑行组（SET×136，completion 2,025 = 全实验最低），
DeepSeek 用 INS/DEL 完整管理涟漪对象生命周期——同一词汇表两种合法解。

**产物锚**：dream/dream_ev2.fr|.mp4（Qwen）、dream_ev2_ds.fr|.mp4（DeepSeek）、
两者 .chatlog（对话存档）；ev 行帧内位置实证（in 段 dt 后、out 前）。

## 2. 已落盘的机制件（随验证提交）

- `dream/run.py --ev "<帧号>:<type> <args...>"`（可多次）：脚本化事件。
  覆盖事件帧的 chunk 请求注入【事件】段（协议行原文）；参数按 type 参数序
  全量给出（token 尽力 float→num，失败记 str）。
- `dream/session.py seal_frames(ev_by_frame=)`：ev 行落帧 in 段
  （dt 后、asset/out 前）；lint/check 全过；round-trip 等价。
- `dream/vocab.txt` 第 9 条：ev 行语法/常用 type 参数序（mousepressed/
  mousereleased/keypressed）/流内时序/整数形示例。
- `tools/fr_gen`：:px 档 variant num 值整即整（`num 320` 非 `num 320.000000`；
  真小数仍 %.6f；full 档契约不变；表指纹不变）。

## 3. 交互式 Runner 架构

```
dream/loop.py（Python 父进程）          fork love.exe（子进程）
├─ LLM 调用（driver 复用）              ├─ offline-replay 渲染路径（复用）
├─ 流管理（seal/append）                ├─ Event::pump 捕获（复用 B10 基础）
├─ 提示词组装（协议式 ev 注入）          ├─ 末帧策略：停留等待新帧
└─ 判据记录（.fr + .chatlog）           └─ ev 上报 / 新帧感知 ↓↑ stdio
```

**流为共享介质**：.fr 文件 append-only，父进程追加帧、子进程感知增长继续播。
chat/chatlog、判据面（fr_check --strict / lint）照旧全链有效。

## 4. stdio JSON 行协议

| 方向 | 消息 | 语义 |
|---|---|---|
| 子→父 | `{"ev":"mousepressed","args":[320,300,1,0],"frame":10}` | 用户输入（附当前渲染帧号） |
| 子→父 | `{"status":"starved","frame":35}` | 播到末帧，等待 |
| 父→子 | `{"append":12}` | 流已追加 12 帧 |
| 父→子 | `{"quit":true}` | 会话结束 |

## 5. 时序设计

- **生成与渲染解耦**：渲染 15fps 消费流，LLM 秒级生产。渲染追上末帧 →
  starved 停帧等待；新帧 append 后继续。ev 可在任意时刻到达，绑定当前
  渲染帧号，父进程排队至下一生成 chunk。
- **初始段**：会话以一次性生成 N 帧开场（run.py 现有逻辑），LÖVE 起播后
  进入交互态。
- **ev 双写不变**：流内 ev 行（判据）+ 协议行注入提示词（生成），与虚拟
  实验同构，仅事件来源从 CLI 换成 pump。
- **会话结束**：完整 .fr 保留全部打断事实——回放重演 = 交互历史复刻
  （"存档是一个流"）。

## 6. 实施任务（TDD）

- T1 LÖVE 侧：interactive 回放模式（详细设计见 §8；C++ ~120 行）。
- T2 Python 侧：dream/loop.py——子进程管理 + 协议 + 生成循环复用
  （~150 行；--ev 逻辑从 run.py 抽取共用）。
- T3 联调判据：脚本化会话（预排 ev 序列）→ 全链 lint/check → 成片目检
  → 回放重演逐帧一致。跑通后 benchmarks 记一行。

## 7. 不做栏

- 实时逐帧对话（LLM 延迟秒级，帧级同步不现实——解耦已覆盖）；
- LLM 书写 ev 行（ev 恒为 runner 职责，词汇表已明示）；
- 多观众并发事件合并（v1 单事件队列顺序处理）；
- 触摸/摇杆 type 扩充（词汇表已留参数序位，按需加行）。

## 8. T1 详细设计：LÖVE interactive 回放模式（fr_capture.cpp）

> 侦察基线：`fr_offline_replay`（fr_capture.cpp:2573 起）现为一次 fread 全量
> → offline_parse_text → `for (fi...)` 一遍到底；g_fr_play 分支（:2650）已有
> SDL_PumpEvents/PollEvent 循环（现只认 QUIT）与 dt 节奏贴屏 present。

### 8.1 开关与零侵入

`FR_INTERACTIVE=1`（父进程注入；与 FR_PLAY 同族）。**未设时全部新逻辑不执行，
行为与现状逐字节一致**（判据回归锚）。interactive 隐含 FR_PLAY（视觉播放是
交互前提），复用其贴屏/present/sleep 分支。

### 8.2 流增长感知：增量解析

- `OfflineSession` + `buf` + `size_t parse_tail`（已解析到的偏移）提升到
  循环外持久；文件句柄保持打开。
- 轮询：每次 starved 周期 `fseek(SEEK_END)/ftell` 比对已读偏移，增长则
  fread 增量 append；**只解析到最后一个 '\n'**（父进程写半行安全），残段
  留待下轮；帧号连续校验改用 `s.frames.size()` 基（head 行仅 offset 0 解析）。
- offline_parse_text 拆出 `offline_parse_text_more(buf, from, s)` 续解析入口。

### 8.3 主循环：starved 等待

```
fi = 0
for (;;):
  if fi >= s.frames.size():
      协议出 {"status":"starved","frame":fi}
      循环等待（不 dt sleep）: 轮询文件增长 + stdin + SDL pump（保窗活）
      新帧 → 继续；stdin quit / 关窗 → break
  执行帧 fi（exec rows → 贴屏 present，复用 g_fr_play 分支）→ D_CRC 判据行照出 → fi++
```

### 8.4 stdin 协议（非阻塞）

- Windows：`PeekNamedPipe(GetStdHandle(STD_INPUT_HANDLE))` 探可读字节再读行；
  POSIX：`poll(fd=0)`。`#ifdef _WIN32` 双路（fork 实际只跑 Windows）。
- 入：`{"quit":true}`（干净退出）。`{"append":N}` 保留为显式踢（轮询为主，
  踢为辅——降低轮询间隔压力）。
- **通道复用 stdout，按行前缀分流**：`D_CRC ...` = 判据（现状不变），
  `{...}` = 协议。父进程按行前缀路由。零新通道，chatlog 不受扰。
- JSON 手写拼串（消息形态固定，不引库）。

### 8.5 ev 上报（SDL → 协议行）

- g_fr_play 的 PollEvent 循环扩展：`SDL_MOUSEBUTTONDOWN/UP`、`SDL_KEYDOWN`。
  - mouse：`e.button.x/y`，button 映射 SDL_BUTTON_LEFT→1 等（love 口径），
    istouch 恒 0 → `{"ev":"mousepressed","args":[x,y,1,0],"frame":fi}`
  - key：keysym.sym → 键名（love 键名口径，demo rig B5 的映射若在 C 侧
    则复用；否则小映射表起步：字母/数字/空格/回车/方向键）
- **子进程不写流**——.fr 归父进程；ev 行由父进程 seal 落流（Python 侧
  已验证的双写）。子进程只上报事实。
- 离线回放不走 love run loop，SDL 直 Poll 是正确的层（与 g_fr_play 同构）。

### 8.6 生命周期与验收

- 末帧不再"停 1s 退出"（FR_PLAY 现状）——interactive 进 starved 循环，
  直到 stdin quit 或关窗（关窗=quit 同义，进程组清理走现状路径）。
- 验收（T1 独立，父侧用 stub 脚本）：
  1. 预生成 .fr + FR_INTERACTIVE=1 起：播到末帧 → stdout 出 starved；
  2. stub 往 .fr append 帧（模拟 LLM 产出）→ 窗口续播、D_CRC 连号；
  3. 点击窗口 → stdout 出 ev JSON（坐标=点击处，frame=当前渲染帧）；
  4. stdin `{"quit":true}` → 干净退出 rc=0；
  5. 回归：FR_INTERACTIVE 未设 → 现有判据全量绿（零侵入验证）。
- 回归挂 tests/test_interactive.py（T3 一并），构建走 megasource 增量。
