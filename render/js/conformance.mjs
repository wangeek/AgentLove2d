// conformance.mjs —— 跨实现一致性验收（JS 侧；单一真源，勿在其他仓改）
//
// 它证明的是**契约**而不是"跑起来没报错"：同一份流，JS 侧解析出的语义与
// Python 侧逐字节一致。三条判据：
//   1. 会话头的表指纹 == 本 codec 的表指纹（两端用的是同一张表）
//   2. 每一行 round-trip 逐字节相等（parse → render 必须还原原文）
//   3. 每帧 d_crc == 重算（对绘制行 join("\n") 求 CRC32，口径同 Python 侧）
//
// 用法：node conformance.mjs <a.fr> [b.fr ...]
// 退出码：0 全过；1 有失配；2 用法错误。

import { readFileSync } from "node:fs";
import {
  parseLine, renderLine, isDrawOp, isDeltaOp, crc32, TBL_SHA256,
} from "./codec.mjs";

function fail(msg) {
  console.error(`FAIL  ${msg}`);
  process.exitCode = 1;
}

function checkFile(path) {
  // CRLF 容忍：与 Python 侧 fr_dump 同规矩（读入即归一 LF）
  const text = readFileSync(path, "utf8").replace(/\r\n/g, "\n");
  const lines = text.split("\n");
  if (!lines.length || !lines[0].startsWith("frb1 ")) {
    fail(`${path}: 第 1 行不是 frb1 会话头`);
    return null;
  }

  const head = lines[0].split(" ");
  const sha = head[3];
  const prec = head[6] || "";                     // :prec / +d 等尾 token
  if (sha !== TBL_SHA256) {
    fail(`${path}: 表指纹不符——流 ${sha.slice(0, 12)}… vs 本 codec ${TBL_SHA256.slice(0, 12)}…`);
  }
  const isPx = prec.includes(":px");
  const isDelta = prec.includes("+d");
  if (isPx) {
    console.log(`SKIP  ${path}: :px 档不在 v0 覆盖范围（先用 fr_prec 转 full）`);
    return null;
  }

  let frames = 0, rows = 0, badRows = 0, badCrc = 0, deltaRows = 0;
  let cur = null;                                  // 当前帧的绘制行

  const finish = (frameNo) => {
    if (cur === null) return;
    const end = cur.end;
    const expect = cur.dcrc;
    if (expect === null) {
      fail(`${path}: frame ${frameNo} 缺 d_crc 行`);
      badCrc++;
    } else if (!isDelta) {                         // 增量流要展开器，v0 不算
      const got = crc32(cur.rows.join("\n"));
      if (got !== expect) {
        badCrc++;
        fail(`${path}: frame ${frameNo} d_crc ${expect} ≠ 重算 ${got}`);
      }
    }
    frames++;
  };

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (line === "" || line.startsWith("cmnt ")) continue;

    if (line.startsWith("frame ")) {
      finish(Number(line.slice(6)));
      cur = { no: Number(line.slice(6)), rows: [], dcrc: null };
      continue;
    }
    if (cur === null) continue;                    // 帧外行（会话头之后、首帧之前）

    // 逐行 round-trip：这是"两端格式一致"的最强证据
    let parsed;
    try {
      parsed = parseLine(line);
    } catch (e) {
      badRows++;
      fail(`${path}:${i + 1}: 解析失败 ${e.message}  ← ${line.slice(0, 80)}`);
      continue;
    }
    rows++;
    const back = renderLine(parsed.op, parsed.fields);
    if (back !== line) {
      badRows++;
      fail(`${path}:${i + 1}: round-trip 不一致\n        原 ${line}\n        回 ${back}`);
    }

    if (isDeltaOp(parsed.op)) { deltaRows++; continue; }
    if (parsed.op === "d_crc") { cur.dcrc = parsed.fields.crc; continue; }
    if (isDrawOp(parsed.op)) cur.rows.push(line);
  }
  finish(cur ? cur.no : 0);

  console.log(`      ${path}: ${frames} 帧 / ${rows} 行 round-trip`
              + `${deltaRows ? ` / ${deltaRows} 行增量（v0 不展开）` : ""}`);
  return { frames, rows, badRows, badCrc, deltaRows };
}

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("用法: node conformance.mjs <a.fr> [b.fr ...]");
  process.exit(2);
}

let totalFrames = 0, totalRows = 0, bad = 0;
for (const path of args) {
  const r = checkFile(path);
  if (r) {
    totalFrames += r.frames;
    totalRows += r.rows;
    bad += r.badRows + r.badCrc;
  } else {
    bad += 1;
  }
}

if (bad === 0 && !process.exitCode) {
  console.log(`CONFORMANCE OK  ${args.length} 个流 / ${totalFrames} 帧 / ${totalRows} 行`
              + `  TBL ${TBL_SHA256.slice(0, 12)}…`);
}
