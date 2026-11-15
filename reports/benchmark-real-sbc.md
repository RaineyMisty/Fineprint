# Real insurer PDF benchmark

Date: 2026-11-15; model: `deepseek-v4-pro`.

Production path: `extract_upload(policy, PDF bytes)` → `LLMCompiler(deepseek).compile` → existing evidence recovery and validation. No parser/compiler edits or fallback substitution.

Three independent runs per document, each re-extracting the PDF. One compile attempt and one transport attempt per run, consistently applying the existing held-out configuration to dev too; this differs from the default three-attempt interactive compiler. JSON response mode; thinking disabled; initial 32,768 tokens; 300-second provider timeout. Provider sampling defaults are unchanged; no deterministic seed. Four concurrent workers; latency includes contention. The exact request configuration is saved per run.

Inventory: seven real insurer SBCs (not nine). The CMS completed example and blank template are not real insurer policies. Three EOCs and one benefits schedule are evaluated separately through the supported generic policy input. Two multi-plan brochures are excluded: no plan-selection input. The JSON inventories every local PDF and its exclusion reason.

Kaiser and Highmark remain dev. All other insurer SBCs are held-out. This is a requested repeated measurement of a frozen pipeline, not a fresh untouched holdout: Cigna/Ambetter had already been measured in the repo. No held-out result was used to alter prompts, selectors or validators. Other-policy split tags follow insurer identity; Kaiser EOC was previously measured too.

## Headline metrics

| Group | Docs / runs | Extract | Valid JSON | Compile + validate | Rules retained / proposed | Validated-rule rate | Quote accuracy | Claim-ready | Key numbers, end-to-end | Mean seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sbc:dev | 2 / 6 | 6/6 | 5/6 | 5/6 | 54/141 | 38.3% | 100.0% | 1/6 | 70.0% | 94.0 |
| sbc:held_out | 5 / 15 | 15/15 | 13/15 | 12/15 | 251/424 | 59.2% | 100.0% | 0/15 | 70.0% | 85.5 |
| sbc:all | 7 / 21 | 21/21 | 18/21 | 17/21 | 305/565 | 54.0% | 100.0% | 1/21 | 70.0% | 87.9 |
| other_policy:dev | 1 / 3 | 3/3 | 2/3 | 2/3 | 20/52 | 38.5% | 100.0% | 0/3 | N/A | 127.2 |
| other_policy:held_out | 3 / 9 | 9/9 | 7/9 | 2/9 | 32/124 | 25.8% | 100.0% | 0/9 | N/A | 102.4 |
| other_policy:all | 4 / 12 | 12/12 | 9/12 | 4/12 | 52/176 | 29.5% | 100.0% | 0/12 | N/A | 108.6 |

## Per-document results

| Document | Split | Extract / JSON / compile | Retained rules (3 runs) | Rule-count variance | Validated-rule rate | Quote accuracy | Claim-ready | Key numbers | Deductible / OOP stable | Mean seconds |
|---|---|---:|---|---:|---:|---:|---:|---:|---|---:|
| aetna_2026_fehb_direct_sbc | sbc, held_out | 3 / 3 / 2 of 3 | [22, 0, 2] | 98.67 | 38.1% | 100.0% | 0/3 | 46.7% | False / False | 37.3 |
| ambetter_2026_ca_gold80_hmo_eoc | other_policy, held_out | 3 / 3 / 0 of 3 | [0, 0, 0] | 0.00 | 0.0% | N/A | 0/3 | N/A | False / False | 25.7 |
| ambetter_2026_ca_gold80_hmo_sbc | sbc, held_out | 3 / 3 / 3 of 3 | [27, 28, 12] | 53.56 | 65.0% | 100.0% | 0/3 | 73.3% | True / True | 58.3 |
| cigna_2026_in_connect_gold_sbc | sbc, held_out | 3 / 3 / 3 of 3 | [16, 23, 26] | 17.56 | 62.5% | 100.0% | 0/3 | 93.3% | True / True | 45.3 |
| highmark_2026_pa_together_blue_gold_sbc | sbc, dev | 3 / 2 / 2 of 3 | [2, 0, 10] | 18.67 | 21.4% | 100.0% | 1/3 | 46.7% | False / False | 124.7 |
| horizon_2026_hmh_omnia_sbc | sbc, held_out | 3 / 2 / 2 of 3 | [21, 0, 23] | 108.22 | 65.7% | 100.0% | 0/3 | N/A | False / False | 132.2 |
| kaiser_2026_ca_gold80_eoc | other_policy, dev | 3 / 2 / 2 of 3 | [16, 0, 4] | 46.22 | 38.5% | 100.0% | 0/3 | N/A | False / False | 127.2 |
| kaiser_2026_ca_gold80_sbc | sbc, dev | 3 / 3 / 3 of 3 | [17, 16, 9] | 12.67 | 49.4% | 100.0% | 0/3 | 93.3% | True / True | 63.4 |
| oscar_2026_tx_bronze_elite_sbc | sbc, held_out | 3 / 2 / 2 of 3 | [21, 30, 0] | 158.00 | 58.6% | 100.0% | 0/3 | 66.7% | False / False | 154.4 |
| oscar_2026_tx_bronze_elite_schedule | other_policy, held_out | 3 / 2 / 2 of 3 | [2, 30, 0] | 187.56 | 51.6% | 100.0% | 0/3 | N/A | False / False | 147.8 |
| oscar_2026_tx_eoc | other_policy, held_out | 3 / 2 / 0 of 3 | [0, 0, 0] | 0.00 | 0.0% | N/A | 0/3 | N/A | False / False | 133.6 |

