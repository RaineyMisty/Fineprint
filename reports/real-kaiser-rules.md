# Real kaiser policy compilation

Source: `data/real_private/docs/kaiser_2026_ca_gold80_sbc.txt` (private).
Text SHA256: `53d9f1b2e5417de48c663972c0794ae6308bb8460f2011a995487d83485ca949`.

Existing compiler and shared provider prompt unchanged. Input is complete raw text; no manual transcription or gold rules.

- **fallback** / no model: **failed**. Fallback requires a '# Insurer — Plan' title and Policy/Member/Period/USD header; other formats need a provider or transcription
- **deepseek** / deepseek-v4-pro: **failed**. deepseek compilation failed after 3 attempts: DeepSeek did not complete a JSON response. No fallback was substituted.

Only validated compilations contain executable rules and clause evidence. A failure has `compilation: null`; no rule or patient total is inferred.

Input excerpts (physical PDF pages; these are not compiled rules):

- p. 1: “What is the out-of-pocket $9,200 Individual / $18,400 Family                                                                                          The out-of”
- p. 3: “If you need mental                          $40 / individual visit. No charge                                 Mental / Behavioral health: $20 / group visit”

Official links and rights notes: [metadata manifest](../data/real_manifest.csv). No redistribution license; PDF/text not in this repo.
