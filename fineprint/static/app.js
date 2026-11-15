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
    $("synthetic-note").hidden = !(S.sample && (S.data || S.sample.requires_policy_upload));
    $("synthetic-note").textContent = S.sample?.requires_policy_upload
      ? "Real policy · SYNTHETIC claim and bill. Allowances, provider, member and prior spending are invented demo facts."
      : "Synthetic sample — fictional people, insurer and bill. Not a real claim.";
    const have = S.data;
    document.querySelectorAll("#steps button").forEach((b) => {
      const n = +b.dataset.step;
      b.disabled = n > 1 && !have;
      b.classList.toggle("done", !!have && n < step);
      if (n === step) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
    });
    window.scrollTo(0, 0);
    const heading = $("step-" + step).querySelector("h1");
    (heading || $("main")).focus({preventScroll: true});
  }
  function loading(text, stage = 1) {
    for (const n of [1, 2, 3]) $("step-" + n).hidden = true;
    $("loading-text").textContent = text;
    for (const n of [1, 2, 3]) $("ls-" + n).className = n < stage ? "done" : n === stage ? "on" : "";
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
    $("in-facts").value = JSON.stringify({claim_context: inputs.claim_context, bill_context: inputs.bill_context, allowed_evidence: inputs.allowed_evidence, category_assignments: inputs.category_assignments}, null, 2);
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
            sample_id: S.sample?.id};
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
        updateCounts(); if (!(kind === "policy" && S.sample?.requires_policy_upload)) S.sample = null;
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
      updateCounts(); if (!(kind === "policy" && S.sample?.requires_policy_upload)) S.sample = null;
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

  async function loadSample(id, demo = false) {
    unbanner();
    try {
      const sample = await api((demo ? "/api/demos/" : "/api/samples/") + encodeURIComponent(id));
      S.sample = sample;
      const existingPolicy = $("in-policy").value;
      const existingPdf = S.pdf.policy;
      resetFiles();
      fillInputs(sample.inputs);
      if (sample.requires_policy_upload) {
        $("in-policy").value = existingPolicy;
        if (existingPdf) setPdf("policy", existingPdf);
        updateCounts(); show(1);
        setStatus("policy", "", existingPolicy ? "Real-policy demo loaded. Check the policy, then Check my bill." : "Upload the real SBC PDF, then Check my bill. Claim and bill below are synthetic.");
        return;
      }
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
      const compiled = await api("/api/compile", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({document: payload.policy, document_id: payload.sample_id ? payload.sample_id + "/policy.md" : "uploaded-policy"})});
      if (S.sample?.requires_policy_upload && payload.claim_context) {
        payload.claim_context.policy_id = compiled.compilation.output.policy.id;
      }
      loading("Policy rules matched to exact quotes. Now the program recalculates each charge and compares…", 2);
      S.data = await api("/api/check", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...payload, ...compiled})});
      S.active = null; S.scenario = 0; S.pdfRun = fromPdf;
      renderRules(); renderResult(); show(2);
    } catch (e) { show(1); banner(e.message, e.kind, () => run()); }
  }

  /* ---------- step 3: optional rules + source ---------- */
  function ruleFacts(r) {
    const f = [];
    if (!r.covered) return [h("span", {class: "fact no"}, "Not covered — you pay the full charge")];
    f.push(h("span", {class: "fact"}, r.copay_cents ? `${money(r.copay_cents)} copay` : "No copay"));
    f.push(h("span", {class: "fact"}, r.coinsurance_bps ? `You pay ${pct(r.coinsurance_bps)}` : "No coinsurance"));
    f.push(h("span", {class: "fact"}, r.deductible_applies ? "Deductible first" : "Skips the deductible"));
    return f;
  }
  function ruleDescription(r) {
    const bits = [];
    if (r.conditions?.length) bits.push("Only if: " + r.conditions.join("; "));
    if (r.service_category) bits.push("Category assigned by a reviewer: " + r.service_category);
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
    card.append(h("b", {}, off ? "Read by the offline reader — no AI" : `Read by the AI reader (${compilation.backend})`),
      h("span", {class: "muted"}, off
        ? "A fixed pattern reader extracted the rules on the server. It understands common wording only."
        : `The AI only read the text. Every rule was matched to an exact quote before use (${compilation.attempts} attempt${compilation.attempts > 1 ? "s" : ""}). The math is done by the program.`),
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

    // rule cards
    const box = clear($("rules"));
    const netName = {in: "In-network", out: "Out-of-network"};
    if (out.coverage_gaps?.length) box.append(h("details", {class: "note warn"},
      h("summary", {}, "Parts of the policy this check does not cover"), h("ul", {}, out.coverage_gaps.map((gap) => h("li", {}, gap)))));
    box.append(h("h3", {}, "Your yearly limits"));
    const lim = h("div", {class: "limits"});
    for (const [net, t] of Object.entries(policy.networks)) {
      const card = ruleCard("net:" + net, `${netName[net] || net} providers`, null, net,
        ["deductible_cents", "oop_max_cents", "balance_billing"].map((k) => evidenceFor(`networks.${net}.${k}`)).filter(Boolean));
      card.insertBefore(h("dl", {class: "kv"},
        h("dt", {}, "Deductible"), h("dd", {}, money(t.deductible_cents)),
        h("dt", {}, "Out-of-pocket max"), h("dd", {}, money(t.oop_max_cents)),
        h("dt", {}, "Billing above the allowed price"), h("dd", {}, t.balance_billing === null ? "Unknown — needs contract evidence" : t.balance_billing ? "Allowed" : "Not allowed")), card.querySelector(".src"));
      lim.append(card);
    }
    box.append(lim);
    box.append(h("h3", {}, "What you pay for each service"));
    for (const b of policy.benefits) {
      const ev = evidenceFor("benefits." + b.id);
      const card = ruleCard("ben:" + b.id, (/network/i.test(b.label) ? b.label : `${b.label} · ${netName[b.network] || b.network}`), ruleDescription(b), null, ev ? [ev] : [], b);
      card.insertBefore(h("div", {class: "facts-row"}, ruleFacts(b)), card.querySelector(".src"));
      box.append(card);
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
      desc ? h("div", {class: "d"}, desc) : null,
      ambiguous ? h("div", {class: "d"}, ambiguous.ambiguity) : null,
      h("div", {class: "src"}, secs.length ? "From your policy: " + secs.join(", ") : "No source passage recorded"));
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
    $("source-legend").replaceChildren(h("i"), "Used for a rule", h("i", {class: "f"}), "Not understood");
    if (scroll && firstOn) firstOn.scrollIntoView({block: "center", behavior: "smooth"});
  }

  /* ---------- step 2: result ---------- */
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
    box.append(h("div", {class: "k"}, v.k), h("h1", {id: "verdict-title", tabindex: "-1"}, v.title));
    const fig = clear($("figures")), asm = clear($("assumptions")), lines = clear($("lines")), pick = clear($("scenario-pick"));
    if (r.status === "blocked") {
      box.append(h("p", {class: "why-text"}, v.text));
      fig.hidden = true; $("export").hidden = false;
      lines.append(h("div", {class: "note warn"}, "Charge-by-charge results appear once every rule in the policy is understood."));
      return;
    }
    fig.hidden = false;
    const s = r.summary, cs = ordered(), cur = cs[S.scenario] || cs[0];
    const range = (a, b) => (a === b ? money(a) : `${money(a)}–${money(b)}`);
    // The one answer: what you're asked to pay vs what your policy supports.
    box.append(h("div", {class: "answer", role: "group", "aria-label": "What you are asked to pay compared with what your policy supports"},
      ans("bill", "The bill asks you to pay", money(s.bill_patient_cents), "Medical bill"),
      h("span", {class: "ans-op", "aria-hidden": "true"}, "·"),
      ans("eob", "Your insurer says you owe", money(s.eob_patient_cents), "Insurer statement (EOB)"),
      h("span", {class: "ans-op", "aria-hidden": "true"}, "→"),
      ans("fp", "Your policy says you should pay", range(s.illustrated_min_patient_cents, s.illustrated_max_patient_cents),
        s.conditional ? "Recalculated · depends on facts we couldn’t confirm" : "Recalculated by Fineprint from your policy")));
    box.append(h("p", {class: "why-text"}, v.text, " ", h("span", {class: "small"}, "Open any charge below to see each step of the math and the policy sentence behind it.")));
    if (!s.conditional) {
      fig.append(figure("Still to pay, by our math", money(cur.fineprint_remaining_cents)));
      const paid = cur.lines.reduce((a, l) => a + (l.already_paid_cents || 0), 0);
      if (paid) fig.append(figure("Already paid", money(paid)));
    }
    fig.append(figure("Rules read by", S.data.compilation.backend === "fallback" ? "offline reader (no AI)" : "AI reader · math by program"));

    const issues = r.validation.filter((i) => i.severity !== "info");
    if (issues.length || r.limitations.length) {
      asm.append(h("details", {class: "note warn"}, h("summary", {}, issues.length ? `${issues.length} thing${issues.length > 1 ? "s" : ""} we assumed or couldn’t confirm` : "What this check doesn’t cover"),
        h("ul", {}, issues.map((i) => h("li", {}, i.message)), r.limitations.map((l) => h("li", {class: "muted"}, l)))));
    }
    if (s.conditional) {
      pick.append(h("label", {for: "scn", class: "muted"}, "Possible reading: "),
        h("select", {id: "scn", onchange: (e) => { S.scenario = +e.target.value; renderResult(); document.getElementById("scn").focus(); }},
          cs.map((c, i) => h("option", {value: i, selected: i === S.scenario}, `${i + 1} of ${cs.length} — you’d owe ${money(c.fineprint_patient_cents)}`))));
      const sc = r.scenarios.find((x) => x.id === cur.scenario_id);
      if (sc) asm.append(h("details", {class: "note"}, h("summary", {}, "What this reading assumes"), h("ul", {}, sc.assumptions.map((a) => h("li", {}, a)))));
    }
    const scenario = r.scenarios.find((x) => x.id === cur.scenario_id);
    cur.lines.forEach((l) => lines.append(lineCard(l, scenario)));
  }
  const ans = (cls, l, v, s) => h("div", {class: "ans " + cls}, h("div", {class: "l"}, l), h("div", {class: "v"}, v), h("div", {class: "s"}, s));
  const figure = (l, v, hl) => h("div", {class: "fig" + (hl ? " hl" : "")}, h("div", {class: "l"}, l), h("div", {class: "v"}, v));

  // Turn one program trace step into plain language. The numbers come from the program, never from AI.
  const centsText = (t) => t.replace(/(\d+) cents/g, (_, c) => money(+c));
  function plainStep(t, claim, res) {
    const e = t.explanation;
    let m;
    if (/^Allowance/.test(e)) return {c: "allowed_cents", what: "Allowed price",
      why: `The price your plan accepts for this service${claim.billed_cents ? ` (the provider charged ${money(claim.billed_cents)})` : ""}. Your share is based on this.`};
    if ((m = /^Deductible:.*remaining deductible (\d+) cents.*applies=(\w+)/.exec(e))) return {c: "deductible_cents", what: "Deductible",
      why: m[2] === "True" ? `Paid first, up to what’s left of your deductible (${money(+m[1])} left).` : "This service skips the deductible."};
    if ((m = /^Copay: up to (\d+) cents/.exec(e))) return {c: "copay_cents", what: "Copay", why: +m[1] ? `A flat ${money(+m[1])} for this service.` : "No copay for this service."};
    if ((m = /^Coinsurance: (\d+)\/10000 × (\d+) cents/.exec(e))) return {c: "coinsurance_cents", what: "Coinsurance",
      why: +m[1] ? `You pay ${pct(+m[1])} of the remaining ${money(+m[2])}.` : "No coinsurance for this service."};
    if ((m = /^Covered cost sharing capped by (\d+) cents/.exec(e))) return {c: null, what: "Yearly out-of-pocket limit",
      why: `You had ${money(+m[1])} left before your yearly maximum. Your share so far, after the cap:`};
    if (/^Network rule/.test(e)) return {c: "balance_cents", what: "Billing above the allowed price",
      why: res && res.network === "out" ? "Out-of-network: extra charges are yours only if the policy allows it." : "Charges above the allowed price are written off unless the policy allows extra billing."};
    if (/^Explicit exclusion/.test(e)) return {c: "noncovered_cents", what: "Not covered", why: "Your policy excludes this service, so the full charge is yours. It doesn’t count toward your limits."};
    return {c: null, what: centsText(e), why: ""};
  }

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
        text = e.component === "allowed_cents" ? `Your insurer used an allowed price of ${money(a)}; the contract supports ${money(b)}.`
          : `Your insurer charged you ${money(a)} in ${LABEL[e.component]}; your policy supports ${money(b)}.`;
      } else if (e.kind === "bill_vs_eob") {
        text = `The bill (${money(l.bill_patient_cents)}) is different from your insurer’s statement (${money(l.eob_patient_cents)}) by ${money(Math.abs(e.difference_cents))}. Ask about a missing credit or adjustment.`;
      } else text = `The bill asks for ${money(l.bill_patient_cents)}; your policy supports ${money(l.fineprint_patient_cents)}. Ask for an itemized explanation.`;
      return h("li", {}, text, h("div", {class: "cite"}, "Rule:", e.clause_ids.map((id) => clauseButton(id))));
    });
    const trace = (res && res.trace) || [];
    const steps = trace.map((t, i) => {
      const p = plainStep(t, claim, res);
      const insurer = p.c && res && Number.isInteger(eob[p.c]) && eob[p.c] !== res[p.c] ? eob[p.c] : null;
      return h("li", {class: insurer !== null ? "diff" : ""}, h("span", {class: "i"}, String(i + 1)),
        h("div", {class: "w"}, h("b", {}, p.what), p.why ? h("span", {}, p.why) : null),
        h("div", {class: "amt"}, money(t.amount_cents), insurer !== null ? h("span", {class: "ins"}, `Insurer: ${money(insurer)}`) : null),
        t.clause_ids?.length ? h("div", {class: "cite"}, t.clause_ids.map((id) => clauseButton(id))) : null);
    });
    if (steps.length) steps.push(h("li", {class: "total"}, h("span", {class: "i"}, "="), h("div", {class: "w"}, h("b", {}, "You should pay"),
      h("span", {}, `Insurer says ${money(l.eob_patient_cents)} · bill says ${money(l.bill_patient_cents)}`)), h("div", {class: "amt"}, money(l.fineprint_patient_cents))));
    const open = material.length > 0;
    return h("details", {class: "line " + (over > 0 || material.length ? "has" : "okl"), open},
      h("summary", {},
        h("div", {class: "line-name"}, h("b", {}, l.description), h("span", {class: "code"}, `Code ${l.code}`)),
        h("div", {class: "amts"}, amt("Bill", l.bill_patient_cents, "bill"), amt("Insurer", l.eob_patient_cents, "eob"), amt("Should pay", l.fineprint_patient_cents, "me")),
        h("div", {class: "line-end"}, h("span", {class: "chip " + chip[0]}, chip[1]), h("span", {class: "open"}, "Why"))),
      h("div", {class: "line-body"},
        reasons.length ? [h("h3", {}, "What doesn’t add up"), h("ul", {class: "why"}, reasons)] : h("p", {class: "ok-line"}, "✓ Your policy, the insurer’s statement and the bill agree on this charge."),
        l.already_paid_cents ? h("p", {class: "paid"}, `You already paid ${money(l.already_paid_cents)}${l.potential_refund_cents ? `, ${money(l.potential_refund_cents)} more than supported` : ""}.`) : null,
        steps.length ? [h("h3", {}, "How the program calculated it"), h("ol", {class: "calc"}, steps),
          h("details", {}, h("summary", {}, "Show the program’s exact steps"),
            h("ol", {class: "trace"}, trace.map((t) => h("li", {class: "raw"}, `${centsText(t.explanation)} → ${money(t.amount_cents)}`))))] : null));
  }
  const amt = (l, c, cls) => h("div", {class: cls}, h("div", {class: "l"}, l), h("div", {class: "v"}, money(c)));

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
      show(3); S.active = null; document.querySelectorAll(".rule").forEach((b) => b.setAttribute("aria-pressed", "false"));
      renderSource(true, i >= 0 ? [i, i + clause.text.length] : null);
      $("source-text").focus({preventScroll: true});
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
      updateCounts();
      const kind = t.closest(".doc")?.dataset.kind;
      if (!(kind === "policy" && S.sample?.requires_policy_upload)) S.sample = null;
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
      const demos = await api("/api/demos");
      for (const s of demos) list.append(h("button", {type: "button", class: "sample", onclick: () => loadSample(s.id, true)},
        h("span", {class: "kicker"}, "Real policy · synthetic claim & bill"), h("b", {}, s.title), h("span", {class: "go"}, "Load claim, then upload the policy PDF →")));
      for (const s of S.samples) list.append(h("button", {type: "button", class: "sample", onclick: () => loadSample(s.id)},
        h("span", {class: "kicker"}, "Synthetic sample" + (s.insurer ? " · " + s.insurer : "")), h("b", {}, s.title),
        s.summary ? h("span", {class: "sum"}, s.summary) : null, h("span", {class: "go"}, "Run this sample →")));
    } catch (e) { clear($("sample-list")).append(h("p", {class: "muted"}, "Samples couldn’t load. You can still paste your own documents.")); }
  }
  init();
})();