## Citation and page checks

| Group | Raw citations | Raw reference accuracy | Retained spans | Retained quote accuracy | Physical page locatable | Labeled-field page checks | Labeled-field page match |
|---|---:|---:|---:|---:|---:|---:|---:|
| sbc:dev | 341 | 99.7% | 152 | 100.0% | 79.6% | 14 | 100.0% |
| sbc:held_out | 1426 | 99.7% | 894 | 100.0% | 78.4% | 31 | 100.0% |
| sbc:all | 1767 | 99.7% | 1046 | 100.0% | 78.6% | 45 | 100.0% |
| other_policy:dev | 355 | 99.4% | 116 | 100.0% | 0.0% | 0 | N/A |
| other_policy:held_out | 665 | 96.5% | 174 | 100.0% | 100.0% | 0 | N/A |
| other_policy:all | 1020 | 97.5% | 290 | 100.0% | 60.0% | 0 | N/A |

## Metric definitions and limitations

- Extraction success means the production parser returned nonempty text; it is not a character-level or table-layout accuracy score. All three runs start from original PDF bytes, never cached extracted text.
- Valid JSON is measured before validation. Compile success means the production compiler returned a validated (possibly partial) compilation without crashing. Proposed rules count raw rule-evidence entries; retained rules count validated financial/network/benefit rule paths. The validated-rule rate uses all proposals, including failed runs. Benefit rules are also counted separately in JSON. Missing proposals on transport/malformed-JSON failures contribute zero; this rate is not rule recall.
- Quote accuracy is whitespace-normalized source containment, micro-averaged over cited spans including repetitions. Raw source-line references are measured separately from retained quotes. The current model cites line IDs, and local code copies the text, so high quote accuracy is mainly a reference-integrity/validator property, not proof that the right clause, column or number was selected.
- The provider schema has no page-number field. Independently predicted page accuracy is N/A. Physical-page locatability is computed from exact offsets only when extraction preserved all pages. A separate limited check asks whether evidence for each labeled key field includes its independently labeled PDF page; broad multi-page citations can pass this check. This does not prove semantic page relevance for every cited line.
- Claim-ready uses the existing measurement definition: at least one benefit, no unresolved items, and explicit balance-billing terms for every retained network. It does not guarantee coverage completeness, correct eligibility, all network tiers, a member identity, or successful real-claim replay. Conditionally executable counts omit the balance-billing requirement.
- Stability uses population variance across the three retained-rule counts, with failed runs counted as zero. A second variance excludes failures in JSON. Deductible/OOP stability requires a present identical in-network value in all three runs; missing values never count as stable. Identical values can still be wrong.
- Provider load from other concurrent work is uncontrolled. Transport timeouts are pipeline failures, not evidence of model-output nondeterminism. All attempts remain in the denominators; no successful replacement run was selected.
- The configured 300-second provider timeout is an I/O timeout, not a hard wall-time deadline. Two failed requests took about 361 seconds; their full measured latency is retained.
- No complete gold rule inventory exists. These results do not estimate all-service recall, condition/waiver accuracy, family deductible behavior, or patient-total accuracy. Only three runs and seven related insurer summaries limit generalization; no confidence intervals are claimed.

