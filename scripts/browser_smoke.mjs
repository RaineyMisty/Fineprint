// Optional real-browser smoke test for the web app. Requires Node >=22 and Chrome; no npm packages.
// Usage: node scripts/browser_smoke.mjs   (env: CHROME_BIN, PYTHON_BIN)
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {mkdtemp, mkdir, writeFile, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const scratch = await mkdtemp(join(tmpdir(), "fineprint-smoke-"));
const artifacts = resolve(root, process.env.BROWSER_ARTIFACT_DIR || "artifacts/browser");
await mkdir(artifacts, {recursive: true});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const port = 8800 + Math.floor(Math.random() * 100), cdp = 9400 + Math.floor(Math.random() * 100);
const server = spawn(process.env.PYTHON_BIN || "python3", ["-m", "fineprint.server", "--port", String(port)], {cwd: root, stdio: "ignore"});
const chrome = spawn(process.env.CHROME_BIN || "google-chrome", ["--headless=new", "--no-sandbox", `--remote-debugging-port=${cdp}`, `--user-data-dir=${scratch}`, "about:blank"], {stdio: "ignore"});
const requests = [];
for (let i = 0; i < 50; i++) { try { await fetch(`http://127.0.0.1:${port}/api/status`); break; } catch { await sleep(200); } }
try {
  let pages;
  for (let i = 0; i < 60 && !pages?.length; i++) { try { pages = (await (await fetch(`http://127.0.0.1:${cdp}/json`)).json()).filter((t) => t.type === "page"); } catch { await sleep(200); } }
  const ws = new WebSocket(pages[0].webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let seq = 0; const waiting = new Map();
  ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); } else if (m.method === "Network.requestWillBeSent") requests.push(m.params.request.url); };
  const cmd = (method, params = {}) => new Promise((r) => { const id = ++seq; waiting.set(id, r); ws.send(JSON.stringify({id, method, params})); });
  const ev = async (expression) => { const r = await cmd("Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true, userGesture: true}); assert.ok(!r.result.exceptionDetails, JSON.stringify(r.result.exceptionDetails)); return r.result.result.value; };
  const until = async (expr, label) => { for (let i = 0; i < 80; i++) { if (await ev(expr)) return; await sleep(100); } assert.fail("Timed out: " + label); };
  const shot = async (name) => writeFile(join(artifacts, name), Buffer.from((await cmd("Page.captureScreenshot", {format: "png"})).result.data, "base64"));
  await cmd("Network.enable");
  for (const [width, tag] of [[1280, "desktop"], [390, "mobile"]]) {
    await cmd("Emulation.setDeviceMetricsOverride", {width, height: 900, deviceScaleFactor: 1, mobile: width < 500});
    await cmd("Page.navigate", {url: `http://127.0.0.1:${port}/`});
    await until("document.querySelectorAll('.sample').length === 3", "samples");
    await shot(`${tag}-1-documents.png`);
    await ev("document.querySelector('.sample').click()");
    await until("!document.getElementById('step-2').hidden && document.querySelectorAll('.rule').length > 0", "rules");
    assert.match(await ev("document.getElementById('backend-card').textContent"), /Offline rule reader/);
    await ev("document.querySelectorAll('.rule')[2].click()");
    assert.ok(await ev("document.querySelectorAll('mark.on').length > 0"), "selected rule highlights its source");
    await shot(`${tag}-2-rules.png`);
    await ev("document.getElementById('to-result').click()");
    assert.match(await ev("document.getElementById('verdict').textContent"), /overcharged \$120/);
    assert.ok(await ev("document.querySelectorAll('.line').length === 2"));
    await ev("document.querySelector('.cite button').click()");
    assert.ok(await ev("document.getElementById('clause-dialog').open"), "citation opens clause");
    await ev("document.getElementById('clause-dialog').close()");
    assert.ok(await ev("document.documentElement.scrollWidth <= innerWidth"), "no horizontal overflow");
    await shot(`${tag}-3-result.png`);
  }
  const external = requests.filter((u) => !u.startsWith(`http://127.0.0.1:${port}/`) && !u.startsWith("data:") && !u.startsWith("chrome-extension:") && !u.startsWith("blob:") && u !== "about:blank");
  assert.deepEqual(external, [], "no external requests");
  console.log("browser smoke passed; screenshots in", artifacts);
} finally {
  chrome.kill(); server.kill(); await rm(scratch, {recursive: true, force: true}).catch(() => {});
}
process.exit(0);
