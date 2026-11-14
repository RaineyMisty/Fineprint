"use strict";

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const usd = (cents) => new Intl.NumberFormat("en-US", {style:"currency",currency:"USD"}).format(cents / 100);
const decimal = (cents) => cents === null || cents === undefined ? "" : `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2,"0")}`;
const refs = (ids) => `<span class="citations">${[...new Set(ids)].map((id) => `<button class="citation" data-clause="${esc(id)}" aria-label="Read policy clause ${esc(id)}">§ ${esc(id)}</button>`).join("")}</span>`;
const sourceDoc = (kind, title) => `<details class="document"><summary>${esc(title)}</summary><pre>${esc(state.documents[kind] || "Normalized JSON import: export this case to inspect the supplied data. Original source documents were not included.")}</pre></details>`;
let state = null, original = null, selectedScenario = 0, activeStep = "policy", catalog = [], requestNumber = 0;

async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function error(message) {
  $("#error").textContent = message;
  $("#error").hidden = !message;
}

function announce(message) { $("#status").textContent = message; }

function setStep(step, focus = false) {
  activeStep = step;
  for (const name of ["policy", "claim", "bill"]) {
    const active = name === step;
    $(`#panel-${name}`).hidden = !active;
    $(`#tab-${name}`).setAttribute("aria-selected", String(active));
    $(`#tab-${name}`).tabIndex = active ? 0 : -1;
  }
  if (focus) $(`#tab-${step}`).focus();
}

function renderCatalog() {
  $("#case-list").innerHTML = catalog.map((item, index) => `<button class="case-button" data-case="${esc(item.id)}" aria-current="${state?.case.id === item.id}"><small>CASE 0${index + 1}</small>${esc(item.title)}<small>${esc(item.insurer)}</small></button>`).join("");
}

async function loadCase(id) {
  const ticket = ++requestNumber;
  error(""); announce("Loading case");
  try {
    const data = await api(`/api/cases/${encodeURIComponent(id)}`);
    if (ticket !== requestNumber) return;
    state = data; original = structuredClone(data); selectedScenario = 0; activeStep = "policy";
    render(); announce("Case loaded. Start with the policy.");
  } catch (err) { if (ticket === requestNumber) error(err.message); }
}

function renderValidation() {
  const issues = state.report.validation;
  const errors = issues.filter((issue) => issue.severity === "error");
  $("#validation").innerHTML = `<details class="validation ${errors.length ? "has-errors" : issues.length ? "has-warnings" : ""}"><summary>${errors.length ? `${errors.length} consistency error(s) · calculation blocked` : issues.length ? `Documents linked · ${issues.length} item(s) to review` : "✓ All documents linked · consistency checks passed"}</summary>${issues.length ? `<ul>${issues.map((issue) => `<li><strong>${esc(issue.code)}</strong>: ${esc(issue.message)} <span class="issue-path">(${esc(issue.path)})</span></li>`).join("")}</ul>` : "Member, policy, claim, provider, date, code, line links and accounting totals agree. Policy evaluation may still reveal incorrect cost sharing."}</details>`;
}

