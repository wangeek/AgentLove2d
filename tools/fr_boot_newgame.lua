-- tools/fr_boot_newgame.lua —— FR 外置状态根注入脚本（B12）
--
-- 用法：FR_BOOT_SCRIPT=<本文件绝对路径> 与 FR_CAPTURE=1 同设。
-- 零游戏源码改动：脚本住 FR 仓库，fork 在首帧 present（s_crc 采集前）
-- 惰性执行；游戏模块此时已全部 require 完（love.load 后）。
--
-- 根选型：package.loaded 中所有 "src." 前缀模块表（newgame 的游戏全域
-- 状态——modes/constants/world 实体/服务都在模块表上）。函数/对象槽在
-- canonical_tv 只计类型 tag（指针位清零），跨进程确定；数据槽全量 CRC。
-- 观测范围从全堆回退（60MB 级）收缩到游戏子图——录制吞吐恢复 +
-- s_crc 升回真判据（子图口径跨进程可比，B6 实证）。
local roots = {}
for k, v in pairs(package.loaded) do
	if type(k) == "string" and k:sub(1, 4) == "src." and type(v) == "table" then
		roots[k] = v
	end
end
local n = 0
for _ in pairs(roots) do n = n + 1 end
if n > 0 then
	love.graphics._frStateRoot(roots)
	io.stderr:write(("fr-boot: %d 个 src.* 模块入状态根\n"):format(n))
else
	io.stderr:write("fr-boot: 未发现 src.* 模块（时机过早？降级全堆）\n")
end
