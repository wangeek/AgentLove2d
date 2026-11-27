// fr_table.mjs —— FR 命令表数据面（GENERATED，勿手改）
//
// 由 tools/fr_gen/gen_js.py 从 tables/cmd.tbl 生成。改表后重新生成：
//     python -m tools.fr_gen.gen_js
// 逻辑不在这里：渲染/解析见同目录 codec.mjs（逐字段驱动，不按 op 硬编码）。
//
// 段：head 资产与帧头 / in 输入 / log 观测 / out 绘制与编辑 / end 校验和
// delta: true 的 op 属帧间增量编辑动词（表里 status=ext）——它们不是"绘制行"，
//        算 d_crc 时不计入（与 Python 侧 fr_lint 的判据口径一致）。
export const TBL_SHA256 = "24bf782b90ff2d1c0cf1ca17aa1ba220de415aed15ede54612b427cb4717ac60";

export const ASSET_KIND = { IMAGE: 0, CANVAS: 1, QUAD: 2, FONT: 3 };
export const ASSET_KIND_NAMES = ["image", "canvas", "quad", "font"];
export const VARIANT = { NUM: 1, STR: 2, BOOL: 3 };

// op → 规格（键序即表序 = opcode 序）
export const OPS = {
  "dt": { section: "head", fields: [["val", "f32"]], variadic: null, status: "sealed", delta: false },
  "asset": { section: "head", fields: [["kind", "u8"], ["id", "u32"]], variadic: "payload...", status: "draft", delta: false },
  "ev": { section: "in", fields: [["slot", "u32"], ["type", "str"], ["src", "u8"]], variadic: "args...", status: "sealed", delta: false },
  "call": { section: "in", fields: [["slot", "u32"], ["fn", "str"], ["depth", "u8"]], variadic: "args...", status: "sealed", delta: false },
  "timer": { section: "in", fields: [["slot", "u32"], ["id", "u32"]], variadic: null, status: "sealed", delta: false },
  "rngc": { section: "log", fields: [["seed_after", "u32"]], variadic: null, status: "sealed", delta: false },
  "st": { section: "log", fields: [["obj", "u32"], ["key", "str"], ["val", "variant"]], variadic: null, status: "draft", delta: false },
  "err": { section: "log", fields: [["what", "str"]], variadic: null, status: "sealed", delta: false },
  "clear": { section: "out", fields: [["color", "rgba8"]], variadic: null, status: "sealed", delta: false },
  "draw": { section: "out", fields: [["tex", "u32"], ["quad", "u32"], ["x", "f32"], ["y", "f32"], ["rot", "f32"], ["sx", "f32"], ["sy", "f32"], ["ox", "f32"], ["oy", "f32"], ["color", "rgba8"]], variadic: null, status: "sealed", delta: false },
  "print": { section: "out", fields: [["font", "u32"], ["text", "str"], ["x", "f32"], ["y", "f32"], ["rot", "f32"], ["sx", "f32"], ["sy", "f32"], ["color", "rgba8"]], variadic: null, status: "sealed", delta: false },
  "rect": { section: "out", fields: [["mode", "u8"], ["x", "f32"], ["y", "f32"], ["w", "f32"], ["h", "f32"], ["rx", "f32"], ["ry", "f32"], ["width", "f32"], ["color", "rgba8"]], variadic: null, status: "sealed", delta: false },
  "line": { section: "out", fields: [["pts", "f32[]"], ["width", "f32"], ["color", "rgba8"]], variadic: null, status: "sealed", delta: false },
  "poly": { section: "out", fields: [["mode", "u8"], ["pts", "f32[]"], ["color", "rgba8"]], variadic: null, status: "sealed", delta: false },
  "circle": { section: "out", fields: [["mode", "u8"], ["x", "f32"], ["y", "f32"], ["r", "f32"], ["seg", "u32"], ["color", "rgba8"]], variadic: null, status: "sealed", delta: false },
  "arc": { section: "out", fields: [["mode", "u8"], ["arctype", "u8"], ["x", "f32"], ["y", "f32"], ["r", "f32"], ["a1", "f32"], ["a2", "f32"], ["seg", "u32"], ["color", "rgba8"]], variadic: null, status: "sealed", delta: false },
  "points": { section: "out", fields: [["pts", "f32[]"], ["size", "f32"], ["color", "rgba8"]], variadic: null, status: "sealed", delta: false },
  "rt": { section: "out", fields: [["target", "u32"]], variadic: null, status: "sealed", delta: false },
  "scissor": { section: "out", fields: [["x", "f32"], ["y", "f32"], ["w", "f32"], ["h", "f32"]], variadic: null, status: "sealed", delta: false },
  "s_crc": { section: "end", fields: [["crc", "u32"]], variadic: null, status: "sealed", delta: false },
  "d_crc": { section: "end", fields: [["crc", "u32"]], variadic: null, status: "sealed", delta: false },
  "CP": { section: "out", fields: [["ref", "u32"]], variadic: null, status: "ext", delta: true },
  "SET": { section: "out", fields: [["asset", "u32"], ["k", "u32"], ["param", "str"], ["val", "f32"]], variadic: null, status: "ext", delta: true },
  "INS": { section: "out", fields: [["pos", "u32"], ["line", "str"]], variadic: null, status: "ext", delta: true },
  "DEL": { section: "out", fields: [["pos", "u32"]], variadic: null, status: "ext", delta: true },
  "MOVE": { section: "out", fields: [["asset", "u32"], ["k", "u32"], ["dx", "f32"], ["dy", "f32"]], variadic: null, status: "ext", delta: true },
  "PLACE": { section: "out", fields: [["asset", "u32"], ["k", "u32"], ["x", "f32"], ["y", "f32"]], variadic: null, status: "ext", delta: true },
  "POSE": { section: "out", fields: [["asset", "u32"], ["k", "u32"], ["line", "str"]], variadic: null, status: "ext", delta: true },
  "ENTER": { section: "out", fields: [["line", "str"]], variadic: null, status: "ext", delta: true },
  "EXIT": { section: "out", fields: [["asset", "u32"], ["k", "u32"]], variadic: null, status: "ext", delta: true },
};

// 表序（=二进制 opcode 序；v0 文本侧只需相对序稳定）
export const OP_ORDER = ["dt", "asset", "ev", "call", "timer", "rngc", "st", "err", "clear", "draw", "print", "rect", "line", "poly", "circle", "arc", "points", "rt", "scissor", "s_crc", "d_crc", "CP", "SET", "INS", "DEL", "MOVE", "PLACE", "POSE", "ENTER", "EXIT"];