function policyPanel() {
  const policy = state.case.policy;
  return `<div class="two-col">${Object.entries(policy.networks).map(([network, terms]) => `<article class="card"><div class="card-title"><h3>${network === "in" ? "In-network" : "Out-of-network"}</h3><span class="pill">INDIVIDUAL / ANNUAL</span></div><div class="terms"><div><span class="term-label">Deductible</span><span class="term-value">${usd(terms.deductible_cents)}</span>${refs([terms.deductible_clause])}</div><div><span class="term-label">Out-of-pocket maximum</span><span class="term-value">${usd(terms.oop_max_cents)}</span>${refs([terms.oop_clause])}</div></div><p class="term-note">${terms.balance_billing ? "This fictional plan permits charges above the allowance to be billed to the member, outside the OOP cap." : "Covered charges above the allowance are a contractual write-off."} ${refs([terms.network_clause])}</p></article>`).join("")}</div>
  <article class="card"><div class="card-title"><div><h3><span class="section-number">01 /</span>Your coverage, connected</h3><p>${esc(policy.name)} · ${esc(policy.effective_from)} to ${esc(policy.effective_to)}</p></div><span class="pill">CLAUSE-LINKED RULES</span></div>${policy.benefits.map((rule) => `<div class="benefit"><div><span class="benefit-title">${esc(rule.label)}</span><p>${esc(rule.codes.join(", "))} · ${rule.network}-network · ${rule.covered ? `${rule.deductible_applies ? "Deductible applies" : "Deductible waived"}; ${usd(rule.copay_cents)} copay; ${rule.coinsurance_bps / 100}% member coinsurance` : "Excluded: full charge outside the OOP cap"}${rule.ambiguity_group ? " · Ambiguous wording: compare interpretations" : ""}</p></div>${refs(rule.clause_ids)}</div>`).join("")}</article>
  <div class="source-note"><strong>Terms are rules. Evidence supplies the facts.</strong>Fineprint uses the structured policy to recalculate cost sharing. Allowed amounts, network status and spending before this claim are separate inputs. The offline fallback reads curated JSON; it does not extract arbitrary prose or PDFs.</div>
  <article class="card"><details id="clauses"><summary>Read the policy clauses & source locations</summary>${policy.clauses.map((clause) => `<div class="clause" id="clause-${esc(clause.id)}"><span class="clause-label">§ ${esc(clause.id)}</span> <small>${esc(clause.location)}</small><p>${esc(clause.text)}</p></div>`).join("")}</details></article>${sourceDoc("policy", "View original synthetic policy summary")}
  <div class="next-row"><p>Next: follow each service through the insurer’s math.</p><button class="primary-button" data-next="claim">Review the claim →</button></div>`;
}

function scenarioToolbar() {
  if (!state.report.scenarios.length) return "";
  const summary = state.report.summary;
  return `<div class="scenario-toolbar"><label for="scenario-${activeStep}">${summary.scenario_count === 1 ? "CALCULATION SCENARIO" : `${summary.scenario_count} EXPLICIT SCENARIOS`}</label><select class="scenario-select" id="scenario-${activeStep}" aria-label="Choose calculation scenario">${state.report.scenarios.map((scenario, i) => `<option value="${i}" ${i === selectedScenario ? "selected" : ""}>${i + 1}. ${usd(scenario.patient_cents)} patient total${scenario.conditional ? " · conditional" : " · supported inputs"}</option>`).join("")}</select></div>`;
}

function assumptions() {
  const scenario = state.report.scenarios[selectedScenario];
  const summary = state.report.summary;
  return scenario.conditional ? `<div class="source-note warning"><strong>Conditional result · resolve the assumptions before drawing a conclusion</strong><ul class="assumptions">${scenario.assumptions.map((item) => `<li>${esc(item)}</li>`).join("")}</ul><p>The scenarios shown span ${usd(summary.illustrated_min_patient_cents)}–${usd(summary.illustrated_max_patient_cents)}. Missing-fact endpoints illustrate possibilities; they are not a complete set of outcomes or guaranteed savings.</p></div>` : `<div class="source-note"><strong>Independent policy evaluation</strong>The contractual allowance and opening spending are supplied as supporting evidence. Fineprint calculates cost sharing from policy rules, separately from EOB amounts. This remains a demonstration of the supported plan rules.</div>`;
}

function blocked() {
  return `<div class="source-note warning"><strong>Recalculation is blocked</strong>${esc(state.report.blocked_reason)} Correct the normalized JSON or update the supporting facts below.</div>`;
}

