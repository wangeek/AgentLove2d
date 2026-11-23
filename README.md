# FR 帧流 IR（AgentLove2d）

把"游戏跑了一趟"变成一个**可传递、可复查、可计算**的物——不是像素录像，是带状态、带输入、带校验和的**确定性执行历史**。载体：魔改 LÖVE 11.5（fork），Lua 游戏内核产出 FR 流，引擎内 C 层捕获与回放。

## 这是什么（一分钟）

```
游戏（任意 LÖVE 游戏，零改动）
   │  FR_CAPTURE=1 FR_OUT=game.fr
   ▼
FR 流（.fr 文本 / .frb 二进制，帧五段：head/in/log/out/end）
   │  python tools/fr_render.py game.fr        ← 脱离原程序回放（判据）
   │  FR_PLAY=1 python tools/fr_render.py ...  ← 视觉播放（可看可关）
   ▼
画面 + 逐帧 D_CRC/像素锚（符号判据，不是人眼）
```

同一份流：LLM 直接读文本验证逻辑、diff 出回归点、离线重渲任意视觉风格。**X11 送画面的命令，视频送画面的像素，FR 送世界的执行历史。**

## MVP 已实证（v0.1.0，2026-10-29）

- **第三方游戏闭环**：newgame《剑侠无敌》零改动录制（240 帧 rc=0）→ 脱离原程序回放/播放 rc=0，画面与原版逐像素一致（--auto-shot 对拍）
- **格式封版**：v1.2.7（.fr/.frb round-trip 逐字节相等；font 字节池化引用形态）
- **性能基准**（newgame 30 帧）：录制 0.09 s/帧（状态根注入）；流 23.5MB 文本 / 11.2MB 二进制；串流档位 15fps≈12Mbps（详见 docs/benchmarks.md）
- **健壮性**：OTF/TTC/垃圾字节字体三态捕获全通；NaN/Inf 参数防线；101 项回归全绿

## 快速开始

```bash
# 录制（SHA 可缺省；表指纹对账时才必需）
FR_CAPTURE=1 FR_OUT=/tmp/game.fr FR_SEED=1 \
  megasource/build115/love/Release/love.exe <任意 LÖVE 游戏目录>

# 回放（判据：D_CRC 序列）/ 播放（视觉，窗口可关）
python tools/fr_render.py /tmp/game.fr
FR_PLAY=1 python tools/fr_render.py /tmp/game.fr

# 转二进制 / 反汇编 / 结构统计
python tools/fr_as.py /tmp/game.fr -o /tmp/game.frb
python tools/fr_dis.py /tmp/game.frb | head
python tools/fr_dump.py /tmp/game.frb --stats
```

## 实战验证（第三方项目实测，2026-11）

MemoryRemake（LÖVE 重制工程）把 FR 流当主验证手段跑了整轮开发，数据与教训见
**[docs/fr-agent-practice-report.md](docs/fr-agent-practice-report.md)**。要点：

- **规模**：23 份判据 / 39 项冒烟 / 72 秒跑完（并行 4 路）；落盘 75 条流
- **判据不吃时间**：92% 的时间是进程启动与封口等待，真正跑游戏 < 10 秒——杠杆在录制路径，不在写更细的判据
- **五步闭环**：双录 → `fr_diff -1`（确定性）→ 扰动必帧 0 分叉 → 正例 rc=0 → 负例必 FAIL
- **体积三档**：全量 10.2MB / 精简 93KB（1.4%，判据链路默认）/ `.frb` 5.0MB（留存）
- **六个录制坑**：普通游戏无头不推帧、不 terminate 必超时 180s、窗口输入污染、存档串味、
  env 传中文崩 UTF-8、GUI 子系统 stdout 无处写
- **最贵一课**：一条手工调试流长到 20.4GB（36.7 万帧、2.2GB 单行混进 NUL），
  之后**整条流对文本工具静默失效**——录制必须带帧上限，工具应当能识别"不可判定流"

## 文档地图

| 想了解 | 去哪 |
|---|---|
| 项目动机与 Agent 工作流 | docs/fr-rationale.md |
| **agent 怎么用 FR 做验证（实践报告）** | **docs/fr-agent-practice-report.md** |
| 系统全貌 / 一帧的一生 / 实施路线 | docs/design.md（总纲入口） |
| 流格式规格（v1.2.7 封版） | docs/fr-spec.md + tables/cmd.tbl（命令单一真源） |
| 架构决策 D1–D13 | docs/decisions.md |
| 性能基准线与优化路径 | docs/benchmarks.md |
| 魔改设计与取证 | docs/love2d-gap.md |
| 魔改引擎源码（LÖVE 11.5 的 fork，`fr-capture` 分支，含构建说明） | [github.com/wangeek/love-fr](https://github.com/wangeek/love-fr) |

## 测试

```bash
pytest tests/   # 101 项：格式/编解码/round-trip/捕获/回放/对拍/闭环
```
