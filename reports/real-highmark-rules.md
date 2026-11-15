# Real highmark policy compilation

Split: **dev**. Held-out documents use one provider request with no validation or transport retries.

Source: `data/real_private/docs/highmark_2026_pa_together_blue_gold_sbc.txt` (private).
Text SHA256: `ef62c3deba0feaf22959c655a99b54a058a2330b18f93b17a8f017cbfd99af6a`.

LLM input uses locally ranked cost-sharing source sections; evidence is located and validated against the complete original source. No manual gold rules or invented member IDs.

- **fallback** / no model: **failed**. Fallback requires a '# Insurer — Plan' title and Policy/Member/Period/USD header; other formats need a provider or transcription
- **deepseek** / deepseek-v4-pro: **validated**. Validated after 3 attempt(s).
  Validated rules: 10; claim-ready: **False**.
  Service rules: 8; validated quote spans: 30; distinct spans: 25.
  Conditionally executable subset: **True**. Missing billing terms need independent contract evidence; categories/conditions need reviewer assignment.

  Compiled services:
  - Primary care visit to treat an injury or illness (in); category `Primary care visit to treat an injury or illness`; conditions: none.
  - Specialist visit (in); category `Specialist visit`; conditions: No referral required.
  - Preventive care/screening/immunization (in); category `Preventive care/screening/Immunization`; conditions: none.
  - Diagnostic test (x-ray, blood work) (in); category `Diagnostic test (x-ray, blood work)`; conditions: Not for treatment of mental illness or substance abuse.
  - Imaging (CT/PET scans, MRIs) (in); category `Imaging (CT/PET scans, MRIs)`; conditions: Not for treatment of mental illness or substance abuse.
  - Tier 1 prescription drug (retail) (in); category `Tier 1`; conditions: Retail pharmacy, Up to 31/60/90-day supply, Medication is not a contraceptive.
  - Emergency room care (in); category `Emergency room care`; conditions: Not admitted as inpatient.
  - Urgent care (in); category `Urgent care`; conditions: Not for treatment of mental illness or substance abuse.

  Not compiled / limitations (provider-reported, not an exhaustive recall score):
  - Out-of-network benefits: all out-of-network services are listed as 'Not covered' in the SBC, except emergency room and urgent care which have copayments. However, no out-of-network deductible or OOP maximum is provided; therefore, an out-of-network network object is omitted.
  - Balance billing: The document mentions balance-billed charges are not included in the OOP limit, but does not explicitly state whether the plan protects against balance billing for in-network or out-of-network providers. Therefore, balance_billing is set to null for both networks.
  - Family-level deductible and OOP maximum: Only individual amounts are compiled; family amounts are not included in this extraction because the engine supports individual pools.
  - Omitted benefits with per-day or multi-day limits: Tier 2 and Tier 3 prescription drug copays vary by supply (e.g., $30/$60/$90) and are not compilable into a single numeric copay without an engine-supported supply condition. They are omitted.
  - Tier 4 prescription drugs use coinsurance with minimum and maximum dollar amounts, which the engine cannot represent.
  - Outpatient surgery, hospital stay, mental health services, pregnancy, home health care, rehabilitation, habilitation, skilled nursing, durable medical equipment, hospice, and children's dental/eye care are omitted due to copayments or coinsurance that are not simple fixed amounts or due to limitations/conditions that require additional claim context or exceed engine capabilities.
  - Some services have precertification requirements; these are not modeled as conditions because they are administrative requirements, not benefit-eligibility facts.
  - The emergency medical transportation benefit is a 30% coinsurance with no copay, but because it applies to both in- and out-of-network with no deductible and no OOP accumulation, it is omitted due to the lack of an out-of-network pool and potential balance billing issues.
  - Partial source review: sections were selected locally; omitted services require review and have no executable rules.
  - Network out omitted: deductible or OOP limit is not established. Claims in that network require separate review, including emergency exceptions.

  Source-backed rule values:
  - `networks.in.deductible_cents`: [1168:1327] “What is the overall $0 individual/$0 family network. See the Common Medical Events chart below for your costs for services this”
  - `networks.in.oop_max_cents`: [2384:2540] “What is the out-of-pocket limit $7,500 individual/$15,000 family network. The out-of-pocket limit is the most you could pay in a year for covered”
  - `benefits.B1`: [4444:4572] “All copayment and coinsurance costs shown in this chart are after your overall deductible has been met, if a deductible applies.” | [5747:5899] “If you visit a health Primary care visit to treat an injury $20 copay/visit Not covered You may have to pay for services that aren’t” | [5900:6060] “care provider’s office or illness preventive. Ask your provider if the services needed” | [6061:6219] “or clinic Specialist visit $20 copay/visit Not covered are preventive. Then check what your plan will pay”
  - `benefits.B2`: [4277:4419] “Do I need a referral to see a No. You can see the specialist you choose without a referral.” | [4421:4432] “specialist?” | [6061:6219] “or clinic Specialist visit $20 copay/visit Not covered are preventive. Then check what your plan will pay”
  - `benefits.B3`: [6245:6332] “Preventive No charge Not covered for.” | [6358:6385] “care/screening/Immunization”
  - `benefits.B4`: [6671:6825] “If you have a test Diagnostic test (x-ray, blood work) $35 copay/visit Not covered Copayments, if any, do not apply to diagnostic” | [6851:6981] “Imaging (CT/PET scans, MRIs) $450 copay/visit Not covered services prescribed for the treatment of mental” | [7090:7117] “illness or substance abuse.”
  - `benefits.B5`: [6851:6981] “Imaging (CT/PET scans, MRIs) $450 copay/visit Not covered services prescribed for the treatment of mental” | [7090:7117] “illness or substance abuse.”
  - `benefits.B6`: [7261:7411] “If you need drugs to Tier 1 No charge Not covered Up to 31/60/90-day supply retail pharmacy.” | [7412:7493] “treat your illness or per prescription” | [7494:7652] “condition (retail) Up to 90-day supply maintenance prescription drugs” | [7718:7780] “No charge through mail order.” | [7781:7862] “More information about per prescription” | [7863:8009] “prescription drug (mail order) This plan uses an Essential Formulary.”
  - `benefits.B7`: [4444:4572] “All copayment and coinsurance costs shown in this chart are after your overall deductible has been met, if a deductible applies.” | [10967:11115] “If you need immediate Emergency room care $400 copay/visit $400 copay/visit Copay waived if admitted as an inpatient.” | [11116:11220] “medical attention Deductible does not” | [11306:11312] “apply.”
  - `benefits.B8`: [4444:4572] “All copayment and coinsurance costs shown in this chart are after your overall deductible has been met, if a deductible applies.” | [11669:11798] “Urgent care $40 copay/visit $40 copay/visit The copayment, if any, does not apply to urgent” | [11884:11958] “Deductible does not care services prescribed for the treatment of mental” | [12044:12093] “apply. illness or substance abuse.”
  Source selection: 21291/30723 characters; omitted sections: True.
  Request configuration: `{"response_format": "json_object", "max_tokens_initial": 32768, "max_tokens": 32768, "max_tokens_ceiling": 65536, "thinking": "disabled", "timeout_seconds": 300, "attempt_limit": 3, "transport_attempt_limit": 2, "evidence_spans": "selected original source lines with local offsets; legacy quotes use whitespace-normalized search"}`.

Only validated compilations contain executable rules and clause evidence. A failure has `compilation: null`; no rule or patient total is inferred.

Input excerpts (physical PDF pages; these are not compiled rules):

- p. 1: “What is the overall               $0 individual/$0 family network.                   See the Common Medical Events chart below for your costs for services this”
- p. 1: “What is the out-of-pocket limit $7,500 individual/$15,000 family network.            The out-of-pocket limit is the most you could pay in a year for covered”

Official links and rights notes: [metadata manifest](../data/real_manifest.csv). No redistribution license; PDF/text not in this repo.
