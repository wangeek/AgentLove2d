# fr_dump --geo：读侧屏幕有效矩形派生视图（D15 方案一）

日期：2026-11-16 ｜ 决策：docs/decisions.md D15 ｜ 状态：实施

## 问题
整图入引擎缩小绘制（icon 128 画 32）时，流=API 事实，agent 看屏幕语义须自乘 sx/sy
并 cross-reference asset 尺寸——geo 混乱，判据无法精细锚。

## 设计
- `fr_dump --geo`：登记表从 **parse 后 Session entries 结构化构建**（image/canvas w h、
  quad x y w h sw sh）——先建表、后 --frames 过滤（帧过滤可能丢 frame 0 的 asset 行）。
- 输出：dump 文本逐行扫描，每条 `draw` 行后插一行 '# geo: …'（'#' 前缀不参与再
  parse，与 --strip-assets 摘要同构）。
- 计算（rot==0）：quad=0 → src=整图；quad=k → src=(qx,qy,qw,qh)；
  rect = (x-ox*sx, y-oy*sy, qw*sx, qh*sy)；数值 %.2f 定长（确定性视图投影）。
- rot≠0：`at=<x>,<y> rot=…（非轴对齐不展开）`；tex 未登记：如实注记不展开。
- 帧内 draw 计数序号 d<N>（frame 行重置）；CP 增量流无 draw 行自然稀疏，不特殊处理。
- fr_read 不加参数（MCP 面维持三件）；需要时 agent 走 CLI。

## 验收
1. 基础缩放/ox oy 偏移/quad 切片/rot 注记/幻 tex 五形态正确；
2. --frames 过滤与 --geo 组合（登记表来自过滤前）；
3. 同流两次 --geo 输出逐字节一致（确定性）；
4. geo 行 '# ' 前缀不破坏 fr_check / fr-as round-trip（dump 输出本就不是 parse 入口，
   但须确认 --geo 关闭时输出与原先逐字节一致——零漂移）。

## 方案二配套（只写建议）
- fr_record description 追加资产预处理建议（预缩屏幕尺寸/atlas 显式 quad/sx=sy=1），
  明确"本工具不执行，由使用方 agent 自行衡量"。
- agent-guide §1 末尾同款建议段；§2/§8 补 --geo 行。

## 方案四配套（2026-11-16 用户追加拍板）
- `fr_dump --names <assets.json>`：fr_assets --from-files 产出的 src 字段
  （文件名=语义名）join 进 strip 摘要行与 geo 行（`tex=1(icon_01.png)`）；
  名字住 kit 目录不进流（D15 精神）。extract 路径无名字来源，不产 src。
- fr_record description 不再扩（三件 description 已达信息密度上限，
  --names 属 CLI 观察面，agent-guide §2/§8 覆盖）。
