# FR 工具链性能基准线（持续优化锚）

> 定位：**性能突破 = 项目应用价值的质变**。本文件记录当前基准线与历史突破点，
> 每次优化落地必须更新对照行——数字是判据，不是装饰。
>
> 基准场景（唯一口径，勿漂）：newgame《剑侠无敌》`--scenario test_world --smoke 30`，
> `FR_CAPTURE=1 FR_OUT=<path> FR_SHA=<指纹> FR_SEED=1`，本机（MSVC Release 构建）。
> 复现命令见文末。

## 当前基准线（2026-10-28，B12+ font 字节池化后）

| 指标 | 值 | 构成 |
|---|---|---|
| 录制吞吐（全堆 s_crc） | **0.14 s/帧**（~7 fps） | 观测范围 6600 表 |
| 录制吞吐（BOOT_SCRIPT 子图） | **0.09 s/帧**（~11 fps） | 观测范围 908 表（7.3× 缩减） |
| 流体积（.fr 文本） | **23.5 MB / 30 帧**（池化前 39.1） | 资产段（一次性）~15.7 + out 行 7.7 |
| **稳态每帧字节（串流口径，B14 实测）** | **world_map：full 229.3 → :px 103.6 KB/帧（-55%）**；**battle：full 13.7 → :px 7.2 KB/帧（-48%）** | 纯 out 行（剔帧 0 首绘）；短名+整数量化+尾部省略全额计入；资产为一次性成本不摊入 |
| **稳态带宽 @30fps（产品档）** | **world_map 56.4 → 25.5 Mbps（:px）**；**battle 3.4 → 1.8 Mbps（:px，已进普通宽带区）** | @15fps 验证档减半：battle 0.9 Mbps / world_map 12.8 Mbps；60fps 档 ×2 |
| asset 构成（一次性） | ~15.7 MB | font **3.1（池化：1 份 TTF 字节 + 5 引用行，前 18.75）** + image 12.62（8 张各异） + canvas ~0 |
| .frb 二进制 | **11.2 MB**（2.09× 压缩） | fr-as 直转 |
| 离线回放（判据） | rc=0，逐帧 D_CRC ×30（.fr/.frb 双形态） | 秒级 |
| 离线播放（FR_PLAY） | rc=0，窗口可交互可关 | 消息泵每帧 |

## 双场景基准锚（B13 起：静态 + 动态并列，任何优化双场景报数）

| 锚 | 场景 | 确定性 | 特征 |
|---|---|---|---|
| 静态锚 | world_map（newgame --scenario test_world） | ✅ 双跑 D_CRC 一致 | tile 全画+UI，same 帧占绝对多数 |
| **动态锚（B13 新增）** | **battle（fr_boot_battle.lua 直切 5v5 + 2s advanceTurn 推进）** | ⚠️ **形态基准**——战斗初始化含 seed 外随机（单位 roll），跨跑 D_CRC 不适用 | rect 8422 行/8 帧+draw 2527（棋盘/单位/血条/拖尾），same 占比 0.86 |

### B13 熵剖面要点（battle 8 帧实测，工具 tools/fr_stats.py）

- **op 层**：rect 75.8% + draw 23.5% = 99.3%——压缩火力全对准两 op
- **参数默认值命中**：rot=0 / ox=0 / oy=0 / color=white / rect width=1 / rx=ry=0 **全部 1.00**（B14 省略表全绿准入）；**sx=sy=1 命中 0.00**（battle 单位有缩放）——静态锚命中 1.0，双场景锚当场纠偏一次拍脑袋设计
- **量化模拟（px+省略）**：996.8KB → 253.7KB（**省 75%**）——B14 收益实证
- **时间层**：same 占比 0.86、均帧差 22.1 行——B15 帧间增量空间实锤

## 已完成的突破点（时间序）

