'use strict';
/* Fineprint demo — renders data.json / evaluation.json. Every figure shown comes from those files. */
const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const usd = new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'});
const money = cents => Number.isSafeInteger(cents) ? usd.format(cents / 100) : '—';
const signedMoney = value => Number.isSafeInteger(value) ? `${value > 0 ? '+' : value < 0 ? '−' : ''}${usd.format(Math.abs(value) / 100)}` : '—';
const pctFmt = new Intl.NumberFormat('en-US', {style:'percent', maximumFractionDigits:1});
const percent = value => typeof value === 'number' && Number.isFinite(value) ? pctFmt.format(value) : '—';
const splitLabel = value => value === 'held_out' ? 'Held-out' : 'Seen';
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const fieldLabels = {allowed_cents:'Allowance', deductible_cents:'Deductible', copay_cents:'Copay', coinsurance_cents:'Coinsurance', noncovered_cents:'Noncovered', balance_cents:'Balance billing', insurer_paid_cents:'Insurer paid', adjustment_cents:'Write-off', patient_cents:'Patient owes'};
const label = value => fieldLabels[value] || String(value).replace(/_cents$/, '').replace(/_/g, ' ');
const networkLabel = value => value === 'in' ? 'In-network' : value === 'out' ? 'Out-of-network' : value;
const kindLabels = {eob_vs_fineprint:['EOB − Fineprint','EOB ≠ Fineprint'], bill_vs_eob:['Bill − EOB','Bill ≠ EOB'], bill_vs_fineprint:['Bill − Fineprint','Bill ≠ Fineprint']};
let data, evaluation, activeScenario = {}, evalGroup = 'all', renderedCase = null;

