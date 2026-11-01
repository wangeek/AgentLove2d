-- dream/runner/main.lua —— M2 §9 交互式 Runner
-- 渲染：love.draw 每帧调 _frOfflineAppend（C++ 增量解析+dt 节奏+贴屏；
--       空闲只贴屏——末帧反复绘制，流不增帧）
-- 事件：Lua 捕获（love.handlers 正统层）→ JSON 行 append 到 .evq（io）
local stream = os.getenv("FR_STREAM") or "dream_session.fr"
local evq = os.getenv("FR_EVQ") or (stream .. ".evq")
local dbg = os.getenv("FR_RUNNER_DBG")
-- FR_EV_INJECT：脚本化事件注入通道（CI/测试用）——love.update 轮询该文件，
-- 每行 "type <arg>..." 经 love.event.push 进 love 事件队列（与 OS 输入同一
-- 管线：回调 Lua 捕获层全链被测；D14 双生产者的合成口径）。
local inject_path = os.getenv("FR_EV_INJECT")
local inject_off = 0

local cur_frame = -1
local ev_no = 0

local function mark(msg)
	if not dbg then
		return
	end
	local fh = io.open(dbg, "a")
	if fh then
		fh:write(msg .. "\n")
		fh:close()
	end
end

local function poll_inject()
	if not inject_path then
		return
	end
	local fh = io.open(inject_path, "rb")
	if not fh then
		return
	end
	fh:seek("set", inject_off)
	local data = fh:read("*a")
	fh:close()
	local last_nl = data:find("\n[^\n]*$")
	if not last_nl then
		return
	end
	data = data:sub(1, last_nl)
	inject_off = inject_off + last_nl
	for line in data:gmatch("[^\n]+") do
		local toks = {}
		for t in line:gmatch("%S+") do
			toks[#toks + 1] = t
		end
		if toks[1] then
			local args = {}
			for i = 2, #toks do
				local v = toks[i]
				if v == "true" or v == "false" then
					args[#args + 1] = (v == "true")
				elseif tonumber(v) then
					args[#args + 1] = tonumber(v)
				else
					args[#args + 1] = v
				end
			end
			mark("inject push " .. line)
			love.event.push(toks[1], unpack(args))
		end
	end
end

local function report(ev, args)
	mark("report enter " .. ev)
	ev_no = ev_no + 1
	local parts = {}
	for _, v in ipairs(args) do
		parts[#parts + 1] = tostring(v)
	end
	local line = string.format('{"no":%d,"ev":"%s","args":[%s],"frame":%d}',
		ev_no, ev, table.concat(parts, ","), cur_frame)
	local fh = io.open(evq, "a")
	if fh then
		fh:write(line, "\n")
		fh:close()
		mark("report wrote " .. line)
	else
		mark("report CANNOT OPEN " .. evq)
	end
end

function love.load()
	love.window.setTitle(os.getenv("FR_TITLE") or "dream-runner")
	mark("load title=" .. tostring(os.getenv("FR_TITLE")))
end

function love.update(dt)
	poll_inject()
end

function love.draw()
	local r = love.graphics._frOfflineAppend(stream)
	mark("draw r=" .. tostring(r))
	if r == -2 then
		mark("parse-error quit")
		io.stderr:write("fr-iact: 解析错误，退出\n")
		love.event.quit(3)
		return
	end
	cur_frame = r
end

function love.mousepressed(x, y, button, istouch)
	mark("mousepressed " .. tostring(x) .. "," .. tostring(y))
	report("mousepressed", { x, y, button, istouch and 1 or 0 })
end

function love.mousereleased(x, y, button, istouch)
	report("mousereleased", { x, y, button, istouch and 1 or 0 })
end

function love.keypressed(key, scancode, isrepeat)
	report("keypressed", { string.format("%q", key), isrepeat and 1 or 0 })
end