function lineAudit(result, index) {
  const claim = state.case.claim.lines.find((line) => line.id === result.claim_line_id);
  const compared = state.report.comparisons[selectedScenario].lines.find((line) => line.claim_line_id === claim.id);
  const evidence = state.case.allowed_evidence[claim.id];
  const components = [["allowed_cents","Allowed amount (evidence)"],["deductible_cents","Deductible"],["copay_cents","Copay"],["coinsurance_cents","Coinsurance"],["noncovered_cents","Excluded charges"],["balance_cents","Balance billing"],["insurer_paid_cents","Insurer payment"],["adjustment_cents","Contractual write-off"]];
  return `<details class="audit-line" ${index === 0 ? "open" : ""}><summary><span class="line-heading"><span><span class="code">${esc(claim.code)}</span><strong>${esc(claim.description)}</strong></span><span class="${compared.eob_difference_cents > 0 ? "amount-warning" : "muted"}">${compared.eob_difference_cents > 0 ? `${usd(compared.eob_difference_cents)} EOB amount to review` : compared.eob_difference_cents < 0 ? "EOB is lower in this scenario" : "EOB cost sharing matches"}</span></span></summary>
  <p class="detail-meta">${esc(claim.id)} · ${esc(claim.service_date)} · ${esc(claim.provider_id)} · evaluated ${esc(result.network)}-network<br>Allowance evidence: ${esc(evidence?.source || "unknown")} — ${esc(evidence?.reference || "Not supplied")}</p><div class="table-scroll"><table><thead><tr><th>Component</th><th class="number">Insurer EOB</th><th class="number">Fineprint</th><th class="number">EOB − Fineprint</th></tr></thead><tbody>${components.map(([key,label]) => `<tr><td>${label}</td><td class="number">${usd(claim.insurer[key])}</td><td class="number">${usd(result[key])}</td><td class="number ${claim.insurer[key] !== result[key] ? "difference" : "muted"}">${usd(claim.insurer[key] - result[key])}</td></tr>`).join("")}<tr class="total-row"><td>Patient responsibility</td><td class="number">${usd(compared.eob_patient_cents)}</td><td class="number">${usd(result.patient_cents)}</td><td class="number">${usd(compared.eob_difference_cents)}</td></tr></tbody></table></div>
  <details class="audit-trace"><summary>How Fineprint computed this line · policy citations</summary><ol class="trace-list">${result.trace.map((step) => `<li>${esc(step.explanation)} <span class="trace-amount">${usd(step.amount_cents)}</span>${refs(step.clause_ids)}</li>`).join("")}</ol><p class="detail-meta">Deductible spending: ${usd(result.opening_deductible_cents)} → ${usd(result.closing_deductible_cents)} · OOP spending: ${usd(result.opening_oop_cents)} → ${usd(result.closing_oop_cents)}</p></details>
  ${compared.explanations.filter((item) => item.kind === "eob_vs_fineprint" || item.kind === "match").map((item) => `<div class="explanation">${esc(item.message)}${refs(item.clause_ids)}</div>`).join("")}</details>`;
}

function factForm() {
  return `<article class="card"><details><summary>Resolve missing facts or try a different scenario</summary><p class="form-help">Enter documented amounts in USD, with at most two decimal places. Blank amounts mean unknown. Opening spending is immediately before this claim. Updates are temporary; export JSON to keep them.</p><form id="facts-form" class="evidence-form">${Object.entries(state.case.claim.accumulators).map(([net, accum]) => `<fieldset><legend>${net === "in" ? "In-network" : "Out-of-network"} spending before this claim</legend><div class="field-grid"><label>Deductible already satisfied (USD)<input inputmode="decimal" name="ded:${net}" value="${decimal(accum.deductible_paid_cents)}" placeholder="Unknown"></label><label>OOP already satisfied (USD)<input inputmode="decimal" name="oop:${net}" value="${decimal(accum.oop_paid_cents)}" placeholder="Unknown"></label></div></fieldset>`).join("")}${state.case.claim.lines.map((line, index) => {const fact = state.case.allowed_evidence[line.id];return `<fieldset><legend>${esc(line.code)} · ${esc(line.id)} · ${esc(line.description)}</legend><div class="field-grid"><label>Provider network<select name="net:${index}">${["in","out","unknown"].map((net) => `<option value="${net}" ${line.network === net ? "selected" : ""}>${esc(net)}</option>`).join("")}</select></label><label>Supporting allowance (USD)<input inputmode="decimal" name="allowed:${index}" value="${decimal(fact?.allowed_cents)}" placeholder="Unknown"></label><label>Allowance source<select name="source:${index}">${["contract","eob","unknown"].map((source) => `<option value="${source}" ${(fact?.source || "unknown") === source ? "selected" : ""}>${esc(source)}</option>`).join("")}</select></label><label>Source reference<input name="ref:${index}" value="${esc(fact?.reference || "Not supplied")}" required maxlength="500"></label></div></fieldset>`;}).join("")}<div class="form-actions"><button class="primary-button" type="submit">Recalculate with these facts ↗</button><span>Rules and EOB observations stay separate from your supporting inputs.</span></div></form></details></article>`;
}

