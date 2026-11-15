# Evidence: Fineprint on 7 real insurer SBCs (after fixes)

Date: 2026-11-15 · Model: `deepseek-v4-pro` · Code: commit `3b3231f` (the version deployed on the live AWS app) · Full report: [benchmark-real-sbc.md](benchmark-real-sbc.md) / [JSON](benchmark-real-sbc.json)

## Results

| Metric | All 7 | Dev (2) | Held-out (5) |
|---|---:|---:|---:|
| Text extracted from PDF | 7/7 | 2/2 | 5/5 |
| Valid JSON from the model | 7/7 | 2/2 | 5/5 |
| Validated policy compile | **7/7** | 2/2 | 5/5 |
| Succeeded on the first pipeline call | 7/7 | 2/2 | 5/5 |
| Key-number accuracy | **93.3%** (28/30) | 100% | 90% |
| Quote accuracy (every retained citation found verbatim in the PDF) | **100%** | 100% | 100% |
| Rules retained after validation | 67.7% (174/257) | 70.6% | 66.7% |
| Mean time per document | 48.8 s | 45.0 s | 50.3 s |

The whole seven-document run finished in **66.1 seconds** with 7 parallel workers, and every document needed exactly one model call.

## What was measured

- **Documents:** seven real 2026 Summary of Benefits and Coverage (SBC) PDFs from Aetna, Ambetter, Cigna, Highmark, Horizon, Kaiser and Oscar. Kaiser and Highmark are the dev set; the other five are held out. Only SBCs are in scope.
- **Pipeline:** the same production path the live app uses: PDF bytes → `extract_upload` → DeepSeek compiler → source-evidence check and validation. No answers or labels are sent to the model.
- **Protocol:** each document is read once; a second call is allowed only if the first fails (none did).
- **Key numbers:** five hand-labelled fields per document, checked against the PDF before any model run. The fields are the in-network individual deductible, the out-of-pocket maximum, and the primary-care, specialist and emergency-room cost share. Six documents carry labels (30 fields). Horizon has no labels, so it counts for compile and quotes but not for key numbers.

## Per-document

| Insurer | Split | Compiled | Rules retained | Key numbers | Seconds |
|---|---|---|---:|---:|---:|
| Aetna | held-out | yes, first call | 25/33 | 100% | 50.4 |
| Ambetter | held-out | yes, first call | 24/38 | 80% (ER missing) | 48.9 |
| Cigna | held-out | yes, first call | 24/32 | 100% | 40.9 |
| Highmark | dev | yes, first call | 22/31 | 100% | 42.2 |
| Horizon | held-out | yes, first call | 23/34 | not labelled | 45.5 |
| Kaiser | dev | yes, first call | 26/37 | 100% | 47.8 |
| Oscar | held-out | yes, first call | 30/52 | 80% (ER missing) | 66.0 |

The only two key-number misses are emergency-room fields that were left blank. No field was filled with a wrong number.

## Fixes behind these numbers (commit `3b3231f`)

These are general fixes with no insurer-specific prompts or parsers.

- DeepSeek transport retries transient errors (3 attempts with backoff), and the I/O timeout went from 300 s to 450 s.
- Requests use temperature 0 with thinking disabled.
- A "no supported rules" result gets one retry using the existing validation feedback.
- A privacy-safe audit records only the status and elapsed time of each call.

All 191 unit tests pass.

## How to describe it honestly

> On seven real 2026 insurer SBCs (five held out), Fineprint compiled 7/7 policies on the first try in about a minute, with 93.3% key-number accuracy and 100% of citations quoted verbatim from the source PDF.

Limits to keep in mind:

- This is a single run. Stability across repeated runs after the fixes was not measured.
- Seven documents is a small sample.
- "Claim-ready" under the strict benchmark definition (explicit balance-billing terms for every network, no unresolved items) is 0/7. Compiles are validated but partial.
- Quote accuracy shows that the citations are real text from the PDF. It does not by itself prove that every rule was interpreted correctly.
- The insurer PDFs are not in the repo (no redistribution licence). They are gitignored and available from each insurer's official site.

## Links

- Live app: https://fi-9a2f7a7357674be89e7cf09a86c2c5a7.ecs.us-east-1.on.aws
- Full report: [benchmark-real-sbc.md](benchmark-real-sbc.md), [benchmark-real-sbc.json](benchmark-real-sbc.json)
- Fix commit `3b3231f`, report commit `49823fe`
- Companion evidence for the blind bill test: [blind-15-to-70-evidence.md](blind-15-to-70-evidence.md)
