-- l0/walker.lua —— 状态走查器 + CRC32（B3b Task 3）
--
-- 【样机口径登记——B6 log A 方案替换，Task 4 回写 spec/cmd.tbl】
--   1. st 行 obj=0 哨兵 + 点路径 key（如 "hero.x"）= **语义形态**：只表达语义槽位
--      与值，无物理对象身份。B6 A 方案换**物理形态**（堆镜像 diff 的真实槽位 +
--      登记表路径）。
--   2. s_crc = CRC32(当帧 st 行文本以 "\n" 连接)、d_crc = CRC32(当帧 out 行文本以
--      "\n" 连接) = **序列化自述口径**（快照 CRC 锚在行文本上）。B6 换堆遍历：
--      A 方案同一次遍历对真状态镜像产 CRC。
--   3. 键遍历序：数字键在前（按值升序）、字符串键在后（按字典序）——纯样机口径
--      自洽即可，与未来 A 方案对拍无关。
--
-- 值域：number / string / boolean（string 以 str variant 表达）；table 递归，
-- 路径拼接：数字键 "[i]"（任意层）、字符串键根层直书、深层 ".key"。其余值类型
-- （function/userdata 等）记 err 行并跳过；循环引用（visiting 路径集检出）记
-- err 行并跳过该子树——走查不中断，状态尽力取全。
local fr = require("fr")
local bit = require("bit")   -- LuaJIT 自带；产出为有符号 int32（Task 1 预警）

local walker = {}

-- CRC32 查表（多项式 0xEDB88320）：模块载入时一次性生成
local CRC_TABLE = {}
for i = 0, 255 do
    local c = i
    for _ = 1, 8 do
        if bit.band(c, 1) ~= 0 then
            c = bit.bxor(bit.rshift(c, 1), 0xEDB88320)
        else
            c = bit.rshift(c, 1)
        end
    end
    CRC_TABLE[i] = c
end

-- 标准 CRC32（init/xorout 0xFFFFFFFF）。bit 库产出有符号 int32——末尾
-- % 4294967296 归一到 u32 域（负数取模在 Lua 中返回非负余数）。空输入 = 0。
function walker.crc32(text)
    local crc = 0xFFFFFFFF
    for i = 1, #text do
        crc = bit.bxor(bit.rshift(crc, 8), CRC_TABLE[bit.band(bit.bxor(crc, text:byte(i)), 0xFF)])
    end
    return bit.bxor(crc, 0xFFFFFFFF) % 4294967296
end

-- 值 → render_line 的 variant 值形（注意：token 化由 fr.render_line 统一做，
-- 这里只做字符串 → {s} 表的值形转换，fr.lua 约定 table.v[1] 为串）
local function variant(v)
    if type(v) == "string" then return { v } end
    return v                              -- number / boolean 原样
end

-- 路径拼接：根层字符串键直书（"hero"），深层 ".key"；数字键恒 "[i]"
local function join_key(base, k)
    if type(k) == "number" then
        return base .. "[" .. tostring(k) .. "]"
    elseif base == "" then
        return k
    end
    return base .. "." .. k
end

-- 排序键深度优先遍历：每层收集后分型各自 sort（数字按值、字符串按字典序，
-- 数字在前——见文件头样机口径 3）
local function collect_keys(t)
    local nums, strs, keys = {}, {}, {}
    for k in pairs(t) do
        if type(k) == "number" then nums[#nums + 1] = k
        elseif type(k) == "string" then strs[#strs + 1] = k end
    end
    table.sort(nums)
    table.sort(strs)
    for _, k in ipairs(nums) do keys[#keys + 1] = k end
    for _, k in ipairs(strs) do keys[#keys + 1] = k end
    return keys
end

-- state → st 行文本列表, err 行文本列表（环 / 非法值类型；语义见文件头）
function walker.st_rows(state)
    local rows, errs = {}, {}
    local visiting = {}                  -- table → true（当前 DFS 路径上，检出环）
    local function walk(t, base)
        visiting[t] = true
        for _, k in ipairs(collect_keys(t)) do
            local v = t[k]
            local path = join_key(base, k)
            local tv = type(v)
            if tv == "table" then
                if visiting[v] then
                    errs[#errs + 1] = fr.render_line("err", { what = "walker: 循环引用于 " .. path })
                else
                    walk(v, path)
                end
            elseif tv == "number" or tv == "boolean" or tv == "string" then
                rows[#rows + 1] = fr.render_line("st", { obj = 0, key = path, val = variant(v) })
            else
                errs[#errs + 1] = fr.render_line("err", { what = "walker: 不支持的值类型 " .. tv .. " 于 " .. path })
            end
        end
        visiting[t] = nil
    end
    walk(state, "")
    return rows, errs
end

return walker
