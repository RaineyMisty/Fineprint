# Fineprint evaluation

Backend: **deepseek**. **Synthetic data only**. Generated 2026-11-15T07:25:03.809156+00:00.

Model: **deepseek-flash**. Request configuration: `{"response_format": "json_object", "max_tokens_initial": 32768, "max_tokens": 32768, "max_tokens_ceiling": 65536, "thinking": "disabled", "timeout_seconds": 300, "attempt_limit": 3, "transport_attempt_limit": 2, "evidence_spans": "local whitespace-normalized quote search"}`.

Parser matches pre-holdout freeze: **False**.

| Split | Policies / cases | Extraction P / R | Exact calculation | Discrepancy P / R | FPR | Traceability / coverage | End-to-end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| seen | 3 / 6 | 92.6% / 92.6% | 1/6 (16.7%) | 100.0% / 25.0% | 0.0% | 100.0% / 100.0% | 1/6 (16.7%) |
| held_out | 2 / 4 | 86.5% / 86.5% | 0/4 (0.0%) | n/a / 0.0% | 0.0% | 100.0% / 100.0% | 0/4 (0.0%) |
| all | 5 / 10 | 90.5% / 90.5% | 1/10 (10.0%) | 100.0% / 16.7% | 0.0% | 100.0% / 100.0% | 1/10 (10.0%) |

| Case | Split | Fineprint patient totals (USD) | Gold patient totals (USD) | Exact | Discrepancy (predicted / gold) | Success |
| --- | --- | --- | --- | --- | --- | --- |
| aurora-imaging | seen | blocked | $385.00 | False | None / True | False |
| mosaic-oop | seen | $1000.00 | $1000.00 | True | True / True | True |
| mosaic-therapy | seen | blocked | $0.00, $40.00, $60.00, $300.00 | False | None / None | False |
| aurora-correct | seen | blocked | $25.00 | False | None / False | False |
| aurora-coinsurance-on-copay | seen | blocked | $25.00 | False | None / True | False |
| aurora-wrong-network | seen | blocked | $200.00 | False | None / True | False |
| cedar-preventive-charged | held_out | blocked | $0.00 | False | None / True | False |
| cedar-correct-specialist | held_out | blocked | $35.00 | False | None / False | False |
| harbor-oop-ignored | held_out | blocked | $50.00 | False | None / True | False |
| harbor-correct-office | held_out | blocked | $20.00 | False | None / False | False |

Failures / unresolved policies:

- mosaic-therapy: Precedence between in-network benefit T1 (deductible then 20% coinsurance) and T2 ($40 copay, waived deductible, no coinsurance) for CPT 97110 is unresolved per section 8; both interpretations retained in ambiguity group T1_T2_therapy_in.; No explicit source HCPCS/CPT codes are provided for service categories other than 97110; no additional code mappings created.
- harbor: No out-of-network member cost-share (copay/coinsurance) is stated for CPT 70551 or 99213, so out-of-network benefits cannot be constructed.; No source CPT/HCPCS codes are provided for services other than 70551 and 99213; other categories are not executable and are not enumerated.

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
