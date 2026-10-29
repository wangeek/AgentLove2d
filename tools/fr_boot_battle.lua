-- tools/fr_boot_battle.lua —— B13 动态基准：直切 Test Battle（零参默认 5v5）
-- 用法：FR_BOOT_SCRIPT=<本文件> FR_CAPTURE=1 FR_OUT=... love.exe newgame
-- 机制：boot script 在首帧 present 前执行（B12）；此后每 0.5s 注入鼠标点击
-- 推进"结束回合"（回合制 UI 固定——点击序列确定性）。
-- 按钮坐标与事件形态来自 src/modes/battle.lua 实测（见设计 §2.1）。
local State = require("src.core.state")
local C = require("src.constants")
State.switch(C.MODE.BATTLE)

-- 注入循环：借 love.event 的定时器线程不可行（无 timer 钩）——改在
-- love.update 上叠加（本 script 执行时 love.update 尚未定义；游戏
-- main.lua 随后定义会覆盖——故用 metatable 拦截不可靠，改用事件侧：
-- love.handlers 不存在则用 love.run 外钩。最稳路径：定时 push 事件
-- 由 Event 队列天然节流不可行——改为每帧 push 由 poll 白名单丢弃？
-- 结论：采用 C tee 已有的 ev 注入通道不可达（boot 期无 C 出口）——
-- 最终方案：直接改 State.current handler 的 advanceTurn 延迟直调，
-- 用 love.timer 线程不安全——改用 love.update 叠加（若被覆盖则
-- 包装：在 love.load 尾部由本 script 的 dofile 时机保证先定义）。
local t = 0
local _orig_update = love.update
function love.update(dt)
    if _orig_update then _orig_update(dt) end
    t = t + dt
    -- 2s 间隔 >> 捕获态帧时长（~1s）：推进点落帧边界的漂移仍存在
    --（墙钟 vs 帧钟不可对齐）——battle 锚按设计降级为"形态基准"
    --（熵剖面有效；D_CRC 确定性判据不适用，如实登记）。
    if t >= 2.0 then
        t = 0
        local h = State.current and State.current() or nil
        if h and h.advanceTurn then
            pcall(function() h:advanceTurn() end)
        end
    end
end
io.stderr:write("fr-boot-battle: switched + advance loop\n")
