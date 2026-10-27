-- l0/shim.lua —— love.graphics 代理（只记录不执行；D11 变换栈就地结算）
-- L0 无真渲染：绘图方法经 fr.render_line 产 canonical 行文本进 api.rows（out 段，
-- runner 每帧清空重收）；资产注册行进 api.asset_rows 独立缓存（frame 0 =
-- checkpoint，仅首帧重放，并入时机由 runner 决定）。变换调用本身不产行——
-- draw/print 捕获时把资产坐标就地结算（x' = tx + sx*x …），结算后的行才进 rows。
local fr = require("fr")
local ops = require("fr_ops")

local shim = {}

-- 变换项：{ tx, ty, sx, sy }——点结算 world = (tx + sx*x, ty + sy*y)。
-- L0 demo 只用平移+缩放（D11 最小落地）；rotate 需扩 2x3 仿射，见 api.rotate TODO。
local function identity()
    return { tx = 0.0, ty = 0.0, sx = 1.0, sy = 1.0 }
end

function shim.new()
    local api = { rows = {}, asset_rows = {}, next_id = 1 }
    local stack = { identity() }   -- 变换栈；栈底恒为单位矩阵（pop 不许穿透）

    ------------------------------------------------------------------
    -- 资产注册（形参约定 B3b Task 2 定死）：
    --   newImage(w, h, data_hex) / newFont(size, data_hex) / newCanvas(w, h)
    --   data_hex = 小写 hex 串（L0 无真解码，调用方给固定假数据）；
    --   font 的 size 走 f32 口径（行内 render 为 %.6f）。
    --   返回自增资产号（1 起；0 保留给"空资产"，如 draw 的 quad=0）。
    ------------------------------------------------------------------
    function api.newImage(w, h, data_hex)
        local id = api.next_id
        api.next_id = id + 1
        api.asset_rows[#api.asset_rows + 1] =
            fr.render_asset({ kind = ops.kinds.image, id = id, w = w, h = h, data_hex = data_hex })
        return id
    end

    function api.newFont(size, data_hex)
        local id = api.next_id
        api.next_id = id + 1
        api.asset_rows[#api.asset_rows + 1] =
            fr.render_asset({ kind = ops.kinds.font, id = id, size = size, data_hex = data_hex })
        return id
    end

    function api.newCanvas(w, h)
        local id = api.next_id
        api.next_id = id + 1
        api.asset_rows[#api.asset_rows + 1] =
            fr.render_asset({ kind = ops.kinds.canvas, id = id, w = w, h = h })
        return id
    end

    -- 栈顶变换就地结算（D11）
    local function settle(x, y)
        local t = stack[#stack]
        return t.tx + t.sx * x, t.ty + t.sy * y
    end

    ------------------------------------------------------------------
    -- out 段绘图方法（形参序 = fr_ops 字段序，demo kernel 调用与此一致）
    ------------------------------------------------------------------
    function api.clear(r, g, b, a)
        api.rows[#api.rows + 1] = fr.render_line("clear", { color = { r, g, b, a } })
    end

    function api.draw(tex, quad, x, y, rot, sx, sy, ox, oy, cr, cg, cb, ca)
        -- D11：x/y 就地结算；draw 自身 rot/sx/sy/ox/oy（旋转/尺寸/锚点在变换下的
        -- 复合）L0 demo 恒 0/1，结算留 TODO（B4 引擎内捕获层一并补齐）。
        local x2, y2 = settle(x, y)
        api.rows[#api.rows + 1] = fr.render_line("draw", {
            tex = tex, quad = quad, x = x2, y = y2, rot = rot,
            sx = sx, sy = sy, ox = ox, oy = oy, color = { cr, cg, cb, ca },
        })
    end

    function api.print(font, text, x, y, rot, sx, sy, cr, cg, cb, ca)
        local x2, y2 = settle(x, y)
        api.rows[#api.rows + 1] = fr.render_line("print", {
            font = font, text = text, x = x2, y = y2, rot = rot,
            sx = sx, sy = sy, color = { cr, cg, cb, ca },
        })
    end

    function api.rectangle(mode, x, y, w, h, rx, ry, width, cr, cg, cb, ca)
        -- 矩形 op 规范名 rect（fr_ops 单一真源）；x/y 同样过变换（demo 恒单位
        -- 矩阵=直通）；尺寸 w/h 的变换缩放留 TODO（同 draw 口径）。
        local x2, y2 = settle(x, y)
        api.rows[#api.rows + 1] = fr.render_line("rect", {
            mode = mode, x = x2, y = y2, w = w, h = h,
            rx = rx, ry = ry, width = width, color = { cr, cg, cb, ca },
        })
    end

    -- 未进 demo 的形状/列表 op：形参直取 fr 字段表（键 = fr_ops 字段名）——
    -- love.graphics 真实形参对齐留 TODO（B4 前不定死签名，先保行编码能力）。
    local function rec_fields(op)
        return function(fields)
            api.rows[#api.rows + 1] = fr.render_line(op, fields)
        end
    end
    api.line = rec_fields("line")
    api.polygon = rec_fields("poly")
    api.circle = rec_fields("circle")
    api.arc = rec_fields("arc")
    api.points = rec_fields("points")

    function api.setCanvas(target)
        -- target = newCanvas 返回的资产号；nil/0 = 回到屏（rt 行 target=0）
        api.rows[#api.rows + 1] = fr.render_line("rt", { target = target or 0 })
    end

    function api.setScissor(x, y, w, h)
        api.rows[#api.rows + 1] = fr.render_line("scissor", { x = x, y = y, w = w, h = h })
    end

    ------------------------------------------------------------------
    -- 变换栈（D11）：只改栈顶、不产行；结算发生在 draw/print 捕获时。
    ------------------------------------------------------------------
    function api.push()
        local top = stack[#stack]
        stack[#stack + 1] = { tx = top.tx, ty = top.ty, sx = top.sx, sy = top.sy }
    end

    function api.pop()
        if #stack <= 1 then
            error("shim: pop 越过栈底（push/pop 不配对）")
        end
        stack[#stack] = nil
    end

    function api.translate(dx, dy)
        -- 对齐 love 复合序（world = M·T·p）：平移发生在当前局部系，偏移被当前缩放放大
        local top = stack[#stack]
        top.tx = top.tx + top.sx * dx
        top.ty = top.ty + top.sy * dy
    end

    function api.scale(sx, sy)
        sy = sy or sx
        local top = stack[#stack]
        top.sx = top.sx * sx
        top.sy = top.sy * sy
    end

    function api.rotate(angle)
        -- TODO（D11）：L0 demo 只用平移+缩放；rotate 接入需扩 2x3 仿射。
        -- 硬失败而非静默直通——记录端不容许"看似成功"的错误结算。
        error("shim.rotate 未实现（L0 demo 未用）")
    end

    function api.origin()
        local top = stack[#stack]
        top.tx, top.ty, top.sx, top.sy = 0.0, 0.0, 1.0, 1.0
    end

    return api
end

return shim
