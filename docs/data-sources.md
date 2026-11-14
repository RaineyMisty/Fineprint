# Future data collection

Every bundled document is synthetic. No public document was copied into a patient case. Links were checked on **2026-11-14**; these are collection candidates, not implemented connectors.

| Public source | Material | Limits / next action |
| --- | --- | --- |
| [CMS SBC template PDF](https://www.cms.gov/CCIIO/Resources/Forms-Reports-and-Other-Resources/Downloads/SBC-Template-Accessible-Format-01-2020.pdf) | Standard summary fields and coverage examples. | A template is neither an actual plan nor a complete policy. Record its version; use it for extraction benchmarks. |
| [UnitedHealthcare SBC page and sample PDF](https://www.uhc.com/understanding-health-insurance/how-does-health-insurance-work/summary-of-benefits-and-coverage) | Real public insurer presentation and sample. | Collect plan/year-specific SBCs, complete policies, endorsements and schedules across insurers. Summaries omit details. |
| [CMS Hospital Price Transparency](https://www.cms.gov/priorities/key-initiatives/hospital-price-transparency/hospitals) | Hospital standard-charge files, including payer-specific negotiated rates. | Match exact plan/provider/service/setting/version. A public rate alone is not an EOB or final liability. |
| [CMS Transparency in Coverage guidance](https://www.cms.gov/initiatives/healthplan-price-transparency/overview/public-data) | Payer-published machine-readable in-network rates and out-of-network allowed amounts. | CMS describes these files; issuers publish them. Use bounded, versioned ingestion for large files. Historical de-identified allowed amounts do not guarantee an individual rate. |

## Matched cases require separate collection

Public policies/rates cannot establish member eligibility, provider participation on a date, opening deductible history, controlling endorsements or actual hospital credits. Policy/EOB/bill trios need permissioned, de-identified collection with supporting history and rights to retain/use the documents.

For each case retain:

1. Complete policy, schedules/endorsements, effective dates, plan year and document version/hash.
2. Original/corrected EOBs, claim/line IDs, dates, provider IDs, codes/modifiers/units, network, charges/allowances and adjustment/denial reasons.
3. Itemized bill and account ledger, remittances, contractual credits, patient payments/refunds and current balance with an as-of date.
4. Pre-claim deductible/OOP history and pool design, clearly distinguishing pre-claim from post-claim figures.
5. Independent rate evidence, URLs/locations, retrieval dates and effective periods. Keep EOB-only allowances labeled.
6. Clause page/spans, reviewed executable rules, unresolved interpretations, expected calculations and reviewer rationale.

Real health information does not belong in this public demo repository. A future authorized corpus needs controlled storage, privacy review, de-identification, access and retention controls. Those capabilities are not claimed by this demo.

## Measure generalization

Fictional Aurora grid/CSV and Mosaic narrative/ledger adapters demonstrate the interfaces, not measured performance on real insurers. Expand insurers, plan products, years and layouts; hold out entire insurers. Evaluate these separately:

- Entity/line linking and mismatch detection.
- Clause retrieval, exceptions and citation accuracy.
- Rule extraction precision/recall and unsupported-rule detection.
- Per-line cost sharing and accumulator accuracy against reviewed expectations.
- Preserved uncertainty, compatible interpretations across lines and conditional/blocked behavior.
- Rate provenance and dependence on EOB-derived inputs.

Include correct adjudications, overcharges, undercharges, bill-credit errors, exclusions, exhausted caps and unresolved cases. Favorable results do not define correctness; independent application of verified terms does.
