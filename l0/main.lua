-- l0/main.lua —— L0 入口：模式分发（--selftest / --demo；完整 run loop + 会话组装随 Task 3）
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

-- --demo：行级验证模式——注册资产 → 固定 dt → update → draw，产出行文本逐行
-- print（每帧序：dt → asset(仅首帧 checkpoint) → out；会话组装与文件写出随 Task 3）。
if has("--demo") then
    local frames = tonumber(get_val("--frames") or "")
    local fixed_dt = tonumber(get_val("--fixed-dt") or "")
    if not frames or not fixed_dt then
        io.stderr:write("l0: --demo 需成对参数 --frames N 与 --fixed-dt X\n")
        os.exit(2)
    end
    local shim = require("shim")
    local kernel = require("kernel")
    local g = shim.new()
    -- 资产注册（行进 asset_rows 独立缓存，runner 首帧并入）：注册序定死
    -- image=1 → font=2，kernel.draw 按此号引用；data_hex 为固定假数据
    -- （L0 无真解码，确定性不受影响）。
    g.newImage(32, 32, "00010203")
    g.newFont(14.0, "00010203")
    for f = 1, frames do
        print(fr.render_line("dt", { val = fixed_dt }))
        kernel.update(fixed_dt)
        g.rows = {}                     -- 当帧行缓存清空后重收（out 段）
        kernel.draw(g)
        if f == 1 then                  -- asset 行仅首帧重放（frame 0 = checkpoint）
            for _, row in ipairs(g.asset_rows) do print(row) end
        end
        for _, row in ipairs(g.rows) do print(row) end
    end
    os.exit(0)
end

io.stderr:write("l0: 未知模式（--selftest | --demo）\n")
os.exit(2)
