# LÖVE 参考渲染器设计

FR 流的第一个图形消费者。规格见 docs/fr-spec.md，纪律 D6：**FR 内核不进 love.update**。

## 库内素材

- `love2d/love-11.5-win64/` —— Windows 运行时（`love.exe`），版本锁定 11.5
- `love2d/love-src/` —— C++ 源码，官方 11.5 tag（commit `6eb8d54`；改造与查实现语义用；素材必须与锁定运行时同版本）
- `love2d/wiki-allpages-1.json` —— 离线 wiki 全页 dump（查 API 用）
- `love2d/readme.md` / `changes.txt` / `license.txt`

差距分析（stdout 出口、绘制层深度、事件流、log 机制）见 `docs/love2d-gap.md`。

## 为什么是它（同构点）

- **立即模式无树**：`love.draw` 每帧全量提交，没有 scene graph / 控件对象 / 失效重画——"树不进协议"（D4）在这里没有东西可剥，渲染端就是"读一行、翻一行"的翻译循环。
- **`love.handlers` = 事件表是数据的活标本**：字符串键查表分发；事件类型表从 cmd.tbl 生成后注册进 handlers 即完事。
- **`love.run` 本身可覆盖**：泵 → 帧首统一出队 → 结算 → 提交 → 帧尾——FR 五段（in/log/out/end）原位挂进这个循环。
- **`love.thread.getChannel` = 队列语义**：同进程拓扑的现成传输层。
- **Quad = 定义一次引用多次的编号资产**（CAD block 的 API 版）；**ImageData = 资产级矩阵运算的脚本接口**（getPixel / mapPixel / paste）——透明掩码、色板替换、块 diff 全在这层做，配合 ImageData 存文件做字节相等验收。
- LuaJIT + FFI = 性能后门。

## 六命令 → 接口映射

| FR | LÖVE | 说明 |
|---|---|---|
| spr | `love.graphics.draw(atlas, quad[n], x, y, 0, flip and -1 or 1, 1)` | `newQuad(x,y,w,h,总宽,总高)` 定义切片；翻转配 origin 防镜像错位 |
| txt | 点阵：`draw(glyph_atlas, quad[码位], x, y)`；过渡期 `love.graphics.print` | 字模 = 资产：原版字模进纹理图集，按码位切片引用 |
| fill | `setColor(...)` + `rectangle("fill", x,y,w,h)` | 每行自设色，不留隐状态 |
| blt | `love.graphics.setCanvas(dst)` + `draw(src)` / `Canvas:renderTo` | Canvas ↔ Pixmap |
| lut | 查表 shader 换 pal uniform | 唯一硬改造点（retro 社区标准手法） |
| end 段 | `love.graphics.present()` | 帧边界；校验和在流协议层 |

调色板查表 shader（示意，256×1 调色板纹理）：

```glsl
uniform sampler2D pal;
vec4 effect(vec4 col, Image idx, vec2 uv, vec2 sc) {
  float i = Texel(idx, uv).r;        -- 像素里存的是索引
  return Texel(pal, vec2((i*255.0+0.5)/256.0, 0.5));
}
```

## love.run 一圈 = FR 一帧

```
pump()                 ← 帧边界，上一帧 end 段闭合
poll() 逐事件          ← in 段（slot = 迭代序号；CALL 嵌套记深度）
handlers[name](...)    ← 内核消费事件
update(dt)             ← log 段挂点（rngc / st）
draw()                 ← out 段（spr/txt/fill/blt 逐行翻译提交）
present()              ← end 段（s_crc + d_crc）
```

## 事件语境

- 词汇表 = handlers 键名；EV 签名 = `love.event.push` 参数序，零翻译。
- **录制** = handlers 外套一层记录器（poll 循环里写 in 段行）。
- **回放** = 按 slot 序把录制的事件行原样 `push` 回去，跑一帧。
- `CALL` = `love.handlers["x"](...)` 直接调用（栈帧增长）；`push` = 队尾追加——SendMessage / PostMessage 的 lowering 对照在 LÖVE 里看得见摸得着。
- 自定义事件：`love.event.push(任意键名, args...)` + `love.handlers[键名] = fn` 注册；回放脚本注入走同一条路。

## 拓扑两种（流格式不变，传输层可换——双形态原则）

- **A 同进程双线程**：无头内核进 `love.thread`，Channel 传帧包。快、简单、调试容易。
- **B 双进程 / 跨机**：stdin / socket / 串口吃同一份流。更接近最终设备形态。

## 已知劣势与对策

| 劣势 | 对策 |
|---|---|
| OpenGL 依赖，上不了裸机 | 定位即参考渲染器；设备端瘦客户端消费同一份流 |
| 调色板非一等公民（RGBA 浮点管线） | 索引图纹理 + 256×1 LUT 纹理 + 查表 shader，唯一硬改造 |
| 文本走 FreeType 现代光栅 | 点阵字库走纹理图集（本来就是资产方案） |
| 版本漂移史（10.x→11.x 颜色 0-255→0-1） | 锁 11.5；升级 = 一次显式迁移 |

## 待实测

- poll 迭代中途 push 的事件落本帧还是下帧（影响 handler 自通知的落帧）。slot 机制两种都能如实记录，实测结论登记进 gdi_map.tsv。
