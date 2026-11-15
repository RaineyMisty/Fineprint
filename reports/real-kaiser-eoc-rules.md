# Real kaiser-eoc policy compilation

Source: `data/real_private/docs/kaiser_2026_ca_gold80_eoc.txt` (private).
Text SHA256: `052a607ec9f0ce6263c9a81c834f09ea4132b357ff19be0795cebbb37372c82d`.

LLM input uses locally ranked cost-sharing source sections; evidence is located and validated against the complete original source. No manual gold rules or invented member IDs.

- **fallback** / no model: **failed**. Fallback requires a '# Insurer — Plan' title and Policy/Member/Period/USD header; other formats need a provider or transcription
- **deepseek** / deepseek-v4-pro: **validated**. Validated after 3 attempt(s).
  Validated rules: 2; claim-ready: **False**.
  Unresolved: No explicit balance billing language found for in-network or out-of-network providers.
  Unresolved: Out-of-network coverage details are limited; policies for non-participating providers are not fully specified in the provided excerpts.
  Unresolved: No CPT/HCPCS codes were provided in the document excerpts; benefits are described by service category only.
  Unresolved: The document does not establish an out-of-network OOP maximum distinct from the in-network OOP maximum; the same amount is applied to both networks due to lack of explicit differentiation.
  Unresolved: Partial source review: sections were selected locally; omitted clauses require review before claim calculation.
  Unresolved: Dropped rule benefits.B1: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B10: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B11: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B12: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B13: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B14: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B15: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B16: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B17: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B18: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B19: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B2: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B20: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B21: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B22: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B23: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B24: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B25: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B26: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B27: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B28: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B29: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B3: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B30: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B31: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B32: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B33: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B34: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B35: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B4: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B5: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B6: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B7: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B8: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule benefits.B9: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule networks.in.balance_billing: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule networks.out.balance_billing: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule networks.out.deductible_cents: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Unresolved: Dropped rule networks.out.oop_max_cents: missing or unmatched source quote/clause/code, or unsupported network; no executable rule retained.
  Source selection: 59953/709473 characters; omitted sections: True.
  Request configuration: `{"response_format": "json_object", "max_tokens_initial": 32768, "max_tokens": 32768, "max_tokens_ceiling": 65536, "thinking": "disabled", "timeout_seconds": 300, "attempt_limit": 3, "transport_attempt_limit": 2, "evidence_spans": "local whitespace-normalized quote search"}`.

Only validated compilations contain executable rules and clause evidence. A failure has `compilation: null`; no rule or patient total is inferred.

Input excerpts (physical PDF pages; these are not compiled rules):

- p. 6: “Plan Out-of-Pocket Maximum (“OOPM”)                   $9,200                    $9,200                      $18,400”
- p. 10: “Individual mental health evaluation and treatment          $40 per visit                                 ✔”

Official links and rights notes: [metadata manifest](../data/real_manifest.csv). No redistribution license; PDF/text not in this repo.
