#!/usr/bin/env node
// Render a motion briefing: open video/motion/index.html in headless Chrome, step every frame with seek(f), and encode the frames with
// the normalized narration and chapters. Usage: motion_render.mjs <project> [--stills 513,759] [--check] [--jobs N]
//   --stills  writes only those frames as video/stills/fNNNNN.png: a quick look at the layout without a render.
//   --check   seeks every scene's last frame and writes video/check-layout/sNN.png and report.json listing blocks that leave the
//             scene, overlap each other, or hold text wider or taller than their box. Exit code 3 when anything is found.
//   --jobs N  renders N frame ranges in parallel Chrome processes and joins them without re-encoding (default: half the cores, at
//             most 4; VB_JOBS overrides).
// "@name" in a step scene's focus, frame or cursor reads shots/<shot>.regions.json, see references/outline.md.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const P = path.resolve(process.argv[2] || ".");
const args = process.argv.slice(3);
const value = (flag) => { const i = args.indexOf(flag); return i < 0 ? null : args[i + 1] ?? ""; };
const STILLS = value("--stills") !== null ? String(value("--stills")).split(",").filter(Boolean).map(Number) : null;
const CHECK = args.includes("--check");
const JOBS = Math.max(1, Math.min(8, Number(value("--jobs") || process.env.VB_JOBS || Math.min(4, Math.floor(os.cpus().length / 2)) || 1)));
const CHROME = process.env.VB_CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const timeline = JSON.parse(fs.readFileSync(path.join(P, "video/motion/timeline.json"), "utf8"));
const plan = JSON.parse(fs.readFileSync(path.join(P, "plan.json"), "utf8"));
const assetsRoot = path.join(P, "assets");

// focus gets room around the element, frame hugs it, cursor points at its middle; all are fractions of the screenshot.
function resolveRegions(slides) {
  for (const s of slides) {
    if (s.t !== "step" || !s.shot) continue;
    const file = path.join(P, "shots", s.shot.replace(/\.[a-z]+$/i, "") + ".regions.json");
    const boxes = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {};
    const shape = {
      focus: (b) => { const dx = b[2] * 0.35 + 0.03, dy = b[3] * 0.35 + 0.03; return [Math.max(0, b[0] - dx), Math.max(0, b[1] - dy), Math.min(1, b[2] + 2 * dx), Math.min(1, b[3] + 2 * dy)]; },
      frame: (b) => [b[0] - 0.006, b[1] - 0.008, b[2] + 0.012, b[3] + 0.016],
      cursor: (b) => [b[0] + b[2] / 2, b[1] + b[3] / 2],
    };
    for (const key of Object.keys(shape)) for (const region of Object.keys(s[key] || {})) {
      const v = s[key][region];
      if (typeof v !== "string" || !v.startsWith("@")) continue;
      if (!boxes[v.slice(1)]) throw new Error(s.shot + ": no region " + v + " in " + path.basename(file));
      s[key][region] = shape[key](boxes[v.slice(1)]);
    }
  }
  return slides;
}
const slides = resolveRegions(structuredClone(plan.slides));
const themeName = plan.theme || "paper";
if (!["paper", "terminal", "studio"].includes(themeName)) throw new Error("Unknown theme: " + themeName);
const href = (file) => pathToFileURL(file).href;
const theme = '<link rel="stylesheet" href="' + href(path.join(SKILL, "assets/themes", themeName + ".css")) + '">';
const font = process.env.VB_FONT || path.join(process.env.XDG_CACHE_HOME || path.join(os.homedir(), ".cache"), "video-briefing/fonts/NotoSansKR.ttf");
if (!fs.existsSync(font)) throw new Error("Font missing: run download_models.py or set VB_FONT");
const fontCSS = '<style>@font-face{font-family:"VB Sans";src:url(' + JSON.stringify(href(font)) + ');font-display:block}</style>';
const data = { timeline, plan: { slides }, assets: { root: href(assetsRoot) }, root: href(P) };
const html = '<!doctype html><html lang="' + (plan.lang === "en" ? "en" : "ko") + '"><head><meta charset="utf-8">' + fontCSS +
  '<link rel="stylesheet" href="' + href(path.join(SKILL, "assets/motion/motion.css")) + '">' + theme +
  '</head><body><div id="stage"></div><script>window.MOTION=' + JSON.stringify(data).replace(/</g, "\\u003c") + '</script><script src="' + href(path.join(SKILL, "assets/motion/motion.js")) + '"></script></body></html>';
