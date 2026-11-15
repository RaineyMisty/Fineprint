# Real cigna policy compilation

Split: **held_out**. Held-out documents use one provider request with no validation or transport retries.

Source: `data/real_private/docs/cigna_2026_in_connect_gold_sbc.txt` (private).
Text SHA256: `cdf6bdd874bd75974e2d877d3aa448701dc43dfef299c530e4a6373baa310169`.

LLM input uses locally ranked cost-sharing source sections; evidence is located and validated against the complete original source. No manual gold rules or invented member IDs.

- **fallback** / no model: **failed**. Fallback requires a '# Insurer — Plan' title and Policy/Member/Period/USD header; other formats need a provider or transcription
- **deepseek** / deepseek-v4-pro: **failed**. deepseek compilation failed after 1 attempts: Excluded service has covered cost sharing. No fallback was substituted.
  Source selection: 25051/37777 characters; omitted sections: True.
  Request configuration: `{"response_format": "json_object", "max_tokens_initial": 32768, "max_tokens": 32768, "max_tokens_ceiling": 65536, "thinking": "disabled", "timeout_seconds": 300, "attempt_limit": 1, "transport_attempt_limit": 1, "evidence_spans": "selected original source lines with local offsets; legacy quotes use whitespace-normalized search"}`.

Only validated compilations contain executable rules and clause evidence. A failure has `compilation: null`; no rule or patient total is inferred.

Input excerpts (physical PDF pages; these are not compiled rules):

- p. 1: “pocket limit for this       $8,200 person/ $16,400 family       family members in this plan, they have to meet their own out-of-pocket limits until the overall”
- p. 6: “◼ The plan’s overall deductible           $2,000        ◼ The plan’s overall deductible             $2,000      ◼ The plan’s overall deductible          $2,000”

Official links and rights notes: [metadata manifest](../data/real_manifest.csv). No redistribution license; PDF/text not in this repo.

Held-out result: **32 proposed rule-evidence entries; 0 validated rules, 0 validated quotes. All service rows remain uncompiled.** One DeepSeek request, no retries or fallback substitution. The failure is preserved as measured; no compiler changes were made in response.
