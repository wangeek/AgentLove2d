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

- T1 LÖVE 侧：`_frOfflineAppend`/`_frOfflineFrame` 两个 Lua 入口（§9；C++ ~110 行）。
- T2 Python 侧：dream/loop.py——子进程管理 + 协议 + 生成循环复用
  （~150 行；--ev 逻辑从 run.py 抽取共用）。
- T3 联调判据：脚本化会话（预排 ev 序列）→ 全链 lint/check → 成片目检
  → 回放重演逐帧一致。跑通后 benchmarks 记一行。

## 7. 不做栏

- 实时逐帧对话（LLM 延迟秒级，帧级同步不现实——解耦已覆盖）；
- LLM 书写 ev 行（ev 恒为 runner 职责，词汇表已明示）；
- 多观众并发事件合并（v1 单事件队列顺序处理）；
- 触摸/摇杆 type 扩充（词汇表已留参数序位，按需加行）。

## 9. 拓扑修订（定案，取代 §3/§4 的 stdio 设计与 §8 的 C++ SDL 轮询）

> 2026-11-01 用户裁决四原则：① 事件由 Lua 捕获（非 C++ 轮询/脚本注入）；
> ② 日志照旧关注 LLM 对话；③ 末帧反复绘制可接续新 ev、但空闲不增帧
> （控制上下文长度）；④ patch 不侵入游戏框架——Runner 是延伸出的完整程序。
> 洞察：**Runner 本身就是一个微型 LÖVE 游戏目录**（`love.exe dream/runner`），
> 框架零侵入。

```
dream/loop.py（Python）              love.exe dream/runner/（Runner 游戏）
├─ LLM driver/seal/chatlog 复用      ├─ conf.lua：窗口=流几何，标题 dream-runner
├─ 生成初始段 .fr → 起 love 子进程    ├─ love.mousepressed 等（Lua 捕获 ev）
├─ 轮询 .evq → 事件→LLM→追加帧      │    → JSON 行 append 到 .evq（io）
└─ 子进程退出/超时 → 收尾判据        ├─ love.draw 每帧调 _frOfflineAppend(path)
                                     │    （C++ 增量：探测增长→续解析→按 dt 节奏
                                     │     渲染新帧到常驻 canvas→贴屏）
                                     └─ 空闲：无新帧只贴屏（末帧反复绘制，
                                        流不增帧；ev 随时可到）
```

- **通道=两个文件**：.fr（Python→Runner，append-only）、.evq（Runner→Python，
  JSON 行）；无 stdio 协议、无端口。子进程只上报事实，不写流。
- **C++ 增量仅两个 Lua 入口**（加法式，~110 行）：
  `love.graphics._frOfflineAppend(path)` → 常驻 OfflineSession+canvas+解析偏移；
  每次 call：文件增长则续解析（只到最后一个 '\n'）、按流内 dt 节奏至多推进
  一帧、canvas 贴屏缩放。`_frOfflineFrame()` → 当前渲染帧号（ev 上报用）。
- **ev 由 Lua 捕获**：love.mousepressed(x,y,button,istouch) →
  `{"ev":...,"args":[x,y,button,istouch],"frame":_frOfflineFrame()}`。
  坐标 1:1（窗口=流几何）。
- **测试自动化**：窗口标题定位 hwnd → ctypes SendMessage(WM_LBUTTONDOWN/UP)
  合成点击（SDL 翻译为 love 事件）；断言 .fr 含 ev 行 + 事件帧后有绘制响应
  （帧内容 diff）+ chatlog 含【事件】回合。
- **生命周期**：关窗/Python 超时即会话终；.fr 保留全部打断事实（回放=复刻）。

