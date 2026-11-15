# Real SBC benchmark: before and after

**Scope: Summary of Benefits and Coverage documents only**

Date: 2026-11-15. Exact requested model: `deepseek-v4-pro`. Seven insurer SBCs; CMS sample/template are excluded. No non-SBC document is part of this benchmark.

## Protocol and changes

The production path is PDF bytes → `extract_upload(policy)` → `LLMCompiler(deepseek).compile` → source-evidence recovery and validation. Kaiser and Highmark remain dev; Aetna, Ambetter, Cigna, Horizon and Oscar remain held-out. Previously tested holdouts are not newly unseen.

Before preserves all 21 SBC runs from the original measurement (three independent runs per SBC, one compile/transport attempt). After follows the revised instruction: one initial pipeline call per SBC, plus one further call only if the first fails. A validated partial compilation counts as success and is not retried merely for missing fields. There is no after-fix three-run stability measurement.

General changes are confined to `fineprint/providers.py`:

- DeepSeek transport now permits three attempts total (two retries), using the existing exponential backoff of 1 and 2 seconds for transient HTTP/transport/malformed-envelope errors. Exhausted transport retries do not multiply through compile retries.
- Default DeepSeek I/O timeout increased from 300 to 450 seconds; the existing environment override remains available. This is not a hard total wall-time deadline.
- Requests explicitly set temperature to zero with thinking disabled. No seed is sent: the endpoint does not document one. Lower temperature does not guarantee identical responses. [DeepSeek API reference](https://api-docs.deepseek.com/api/create-chat-completion/).
- A no-supported-rules validation result receives at most one retry, using the existing general validation-feedback mechanism. There is no insurer-specific prompt or parser change.
- A privacy-safe transport attempt audit records only status and elapsed seconds.

After uses 7 concurrent document workers and one normal compile-validation attempt per pipeline call, plus the new no-supported-rules retry. Internal transport/compile retries can occur inside the first or second pipeline call; first-try success below means first **pipeline call**, not first HTTP request. All internal attempts are recorded. No gold labels enter the request.

**Comparison caveat:** the shared repository also changed between phases. The after run includes concurrent general compiler/validation fixes by another agent, in addition to this task’s client changes. This is an operational before/after comparison, not an isolated causal experiment. Full code hashes and changed-file lists are in JSON. Provider load and retry effort also differ.

## Headline metrics

| Phase / split | Outcome denominator | Extraction | Valid JSON | Validated compile | First pipeline call | Recovered on second call | Rules retained / proposed | Rule retention | Quote accuracy | Claim-ready | Key numbers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Before / dev | 6 runs | 6/6 | 5/6 | 5/6 | N/A | N/A | 54/141 | 38.3% | 100.0% | 1/6 | 70.0% |
| Before / held_out | 15 runs | 15/15 | 13/15 | 12/15 | N/A | N/A | 251/424 | 59.2% | 100.0% | 0/15 | 70.0% |
| Before / all | 21 runs | 21/21 | 18/21 | 17/21 | N/A | N/A | 305/565 | 54.0% | 100.0% | 1/21 | 70.0% |
| After / dev | 2 documents | 2/2 | 2/2 | 2/2 | 2/2 | 0/0 | 48/68 | 70.6% | 100.0% | 0/2 | 100.0% |
| After / held_out | 5 documents | 5/5 | 5/5 | 5/5 | 5/5 | 0/0 | 126/189 | 66.7% | 100.0% | 0/5 | 90.0% |
| After / all | 7 documents | 7/7 | 7/7 | 7/7 | 7/7 | 0/0 | 174/257 | 67.7% | 100.0% | 0/7 | 93.3% |

After outcome rates and key-number accuracy use one final outcome per document. Proposed-rule and citation accounting include failed initial calls and all internal response attempts; all-call aggregates are separately saved in JSON. Recovery 0/0 means no second call was needed.

## Per-document results

| Document | Split | Before validated / 3 | Before rule counts | Before variance | Before deductible / OOP stable | After first call | Second call needed / recovered | After retained / proposed rules | After key numbers | Total after seconds |
|---|---|---:|---|---:|---|---|---|---:|---:|---:|
| aetna_2026_fehb_direct_sbc | held_out | 2/3 | [22, 0, 2] | 98.67 | False / False | True | False / False | 25/33 | 100.0% | 50.4 |
| ambetter_2026_ca_gold80_hmo_sbc | held_out | 3/3 | [27, 28, 12] | 53.56 | True / True | True | False / False | 24/38 | 80.0% | 48.9 |
| cigna_2026_in_connect_gold_sbc | held_out | 3/3 | [16, 23, 26] | 17.56 | True / True | True | False / False | 24/32 | 100.0% | 40.9 |
| highmark_2026_pa_together_blue_gold_sbc | dev | 2/3 | [2, 0, 10] | 18.67 | False / False | True | False / False | 22/31 | 100.0% | 42.2 |
| horizon_2026_hmh_omnia_sbc | held_out | 2/3 | [21, 0, 23] | 108.22 | False / False | True | False / False | 23/34 | N/A | 45.5 |
| kaiser_2026_ca_gold80_sbc | dev | 3/3 | [17, 16, 9] | 12.67 | True / True | True | False / False | 26/37 | 100.0% | 47.8 |
| oscar_2026_tx_bronze_elite_sbc | held_out | 2/3 | [21, 30, 0] | 158.00 | False / False | True | False / False | 30/52 | 80.0% | 66.0 |

**After stability: not measured.** Failure-only retries cannot estimate nondeterministic run-to-run variance. Before population variance includes failures as zero; successful-only variance and exact deductible/OOP values remain in JSON.

## Citation, page and latency checks

| Phase / split | Raw reference accuracy | Retained spans | Retained quote accuracy | Physical page locatable | Key-field page checks / match | Mean elapsed seconds |
|---|---:|---:|---:|---:|---|---:|
| Before / dev | 99.7% | 152 | 100.0% | 79.6% | 14 / 100.0% | 94.0 |
| Before / held_out | 99.7% | 894 | 100.0% | 78.4% | 31 / 100.0% | 85.5 |
| Before / all | 99.7% | 1046 | 100.0% | 78.6% | 45 / 100.0% | 87.9 |
| After / dev | 100.0% | 113 | 100.0% | 51.3% | 5 / 100.0% | 45.0 |
| After / held_out | 100.0% | 456 | 100.0% | 88.2% | 14 / 100.0% | 50.3 |
| After / all | 100.0% | 569 | 100.0% | 80.8% | 19 / 100.0% | 48.8 |

Latency is measured from worker start, excluding queue time. After document latency includes both calls when a retry was necessary; each extraction/compile latency is also saved. The reported provider timeout is per I/O, not a total deadline.

## Pre-model reference labels

Codex hand-read the reference values from original SBC text at **2026-11-15T11:28:49.779004+00:00**, before viewing any benchmark model output or prior compilation report. The unchanged reference-file SHA256 is `45398746db47b9a8fed143e4ce87bf316d3f0b8818bdbb56d51246a62008d79a`. These same labels were frozen for both phases; they were not fed to the compiler.

The existing coverage-example CSV labels whole episodes, not the requested plan limits/copays. It is not used as plan-field gold. Six SBCs have five reference fields each: 90 before opportunities and 30 after final-outcome opportunities. Horizon has multiple in-network tiers that cannot be identified faithfully by the current in/out schema; its tier values are recorded, but excluded from the single-network numeric score.

| Document | Deductible cents | OOP cents | PCP copay cents / coin bps | Specialist copay cents / coin bps | ER copay cents / coin bps |
|---|---:|---:|---|---|---|
| aetna_2026_fehb_direct_sbc | 160000 | 600000 | 0 / 2000 | 0 / 2000 | 0 / 2000 |
| ambetter_2026_ca_gold80_hmo_sbc | 0 | 920000 | 4000 / 0 | 7000 / 0 | 35000 / 0 |
| cigna_2026_in_connect_gold_sbc | 200000 | 820000 | 3000 / 0 | 6000 / 0 | 0 / 2500 |
| highmark_2026_pa_together_blue_gold_sbc | 0 | 750000 | 2000 / 0 | 2000 / 0 | 40000 / 0 |
| kaiser_2026_ca_gold80_sbc | 0 | 920000 | 4000 / 0 | 7000 / 0 | 35000 / 0 |
| oscar_2026_tx_bronze_elite_sbc | 0 | 1015000 | 4000 / 0 | 13000 / 0 | 250000 / 0 |

## Definitions and caveats

- Extraction success means nonempty production-parser text, not verified table or character accuracy. No cached text replaces PDF extraction.
- Valid JSON is observed before validation. Compile success is a returned validated, potentially partial compilation. Proposed rules are raw rule-evidence entries; retained rules are validated financial/network/benefit paths. Retention is not all-service recall. All emitted proposals, including failed internal attempts, remain in its denominator.
- Quote accuracy means whitespace-normalized source containment. Line IDs are copied locally into exact quotes, so high accuracy mainly measures reference integrity, not semantic correctness. Duplicate citations are counted. Invalid raw references remain in raw accuracy.
- No page-number prediction exists in the schema: independently predicted page accuracy is N/A. Physical-page location is available only when extraction retains all pages. The limited labeled-field check asks whether its evidence includes its reference PDF page; broad citations can pass without proving correct interpretation.
- Claim-ready uses the existing benchmark definition: benefits present, no unresolved items, and explicit balance-billing terms for every retained network. It does not prove complete coverage, correct conditions/waivers or successful real-claim processing.
- Numeric scoring covers individual in-network medical deductible/OOP, ordinary in-person primary/specialist care and non-admitted emergency facility cost sharing. Service scores compare copay and coinsurance jointly. Missing/ambiguous fields and failed final outcomes are nonmatches; observed-only accuracy excludes missing fields. Conditions and fee-component completeness are not scored.
- Seven documents are a small corpus. No confidence intervals, all-rule gold recall or patient-total correctness is claimed. Concurrent traffic and transport failures affect latency. Before failures contribute zero to rule variance; this is not pure model-output variance.

## Failures and omissions

- Before, aetna_2026_fehb_direct_sbc, call 1: failure=none; dropped rules=6; no scored numeric misses.
- Before, aetna_2026_fehb_direct_sbc, call 2: failure=no_supported_rules; dropped rules=0; deductible: missing, oop_max: missing, primary_care: missing, specialist: missing, er: missing.
- Before, aetna_2026_fehb_direct_sbc, call 3: failure=none; dropped rules=35; primary_care: missing, specialist: missing, er: missing.
- Before, ambetter_2026_ca_gold80_hmo_sbc, call 1: failure=none; dropped rules=7; no scored numeric misses.
- Before, ambetter_2026_ca_gold80_hmo_sbc, call 2: failure=none; dropped rules=5; er: missing.
- Before, ambetter_2026_ca_gold80_hmo_sbc, call 3: failure=none; dropped rules=22; primary_care: missing, specialist: missing, er: missing.
- Before, cigna_2026_in_connect_gold_sbc, call 1: failure=none; dropped rules=17; primary_care: missing.
- Before, cigna_2026_in_connect_gold_sbc, call 2: failure=none; dropped rules=7; no scored numeric misses.
- Before, cigna_2026_in_connect_gold_sbc, call 3: failure=none; dropped rules=12; no scored numeric misses.
- Before, highmark_2026_pa_together_blue_gold_sbc, call 1: failure=none; dropped rules=30; primary_care: missing, specialist: missing, er: missing.
- Before, highmark_2026_pa_together_blue_gold_sbc, call 2: failure=transport_timeout; dropped rules=0; deductible: missing, oop_max: missing, primary_care: missing, specialist: missing, er: missing.
- Before, highmark_2026_pa_together_blue_gold_sbc, call 3: failure=none; dropped rules=1; no scored numeric misses.
- Before, horizon_2026_hmh_omnia_sbc, call 1: failure=none; dropped rules=9; no scored numeric misses.
- Before, horizon_2026_hmh_omnia_sbc, call 2: failure=transport_timeout; dropped rules=0; no scored numeric misses.
- Before, horizon_2026_hmh_omnia_sbc, call 3: failure=none; dropped rules=10; no scored numeric misses.
- Before, kaiser_2026_ca_gold80_sbc, call 1: failure=none; dropped rules=17; primary_care: missing.
- Before, kaiser_2026_ca_gold80_sbc, call 2: failure=none; dropped rules=19; no scored numeric misses.
- Before, kaiser_2026_ca_gold80_sbc, call 3: failure=none; dropped rules=4; no scored numeric misses.
- Before, oscar_2026_tx_bronze_elite_sbc, call 1: failure=none; dropped rules=15; no scored numeric misses.
- Before, oscar_2026_tx_bronze_elite_sbc, call 2: failure=none; dropped rules=18; no scored numeric misses.
- Before, oscar_2026_tx_bronze_elite_sbc, call 3: failure=transport_timeout; dropped rules=0; deductible: missing, oop_max: missing, primary_care: missing, specialist: missing, er: missing.
- After, aetna_2026_fehb_direct_sbc, call 1: failure=none; dropped rules=8; no scored numeric misses.
- After, ambetter_2026_ca_gold80_hmo_sbc, call 1: failure=none; dropped rules=14; er: missing.
- After, cigna_2026_in_connect_gold_sbc, call 1: failure=none; dropped rules=7; no scored numeric misses.
- After, highmark_2026_pa_together_blue_gold_sbc, call 1: failure=none; dropped rules=9; no scored numeric misses.
- After, horizon_2026_hmh_omnia_sbc, call 1: failure=none; dropped rules=10; no scored numeric misses.
- After, kaiser_2026_ca_gold80_sbc, call 1: failure=none; dropped rules=11; no scored numeric misses.
- After, oscar_2026_tx_bronze_elite_sbc, call 1: failure=none; dropped rules=18; er: missing.

Failures use fixed privacy-safe codes. No raw model response, policy text, evidence quote or free-form exception message is published.

## Provenance and verification

Before revision: `79d98f80dda182e76dd8a0dfaf9a21133ac2d7e6`. After starting revision: `f40e893c89bcd4396c6a55f64f7819412b09692f` plus the recorded DeepSeek client patch. Modules are imported once per phase; on-disk concurrent edits are not reloaded. PDF hashes, extraction hashes, source-label hashes, script hashes, dependency versions, code hashes and attempt audits are in JSON. The before baseline was preserved from commit `f40e893`; only its SBC rows are retained here.

All 191 unittest tests passed, including provider retry bounds, request sampling, privacy, and conditional-retry denominator checks. The Pages build passed using a private output directory. The measured after phase completed in 66.1 seconds; all seven documents used exactly one HTTP attempt and one pipeline call, so live retry recovery was not exercised. Retry behavior is covered by offline transport tests. No private PDF text or model response is committed.

Private PDFs/text remain gitignored. `reports/evaluation-real-sbc.json` is unchanged by this task.

Reproduction (requires ignored PDFs and the frozen labels; preserve the baseline before rerunning):

```sh
timeout 1500 .venv/bin/python scripts/bench_real_sbc.py --labels data/real_private/benchmark-real-sbc/labels.json --before data/real_private/benchmark-real-sbc/before-sbc.json --workers 7
```