## Pre-model numeric references

Labels were hand-read by Codex from the original cached SBC text at **2026-11-15T11:28:49.779004+00:00**, before any benchmark model output or prior compilation report was viewed. Their frozen file SHA256 is `45398746db47b9a8fed143e4ce87bf316d3f0b8818bdbb56d51246a62008d79a`. Labels were never provided to the compiler. Source-text hashes and source page numbers are saved in JSON.

The existing `data/real_coverage_example_labels.csv` contains episode spending, not plan deductible/OOP/copay gold labels; its amounts were not used as substitutes. Six SBCs have five labeled fields each, scored three times (90 opportunities). Horizon's multiple in-network tiers cannot be faithfully identified by the current `in`/`out` schema, so its independently recorded tier values are disclosed but excluded from a single-network numeric accuracy score. EOCs/schedules have no hand labels in this benchmark.

Numeric scope: individual annual in-network medical deductible/OOP, ordinary in-person primary/specialist care, and the non-admitted emergency facility. Service checks compare the pair (copay cents, coinsurance basis points), so coinsurance-only care is not called free. Multiple differing prices are ambiguous rather than selecting a favorable match. Key-number end-to-end accuracy counts missing/ambiguous fields and compile failures as nonmatches; observed accuracy excludes only missing fields. These checks do not establish service eligibility or fee-component completeness.

| Document | Deductible cents | OOP cents | PCP copay cents / coin bps | Specialist copay cents / coin bps | ER copay cents / coin bps |
|---|---:|---:|---|---|---|
| aetna_2026_fehb_direct_sbc | 160000 | 600000 | 0 / 2000 | 0 / 2000 | 0 / 2000 |
| ambetter_2026_ca_gold80_hmo_sbc | 0 | 920000 | 4000 / 0 | 7000 / 0 | 35000 / 0 |
| cigna_2026_in_connect_gold_sbc | 200000 | 820000 | 3000 / 0 | 6000 / 0 | 0 / 2500 |
| highmark_2026_pa_together_blue_gold_sbc | 0 | 750000 | 2000 / 0 | 2000 / 0 | 40000 / 0 |
| kaiser_2026_ca_gold80_sbc | 0 | 920000 | 4000 / 0 | 7000 / 0 | 35000 / 0 |
| oscar_2026_tx_bronze_elite_sbc | 0 | 1015000 | 4000 / 0 | 13000 / 0 | 250000 / 0 |

## Failures and missing fields

