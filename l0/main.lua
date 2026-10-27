-- l0/main.lua —— L0 入口：模式分发（--selftest / --demo）
--
-- arg 表语义实测（2026-10-27，love-11.5-win64，headless t.window=false，探针结论）：
--   love.exe l0 --selftest 时——arg[1]=游戏目录绝对路径，arg[2..n]=游戏参数
--   （--selftest 落在 arg[2]），arg[-1]="embedded boot.lua"，arg[-2]=love.exe 路径；
--   boot.lua:323 以 require("main") 加载本文件，vararg 实参只有模块名 "main"，
--   游戏参数不在 ... 里。故：模式解析一律读 arg[2] 起，不收 vararg。
--   headless 下主 chunk 内 os.exit 即整进程退出（探针验证 exit=0）。
local args = {}
if type(arg) == "table" then
    local i = 2
    while arg[i] ~= nil do
        args[#args + 1] = arg[i]
        i = i + 1
    end
end

local function has(flag)
    for _, a in ipairs(args) do
        if a == flag then return true end
    end
    return false
end

local function get_val(flag)
    for i, a in ipairs(args) do
        if a == flag then return args[i + 1] end
    end
    return nil
end

local fr = require("fr")

if has("--selftest") then
    local ok, err = xpcall(fr.selftest, debug.traceback)
    if not ok then
        io.stderr:write("l0 selftest 失败: ", tostring(err), "\n")
        os.exit(1)
    end
    os.exit(0)
end

-- --demo：完整会话产出（Task 3）——排干快照 run loop + 状态走查器 + 会话组装
-- 与文件写出（行级验证由测试覆盖，行打印不再保留）。
-- 参数：--frames N（计划帧数上限，quit 提前终止）--fixed-dt X --sha <64hex>
-- （cmd.tbl 指纹，调用侧算好传入；缺省报错 exit 2）[--seed n，缺省 0] --out <path>。
if has("--demo") then
    local frames = tonumber(get_val("--frames") or "")
    local fixed_dt = tonumber(get_val("--fixed-dt") or "")
    local sha = get_val("--sha")
    local seed = tonumber(get_val("--seed") or "0")
    local out_path = get_val("--out")
    if not frames or not fixed_dt or not out_path then
        io.stderr:write("l0: --demo 需参数 --frames N --fixed-dt X --out <path>\n")
        os.exit(2)
    end
    if not seed or seed < 0 or math.floor(seed) ~= seed then
        io.stderr:write("l0: --seed 须为非负整数\n")
        os.exit(2)
    end
    if not sha or #sha ~= 64 or sha:find("[^0-9a-f]") then
        io.stderr:write("l0: --demo 缺 --sha <64hex>（cmd.tbl 指纹，测试侧以 tbl_sha256 算好传入）\n")
        os.exit(2)
    end
    local shim = require("shim")
    local kernel = require("kernel")
    local walker = require("walker")
    local g = shim.new()
    -- 资产注册（asset_rows 独立缓存，frame 0 = checkpoint 重放）：注册序定死
    -- image=1 → font=2，kernel.draw 按此号引用；data_hex 为固定假数据
    -- （L0 无真解码，确定性不受影响）。
    g.newImage(32, 32, "00010203")
    g.newFont(14.0, "00010203")

    -- LÖVE 事件实参（原始 Lua 值）→ variant 形态（字符串包 {s} 表，fr.lua 约定）
    local function variants(vals)
        local vs = {}
        for i, v in ipairs(vals) do
            if type(v) == "string" then vs[i] = { v } else vs[i] = v end
        end
        return vs
    end

    local parts = {
        ("frb1 640 480 %s base %d"):format(sha, seed),
        "cmnt L0 demo session",
    }
    local quitting = false
    for f = 0, frames - 1 do
        -- 帧首：排干快照（design §2 ③；headless 下 OS 事件为空，pump 在
        -- boot.lua:310 先于本文件被调用——可用性有源码实证）。分发中新 push
        -- 落下一帧快照——L0 事件层注入走 runner 固定脚本，不经队列。
        love.event.pump()
        local snapshot = {}
        for name, a, b, c in love.event.poll() do
            snapshot[#snapshot + 1] = { name = name, vals = { a, b, c }, src = 0 }
        end
        -- runner 注入脚本（固定；src=2 合成）：帧 2 keypressed、帧 3 quit
        if f == 2 then
            snapshot[#snapshot + 1] = { name = "keypressed",
                                        vals = { "return", "return", false }, src = 2 }
        end
        if f == 3 then
            snapshot[#snapshot + 1] = { name = "quit", vals = {}, src = 2 }
        end

        -- 分发：ev 行（slot=帧内 in 段流水号）→ handlers 直调（CALL 行记深度）
        local in_rows = {}
        local slot_n = 0
        local function em(fn, depth, vals)
            in_rows[#in_rows + 1] = fr.render_line("call",
                { slot = slot_n, fn = fn, depth = depth, args = variants(vals) })
            slot_n = slot_n + 1
        end
        for _, e in ipairs(snapshot) do
            in_rows[#in_rows + 1] = fr.render_line("ev",
                { slot = slot_n, type = e.name, src = e.src, args = variants(e.vals) })
            slot_n = slot_n + 1
            local h = kernel.handlers[e.name]
            if h then h(em, unpack(e.vals)) end
            if e.name == "quit" then quitting = true end
        end

        -- update（dt 进帧头：墙钟派生的状态输入，回放喂记录值）→ draw（out 段）
        kernel.update(fixed_dt)
        g.rows = {}                     -- 当帧行缓存清空后重收（out 段）
        kernel.draw(g)

        -- walker 产 st/err（log 段；样机口径见 walker.lua 文件头）
        local st_rows, err_rows = walker.st_rows(kernel.state)

        -- 帧闭合（end 段）：样机口径 CRC32 = 行文本拼接（B6 换堆遍历）
        local s_crc = walker.crc32(table.concat(st_rows, "\n"))
        local d_crc = walker.crc32(table.concat(g.rows, "\n"))

        -- 拍平组装（段归属由 fr_ops section 元数据承载）：
        --   dt → asset(仅首帧) → ev/call(in) → st/err(log) → out → s_crc/d_crc(end)
        parts[#parts + 1] = ("frame %d"):format(f)
        parts[#parts + 1] = fr.render_line("dt", { val = fixed_dt })
        if f == 0 then
            for _, row in ipairs(g.asset_rows) do parts[#parts + 1] = row end
        end
        for _, row in ipairs(in_rows) do parts[#parts + 1] = row end
        for _, row in ipairs(st_rows) do parts[#parts + 1] = row end
        for _, row in ipairs(err_rows) do parts[#parts + 1] = row end
        for _, row in ipairs(g.rows) do parts[#parts + 1] = row end
        parts[#parts + 1] = fr.render_line("s_crc", { crc = s_crc })
        parts[#parts + 1] = fr.render_line("d_crc", { crc = d_crc })

        if quitting then break end      -- quit 提前终止（帧照常闭合）
    end

    -- 文件写出：UTF-8 / LF（"wb" 防 CRT 文本模式 CRLF 改写）；末尾单 LF
    local fh = assert(io.open(out_path, "wb"))
    fh:write(table.concat(parts, "\n") .. "\n")
    fh:close()
    os.exit(0)
end

io.stderr:write("l0: 未知模式（--selftest | --demo）\n")
os.exit(2)
