# Real kaiser-eoc policy compilation

Source: `data/real_private/docs/kaiser_2026_ca_gold80_eoc.txt` (private).
Text SHA256: `052a607ec9f0ce6263c9a81c834f09ea4132b357ff19be0795cebbb37372c82d`.

Existing compiler and shared provider prompt unchanged. Input is complete raw text; no manual transcription or gold rules.

- **fallback** / no model: **failed**. Fallback requires a '# Insurer — Plan' title and Policy/Member/Period/USD header; other formats need a provider or transcription
- **deepseek** / deepseek-v4-pro: **failed**. deepseek compilation failed after 3 attempts: output.policy.member_id: text must not be empty. No fallback was substituted.

Only validated compilations contain executable rules and clause evidence. A failure has `compilation: null`; no rule or patient total is inferred.

Input excerpts (physical PDF pages; these are not compiled rules):

- p. 6: “Plan Out-of-Pocket Maximum (“OOPM”)                   $9,200                    $9,200                      $18,400”
- p. 10: “Individual mental health evaluation and treatment          $40 per visit                                 ✔”

Official links and rights notes: [metadata manifest](../data/real_manifest.csv). No redistribution license; PDF/text not in this repo.
