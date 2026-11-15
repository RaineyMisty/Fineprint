# Blind benchmark: 15% → 70% — evidence record

Synthetic data only: fictional people, insurers and bills. Model: DeepSeek `deepseek-v4-pro`.

## What was measured
40 synthetic cases (16 correct bills, 24 bills with a real error). Each case has a policy, an insurer statement (EOB), a bill, and a hand-written expected answer.
An independent Codex agent wrote all 40 cases. It read only the README and `docs/architecture.md`, and never saw the product code, the tests, or the existing benchmark answers.

## Step 1: freeze, then run once (blind)
- The cases were frozen and pushed before any run: commit `79d98f80dda182e76dd8a0dfaf9a21133ac2d7e6`.
- SHA-256 of the cases directory: `6b170685afb68afa0d64d49b4313b4eb9eba5283ae187759888a16a4dc4c7679`. It was unchanged after both runs (0 mismatches across 160 files).
- Each case ran exactly once through the real pipeline: one DeepSeek call per case, with no reruns and no tuning.
- Results commit: `36ac3ff3abb3b551667befe39ac685e173c52b73`.

## Step 2: diagnose, fix the general causes, rerun once (not blind)
The cases were seen at this point, so this is a fix-and-verify result, not a new blind score.

Root causes of the 33 cases that gave no answer:

| Cause | Cases |
|---|---:|
| Explicit balance/excess-billing wording rejected by the source validator. It appeared in 4 layouts: yes/no reference cards, question-and-answer text, SBC table cells, and narrative prose. | 24 |
| Plan display name missing or empty, which failed the schema | 9 |

General fixes:
- `e2be3f2`: billing-language validation now handles all four layouts and both word orders, and unnamed plans fall back to the source heading.
- `edbef78`: a negation guard, so "not permitted to balance bill" stays a prohibition.

Supporting fixes made in parallel:
- `3b3231f`: DeepSeek retries and temperature 0.
- `13232be` and `92bd83b`: rule de-duplication and plain-English messages.
- `4234ea3` and `b761208`: the patient amount is never above the bill.

No case, expected answer, insurer name or amount is referenced in product code. The frozen inputs and expected answers were not edited.

## Results

| Metric | Blind run (step 1) | After fixes (step 2, not blind) |
|---|---:|---:|
| Exact amount within $1 (all 40) | **15.0%** (6/40) | **70.0%** (28/40) |
| No answer (needs clarification or error) | 82.5% (33/40) | 7.5% (3/40) |
| Error-detection precision | 100% | 100% |
| Error-detection recall (24 true errors) | 16.7% (4/24) | 62.5% (15/24) |
| False-positive rate (16 correct bills) | 0% | 0% |
| Patient amount above the bill | 0 | 0 |

Regression check: the original 10-case synthetic benchmark stayed at 8/10, and the three built-in app samples were unchanged ($385, $1,000, $40). Full unit tests passed: 197 tests, 9 skipped.

## How to describe it honestly
"On 40 independently written cases, the first blind run answered 15% exactly. We diagnosed two general failure classes, fixed them in the product, and the same 40 cases rose to 70%, with 0 false positives and no amount above the bill." The 70% figure was measured on cases we had already seen. It is not a new blind accuracy.

Full details: `reports/benchmark-blind.md`, `reports/benchmark-blind-after-fixes.md`, and the JSON files next to them.
