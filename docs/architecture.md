# Architecture and extension notes

## Initial decisions

- Python 3.11+ standard library: dataclasses, integer arithmetic, JSON/CSV and a threaded local HTTP server. No database, framework, model SDK or account prerequisite.
- Browser-native HTML/CSS/JavaScript: no build pipeline, CDN fonts, analytics or external requests.
- Presentation differences stop at adapters. The engine never branches on insurer names or layout.
- The default repository compiles original natural-language policy documents. Curated policy JSON is independent gold and an explicit legacy import option. No gold rules are passed to the compiler.
- Schema `1.0` rejects unknown fields rather than ignoring them. Add explicit migrations when extending the contract.
- Changes remain local commits; deployment is outside this run.

## Unified model

| Entity | Responsibility |
| --- | --- |
| `Case` | Version, identity/title, synthetic flag, policy, claim, bill and allowance evidence. |
| `Policy` | Policy/member IDs, insurer, effective period, USD, network terms, benefits and clauses. |
| `Clause` | Citation ID, original text and source location. `Compilation.output.rule_evidence` adds document ID, exact quote, character offsets and confidence/ambiguity for every executable rule. |
| `NetworkTerms` | Individual deductible/OOP maximum, excess-charge balance-billing rule, citations. Separate in/out pools. |
| `Benefit` | Codes, network, coverage/exclusion, deductible applicability, copay, member coinsurance basis points, clauses and optional ambiguity group. |
| `Claim` / `ClaimLine` | Identity links, pre-claim accumulators, provider/date/code/line identifiers, network and charge. `Adjudication` preserves insurer observations. |
| `Bill` / `BillLine` | Claim/member and explicit claim-line links, provider/date/code, charge, insurance credit, adjustment, patient payment and balance due. |
| `AllowedEvidence` | Allowance, source (`contract`, `eob`, `unknown`) and reference. Never automatically copied from EOB. |

All money fields end in `_cents`, with bounds 0–10^12. Integers are strict: `true`, `1.0` and `"1"` are invalid money. Coinsurance uses 0–10,000 basis points; dates are canonical `YYYY-MM-DD`. Use `case_from_dict` at external boundaries and `service.analyze` for analysis. Structural decoding and semantic validation are separate.

Provider/date/code are validation keys, not fuzzy matching. Explicit `claim_line_id` distinguishes repeated services. Currently exactly one bill line must match each claim line; split/consolidated bills require a future mapping model. The UI's exported JSON is a complete normalized API example. Raw fixture formats remain separate to exercise adapters.

## Consistency versus policy compliance

Validation checks identity, unique IDs, coverage period, provider/date/code equality, charge agreement, complete line links, valid clause references, supported rule semantics and accumulator constraints. Accounting identities:

```text
EOB charge = deductible + copay + coinsurance + noncovered + balance
             + insurer payment + adjustment
Bill charge = insurance credit + adjustment + patient paid + balance due
```

Bill/EOB patient-total or insurance-credit differences are warnings when documents individually balance. These are reconciliation findings. Broken identities, invalid rules and unsupported relationships are errors and block calculation. A balanced EOB can still use the wrong deductible; the engine/comparison layer independently evaluates policy compliance.

## Deterministic calculation contract

For a covered line: allowance `A`, charge `B`, remaining deductible `D`, remaining OOP `O`:

```text
raw_deductible = min(A, D) if applicable, otherwise 0
raw_copay = min(configured copay, A - raw_deductible)
raw_coinsurance = round_half_up((A - raw_deductible - raw_copay) × member bps / 10,000)

deductible = min(raw_deductible, O)
copay = min(raw_copay, O - deductible)
coinsurance = min(raw_coinsurance, O - deductible - copay)

covered_patient = deductible + copay + coinsurance
balance = B - A if balance billing permitted, otherwise 0
patient = covered_patient + balance
insurer = A - covered_patient
adjustment = B - patient - insurer
```

Half-up rounding is `(cents × bps + 5000) // 10000`; no float affects arithmetic. The cap allocates in deductible/copay/coinsurance order and only actual charged cost sharing updates accumulators. All amounts are nonnegative; patient + insurer + adjustment equals charge. Benefit clauses in every fixture explicitly declare this order.

