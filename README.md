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

## 文档地图

| 想了解 | 去哪 |
|---|---|
| 项目动机与 Agent 工作流 | docs/fr-rationale.md |
| 系统全貌 / 一帧的一生 / 实施路线 | docs/design.md（总纲入口） |
| 流格式规格（v1.2.7 封版） | docs/fr-spec.md + tables/cmd.tbl（命令单一真源） |
| 架构决策 D1–D13 | docs/decisions.md |
| 性能基准线与优化路径 | docs/benchmarks.md |
| 魔改设计与取证 | docs/love2d-gap.md |

## 测试

```bash
pytest tests/   # 101 项：格式/编解码/round-trip/捕获/回放/对拍/闭环
```
