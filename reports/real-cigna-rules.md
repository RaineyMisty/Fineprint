# Real cigna policy compilation

Source: `data/real_private/docs/cigna_2026_in_connect_gold_sbc.txt` (private).
Text SHA256: `cdf6bdd874bd75974e2d877d3aa448701dc43dfef299c530e4a6373baa310169`.

Existing compiler and shared provider prompt unchanged. Input is complete raw text; no manual transcription or gold rules.

- **fallback** / no model: **failed**. Fallback requires a '# Insurer — Plan' title and Policy/Member/Period/USD header; other formats need a provider or transcription
- **deepseek** / deepseek-v4-pro: **failed**. deepseek compilation failed after 3 attempts: DeepSeek did not complete a JSON response. No fallback was substituted.

Only validated compilations contain executable rules and clause evidence. A failure has `compilation: null`; no rule or patient total is inferred.

Input excerpts (physical PDF pages; these are not compiled rules):

- p. 1: “pocket limit for this       $8,200 person/ $16,400 family       family members in this plan, they have to meet their own out-of-pocket limits until the overall”
- p. 6: “◼ The plan’s overall deductible           $2,000        ◼ The plan’s overall deductible             $2,000      ◼ The plan’s overall deductible          $2,000”

Official links and rights notes: [metadata manifest](../data/real_manifest.csv). No redistribution license; PDF/text not in this repo.