| 日期 | 批 | 前 → 后 | 量级 |
|---|---|---|---|
| 2026-10-28 | B9 present 增量重放 | 全量重放二次方爆炸（11 s/帧）→ **增量 1 s/帧** | ~11× |
| 2026-10-28 | B11 FR_PLAY 跳逐帧回读 | 播放每帧全画布 GPU 回读 → 只留末帧 | 播放可交互 |
| 2026-10-28 | B12 BOOT_SCRIPT 注入 | 全堆 6600 表 → 子图 908 表，0.14 → 0.09 s/帧 | 1.6× |
| 2026-10-28 | B12 资产编码字节 | 路径资产 RGBA8 像素域膨胀 → 原样字节 | 资产 5-10× |
| 2026-10-28 | B12+ font 字节池化 | 同 TTF ×6 字号全量 hex（18.75 MB）→ 1 份 + 5 引用（3.1 MB），全流 39.1 → 23.5 MB | **-40% 全流** |
| 2026-10-29 | B15 帧间增量（P1 + pd 优化） | **稳态/帧**：world_map 103.6→**2.03 KB（-98%）**、battle 7.2→**2.45 KB（-66%）**；@30fps world_map **0.50 Mbps**、battle **0.60 Mbps（双场景均进电话线级）** | **-98%**（静态锚） |
| 2026-10-30 | B18 dream M1（LLM 直出） | Qwen3.8 直出 60 帧（剑侠 kit 18 资产）：**生成密度 ≈119 tok/帧**（477 B/帧 = out 338 + st 82 + 封装；op 分布 draw 2/帧+circle+print+clear）；全流 15.77 MB 中资产段 15.74 MB 占 **99.8%**（kit 死重，B16 内容寻址正靶）；.frb 7.88 MB（hex 减半） | LLM 生成密度基线 |
| 2026-10-30 | B18 dream :px 直写切换 | 同题英雄行走：:full 119 tok/帧（477 B）→ **:px ≈55 tok/帧（~250 B，-53%）**；LLM 直写 :px（短名/整数量化/缺省省略），fr-as 归档自动 :full（.frb 档位自由）。**新瓶颈定位**：网关 `/thinking/v1` 强制 reasoning（同题 942~17636 字符随机），延迟 2.8~40s 波动——nginx 60s 超时是主要失败源（504），客户端解=chunk-frames 旋钮+重试，根治=网关调超时/换 no-thinking 路由 | **-53% 生成 token** |
| 2026-10-31 | B18 dream append-only messages（缓存友好） | DeepSeek flash 60 帧 :px 直写：**usage 实测** prompt 24,981（**命中缓存 17,280=69%**）/ completion 7,729 / 墙钟 27s（滑窗版 92s，-71%；chunk 均时 4.0s）。滑窗改写中段是反缓存优化（前缀缓存要求第 0 字节起逐字节相同）——append-only（system 静态+turn 对追加）让除最新段外全命中。净内容账 ≈50 tok/帧；成本大头=flash 档 reasoning（chat 档为零） | **缓存命中 69%、墙钟 -71%** |
| 2026-10-31 | B18 dream 本地 Qwen `/no-thinking` 路由 | 同题 60 帧 :px（本地 Qwen3.8-flash，append-only）：usage prompt 31,245 / completion 9,257（**reasoning_tokens=0**——`/no-thinking/v1` 与 `/v1` 路由实测关思考，`/thinking/v1` 强制开）/ 墙钟 **45s、chunk 均时 7.2s±0.1**（零重试零网络波动）；lint/check/FR_PLAY 全过。**三家对照**：DeepSeek flash 27s（有缓存）/ 本地 no-thinking 45s（无缓存、无网络、无费用）/ 本地 thinking 路由=不可用（60s 超时全灭）。**dream 后端推荐序：DeepSeek（质量+缓存）> 本地 no-thinking（免费+稳定）**；`enable_thinking` 参数网关不支持，路由名即开关 | **本地后端可用化（免费稳定档）** |
| 2026-10-31 | B18 dream v1.5 词汇实测（CP 裸形 + Tier2 首考） | 本地 no-thinking 同题（走 40 帧+停 20 帧）：**CP 裸形即刻采用**（19 帧驻留全用裸 CP）；**Tier2 动词零采用**（行走段模型仍写全量 D 行——"走路=MOVE 链"的模式识别未建立，vocab 需给运动示例）；completion **9,257→6,468 tok（-30%）**；chunk 分化显著：全量段 7.2s vs CP 段 **1.3s（1/5.5）**；prompt 40,164（词汇表扩大）；墙钟 34s。判据全过（lint/check/播放 60 帧） | **CP 即刻采用；Tier2 待 vocab 运动（MOVE）示例强化** |
| 2026-10-31 | B18 v1.5 词汇二考（vocab 补 MOVE 行走示例帧） | 同题重跑：**MOVE 仍 0/40 采用**——示例帧对"模式映射"类动词教学无效（Qwen3.8-flash 能力边界：偏好全量重写/CP 复制，不做增量模式映射）；**新现象**：驻留段退化为逐帧单写 CP（不遵守"本次输出 10 帧"），chunk 轮次 6→14，prompt 40k→**116k**（append-only 累积+轮次翻倍）；completion 6,427 持平；判据全过。结论：**Tier2 采用率是模型能力边界非教学问题**——换强模型（DeepSeek）重测或接受 CP-only 现状 | **MOVE 示例无效；逐帧单写退化现形** |
| 2026-10-31 | B18 dream **S 行进 LLM 词汇面**（模型直出帧级重复引用） | 同后端同题+驻留段（中间停 15 帧+边缘停住）：模型主动用 S **36/60 帧**（指令只要求 ~25——边缘停住也自觉用 S 链）；S-heavy chunk **1.4s vs 全量 7.2s（1/5）**；completion **9,257→4,064 tok（-56%）**，墙钟 45→**23s**；head `:px +d` 自动协商、lint（L002 锚对账/L005 协商）全绿、fr-check --strict 过、FR_PLAY 60 帧播出（**dream 首条 +d 流过 C 展开器全链**）。D14 可实测项落地：LLM 能书写 S（ref=刚写帧号无簿记），pd 仍禁 | **驻留段 completion -56%** |
| 2026-10-31 | B18+ 雷达用例：矢量原语全家桶（Qwen no-thinking） | 60 帧 19 行/帧（AR 扫描束/CI×3/LN×2/PY×3/PT×8/R×2/PR×2/C），**completion 52,468（≈865 tok/帧）**，chunk 均时 39.6s，零重试，CHECK OK。**剧本设计三教训**：① arc 角度域=弧度（度数剧本 → 279° 大饼每帧跳 344°，"扫描线消失"）；② Qwen 对 >15 token 变长行必数错（16 星一行 PT 打回 2 次仍错；**单点 PT + 静态行整行照抄**绕开）；③ "指向运动方向"需旋转矩阵 → 退化固定偏移模板（187px 横刺），**偏移写死成剧本常量**后形状恒定；cos/sin 轨道点帧 30+ 漂移出画面（后期 chunk 心算累积） | **七原语覆盖；弱模型剧本适配模式定型** |
| 2026-10-31 | B18+ 雷达 DeepSeek flash 对照（同剧本） | completion **68,553（比 Qwen +30%**——小数位写满）；prompt 缓存命中 **73,088/105,477=69%**；chunk 均时 35.0s（略快于本地 Qwen 39.6s）；零重试 CHECK OK。强模型未再实测三角漂移（未逐帧验，成片目视正常） | **强模型对照锚** |
| 2026-10-31 | B18+ 像素 sprite 帧动画（D 换图） | kit 8 帧 32×32 序列帧（PIL 程序生成→fr-assets --from-files），剧本只给 `资产号=1+(N mod 8)`：60 帧零重试，D 行资产号轮转分布全对；**completion 11,210（≈187 tok/帧，全用例最低）**；chunk 均时 8.4s。LLM 退化为查表复读——机制验证通过，创作含量零 | **帧动画语义通；生成密度基线（复读档）** |
| 2026-10-31 | B18+ 像素心跳 v1（R 指令即像素，ASCII 参照） | 36 帧 **1,530 行 R**（大心 53 格/小心 27 格逐格），ASCII→坐标行空间翻译**零错格**；completion 63,386（≈**1.7k tok/帧**——雷达 2×、sprite 9×）；chunk 均时 23.9s。**网关边界实测**：密集 R 行 chunk 9 帧×15k completion=nginx 60s 超时 504；**chunk 3 帧×2k=12 chunk 全过**。R 定长行天然避开数数弱点 | **密集定长行可行；chunk 配比=3 帧** |
| 2026-10-31 | B18+ 像素心跳 v2（自由创作，撤 ASCII） | 同题撤图案参照：**自由创作反而更好**——自设格子轮廓圆润带阶梯感、两态自洽（大心形状跨帧一致）、颜色语义分明（大红/浅粉）。completion 93,824；**append-only 疲劳量化**：chunk 3 起每请求只写 1 帧，28 request/36 帧，prompt 累积 **1.75M tok**——高输出用例历史疲劳更早出现，**M2 前情提要立项数据**。剧本设计模式：**约束给死（格子/区域/行数/切换规则），创作放活（形状/颜色）** | **自由创作>图案参照；M2 立项锚** |
| 2026-10-31 | B18+ 心跳 v2 复跑：**chunk 帧数不足打回**（92d7605） | run.py 补"要 N 帧实得 M 帧 → ValueError 打回+feedback 点名"（此前短输出照单全收，进 assistant 历史成为"少写也行"的自我示范）。同剧本同模型复跑：**28→12 request（每次满 3 帧）**，prompt 累积 **1.75M→505k（-71%）**，completion 93.8k→81.1k，墙钟 7→6.1min，判据全过、成片目视同质。**归因修正**：append-only 疲劳的主因是示范滑坡（runner 放行所致）而非纯历史长度——滑坡已堵，M2 对象只剩无状态重复发送本身 | **prompt -71%；M2 范围收窄** |
| 2026-10-31 | B18+ 分层场景《夜行》：**Tier2 首次大规模采用**（MOVE/POSE/ENTER/CP） | 矢量后景画一次不动 + 英雄精灵编辑行组行走：36 帧 **completion 868（≈24 tok/帧，全用例最低**，雷达 1/36）**，chunk 均时 1.1s**，零重试 CHECK OK，成片四帧目检全对（行走轨迹/帧 15 换装/帧 20 云入场/静止段）。**采用率**：编辑行组 35/35 帧（全量重写 0）；MOVE ~90%（canonical SET 54≈MOVE 降级两行×26+直写；此前行走用例 MOVE 0/40）；POSE 1（身份随行转移正确）、ENTER 1、CP 6（静止段全对）。**采用率翻转的杠杆=剧本用指令词汇写动作**（"每帧一行 MOVE 1 12 0"式分镜），vocab 示例教学无效、分镜式剧本有效 | **24 tok/帧；Tier2 采用 0→90%** |

