# Real DeepSeek billing regression check

Each run calls the real pasted-document check entry point with original policy/EOB/bill and DeepSeek. No cache, fallback, hand-compiled rules or expected amount is supplied to the pipeline. Therapy remains conditional; its patient-facing document-bounded amount must be $40.

| Sample | Run | Status | Patient total | Conditional | Passed |
| --- | ---: | --- | ---: | --- | --- |
| aurora-imaging | 1 | ready | $385.00–$385.00 | False | True |
| aurora-imaging | 2 | ready | $385.00–$385.00 | False | True |
| mosaic-oop | 1 | ready | $1,000.00–$1,000.00 | False | True |
| mosaic-oop | 2 | ready | $1,000.00–$1,000.00 | False | True |
| mosaic-therapy | 1 | ready | $40.00–$40.00 | True | True |
| mosaic-therapy | 2 | ready | $40.00–$40.00 | True | True |

All six passed: **True**. Model: `deepseek-v4-pro`; source hashes, complete outputs and real request audits are in the companion JSON. No deployment.

Full unittest: **201 tests passed; 9 skipped**.
