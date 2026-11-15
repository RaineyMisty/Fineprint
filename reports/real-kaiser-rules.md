# Real kaiser policy compilation

Split: **dev**. Held-out documents use one provider request with no validation or transport retries.

Source: `data/real_private/docs/kaiser_2026_ca_gold80_sbc.txt` (private).
Text SHA256: `53d9f1b2e5417de48c663972c0794ae6308bb8460f2011a995487d83485ca949`.

LLM input uses locally ranked cost-sharing source sections; evidence is located and validated against the complete original source. No manual gold rules or invented member IDs.

- **fallback** / no model: **failed**. Fallback requires a '# Insurer — Plan' title and Policy/Member/Period/USD header; other formats need a provider or transcription
- **deepseek** / deepseek-v4-pro: **validated**. Validated after 3 attempt(s).
  Validated rules: 16; claim-ready: **False**.
  Service rules: 14; validated quote spans: 31; distinct spans: 31.
  Conditionally executable subset: **True**. Missing billing terms need independent contract evidence; categories/conditions need reviewer assignment.

  Compiled services:
  - Specialist visit (in); category `Specialist visit`; conditions: none.
  - X-ray (in); category `X-ray`; conditions: none.
  - Lab tests (in); category `Lab tests`; conditions: none.
  - Generic drugs (Tier 1) - retail (in); category `Generic drugs (Tier 1)`; conditions: Retail supply up to 30 days.
  - Preferred brand drugs (Tier 2) - retail (in); category `Preferred brand drugs (Tier 2)`; conditions: Retail supply up to 30 days.
  - Non-preferred brand drugs (Tier 2) - retail (in); category `Non-preferred brand drugs (Tier 2)`; conditions: Retail supply up to 30 days.
  - Emergency room care (in); category `Emergency room care`; conditions: Not admitted as inpatient.
  - Urgent care (in); category `Urgent care`; conditions: none.
  - Outpatient mental health - individual (in); category `Outpatient services`; conditions: Individual visit.
  - Home health care (in); category `Home health care`; conditions: none.
  - Rehabilitation services - outpatient (in); category `Rehabilitation services`; conditions: Outpatient.
  - Habilitation services - outpatient (in); category `Habilitation services`; conditions: Outpatient.
  - Durable medical equipment (in); category `Durable medical equipment`; conditions: none.
  - Hospice service (in); category `Hospice service`; conditions: none.

  Not compiled / limitations (provider-reported, not an exhaustive recall score):
  - Out-of-network coverage is generally not provided; only emergency room, emergency medical transportation, and urgent care when temporarily outside service area are covered out-of-network. No out-of-network deductible or OOP max is defined.
  - Mail order pharmacy benefits are omitted because they are per-prescription charges not directly comparable to retail copays and have supply limits; the engine handles simple retail copays.
  - Specialty drugs (Tier 4) have 20% coinsurance up to $250 per prescription; the cap cannot be represented by the simple coinsurance model, so benefit is omitted.
  - Facility fee for hospital stay ($375/day up to 5 days) is per-day cap, which is not representable; omitted.
  - Inpatient mental health has $375/day up to 5 days; per-day cap omitted.
  - Rehabilitation services inpatient $375/day up to 5 days; per-day cap omitted.
  - Habilitation services inpatient $375/day up to 5 days; per-day cap omitted.
  - Skilled nursing care is $150/day up to 5 days; per-day cap omitted.
  - Outpatient services for mental health: other outpatient services no charge; group mental health $20, group substance abuse $5; these variants omitted as not simple individual visit.
  - Maternity office visits no charge and childbirth/delivery professional services not applicable; facility services $375/day up to 5 days; per-day cap omitted.
  - Children's eye exam, glasses, dental check-up no charge; but these are age-limited and require additional information; omitted.
  - No explicit balance billing statement for in-network providers; inferred as false from HMO plan type and network use but not directly quoted.
  - No explicit out-of-network balance billing language; set to null due to absence of clear statement.
  - No effective end date provided.
  - Partial source review: sections were selected locally; omitted services require review and have no executable rules.
  - Network out omitted: deductible or OOP limit is not established. Claims in that network require separate review, including emergency exceptions.
  - Dropped rule benefits.B1 (Primary care visit): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B10 (Facility fee (ambulatory surgery center)): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B12 (Emergency medical transportation): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B15 (Inpatient mental health): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B19 (Skilled nursing care): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B3 (Preventive care/screening/immunization): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B6 (Imaging (CT/PET scans, MRI)): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule networks.in.balance_billing: missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.

  Source-backed rule values:
  - `networks.in.deductible_cents`: [1840:2069] “What is the overall $0 See the Common Medical Events chart below for your costs for services this plan” | [2070:2227] “deductible? covers.” | [6802:6922] “All copayment and coinsurance costs shown in this chart are after your deductible has been met, if a deductible applies.”
  - `networks.in.oop_max_cents`: [3570:3804] “What is the out-of-pocket $9,200 Individual / $18,400 Family The out-of-pocket limit is the most you could pay in a year for covered services. If” | [3805:4034] “limit for this plan? you have other family members in this plan, they have to meet their own out-of-”
  - `benefits.B2`: [7536:7656] “If you visit a health Specialist visit $70 / visit Not covered None”
  - `benefits.B4`: [8315:8411] “Diagnostic test (x- X-ray: $75 / encounter Not covered None”
  - `benefits.B5`: [8436:8486] “ray, blood work) Lab tests: $40 / encounter”
  - `benefits.B7`: [8853:8987] “Generic drugs (Tier $18 / prescription (retail). $36 / Not covered supply (mail order). Contraceptives are no” | [9012:9062] “1) prescription (mail order).” | [9063:9219] “If you need drugs to charge. Subject to formulary guidelines.”
  - `benefits.B8`: [9384:9541] “condition Preferred brand $60 / prescription (retail). $120 / Not covered supply (mail order). Subject to formulary” | [9564:9669] “drugs (Tier 2) prescription (mail order). guidelines.”
  - `benefits.B9`: [9850:10014] “drug coverage is Non-preferred brand $60 / prescription (retail). $120 / under this plan aligns with the cost-sharing for” | [10101:10112] “Not covered” | [10113:10274] “available at drugs (Tier 2) prescription (mail order). preferred brand drugs (Tier 2), when approved”
  - `benefits.B11`: [12231:12363] “Emergency room Copayment waived if admitted directly to the” | [12408:12456] “$350 / visit $350 / visit” | [12479:12592] “care hospital as an inpatient.”
  - `benefits.B13`: [12933:13058] “Urgent care $40 / visit Not covered outside the service area: $40 / visit”
  - `benefits.B14`: [13580:13735] “If you need mental $40 / individual visit. No charge Mental / Behavioral health: $20 / group visit” | [13736:13879] “health, behavioral Outpatient services for other outpatient services. Not covered Substance Abuse: $5 / group visit” | [13880:13900] “health, or substance”
  - `benefits.B16`: [16121:16233] “Home health care $30 / visit Not covered 100 visits / year.”
  - `benefits.B17`: [16258:16356] “Rehabilitation Outpatient: $40 / visit; Inpatient: Not covered None” | [16381:16428] “services $375 / day up to 5 days.”
  - `benefits.B18`: [16446:16568] “recovering or have Habilitation services Outpatient: $40 / visit; Inpatient: Not covered None” | [16569:16640] “other special health $375 / day up to 5 days.”
  - `benefits.B20`: [16805:16927] “Durable medical 20% coinsurance Not covered Prior authorization required” | [16952:16961] “equipment”
  - `benefits.B21`: [16986:17084] “Hospice service No charge Not covered None”
  Source selection: 18796/47390 characters; omitted sections: True.
  Request configuration: `{"response_format": "json_object", "max_tokens_initial": 32768, "max_tokens": 32768, "max_tokens_ceiling": 65536, "thinking": "disabled", "timeout_seconds": 300, "attempt_limit": 3, "transport_attempt_limit": 2, "evidence_spans": "selected original source lines with local offsets; legacy quotes use whitespace-normalized search"}`.

Only validated compilations contain executable rules and clause evidence. A failure has `compilation: null`; no rule or patient total is inferred.

Input excerpts (physical PDF pages; these are not compiled rules):

- p. 1: “What is the out-of-pocket $9,200 Individual / $18,400 Family                                                                                          The out-of”
- p. 3: “If you need mental                          $40 / individual visit. No charge                                 Mental / Behavioral health: $20 / group visit”

Official links and rights notes: [metadata manifest](../data/real_manifest.csv). No redistribution license; PDF/text not in this repo.

The separately measured **PDF upload path** retained 15 rules and 42 quote spans, including primary care, specialist, urgent care, ER, X-ray, lab, imaging and generic drugs. The real-policy / synthetic-claim HTTP demo recalculated $50. See [HTTP demo and hand-check](real-kaiser-http-demo.md). Its pypdf extraction differs from this pdftotext run; rules are not silently merged.
