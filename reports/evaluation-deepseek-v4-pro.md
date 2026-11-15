# Fineprint evaluation

Backend: **deepseek**. **Synthetic data only**. Generated 2026-11-15T02:46:16.072049+00:00.

Model: **deepseek-v4-pro**. Request configuration: `{"response_format": "json_object", "max_tokens": 16384, "thinking": "disabled", "timeout_seconds": 60, "attempt_limit": 3}`.

Parser matches pre-holdout freeze: **True**.

| Split | Policies / cases | Extraction P / R | Exact calculation | Discrepancy P / R | FPR | Traceability / coverage | End-to-end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| seen | 3 / 6 | n/a / 0.0% | 0/6 (0.0%) | n/a / 0.0% | 0.0% | n/a / 0.0% | 0/6 (0.0%) |
| held_out | 2 / 4 | n/a / 0.0% | 0/4 (0.0%) | n/a / 0.0% | 0.0% | n/a / 0.0% | 0/4 (0.0%) |
| all | 5 / 10 | n/a / 0.0% | 0/10 (0.0%) | n/a / 0.0% | 0.0% | n/a / 0.0% | 0/10 (0.0%) |

| Case | Split | Fineprint patient totals (USD) | Gold patient totals (USD) | Exact | Discrepancy (predicted / gold) | Success |
| --- | --- | --- | --- | --- | --- | --- |
| aurora-imaging | seen | blocked | $385.00 | False | None / True | False |
| mosaic-oop | seen | blocked | $1000.00 | False | None / True | False |
| mosaic-therapy | seen | blocked | $0.00, $40.00, $60.00, $300.00 | False | None / None | False |
| aurora-correct | seen | blocked | $25.00 | False | None / False | False |
| aurora-coinsurance-on-copay | seen | blocked | $25.00 | False | None / True | False |
| aurora-wrong-network | seen | blocked | $200.00 | False | None / True | False |
| cedar-preventive-charged | held_out | blocked | $0.00 | False | None / True | False |
| cedar-correct-specialist | held_out | blocked | $35.00 | False | None / False | False |
| harbor-oop-ignored | held_out | blocked | $50.00 | False | None / True | False |
| harbor-correct-office | held_out | blocked | $20.00 | False | None / False | False |

Failures / unresolved policies:

- aurora-imaging: deepseek compilation failed after 3 attempts: Every executable rule must have exactly one evidence entry. No fallback was substituted.
- mosaic-oop: deepseek compilation failed after 3 attempts: Every executable rule must have exactly one evidence entry. No fallback was substituted.
- mosaic-therapy: deepseek compilation failed after 3 attempts: Every executable rule must have exactly one evidence entry. No fallback was substituted.
- cedar: deepseek compilation failed after 3 attempts: Every executable rule must have exactly one evidence entry. No fallback was substituted.
- harbor: deepseek compilation failed after 3 attempts: Evidence quote/span does not match the source document. No fallback was substituted.

Methodology:

- Author-created format holdout; not blinded and not evidence of real-world performance.
- Extraction micro precision/recall: financial fields per network and per code/network interpretation; each policy scored once; IDs/labels/order ignored.
- Calculation exactness: all nine integer-cent fields on every line, network, complete distinct scenario outcome set, scenario count and conditional status.
- Discrepancy: any EOB patient-total difference per line in a nonconditional case. Ambiguous/missing-fact cases abstain and are excluded from labeled precision/recall.
- Compilation failures remain in extraction recall, calculation and end-to-end denominators; positive failures count as false negatives. Negative failures abstain, not true negatives; FPR denominator is all gold-negative cases.
- Traceability is valid spans / emitted rules; coverage also counts missing rules from failed policies.
- End-to-end success requires exact extraction, exact calculations and final bill reconciliation, complete evidence and correct discrepancy decision or justified conditional abstention.
- No live LLM measurement unless backend explicitly names a real configured provider. No LLM used for arithmetic.
- The shared LLM prompt was not tuned on held-out insurers or their gold answers; validation retries use local validation errors only.
