// Optional real-browser integration checks. Requires Node >=22 and Chrome.
// Starts its own disposable local server/browser; adds no npm dependencies.
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {mkdtemp, readFile, mkdir, writeFile, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const scratch = await mkdtemp(join(tmpdir(), "fineprint-smoke-"));
const artifacts = resolve(root, process.env.BROWSER_ARTIFACT_DIR || "artifacts/browser");
let server, chrome, ws, sequence = 0;
const waiting = new Map(), exceptions = [], requests = [];
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(fn, label) {
  for (let i = 0; i < 100; i++) { const value = await fn(); if (value) return value; await pause(100); }
  throw new Error(`Timed out: ${label}`);
}
function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(() => {waiting.delete(id);reject(new Error(`CDP timeout: ${method}`));}, 10000);
    waiting.set(id, {resolve, reject, timeout});
    ws.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const response = await command("Runtime.evaluate", {expression, awaitPromise:true, returnByValue:true, userGesture:true});
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
  return response.result.value;
}
async function click(selector) {
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
}
async function ready(expression, label) { return until(() => evaluate(expression), label); }
async function screenshot(name) {
  const image = await command("Page.captureScreenshot", {format:"png", captureBeyondViewport:false});
  await writeFile(join(artifacts, name), Buffer.from(image.data, "base64"));
}

