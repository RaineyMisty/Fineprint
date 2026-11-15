"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const S = {step: 1, samples: [], sample: null, data: null, active: null, scenario: 0, lastRequest: null,
             pdf: {}, pdfRun: [], reading: new Set(), token: {}, seq: 0};

  /* ---------- helpers ---------- */
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === false || v == null) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
    return el;
  }
  const money = (c) => {
    const neg = c < 0, v = Math.abs(c) / 100;
    return (neg ? "−" : "") + "$" + v.toLocaleString("en-US", {minimumFractionDigits: Number.isInteger(v) ? 0 : 2, maximumFractionDigits: 2});
  };
  const pct = (bps) => (bps / 100).toLocaleString("en-US", {maximumFractionDigits: 2}) + "%";
  const clear = (el) => { el.replaceChildren(); return el; };

  async function api(path, options) {
    let res;
    try { res = await fetch(path, options); }
    catch { throw {message: "Can’t reach the Fineprint server. Is it still running?", kind: "network"}; }
    let body = null;
    try { body = await res.json(); } catch { /* non-JSON */ }
    if (!res.ok) throw {message: (body && body.error) || `Request failed (${res.status})`, kind: (body && body.kind) || "input"};
    return body;
  }

  /* ---------- navigation ---------- */
  function show(step) {
    S.step = step;
    for (const n of [1, 2, 3]) $("step-" + n).hidden = n !== step;
    $("loading").hidden = true;
    $("synthetic-note").hidden = !(S.sample && S.data && step > 1);
    const have = S.data;
    document.querySelectorAll("#steps button").forEach((b) => {
      const n = +b.dataset.step;
      b.disabled = n > 1 && !have;
      b.classList.toggle("done", !!have && n < step);
      if (n === step) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
    });
    window.scrollTo(0, 0);
    $("main").focus({preventScroll: true});
  }
  function loading(text) {
    for (const n of [1, 2, 3]) $("step-" + n).hidden = true;
    $("loading-text").textContent = text;
    $("loading").hidden = false;
  }
  function banner(message, kind, retry) {
    const box = clear($("banner"));
    const title = kind === "provider" ? "The AI policy reader failed — nothing was guessed"
      : kind === "network" ? "Connection problem" : "We couldn’t check these documents";
    const extra = kind === "provider" ? "No offline fallback was substituted, so no result is shown. Try again, or ask whoever runs this server to switch to the offline reader." : "";
    box.append(h("div", {}, h("strong", {}, title), message, extra ? h("div", {class: "hint"}, extra) : null));
    if (retry) box.append(h("button", {class: "btn", type: "button", onclick: retry}, "Try again"));
    box.hidden = false;
  }
  const unbanner = () => { $("banner").hidden = true; };

  /* ---------- step 1 ---------- */
  function updateCounts() {
    document.querySelectorAll("[data-count]").forEach((el) => {
      const n = $(el.dataset.count).value.length;
      el.textContent = n ? n.toLocaleString("en-US") + " characters" : "";
    });
  }
  function fillInputs(inputs) {
    $("in-policy").value = inputs.policy; $("in-eob").value = inputs.eob; $("in-bill").value = inputs.bill;
    $("in-format").value = inputs.claim_format;
    $("in-facts").value = JSON.stringify({claim_context: inputs.claim_context, bill_context: inputs.bill_context, allowed_evidence: inputs.allowed_evidence}, null, 2);
    updateCounts();
  }
  function collect() {
    const eob = $("in-eob").value;
    let facts = {};
    const raw = $("in-facts").value.trim();
    if (raw) {
      try { facts = JSON.parse(raw); } catch { throw {message: "The claim facts are not valid JSON. Open “Claim facts & format” to fix them.", kind: "input"}; }
    }
    return {policy: $("in-policy").value, eob, bill: $("in-bill").value, claim_format: $("in-format").value, ...facts,
            synthetic: !!S.sample};
  }
  /* ---------- file upload & drop (PDFs are extracted by /api/extract) ---------- */
  const KINDS = ["policy", "eob", "bill"];
  const MAX_PDF = 11 * 1024 * 1024, MAX_TEXT = 900000;
  const DOC_NAME = {policy: "policy", eob: "insurer statement", bill: "provider bill"};
  const isPdf = (f) => f.type === "application/pdf" || /\.pdf$/i.test(f.name);
  const plural = (n, w) => `${(+n || 0).toLocaleString("en-US")} ${w}${+n === 1 ? "" : "s"}`;
  function setStatus(kind, cls, ...kids) {
    const el = $("status-" + kind);
    el.className = "file-status" + (cls ? " " + cls : "");
    el.replaceChildren(...kids.flat());
  }
  // res = the /api/extract response while the box holds PDF-extracted text, else null.
  function setPdf(kind, res) {
    S.pdf[kind] = res;
    $("in-" + kind).closest(".doc").classList.toggle("from-pdf", !!res);
    if (!res) return setStatus(kind, "");
    const what = res.status === "structured" ? plural(res.rows, kind === "bill" ? "bill line" : "claim line") + " found" : "text extracted";
    const notice = res.notice || "extracted from PDF — please check";
    setStatus(kind, "pdf",
      h("span", {}, h("b", {}, res.filename), ` · ${plural(res.pages, "page")} · ${what}`),
      h("span", {class: "file-check"}, notice.charAt(0).toUpperCase() + notice.slice(1)),
      (res.warnings || []).map((w) => h("span", {class: "file-warn"}, String(w))));
  }
  const syncBusy = () => { $("check-btn").disabled = S.reading.size > 0; };
  function resetFiles() { // Clear / sample: forget PDF provenance and ignore any extraction still in flight
    for (const k of KINDS) { S.token[k] = ++S.seq; setPdf(k, null); }
    S.reading.clear(); syncBusy();
  }
  const readBase64 = (file) => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => { const s = String(r.result); resolve(s.slice(s.indexOf(",") + 1)); };
    r.onerror = () => reject({message: "Couldn’t read that file."});
    r.onabort = () => reject({message: "File reading was cancelled."});
    r.readAsDataURL(file);
  });
  async function loadFile(kind, file) {
    const input = $("file-" + kind), token = S.token[kind] = ++S.seq;
    S.reading.delete(kind); syncBusy();
    const types = input.accept.split(",").map((t) => t.trim().toLowerCase()), name = file.name.toLowerCase();
    if (!types.some((t) => (t.startsWith(".") ? name.endsWith(t) : t === file.type))) {
      const exts = types.filter((t) => t.startsWith("."));
      return setStatus(kind, "error", `Choose a ${exts.slice(0, -1).join(", ")} or ${exts.at(-1)} file.`);
    }
    if (!isPdf(file)) {
      if (file.size > MAX_TEXT) return setStatus(kind, "error", "That file is too large (limit about 900 KB).");
      S.reading.add(kind); syncBusy();
      setStatus(kind, "busy", `Reading ${file.name}…`);
      try {
        const text = await file.text();
        if (S.token[kind] !== token) return;
        $("in-" + kind).value = text;
        if (kind === "eob") $("in-format").value = text.trim().startsWith("{") ? "mosaic-ledger-v1" : "aurora-csv-v1";
        setPdf(kind, null); setStatus(kind, "", `${file.name} · text loaded`);
        updateCounts(); S.sample = null;
      } catch {
        if (S.token[kind] === token) setStatus(kind, "error", "Couldn’t read that file.");
      } finally {
        if (S.token[kind] === token) { S.reading.delete(kind); syncBusy(); }
      }
      return;
    }
    if (!file.size) return setStatus(kind, "error", "This PDF is empty.");
    if (file.size > MAX_PDF) return setStatus(kind, "error", "PDF is larger than 11 MB");
    S.reading.add(kind); syncBusy();
    setStatus(kind, "busy", `Reading ${file.name}…`);
    try {
      const content_base64 = await readBase64(file);
      if (S.token[kind] !== token) return;
      const res = await api("/api/extract", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({kind, filename: file.name, content_base64})});
      if (S.token[kind] !== token) return;
      if (!res || typeof res.text !== "string" || !res.text.trim()) throw {message: "No text came back from this PDF."};
      $("in-" + kind).value = res.text;
      if (kind === "eob" && res.format === "aurora-csv-v1") $("in-format").value = "aurora-csv-v1";
      setPdf(kind, {...res, filename: res.filename || file.name});
      updateCounts(); S.sample = null;
    } catch (e) {
      // Fail closed: show why, leave the textarea as it was.
      if (S.token[kind] === token) setStatus(kind, "error", (e && e.message) || "Couldn’t read that PDF.");
    } finally {
      if (S.token[kind] === token) { S.reading.delete(kind); syncBusy(); }
    }
  }
  function renderPdfNote() {
    const from = S.pdfRun, parts = [];
    if (from.includes("policy")) parts.push("Policy text was extracted from your PDF — please check the cited passages against the original.");
    const rest = from.filter((k) => k !== "policy").map((k) => DOC_NAME[k]);
    if (rest.length) parts.push(`The ${rest.join(" and ")} ${rest.length > 1 ? "were" : "was"} extracted from PDF — please check the amounts against the original${rest.length > 1 ? "s" : ""}.`);
    $("pdf-note").textContent = parts.join(" ");
    $("pdf-note").hidden = !parts.length;
  }

  async function loadSample(id) {
    unbanner();
    try {
      const sample = await api("/api/samples/" + encodeURIComponent(id));
      S.sample = sample;
      resetFiles();
      fillInputs(sample.inputs);
      $("doc-form").scrollIntoView({block: "start", behavior: "smooth"});
      $("doc-form").classList.add("filled");
      $("check-btn").textContent = "Reading sample…";
      await new Promise((r) => setTimeout(r, 1400)); // let the user see what was filled in
      $("check-btn").textContent = "Check my bill";
      $("doc-form").classList.remove("filled");
      await run(`Reading “${sample.title}” (synthetic)…`);
    } catch (e) { show(1); banner(e.message, e.kind); }
  }
  async function run(text) {
    unbanner();
    if (S.reading.size) { show(1); banner("Still reading your PDF — check again once it’s done.", "input"); return; }
    let payload;
    try { payload = collect(); } catch (e) { show(1); banner(e.message, e.kind); return; }
    if (!payload.policy.trim() || !payload.eob.trim() || !payload.bill.trim()) {
      show(1); banner("Add all three documents, or try a sample case.", "input"); return;
    }
    const fromPdf = KINDS.filter((k) => S.pdf[k]);
    loading(text || "Reading your policy…");
    try {
      S.data = await api("/api/check", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
      S.active = null; S.scenario = 0; S.pdfRun = fromPdf;
      renderRules(); renderResult(); show(2);
    } catch (e) { show(1); banner(e.message, e.kind, () => run()); }
  }

  /* ---------- step 2: rules + source ---------- */
  function ruleDescription(r) {
    const bits = [];
    if (!r.covered) bits.push("Not covered — you pay the full charge");
    else {
      bits.push(r.copay_cents ? `${money(r.copay_cents)} copay` : "no copay");
      bits.push(r.coinsurance_bps ? `you pay ${pct(r.coinsurance_bps)} after` : "no coinsurance");
      bits.push(r.deductible_applies ? "deductible applies" : "deductible waived");
    }
    return bits.join(" · ");
  }
  function evidenceFor(path) {
    const re = S.data.compilation.output.rule_evidence.find((e) => e.rule_path === path);
    return re || null;
  }
  function unresolvedRanges() {
    const text = S.data.documents.policy, out = [];
    for (const msg of S.data.compilation.output.unresolved) {
      const id = (/Clause\s+([^\s:]+)/.exec(msg) || [])[1];
      let range = null;
      if (id) {
        const esc = id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const m = new RegExp(`^.*(?:^|[\\s|#])(?:Clause\\s+)?${esc}(?=[\\s|:.)])[^\\n]*$`, "m").exec(text);
        if (m) range = [m.index, m.index + m[0].length];
      }
      out.push({msg, id, range});
    }
    return out;
  }
  function renderRules() {
    const {compilation, case: kase} = S.data, out = compilation.output, policy = out.policy;
    // backend card
    const off = compilation.backend === "fallback";
    const card = clear($("backend-card"));
    card.className = "backend " + (off ? "off" : "llm");
    card.append(h("b", {}, off ? "Offline rule reader — no AI used" : `AI provider: ${compilation.backend}`),
      h("span", {class: "muted"}, off
        ? "A fixed pattern parser read your policy on this device. It understands common wording only."
        : `Rules were drafted by an AI model, then checked against your text. ${compilation.attempts} attempt${compilation.attempts > 1 ? "s" : ""}.`),
      h("div", {class: "hint"}, "Document fingerprint " + compilation.source_sha256.slice(0, 10)));

    // unresolved
    const un = clear($("unresolved")), ranges = S.unresolved = unresolvedRanges();
    if (ranges.length) {
      un.hidden = false;
      un.append(h("h2", {}, `${ranges.length} clause${ranges.length > 1 ? "s" : ""} we couldn’t understand`),
        h("p", {}, "We won’t guess. The result will say “needs clarification” until these are fixed or reworded."),
        h("ul", {}, ranges.map((r, i) => h("li", {}, r.range
          ? h("button", {type: "button", onclick: () => selectRule("unresolved:" + i)}, r.msg)
          : r.msg))));
    } else un.hidden = true;
    $("to-result").textContent = ranges.length ? "See what this means →" : "See my result →";

    // rule cards
    const box = clear($("rules"));
    const netName = {in: "In-network", out: "Out-of-network"};
    box.append(h("h3", {}, "Plan limits"));
    for (const [net, t] of Object.entries(policy.networks)) {
      const ev = evidenceFor(`networks.${net}.deductible_cents`);
      box.append(ruleCard("net:" + net, `${netName[net] || net} limits`,
        `Deductible ${money(t.deductible_cents)} · out-of-pocket max ${money(t.oop_max_cents)} · ${t.balance_billing ? "extra billing allowed" : "no extra billing"}`,
        net, ["deductible_cents", "oop_max_cents", "balance_billing"].map((k) => evidenceFor(`networks.${net}.${k}`)).filter(Boolean)));
    }
    box.append(h("h3", {}, "Covered services"));
    for (const b of policy.benefits) {
      const ev = evidenceFor("benefits." + b.id);
      box.append(ruleCard("ben:" + b.id, (/network/i.test(b.label) ? b.label : `${b.label} (${netName[b.network] || b.network})`), ruleDescription(b), null, ev ? [ev] : [], b));
    }
    renderPdfNote();
    renderSource();
  }
  function ruleCard(id, title, desc, _net, evs, benefit) {
    const spans = evs.flatMap((e) => e.evidence);
    const ambiguous = evs.find((e) => e.ambiguity && e.ambiguity !== "none");
    const secs = [...new Set(spans.map((s) => s.section))];
    const card = h("button", {type: "button", class: "rule", "data-rule": id, "aria-pressed": "false", onclick: () => selectRule(id)},
      h("div", {class: "t"}, h("span", {}, title, ambiguous ? h("span", {class: "flag"}, "Unclear wording") : null)),
      h("div", {class: "d"}, desc),
      ambiguous ? h("div", {class: "d"}, ambiguous.ambiguity) : null,
      h("div", {class: "src"}, secs.length ? "Source: " + secs.join(", ") : "No source passage recorded"));
    card._spans = spans;
    return card;
  }
  function spansOf(id) {
    if (!id) return [];
    if (id.startsWith("unresolved:")) { const r = S.unresolved[+id.slice(11)]; return r && r.range ? [{start: r.range[0], end: r.range[1]}] : []; }
    const el = document.querySelector(`[data-rule="${CSS.escape(id)}"]`);
    return el ? el._spans : [];
  }
  function selectRule(id) {
    S.active = S.active === id ? null : id;
    document.querySelectorAll(".rule").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.rule === S.active)));
    renderSource(true);
    if (S.active && window.matchMedia("(max-width:900px)").matches) $("source-text").scrollIntoView({block: "center", behavior: "smooth"});
  }
  function renderSource(scroll, focusRange) {
    const text = S.data.documents.policy, box = clear($("source-text"));
    const all = [...document.querySelectorAll(".rule")].flatMap((b) => b._spans || []);
    const active = focusRange ? [focusRange] : spansOf(S.active);
    const flagged = S.unresolved.filter((r) => r.range).map((r) => r.range);
    const cuts = new Set([0, text.length]);
    for (const s of [...all, ...active, ...flagged.map(([start, end]) => ({start, end}))]) { cuts.add(Math.max(0, s.start)); cuts.add(Math.min(text.length, s.end)); }
    const pts = [...cuts].sort((a, b) => a - b);
    const within = (list, a, b) => list.some((s) => (s.start ?? s[0]) <= a && (s.end ?? s[1]) >= b);
    let firstOn = null;
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1], piece = text.slice(a, b);
      const on = within(active, a, b), fl = within(flagged, a, b), cov = within(all, a, b);
      if (!on && !fl && !cov) { box.append(piece); continue; }
      const m = h("mark", {class: on ? "on" : fl ? "flagged" : ""}, piece);
      if (on && !firstOn) firstOn = m;
      box.append(m);
    }
    $("source-legend").replaceChildren(h("i"), "Source of a rule", h("i", {class: "f"}), "Not understood");
    if (scroll && firstOn) firstOn.scrollIntoView({block: "center", behavior: "smooth"});
  }

  /* ---------- step 3: result ---------- */
  const MAIN = ["allowed_cents", "deductible_cents", "copay_cents", "coinsurance_cents", "noncovered_cents", "balance_cents"];
  const LABEL = {allowed_cents: "allowed price", deductible_cents: "deductible", copay_cents: "copay", coinsurance_cents: "coinsurance", noncovered_cents: "uncovered charge", balance_cents: "extra billing"};
  function verdict() {
    const r = S.data.report;
    if (r.status === "blocked") return {kind: "ask", k: "Needs clarification", title: "We can’t give you an answer yet",
      text: r.blocked_reason + " Fix the policy text or the claim facts and check again."};
    const s = r.summary, min = s.potential_overpayment_min_cents, max = s.potential_overpayment_max_cents;
    const refund = Math.max(...r.comparisons.map((c) => c.lines.reduce((a, l) => a + l.potential_refund_cents, 0)));
    if (min > 0) return {kind: "over", k: "Possible overcharge", title: s.conditional ? `You may be overcharged at least ${money(min)}` : `You may be overcharged ${money(min)}`,
      text: `The bill asks for ${money(s.bill_patient_cents)}. Your policy supports ${s.conditional ? "as little as " : ""}${money(s.bill_patient_cents - min)}. Ask the billing office to explain the difference.`};
    if (max > 0) return {kind: "ask", k: "Needs clarification", title: `You could be overcharged up to ${money(max)}`,
      text: `It depends on facts we couldn’t confirm (such as network, contracted price or what you’ve already paid). ${s.scenario_count} possible readings fit your documents; some match your bill.`};
    if (refund > 0) return {kind: "over", k: "Possible refund", title: `You may have overpaid ${money(refund)}`,
      text: "You’ve already paid more than your policy supports. Ask for a credit or refund."};
    const diffs = r.comparisons.some((c) => c.lines.some((l) => l.explanations.some((e) => e.kind !== "match")));
    return {kind: "ok", k: "Looks right", title: "Your bill matches",
      text: diffs ? `The bill isn’t higher than your policy supports, but the insurer’s statement differs in places — see below.` : "Our independent calculation, the insurer’s statement and the bill all agree."};
  }
  function ordered() {
    return [...S.data.report.comparisons].sort((a, b) => a.fineprint_patient_cents - b.fineprint_patient_cents || a.scenario_id.localeCompare(b.scenario_id));
  }
  function renderResult() {
    const r = S.data.report, v = verdict();
    const box = clear($("verdict")); box.className = "verdict " + v.kind;
    box.append(h("div", {class: "k"}, v.k), h("h1", {id: "verdict-title"}, v.title), h("p", {}, v.text));
    const fig = clear($("figures")), asm = clear($("assumptions")), lines = clear($("lines")), pick = clear($("scenario-pick"));
    if (r.status === "blocked") {
      fig.hidden = true; $("export").hidden = false;
      lines.append(h("div", {class: "note warn"}, "Line-by-line results appear once the policy is fully understood."));
      return;
    }
    fig.hidden = false;
    const s = r.summary, cs = ordered(), cur = cs[S.scenario] || cs[0];
    const range = (a, b) => (a === b ? money(a) : `${money(a)}–${money(b)}`);
    fig.append(figure("Hospital bill", money(s.bill_patient_cents)), figure("Insurer says you owe", money(s.eob_patient_cents)),
      figure("Fineprint calculates", range(s.illustrated_min_patient_cents, s.illustrated_max_patient_cents), true));
    if (!s.conditional) fig.append(figure("Still to pay (by our math)", money(cur.fineprint_remaining_cents)));

    const issues = r.validation.filter((i) => i.severity !== "info");
    if (issues.length || r.limitations.length) {
      asm.append(h("details", {class: "note warn"}, h("summary", {}, issues.length ? `${issues.length} thing${issues.length > 1 ? "s" : ""} we assumed or couldn’t confirm` : "What this check doesn’t cover"),
        h("ul", {}, issues.map((i) => h("li", {}, i.message)), r.limitations.map((l) => h("li", {class: "muted"}, l)))));
    }
    if (s.conditional) {
      pick.append(h("label", {for: "scn", class: "muted"}, "Reading: "),
        h("select", {id: "scn", onchange: (e) => { S.scenario = +e.target.value; renderResult(); document.getElementById("scn").focus(); }},
          cs.map((c, i) => h("option", {value: i, selected: i === S.scenario}, `${i + 1} of ${cs.length} — you’d owe ${money(c.fineprint_patient_cents)}`))));
      const sc = r.scenarios.find((x) => x.id === cur.scenario_id);
      if (sc) asm.append(h("details", {class: "note"}, h("summary", {}, "Assumptions in this reading"), h("ul", {}, sc.assumptions.map((a) => h("li", {}, a)))));
    }
    const scenario = r.scenarios.find((x) => x.id === cur.scenario_id);
    cur.lines.forEach((l) => lines.append(lineCard(l, scenario)));
  }
  const figure = (l, v, hl) => h("div", {class: "fig" + (hl ? " hl" : "")}, h("div", {class: "l"}, l), h("div", {class: "v"}, v));

  function lineCard(l, scenario) {
    const claim = S.data.case.claim.lines.find((c) => c.id === l.claim_line_id), eob = claim.insurer;
    const res = scenario && scenario.lines.find((x) => x.claim_line_id === l.claim_line_id);
    const diffs = l.explanations.filter((e) => e.kind !== "match");
    const material = diffs.filter((e) => e.kind !== "eob_vs_fineprint" || MAIN.includes(e.component));
    const over = l.bill_patient_cents - l.fineprint_patient_cents;
    const chip = over > 0 ? ["over", `Overbilled ${money(over)}`] : over < 0 ? ["ask", `Billed ${money(-over)} less`] : material.length ? ["ask", "Check statement"] : ["ok", "Matches"];
    const reasons = material.map((e) => {
      let text;
      if (e.kind === "eob_vs_fineprint") {
        const a = eob[e.component], b = res ? res[e.component] : a - e.difference_cents;
        text = e.component === "allowed_cents" ? `The insurer used an allowed price of ${money(a)}; your contract supports ${money(b)}.`
          : `The insurer charged you ${money(a)} in ${LABEL[e.component]}; your policy supports ${money(b)}.`;
      } else if (e.kind === "bill_vs_eob") {
        text = `The bill (${money(l.bill_patient_cents)}) differs from the insurer’s statement (${money(l.eob_patient_cents)}) by ${money(Math.abs(e.difference_cents))}. Ask about a missing credit or adjustment.`;
      } else text = `The bill asks for ${money(l.bill_patient_cents)}; your policy supports ${money(l.fineprint_patient_cents)}. Request an itemized explanation.`;
      return h("li", {}, text, h("div", {class: "cite"}, "Based on:", e.clause_ids.map((id) => clauseButton(id))));
    });
    const trace = res && res.trace;
    return h("article", {class: "line"},
      h("div", {class: "line-top"}, h("div", {}, h("b", {}, l.description), h("span", {class: "code"}, l.code)), h("span", {class: "chip " + chip[0]}, chip[1])),
      h("div", {class: "amts"}, amt("Hospital bill", l.bill_patient_cents), amt("Insurer says", l.eob_patient_cents), amt("Fineprint", l.fineprint_patient_cents, true)),
      reasons.length ? h("ul", {class: "why"}, reasons) : h("p", {class: "ok-line"}, "✓ Policy, statement and bill agree for this line."),
      l.already_paid_cents ? h("p", {class: "hint"}, `You already paid ${money(l.already_paid_cents)}${l.potential_refund_cents ? `, ${money(l.potential_refund_cents)} more than supported` : ""}.`) : null,
      trace && trace.length ? h("details", {}, h("summary", {}, "How we calculated this"),
        h("ol", {class: "trace"}, trace.map((t) => h("li", {}, `${t.explanation} (${money(t.amount_cents)}) `, h("span", {class: "cite"}, t.clause_ids.map((id) => clauseButton(id)))))) ) : null);
  }
  const amt = (l, c, me) => h("div", {class: me ? "me" : ""}, h("div", {class: "l"}, l), h("div", {class: "v"}, money(c)));

  function clauseButton(id) {
    return h("button", {type: "button", onclick: () => openClause(id), "aria-label": `Show clause ${id}`}, id);
  }
  function openClause(id) {
    const clause = S.data.case.policy.clauses.find((c) => c.id === id);
    $("clause-title").textContent = clause ? `Clause ${id}` : `Clause ${id} not found`;
    $("clause-text").textContent = clause ? clause.text : "This clause is not in the compiled policy.";
    $("clause-show").hidden = !clause;
    $("clause-show").onclick = () => {
      $("clause-dialog").close();
      const text = S.data.documents.policy, i = clause ? text.indexOf(clause.text) : -1;
      show(2); S.active = null; document.querySelectorAll(".rule").forEach((b) => b.setAttribute("aria-pressed", "false"));
      renderSource(true, i >= 0 ? [i, i + clause.text.length] : null);
    };
    $("clause-dialog").showModal();
  }

  /* ---------- export ---------- */
  function summaryText() {
    const r = S.data.report, v = verdict(), c = S.data.compilation, lines = [];
    lines.push("# Fineprint summary", "", `**${v.title}**`, "", v.text, "");
    lines.push(`Policy reader: ${c.backend === "fallback" ? "offline rule reader (no AI)" : "AI provider " + c.backend}`);
    if (S.data.case.synthetic) lines.push("Data: synthetic demo case, not a real claim.");
    if (S.pdfRun.length) lines.push(`Extracted from PDF (please check against the original): ${S.pdfRun.map((k) => DOC_NAME[k]).join(", ")}.`);
    if (r.status !== "blocked") {
      const s = r.summary;
      lines.push("", `- Hospital bill: ${money(s.bill_patient_cents)}`, `- Insurer statement: ${money(s.eob_patient_cents)}`,
        `- Fineprint: ${s.illustrated_min_patient_cents === s.illustrated_max_patient_cents ? money(s.illustrated_min_patient_cents) : money(s.illustrated_min_patient_cents) + "–" + money(s.illustrated_max_patient_cents)}`, "");
      const cur = ordered()[S.scenario] || ordered()[0];
      if (s.conditional) lines.push(`_Showing reading ${S.scenario + 1} of ${s.scenario_count}; results depend on unconfirmed facts._`, "");
      lines.push("## Lines", "");
      for (const l of cur.lines) {
        lines.push(`### ${l.description} (${l.code})`, `Bill ${money(l.bill_patient_cents)} · Insurer ${money(l.eob_patient_cents)} · Fineprint ${money(l.fineprint_patient_cents)}`);
        const eob = S.data.case.claim.lines.find((x) => x.id === l.claim_line_id).insurer;
        for (const e of l.explanations.filter((x) => x.kind !== "match" && (x.kind !== "eob_vs_fineprint" || MAIN.includes(x.component))))
          lines.push(`- ${e.kind === "eob_vs_fineprint" ? `Insurer’s ${LABEL[e.component]} ${money(eob[e.component])} vs policy ${money(eob[e.component] - e.difference_cents)}` : e.kind === "bill_vs_eob" ? "Bill differs from insurer statement by " + money(Math.abs(e.difference_cents)) : "Bill differs from policy calculation by " + money(Math.abs(e.difference_cents))} (clauses: ${e.clause_ids.join(", ")})`);
        lines.push("");
      }
    }
    lines.push("_Not legal or medical advice. A difference is a question to ask, not a reason to withhold payment._");
    return lines.join("\n");
  }
  function download(name, mime, content) {
    const a = h("a", {href: URL.createObjectURL(new Blob([content], {type: mime})), download: name});
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  /* ---------- wiring ---------- */
  async function init() {
    document.querySelectorAll("#steps button").forEach((b) => b.addEventListener("click", () => show(+b.dataset.step)));
    document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => show(+b.dataset.go)));
    $("doc-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
    $("clear-btn").addEventListener("click", () => { for (const id of ["in-policy", "in-eob", "in-bill", "in-facts"]) $(id).value = ""; S.sample = null; resetFiles(); updateCounts(); unbanner(); });
    document.querySelectorAll("textarea").forEach((t) => t.addEventListener("input", () => {
      updateCounts(); S.sample = null;
      const kind = t.closest(".doc")?.dataset.kind;
      if (!kind) return;
      if (S.reading.has(kind)) {
        // A user's edit wins over any upload response still in flight.
        S.token[kind] = ++S.seq; S.reading.delete(kind); syncBusy();
        setPdf(kind, S.pdf[kind] || null);
      }
      if (!t.value.trim()) setPdf(kind, null); // emptied: no longer PDF text
      else if ($("status-" + kind).classList.contains("error")) setPdf(kind, S.pdf[kind] || null); // edits keep the "please check" marker
    }));
    document.querySelectorAll("input[type=file]").forEach((f) => f.addEventListener("change", () => {
      const file = f.files[0]; f.value = "";
      if (file) loadFile(f.dataset.target.slice(3), file);
    }));
    // Drag & drop: a file dropped on a document box loads like Upload; anywhere else it is ignored (never navigates away).
    const hasFiles = (e) => !!e.dataTransfer && [...e.dataTransfer.types].includes("Files");
    const boxOf = (e) => (e.target instanceof Element ? e.target.closest(".doc") : null);
    const highlight = (box) => document.querySelectorAll(".doc").forEach((d) => d.classList.toggle("drag", d === box));
    for (const type of ["dragenter", "dragover"]) document.addEventListener(type, (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      const box = boxOf(e);
      e.dataTransfer.dropEffect = box ? "copy" : "none";
      highlight(box);
    });
    document.addEventListener("dragleave", (e) => { if (!e.relatedTarget) highlight(null); });
    document.addEventListener("drop", (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault(); highlight(null);
      const box = boxOf(e), file = e.dataTransfer.files[0];
      if (box && file) loadFile(box.dataset.kind, file);
    });
    $("copy-btn").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(summaryText()); $("copy-status").textContent = "Summary copied."; }
      catch { $("copy-status").textContent = "Couldn’t copy automatically — use Download instead."; }
    });
    $("dl-md").addEventListener("click", () => download("fineprint-summary.md", "text/markdown", summaryText()));
    $("dl-json").addEventListener("click", () => download("fineprint-result.json", "application/json", JSON.stringify(S.data, null, 2)));
    $("print-btn").addEventListener("click", () => window.print());
    $("restart").addEventListener("click", () => { S.data = null; show(1); });
    show(1);
    api("/api/status").then((st) => {
      const b = $("provider-badge"); b.hidden = false;
      b.textContent = st.offline ? "Offline reader" : "AI reader: " + st.provider;
      b.classList.toggle("llm", !st.offline);
      b.title = st.offline ? "Policies are read by the built-in offline parser." : "Policies are read by an external AI provider.";
      if (!st.offline) $("privacy-note").textContent += ` Policy text is sent to the AI policy reader (${st.provider}) to extract rules.`;
    }).catch(() => {});
    try {
      S.samples = await api("/api/samples");
      const list = clear($("sample-list"));
      for (const s of S.samples) list.append(h("button", {type: "button", class: "sample", onclick: () => loadSample(s.id)},
        h("span", {class: "kicker"}, "Sample · synthetic"), h("b", {}, s.title), h("span", {class: "go"}, "Fill in & run →")));
    } catch (e) { clear($("sample-list")).append(h("p", {class: "muted"}, "Samples couldn’t load. You can still paste your own documents.")); }
  }
  init();
})();
