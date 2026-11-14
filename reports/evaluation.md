# Fineprint evaluation

Backend: **fallback**. **Synthetic data only**. Generated 2026-11-14T19:22:54.439378+00:00.

Parser matches pre-holdout freeze: **True**.

| Split | Policies / cases | Extraction P / R | Exact calculation | Discrepancy P / R | FPR | Traceability / coverage | End-to-end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| seen | 3 / 6 | 100.0% / 100.0% | 6/6 (100.0%) | 100.0% / 100.0% | 0.0% | 100.0% / 100.0% | 6/6 (100.0%) |
| held_out | 2 / 4 | 100.0% / 56.8% | 2/4 (50.0%) | 100.0% / 50.0% | 0.0% | 100.0% / 52.9% | 2/4 (50.0%) |
| all | 5 / 10 | 100.0% / 84.8% | 8/10 (80.0%) | 100.0% / 83.3% | 0.0% | 100.0% / 81.8% | 8/10 (80.0%) |

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
| harbor-oop-ignored | held_out | blocked | $50.00 | False | None / True | False |
| harbor-correct-office | held_out | blocked | $20.00 | False | None / False | False |

Failures / unresolved policies:

- harbor: Fallback could not establish both network deductibles, OOP caps and balance-billing rules

Methodology:

- Author-created format holdout; not blinded and not evidence of real-world performance.
- Extraction micro precision/recall: financial fields per network and per code/network interpretation; each policy scored once; IDs/labels/order ignored.
- Calculation exactness: all nine integer-cent fields on every line, network, complete distinct scenario outcome set, scenario count and conditional status.
- Discrepancy: any EOB patient-total difference per line in a nonconditional case. Ambiguous/missing-fact cases abstain and are excluded from labeled precision/recall.
- Compilation failures remain in extraction recall, calculation and end-to-end denominators; positive failures count as false negatives. Negative failures abstain, not true negatives; FPR denominator is all gold-negative cases.
- Traceability is valid spans / emitted rules; coverage also counts missing rules from failed policies.
- End-to-end success requires exact extraction, exact calculations and final bill reconciliation, complete evidence and correct discrepancy decision or justified conditional abstention.
- No live LLM measurement unless backend explicitly names a real configured provider. No LLM used for arithmetic.
