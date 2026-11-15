# Real highmark policy compilation

Source: `data/real_private/docs/highmark_2026_pa_together_blue_gold_sbc.txt` (private).
Text SHA256: `ef62c3deba0feaf22959c655a99b54a058a2330b18f93b17a8f017cbfd99af6a`.

Existing compiler and shared provider prompt unchanged. Input is complete raw text; no manual transcription or gold rules.

- **fallback** / no model: **failed**. Fallback requires a '# Insurer — Plan' title and Policy/Member/Period/USD header; other formats need a provider or transcription
- **deepseek** / deepseek-v4-pro: **failed**. deepseek compilation failed after 3 attempts: output.policy.member_id: expected string. No fallback was substituted.

Only validated compilations contain executable rules and clause evidence. A failure has `compilation: null`; no rule or patient total is inferred.

Input excerpts (physical PDF pages; these are not compiled rules):

- p. 1: “What is the overall               $0 individual/$0 family network.                   See the Common Medical Events chart below for your costs for services this”
- p. 1: “What is the out-of-pocket limit $7,500 individual/$15,000 family network.            The out-of-pocket limit is the most you could pay in a year for covered”

Official links and rights notes: [metadata manifest](../data/real_manifest.csv). No redistribution license; PDF/text not in this repo.
