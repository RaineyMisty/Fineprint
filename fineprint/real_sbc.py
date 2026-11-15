"""Audit rounded published SBC labels without substituting them for predictions.

No live providers or private text are read by the evaluator. Compilation reports
are measurements, not curated gold policies. Full episode replay is currently
blocked: no reviewed mapping from CMS timelines to these plans' benefits exists.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ("deductibles", "copayments", "coinsurance", "limits_exclusions")
TARGETS = {
    "kaiser_2026_ca_gold80_sbc.pdf": "kaiser",
    "cigna_2026_in_connect_gold_sbc.pdf": "cigna",
    "highmark_2026_pa_together_blue_gold_sbc.pdf": "highmark",
}
# A conservative comparison envelope, not an official exact-match criterion:
# four separately rounded components, each with at most $50 rounding error.
ROUNDING_TOLERANCE_CENTS = 20_000


def compare_total(predicted_cents, published_cents, tolerance_cents=ROUNDING_TOLERANCE_CENTS):
    """A missing prediction never counts as either a match or a numeric miss."""
    if type(published_cents) is not int or published_cents < 0:
        raise ValueError("Published total must be nonnegative integer cents")
    if type(tolerance_cents) is not int or tolerance_cents < 0:
        raise ValueError("Tolerance must be nonnegative integer cents")
    if predicted_cents is None:
        return dict(predicted_patient_cents=None, absolute_error_cents=None, within_tolerance=None)
    if type(predicted_cents) is not int or predicted_cents < 0:
        raise ValueError("Predicted total must be nonnegative integer cents")
    error = abs(predicted_cents - published_cents)
    return dict(predicted_patient_cents=predicted_cents, absolute_error_cents=error,
                within_tolerance=error <= tolerance_cents)


def evaluate(labels_path=ROOT / "data/real_coverage_example_labels.csv", reports_dir=ROOT / "reports",
             audit_path=ROOT / "data/real_coverage_example_input_audit.json"):
    with labels_path.open(newline="", encoding="utf-8") as stream:
        labels = list(csv.DictReader(stream))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    input_audits = {(row["document"], row["example"]): row for row in audit["examples"]}
    rows = []
    compilation_counts = {}
    for label in labels:
        components = {field: int(label[field]) * 100 for field in COMPONENTS}
        published = int(label["patient_total"]) * 100
        slug = TARGETS.get(Path(label["local_file"]).name)
        reasons = []
        provider_runs = []
        input_audit = input_audits.get((slug, label["example"]))
        if slug:
            path = reports_dir / f"real-{slug}-rules.json"
            if not path.is_file():
                reasons.append("Compilation measurement unavailable")
            else:
                compilation_report = json.loads(path.read_text(encoding="utf-8"))
                for run in compilation_report["runs"]:
                    provider_runs.append(dict(provider=run["provider"], model=run["model"],
                                              status=run["status"], error=run["error"],
                                              claim_ready=run.get("claim_ready", False),
                                              validated_rules=run.get("validated_rules", 0),
                                              report=path.name))
                    compilation_counts[(slug, run["provider"])] = run["status"]
                if not any(run["status"] == "validated" for run in compilation_report["runs"]):
                    reasons.append("No validated executable policy from the measured compilers")
                elif not any(run.get("claim_ready") for run in compilation_report["runs"]):
                    reasons.append("Only partial financial rules validated; no claim-ready service policy")
                if input_audit and input_audit["source_sha256"] != compilation_report["source_sha256"]:
                    raise ValueError("Coverage-example input audit does not match the compiled source")
            reasons += ["SBC episode totals are not service-level allowed amounts or service counts",
                        "Local CMS timelines exist, but no reviewed service/code-to-plan-benefit mapping or complete scenario replay is implemented; cached workbook outcomes are not insurer predictions"]
            reasons.append("Published patient cost-sharing components are outputs, not independent allowed-cost inputs; adding them would reuse the answer")
        else:
            reasons.append("Insurer outside this compilation run (Kaiser, Cigna and Highmark only)")
        rows.append(dict(insurer=label["insurer"], plan=label["plan"], plan_year=int(label["plan_year"]),
                         example=label["example"], source_url=label["source_url"], pdf_page=int(label["pdf_page"]),
                         label_status=label["label_status"], published_components_cents=components,
                         published_patient_cents=published,
                         label_components_sum_correctly=sum(components.values()) == published,
                         status="blocked" if slug else "not_attempted", reasons=reasons,
                         input_audit=input_audit,
                         compiler_runs=provider_runs,
                         **compare_total(None, published)))
    recalculated = [row for row in rows if row["predicted_patient_cents"] is not None]
    return dict(schema_version=1, kind="real_published_sbc_examples", synthetic=False,
                title="real published SBC examples (rounded)",
                generated_at=datetime.now(timezone.utc).isoformat(),
                labels_sha256=hashlib.sha256(labels_path.read_bytes()).hexdigest(),
                input_audit_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
                input_audit_method=audit["method"],
                currency="USD", rounding_tolerance_cents=ROUNDING_TOLERANCE_CENTS,
                rounding_note="Analyst-selected conservative $200 absolute total envelope: four published components, each rounded by at most $50. CMS instructions p. 4 round costs above $100 to $100 and below $100 to $10, with OOP-cap adjustment. This envelope alone cannot establish component accuracy or exact adjudication. No predictions were available to apply it to in this run.",
                rounding_source_url="https://www.cms.gov/files/document/coverage-examples-calculator-instructions-060723.pdf",
                methodology=["Official rounded illustrations, not actual adjudicated claims, bills, or savings measurements.",
                             "All 18 published labels retained; compilation attempted for nine examples across three insurers; other nine explicitly not attempted.",
                             "Compiler failures and missing scenario inputs block calculation; no manual gold policy, invented CPT codes, inferred service counts or episode-price substitution.",
                             "Published component addition checks transcription only; it is never counted as independent patient-cost recalculation.",
                             "Nine SBC example pages were reviewed for input sufficiency: published episode costs are available, but service quantities and per-service allowed prices are absent. Patient cost-sharing outputs are excluded from prediction inputs.",
                             "Kaiser EOC compilation is reported separately; no merger with the SBC was attempted.",
                             "Accuracy and mean absolute error are null when no scenario can be independently recalculated.",
                             "SYNTHETIC_kaiser_demo_replay.json and all bundled synthetic benchmarks are excluded."],
                summary=dict(published_labels=len(rows), insurers=len({row['insurer'] for row in rows}),
                             compilation_targeted_examples=sum(row["status"] == "blocked" for row in rows),
                             blocked=sum(row["status"] == "blocked" for row in rows),
                             not_attempted=sum(row["status"] == "not_attempted" for row in rows),
                             recalculated=len(recalculated),
                             matches_within_tolerance=sum(row["within_tolerance"] is True for row in recalculated),
                             misses=sum(row["within_tolerance"] is False for row in recalculated),
                             accuracy=None if not recalculated else sum(row["within_tolerance"] for row in recalculated) / len(recalculated),
                             mean_absolute_error_cents=None if not recalculated else sum(row["absolute_error_cents"] for row in recalculated) / len(recalculated),
                             label_arithmetic_checks_passed=sum(row["label_components_sum_correctly"] for row in rows)),
                compilation_measurements=[dict(insurer=slug, provider=provider, status=status)
                                          for (slug, provider), status in sorted(compilation_counts.items())],
                examples=rows)


def render_markdown(report):
    summary = report["summary"]
    lines = ["# Real published SBC examples (rounded)", "", f"Measured {report['generated_at']}.", "",
             f"**{summary['published_labels']} labels / {summary['insurers']} insurers; {summary['compilation_targeted_examples']} examples targeted; "
             f"{summary['recalculated']} independently recalculated, {summary['blocked']} blocked, {summary['not_attempted']} not attempted.**",
             f"Confirmed matches: {summary['matches_within_tolerance']}; numeric misses: {summary['misses']}. Accuracy and mean error: **unavailable** (no predictions).", "",
             "These are published illustrations, not matched real claims. There is no public matched policy → adjudicated claim → hospital bill chain.", "",
             "The provider reviewed selected source sections, with quotes validated against the full source. Partial financial-rule validation does not establish a claim-ready policy. See [Kaiser SBC](real-kaiser-rules.md), [Kaiser EOC](real-kaiser-eoc-rules.md), [Cigna](real-cigna-rules.md), and [Highmark](real-highmark-rules.md).", "",
             "SBCs do not itemize episode service quantities/allowed prices. The private CMS workbook contains generic timelines, but mapping those services to these plans' categories, deductible exceptions, visits/admissions and limits is unimplemented. Its cached outcomes are not plan-configured predictions. A published episode total cannot replace that work.", "",
             "Source-page input audit: each targeted SBC publishes episode costs of $12,700 (Peg), $5,600 (Joe) and $2,800 (Mia), plus service category names. None supplies the quantities and allowed-price breakdown needed to apply category-specific copays/coinsurance independently. The patient deductible/copay/coinsurance rows are published answers, excluded from prediction inputs. [Numeric audit and source hashes](../data/real_coverage_example_input_audit.json).", "",
             f"**Rounding:** {report['rounding_note']} [Official CMS instructions, physical PDF p. 4]({report['rounding_source_url']}).", "",
             f"Transcription-only check: {summary['label_arithmetic_checks_passed']}/{summary['published_labels']} published component sums equal the published totals. **This is not recalculation accuracy.**", "",
             "| Insurer | Example | Published patient total | Predicted | Result |", "|---|---|---:|---:|---|"]
    for row in report["examples"]:
        lines.append(f"| {row['insurer']} | {row['example']} | ${row['published_patient_cents'] / 100:,.0f} | — | {row['status']} |")
    lines += ["", "Numeric labels and official source links: [CSV](../data/real_coverage_example_labels.csv). "
              "[Manifest and redistribution limits](../data/README.md). No PDFs or full policy extracts included. "
              "Synthetic demo replay and synthetic benchmark cases remain separate."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    report = evaluate()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "evaluation-real-sbc.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (args.output_dir / "evaluation-real-sbc.md").write_text(render_markdown(report))
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
