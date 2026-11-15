'use strict';
const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = cents => Number.isSafeInteger(cents) ? new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents / 100) : '—';
const percent = value => typeof value === 'number' ? new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:1}).format(value) : '—';
const splitLabel = value => value === 'held_out' ? 'Held-out' : 'Seen';
let data;
let evaluation;
function route() {
  const page = location.hash.slice(1).split('/')[0] || 'overview';
  const current = ['overview','explorer','evaluation'].includes(page) ? page : 'overview';
  document.querySelectorAll('.screen').forEach(el => { el.hidden = el.id !== current; });
  document.querySelectorAll('nav a').forEach(el => { if (el.hash === `#${current}`) el.setAttribute('aria-current','page'); else el.removeAttribute('aria-current'); });
  if (data && current === 'explorer') renderExplorer();
  if (current === 'evaluation') {
    if (evaluation) renderEvaluation();
    else if (!$('#evaluation-content').textContent) $('#evaluation-content').textContent = 'Loading evaluation…';
  }
}
function renderOverview() {
  const cases = data.cases;
  const ready = cases.filter(c => c.report.status === 'ready').length;
  const flagged = cases.filter(c => c.report.comparisons.some(s => s.lines.some(l => l.eob_difference_cents !== 0))).length;
  $('#headlines').innerHTML = [[cases.length,'Synthetic cases'],[ready,'Calculated cases'],[flagged,'Cases with EOB differences'],[percent(data.evaluation.groups.all.end_to_end.rate),'End-to-end success']].map(([v,label]) => `<div class="stat"><strong>${escapeHTML(v)}</strong><span>${label}</span></div>`).join('');
  $('#case-list').innerHTML = cases.map(c => `<a class="case-row" href="#explorer/${encodeURIComponent(c.id)}"><div><strong>${escapeHTML(c.title)}</strong><small>${splitLabel(c.split)} · ${escapeHTML(c.report.status)}</small></div><span class="case-value">${c.report.summary ? money(c.report.summary.eob_patient_cents) : 'Blocked'}<small>${c.report.summary ? 'EOB patient total' : 'Parser abstention'}</small></span><span aria-hidden="true">↗</span></a>`).join('');
}
const fieldLabels = {allowed_cents:'Allowance',deductible_cents:'Deductible',copay_cents:'Copay',coinsurance_cents:'Coinsurance',noncovered_cents:'Noncovered',balance_cents:'Balance billing',patient_cents:'Patient total',insurer_paid_cents:'Insurer paid',adjustment_cents:'Write-off'};
const label = value => fieldLabels[value] || value.replace(/_/g,' ');
const networkLabel = value => value === 'in' ? 'In-network' : value === 'out' ? 'Out-of-network' : value;
const signedMoney = value => Number.isSafeInteger(value) ? `${value > 0 ? '+' : ''}${money(value)}` : '—';
function evidenceSpans(c) {
  const chars = Array.from(c.document);
  const unique = new Map();
  for (const rule of c.compilation?.output.rule_evidence || []) for (const span of rule.evidence) {
    if (Number.isInteger(span.start) && span.start >= 0 && span.end > span.start && span.end <= chars.length && chars.slice(span.start,span.end).join('') === span.quote) unique.set(`${span.start}-${span.end}`,span);
  }
  return [...unique.values()].sort((a,b) => a.start-b.start || a.end-b.end);
}
const evidenceID = span => `evidence-${span.start}-${span.end}`;
function spanLink(c,span,text) {
  return `<a class="citation" href="#explorer/${encodeURIComponent(c.id)}/${evidenceID(span)}">${escapeHTML(text || span.section)}</a>`;
}
function citations(c,ids) {
  return [...new Set(ids)].map(id => {
    const clause = c.compilation.output.policy.clauses.find(item => item.id === id);
    const span = evidenceSpans(c).find(item => item.section === clause?.location || item.quote === clause?.text);
    return span ? spanLink(c,span,id) : `<span class="muted">${escapeHTML(id)}</span>`;
  }).join(' ');
}
function policyText(c) {
  const chars = Array.from(c.document);
  let cursor = 0, html = '';
  for (const span of evidenceSpans(c)) {
    if (span.start < cursor) continue;
    html += escapeHTML(chars.slice(cursor,span.start).join(''));
    html += `<mark id="${evidenceID(span)}" tabindex="-1">${escapeHTML(chars.slice(span.start,span.end).join(''))}</mark>`;
    cursor = span.end;
  }
  return html + escapeHTML(chars.slice(cursor).join(''));
}
function compiledRules(c) {
  const policy = c.compilation.output.policy;
  return c.compilation.output.rule_evidence.map(rule => {
    const parts = rule.rule_path.split('.');
    let title, value;
    if (parts[0] === 'networks') {
      title = `${networkLabel(parts[1])} · ${label(parts[2])}`;
      const raw = policy.networks[parts[1]][parts[2]];
      value = parts[2].endsWith('_cents') ? money(raw) : raw ? 'Permitted' : 'Prohibited';
    } else {
      const benefit = policy.benefits.find(b => b.id === parts.slice(1).join('.'));
      title = benefit?.label || rule.rule_path;
      value = benefit ? `${benefit.covered ? 'Covered' : 'Excluded'} · Deductible ${benefit.deductible_applies ? 'applies' : 'waived'} · ${money(benefit.copay_cents)} copay · ${percent(benefit.coinsurance_bps / 10000)} coinsurance` : '—';
    }
    const spans = evidenceSpans(c);
    return `<div class="rule"><strong>${escapeHTML(title)}</strong><div>${escapeHTML(value)}</div><div class="citations">${rule.evidence.filter(e => spans.some(s => s.start === e.start && s.end === e.end)).map(e => spanLink(c,e)).join(' ')}</div></div>`;
  }).join('');
}
function renderReconciliation(c,scenarioID) {
  const scenario = c.report.scenarios.find(s => s.id === scenarioID) || c.report.scenarios[0];
  const comparison = c.report.comparisons.find(s => s.scenario_id === scenario.id);
  const summary = c.report.summary;
  $('#reconciliation').innerHTML = `<div class="stats">${[[money(summary.eob_patient_cents),'EOB patient total'],[money(scenario.patient_cents),'Fineprint patient total'],[money(summary.bill_patient_cents),'Bill patient total'],[scenario.conditional ? 'Conditional' : signedMoney(summary.eob_patient_cents-scenario.patient_cents),'EOB − Fineprint']].map(([v,t]) => `<div class="stat"><strong>${escapeHTML(v)}</strong><span>${t}</span></div>`).join('')}</div>
    ${scenario.assumptions.length ? `<details class="panel assumptions" open><summary>Scenario assumptions · ${escapeHTML(scenario.id)}</summary><ul>${scenario.assumptions.map(a => `<li>${escapeHTML(a)}</li>`).join('')}</ul></details>` : ''}
    ${scenario.lines.map(line => {
      const original = c.case.claim.lines.find(l => l.id === line.claim_line_id);
      const compared = comparison.lines.find(l => l.claim_line_id === line.claim_line_id);
      const issues = compared.explanations.filter(e => e.kind !== 'match');
      const allCitations = [...new Set(line.trace.flatMap(t => t.clause_ids))];
      return `<article class="panel line-card"><div class="section-heading"><h3>${escapeHTML(line.claim_line_id)} · ${escapeHTML(original.description)}</h3><span class="badge">${escapeHTML(original.code)} · ${escapeHTML(networkLabel(line.network))}</span></div>
        <div class="table-scroll" tabindex="0" role="region" aria-label="${escapeHTML(line.claim_line_id)} EOB comparison"><table><thead><tr><th>Component</th><th>EOB</th><th>Fineprint</th><th>EOB − Fineprint</th></tr></thead><tbody>${Object.entries(fieldLabels).map(([key,title]) => {
          const eob = key === 'patient_cents' ? compared.eob_patient_cents : original.insurer[key];
          const diff = Number.isSafeInteger(eob) ? eob-line[key] : null;
          return `<tr class="${diff ? 'difference' : ''}"><th scope="row">${title}</th><td>${money(eob)}</td><td>${money(line[key])}</td><td>${signedMoney(diff)}</td></tr>`;
        }).join('')}</tbody></table></div>
        <div class="accumulators"><span>Deductible ${money(line.opening_deductible_cents)} → ${money(line.closing_deductible_cents)}</span><span>OOP ${money(line.opening_oop_cents)} → ${money(line.closing_oop_cents)}</span></div>
        <div class="citations">${citations(c,allCitations)}</div>
        <details><summary>Bill reconciliation</summary><div class="table-scroll"><table><tbody>${[['Bill patient total',compared.bill_patient_cents],['Already paid',compared.already_paid_cents],['Bill balance due',compared.bill_balance_due_cents],['Fineprint remaining',compared.fineprint_remaining_cents],['Potential refund',compared.potential_refund_cents],['Potential overpayment',compared.potential_overpayment_cents]].map(([t,v]) => `<tr><th scope="row">${t}</th><td>${money(v)}</td></tr>`).join('')}</tbody></table></div></details>
        <div class="discrepancies"><h3>${issues.length ? (scenario.conditional ? 'Conditional differences' : 'Discrepancies') : 'Match'}</h3>${issues.map(e => `<div class="issue"><span>${escapeHTML(e.kind.replace(/_/g,' '))} · ${escapeHTML(label(e.component))}</span><strong>${signedMoney(e.difference_cents)}</strong><div class="citations">${citations(c,e.clause_ids)}</div></div>`).join('')}</div></article>`;
    }).join('')}`;
}
function renderExplorer() {
  const parts = location.hash.slice(1).split('/');
  let requested;
  try { requested = decodeURIComponent(parts[1] || ''); } catch { requested = ''; }
  const c = data.cases.find(item => item.id === requested) || data.cases[0];
  $('#explorer-content').innerHTML = `<label class="case-picker">Case<select id="case-select">${data.cases.map(item => `<option value="${escapeHTML(item.id)}" ${item.id === c.id ? 'selected' : ''}>${escapeHTML(item.title)} · ${splitLabel(item.split)}</option>`).join('')}</select></label>
    <div class="section-heading"><h2>${escapeHTML(c.title)}</h2><span class="badge">${splitLabel(c.split)} · ${c.report.status === 'blocked' ? 'parser abstained' : c.report.summary.conditional ? 'Conditional' : 'Calculated'}</span></div>
    ${c.report.status === 'blocked' ? '<div class="panel abstained">parser abstained</div>' : `<div class="section-heading"><h3>EOB vs Fineprint</h3><label>Scenario <select id="scenario-select">${c.report.scenarios.map(s => `<option value="${escapeHTML(s.id)}">${escapeHTML(s.id)} · ${money(s.patient_cents)}${s.conditional ? ' · Conditional' : ''}</option>`).join('')}</select></label></div><div id="reconciliation"></div>`}
    <div class="evidence-grid"><section class="panel"><h3>Policy text · evidence</h3><pre class="policy-text">${policyText(c)}</pre></section>${c.compilation ? `<section class="panel"><h3>Compiled rules</h3>${compiledRules(c)}</section>` : ''}</div>`;
  $('#case-select').addEventListener('change',event => { location.hash = `explorer/${encodeURIComponent(event.target.value)}`; });
  if (c.report.status !== 'blocked') {
    const select = $('#scenario-select');
    if (activeScenario.caseID === c.id && c.report.scenarios.some(s => s.id === activeScenario.id)) select.value = activeScenario.id;
    renderReconciliation(c,select.value);
    select.addEventListener('change',event => { activeScenario = {caseID:c.id,id:event.target.value}; renderReconciliation(c,event.target.value); });
  }
  if (/^evidence-\d+-\d+$/.test(parts[2] || '')) {
    const target = document.getElementById(parts[2]);
    if (target) { target.scrollIntoView({block:'center'}); target.focus({preventScroll:true}); }
  }
}
let activeScenario = {};
function renderEvaluation() {
  const groups = [['seen','Seen'],['held_out','Held-out'],['all','All']];
  const metrics = [
    ['Extraction P',g => g.extraction.precision,g => `${g.extraction.tp} / ${g.extraction.tp + g.extraction.fp}`],
    ['Extraction R',g => g.extraction.recall,g => `${g.extraction.tp} / ${g.extraction.tp + g.extraction.fn}`],
    ['Calc exact',g => g.calculation.accuracy,g => `${g.calculation.exact} / ${g.calculation.total}`],
    ['Discrepancy P',g => g.discrepancy.precision,g => `${g.discrepancy.tp} / ${g.discrepancy.tp + g.discrepancy.fp}`],
    ['Discrepancy R',g => g.discrepancy.recall,g => `${g.discrepancy.tp} / ${g.discrepancy.tp + g.discrepancy.fn}`],
    ['FPR',g => g.discrepancy.false_positive_rate,g => `${g.discrepancy.fp} / ${g.discrepancy.labeled_cases - g.discrepancy.tp - g.discrepancy.fn}`],
    ['Traceability',g => g.evidence.traceability_rate,g => `${g.evidence.valid_rules} / ${g.evidence.emitted_rules}`],
    ['Evidence coverage',g => g.evidence.coverage_rate,g => `${g.evidence.valid_rules} / ${g.evidence.gold_rules}`],
    ['End-to-end',g => g.end_to_end.rate,g => `${g.end_to_end.success} / ${g.end_to_end.total}`]
  ];
  $('#evaluation-content').innerHTML = `<div class="evaluation-legend"><span class="legend-key seen">Seen</span><span class="legend-key held-out">Held-out</span><span class="muted">Author-created holdout · Not blinded</span></div>
    <div class="panel table-scroll" tabindex="0" role="region" aria-label="Evaluation metrics"><table class="metrics"><thead><tr><th scope="col">Metric</th>${groups.map(([,title]) => `<th scope="col">${title}</th>`).join('')}</tr></thead><tbody>
    ${metrics.map(([title,value,count]) => `<tr><th scope="row">${title}</th>${groups.map(([key]) => {
      const g = evaluation.groups[key], rate = value(g);
      const valid = typeof rate === 'number' && Number.isFinite(rate);
      return `<td><strong>${percent(rate)}</strong><div class="metric-bar ${key}" ${valid ? `role="meter" aria-label="${escapeHTML(title)} · ${key === 'all' ? 'All' : splitLabel(key)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${rate * 100}" aria-valuetext="${percent(rate)}"` : ''}><span style="width:${valid ? Math.max(0,Math.min(1,rate)) * 100 : 0}%"></span></div><small class="muted">${escapeHTML(count(g))}</small></td>`;
    }).join('')}</tr>`).join('')}
    ${[['Policies',g => g.policies],['Cases',g => g.cases],['Labeled cases',g => g.discrepancy.labeled_cases],['Resolved labeled cases',g => g.discrepancy.resolved_labeled_cases],['Abstentions',g => g.discrepancy.abstentions]].map(([title,value]) => `<tr><th scope="row">${title}</th>${groups.map(([key]) => `<td>${escapeHTML(value(evaluation.groups[key]))}</td>`).join('')}</tr>`).join('')}
    </tbody></table></div>`;
}
async function loadJSON(path) { const response = await fetch(path); if (!response.ok) throw new Error(`${path}: ${response.status}`); return response.json(); }
window.addEventListener('hashchange',route);
route();
loadJSON('data.json').then(payload => { data = payload; renderOverview(); $('#status').hidden = true; route(); }).catch(() => { $('#status').textContent = 'Data unavailable · reload to retry'; });

loadJSON('evaluation.json').then(payload => { evaluation = payload; renderEvaluation(); }).catch(() => { $('#evaluation-content').textContent = 'Evaluation unavailable · reload to retry'; });
