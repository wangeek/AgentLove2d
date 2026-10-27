-- l0/main.lua —— L0 入口：模式分发（本任务：--selftest；runner 随 Task 2/3 扩展）
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

local fr = require("fr")

if has("--selftest") then
    local ok, err = xpcall(fr.selftest, debug.traceback)
    if not ok then
        io.stderr:write("l0 selftest 失败: ", tostring(err), "\n")
        os.exit(1)
    end
    os.exit(0)
end

io.stderr:write("l0: 未知模式（本任务仅支持 --selftest；runner 随 Task 2 接入）\n")
os.exit(2)
