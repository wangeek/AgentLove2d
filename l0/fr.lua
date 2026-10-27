-- l0/fr.lua —— FR 行文本编码器（canonical .fr 文本，spec §6；Lua 5.1/LuaJIT）
-- 对拍权威：tools/fr_codec_gen.py 的 render_line（B3b Task 1 跨语言逐字节对拍锚，
-- 见 tests/test_l0.py::test_selftest_cross_language）。
--
-- asset 行字段约定（Task 1 定死）：
--   kind 用数字口径值（0=image 1=canvas 2=quad 3=font；名值对由 fr_ops.lua 的
--   ops.kinds 承载，单一真源不手抄）；image/font 的字节载荷以 fields.data_hex
--   （小写十六进制串）直接表达——gen_python 生成的 fr_samples.lua 即此形；
--   代码侧若持原始字节串可先经 fr.tohex(fields.data) 转 hex。空载荷（空串）
--   render 记 "-"，对齐 Python `hexed if hexed else "-"`（bytes.hex()=="" 分支）。
local fr = {}

-- 字符串转义：与 Python _esc 同构——\ " \n \r \t 转义；其余 C0 与 DEL、
-- U+2028/U+2029 拒收（canonical 文本行不容纳未转义控制字符，防行撕裂）。
-- C0 检查逐字节做（不用字符类 pattern——LuaJIT 下源码 `\0` 转义进 pattern 不可靠）。
function fr.esc(s)
    for i = 1, #s do
        local b = s:byte(i)
        if (b < 32 and b ~= 9 and b ~= 10 and b ~= 13) or b == 127 then
            error("fr: 控制字符禁入 canonical 文本")
        end
    end
    if s:find("\226\128\168", 1, true) or s:find("\226\128\169", 1, true) then
        error("fr: U+2028/U+2029 禁入 canonical 文本")
    end
    s = s:gsub("\\", "\\\\")
    s = s:gsub('"', '\\"')
    s = s:gsub("\n", "\\n")
    s = s:gsub("\r", "\\r")
    s = s:gsub("\t", "\\t")
    return s
end

-- 量化域文本：%.6f 定长。NaN/Inf 拒收，对齐 Python qf 的数值域纪律。
-- （渲染前不再单独 qf：qf 后再 %.6f 与直接 %.6f 文本等价，值域归一由消费端
--  parse 侧 qf 承担——与 Python render_line 的 `_render_tok` 同理。）
function fr.f(v)
    if v ~= v or v == math.huge or v == -math.huge then
        error("fr: NaN/Inf 禁入数值域")
    end
    return string.format("%.6f", v)
end

-- bytes 字符串 → 小写 hex（对齐 Python bytes.hex()；空串返回空串）
function fr.tohex(data)
    return (data:gsub(".", function(c) return ("%02x"):format(c:byte()) end))
end

-- variant → token 对：num <%.6f> / str "<引号串>" / bool 0|1。
-- Lua 值形约定（fr_samples.lua 由 gen_python 按此生成）：
--   number = num variant；boolean = bool variant；table = str variant（v[1] 为串）。
function fr.tok_variant(v)
    local tv = type(v)
    if tv == "boolean" then return v and "bool 1" or "bool 0" end
    if tv == "number" then return "num " .. fr.f(v) end
    if tv == "table" then return 'str "' .. fr.esc(v[1]) .. '"' end
    error("fr: 非法 variant: " .. tostring(v))
end

-- OPS 元数据由 gen_python 生成（l0/fr_ops.lua，表驱动单一真源）。模块直接 return
-- ops 表：meta[op] = { fields = {{名,类型},...}, variadic = 'args...'/'payload...'/nil,
-- section = 'head'/'in'/'log'/'out'/'end' }；meta.kinds = asset kind 名值对
-- （"kinds" 键与 op 名空间共存，现表无此名 op——生成器若引入需换包裹结构）。
local meta = require("fr_ops")

-- kinds 生成形为 名字→口径值；render_asset 按 数字→名字 反查，载入时反转一次
-- （对齐 Python _ASSET_KIND_NAMES 的方向）。
local kind_names = {}
for name, num in pairs(meta.kinds) do
    kind_names[num] = name
end

local put = {
    u8    = function(t, v) t[#t + 1] = tostring(v) end,
    u32   = function(t, v) t[#t + 1] = tostring(v) end,
    f32   = function(t, v) t[#t + 1] = fr.f(v) end,
    f64   = function(t, v) t[#t + 1] = fr.f(v) end,
    rgba8 = function(t, v) t[#t + 1] = ("%d %d %d %d"):format(v[1], v[2], v[3], v[4]) end,
    str   = function(t, v) t[#t + 1] = '"' .. fr.esc(v) .. '"' end,
    ["f32[]"] = function(t, v)
        t[#t + 1] = tostring(#v)
        for _, p in ipairs(v) do t[#t + 1] = fr.f(p[1]); t[#t + 1] = fr.f(p[2]) end
    end,
}

-- asset 行（kind 用名字；u32 记 tostring 整数；浮点 %.6f；hex 载荷空记 "-"）
function fr.render_asset(f)
    local kindname = kind_names[f.kind] or error("fr: asset kind 非法: " .. tostring(f.kind))
    local t = { "asset", kindname, tostring(f.id) }
    if f.kind == 1 then        -- canvas：宽高
        t[#t + 1] = tostring(f.w)
        t[#t + 1] = tostring(f.h)
    elseif f.kind == 2 then    -- quad：x y w h sw sh 六个 f32
        for _, k in ipairs({ "x", "y", "w", "h", "sw", "sh" }) do
            t[#t + 1] = fr.f(f[k])
        end
    else                       -- image / font：宽高或字号 + hex 载荷
        if f.kind == 0 then
            t[#t + 1] = tostring(f.w)
            t[#t + 1] = tostring(f.h)
        else
            t[#t + 1] = fr.f(f.size)
        end
        local hex = f.data_hex or fr.tohex(f.data or "")
        t[#t + 1] = (hex ~= "" and hex or "-")
    end
    return table.concat(t, " ")
end

-- 行 → canonical 文本（空格分隔 token；asset 走 render_asset，与 Python render_line 同构）
function fr.render_line(op, fields)
    local spec = meta[op] or error("fr: 未知 op: " .. tostring(op))
    if op == "asset" or spec.variadic == "payload..." then
        return fr.render_asset(fields)
    end
    local t = { op }
    for _, f in ipairs(spec.fields) do
        local name, typ = f[1], f[2]
        if typ == "variant" then
            t[#t + 1] = fr.tok_variant(fields[name])
        else
            local fn = put[typ] or error("fr: 未知类型: " .. tostring(typ))
            fn(t, fields[name])
        end
    end
    if spec.variadic == "args..." then
        local arr = fields.args
        t[#t + 1] = tostring(#arr)
        for _, v in ipairs(arr) do t[#t + 1] = fr.tok_variant(v) end
    end
    return table.concat(t, " ")
end

-- 自检：24 条生成样例逐行 render 到 stdout（tests/test_l0.py 与 Python 侧逐字节对拍）
function fr.selftest()
    local samples = require("fr_samples")
    for _, s in ipairs(samples) do
        print(fr.render_line(s.op, s.fields))
    end
end

return fr