function claimPanel() {
  const report = state.report;
  return `${report.status === "blocked" ? blocked() : `${scenarioToolbar()}${assumptions()}<div class="metric-grid"><div class="metric"><label>INSURER’S PATIENT TOTAL</label><strong>${usd(report.comparisons[selectedScenario].eob_patient_cents)}</strong><small>Recorded on the EOB</small></div><div class="metric highlight"><label>FINEPRINT’S PATIENT TOTAL</label><strong>${usd(report.scenarios[selectedScenario].patient_cents)}</strong><small>${report.scenarios[selectedScenario].conditional ? "Subject to this scenario’s assumptions" : "Calculated from the structured policy"}</small></div><div class="metric"><label>EOB − FINEPRINT</label><strong>${usd(report.comparisons[selectedScenario].eob_difference_cents)}</strong><small>Positive: EOB assigns more to the patient</small></div></div><article class="card"><div class="card-title"><div><h3><span class="section-number">02 /</span>The math behind each service</h3><p>Expand a line to compare every component and inspect the calculation trace.</p></div></div>${report.scenarios[selectedScenario].lines.map(lineAudit).join("")}</article>`}${factForm()}${sourceDoc("claim", "View original synthetic insurer EOB")}<div class="next-row"><p>Next: connect this result to the hospital’s actual balance.</p><button class="primary-button" data-next="bill">Review the bill →</button></div>`;
}

