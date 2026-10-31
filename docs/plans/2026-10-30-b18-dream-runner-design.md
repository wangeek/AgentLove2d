# B18 dream runner 设计：LLM 直出 FR（M1 离线短片）

> 状态：**已实施（M1，2026-10-30 收批）**。取代 2026-10-29 送审稿（已删除，
> git 史 46de3e3 可考；其三层分工/语义 delta schema/通用结算器由 D14 否决）。裁决链：
> decisions.md D14 + roadmap 附录 §5.2/§5.5 + 本文档。
> **M1 实况**：Qwen3.8 直出 60 帧（剑侠 kit）全链判据过（lint 全绿/check --strict/
> 双跑 D_CRC 逐帧一致/FR_PLAY 播出/剥 st .frb 画面等价）；实测防线两轮（L001 拦幻资产、
> 诊断回喂自修复）。**新增 known boundary**（B18+ 队列）：① fr_dis 对 >10MB 单资产行
> O(L²)（B1 登记边界，fr_as 0.97s 正常）；② C 离线解析器 .frb 路径不认 st/log 行
> （B8 op 集；.fr 文本路径全通）。

## 0. 一句话

dream 是一个新产品：**runner 当会话后勤，LLM 直接书写 canonical FR 行**，芯（流格式/
fr-check/fr-as·fr-dis/fr-render·FR_PLAY）零新机制——LLM 当导演兼结算，runner 只管壳。

## 1. 定位与术语

- dream = 新产物，但**本仓 PoC 起步**（`dream/` 目录，Python，工具族同语）；产品成熟按
  D9 先例（sango 剥离）再议分家。
- 与 roadmap 附录 §5.5 的关系：部件四件「流+结算器+LLM+lint（无新底层机制）」原样成立；
  dream 侧的「结算器」= **LLM 本人**（创作与结算合一，lowering 在其上下文内完成），
  非独立代码部件——送审稿的错=给这个角色发明了第三个实例（通用规则库/展开器）。
- **术语**：§5.5 所称「前缀投影格式」更名为「**提示词工程**」——本质=喂给 LLM 的上下文
  怎么组装，不发明新概念。
- 口径（D14）：流是唯一持久化物，**生成吞吐≠播放帧率**——生成异步攒流、播放实时。

## 2. 架构与数据流

```
导演指令 + 资产目录单 + 词汇速查 + K 帧滑窗 ──提示词工程──▶ LLM
                                                        │ 直出 canonical 行文本
                                                        │ （frame + out 绘制行 + st 自述行）
                                                        ▼
runner：解析校验（lint 语法/语义）→ 逐帧封帧（dt / end·d_crc / s_crc）→ 追加 .fr
                                                        │
                 fr-check ── fr-as/fr-dis round-trip ── fr-render / FR_PLAY 出画面
```

新代码只有两处：runner（会话后勤）与 fr-lint 语义层（回流本仓既有工具族）。

## 3. Runner 职责面（`dream/`，Python）

| 单元 | 干什么 | 依赖 |
|---|---|---|
| `kit`（资产后勤） | 从 newgame（剑侠无敌）已录流抽 asset 行成 kit（字节已近流格式，零解码；renumber 归 kit 号）；产出**目录单**（名字/描述/尺寸/资产号）给 LLM——LLM 只引用不碰字节 | 顺手补 tools/fr_assets.py 最小面（工具族地图挂名未实现） |
| `prompt`（提示词工程） | 组装上下文：静态件（词汇速查+示例帧，参照 golden）+ 资产目录单 + K 帧滑窗（含 st/ev）+ 导演指令；分块续写回喂尾部 | 纯拼装，无新机制 |
| `driver`（LLM 适配） | 两模式：`--from-file`（确定性文本回放，测试零 token）与 provider 调用（llm-call 的 config.yaml 模式） | 本机既有配置 |
| `session`（会话壳） | header（几何/表指纹/loglvl=full）、帧号与 dt 推进（缺省 dt=1/15 即 15fps 档，可调）、封帧补 end | 复用 tools/fr_session.py |

CLI：`python -m dream.run --frames N --out <path> --kit <dir> [--from-file <f> | --llm <cfg>]`

## 4. LLM 输出契约（职责切分）

- **LLM 写内容行**：每帧 `frame N` + out 绘制行（**:px 紧凑档直写**——短名/整数
  坐标/尾部缺省省略；token 经济修正 2026-10-30：%.6f 高精 float 是生成 token 纯
  浪费，:px 静态全量帧无跨帧簿记问题，B15 冲突裁决只约束 paramdelta 层）+
  ~~st 自述行~~（**取消**：px codec 不支持 variant 解析——codec 约束顺势落定语义：
  px 生成档无 st，连续性归滑窗 out 行，D14「状态即流历史」的彻底形态）。
  **frame/dt/end/asset 行由 runner 写**——创作归 LLM，封装归 runner，资产只引用不碰字节。