/* ---------- helpers ---------- */
function barPct(value, max) { return max > 0 && Number.isFinite(value) ? Math.max(0, Math.min(100, value / max * 100)) : 0; }
function bar(cls, value, max) { return `<span class="track"><span class="fill ${cls}" style="--w:${barPct(value, max).toFixed(2)}%"></span></span>`; }
function eobDiffers(c) { return (c.report.comparisons || []).some(s => !s.conditional && s.lines.some(l => l.eob_difference_cents !== 0)); }
function caseState(c) {
  if (c.report.status === 'blocked') return 'abstain';
  if (c.report.summary.conditional) return 'cond';
  return eobDiffers(c) ? 'flag' : 'ok';
}
const stateText = {abstain:'Parser abstained', cond:'Conditional', flag:'Discrepancy', ok:'Matches'};
function animateNumbers(root) {
  if (reduceMotion) return;
  root.querySelectorAll('[data-count]').forEach(el => {
    const to = Number(el.dataset.count), kind = el.dataset.kind, final = el.textContent;
    const fmt = kind === 'pct' ? percent : kind === 'int' ? v => String(Math.round(v)) : kind === 'signed' ? v => signedMoney(Math.round(v)) : v => money(Math.round(v));
    if (!Number.isFinite(to)) return;
    const t0 = performance.now(), dur = 900;
    const tick = now => {
      const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = p < 1 ? fmt(to * e) : final;
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    setTimeout(() => { el.textContent = final; }, dur + 150);
  });
}
const counted = (value, kind, text) => `<span class="n" data-count="${value}" data-kind="${kind}">${escapeHTML(text)}</span>`;

/* ---------- routing ---------- */
function route() {
  const page = location.hash.slice(1).split('/')[0] || 'overview';
  const current = ['overview', 'explorer', 'evaluation'].includes(page) ? page : 'overview';
  document.querySelectorAll('.screen').forEach(el => { el.hidden = el.id !== current; });
  document.querySelectorAll('.topbar nav a').forEach(el => { if (el.hash === `#${current}`) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current'); });
  if (current === 'explorer' && data) renderExplorer();
  if (current === 'evaluation') {
    if (evaluation) { if (!$('#evaluation-content').children.length) renderEvaluation(); }
    else if (!$('#evaluation-content').textContent) $('#evaluation-content').textContent = 'Loading evaluation…';
  }
  if (!location.hash.split('/')[2]) window.scrollTo(0, 0);
}

/* ---------- overview ---------- */
function renderOverview() {
  const cases = data.cases, all = data.evaluation.groups.all;
  const states = cases.map(caseState);
  const featured = cases.find((c, i) => states[i] === 'flag') || cases.find(c => c.report.status === 'ready');
  if (featured) {
    const s = featured.report.scenarios[0], cmp = featured.report.comparisons[0];
    const eob = featured.report.summary.eob_patient_cents, fp = s.patient_cents;
    const found = cmp.lines.reduce((n, l) => n + l.explanations.filter(e => e.kind === 'eob_vs_fineprint').length, 0);
    const steps = [[featured.compilation.output.policy.clauses.length, 'Clauses'], [featured.compilation.output.rule_evidence.length, 'Rules compiled'], [cmp.lines.length, 'Lines recalculated'], [found, 'Discrepancies']];
    $('#proof').innerHTML = `<div class="proof-top"><div class="proof-title">${escapeHTML(featured.title)}<a href="#explorer/${encodeURIComponent(featured.id)}">Open case →</a></div>
      <div class="proof-eq"><div class="big eob"><small>EOB</small><strong>${counted(eob, 'money', money(eob))}</strong></div><span class="op" aria-hidden="true">→</span>
      <div class="big fp"><small>Fineprint</small><strong>${counted(fp, 'money', money(fp))}</strong></div><span class="op" aria-hidden="true">=</span>
      <div class="big delta"><small>Difference</small><strong>${counted(eob - fp, 'signed', signedMoney(eob - fp))}</strong></div></div></div>
      <ol class="pipe">${steps.map(([n, t]) => `<li><strong>${counted(n, 'int', n)}</strong><span>${t}</span></li>`).join('')}</ol>`;
  }
  const blocked = states.filter(s => s === 'abstain').length, flagged = states.filter(s => s === 'flag').length;
  $('#headlines').innerHTML = [
    ['', cases.length, 'int', cases.length, 'Cases'],
    ['red', flagged, 'int', flagged, 'Discrepancies flagged'],
    ['ink', blocked, 'int', blocked, 'Parser abstentions'],
    ['green', all.evidence.traceability_rate, 'pct', percent(all.evidence.traceability_rate), 'Rules traceable'],
    ['green', all.end_to_end.rate, 'pct', percent(all.end_to_end.rate), 'End-to-end success']
  ].map(([cls, v, kind, text, name]) => `<div class="stat ${cls}"><strong>${counted(v, kind, text)}</strong><span>${name}</span></div>`).join('');
  const maxAll = Math.max(1, ...cases.flatMap(c => c.report.summary ? [c.report.summary.eob_patient_cents, c.report.scenarios[0].patient_cents] : []));
  $('#case-list').innerHTML = cases.map((c, i) => {
    const st = states[i];
    const body = st === 'abstain'
      ? `<div class="abstain-box"><span class="dot abstain"></span>Parser abstained</div>`
      : `<div class="cmp"><div class="cmp-row"><span>EOB</span>${bar('eob', c.report.summary.eob_patient_cents, maxAll)}<span>${money(c.report.summary.eob_patient_cents)}</span></div>
         <div class="cmp-row"><span>Fineprint</span>${bar('fp', c.report.scenarios[0].patient_cents, maxAll)}<span>${st === 'cond' ? `${money(c.report.summary.illustrated_min_patient_cents)}–${money(c.report.summary.illustrated_max_patient_cents)}` : money(c.report.scenarios[0].patient_cents)}</span></div></div>`;
    return `<a class="case-card" href="#explorer/${encodeURIComponent(c.id)}"><div class="card-top"><span class="chip ${st}">${stateText[st]}</span><span class="chip ${c.split === 'held_out' ? 'held' : ''}">${splitLabel(c.split)}</span></div><h3>${escapeHTML(c.title)}</h3>${body}</a>`;
  }).join('');
  animateNumbers($('#overview'));
}

/* ---------- explorer: evidence + rules ---------- */
function evidenceSpans(c) {
  if (c._spans) return c._spans;
  const chars = Array.from(c.document), unique = new Map();
  for (const rule of c.compilation?.output.rule_evidence || []) for (const span of rule.evidence) {
    if (Number.isInteger(span.start) && span.start >= 0 && span.end > span.start && span.end <= chars.length && chars.slice(span.start, span.end).join('') === span.quote) unique.set(`${span.start}-${span.end}`, span);
  }
  return c._spans = [...unique.values()].sort((a, b) => a.start - b.start || a.end - b.end);
}
const spanKey = span => `${span.start}-${span.end}`;
const evidenceID = span => `evidence-${spanKey(span)}`;
const hashFor = (c, span) => `#explorer/${encodeURIComponent(c.id)}/${evidenceID(span)}`;
function ruleNumbers(c) {
  const map = new Map();
  (c.compilation?.output.rule_evidence || []).forEach((rule, i) => rule.evidence.forEach(e => { const k = spanKey(e); map.set(k, [...(map.get(k) || []), i + 1]); }));
  return map;
}
function citations(c, ids) {
  const spans = evidenceSpans(c);
  return [...new Set(ids)].map(id => {
    const clause = c.compilation.output.policy.clauses.find(item => item.id === id);
    const span = spans.find(item => item.section === clause?.location || item.quote === clause?.text);
    return span ? `<a class="citation" href="${hashFor(c, span)}" data-spans="${spanKey(span)}" title="${escapeHTML(clause.text)}">${escapeHTML(id)}</a>` : `<span class="citation" style="opacity:.55">${escapeHTML(id)}</span>`;
  }).join('');
}
function policyText(c) {
  const chars = Array.from(c.document), numbers = ruleNumbers(c);
  let cursor = 0, html = '';
  for (const span of evidenceSpans(c)) {
    if (span.start < cursor) continue;
    const nums = numbers.get(spanKey(span)) || [];
    html += escapeHTML(chars.slice(cursor, span.start).join(''));
    html += `<mark id="${evidenceID(span)}" tabindex="0" data-rules="${nums.join(',')}" data-r="${nums.map(n => 'R' + n).join('·')}" title="${escapeHTML(span.section)}">${escapeHTML(chars.slice(span.start, span.end).join(''))}</mark>`;
    cursor = span.end;
  }
  return html + escapeHTML(chars.slice(cursor).join(''));
}
function compiledRules(c) {
  const policy = c.compilation.output.policy, spans = evidenceSpans(c);
  return c.compilation.output.rule_evidence.map((rule, i) => {
    const parts = rule.rule_path.split('.');
    let title, chips;
    if (parts[0] === 'networks') {
      title = `${networkLabel(parts[1])} · ${label(parts[2])}`;
      const raw = policy.networks[parts[1]]?.[parts[2]];
      chips = [parts[2].endsWith('_cents') ? money(raw) : raw ? 'Permitted' : 'Prohibited'];
    } else {
      const b = policy.benefits.find(x => x.id === parts.slice(1).join('.'));
      title = b?.label || rule.rule_path;
      chips = b ? [b.covered ? 'Covered' : 'Excluded', `Deductible ${b.deductible_applies ? 'applies' : 'waived'}`, `${money(b.copay_cents)} copay`, `${percent(b.coinsurance_bps / 10000)} coinsurance`] : ['—'];
    }
    const mine = rule.evidence.filter(e => spans.some(s => spanKey(s) === spanKey(e)));
    return `<div class="rule" data-n="${i + 1}" data-spans="${mine.map(spanKey).join(',')}"><span class="rn">R${i + 1}</span><strong>${escapeHTML(title)}</strong><div class="rule-vals">${chips.map(t => `<span class="chip">${escapeHTML(t)}</span>`).join('')}</div><div class="cites">${mine.map(e => `<a class="citation" href="${hashFor(c, e)}" data-spans="${spanKey(e)}">${escapeHTML(e.section)}</a>`).join('')}</div></div>`;
  }).join('');
}

/* ---------- explorer: reconciliation ---------- */
function renderVerdict(c, scenario) {
  const s = c.report.summary, max = Math.max(s.eob_patient_cents, s.bill_patient_cents, scenario.patient_cents, 1);
  const delta = s.eob_patient_cents - scenario.patient_cents;
  const cls = scenario.conditional ? 'cond' : delta ? 'flag' : 'ok';
  const row = (name, cls2, v) => `<div class="vbar"><span>${name}</span>${bar(cls2, v, max)}<strong>${counted(v, 'money', money(v))}</strong></div>`;
  $('#verdict').innerHTML = `<div class="vbars">${row('EOB', 'eob', s.eob_patient_cents)}${row('Bill', 'bill', s.bill_patient_cents)}${row('Fineprint', 'fp', scenario.patient_cents)}</div>
    <div class="delta-box ${cls}"><small>${scenario.conditional ? 'Conditional' : 'EOB − Fineprint'}</small><strong>${scenario.conditional ? `${money(s.illustrated_min_patient_cents)}–${money(s.illustrated_max_patient_cents)}` : counted(delta, 'signed', signedMoney(delta))}</strong>${scenario.conditional ? `<small>${s.scenario_count} scenarios</small>` : ''}</div>`;
  animateNumbers($('#verdict'));
}
function renderScenarios(c, scenario) {
  const list = c.report.scenarios;
  if (list.length < 2) { $('#scenarios').innerHTML = ''; return; }
  const max = Math.max(1, ...list.map(s => s.patient_cents));
  $('#scenarios').innerHTML = `<div class="scen"><div class="scen-top"><h3>Scenarios · ${list.length}</h3><span class="chip cond">${escapeHTML(scenario.id)} · ${money(scenario.patient_cents)}</span></div>
    <div class="scen-strip" role="group" aria-label="Scenarios">${list.map(s => `<button type="button" data-scenario="${escapeHTML(s.id)}" aria-pressed="${s.id === scenario.id}" aria-label="${escapeHTML(s.id)} · ${money(s.patient_cents)}" title="${escapeHTML(s.id)} · ${money(s.patient_cents)}" style="--h:${Math.max(6, s.patient_cents / max * 100)}%"></button>`).join('')}</div>
    ${scenario.assumptions.length ? `<ul class="assump">${scenario.assumptions.map(a => `<li>${escapeHTML(a)}</li>`).join('')}</ul>` : ''}</div>`;
}
function renderLines(c, scenario) {
  const comparison = c.report.comparisons.find(s => s.scenario_id === scenario.id);
  const maxLine = Math.max(1, ...scenario.lines.map(l => l.patient_cents), ...comparison.lines.map(l => l.eob_patient_cents));
  $('#lines').innerHTML = scenario.lines.map(line => {
    const original = c.case.claim.lines.find(l => l.id === line.claim_line_id);
    const cmp = comparison.lines.find(l => l.claim_line_id === line.claim_line_id);
    const issues = cmp.explanations.filter(e => e.kind !== 'match');
    const differs = cmp.eob_difference_cents !== 0;
    const rows = Object.keys(fieldLabels).map(key => {
      const eob = key === 'patient_cents' ? cmp.eob_patient_cents : original.insurer[key];
      const diff = Number.isSafeInteger(eob) ? eob - line[key] : null;
      return `<tr class="${key === 'patient_cents' ? 'total ' : ''}${diff ? 'diff' : eob === 0 && line[key] === 0 ? 'zero' : ''}"><th scope="row">${fieldLabels[key]}</th><td>${money(eob)}</td><td>${money(line[key])}</td><td>${diff ? signedMoney(diff) : '—'}</td></tr>`;
    }).join('');
    const cites = [...new Set(line.trace.flatMap(t => t.clause_ids))];
    return `<article class="line ${issues.length ? 'has' : ''}"><div class="line-head"><h3><small>${escapeHTML(line.claim_line_id)} · ${escapeHTML(original.code)}</small>${escapeHTML(original.description)}</h3><span class="chip">${escapeHTML(networkLabel(line.network))}</span></div>
      <div class="line-bars"><div class="cmp-row"><span>EOB</span>${bar('eob', cmp.eob_patient_cents, maxLine)}<span>${money(cmp.eob_patient_cents)}</span></div><div class="cmp-row"><span>Fineprint</span>${bar('fp', line.patient_cents, maxLine)}<span>${money(line.patient_cents)}</span></div></div>
      <div class="t-scroll" tabindex="0" role="region" aria-label="${escapeHTML(line.claim_line_id)} EOB vs Fineprint"><table class="tbl"><thead><tr><th scope="col">Component</th><th scope="col">EOB</th><th scope="col">Fineprint</th><th scope="col">Δ</th></tr></thead><tbody>${rows}</tbody></table></div>
      ${issues.length ? `<div class="issues">${scenario.conditional ? '<span class="chip cond">Conditional differences</span>' : ''}${issues.map(e => { const k = kindLabels[e.kind] || [e.kind.replace(/_/g, ' '), e.kind]; return `<div class="issue"><span class="k"><b>${escapeHTML(k[1])}</b> · ${escapeHTML(label(e.component))}<br><span class="muted">${escapeHTML(k[0])}</span></span><strong>${signedMoney(e.difference_cents)}</strong><div class="cites">${citations(c, e.clause_ids)}</div></div>`; }).join('')}</div>` : `<div class="matchline"><span aria-hidden="true">✓</span>Matches to the cent</div>`}
      <div class="accs"><span>Deductible ${money(line.opening_deductible_cents)} → ${money(line.closing_deductible_cents)}</span><span>OOP ${money(line.opening_oop_cents)} → ${money(line.closing_oop_cents)}</span></div>
      <details><summary>Bill reconciliation</summary><div class="mini">${[['Bill patient', cmp.bill_patient_cents], ['Already paid', cmp.already_paid_cents], ['Balance due', cmp.bill_balance_due_cents], ['Fineprint remaining', cmp.fineprint_remaining_cents], ['Potential refund', cmp.potential_refund_cents], ['Potential overpayment', cmp.potential_overpayment_cents]].map(([t, v]) => `<div><small>${t}</small><strong>${money(v)}</strong></div>`).join('')}</div></details>
      <details><summary>Calculation trace</summary><ol class="trace">${line.trace.map(t => `<li><b>${money(t.amount_cents)}</b><span>${escapeHTML(t.explanation)}</span><span class="cites">${citations(c, t.clause_ids)}</span></li>`).join('')}</ol></details></article>`;
  }).join('');
}
function renderReconciliation(c, scenarioID) {
  const scenario = c.report.scenarios.find(s => s.id === scenarioID) || c.report.scenarios[0];
  renderVerdict(c, scenario); renderScenarios(c, scenario); renderLines(c, scenario);
}

/* ---------- explorer shell ---------- */
function renderExplorer() {
  const parts = location.hash.slice(1).split('/');
  let requested;
  try { requested = decodeURIComponent(parts[1] || ''); } catch { requested = ''; }
  const c = data.cases.find(item => item.id === requested) || data.cases[0];
  if (renderedCase !== c.id || !$('#explorer-content').children.length) buildExplorer(c);
  focusEvidence(parts[2]);
}
function buildExplorer(c) {
  renderedCase = c.id;
  const st = caseState(c), blocked = st === 'abstain';
  const nSpans = evidenceSpans(c).length, nRules = c.compilation?.output.rule_evidence.length || 0;
  $('#explorer-content').innerHTML = `<div class="picker" role="group" aria-label="Cases">${data.cases.map(item => `<a href="#explorer/${encodeURIComponent(item.id)}" ${item.id === c.id ? 'aria-current="true"' : ''}><span class="dot ${caseState(item)}"></span>${escapeHTML(item.title)}</a>`).join('')}</div>
    <div class="case-head"><h2>${escapeHTML(c.title)}</h2><div class="tags"><span class="chip ${st}">${stateText[st]}</span><span class="chip ${c.split === 'held_out' ? 'held' : ''}">${splitLabel(c.split)}</span><span class="badge">Synthetic</span></div></div>
    ${blocked ? `<div class="abstained" role="status"><span class="stop" aria-hidden="true">∅</span><strong>Parser abstained</strong><span class="why">${escapeHTML(c.report.blocked_reason || '')}</span><div class="tags"><span class="chip abstain">0 rules compiled</span><span class="chip abstain">No recalculation</span></div></div>` : '<div id="verdict" class="verdict"></div><div id="scenarios"></div>'}
    <div class="split"><div class="left">
      <section class="pane policy-pane" aria-label="Policy text"><div class="pane-head"><h3>Policy text</h3><span class="chip">${nSpans} evidence spans</span></div><div class="pane-body" id="policy-body" tabindex="0"><pre class="policy-text">${policyText(c)}</pre></div></section>
      <section class="pane rules-pane" aria-label="Compiled rules"><div class="pane-head"><h3>Compiled rules</h3><span class="chip">${nRules} rules</span></div><div class="pane-body" id="rules-body">${nRules ? compiledRules(c) : '<div class="empty">No rules emitted</div>'}</div></section>
    </div><div class="right">${blocked ? '' : '<div id="lines" class="lines"></div>'}</div></div>`;
  const picker = $('.picker a[aria-current]');
  if (picker) picker.scrollIntoView({block:'nearest', inline:'center'});
  if (!blocked) {
    const id = activeScenario.caseID === c.id && c.report.scenarios.some(s => s.id === activeScenario.id) ? activeScenario.id : c.report.scenarios[0].id;
    renderReconciliation(c, id);
  }
}
function focusEvidence(id) {
  if (!/^evidence-\d+-\d+$/.test(id || '')) return;
  const target = document.getElementById(id), body = $('#policy-body');
  if (!target || !body) return;
  const head = $('.topbar').offsetHeight;
  const pane = body.closest('.pane').getBoundingClientRect();
  if (pane.top < head || pane.bottom > innerHeight) window.scrollBy({top: pane.top - head - 12, behavior: reduceMotion ? 'auto' : 'smooth'});
  body.scrollTo({top: Math.max(0, target.offsetTop - body.clientHeight / 3), behavior: reduceMotion ? 'auto' : 'smooth'});
  target.focus({preventScroll:true});
  target.classList.remove('flash'); void target.offsetWidth; target.classList.add('flash');
  selectRules(target.dataset.rules);
}
function selectRules(list) {
  document.querySelectorAll('.rule.on').forEach(el => el.classList.remove('on'));
  const first = (list || '').split(',').filter(Boolean).map(n => document.querySelector(`.rule[data-n="${n}"]`)).filter(Boolean);
  first.forEach(el => el.classList.add('on'));
  const body = $('#rules-body');
  if (first[0] && body) body.scrollTo({top: Math.max(0, first[0].offsetTop - 8), behavior: reduceMotion ? 'auto' : 'smooth'});
}
/* hover / focus linking: rule ⇄ evidence span ⇄ citation */
function linkSpans(el, on) {
  const spans = (el.dataset.spans || '').split(',').filter(Boolean);
  spans.forEach(k => document.getElementById(`evidence-${k}`)?.classList.toggle('on', on));
  document.querySelectorAll('.citation[data-spans]').forEach(a => { if (a !== el && spans.includes(a.dataset.spans)) a.classList.toggle('on', on); });
}
function linkRules(mark, on) {
  (mark.dataset.rules || '').split(',').filter(Boolean).forEach(n => document.querySelector(`.rule[data-n="${n}"]`)?.classList.toggle('on', on));
}
function bindExplorer() {
  const root = $('#explorer-content');
  const handler = on => event => {
    const src = event.target.closest?.('[data-spans]');
    if (src) linkSpans(src, on);
    const mark = event.target.closest?.('mark');
    if (mark) linkRules(mark, on);
  };
  root.addEventListener('mouseover', handler(true)); root.addEventListener('mouseout', handler(false));
  root.addEventListener('focusin', handler(true)); root.addEventListener('focusout', handler(false));
  root.addEventListener('click', event => {
    const mark = event.target.closest('mark');
    if (mark) { selectRules(mark.dataset.rules); return; }
    const dot = event.target.closest('[data-scenario]');
    if (dot) {
      const c = data.cases.find(item => item.id === renderedCase);
      activeScenario = {caseID: c.id, id: dot.dataset.scenario};
      renderReconciliation(c, dot.dataset.scenario);
      $(`[data-scenario="${CSS.escape(dot.dataset.scenario)}"]`)?.focus();
    }
  });
}

/* ---------- evaluation ---------- */
const metricDefs = [
  ['Extraction precision', g => g.extraction.precision, g => `${g.extraction.tp}/${g.extraction.tp + g.extraction.fp}`],
  ['Extraction recall', g => g.extraction.recall, g => `${g.extraction.tp}/${g.extraction.tp + g.extraction.fn}`],
  ['Calculation exact', g => g.calculation.accuracy, g => `${g.calculation.exact}/${g.calculation.total}`],
  ['Discrepancy precision', g => g.discrepancy.precision, g => `${g.discrepancy.tp}/${g.discrepancy.tp + g.discrepancy.fp}`],
  ['Discrepancy recall', g => g.discrepancy.recall, g => `${g.discrepancy.tp}/${g.discrepancy.tp + g.discrepancy.fn}`],
  ['False-positive rate', g => g.discrepancy.false_positive_rate, g => `${g.discrepancy.fp}/${g.discrepancy.labeled_cases - g.discrepancy.tp - g.discrepancy.fn}`],
  ['Traceability', g => g.evidence.traceability_rate, g => `${g.evidence.valid_rules}/${g.evidence.emitted_rules}`],
  ['Evidence coverage', g => g.evidence.coverage_rate, g => `${g.evidence.valid_rules}/${g.evidence.gold_rules}`],
  ['End-to-end', g => g.end_to_end.rate, g => `${g.end_to_end.success}/${g.end_to_end.total}`]
];
function ringHTML(name, rate, counts) {
  const ok = typeof rate === 'number' && Number.isFinite(rate), r = 42, C = 2 * Math.PI * r;
  const tone = !ok ? '' : rate >= .9 ? 'hi' : rate >= .6 ? 'mid' : 'low';
  return `<div class="ring ${tone}"><svg viewBox="0 0 100 100" role="img" aria-label="${escapeHTML(name)} ${percent(rate)}"><circle class="bg" cx="50" cy="50" r="${r}"/>${ok ? `<circle class="fg" cx="50" cy="50" r="${r}" style="--p:${(Math.max(0, Math.min(1, rate)) * C).toFixed(1)}"/>` : ''}</svg>
    <div><strong>${ok ? counted(rate, 'pct', percent(rate)) : '—'}</strong><span>${name}</span><small>${escapeHTML(counts)}</small></div></div>`;
}
function renderGroup() {
  const g = evaluation.groups[evalGroup], d = g.discrepancy;
  const reports = [evaluation, ...(data?.llm_evaluations || [])];
  $('#eval-comparison').innerHTML = `<div class="t-scroll"><table class="tbl"><caption class="sr-only">Synthetic data · ${escapeHTML(evalGroup)} · provider comparison</caption><thead><tr><th scope="col">${evalGroup === 'all' ? 'All' : splitLabel(evalGroup)} · synthetic data</th>${reports.map(r => `<th scope="col">${r.backend === 'fallback' ? 'Offline fallback' : 'DeepSeek'}<br><span>${escapeHTML(r.model || 'No LLM')}</span><br><time datetime="${escapeHTML(r.generated_at)}">${escapeHTML(r.generated_at.slice(0, 10))}</time></th>`).join('')}</tr></thead><tbody>
    ${metricDefs.map(([name, val, count]) => `<tr><th scope="row">${name}</th>${reports.map(r => `<td>${percent(val(r.groups[evalGroup]))} <small>(${escapeHTML(count(r.groups[evalGroup]))})</small></td>`).join('')}</tr>`).join('')}
    <tr><th scope="row">Failed compilations</th>${reports.map(r => { const rows = r.policies.filter(p => evalGroup === 'all' || p.split === evalGroup); return `<td>${rows.filter(p => p.error).length}/${rows.length}</td>`; }).join('')}</tr>
    <tr><th scope="row">Abstentions</th>${reports.map(r => `<td>${r.groups[evalGroup].discrepancy.abstentions}/${r.groups[evalGroup].cases}</td>`).join('')}</tr>
    </tbody></table></div>`;
  $('#eval-group').innerHTML = `<div class="rings">${[['End-to-end', g => g.end_to_end.rate, g => `${g.end_to_end.success}/${g.end_to_end.total} cases`], ['Calculation exact', g => g.calculation.accuracy, g => `${g.calculation.exact}/${g.calculation.total} cases`], ['Discrepancy recall', g => g.discrepancy.recall, g => `${g.discrepancy.tp}/${g.discrepancy.tp + g.discrepancy.fn} flagged`], ['Rules traceable', g => g.evidence.traceability_rate, g => `${g.evidence.valid_rules}/${g.evidence.emitted_rules} rules`]].map(([n, v, t]) => ringHTML(n, v(g), t(g))).join('')}</div>`;
  $('#eval-conf').innerHTML = `<div class="conf"><div class="hd"></div><div class="hd">Flagged</div><div class="hd">Not flagged</div>
    <div class="hd">Has issue</div><div class="good"><small>TP</small><strong>${d.tp}</strong></div><div class="bad"><small>FN</small><strong>${d.fn}</strong></div>
    <div class="hd">No issue</div><div class="bad"><small>FP</small><strong>${d.fp}</strong></div><div class="good"><small>TN</small><strong>${d.tn}</strong></div></div>
    <div class="conf-foot"><span class="chip abstain">${d.abstentions} abstentions</span><span class="chip">${d.resolved_labeled_cases}/${d.labeled_cases} resolved</span><span class="chip">${g.policies} policies · ${g.cases} cases</span></div>`;
  animateNumbers($('#eval-group'));
}
function renderEvaluation() {
  const g = evaluation.groups, titles = new Map((data?.cases || []).map(c => [c.id, c.title]));
  const outcome = c => c.end_to_end_success ? ['pass', 'Pass'] : c.error ? ['block', 'Parser abstained'] : ['miss', 'Miss'];
  $('#evaluation-content').innerHTML = `<div class="eval-head"><h2>Evaluation</h2><fieldset class="seg" aria-label="Group"><legend class="sr-only">Group</legend>${[['seen', 'Seen'], ['held_out', 'Held-out'], ['all', 'All']].map(([k, t]) => `<label><input type="radio" name="grp" value="${k}" ${k === evalGroup ? 'checked' : ''}><span>${t}</span></label>`).join('')}</fieldset></div>
    <p class="caveat"><span aria-hidden="true">⚠</span>${escapeHTML(evaluation.methodology[0] || '')}</p>
    <section class="panel provider-comparison" aria-label="Offline fallback vs DeepSeek"><h3>Offline fallback vs DeepSeek</h3><div id="eval-comparison"></div></section>
    <h3 class="fallback-detail">Offline fallback</h3>
    <div id="eval-group"></div>
    <div class="eval-grid"><section class="panel"><h3>Seen vs held-out</h3><div class="legend"><span class="key">Seen</span><span class="key held">Held-out</span><span class="key all">All</span></div>
      ${metricDefs.map(([name, val, count]) => `<div class="mrow"><b>${name}</b><div class="mbars" role="group" aria-label="${name}">${[['seen', 'Seen', ''], ['held_out', 'Held-out', 'hel']].map(([k, t, cls]) => { const r = val(g[k]); return `<div class="mb" role="meter" aria-label="${name} · ${t}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Number.isFinite(r) ? (r * 100).toFixed(1) : 0}" aria-valuetext="${percent(r)}">${bar(cls, r, 1)}<em><b>${percent(r)}</b><small>${escapeHTML(count(g[k]))}</small></em></div>`; }).join('')}</div><span class="mall" title="All">${percent(val(g.all))}</span></div>`).join('')}</section>
      <div style="display:grid;gap:22px"><section class="panel"><h3>Discrepancy detection</h3><div id="eval-conf"></div></section>
      <section class="panel"><h3>Cases</h3><div class="tiles">${evaluation.cases.map(c => { const [cls, text] = outcome(c); return `<a class="tile ${cls}" href="#explorer/${encodeURIComponent(c.id)}"><b>${escapeHTML(titles.get(c.id) || c.id)}</b><span class="chip ${cls === 'pass' ? 'ok' : cls === 'miss' ? 'flag' : 'abstain'}">${text}</span><span class="muted">${splitLabel(c.split)}</span></a>`; }).join('')}</div></section></div></div>
    <div class="prov"><span>Backend <b>${escapeHTML(evaluation.backend)}</b></span><span>Revision <b>${escapeHTML(String(evaluation.revision || '').slice(0, 7))}</b></span><span>Corpus <b>${escapeHTML(String(evaluation.corpus_sha256 || '').slice(0, 10))}</b></span><span>Generated <b>${escapeHTML(String(evaluation.generated_at || '').slice(0, 10))}</b></span><span>Synthetic data · offline fallback</span></div>`;
  if (data?.real_evaluation) $('#evaluation-content').insertAdjacentHTML('afterbegin', '<p class="caveat"><a href="evaluation-real-sbc.json">real published SBC examples (rounded)</a> · Saved results and calculation blockers</p>');
  $('.seg').addEventListener('change', event => { if (event.target.name === 'grp') { evalGroup = event.target.value; renderGroup(); } });
  renderGroup();
}

/* ---------- boot ---------- */
async function loadJSON(path) { const response = await fetch(path); if (!response.ok) throw new Error(`${path}: ${response.status}`); return response.json(); }
window.addEventListener('hashchange', route);
bindExplorer();
route();
loadJSON('data.json').then(payload => {
  data = payload; renderOverview(); $('#status').hidden = true;
  $('#evaluation-content').replaceChildren(); route();
}).catch(() => { $('#status').textContent = 'Data unavailable · reload to retry'; });
loadJSON('evaluation.json').then(payload => {
  evaluation = payload; $('#evaluation-content').replaceChildren(); if (location.hash.startsWith('#evaluation')) renderEvaluation();
}).catch(() => { $('#evaluation-content').textContent = 'Evaluation unavailable · reload to retry'; });