An exclusion makes the full charge patient liability, insurer/adjustment zero, with no deductible/OOP accrual. This is the fictional contract, not a general rule for real denials or provider liability. Permitted network excess is outside the OOP cap. Legal restrictions on balance billing are not evaluated.

Sort by `(service_date, line_id)`; same-day component allocation follows lexical line-ID order. Start from spending immediately before this claim. Reversals, multiple claims and chronology of an annual ledger are not managed. Individual annual pools are independent by network; each line is one visit/unit. Family, shared/tiered pools and benefit maximums are unsupported.

## Ambiguity and missing evidence

- Missing code/network rules block calculation; neither coverage nor exclusion is guessed.
- Overlapping rules require a shared nonempty `ambiguity_group` and distinct labels. Each affected code/network must define the same label set. One interpretation is selected consistently across its lines, preventing incompatible line-by-line cherry-picking.
- Unknown network branches per line to in/out.
- Missing allowance generates $0 and full-charge **illustrative endpoints**, not a contractual estimate. Intermediate rates may give different results. SBC cost sharing alone cannot supply a negotiated rate.
- Missing opening spending generates endpoint combinations respecting deductible spending <= OOP spending. Known OOP bounds missing deductible; known deductible supplies the lower endpoint of missing OOP.
- Assumptions and EOB-derived allowances set `conditional=True`, even if only one monetary outcome remains.
- Above 256 scenarios, analysis is blocked. No alternatives are truncated, no partial minimum is advertised. Summary min/max covers enumerated examples, not exhaustive bounds on real policies.

Scenarios may retain different facts that yield the same amount. For example, an in-network ambiguity is irrelevant when a line is assumed out-of-network. Keeping these scenarios explicit preserves assumptions.

## Three-way comparison and payments

Compare EOB components to recalculated components, then EOB patient total to bill patient payments plus current balance. Explanations cite existing clauses resolved to source text/locations. Recorded insurer components are not presented as an invented insurer reasoning trace.

```text
bill_patient_total = previous patient payment + current balance
potential_excess = max(0, bill_patient_total - Fineprint patient total)
line_remaining = max(0, Fineprint line liability - line patient payment)
line_potential_refund = max(0, line patient payment - Fineprint line liability)
```

Remaining amounts/refunds sum per line, without silently offsetting credits across providers. Potential case excess is a net comparison; line details can include both overcharges and undercharges. Negative EOB/Fineprint differences remain visible. A conditional result does not become a confirmed saving merely because it favors the patient.

## Provider and insurer extension points

`compiler.get_compiler(provider=None).compile(document, document_id)` is the new common interface. It returns `Compilation`: backend, attempt count, document ID/hash, strict `Policy`, evidence, warnings and unresolved clauses. `RuleEvidence.rule_path` identifies each network financial field or benefit rule. `Evidence.start/end` use Unicode character offsets, with an exclusive end. Exact quote validation runs on deterministic and provider outputs alike.

`FallbackCompiler` parses bounded English patterns from clause grids, numbered Markdown sections and tagged paragraphs. It reads no insurer names for dispatch and never opens curated gold. It requires documented calculation order, network terms, plan metadata and explicit service codes. Unsupported recognized clauses remain unresolved; missing core terms fail compilation. Text outside recognized clause blocks and arbitrary natural-language exceptions are not reliably understood. This is a bounded parser, not a general contract-understanding system.

`OUTPUT_SCHEMA` is generated from the compiler/domain dataclasses. Its supported vocabulary is closed objects, required fields, arrays, primitive types, enums, numeric bounds and unions. The dependency-free local validator checks that exact schema vocabulary; it is not a general-purpose JSON Schema library. The decoder additionally validates dates/nonempty strings. Semantic checks require evidence for all rule paths, source/quote/span integrity, existing clause references, supported exclusions and explicit ambiguity groups for overlaps. Source validity does not establish semantic correctness; a quoted clause could still be misinterpreted.

