# Fineprint evaluation

Backend: **deepseek**. **Synthetic data only**. Generated 2026-11-15T07:24:33.393304+00:00.

Model: **deepseek-v4-pro**. Request configuration: `{"response_format": "json_object", "max_tokens_initial": 32768, "max_tokens": 32768, "max_tokens_ceiling": 65536, "thinking": "disabled", "timeout_seconds": 300, "attempt_limit": 3, "transport_attempt_limit": 2, "evidence_spans": "local whitespace-normalized quote search"}`.

Parser matches pre-holdout freeze: **False**.

| Split | Policies / cases | Extraction P / R | Exact calculation | Discrepancy P / R | FPR | Traceability / coverage | End-to-end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| seen | 3 / 6 | 100.0% / 100.0% | 6/6 (100.0%) | 100.0% / 100.0% | 0.0% | 100.0% / 100.0% | 6/6 (100.0%) |
| held_out | 2 / 4 | 100.0% / 100.0% | 4/4 (100.0%) | 100.0% / 100.0% | 0.0% | 100.0% / 100.0% | 4/4 (100.0%) |
| all | 5 / 10 | 100.0% / 100.0% | 10/10 (100.0%) | 100.0% / 100.0% | 0.0% | 100.0% / 100.0% | 10/10 (100.0%) |

| Case | Split | Fineprint patient totals (USD) | Gold patient totals (USD) | Exact | Discrepancy (predicted / gold) | Success |
| --- | --- | --- | --- | --- | --- | --- |
| aurora-imaging | seen | $385.00 | $385.00 | True | True / True | True |
| mosaic-oop | seen | $1000.00 | $1000.00 | True | True / True | True |
| mosaic-therapy | seen | $0.00, $40.00, $60.00, $300.00 | $0.00, $40.00, $60.00, $300.00 | True | None / None | True |
| aurora-correct | seen | $25.00 | $25.00 | True | False / False | True |
| aurora-coinsurance-on-copay | seen | $25.00 | $25.00 | True | True / True | True |
| aurora-wrong-network | seen | $200.00 | $200.00 | True | True / True | True |
| cedar-preventive-charged | held_out | $0.00 | $0.00 | True | True / True | True |
| cedar-correct-specialist | held_out | $35.00 | $35.00 | True | False / False | True |
| harbor-oop-ignored | held_out | $50.00 | $50.00 | True | True / True | True |
| harbor-correct-office | held_out | $20.00 | $20.00 | True | False / False | True |

Failures / unresolved policies:


Methodology:

- Author-created format holdout; not blinded and not evidence of real-world performance.
- Extraction micro precision/recall: financial fields per network and per code/network interpretation; each policy scored once; IDs/labels/order ignored.
- Calculation exactness: all nine integer-cent fields on every line, network, complete distinct scenario outcome set, scenario count and conditional status.
- Discrepancy: any EOB patient-total difference per line in a nonconditional case. Ambiguous/missing-fact cases abstain and are excluded from labeled precision/recall.
- Compilation failures remain in extraction recall, calculation and end-to-end denominators; positive failures count as false negatives. Negative failures abstain, not true negatives; FPR denominator is all gold-negative cases.
- Traceability is valid spans / emitted rules; coverage also counts missing rules from failed policies.
- End-to-end success requires exact extraction, exact calculations and final bill reconciliation, complete evidence and correct discrepancy decision or justified conditional abstention.
- No live LLM measurement unless backend explicitly names a real configured provider. No LLM used for arithmetic.
- Synthetic compiler outputs, exact source spans and attempts are saved per policy; claim/EOB/bill data and gold policy answers are never sent to the model.
- The shared LLM prompt was not tuned on held-out insurers or their gold answers; validation retries use local validation errors only.
