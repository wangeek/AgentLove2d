// run.mjs —— Phaser 探针驱动：取证材料（docs/plans/2026-11-27-multi-frontend-phaser.md
// 里"时间基准""捕获挂点"两节的数字就是它跑出来的）。
//
// 回答两个决定 capture.js 设计的问题：
//   Q1 步长：Phaser 的 update(time, delta) 能不能钉成固定、可复现的序列？
//   Q2 挂点：要捕获"画了什么"，挂在哪一层才能同时拿到对象身份和最终屏幕几何？
//
// 做法：本地 http 服务（供探针页取 Phaser 本体与主仓 codec）→ 无头浏览器打开探针页
// → 页面把结果 POST 回来 → 这里打印。
//
// 用法（仓库根）：
//   node docs/probes/phaser/run.mjs [帧数=240] [auto|manual] [default|softgl] [页面] [Hz=60] [层]
//     页面：timestep.html（默认，Q1）| capture-hooks.html（Q2）
//     层  ：仅 capture-hooks 早期版本用；默认即可
//   例：node docs/probes/phaser/run.mjs 240 manual default timestep.html 60
//       node docs/probes/phaser/run.mjs 8   manual default capture-hooks.html
//
// 环境变量（都有缺省，缺省是本机实测形态）：
//   FR_BROWSER   浏览器可执行文件（Chromium 系；缺省找 Edge/Chrome 的常见安装位）
//   FR_PHASER    phaser.min.js 路径（缺省：系统临时目录下的 fr_phaser_probe/phaser.min.js，
//                没有就从官方 CDN 取 npm latest——只取单文件，不装 npm 包）
//
// 零 npm 依赖（node >= 18）。无头浏览器是 GUI 程序，stdout 不可靠，所以走 http 回报。

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { mkdtempSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..", "..");        // docs/probes/phaser → 仓库根

const FRAMES = Number(process.argv[2] || 240);
const MODE = process.argv[3] || "auto";                     // auto | manual
const SOFT_GL = process.argv[4] === "softgl";
const PAGE = process.argv[5] || "timestep.html";
const HZ = Number(process.argv[6] || 60);
const LAYER = process.argv[7] || "nodes";

// ---- 浏览器：不写死一台机器的路径 ------------------------------------
const BROWSER_CANDS = [
  process.env.FR_BROWSER,
  String.raw`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`,
  String.raw`C:\Program Files\Microsoft\Edge\Application\msedge.exe`,
  String.raw`C:\Program Files\Google\Chrome\Application\chrome.exe`,
  String.raw`C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`,
  "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter(Boolean);
const EDGE = BROWSER_CANDS.find((p) => existsSync(p));
if (!EDGE) {
  console.error("找不到浏览器：请设 FR_BROWSER=<chromium 系浏览器可执行文件>");
  process.exit(2);
}

// ---- Phaser 本体：单文件，按需取 ------------------------------------
const PHASER_VERSION = "4.2.1";          // 本仓取证时的版本；换版本请重跑两份探针
const PHASER_DIR = process.env.FR_PHASER
  ? path.dirname(process.env.FR_PHASER) : path.join(tmpdir(), "fr_phaser_probe");
const PHASER_FILE = process.env.FR_PHASER
  ? process.env.FR_PHASER : path.join(PHASER_DIR, "phaser.min.js");

async function ensurePhaser() {
  if (existsSync(PHASER_FILE)) return;
  mkdirSync(PHASER_DIR, { recursive: true });
  const url = `https://cdn.jsdelivr.net/npm/phaser@${PHASER_VERSION}/dist/phaser.min.js`;
  process.stderr.write(`取 Phaser ${PHASER_VERSION}：${url}\n`);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`下载失败 HTTP ${res.status}`);
  writeFileSync(PHASER_FILE, Buffer.from(await res.arrayBuffer()));
}

await ensurePhaser();

let doneResolve;
const done = new Promise((r) => { doneResolve = r; });
let report = null;

const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  try {
    if (req.method === "POST" && url.pathname === "/report") {
      let body = "";
      for await (const c of req) body += c;
      report = JSON.parse(body);
      res.writeHead(204).end();
      return;
    }
    if (req.method === "POST" && url.pathname === "/done") {
      res.writeHead(204).end();
      doneResolve();
      return;
    }
    if (req.method === "GET") {
      if (url.pathname === "/") {
        res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        res.end(await readFile(path.join(HERE, PAGE)));
        return;
      }
      const f = path.basename(url.pathname);              // 只取文件名，防目录穿越
      if (f === "phaser.min.js") {
        res.writeHead(200, { "content-type": "text/javascript" });
        res.end(await readFile(PHASER_FILE));
        return;
      }
      if (f === "codec.mjs" || f === "fr_table.mjs") {
        res.writeHead(200, { "content-type": "text/javascript" });
        res.end(await readFile(path.join(REPO, "render", "js", f)));
        return;
      }
      res.writeHead(404).end();
      return;
    }
    res.writeHead(405).end();
  } catch (e) {
    res.writeHead(500).end(String(e));
  }
});

