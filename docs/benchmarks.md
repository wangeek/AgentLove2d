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
| **稳态每帧字节（串流口径，10 帧实测）** | **.fr 229 KB/帧** / **.frb 101.6 KB/帧** | 纯 out 行（稳态帧=帧 1 起；帧 0 out 段偏大拖高均值）；out 行段 frb 压缩比 2.33×（勿用全流 2.09× 近似——资产段 hex 消除的压缩比远高于行段） |
| **稳态带宽（串流档位）** | **@60fps**：.fr ~109 / .frb ~47 Mbps<br>**@30fps（产品档）**：.fr ~55 / **.frb ~24 Mbps**<br>**@15fps（理念验证档）**：.fr ~27 / **.frb ~12 Mbps** | 云渲染帧率策略：稳定 30 足够、验证期 15 可接受（用户定调 2026-10-29）——**15fps 档已进普通宽带可达区**；帧间增量后目标 KB 级/帧（任何档位均轻松） |
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