- 生成形态 = :px 直写；要 :full 观感走 fr_prec 反向展开（值落档内无损）。
- end 段口径：d_crc = 当帧 out 行文本 CRC32（常规口径，fr-render 回放重算对账）；
  s_crc = dream 口径 = 当帧 st 行文本 CRC32（dream 无内核，与录制流「注册状态根子图
  CRC」语义不同——如实注明，回放不依赖它）。
- 帧号由 LLM 写、runner 校验连续性（lint 语义层职责）。

## 5. 提示词工程（唯一真设计点）

- **M1 = append-only messages（2026-10-31 缓存修正，取代原方案 1 滑窗原文）**：
  system（词汇表+目录单+几何，静态永不改）+ 逐 chunk 追加 user（指令+本次
  输出数+诊断回喂）/ assistant（原文）对。裁决依据：前缀缓存（厂商通例）
  要求第 0 字节起逐字节相同——滑窗每次改写中段是反缓存优化；**DeepSeek
  实测命中 69%、墙钟 -71%**（benchmarks 2026-10-31 行）。上下文增长的解法
  是 M2 前情提要（压缩历史），不是改写中段——与 D14「接续=读聊天记录」、
  M2「ev 打断=user 消息追加」自然合流。sliding_window 降为投影/诊断工具。
- **M2 = 前情提要（chat history 压缩）**：历史超阈值时由 LLM 自产叙事态
  提要折叠旧 turn；提要是流外副产物、可从流重放再生（D14），不进流不落台账。
- **方案 3 机械状态投影 = 否决在案**：runner 从 out 行硬编码抽取「世界态」
  是变相发明 schema（哪些参数构成状态=语义选择），展开器还魂，不采用。
- 分块协议：单次补全产若干帧；runner 回喂「你刚写的尾部帧」请求续写，直至 N 帧收满。
- **usage 记账**：driver 透传累加响应 usage（prompt/completion/cache_hit 各列）
  ——计费口径真实数字，进 benchmarks。

## 6. 错误处理（fr-lint 三层，附录 5.3-6 落地）

1. **语法层**：行格式/参数域/定长小数/帧号连续；
2. **语义层**：资产引用完整性（幻资产号拦截）/帧配对/end 配对——M1 新增的 lint 缺口；
3. **锚定回放层**：fr-render 终审——rc=0、帧数出齐、**双跑画布 D_CRC 逐帧一致**
   （注意口径：回放 stdout D_CRC=画布像素 CRC，fr_capture.cpp:2658；流内 d_crc=out
   行文本 CRC，B7a——两个域不可互比）。

不合格 chunk 带**编译器式诊断**（行号+错误码+修复提示）打回 LLM 自修复，重试上限；
超限该 chunk 作废、会话照常闭合（err 忠实记录，不静默吞）。NaN/Inf 防线沿用 rows() 先例。

## 7. 验收线（M1）

- 单流 ≥60 帧（分块生成），**fr-check 全绿 + fr-as/fr-dis round-trip 逐字节相等**
  （dream 流过最高纪律回归）；
- fr-render 离线回放 rc=0、60 帧画布 D_CRC 出齐且双跑逐帧一致（同 B10 稳定口径）；FR_PLAY 播出连贯小动画（人眼 + PIXEL
  采样锚）；
- lint 语义层零漏报（幻资产号/坏帧全被拦）；
- kit 从 newgame 流借 ≥8 资产；
- token 账（每帧均值、canonical vs :px）落 benchmarks.md。

## 8. 测试

- pytest 新增 dream 组：`--from-file` 确定性模式全链（kit→prompt→封帧→check→render），
  CI 零 token 消耗；LLM 实调不进回归。

## 9. 不做栏（防还魂）

方案 3 机械状态投影；语义 delta schema / 通用结算器（D14 已毙）；M2 前情提要只留
接口位不实现；ev 交互循环 = M2；「给 LLM 喂资产字节」（只给目录单）。

## 10. M2+ 演进位

- **ev 交互**：runner 抓用户动作 → ev 行插入当前帧 = 分叉点（既有 ev 行零新语法，
  D14 双生产者的第二种）→ 注入提示词 → LLM 续写；「打断 = 分叉 + append」。
- 前情提要（方案 2）；kit 扩充与按需登记；产品成熟分家评估（D9 先例）。
