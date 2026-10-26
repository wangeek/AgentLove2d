# AGENTS.md

FR 帧流 IR（.fr / .frb 双形态）工具链，载体为魔改 LÖVE 11.5：Lua 内核脚本产出 FR 流，引擎内 C 层捕获与回放。先建工具、后改造 sango——sango 只是未来的 lowering 前端之一，与本项目解耦，**不得把 sango 的实现形态当成本项目的设计约束**。

## 真源文件（动手前先读）

- `docs/design.md` — **总纲入口**：系统全貌、一帧的一生、机制卡、工具族地图、实施路线——新会话从这里进，再按其 §0 读者地图跳真源
- `docs/fr-spec.md` — FR 规格 v1.2（封版）：段语义、级别三档、命令集、事件词汇表、工具族、取证清单
- `docs/decisions.md` — 架构决策 D1–D7：LLVM 模式总则、语义四准则、验证两律、树不进协议、语境纪律、LÖVE 定位
- `docs/love2d-gap.md` — 魔改设计与差距分析 v2：六个挂点、绘制层（引擎内 C 回放 + 捕获后回放）、事件层（C 捕获/注入 + 自有 run loop）、log（API 边界记录，debug 栈钩仅审计）
- `tables/cmd.tbl` — 命令表 = 单一真源；两端编解码代码从它生成，**不许手写编解码**

## 硬纪律

- IR 词汇表只用现代语义（f32 `%.6f`、RGBA8、TTF 字体字节、HID scancode、UTF-8），宿主 = LÖVE，它的事件名/像素格式/字体管线就是普通话；**legacy 方言（GDI / WM_ / VK_ / 调色板 / 点阵）不进本仓库**，未来前端的兼容映射住前端自己的仓库
- 判据只许"符号比较"（锚行 diff）或"字节相等"；墙钟时间只进注释列
- 规格条目状态：sealed 不擅改；draft 待 fr-gen 首版落定；待取证项先取证再定
- 内核与渲染端的唯一通道是 FR 流，内核不得读渲染端状态（D8〔待拍板〕取代 D6，见 docs/decisions.md）
- 工具命名不与现成 shell 命令撞语义
- 修改规格 = 改 `docs/fr-spec.md` + 在其 §13 版本记录追加一行；决策修订 = 在 `docs/decisions.md` 追加新条目注明取代关系

## Setup commands

- 运行 LÖVE：`love2d/love-11.5-win64/love.exe <游戏目录>`
- Python 工具（fr-*）：`python tools/<tool>.py ...`（fr-gen 已交付：`python -m tools.fr_gen.gen_python` / `gen_c` 再生双目标，改表后必跑）
- 测试：`pytest tests/`（29 项：解析/量化/编解码/零漂移与跨目标锚）

## Project layout

- `docs/` — 规格真源与决策台账（中文）
- `tables/` — `cmd.tbl`（IR 单一真源，命令集 v1.2 对照 LÖVE 11.5 源码定稿）
- `tools/` — fr-* 工具族（Python；C 编解码由 fr-gen 生成）
- `render/` — LÖVE 渲染端（Lua）
- `tests/` — round-trip 回归、对拍
- `love2d/` — LÖVE 11.5 素材（win64 运行时 / 官方 11.5 源码 / wiki dump；运行时二进制不入 git；**源码必须与锁定运行时同版本**）

## Code style

- 三语并存：Python（工具）、C（编解码，fr-gen 生成）、Lua（渲染端）；**生成代码不手改，改表重新生成**
- 文档与注释用中文，标识符用英文
- 浮点文本 `%.6f` 定长；判据锚行不锚全文

## Testing instructions

- 最高优先回归：`.fr` → `.frb` → `.fr` round-trip 逐字节相等，CMNT 注释保留
- 待取证项（`docs/fr-spec.md` §12）先取证，再改规格，再实现；取证结论登记进 `tables/cmd.tbl` 的 source/notes 列
