# Real Kaiser SBC PDF → synthetic claim: measured HTTP demo

Status: **passed**. DeepSeek compiled the actual uploaded PDF text; all claim, bill, contracted allowance, balance-billing and prior-spend facts are **SYNTHETIC**.

Measured 2026-11-15T09:41:53.892015+00:00; elapsed 374.314 seconds. Retained **15 rules**, **42 exact quote spans**. Source SHA256: `e0bcadefad9be83db174abe0afe8b387844d8d3b99664d690c13bee5e0e7fdfb`.

All six HTTP requests returned 200: status, demo inputs, extract, compile, check, and a second check that perturbed adjudication/bill amounts. The check reused the signed compilation; it did not ask the LLM to calculate.

## Hand-check

The quoted individual deductible is $0, the OOP maximum is $9,200, and in-network urgent care is $40 per visit. Synthetic opening OOP spend is $9,150, so only $50 remains. First visit: min($40, $50) = $40. Second visit: min($40, $10) = $10. **Total $50; closing OOP $9,200.** The synthetic allowances ($150 and $200) exceed the copays. Synthetic independent contract evidence specifies no balance billing.

EOB patient total: $80. Bill patient total: $100. Fineprint: $50. Difference from EOB: $30; difference from bill: $50. These are invented demo discrepancies, not measured real-world overcharges.

Recalculated insurer payment: $110 + $190 = $300; adjustments: $50 + $100 = $150. Conservation: $500 billed = $50 patient + $300 insurer + $150 adjustment. Increasing only EOB and bill responsibility by $1 leaves the independently calculated $50 unchanged.

## Retained service rules

| Service | Copay | Coinsurance | Required claim facts |
|---|---:|---:|---|
| Primary care visit | $40.00 | 0% | None specified |
| Specialist visit | $70.00 | 0% | Referral obtained before seeing specialist OR permitted self-referral |
| Preventive care/screening/immunization | $0.00 | 0% | None specified |
| Diagnostic test - X-ray | $75.00 | 0% | None specified |
| Diagnostic test - Lab tests | $40.00 | 0% | None specified |
| Imaging (CT/PET scans, MRIs) | $75.00 | 0% | None specified |
| Generic drugs (Tier 1) - Retail | $18.00 | 0% | Retail prescription; Up to 30-day supply; Medication is not a contraceptive |
| Preferred brand drugs (Tier 2) - Retail | $60.00 | 0% | Retail prescription; Up to 30-day supply |
| Non-preferred brand drugs (Tier 2) - Retail | $60.00 | 0% | Retail prescription; Up to 30-day supply; Approved through formulary exception process |
| Emergency room care | $350.00 | 0% | Not admitted directly to the hospital as an inpatient |
| Urgent care | $40.00 | 0% | None specified |
| Outpatient mental/behavioral health - individual visit | $40.00 | 0% | Mental/behavioral health; Individual visit |
| Office visits (prenatal) | $0.00 | 0% | Pregnancy |

## Source evidence

- `networks.in.deductible_cents`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan”
- `networks.in.oop_max_cents`: [3149:3334] “limit for this plan? $9,200 Individual / $18,400 Family you have other family members in this plan, they have to meet their own out-of-”
- `benefits.B1`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [6177:6198] “Primary care visit to” | [6227:6346] “treat an injury or $40 / visit Not covered None” | [6375:6382] “illness”
- `benefits.B2`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [4948:5142] “Do you need a referral to Yes, but you may self-refer to certain This plan will pay some or all of the costs to see a specialist for covered services but” | [5143:5307] “see a specialist? specialists. only if you have a referral before you see the specialist.” | [6383:6530] “If you visit a health Specialist visit $70 / visit Not covered None”
- `benefits.B3`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [6719:6907] “office or clinic Preventive care/ preventive. Ask your provider if the services” | [6936:7094] “screening/ No charge Not covered needed are preventive. Then check what your” | [7123:7256] “immunization plan will pay for.”
- `benefits.B4`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [7286:7405] “Diagnostic test (x- X-ray: $75 / encounter Not covered None”
- `benefits.B5`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [7406:7489] “If you have a test ray, blood work) Lab tests: $40 / encounter”
- `benefits.B6`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [7518:7637] “Imaging (CT/PET $75 / procedure Not covered None” | [7666:7679] “scans, MRI's)”
- `benefits.B7`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [7708:7870] “Generic drugs (Tier $18 / prescription (retail). $36 / Up to a 30-day supply (retail); up to a 100-day” | [7899:8056] “1) prescription (mail order). Not covered supply (mail order). Contraceptives are no” | [8057:8240] “If you need drugs to charge. Subject to formulary guidelines.”
- `benefits.B8`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [8241:8431] “treat your illness or Preferred brand $60 / prescription (retail). $120 / Up to a 30-day supply (retail); up to a 100-day” | [8432:8616] “condition drugs (Tier 2) prescription (mail order). Not covered supply (mail order). Subject to formulary” | [8617:8771] “More information guidelines.”
- `benefits.B9`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [8962:9153] “drug coverage is Non-preferred brand $60 / prescription (retail). $120 / Not covered under this plan aligns with the cost-sharing for” | [9154:9342] “available at drugs (Tier 2) prescription (mail order). preferred brand drugs (Tier 2), when approved” | [9343:9526] “www.kp.org/formulary through the formulary exception process.”
- `benefits.B10`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [11173:11330] “Emergency room $350 / visit $350 / visit Copayment waived if admitted directly to the” | [11359:11497] “care hospital as an inpatient.”
- `benefits.B11`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [11728:11884] “Urgent care $40 / visit Not covered Non-Plan providers covered when temporarily”
- `benefits.B12`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [12592:12778] “If you need mental Outpatient services $40 / individual visit. No charge Not covered Mental / Behavioral health: $20 / group visit”
- `benefits.B13`: [1580:1765] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [13504:13660] “Office visits No charge Not covered apply. Maternity care may include tests and”

## Omitted rows / limits

This upload run did not retain emergency medical transportation, outpatient surgery facility fees, bundled professional fees, inpatient/day-capped services, group/other outpatient mental-health variants, home health, rehabilitation/habilitation, skilled nursing, durable medical equipment, hospice, children’s vision/dental, mail-order drugs, or capped specialty drugs. See the retained-service table rather than assuming coverage for an omitted row. The separate pdftotext run retained a different subset; the two inputs are not silently merged.

Missing in-network balance-billing terms require independent contract evidence. Out-of-network coverage and emergency exceptions are omitted, not treated as a blanket exclusion. Exact quote matching is a provenance check and does not prove every table interpretation; category assignment and eligibility conditions require review.

Raw measurement and compilation: [JSON](real-kaiser-http-demo.json). Web demo inputs: `fineprint/demos/kaiser-real-sbc.json`.