try {
  let serverOutput = "", serverError = "";
  server = spawn(process.env.PYTHON_BIN || "python3", ["-m", "fineprint.server", "--port", "0"], {cwd:root, stdio:["ignore","pipe","pipe"]});
  server.stdout.on("data", (data) => {serverOutput += data;});
  server.stderr.on("data", (data) => {serverError += data;});
  server.on("error", (error) => {serverError += error.message;});
  const base = await until(async () => {
    if (serverError) throw new Error(serverError);
    return serverOutput.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0];
  }, "local server");
  let chromeError = "";
  chrome = spawn(process.env.CHROME_BIN || "google-chrome", ["--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--no-first-run", "--remote-debugging-port=0", `--user-data-dir=${scratch}`, "about:blank"], {stdio:"ignore"});
  chrome.on("error", (error) => {chromeError = error.message;});
  const port = await until(async () => {
    if (chromeError) throw new Error(`Chrome unavailable; set CHROME_BIN. ${chromeError}`);
    try { return (await readFile(join(scratch,"DevToolsActivePort"),"utf8")).split("\n")[0]; } catch { return null; }
  }, "Chrome debugging port");
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?${base}`, {method:"PUT"})).json();
  ws = new WebSocket(target.webSocketDebuggerUrl);
  ws.onmessage = ({data}) => {
    const message = JSON.parse(data);
    if (message.id && waiting.has(message.id)) {
      const promise = waiting.get(message.id); waiting.delete(message.id); clearTimeout(promise.timeout);
      if (message.error) promise.reject(new Error(message.error.message)); else promise.resolve(message.result);
    }
    if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails);
    if (message.method === "Network.requestWillBeSent") requests.push(message.params.request.url);
  };
  await new Promise((resolve, reject) => {ws.onopen = resolve; ws.onerror = reject;});
  await command("Page.enable"); await command("Runtime.enable"); await command("Network.enable");
  await command("Emulation.setDeviceMetricsOverride", {width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await command("Page.navigate", {url:base});
  await ready(`document.querySelector('#case-title')?.textContent === 'A deductible charged twice'`, "initial case");
  assert.equal(await evaluate(`document.querySelectorAll('[role=tab]').length`), 3);
  await mkdir(artifacts, {recursive:true});
  await screenshot("desktop-policy.png");
  await click('#panel-policy [data-next="claim"]');
  assert.equal(await evaluate(`document.querySelector('#panel-claim').hidden`), false);
  assert.match(await evaluate(`document.querySelector('#panel-claim').textContent`), /\$385\.00/);
  await screenshot("desktop-claim.png");
  await click('#panel-claim .citation');
  assert.equal(await evaluate(`document.querySelector('#panel-policy').hidden`), false);
  assert.equal(await evaluate(`document.querySelector('#clauses').open`), true);
  await click('#tab-bill');
  assert.equal(await evaluate(`document.querySelector('.big-number').textContent`), "$120.00");
  assert.match(await evaluate(`document.querySelector('#panel-bill').textContent`), /\$285\.00/);
  await click('[data-case="mosaic-oop"]');
  await ready(`document.querySelector('#case-title').textContent === 'The out-of-pocket limit matters'`, "Mosaic OOP case");
  await click('#tab-bill');
  assert.equal(await evaluate(`document.querySelector('.big-number').textContent`), "$150.00");
  await click('[data-case="mosaic-therapy"]');
  await ready(`document.querySelector('#case-title').textContent === 'When the policy needs clarification'`, "therapy case");
  await click('#tab-claim');
  assert.equal(await evaluate(`document.querySelector('#scenario-claim').options.length`), 32);
  await evaluate(`document.querySelector('#scenario-claim').value='1';document.querySelector('#scenario-claim').dispatchEvent(new Event('change',{bubbles:true}))`);
  assert.equal(await evaluate(`document.querySelector('#scenario-claim').value`), "1");
  // Resolve all missing facts: only the two conflicting policy interpretations remain.
  await evaluate(`(() => {const form=document.querySelector('#facts-form');for(const [name,value] of Object.entries({'ded:in':'0','oop:in':'0','net:0':'in','allowed:0':'200.00','source:0':'contract','ref:0':'Synthetic browser test evidence'})){form.elements.namedItem(name).value=value;}form.requestSubmit();})()`);
  await ready(`document.querySelector('#scenario-claim').options.length === 2`, "facts recalculation");
  assert.equal(await evaluate(`document.querySelector('#error').hidden`), true);
  // Export then re-import an actual browser download using the same JSON file.
  await command("Browser.setDownloadBehavior", {behavior:"allow", downloadPath:scratch});
  await click('#download');
  const saved = await until(async () => {try{return await readFile(join(scratch,"fineprint-case.json"),"utf8");}catch{return null;}}, "case export");
  assert.equal(JSON.parse(saved).allowed_evidence.T1.allowed_cents, 20000);
  await click('#reset');
  assert.equal(await evaluate(`document.querySelector('#scenario-claim').options.length`), 32);
  const dom = await command("DOM.getDocument");
  const fileInput = await command("DOM.querySelector", {nodeId:dom.root.nodeId,selector:"#import-file"});
  await command("DOM.setFileInputFiles", {nodeId:fileInput.nodeId,files:[join(scratch,"fineprint-case.json")]});
  await ready(`document.querySelector('#scenario-claim').options.length === 2`, "JSON import");
  // Keyboard workflow navigation and small viewport layout.
  await click('#tab-policy');
  await evaluate(`document.querySelector('#tab-policy').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))`);
  assert.equal(await evaluate(`document.querySelector('#tab-claim').getAttribute('aria-selected')`), "true");
  await command("Emulation.setDeviceMetricsOverride", {width:390,height:844,deviceScaleFactor:1,mobile:true});
  assert.ok(await evaluate(`document.documentElement.scrollWidth <= innerWidth`), "Mobile page should not overflow horizontally");
  await evaluate("window.scrollTo(0,0)"); await screenshot("mobile-claim.png");
  await click('#tab-bill');
  assert.ok(await evaluate(`document.documentElement.scrollWidth <= innerWidth`), "Bill table must scroll inside its container");
  await screenshot("mobile-bill.png");
  assert.equal(exceptions.length, 0, JSON.stringify(exceptions));
  assert.ok(requests.every((url) => url.startsWith(base) || url === "about:blank"), "App must not make external requests");
  console.log("Browser smoke passed: 3 cases, workflow, clause links, 32→2 scenarios, facts, export/import, keyboard, mobile, no JS exceptions or external requests.");
  console.log(`Screenshots: ${artifacts}`);
} finally {
  if (ws) ws.close();
  for (const pending of waiting.values()) clearTimeout(pending.timeout);
  const stop = async (child) => {
    if (!child || child.exitCode !== null) return;
    child.kill("SIGTERM");
    await Promise.race([new Promise((resolve) => child.once("exit",resolve)),pause(1500)]);
    if (child.exitCode === null) child.kill("SIGKILL");
  };
  await stop(chrome); await stop(server);
  await rm(scratch, {recursive:true,force:true,maxRetries:3});
}
