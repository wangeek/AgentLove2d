// codec.mjs —— FR canonical 文本编解码（JS 侧单一真源，手写；勿在其他仓改）
//
// 分工：**数据面**在 fr_table.mjs（由 tables/cmd.tbl 生成）；本文件只有逻辑，
// 且逐字段驱动（按表里的字段序与类型渲染/解析），不按 op 硬编码——加 op 只需
// 改表 + 重生成表模块，本文件不动。
//
// v0 覆盖范围（有意收窄，先说清）：
//   - **只做文本**（canonical `.fr`）：回放读文本、捕获写文本。`.frb` 二进制容器
//     不在 v0（以后要就让生成器补字节层）。
//   - **只做 full 档**：`:px` 短名/省略形不在 v0（`fr_prec` 可先把流转成 full）。
//   - **不做增量展开**：含 CP/SET/INS/DEL/MOVE/PLACE/POSE/ENTER/EXIT 的流（帧间
//     增量编辑）需要展开器，v0 只识别、不展开——conformance 会明确报"跳过"。
//
// 与 Python 侧逐字节对齐的三处细节（都踩过才知道）：
//   1. 浮点先 qf 到 6 位小数域再格式化（Python "%.6f" % qf(v)）；
//   2. -0 要输出 "-0.000000"（JS 的 toFixed 不给零带符号，Python 给）；
//   3. 字符串转义集固定 \\ \" \n \r \t，其余 C0 与 U+2028/2029 拒收。

import {
  OPS, OP_ORDER, TBL_SHA256, ASSET_KIND, ASSET_KIND_NAMES, VARIANT,
} from "./fr_table.mjs";

export { OPS, OP_ORDER, TBL_SHA256, ASSET_KIND, ASSET_KIND_NAMES, VARIANT };

export class FrCodecError extends Error {}

// ---- 数值域 ----------------------------------------------------------

/** 量化到 %.6f 语义域（NaN/Inf 拒收——与 Python 侧 qf 同律）。 */
export function qf(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new FrCodecError(`NaN/Inf 禁入数值域: ${v}`);
  }
  const q = Number(v.toFixed(6));
  return Object.is(q, -0) ? 0 : q;
}

/** 浮点 → 定长 6 位文本；-0 保留符号（Python "%.6f" % -0.0 输出负号）。 */
function fmtF(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new FrCodecError(`NaN/Inf 禁入数值域: ${v}`);
  }
  if (Object.is(v, -0)) return "-0.000000";
  const q = Number(v.toFixed(6));
  if (Object.is(q, -0)) return "-0.000000";
  return q.toFixed(6);
}

function fmtInt(v, what) {
  const n = Number(v);
  if (!Number.isInteger(n)) throw new FrCodecError(`${what} 需整数: ${v}`);
  return String(n);
}

// ---- 字符串 ----------------------------------------------------------

export function escapeStr(s) {
  let out = "";
  for (const ch of s) {
    if (ch === "\\") out += "\\\\";
    else if (ch === '"') out += '\\"';
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else {
      const cp = ch.codePointAt(0);
      if (cp < 0x20 || cp === 0x2028 || cp === 0x2029) {
        throw new FrCodecError(
          `字符码位 U+${cp.toString(16).toUpperCase().padStart(4, "0")} 拒收` +
          "：canonical 文本不容纳未转义控制字符");
      }
      out += ch;
    }
  }
  return out;
}

export function unescapeStr(s) {
  let out = "";
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c !== "\\") { out += c; continue; }
    if (i + 1 >= s.length) throw new FrCodecError("字符串以孤立反斜杠结尾");
    const n = s[++i];
    if (n === "\\") out += "\\";
    else if (n === '"') out += '"';
    else if (n === "n") out += "\n";
    else if (n === "r") out += "\r";
    else if (n === "t") out += "\t";
    else throw new FrCodecError(`未知转义序列: \\${n}`);
  }
  return out;
}

// ---- 字段渲染 --------------------------------------------------------

function renderVariant(v) {
  if (!v || typeof v !== "object" || !("tag" in v)) {
    throw new FrCodecError(`variant 需 {tag,value}: ${JSON.stringify(v)}`);
  }
  if (v.tag === "num") return ["num", fmtF(v.value)];
  if (v.tag === "str") return ["str", '"' + escapeStr(v.value) + '"'];
  if (v.tag === "bool") return ["bool", v.value ? "1" : "0"];
  throw new FrCodecError(`variant tag 非法: ${v.tag}`);
}