### B15 增量档实测（2026-10-29，双场景；FR_DELTA=1，I 帧缺省策略 + pd 优化）

| 场景 | :px full | :px +d 增量 | 收益 | S 帧 |
|---|---|---|---|---|
| world_map 17 帧 | 103.6 KB/帧 | **2.03 KB/帧** | **-98%** | 15 |
| battle 15 帧 | 7.2 KB/帧 | **2.45 KB/帧** | **-66%** | 14 |

@30fps：world_map **0.50 Mbps**、battle **0.60 Mbps（双场景均进电话线级）**
——15fps 验证档再减半（~0.25/0.30 Mbps）。判据：增量流 C 展开回放 rc=0；
mini 三帧流（I/S/pd/rdp/rdm 混合）展开 D_CRC 与手推全量逐帧一致。已知边界：
battle 锚形态基准（跨跑 D_CRC 不适用），增量决策确定性按 world_map 锚验证。

### B14 :px 档实测（2026-10-29，双场景）

| 场景 | .fr full | .fr :px | 收益 | .frb |
|---|---|---|---|---|
| world_map 10 帧 | 19.69 MB | 17.68 MB | -10% | 9.58 MB |
| battle 8 帧 | 20.55 MB | 20.13 MB | -2% | 10.16 MB |

px 流离线回放 rc=0、D_CRC 与 full 逐帧一致（整值量化渲染等价判据 ✅）。
**结论修正**：全流体积的主导项是资产段——全流级压缩的下一级台阶是 B16
资产内容寻址（hex→sha 引用，预估再 -10~20MB）；:px 档的 :75% 模拟系
out 段内部比例。载数字教训：**模拟收益必须按"对全流的分母"重新归一**。
| 2026-10-28 | B12+ font 字节池化 | 同 TTF ×6 字号全量 hex（18.75 MB）→ 1 份 + 5 引用（3.1 MB），全流 39.1 → 23.5 MB | **-40% 全流** |

