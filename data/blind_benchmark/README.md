# Blind synthetic benchmark

All insurers, people, providers, contracts, recognized amounts and documents are fictional and **SYNTHETIC**. There are 40 independent cases: 16 correct statements and 24 erroneous statements. Errors include underbilling as well as overbilling. These documents are not legal or clinical guidance.

Each case has an SBC-style `policy.md`, an observed `eob.json`, an itemized `bill.json`, and a separately hand-authored `expected.json`. Currency is USD; serialized money is integer cents. Gold responsibility is the total liability before previous payments; gold remaining owed subtracts payments per line. A real error means the statement's patient-paid-plus-balance amount differs from the correct liability. A protected emergency/ancillary service, provider authorization/referral liability, duplicate, bundled component, or acknowledged code error includes explicit applicability facts; applicability is not inferred from a code alone.

## Blinding and freeze

Before creating expectations the independent writer read only the root README and `docs/architecture.md`, plus repository metadata and directory listings. No product source, tests, existing benchmark input cases or gold answers were opened. The root README itself contains demonstration arithmetic and prior aggregate benchmark results; this is disclosed exposure, rather than a claim that all prior product examples were unknown. None of those cases was opened or reused. The writer did not inspect any application source or run any application pipeline before freezing.

`author_cases.py` contains literal hand-worked answers and explanations. Its arithmetic only converts USD literals to cents, renders documents, balances observed statements, and verifies the authored totals. It imports no product code and computes no gold responsibility from policy rules. It was executed once before the freeze. Do not regenerate or change cases after freezing.

The frozen directory digest is SHA-256 over each regular file in `cases/`, in lexical POSIX relative-path order: UTF-8 relative path, a NUL byte, file contents, then a NUL byte. `cases.sha256` contains independent file hashes; `freeze.json` records the composite digest. The freeze commit is recorded separately after committing, before any pipeline inspection or execution. Cases must be committed and pushed before phase 2.

## Prespecified scoring

Every case is submitted once to the real policy compilation and analysis pipeline with DeepSeek. No fallback, gold policy, answer substitution, case repair, or rerun is allowed. One provider attempt per case is selected explicitly to preserve the single-run constraint. A local schema adapter may translate the frozen observation format to the public app input schema, without reading gold answers or changing policy/facts. Authoring and run helpers live outside `cases/`.

Statuses: **answer** for a supported nonconditional point result; **range** for a conditional or multiple-scenario result; **needs clarification** for a semantic block without a calculation; **error** for compilation/transport/structural/runtime failures. Conditional scenario extrema are illustrative and are not asserted to be exhaustive contractual bounds.

Exact-amount accuracy: an answer's total patient responsibility is within 100 cents inclusive of gold, divided by all 40 cases. Also report answer-only accuracy and per-line accuracy. A range does not count as an exact answer. Range containment: gold within the inclusive reported scenario extrema, divided by range cases; also report containment across all cases, counting a point answer as a singleton. Abstain/dead-end: needs-clarification or error divided by 40; separately report conditional results and all cases without a confirmed answer.

Error detection uses an explicit nonconditional app finding of EOB/patient responsibility or final-bill disagreement. Bill reconciliation differences count; a component difference alone without a total responsibility difference does not establish a statement error. Conditional/failed cases abstain. Precision = TP/(TP+FP); recall = TP/24, counting failed positives as misses; FPR = FP/16, with resolved negative coverage separately stated. A zero denominator is reported as null/n/a. Report confusion counts and prediction coverage. Any supported point amount or illustrative range upper endpoint exceeding the statement patient total is listed, as is any exceeding the gross charge; underbilling is not automatically an app error.

Gold is loaded only after all run records are durably saved. Raw returned outputs, errors and the adapter/run configuration are retained without repair. No product code may be modified.
