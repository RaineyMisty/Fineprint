# Real ambetter policy compilation

Split: **held_out**. Held-out documents use one provider request with no validation or transport retries.

Source: `data/real_private/docs/ambetter_2026_ca_gold80_hmo_sbc.txt` (private).
Text SHA256: `ae7f38f5c2a252c74af0aa5df14bb1ab58849e2eaca53f1d49427b44c5bf5180`.

LLM input uses locally ranked cost-sharing source sections; evidence is located and validated against the complete original source. No manual gold rules or invented member IDs.

- **fallback** / no model: **failed**. Fallback requires a '# Insurer — Plan' title and Policy/Member/Period/USD header; other formats need a provider or transcription
- **deepseek** / deepseek-v4-pro: **validated**. Validated after 1 attempt(s).
  Validated rules: 21; claim-ready: **False**.
  Service rules: 19; validated quote spans: 55; distinct spans: 52.
  Conditionally executable subset: **True**. Missing billing terms need independent contract evidence; categories/conditions need reviewer assignment.

  Compiled services:
  - Primary care visit to treat an injury or illness (in); category `Primary care visit to treat an injury or illness`; conditions: none.
  - Specialist visit (in); category `Specialist visit`; conditions: Prior authorization obtained.
  - Preventive care/screening/immunization (in); category `Preventive care/screening/immunization`; conditions: none.
  - Imaging (CT/PET scans, MRIs) (in); category `Imaging (CT/PET scans, MRIs)`; conditions: Prior authorization obtained.
  - Generic drugs (Tier 1) - Retail (in); category `Generic drugs (Tier 1)`; conditions: Retail supply within 30 days.
  - Preferred brand drugs (Tier 2) - Retail (in); category `Preferred brand drugs (Tier 2)`; conditions: Retail supply within 30 days, Prior authorization if required for select drugs.
  - Non-preferred brand drugs (Tier 3) - Retail (in); category `Non-preferred brand drugs (Tier 3)`; conditions: Retail supply within 30 days, Prior authorization if required for select drugs.
  - Physician/surgeon fees (outpatient surgery) (in); category `Physician/surgeon fees`; conditions: none.
  - Emergency room care - Facility (in); category `Emergency room care`; conditions: Not admitted as inpatient.
  - Emergency medical transportation - Medical, mental health & substance use disorders (in); category `Emergency medical transportation`; conditions: none.
  - Urgent care - Medical, mental health & substance use disorders (in); category `Urgent care`; conditions: none.
  - Office visits (pregnancy) - Prenatal (in); category `Office visits`; conditions: Prenatal.
  - Office visits (pregnancy) - Postnatal (in); category `Office visits`; conditions: Postnatal.
  - Childbirth/delivery professional services (in); category `Childbirth/delivery professional services`; conditions: none.
  - Home health care (in); category `Home health care`; conditions: Prior authorization obtained, Visits within 100 per calendar year.
  - Rehabilitation services (in); category `Rehabilitation services`; conditions: Prior authorization obtained.
  - Habilitation services (in); category `Habilitation services`; conditions: Prior authorization obtained.
  - Durable medical equipment (in); category `Durable medical equipment`; conditions: Prior authorization obtained.
  - Hospice services (in); category `Hospice services`; conditions: Prior authorization obtained.

  Not compiled / limitations (provider-reported, not an exhaustive recall score):
  - Out-of-network deductible and OOP maximum not specified; the plan uses in-network cost-sharing for emergencies but does not state a separate out-of-network deductible or OOP maximum.
  - In-network balance billing not explicitly stated; generic network language suggests out-of-network providers may balance bill, but in-network balance billing is not addressed.
  - Omitted benefit rows with per-day or multi-day caps: Hospital facility fee ($375 copay/day for max 5 days), Inpatient mental health services ($375 copay/day for max 5 days), Childbirth/delivery facility services ($375 copay/day for max 5 days), Skilled nursing center ($150 copay/day for max 5 days) because the engine cannot represent per-day caps.
  - Omitted prescription drug mail order variants and specialty drugs because retail is the common simple variant; mail order copays ($36 generic, $120 preferred brand, $170 non-preferred brand) and specialty drugs (20% coinsurance up to $250 per prescription) require calculation order not supported.
  - Omitted outpatient surgery facility fee non-hospital/ASC variant: 20% coinsurance for services other than surgery because coinsurance-only variant requires no mixed copay/coinsurance ordering assumption but is not a simple flat copay.
  - Omitted emergency room professional services (no charge) as a separate benefit because it is part of the ER row but can be captured as a condition in a future enhancement.
  - Omitted mental health outpatient services other than office visit (no charge) and inpatient services due to per-day cap.
  - Omitted preventive care cost-sharing for non-preventive services as a condition because the source states 'You may have to pay for services that aren't preventive' but does not specify the cost.
  - Partial source review: sections were selected locally; omitted services require review and have no executable rules.
  - Network out omitted: deductible or OOP limit is not established. Claims in that network require separate review, including emergency exceptions.
  - Dropped rule benefits.B10 (Facility fee (e.g., ambulatory surgery center) - Hospital/ASC): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B15 (Outpatient services (mental health) - Office visit individual therapy session): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B16 (Outpatient services (mental health) - Group therapy session): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B25 (Children's eye exam): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B26 (Children's glasses): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B27 (Children's dental check-up): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B4 (Diagnostic test (x-ray, blood work) - Lab): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.
  - Dropped rule benefits.B5 (Diagnostic test (x-ray, blood work) - X-ray): missing or unmatched source quote/clause/code/category/amount/conditions, or unsupported network; no executable rule retained.

  Source-backed rule values:
  - `networks.in.deductible_cents`: [1195:1358] “What is the overall $0. See the Common Medical Events chart below for your costs for services this plan covers.” | [1359:1370] “deductible?” | [1390:1489] “covered before you There is no deductible. There is no deductible.”
  - `networks.in.oop_max_cents`: [1672:1841] “What is the out-of- The out-of-pocket limit is the most you could pay in a year for covered services. If you have” | [1870:1911] “$9,200 member/$18,400 family per calendar” | [1912:2081] “pocket limit for this other family members in this plan, they have to meet their own out-of-pocket limits until the” | [2110:2115] “year.”
  - `benefits.B1`: [4497:4595] “Primary care visit to treat $40 copay/visit Not covered None” | [4626:4646] “an injury or illness”
  - `benefits.B2`: [3270:3442] “Do you need a referral This plan will pay some or all of the costs to see a specialist for covered services but only if” | [3443:3569] “to see a specialist? Yes. Requires written prior authorization. you have a referral before you see the specialist.” | [4648:4801] “If you visit a health care Specialist visit $70 copay/visit Not covered Requires prior authorization.”
  - `benefits.B3`: [5022:5159] “Preventive aren’t preventive. Ask your provider if the” | [5190:5320] “care/screening/ No charge Not covered services needed are preventive. Then” | [5351:5479] “immunization check what your plan will pay for.”
  - `benefits.B6`: [5757:5880] “Imaging (CT/PET scans, $75 copay/procedure Not covered Requires prior authorization.” | [5911:5916] “MRIs)”
  - `benefits.B7`: [5980:6002] “$18 copay/retail order” | [6033:6114] “Generic drugs (Tier 1) Not covered” | [6178:6198] “$36 copay/mail order” | [6199:6365] “If you need drugs to treat Supply/order: up to 30 day (retail); 35-90”
  - `benefits.B8`: [6396:6530] “Preferred brand drugs $60 copay/retail order day (mail), except where quantity limits” | [6531:6642] “your illness or condition. Not covered” | [6673:6806] “(Tier 2) $120 copay/mail order apply. Prior authorization required for” | [6931:6944] “select drugs.”
  - `benefits.B9`: [6945:7056] “More information about Non-preferred brand $85 copay/retail order Not covered” | [7057:7141] “prescription drug drugs (Tier 3) $170 copay/mail order” | [7142:7166] “coverage is available at” | [7167:7330] “www.myhealthnetca.com Prior authorization required for select”
  - `benefits.B11`: [9056:9155] “Physician/surgeon fees $60 copay/visit Not covered None”
  - `benefits.B12`: [9359:9497] “Emergency room care Facility-$350 copay/visit Copay waived if admitted into the hospital.”
  - `benefits.B13`: [9665:9786] “If you need immediate Medical, mental health & Covered at In-Network cost-” | [9787:9915] “medical attention Emergency medical substance use disorders-$250 share for emergencies only None” | [9945:9998] “transportation copay/transport”
  - `benefits.B14`: [10061:10085] “Medical, mental health &” | [10115:10214] “Urgent care substance use disorders-$40 None” | [10283:10294] “copay/visit”
  - `benefits.B17`: [12496:12597] “Prenatal-No charge Cost sharing does not apply for preventive” | [12627:12707] “Office visits Not covered” | [12769:12839] “Postnatal-$40 copay/visit services.”
  - `benefits.B18`: [12496:12597] “Prenatal-No charge Cost sharing does not apply for preventive” | [12627:12707] “Office visits Not covered” | [12769:12839] “Postnatal-$40 copay/visit services.”
  - `benefits.B19`: [12869:12888] “Childbirth/delivery” | [12889:13015] “If you are pregnant No charge Not covered None” | [13045:13066] “professional services”
  - `benefits.B20`: [13477:13517] “Limited to 100 visits per calendar year.” | [13547:13669] “Home health care $30 copay/visit Not covered Requires prior authorization.”
  - `benefits.B21`: [13699:13779] “Rehabilitation services $40 copay/visit Not covered” | [13902:13931] “Requires prior authorization.”
  - `benefits.B22`: [13961:14041] “Habilitation services $40 copay/visit Not covered” | [14042:14058] “If you need help”
  - `benefits.B23`: [14562:14684] “Durable medical 20% coinsurance Not covered Requires prior authorization.” | [14714:14723] “equipment”
  - `benefits.B24`: [14753:14875] “Hospice services No charge Not covered Requires prior authorization.”
  Source selection: 15794/29790 characters; omitted sections: True.
  Request configuration: `{"response_format": "json_object", "max_tokens_initial": 32768, "max_tokens": 32768, "max_tokens_ceiling": 65536, "thinking": "disabled", "timeout_seconds": 300, "attempt_limit": 1, "transport_attempt_limit": 1, "evidence_spans": "selected original source lines with local offsets; legacy quotes use whitespace-normalized search"}`.

Only validated compilations contain executable rules and clause evidence. A failure has `compilation: null`; no rule or patient total is inferred.

Input excerpts (physical PDF pages; these are not compiled rules):

- p. 7: “     The plan’s overall deductible               $0           The plan’s overall deductible               $0        The plan’s overall deductible            ”
- p. 7: “Deductibles                                   $0          Deductibles                                   $0       Deductibles                                  $0”

Official links and rights notes: [metadata manifest](../data/real_manifest.csv). No redistribution license; PDF/text not in this repo.