const pageFile = path.join(P, "video/motion/index.html");
fs.writeFileSync(pageFile, html);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function openPage(port) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "vb-motion-"));
  const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=" + port, "--remote-debugging-address=127.0.0.1", "--user-data-dir=" + profile, "--no-first-run", "--no-default-browser-check",
    "--disable-background-networking", "--disable-component-update", "--disable-sync", "--metrics-recording-only",
    "--hide-scrollbars", "--force-color-profile=srgb", "--force-device-scale-factor=1", "--disable-gpu-vsync", "--run-all-compositor-stages-before-draw", "about:blank"], { stdio: "ignore" });
  let ws, id = 0;
  const pending = new Map();
  const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
  const close = async () => { try { ws?.close(); } catch {} chrome.kill(); await sleep(400); try { fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch {} };
  try {
    let targets;
    for (let i = 0; i < 80 && !targets; i++) { try { targets = await (await fetch("http://127.0.0.1:" + port + "/json")).json(); } catch { await sleep(150); } }
    if (!targets) throw new Error("Chrome did not start");
    ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
    await new Promise((res, rej) => { ws.addEventListener("open", res, { once: true }); ws.addEventListener("error", rej, { once: true }); });
    ws.addEventListener("message", (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); } });
    await send("Page.enable"); await send("Runtime.enable");
    await send("Emulation.setDeviceMetricsOverride", { width: timeline.width, height: timeline.height, deviceScaleFactor: 1, mobile: false });
    await send("Page.navigate", { url: href(pageFile) });
    for (let i = 0; i < 100; i++) {
      const r = await send("Runtime.evaluate", { expression: "typeof window.seek === 'function' && window.motionReady ? window.motionReady.then(() => 'ready') : 'wait'", awaitPromise: true, returnByValue: true });
      if (r.result?.value === "ready") break;
      if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 400));
      await sleep(100);
    }
    await send("Runtime.evaluate", { expression: "seek(0); document.fonts.ready.then(() => true)", awaitPromise: true });
  } catch (e) { await close(); throw e; }
  const seek = async (f) => {
    const r = await send("Runtime.evaluate", { expression: "seek(" + f + ")", returnByValue: true });
    if (r.exceptionDetails) throw new Error("seek(" + f + ") failed: " + JSON.stringify(r.exceptionDetails).slice(0, 400));
    return r.result.value;
  };
  const shot = async (png) => Buffer.from((await send("Page.captureScreenshot", png ? { format: "png", fromSurface: true } : { format: "jpeg", quality: 92, fromSurface: true })).data, "base64");
  return { send, seek, shot, close };
}
const run = (cmd, argv) => new Promise((res, rej) => spawn(cmd, argv, { stdio: ["ignore", "inherit", "inherit"] }).on("close", (c) => (c === 0 ? res() : rej(new Error(cmd + " exit " + c)))));