- aetna_2026_fehb_direct_sbc run 1: failure=none; dropped rules=6; no scored numeric misses.
- aetna_2026_fehb_direct_sbc run 2: failure=no_supported_rules; dropped rules=0; deductible: missing, oop_max: missing, primary_care: missing, specialist: missing, er: missing.
- aetna_2026_fehb_direct_sbc run 3: failure=none; dropped rules=35; primary_care: missing, specialist: missing, er: missing.
- ambetter_2026_ca_gold80_hmo_eoc run 1: failure=schema_fields; dropped rules=0; no scored numeric misses.
- ambetter_2026_ca_gold80_hmo_eoc run 2: failure=no_supported_rules; dropped rules=0; no scored numeric misses.
- ambetter_2026_ca_gold80_hmo_eoc run 3: failure=no_supported_rules; dropped rules=0; no scored numeric misses.
- ambetter_2026_ca_gold80_hmo_sbc run 1: failure=none; dropped rules=7; no scored numeric misses.
- ambetter_2026_ca_gold80_hmo_sbc run 2: failure=none; dropped rules=5; er: missing.
- ambetter_2026_ca_gold80_hmo_sbc run 3: failure=none; dropped rules=22; primary_care: missing, specialist: missing, er: missing.
- cigna_2026_in_connect_gold_sbc run 1: failure=none; dropped rules=17; primary_care: missing.
- cigna_2026_in_connect_gold_sbc run 2: failure=none; dropped rules=7; no scored numeric misses.
- cigna_2026_in_connect_gold_sbc run 3: failure=none; dropped rules=12; no scored numeric misses.
- highmark_2026_pa_together_blue_gold_sbc run 1: failure=none; dropped rules=30; primary_care: missing, specialist: missing, er: missing.
- highmark_2026_pa_together_blue_gold_sbc run 2: failure=transport_timeout; dropped rules=0; deductible: missing, oop_max: missing, primary_care: missing, specialist: missing, er: missing.
- highmark_2026_pa_together_blue_gold_sbc run 3: failure=none; dropped rules=1; no scored numeric misses.
- horizon_2026_hmh_omnia_sbc run 1: failure=none; dropped rules=9; no scored numeric misses.
- horizon_2026_hmh_omnia_sbc run 2: failure=transport_timeout; dropped rules=0; no scored numeric misses.
- horizon_2026_hmh_omnia_sbc run 3: failure=none; dropped rules=10; no scored numeric misses.
- kaiser_2026_ca_gold80_eoc run 1: failure=none; dropped rules=21; no scored numeric misses.
- kaiser_2026_ca_gold80_eoc run 2: failure=transport_timeout; dropped rules=0; no scored numeric misses.
- kaiser_2026_ca_gold80_eoc run 3: failure=none; dropped rules=11; no scored numeric misses.
- kaiser_2026_ca_gold80_sbc run 1: failure=none; dropped rules=17; primary_care: missing.
- kaiser_2026_ca_gold80_sbc run 2: failure=none; dropped rules=19; no scored numeric misses.
- kaiser_2026_ca_gold80_sbc run 3: failure=none; dropped rules=4; no scored numeric misses.
- oscar_2026_tx_bronze_elite_sbc run 1: failure=none; dropped rules=15; no scored numeric misses.
- oscar_2026_tx_bronze_elite_sbc run 2: failure=none; dropped rules=18; no scored numeric misses.
- oscar_2026_tx_bronze_elite_sbc run 3: failure=transport_timeout; dropped rules=0; deductible: missing, oop_max: missing, primary_care: missing, specialist: missing, er: missing.
- oscar_2026_tx_bronze_elite_schedule run 1: failure=none; dropped rules=9; no scored numeric misses.
- oscar_2026_tx_bronze_elite_schedule run 2: failure=none; dropped rules=25; no scored numeric misses.
- oscar_2026_tx_bronze_elite_schedule run 3: failure=transport_timeout; dropped rules=0; no scored numeric misses.
- oscar_2026_tx_eoc run 1: failure=transport_timeout; dropped rules=0; no scored numeric misses.
- oscar_2026_tx_eoc run 2: failure=no_supported_rules; dropped rules=0; no scored numeric misses.
- oscar_2026_tx_eoc run 3: failure=no_supported_rules; dropped rules=0; no scored numeric misses.

Failure codes are deliberately fixed, privacy-safe categories; exception messages, policy quotes, model responses and full compilations are not published. JSON includes all per-run timings, numeric predictions, citation counts, omissions and request audits. No failure was replaced by a retry or curated rule.

## Provenance and reproducibility

Starting revision: `79d98f80dda182e76dd8a0dfaf9a21133ac2d7e6`. Production files unchanged on disk during measurement: **False**. The compiler, provider, schema and PDF modules were imported once in a single process; concurrent on-disk edits were not reloaded. The initial hashes identify the measured implementation. pypdf: `7.1.0`. Python: `3.13.5`. Production module hashes, manifest hash, PDF hashes, extraction hashes and the script hash at measurement start are in JSON.

Reproduction (requires the ignored original PDFs, DEEPSEEK_API_KEY, and a manually reviewed numeric labels JSON):

```sh
timeout 3600 .venv/bin/python scripts/bench_real_sbc.py --labels data/real_private/benchmark-real-sbc/labels.json
```

The public JSON embeds the frozen numeric labels for reconstruction. The script never prints credentials or source text. Reports contain only metrics, numeric facts, identifiers and methodology; private PDFs and text remain ignored. `reports/evaluation-real-sbc.json` is not changed.

## Repository checks

The final full unittest run passed all 186 tests, including five new benchmark accounting/privacy tests. The Pages build passed using a private output directory. Earlier shared-repository checks failed; the initial 18 failures were reproduced on the committed baseline. Concurrent fixes resolved them. This task changed no production code or existing evaluation report.
