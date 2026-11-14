'use strict';
const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = cents => Number.isSafeInteger(cents) ? new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents / 100) : '—';
const percent = value => typeof value === 'number' ? new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:1}).format(value) : '—';
const splitLabel = value => value === 'held_out' ? 'Held-out' : 'Seen';
let data;
function route() {
  const page = location.hash.slice(1).split('/')[0] || 'overview';
  const current = ['overview','explorer','evaluation'].includes(page) ? page : 'overview';
  document.querySelectorAll('.screen').forEach(el => { el.hidden = el.id !== current; });
  document.querySelectorAll('nav a').forEach(el => { if (el.hash === `#${current}`) el.setAttribute('aria-current','page'); else el.removeAttribute('aria-current'); });
  if (data && current === 'explorer') renderExplorer();
}
function renderOverview() {
  const cases = data.cases;
  const ready = cases.filter(c => c.report.status === 'ready').length;
  const flagged = cases.filter(c => c.report.comparisons.some(s => s.lines.some(l => l.eob_difference_cents !== 0))).length;
  $('#headlines').innerHTML = [[cases.length,'Synthetic cases'],[ready,'Calculated cases'],[flagged,'Cases with EOB differences'],[percent(data.evaluation.groups.all.end_to_end.rate),'End-to-end success']].map(([v,label]) => `<div class="stat"><strong>${escapeHTML(v)}</strong><span>${label}</span></div>`).join('');
  $('#case-list').innerHTML = cases.map(c => `<a class="case-row" href="#explorer/${encodeURIComponent(c.id)}"><div><strong>${escapeHTML(c.title)}</strong><small>${splitLabel(c.split)} · ${escapeHTML(c.report.status)}</small></div><span class="case-value">${c.report.summary ? money(c.report.summary.eob_patient_cents) : 'Blocked'}<small>${c.report.summary ? 'EOB patient total' : 'Parser abstention'}</small></span><span aria-hidden="true">↗</span></a>`).join('');
}
function renderExplorer() { $('#explorer-content').innerHTML = '<p class="muted">Case evidence loading…</p>'; }
async function loadJSON(path) { const response = await fetch(path); if (!response.ok) throw new Error(`${path}: ${response.status}`); return response.json(); }
window.addEventListener('hashchange',route);
route();
loadJSON('data.json').then(payload => { data = payload; renderOverview(); $('#status').hidden = true; route(); }).catch(() => { $('#status').textContent = 'Data unavailable · reload to retry'; });
