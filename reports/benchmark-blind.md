# Blind held-out benchmark — SYNTHETIC

40 cases; 16 correct bills and 24 erroneous bills. Run completed 2026-11-15T11:57:44.884393+00:00.

Exact amount (±$1): **6/40 (15.0%)**. Range contains truth: **0/0 (n/a)**. Abstain/dead-end: **33/40 (82.5%)**.

Error detection precision **100.0%**, recall **16.7%**, false-positive rate **0.0%**. TP=4, FP=0, FN=20, TN=2; abstained positives=19, abstained negatives=14. Resolved negative coverage **12.5%**; a zero FPR with abstentions is not proof of correct negative decisions.

Statuses: 7 answer; 0 range; 24 needs clarification; 9 error. Answer-only exact accuracy: 85.7%; per-line exact: 6/48. All-case point/range containment: 15.0%. Without confirmed answer (including ranges): 82.5%.

## Method and freeze

Freeze commit: `79d98f80dda182e76dd8a0dfaf9a21133ac2d7e6` (pushed before phase 2). Cases SHA-256: `6b170685afb68afa0d64d49b4313b4eb9eba5283ae187759888a16a4dc4c7679`; unchanged after the run.

Provider: `deepseek`; model: `deepseek-v4-pro`. Configuration: `{"attempt_limit": 1, "evidence_spans": "selected original source lines with local offsets; legacy quotes use whitespace-normalized search", "max_tokens": 32768, "max_tokens_ceiling": 65536, "max_tokens_initial": 32768, "response_format": "json_object", "thinking": "disabled", "timeout_seconds": 120, "transport_attempt_limit": 1}`.

Independent writer read root README and docs/architecture.md only before authoring; no product source, tests, existing benchmark cases or gold. README disclosed prior examples/aggregate results. All 40 expectations were hand-authored and pushed before interface inspection and inference.

One compiler invocation and at most one DeepSeek HTTP request per case; four concurrent workers; both provider and transport attempt limits one; no fallback, repairs, reruns or tuning. All raw records saved before gold scoring.

Unmodified real pipeline imported from a temporary git archive of the freeze revision to isolate concurrent repo edits. Compiler receives original policy only. Compiled policy is the only policy supplied to the deterministic app analysis.

Text policy compilation plus mechanical schema normalization of independently supplied EOB, bill, contract allowance and opening accumulators. This does not evaluate PDF/OCR or automatic raw-document extraction.

Narrative clinical/legal/coding facts are retained in claim descriptions and literal confirmation strings. No hand-written benefit corrections, category inference, legal protection override, duplicate removal or semantic mapping of compiled condition labels. Unsupported cases can block or fail; they stay in denominators.

Nonconditional answer within 100 cents inclusive, denominator 40; range results are not exact answers. Patient responsibility is pre-payment liability; remaining balance is separately reported.

Inclusive illustrative scenario extrema, no tolerance; rate denominator is range cases. Also report point/range containment over all 40. Scenario endpoints are not proven exhaustive bounds.

Needs clarification or error / 40. A separate without-confirmed-answer rate includes conditional ranges.

Only nonconditional answers yield a binary flag. An explicit per-line total patient difference versus EOB or statement establishes a flag; component reallocations alone do not. Failed positive cases count as FN; failed negatives abstain, not TN. Precision TP/(TP+FP), recall TP/24, FPR FP/16, resolved-negative coverage separately. Null indicates a zero denominator.

List predictions above statement patient-paid-plus-balance, and separately above gross charges. Also retain remaining-balance comparisons. Some gold cases intentionally underbill, so a higher prediction is not automatically incorrect.

The benchmark is small, synthetic and authored by this agent. It is a procedural holdout from product implementation inspection, not independent real-world clinical validation. Gold applicability facts about legal protections and coding are stipulated. Failures below are preserved without repairs. The frozen authoring protocol is in `data/blind_benchmark/README.md`; full per-line gold/prediction data, raw errors and source hashes are in the companion JSON and raw run records.

## Per-case results

Predicted and expected columns are total patient liability before payments. ‘Flag’ is the app's error decision; ‘Truth’ is whether the frozen bill has a real error. Conditional totals are illustrative ranges.