`providers.LLMCompiler` selects OpenAI, Anthropic or Amazon Bedrock through `FINEPRINT_LLM_PROVIDER`. OpenAI uses [Chat Completions JSON-schema output](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), Anthropic uses [Messages structured output](https://platform.claude.com/docs/en/api/messages/create), and Bedrock uses [Converse forced tools](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html). HTTPS transports for OpenAI/Anthropic use the standard library. Optional boto3 handles AWS credentials/SigV4. Set an enabled Bedrock model/profile supporting forced tools. See `.env.example` for environment configuration.

Every attempt validates JSON Schema and source fidelity; failures trigger bounded retries/backoff, then surface without silently replacing output. Test transports are test doubles only, not LLM measurements. Live transports are implemented but have not been credential-tested. The UI labels live provider output as requiring source review. No durable human approval workflow is implemented.

`extraction.PolicyExtractor` remains a legacy structured-import extension. `StructuredPolicyExtractor` explicitly reads curated JSON; injected `ProviderPolicyExtractor` output still requires review before legacy fixture ingestion. This legacy boundary is not the prose compiler used by the demo/evaluation.

An insurer adapter implements `ClaimAdapter`: source string + context dictionary → strictly decoded `Claim`. Register it in `CLAIM_ADAPTERS`; add a distinct-format fixture and manually checked normalization/calculation expectations. Engine/UI should need no insurer-specific code. A new policy layout can use a new compiler backend/parser version, evaluated on a new untouched holdout.

## Application/API boundary

`service.analyze` returns validation, links, scenarios, traces, comparisons, summary and limitations. Errors or too many scenarios yield `status="blocked"`, a reason, empty scenario/comparison lists and no summary total. Structural failures return HTTP 400; semantic blocked reports return HTTP 200 for UI inspection.

The server uses an explicit static allowlist and validated case IDs, a 1 MiB JSON limit, same-origin assets, restrictive CSP, no CORS opt-in, cross-site browser request rejection and no case-content logging. Imports are not persisted. Export is an intentional browser download. The standard-library server and these measures do not replace production hosting, authentication, secure durable storage or health-data governance.

## End-to-end synthetic evaluation

`python3 -m fineprint.eval --provider fallback` runs compilation → strict validation → independent calculation → EOB comparison → final bill reconciliation. The compiler receives only source text and document ID. Independent gold is loaded afterward for scoring; the case's policy is replaced completely by compiled output before `analyze` runs.

The manifest identifies three seen policy documents and two held-out insurers, with ten cases. The fallback was committed at `bd9f7ab` before authoring held-out Cedar/Harbor documents; a stored SHA-256 verifies the frozen compiler. This is an author-created format holdout, not blind external validation. Cedar parses; Harbor's transposed matrix fails closed. Both Harbor cases stay in metric denominators. Do not tune the frozen parser on Harbor and continue calling it held out.

Extraction scores a multiset of semantic financial fields, ignoring cosmetic IDs/labels; policies are counted once even when multiple claims share them. Exact calculation compares all line monetary fields, networks, complete distinct outcomes, scenario count and conditional status. Conditional cases abstain from binary discrepancy classification. Failed positive compilations count as false negatives; failed negatives abstain rather than becoming true negatives. FPR divides false positives by all gold negatives, with resolved coverage reported separately.

Traceability divides valid spans by emitted rules; evidence coverage also includes missing rules from compilation failures. End-to-end success requires exact extraction/calculation, independent final-bill reconciliation against gold line liabilities, complete evidence and a correct discrepancy/ambiguity decision. Report JSON includes raw counts and per-policy/per-case failures; Markdown and both READMEs show measured split results. Unit tests inject wrong fields, final balances, false positives and total compilation failure to check that metrics do not hide errors.

`POST /api/compile` compiles text alone or accepts an attached normalized case for recalculation; unresolved clauses block execution. `GET /api/cases/{id}` compiles its original policy document. `GET /api/evaluation` explicitly runs the offline fallback regardless of server provider settings. Normalized JSON imports do not inherit invented compiler evidence; source text must be compiled again to create it.
