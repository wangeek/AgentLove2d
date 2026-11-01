-- dream/runner/conf.lua —— M2 §9 交互式 Runner（love.exe dream/runner）
-- 窗口=流几何（Python 经 FR_W/FR_H 注入）；标题带会话 pid（防僵尸窗口误配）
function love.conf(t)
	t.window.width = tonumber(os.getenv("FR_W")) or 640
	t.window.height = tonumber(os.getenv("FR_H")) or 480
	t.window.title = os.getenv("FR_TITLE") or "dream-runner"
	t.window.vsync = 1
end