| Case | Status | Predicted | Expected | Statement patient total | Flag | Truth | Within $1 |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| blind-01 | answer | $440.00 | $440.00 | $440.00 | no | no | yes |
| blind-02 | needs clarification | — | $35.00 | $35.00 | abstain | no | no |
| blind-03 | needs clarification | — | $0.00 | $0.00 | abstain | no | no |
| blind-04 | needs clarification | — | $75.00 | $75.00 | abstain | no | no |
| blind-05 | error | — | $1,200.00 | $1,200.00 | abstain | no | no |
| blind-06 | needs clarification | — | $800.00 | $800.00 | abstain | no | no |
| blind-07 | needs clarification | — | $380.00 | $380.00 | abstain | no | no |
| blind-08 | needs clarification | — | $50.00 | $50.00 | abstain | no | no |
| blind-09 | answer | $40.00 | $40.00 | $40.00 | no | no | yes |
| blind-10 | needs clarification | — | $150.00 | $150.00 | abstain | no | no |
| blind-11 | needs clarification | — | $1,200.00 | $1,200.00 | abstain | no | no |
| blind-12 | needs clarification | — | $50.00 | $50.00 | abstain | no | no |
| blind-13 | error | — | $56.00 | $56.00 | abstain | no | no |
| blind-14 | error | — | $200.00 | $200.00 | abstain | no | no |
| blind-15 | error | — | $90.00 | $90.00 | abstain | no | no |
| blind-16 | needs clarification | — | $120.00 | $120.00 | abstain | no | no |
| blind-17 | answer | $360.00 | $360.00 | $440.00 | yes | yes | yes |
| blind-18 | needs clarification | — | $30.00 | $84.00 | abstain | yes | no |
| blind-19 | needs clarification | — | $0.00 | $100.00 | abstain | yes | no |
| blind-20 | needs clarification | — | $20.00 | $200.00 | abstain | yes | no |
| blind-21 | answer | $80.00 | $80.00 | $480.00 | yes | yes | yes |
| blind-22 | needs clarification | — | $700.00 | $140.00 | abstain | yes | no |
| blind-23 | needs clarification | — | $40.00 | $700.00 | abstain | yes | no |
| blind-24 | error | — | $400.00 | $1,000.00 | abstain | yes | no |
| blind-25 | needs clarification | — | $120.00 | $720.00 | abstain | yes | no |
| blind-26 | needs clarification | — | $0.00 | $900.00 | abstain | yes | no |
| blind-27 | needs clarification | — | $1,400.00 | $280.00 | abstain | yes | no |
| blind-28 | needs clarification | — | $45.00 | $90.00 | abstain | yes | no |
| blind-29 | answer | $70.00 | $20.00 | $70.00 | no | yes | no |
| blind-30 | error | — | $20.00 | $32.00 | abstain | yes | no |
| blind-31 | needs clarification | — | $55.00 | $95.00 | abstain | yes | no |
| blind-32 | needs clarification | — | $200.00 | $700.00 | abstain | yes | no |
| blind-33 | answer | $120.00 | $120.00 | $220.00 | yes | yes | yes |
| blind-34 | needs clarification | — | $220.00 | $460.00 | abstain | yes | no |
| blind-35 | error | — | $30.00 | $500.00 | abstain | yes | no |
| blind-36 | needs clarification | — | $800.00 | $600.00 | abstain | yes | no |
| blind-37 | answer | $80.00 | $80.00 | $180.00 | yes | yes | yes |
| blind-38 | error | — | $150.00 | $155.00 | abstain | yes | no |
| blind-39 | needs clarification | — | $0.00 | $250.00 | abstain | yes | no |
| blind-40 | error | — | $1,200.00 | $900.00 | abstain | yes | no |

## Predictions above billed

Point predictions above statement patient responsibility: none.
Range upper endpoints above statement patient responsibility: none.
Point predictions above gross charges: none.
Range upper endpoints above gross charges: none.

## Failures as observed