function billPanel() {
  const report = state.report;
  if (report.status === "blocked") return blocked() + sourceDoc("bill", "View original bill");
  const comparison = report.comparisons[selectedScenario];
  const conditional = report.scenarios[selectedScenario].conditional;
  return `${scenarioToolbar()}${assumptions()}<div class="bill-banner"><div><p class="eyebrow">${conditional ? "CONDITIONAL AMOUNT TO REVIEW" : "POTENTIAL EXCESS PATIENT RESPONSIBILITY"}</p><h3>${comparison.potential_overpayment_cents > 0 ? "An amount worth questioning." : "Check the balance against the policy."}</h3><p>Hospital patient payments + balance due, compared with Fineprint’s calculated total. ${conditional ? "This depends on unverified assumptions. Obtain the missing evidence before treating it as a correction." : "Use the clause references to request an explanation or corrected adjudication."}</p></div><span class="big-number">${usd(comparison.potential_overpayment_cents)}</span></div>
  <div class="metric-grid"><div class="metric"><label>HOSPITAL BALANCE DUE</label><strong>${usd(comparison.bill_balance_due_cents)}</strong><small>Patient already paid ${usd(comparison.already_paid_cents)}</small></div><div class="metric highlight"><label>FINEPRINT REMAINING</label><strong>${usd(comparison.fineprint_remaining_cents)}</strong><small>After prior payments, by service line</small></div><div class="metric"><label>POTENTIAL REFUND</label><strong>${usd(comparison.potential_refund_cents)}</strong><small>Payments above this scenario’s line liability</small></div></div>
  <article class="card"><div class="card-title"><div><h3><span class="section-number">03 /</span>Three documents. One view.</h3><p>Patient totals include amounts already paid. Remaining balances account for those payments.</p></div></div><div class="table-scroll"><table><thead><tr><th>Service</th><th class="number">Fineprint total</th><th class="number">EOB total</th><th class="number">Bill total</th><th class="number">Paid</th><th class="number">Bill due</th><th class="number">Fineprint remaining</th></tr></thead><tbody>${comparison.lines.map((line) => `<tr><td><span class="code">${esc(line.code)}</span>${esc(line.claim_line_id)}</td><td class="number">${usd(line.fineprint_patient_cents)}</td><td class="number">${usd(line.eob_patient_cents)}</td><td class="number ${line.potential_overpayment_cents ? "difference" : ""}">${usd(line.bill_patient_cents)}</td><td class="number">${usd(line.already_paid_cents)}</td><td class="number">${usd(line.bill_balance_due_cents)}</td><td class="number">${usd(line.fineprint_remaining_cents)}</td></tr>`).join("")}<tr class="total-row"><td>Total</td>${[comparison.fineprint_patient_cents, comparison.eob_patient_cents, comparison.bill_patient_cents, comparison.already_paid_cents, comparison.bill_balance_due_cents, comparison.fineprint_remaining_cents].map((n) => `<td class="number">${usd(n)}</td>`).join("")}</tr></tbody></table></div>${comparison.lines.flatMap((line) => line.explanations.filter((item) => item.kind.startsWith("bill_")).map((item) => `<div class="explanation"><strong>${esc(line.code)} · ${esc(line.claim_line_id)}</strong> — ${esc(item.message)} Difference: ${usd(item.difference_cents)}.${refs(item.clause_ids)}</div>`)).join("")}</article>
  <article class="card"><div class="card-title"><h3>Questions to bring to a review</h3></div><ol class="questions"><li>Ask the insurer for its line-by-line deductible, copay, coinsurance and OOP calculations. Compare the cited policy clauses in the Claim step.</li><li>Ask the provider to reconcile the EOB with all insurance credits, contractual adjustments and prior patient payments.</li>${conditional ? "<li>Confirm network participation, the contracted allowance, prior spending and which conflicting policy clause governs before relying on a scenario.</li>" : ""}<li>Keep the original policy, EOB and itemized bill with the exported case for a documented review. The results are an estimate under the supported rules.</li></ol></article>
  <article class="card"><details><summary>Inspect the links across all three documents</summary><div class="table-scroll"><table class="link-table"><thead><tr><th>Member / claim</th><th>Provider / date</th><th>Code / claim line</th><th>Bill lines</th></tr></thead><tbody>${report.links.map((link) => `<tr><td>${esc(link.member_id)}<br>${esc(link.claim_id)}</td><td>${esc(link.provider_id)}<br>${esc(link.service_date)}</td><td>${esc(link.code)} / ${esc(link.claim_line_id)}</td><td>${esc(link.bill_line_ids.join(", "))}</td></tr>`).join("")}</tbody></table></div></details></article>${sourceDoc("bill", "View original synthetic itemized bill")}<details class="document"><summary>Supported scope and current limits</summary><ul class="questions">${report.limitations.map((line) => `<li>${esc(line)}</li>`).join("")}</ul></details><div class="next-row"><button class="secondary-button" data-next="claim">← Back to claim</button><button id="export-bill" class="primary-button" data-export>Export case JSON ↓</button></div>`;
}

function renderPanels() {
  $("#panel-policy").innerHTML = policyPanel();
  // Distinct IDs keep the scenario dropdown labels accessible in hidden panels too.
  const current = activeStep;
  activeStep = "claim"; $("#panel-claim").innerHTML = claimPanel();
  activeStep = "bill"; $("#panel-bill").innerHTML = billPanel();
  activeStep = current;
  setStep(current);
}

function render() {
  $("#case-title").textContent = state.case.title;
  $("#insurer").textContent = state.case.policy.insurer;
  $("#case-summary").textContent = catalog.find((item) => item.id === state.case.id)?.summary || "Imported normalized case · data stays in this local session.";
  $("#data-badge").textContent = state.case.synthetic ? "SYNTHETIC DATA ONLY" : "IMPORTED CASE · LOCAL SESSION";
  $("#download").disabled = false; $("#reset").disabled = false;
  renderCatalog(); renderValidation(); renderPanels();
}