await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;
console.log(`探针：${FRAMES} 帧，mode=${MODE}，${HZ}Hz，${SOFT_GL ? "软件 GL" : "默认 GL"}，`
            + `页面=${PAGE}，端口 ${port}`);

const profile = mkdtempSync(path.join(tmpdir(), "fr-phaser-prof-"));
const args = [
  "--headless=new", "--no-first-run", "--no-default-browser-check",
  "--disable-extensions", "--disable-background-networking", "--mute-audio",
  `--user-data-dir=${profile}`,
];
if (SOFT_GL) args.push("--use-gl=swiftshader", "--enable-unsafe-swiftshader");
args.push(`http://127.0.0.1:${port}/?frames=${FRAMES}&mode=${MODE}&hz=${HZ}&layer=${LAYER}`);
const child = spawn(EDGE, args, { stdio: ["ignore", "pipe", "pipe"] });
let stderr = "";
child.stderr.on("data", (b) => { stderr += b.toString(); });
const timer = setTimeout(doneResolve, 120000);
await done;
clearTimeout(timer);
child.kill();
server.close();

if (!report) {
  console.error("页面没有回报（浏览器没起来，或页面脚本报错）：\n" + stderr.slice(-1200));
  process.exit(1);
}
if (report.seriesHash !== undefined) {
  // timestep.html：一行紧凑输出，便于并排比较多次运行
  const d = report.delta, w = report.wall, h = report.hook;
  console.log(
    `${MODE.padEnd(6)} ${String(HZ).padStart(3)}Hz  帧=${report.frames}  ` +
    `delta ${d.min}~${d.max}（取值 ${Object.keys(report.deltaDistinct).length} 种）  ` +
    `time精确=${report.timeStepExact}` +
    `（最大偏差 delta=${report.maxDev.delta.toExponential(1)} time=${report.maxDev.time.toExponential(1)}）  ` +
    `序列哈希=${report.seriesHash}  ` +
    `墙钟 ${w.median}~${w.max}ms  钩子 list=${h.listRender} renderer=${h.rendererRender} obj=${h.prerender}`);
} else if (report.unique) {
  // capture-hooks.html：对象层上下文 × 节点层几何 的逐笔对账
  console.log(`记录 ${report.records} 条（稳态）；失配 ${report.mismatches} 条`);
  const pad = (s, n) => String(s).padEnd(n);
  const line = (cells) => pad(cells[0], 14) + pad(cells[1], 30) + pad(cells[2], 9)
    + pad(cells[3], 10) + pad(cells[4], 7) + cells[5];
  console.log(line(["节点", "对象", "经参数", "经上下文", "结果", "说明"]));
  console.log("-".repeat(110));
  for (const u of report.unique) {
    const verdict = u.ok === true ? "OK" : u.ok === false ? "失配" : "?";
    console.log(line([u.node, u.go, u.viaArg ? "是" : "-", u.viaCtx ? "是" : "-",
                      verdict, u.why]));
  }
  console.log(`VERDICT: ${report.mismatches === 0 ? "PASS" : "FAIL"}`);
} else {
  console.log(JSON.stringify(report, null, 1));
}
