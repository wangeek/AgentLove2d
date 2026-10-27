-- l0/conf.lua —— L0 headless 配置
function love.conf(t)
    t.window = false        -- headless：L0 shim 只记录不执行
    t.identity = "fr-l0"
end
