# Real published SBC examples (rounded)

Measured 2026-11-15T03:32:32.404713+00:00.

**18 labels / 6 insurers; 9 examples targeted; 0 independently recalculated, 9 blocked, 9 not attempted.**
Confirmed matches: 0; numeric misses: 0. Accuracy and mean error: **unavailable** (no predictions).

These are published illustrations, not matched real claims. There is no public matched policy → adjudicated claim → hospital bill chain.

The existing compilers were run on raw text. See [Kaiser SBC](real-kaiser-rules.md), [Kaiser EOC](real-kaiser-eoc-rules.md), [Cigna](real-cigna-rules.md), and [Highmark](real-highmark-rules.md) for measured outcomes.

SBCs do not itemize episode service quantities/allowed prices. The private CMS workbook contains generic timelines, but mapping those services to these plans' categories, deductible exceptions, visits/admissions and limits is unimplemented. Its cached outcomes are not plan-configured predictions. A published episode total cannot replace that work.

**Rounding:** Analyst-selected conservative $200 absolute total envelope: four published components, each rounded by at most $50. CMS instructions p. 4 round costs above $100 to $100 and below $100 to $10, with OOP-cap adjustment. This envelope alone cannot establish component accuracy or exact adjudication. No predictions were available to apply it to in this run. [Official CMS instructions, physical PDF p. 4](https://www.cms.gov/files/document/coverage-examples-calculator-instructions-060723.pdf).

Transcription-only check: 18/18 published component sums equal the published totals. **This is not recalculation accuracy.**

| Insurer | Example | Published patient total | Predicted | Result |
|---|---|---:|---:|---|
| Kaiser Permanente | Peg childbirth | $750 | — | blocked |
| Kaiser Permanente | Joe diabetes | $1,100 | — | blocked |
| Kaiser Permanente | Mia fracture | $1,000 | — | blocked |
| Cigna | Peg childbirth | $4,670 | — | blocked |
| Cigna | Joe diabetes | $1,720 | — | blocked |
| Cigna | Mia fracture | $2,000 | — | blocked |
| Highmark | Peg childbirth | $1,260 | — | blocked |
| Highmark | Joe diabetes | $920 | — | blocked |
| Highmark | Mia fracture | $1,000 | — | blocked |
| Ambetter/Health Net | Peg childbirth | $1,060 | — | not_attempted |
| Ambetter/Health Net | Joe diabetes | $1,620 | — | not_attempted |
| Ambetter/Health Net | Mia fracture | $1,350 | — | not_attempted |
| Aetna | Peg childbirth | $3,370 | — | not_attempted |
| Aetna | Joe diabetes | $4,520 | — | not_attempted |
| Aetna | Mia fracture | $1,800 | — | not_attempted |
| Oscar | Peg childbirth | $4,200 | — | not_attempted |
| Oscar | Joe diabetes | $4,800 | — | not_attempted |
| Oscar | Mia fracture | $1,800 | — | not_attempted |

Numeric labels and official source links: [CSV](../data/real_coverage_example_labels.csv). [Manifest and redistribution limits](../data/README.md). No PDFs or full policy extracts included. Synthetic demo replay and synthetic benchmark cases remain separate.