function renderTok(typ, v) {
  switch (typ) {
    case "u8":
    case "u32":
      return [fmtInt(v, typ)];
    case "f32":
    case "f64":
      return [fmtF(v)];
    case "rgba8":
      return [v[0], v[1], v[2], v[3]].map((c) => fmtInt(c, "rgba8"));
    case "str":
      return ['"' + escapeStr(v) + '"'];
    case "f32[]": {
      const toks = [String(v.length)];
      for (const [x, y] of v) { toks.push(fmtF(x)); toks.push(fmtF(y)); }
      return toks;
    }
    case "variant":
      return renderVariant(v);
    default:
      throw new FrCodecError(`未知类型: ${typ}`);
  }
}

function hexOf(data) {
  if (data == null) return "";
  if (typeof data === "string") return data === "-" ? "" : data.toLowerCase();
  let s = "";
  for (const b of data) s += b.toString(16).padStart(2, "0");
  return s;
}

function renderAsset(fields) {
  const kind = fields.kind;
  const name = ASSET_KIND_NAMES[kind];
  if (name === undefined) throw new FrCodecError(`asset kind 非法: ${kind}`);
  const toks = ["asset", name, fmtInt(fields.id, "asset id")];
  if (kind === ASSET_KIND.CANVAS) {
    toks.push(fmtInt(fields.w, "canvas w"), fmtInt(fields.h, "canvas h"));
  } else if (kind === ASSET_KIND.QUAD) {
    for (const k of ["x", "y", "w", "h", "sw", "sh"]) toks.push(fmtF(fields[k]));
  } else {
    if (kind === ASSET_KIND.IMAGE) {
      toks.push(fmtInt(fields.w, "image w"), fmtInt(fields.h, "image h"));
    } else {
      toks.push(fmtF(fields.size));
    }
    if (fields.font_src) {          // font 字节引用形态：=srcid
      toks.push("=" + fmtInt(fields.font_src, "font_src"));
      return toks;
    }
    const hex = hexOf(fields.data);
    toks.push(hex === "" ? "-" : hex);
  }
  return toks;
}

/** 行 → canonical 文本。fields 形状与 fr_table 的字段名一致。 */
export function renderLine(op, fields) {
  const spec = OPS[op];
  if (!spec) throw new FrCodecError(`未知 op: ${op}`);
  if (spec.variadic === "payload...") return renderAsset(fields).join(" ");
  const toks = [op];
  for (const [name, typ] of spec.fields) toks.push(...renderTok(typ, fields[name]));
  if (spec.variadic === "args...") {
    const args = fields.args || [];
    toks.push(String(args.length));
    for (const v of args) toks.push(...renderVariant(v));
  }
  return toks.join(" ");
}

// ---- 解析 ------------------------------------------------------------

/** 文本行 → token 列表；引号串为单 token（含两侧引号，转义不拆分）。 */
export function tokenize(line) {
  const toks = [];
  let i = 0;
  const n = line.length;
  while (i < n) {
    const c = line[i];
    if (c === " " || c === "\t" || c === "\r") { i++; continue; }
    if (c === '"') {
      let j = i + 1;
      while (j < n) {
        if (line[j] === "\\") { j += 2; continue; }
        if (line[j] === '"') break;
        j++;
      }
      if (j >= n) throw new FrCodecError("字符串 token 未闭合");
      toks.push(line.slice(i, j + 1));
      i = j + 1;
    } else {
      let j = i;
      while (j < n && line[j] !== " " && line[j] !== "\t" && line[j] !== "\r") j++;
      toks.push(line.slice(i, j));
      i = j;
    }
  }
  return toks;
}

function parseVariant(take) {
  const tag = take();
  if (tag === "num") return { tag: "num", value: qf(parseFloat(take())) };
  if (tag === "str") return { tag: "str", value: unescapeStr(unquote(take())) };
  if (tag === "bool") return { tag: "bool", value: take() !== "0" };
  throw new FrCodecError(`variant tag 非法: ${tag}`);
}

function unquote(tok) {
  if (!(tok.startsWith('"') && tok.endsWith('"')) || tok.length < 2) {
    throw new FrCodecError(`期望带引号字符串: ${tok}`);
  }
  return tok.slice(1, -1);
}