- **blind-02 — Primary care with a deductible waiver**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: The $35 copay replaces all other cost sharing for this visit.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-03 — Routine preventive screening**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: The stipulated screening is preventive, in network, and covered without cost sharing.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-04 — Last dollars before the out-of-pocket ceiling**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: $5,000 - $4,925 = $75 remaining OOP; nominal $200 sharing is capped at $75.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-05 — Permitted out-of-network excess**: error. {"phase": "compile", "type": "ProviderError", "message": "deepseek compilation failed after 1 attempts: output.policy.name: expected string. No fallback was substituted."} Gold rationale: $500 deductible + 40% of $500 + $500 permitted excess = $1,200.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "error": "output.policy.name: expected string"}]`.
- **blind-06 — Explicit cosmetic exclusion**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: This explicitly excluded service is the patient's full $800 charge; it does not accrue to OOP.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-07 — Two dates share one remaining deductible**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: First line uses $100 remaining deductible and $180 coinsurance; the next uses $100 coinsurance. Total $380.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 8, "validated_rules": 6, "validated_quote_spans": 8}]`.
- **blind-08 — Two distinct office visits**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: These are separate documented visits on separate dates: two $25 copays, total $50.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 10}]`.
- **blind-10 — Entire small allowance falls under deductible**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: The $150 allowance is smaller than the $1,000 unmet deductible, so responsibility is $150.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 11}]`.
- **blind-11 — Exclusion survives a satisfied OOP maximum**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: Covered sharing is $0 because OOP is met; the $1,200 cosmetic exclusion stays outside the cap.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 8, "validated_rules": 6, "validated_quote_spans": 8}]`.
- **blind-12 — Half-up cents on a 15 percent benefit**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: $333.33 times 15% = $49.9995, rounded half up to $50.00.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-13 — Copay precedes coinsurance**: error. {"phase": "compile", "type": "ProviderError", "message": "deepseek compilation failed after 1 attempts: output.policy.name: expected string. No fallback was substituted."} Gold rationale: $20 copay plus 20% of the remaining $180 = $56.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "error": "output.policy.name: expected string"}]`.
- **blind-14 — Out-of-network contract prohibits excess**: error. {"phase": "compile", "type": "ProviderError", "message": "deepseek compilation failed after 1 attempts: output.policy.name: expected string. No fallback was substituted."} Gold rationale: 50% of the $400 allowance is $200; this contract expressly prohibits the $500 excess.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "error": "output.policy.name: expected string"}]`.
- **blind-15 — Sequential lines consume the last OOP dollars**: error. {"phase": "compile", "type": "ProviderError", "message": "deepseek compilation failed after 1 attempts: output.policy.name: text must not be empty. No fallback was substituted."} Gold rationale: $90 OOP remains: first line owes $80; second owes only the last $10, for $90 total.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 8, "error": "output.policy.name: text must not be empty"}]`.
- **blind-16 — Authorized advanced imaging**: needs clarification. "Resolve validation errors before recalculation: incomplete_network; missing_rule" Gold rationale: Authorization is documented. 20% of $600 is $120.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 11}]`.
- **blind-18 — Coinsurance added to an exclusive copay**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: The visit owes only $30; adding 20% of $270 invents $54 of liability.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 5}]`.
- **blind-19 — Preventive mammogram treated as diagnostic**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: The documented routine preventive service has zero patient sharing, not $100.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 7}]`.
- **blind-20 — OOP ceiling ignored**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: Only $20 remains under the $5,000 maximum, so nominal $200 is capped at $20.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-22 — Excluded procedure incorrectly paid as covered**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: Explicit exclusion makes the full $700 payable; $140 is an underbill of $560.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-23 — Prohibited excess balance added to a bill**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: The plan and provider agreement prohibit excess: 20% of $200 = $40, regardless of the $900 charge.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 6, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-24 — Emergency surprise bill with stipulated protection**: error. {"phase": "compile", "type": "ProviderError", "message": "deepseek compilation failed after 1 attempts: output.policy.name: expected string. No fallback was substituted."} Gold rationale: The supplied protected recognized amount is $1,200. In-network terms apply: $200 remaining deductible plus 20% of $1,000 = $400; no excess.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 8, "error": "output.policy.name: expected string"}]`.
- **blind-25 — Protected ancillary anesthesiologist**: needs clarification. "Resolve validation errors before recalculation: incomplete_network; incomplete_interpretations; incomplete_interpretations" Gold rationale: Protected ancillary anesthesia uses 20% in-network sharing on the supplied $600 recognized amount = $120, with no balance bill.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 8, "validated_rules": 7, "validated_quote_spans": 11}]`.
- **blind-26 — Provider failed to obtain authorization**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: The explicit provider-liability clause bars transferring the $900 authorization denial to the patient.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 7}]`.
- **blind-27 — Patient expressly elects nonauthorized service**: needs clarification. "Resolve validation errors before recalculation: incomplete_network; missing_rule" Gold rationale: The stipulated valid advance undertaking invokes this plan's exclusion: full $1,400, outside OOP, rather than $280.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-28 — A duplicated office charge**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: Only one encounter occurred; one $45 copay is due. The duplicated line has $0 responsibility.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-29 — Documented low-complexity visit upcoded**: answer. No runtime error; amount and/or error decision differs from gold. Gold rationale: The acknowledged correct service is 99212, which owes $20, not the billed 99215's $70.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 8, "validated_rules": 7, "validated_quote_spans": 9}]`.
- **blind-30 — Panel component unbundled a second time**: error. {"phase": "compile", "type": "ProviderError", "message": "deepseek compilation failed after 1 attempts: output.policy.name: expected string. No fallback was substituted."} Gold rationale: Panel sharing is $20. Its already included electrolyte component carries no additional $12.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 8, "error": "output.policy.name: expected string"}]`.
- **blind-31 — Correct EOB but unexplained bill surcharge**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: EOB and contract agree on $55; the bill adds an unsupported $40.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 7}]`.
- **blind-32 — Insurance credit omitted from statement**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: 20% of $1,000 is $200. The bill's $700 reflects $500 of missing insurer credit.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 14}]`.
- **blind-34 — Opening deductible history understated**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: Verified prior deductible $850 leaves $150, then 20% of $350 = $70: total $220, not $460.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 6}]`.
- **blind-35 — OOP cap also limits deductible collection**: error. {"phase": "compile", "type": "ProviderError", "message": "deepseek compilation failed after 1 attempts: output.policy.name: text must not be empty. No fallback was substituted."} Gold rationale: Although $500 deductible remains, only $30 OOP remains. Covered responsibility cannot exceed $30.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "error": "output.policy.name: text must not be empty"}]`.
- **blind-36 — Excluded cosmetic spending wrongly consumes OOP**: needs clarification. "Resolve validation errors before recalculation: incomplete_network" Gold rationale: The $600 exclusion does not consume the $500 remaining OOP. Covered CT still owes $200; total $800.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 8, "validated_rules": 6, "validated_quote_spans": 10}]`.
- **blind-38 — Coinsurance assessed before subtracting copay**: error. {"phase": "compile", "type": "ProviderError", "message": "deepseek compilation failed after 1 attempts: output.policy.name: text must not be empty. No fallback was substituted."} Gold rationale: $100 deductible, then $25 copay, then 20% of $125 = $25. Total $150, not $155.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "error": "output.policy.name: text must not be empty"}]`.
- **blind-39 — Referral omission is provider liability**: needs clarification. "Resolve validation errors before recalculation: incomplete_network; missing_rule" Gold rationale: The explicit plan clause assigns this procedural denial to the participating provider, leaving $0 to the member.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 7, "validated_rules": 5, "validated_quote_spans": 11}]`.
- **blind-40 — Separate network pools and omitted permitted excess**: error. {"phase": "compile", "type": "ProviderError", "message": "deepseek compilation failed after 1 attempts: output.policy.name: expected string. No fallback was substituted."} Gold rationale: In network: $100 + 20% of $500 = $200. Out network: separate $500 deductible + 40% of $500 + $300 permitted balance = $1,000. Total $1,200; the $900 statement is an underbill.
  Provider attempt audit: `[{"attempt": 1, "proposed_rules": 8, "error": "output.policy.name: expected string"}]`.


## After fixes (not blind — cases were seen)

Product revision `49823fe85d3be2413d4e9bc255888819eb314596`. One additional pipeline invocation per case; no frozen input or expected answer changed. The original blind section above and its JSON are preserved byte for byte. The same observation adapter, gold totals, $1 tolerance and metric denominators are used. The follow-up is diagnostic and must not be described as new blind performance.

| Metric | Official blind | After fixes (not blind) |
| --- | ---: | ---: |
| Exact amount within $1 (all 40) | 15.0% | 70.0% |
| Abstain/dead-end | 82.5% | 7.5% |
| Error precision | 100.0% | 100.0% |
| Error recall (all 24 true errors) | 16.7% | 62.5% |
| False-positive rate (all 16 correct) | 0.0% | 0.0% |
| Resolved negative coverage | 12.5% | 93.8% |
| Range contains truth | n/a | n/a |
| Owed above bill (any scenario/line) | 0 | 0 |

Statuses: `{"answer": 37, "range": 0, "needs clarification": 3, "error": 0}`. Detection counts: `{"tp": 15, "fp": 0, "fn": 9, "tn": 15, "abstained_positive": 2, "abstained_negative": 1}`. Provider: DeepSeek `deepseek-v4-pro`; four workers, timeout 120 seconds. Actual compiler attempts 40; HTTP attempts 40. Configured validation/transport attempt limits one. Revised client may grant its explicit one extra no-supported-rules retry; actual compiler and HTTP attempts are retained. No case pipeline reruns.

### Root causes in the original run

| Cause | Cases | Relationship |
| --- | ---: | --- |
| Explicit balance/excess billing language rejected by local source validator | 24 | Primary; sums to 33 abstentions |
| Null or empty policy display name fails closed schema | 9 | Primary; sums to 33 abstentions |
| Compiled condition wording does not equal literal supplied claim confirmations (missing_rule) | 3 | Overlaps the 24 billing-language blocks |
| Incompatible shared ambiguity interpretation labels (incomplete_interpretations) | 1 | Overlaps the 24 billing-language blocks |
| Acknowledged upcode ignored; submitted code used | 1 | Wrong answered case, additional to 33 abstentions |
| EOB/bill format parsing, transport failure, missing allowance/opening history | 0 | None occurred in the official run |

Billing-language blocks by format: Reference card: balance billing = yes/no: 7; Question and answer: excess charges: 8; SBC table: prohibited/permitted cell: 8; Narrative: excess balance billing permitted: 1. All 24 were `incomplete_network` at the in-network balance-billing field. The nine errors were six null-name string failures and three empty-name failures. Secondary errors were `missing_rule` (3 cases: literal claim confirmations did not match compiled condition labels) and `incomplete_interpretations` (2 issues in 1 case). Recall was 4/24 because 19 erroneous cases abstained and one answered upcode case missed the error. The original run normalized structured EOB/bill observations; it did not test PDF/OCR or raw-format adapters. Unsupported legal/clinical/coding semantics remain distinct from the main balance-language gate.

### General code changes

- Evidence validation recognizes explicit billing prohibitions/permissions in either word order, yes/no reference fields, network-scoped question/answer text, and row-based/transposed SBC tables. It requires a billing heading, respects network scope, and preserves contradictions.
- Null/blank display names use a source heading or explicit plan name; numeric fields, source evidence and coverage remain strict.
- Combined product revision includes the other agents' generic interpretation normalization, human-readable clarification reasons, separate uncapped policy audits and patient-facing bill/payment bounds, plus bounded zero-temperature DeepSeek compilation. Source revisions are recorded below.

- `e2be3f2fd06b9e2c45e4a9d1fab9a2d664f6338b Validate explicit balance-billing language across SBC layouts and preserve unnamed plans`
- `3b3231fc03ef70f23c12ae9362f5aa1dbadb41df Bound DeepSeek retries and use zero-temperature compilation`
- `13232be1c47530814eacedaad2d858529ce8acdb Handle repeated rule IDs and keep clarification text human-readable`
- `4234ea3ebcc22fdd2d6d4e841bf53b9885a78eaf Keep independent policy audits distinct from bounded payment answers`
- `92bd83b801cba16c2eb4f1d64cab4d1323bf85b0 Deduplicate equivalent rules and evaluate conflicting source interpretations`

Post-run hardening (unit-tested; no additional live benchmark run):
- `edbef78a2421a028ddc10fe163f774a32906c380 Keep negated balance-billing permission from becoming an allowance`

The negation guard additionally preserves prohibitions such as ‘not permitted to balance bill’. The live metrics above remain attributed to the archived product revision, which precedes this final guard.

Patient-facing owed remains bounded by the statement, its credits and payments. Four frozen cases intentionally contain underbilling; their contractual gold liability can exceed the bill. They remain in the accuracy denominator, and the bounded payment answer may therefore differ from gold. Uncapped policy arithmetic in raw traces is not a payment recommendation. Unsupported authorization/referral, legal-protection and coding/bundling facts have not been converted into bespoke benchmark rules.

### Regressions

Before (committed original report): original synthetic benchmark exact calculation 8/10; end-to-end 8/10; discrepancy precision 100.0%, recall 83.3%, FPR 0.0%.

After (fresh fallback run): original synthetic benchmark exact calculation 8/10; end-to-end 8/10; discrepancy precision 100.0%, recall 83.3%, FPR 0.0%.

Built-in samples use original prose through the fallback compiler in both archived revisions:

| Sample | Before illustrated total | After illustrated total | Scenario count before → after | Same status/summary |
| --- | ---: | ---: | ---: | --- |
| aurora-imaging | $385.00–$385.00 | $385.00–$385.00 | 1 → 1 | True |
| mosaic-oop | $1,000.00–$1,000.00 | $1,000.00–$1,000.00 | 1 → 1 | True |
| mosaic-therapy | $40.00–$40.00 | $40.00–$40.00 | 3 → 3 | True |

Full unittest passed before both product-fix commits (197 tests; 9 skipped). Full unittest before the final report commit: 197 tests, 9 skipped; passed=True. Raw regression outputs are in `data/blind_benchmark/run-after-fixes/`; the original synthetic benchmark's pre-existing held-out failures remain reported.

### Per-case follow-up

| Case | Status | Predicted liability | Gold liability | Error flag / truth |
| --- | --- | ---: | ---: | --- |
| blind-01 | answer | $440.00 | $440.00 | False / False |
| blind-02 | answer | $35.00 | $35.00 | False / False |
| blind-03 | answer | $0.00 | $0.00 | False / False |
| blind-04 | answer | $75.00 | $75.00 | False / False |
| blind-05 | answer | $1,200.00 | $1,200.00 | False / False |
| blind-06 | answer | $800.00 | $800.00 | False / False |
| blind-07 | answer | $380.00 | $380.00 | False / False |
| blind-08 | answer | $50.00 | $50.00 | False / False |
| blind-09 | answer | $40.00 | $40.00 | False / False |
| blind-10 | answer | $150.00 | $150.00 | False / False |
| blind-11 | answer | $1,200.00 | $1,200.00 | False / False |
| blind-12 | answer | $50.00 | $50.00 | False / False |
| blind-13 | answer | $56.00 | $56.00 | False / False |
| blind-14 | answer | $200.00 | $200.00 | False / False |
| blind-15 | answer | $90.00 | $90.00 | False / False |
| blind-16 | needs clarification | — | $120.00 | None / False |
| blind-17 | answer | $360.00 | $360.00 | True / True |
| blind-18 | answer | $30.00 | $30.00 | True / True |
| blind-19 | answer | $0.00 | $0.00 | True / True |
| blind-20 | answer | $20.00 | $20.00 | True / True |
| blind-21 | answer | $80.00 | $80.00 | True / True |
| blind-22 | answer | $140.00 | $700.00 | False / True |
| blind-23 | answer | $40.00 | $40.00 | True / True |
| blind-24 | answer | $1,000.00 | $400.00 | False / True |
| blind-25 | answer | $720.00 | $120.00 | False / True |
| blind-26 | answer | $120.00 | $0.00 | True / True |
| blind-27 | answer | $200.00 | $1,400.00 | True / True |
| blind-28 | answer | $90.00 | $45.00 | False / True |
| blind-29 | answer | $70.00 | $20.00 | False / True |
| blind-30 | answer | $32.00 | $20.00 | False / True |
| blind-31 | answer | $55.00 | $55.00 | True / True |
| blind-32 | answer | $200.00 | $200.00 | True / True |
| blind-33 | answer | $120.00 | $120.00 | True / True |
| blind-34 | answer | $220.00 | $220.00 | True / True |
| blind-35 | answer | $30.00 | $30.00 | True / True |
| blind-36 | answer | $600.00 | $800.00 | False / True |
| blind-37 | answer | $80.00 | $80.00 | True / True |
| blind-38 | answer | $150.00 | $150.00 | True / True |
| blind-39 | needs clarification | — | $0.00 | None / True |
| blind-40 | needs clarification | — | $1,200.00 | None / True |

Remaining failures (preserved, no case repair or rerun):

- **blind-16** (needs clarification): "Some document details need review before calculation: No explicit coverage rule with confirmed conditions for 70553/in; calculation blocked."
- **blind-22** (answer): Amount or error decision differs from frozen gold.
- **blind-24** (answer): Amount or error decision differs from frozen gold.
- **blind-25** (answer): Amount or error decision differs from frozen gold.
- **blind-26** (answer): Amount or error decision differs from frozen gold.
- **blind-27** (answer): Amount or error decision differs from frozen gold.
- **blind-28** (answer): Amount or error decision differs from frozen gold.
- **blind-29** (answer): Amount or error decision differs from frozen gold.
- **blind-30** (answer): Amount or error decision differs from frozen gold.
- **blind-36** (answer): Amount or error decision differs from frozen gold.
- **blind-39** (needs clarification): "Some document details need review before calculation: No explicit coverage rule with confirmed conditions for 99214/in; calculation blocked."
- **blind-40** (needs clarification): "Some document details need review before calculation: Balance-billing terms are unknown; supply independent contract evidence for each affected line."

Full per-line outcomes, validation messages, attempts and code hashes: [after-fixes JSON](benchmark-blind-after-fixes.json).
