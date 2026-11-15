# After fixes (not blind — cases were seen)

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