function parseTok(typ, take) {
  switch (typ) {
    case "u8":
    case "u32": {
      const tok = take();
      const n = Number(tok);
      if (!Number.isInteger(n)) throw new FrCodecError(`${typ} 需整数: ${tok}`);
      return n;
    }
    case "f32":
    case "f64":
      return qf(parseFloat(take()));
    case "rgba8":
      return [0, 0, 0, 0].map(() => Number(take()));
    case "str":
      return unescapeStr(unquote(take()));
    case "f32[]": {
      const n = Number(take());
      if (!Number.isInteger(n) || n < 0) throw new FrCodecError(`f32[] 点数非法: ${n}`);
      const pts = [];
      for (let i = 0; i < n; i++) pts.push([qf(parseFloat(take())), qf(parseFloat(take()))]);
      return pts;
    }
    case "variant":
      return parseVariant(take);
    default:
      throw new FrCodecError(`未知类型: ${typ}`);
  }
}

function parseAsset(toks, pos) {
  let p = pos;
  const take = () => {
    if (p >= toks.length) throw new FrCodecError("asset 行 token 不足");
    return toks[p++];
  };
  const name = take();
  const kind = ASSET_KIND_NAMES.indexOf(name);
  if (kind < 0) throw new FrCodecError(`asset kind 名非法: ${name}`);
  const fields = { kind, id: Number(take()) };
  if (kind === ASSET_KIND.IMAGE) {
    fields.w = Number(take());
    fields.h = Number(take());
    fields.data = take();
  } else if (kind === ASSET_KIND.CANVAS) {
    fields.w = Number(take());
    fields.h = Number(take());
  } else if (kind === ASSET_KIND.QUAD) {
    for (const k of ["x", "y", "w", "h", "sw", "sh"]) fields[k] = qf(parseFloat(take()));
  } else {
    fields.size = qf(parseFloat(take()));
    const tok = take();
    if (tok.startsWith("=")) {
      fields.font_src = Number(tok.slice(1));
      fields.data = "";
    } else {
      fields.data = tok === "-" ? "" : tok;
    }
  }
  return { fields, pos: p };
}

/** canonical 文本 → { op, fields }（renderLine 的逆）。 */
export function parseLine(line) {
  const toks = tokenize(line);
  if (toks.length === 0) throw new FrCodecError("空行");
  const op = toks[0];
  const spec = OPS[op];
  if (!spec) throw new FrCodecError(`未知 op: ${op}`);
  if (spec.variadic === "payload...") {
    const r = parseAsset(toks, 1);
    if (r.pos !== toks.length) throw new FrCodecError(`asset 行尾冗余 token: ${op}`);
    return { op, fields: r.fields };
  }
  let pos = 1;
  const take = () => {
    if (pos >= toks.length) throw new FrCodecError(`${op} 行 token 不足`);
    return toks[pos++];
  };
  const fields = {};
  for (const [name, typ] of spec.fields) fields[name] = parseTok(typ, take);
  if (spec.variadic === "args...") {
    const argc = Number(take());
    if (!Number.isInteger(argc) || argc < 0) throw new FrCodecError(`${op} argc 非法`);
    fields.args = [];
    for (let i = 0; i < argc; i++) fields.args.push(parseVariant(take));
  }
  if (pos !== toks.length) throw new FrCodecError(`${op} 行尾冗余 token`);
  return { op, fields };
}

// ---- d_crc 口径 ------------------------------------------------------

/** 该 op 是否是"绘制行"（算 d_crc 时计入）：out 段且非增量编辑动词。 */
export function isDrawOp(op) {
  const spec = OPS[op];
  return !!spec && spec.section === "out" && !spec.delta;
}

/** 该 op 是否是增量编辑动词（v0 不展开，conformance 会报"不可判定"）。 */
export function isDeltaOp(op) {
  const spec = OPS[op];
  return !!spec && spec.delta;
}

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c >>> 0;
  }
  return t;
})();

/** CRC32（IEEE，zlib 口径：init/xorout 均 0xFFFFFFFF，空输入 = 0）。 */
export function crc32(text) {
  const bytes = new TextEncoder().encode(text);
  let c = 0xFFFFFFFF;
  for (const b of bytes) c = CRC_TABLE[(c ^ b) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}