// seek() is a pure function of the frame, so ranges render independently; a range starts by drawing its first frame in full.
async function renderRange(a, b, out, port, tag) {
  const page = await openPage(port);
  try {
    const ff = spawn("ffmpeg", ["-v", "error", "-y", "-f", "image2pipe", "-framerate", String(timeline.fps), "-c:v", "mjpeg", "-i", "-",
      "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-an", out], { stdio: ["pipe", "inherit", "inherit"] });
    const done = new Promise((res, rej) => ff.on("close", (code) => (code === 0 ? res() : rej(new Error("ffmpeg exit " + code)))));
    let last = null, captured = 0;
    const t0 = Date.now();
    for (let f = a; f < b; f++) {
      if ((await page.seek(f)) > 0 || !last) { last = await page.shot(false); captured++; }
      if (!ff.stdin.write(last)) await new Promise((res) => ff.stdin.once("drain", res));
      if ((f - a) % 600 === 0) console.log(tag + " frame " + f + "/" + b + " captured " + captured + " " + Math.round((Date.now() - t0) / 1000) + "s");
    }
    ff.stdin.end();
    await done;
    return captured;
  } finally { await page.close(); }
}

async function main() {
  const base = 9400 + Math.floor(Math.random() * 300);
  if (STILLS || CHECK) {
    const page = await openPage(base);
    try {
      if (STILLS) {
        const dir = path.join(P, "video/stills"); fs.mkdirSync(dir, { recursive: true });
        for (const f of STILLS) { await page.seek(f); fs.writeFileSync(path.join(dir, "f" + String(f).padStart(5, "0") + ".png"), await page.shot(true)); }
        console.log(JSON.stringify({ stills: STILLS.length, dir }));
        return;
      }
      const dir = path.join(P, "video/check-layout"); fs.mkdirSync(dir, { recursive: true });
      const report = [];
      for (let i = 0; i < timeline.slides.length; i++) {
        const f = timeline.slides[i].f1 - 1;
        await page.seek(f);
        const r = await page.send("Runtime.evaluate", { expression: "layoutProblems(" + i + ")", returnByValue: true });
        fs.writeFileSync(path.join(dir, "s" + String(i + 1).padStart(2, "0") + ".png"), await page.shot(true));
        report.push({ scene: i + 1, type: slides[i].t, title: slides[i].title, frame: f, problems: r.result?.value || ["layout check failed"] });
      }
      fs.writeFileSync(path.join(dir, "report.json"), JSON.stringify(report, null, 1));
      const count = report.reduce((n, s) => n + s.problems.length, 0);
      for (const s of report) for (const p of s.problems) console.log("LAYOUT scene " + s.scene + " (" + s.type + "): " + p);
      console.log(JSON.stringify({ scenes: report.length, problems: count, dir }));
      if (count) process.exitCode = 3;
    } finally { await page.close(); }
    return;
  }
  const total = timeline.frames / timeline.fps;
  const jobs = Math.min(JOBS, Math.max(1, Math.floor(timeline.frames / 300)));
  const size = Math.ceil(timeline.frames / jobs);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vb-parts-"));
  const t0 = Date.now();
  const parts = Array.from({ length: jobs }, (_, j) => ({ a: j * size, b: Math.min(timeline.frames, (j + 1) * size), out: path.join(dir, "part-" + j + ".mp4") })).filter((p) => p.a < p.b);
  const captured = await Promise.all(parts.map((p, j) => renderRange(p.a, p.b, p.out, base + j * 3, "job " + (j + 1) + "/" + parts.length)));
  fs.writeFileSync(path.join(dir, "parts.txt"), parts.map((p) => "file '" + p.out + "'").join("\n") + "\n");
  await run("ffmpeg", ["-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", path.join(dir, "parts.txt"), "-i", timeline.audio, "-i", timeline.chapters,
    "-map", "0:v", "-map", "1:a", "-map_metadata", "2", "-map_chapters", "2", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ac", "2",
    "-movflags", "+faststart", "-t", total.toFixed(3), timeline.out]);
  fs.rmSync(dir, { recursive: true, force: true });
  console.log(JSON.stringify({ frames: timeline.frames, captured: captured.reduce((x, y) => x + y, 0), jobs: parts.length, seconds: Math.round((Date.now() - t0) / 1000), out: timeline.out }));
}
main().catch((e) => { console.error(e.stack || String(e)); process.exitCode = 1; });
