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