## 已知优化路径（按投入/收益排序）

> 串流目标阶梯（用户定调）：**15fps 理念验证（.frb ~12 Mbps，已进普通宽带区）
> → 30fps 产品档（~24 Mbps）→ 帧间增量后 KB 级/帧（60fps 随意）**。
> 录制吞吐同理分档推进。

1. **帧间增量**（v2 大招）：静态画面帧引用上帧（`same` 行）——out 段 7.7MB/30 帧里静态世界重复占绝对多数，10-50× 量级；spec 显式演进。增量后稳态带宽由"画面变化率"决定而非"画面复杂度"。
2. **`.fr` 容器 gzip/zstd**：tile 行高度重复，5-10×，工具透明（对串流带宽同样直接 ×压缩比）。
3. **录制吞吐**：s_crc 降频（FR_SCRC_EVERY）／sim harness（确定性重放，第三方 s_crc 可比的前提）。

## 复现命令

```bash
cd /d/Lab/AgentLove2d
SHA=$(python -c "from tools.fr_gen import tbl; print(tbl.tbl_sha256(tbl.parse(open('tables/cmd.tbl',encoding='utf-8').read())))")

# 吞吐基线（全堆 / 子图注入二选一）
time (FR_CAPTURE=1 FR_OUT=/tmp/bench.fr FR_SHA=$SHA FR_SEED=1 \
  [FR_BOOT_SCRIPT=D:/Lab/AgentLove2d/tools/fr_boot_newgame.lua] \
  megasource/build115/love/Release/love.exe /d/Lab/MiniMaxWorkspace/newgame \
  --scenario test_world --smoke 30 >/dev/null 2>&1)

# 体积构成（stderr 首帧含 s_crc 规模护栏：全堆/子图表数）
ls -l /tmp/bench.fr
grep -c "=4" /tmp/bench.fr   # font 引用行数
```