function exportCase() {
  if (!state) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(state.case,null,2) + "\n"], {type:"application/json"}));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = "fineprint-case.json"; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function parseMoney(text) {
  text = text.trim();
  if (!text) return null;
  if (!/^\d+(?:\.\d{1,2})?$/.test(text)) throw new Error("Use nonnegative USD amounts with at most two decimal places.");
  const [whole, fraction = ""] = text.split(".");
  const value = Number(whole) * 100 + Number(fraction.padEnd(2,"0"));
  if (!Number.isSafeInteger(value) || value > 1e12) throw new Error("Amount is too large.");
  return value;
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.case) return void loadCase(button.dataset.case);
  if (button.dataset.step) return void setStep(button.dataset.step);
  if (button.dataset.next) return void setStep(button.dataset.next, true);
  if (button.dataset.clause && state) {
    setStep("policy", true); $("#clauses").open = true;
    document.getElementById(`clause-${button.dataset.clause}`)?.scrollIntoView({block:"center"});
  }
  if (button.id === "download" || button.hasAttribute("data-export")) exportCase();
  if (button.id === "reset" && original) {
    ++requestNumber; state = structuredClone(original); selectedScenario = 0; error(""); render(); announce("Original case restored");
  }
});

$(".steps").addEventListener("keydown", (event) => {
  const names = ["policy","claim","bill"], index = names.indexOf(activeStep);
  const next = {ArrowRight:names[(index + 1) % 3],ArrowLeft:names[(index + 2) % 3],Home:"policy",End:"bill"}[event.key];
  if (next) { event.preventDefault(); setStep(next,true); }
});

document.addEventListener("change", (event) => {
  if (event.target.matches(".scenario-select")) { selectedScenario = Number(event.target.value); renderPanels(); announce("Calculation scenario updated"); }
});

document.addEventListener("submit", async (event) => {
  if (event.target.id !== "facts-form") return;
  event.preventDefault(); error("");
  const button = event.target.querySelector("button[type=submit]");
  const ticket = ++requestNumber;
  try {
    const data = new FormData(event.target), updated = structuredClone(state.case), documents = state.documents;
    for (const [net, accum] of Object.entries(updated.claim.accumulators)) {
      accum.deductible_paid_cents = parseMoney(data.get(`ded:${net}`));
      accum.oop_paid_cents = parseMoney(data.get(`oop:${net}`));
    }
    updated.claim.lines.forEach((line,index) => {
      line.network = data.get(`net:${index}`);
      const allowed = parseMoney(data.get(`allowed:${index}`));
      const source = allowed === null ? "unknown" : data.get(`source:${index}`);
      if (allowed !== null && source === "unknown") throw new Error("Choose a documented allowance source or leave the amount blank.");
      updated.allowed_evidence[line.id] = {allowed_cents:allowed, source, reference:data.get(`ref:${index}`).trim()};
    });
    button.disabled = true;
    const result = await api("/api/analyze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(updated)});
    if (ticket !== requestNumber) return;
    state = {...result,documents}; selectedScenario = 0; render(); announce("Facts updated and case recalculated");
  } catch (err) { if (ticket === requestNumber) error(err.message); }
  finally { button.disabled = false; }
});

$("#import-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const ticket = ++requestNumber;
  error("");
  try {
    if (file.size > 1024 * 1024) throw new Error("Case JSON must be at most 1 MiB.");
    const payload = JSON.parse(await file.text());
    const result = await api("/api/analyze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    if (ticket !== requestNumber) return;
    state = result; original = structuredClone(result); selectedScenario = 0; activeStep = "policy"; render(); announce("Imported case analyzed");
  } catch (err) { if (ticket === requestNumber) error(err.message); }
  finally { event.target.value = ""; }
});

(async () => {
  try { catalog = await api("/api/cases"); renderCatalog(); if (catalog.length) await loadCase(catalog[0].id); }
  catch (err) { error(`Unable to load Fineprint: ${err.message}`); }
})();
