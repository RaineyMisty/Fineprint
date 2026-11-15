"""Copy an already downloaded research bundle locally; publish metadata only.

Run from the repository root. This script never downloads anything.
"""
import argparse
import csv
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "data/real_private"
NOTICE = "No redistribution license; PDF/text not in this repo. Local testing only; link to official source."


def import_corpus(source):
    sources = list(csv.DictReader((source / "sources.csv").open(newline="", encoding="utf-8")))
    indexed = {}
    for row in sources:
        for field in ("local_file", "extracted_text"):
            if row[field]:
                indexed[row[field]] = row
    PRIVATE.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / "docs", PRIVATE / "docs", dirs_exist_ok=True)
    shutil.copy2(source / "sources.csv", PRIVATE / "sources.csv")
    shutil.copy2(source / "REPORT.md", PRIVATE / "REPORT.md")
    rows = []
    for path in sorted(PRIVATE.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(PRIVATE).as_posix()
        metadata = indexed.get(relative, {})
        derivatives = {
            "cms_coverage_examples_calculator.txt": "docs/cms_coverage_examples_calculator.xlsm",
            "ucla_ronald_reagan_standardcharges.txt": "docs/ucla_ronald_reagan_standardcharges.json.gz",
            "ucla_rate_excerpt.json": "docs/ucla_ronald_reagan_standardcharges.json.gz",
            "cms_2026_selected_plan_attributes.json": "docs/cms_2026_plan_attributes.zip",
        }
        if not metadata and path.name in derivatives:
            metadata = indexed.get(derivatives[path.name], {})
        # Research-generated scenario extracts inherit the official workbook source.
        if not metadata and (path.name.startswith("cms_") and
                             ("timeline" in path.name or "line_item" in path.name)):
            metadata = indexed.get("docs/cms_coverage_examples_calculator.xlsm", {})
        if not metadata and "cms_2026_plan_attributes/" in relative:
            metadata = indexed.get("docs/cms_2026_plan_attributes.zip", {})
        payload = path.read_bytes()
        rows.append(dict(local_path=path.relative_to(ROOT).as_posix(),
                         source_url=metadata.get("url", ""), resolved_url=metadata.get("resolved_url", ""),
                         insurer=metadata.get("insurer", ""), plan=metadata.get("plan", ""),
                         doc_type=metadata.get("doc_type", "research-derived metadata/fixture"),
                         sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload),
                         retrieved_utc=metadata.get("retrieved_utc", ""),
                         retrieval_notes=metadata.get("status", "Local research artifact; see private sources.csv and REPORT.md"),
                         synthetic=str(path.name.startswith("SYNTHETIC_")).lower(),
                         redistribution_note=NOTICE,
                         source_license_notes=metadata.get("license_redistribution_notes", "")))
    with (ROOT / "data/real_manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    labels = list(csv.DictReader((PRIVATE / "docs/coverage_example_labels.csv").open(newline="", encoding="utf-8")))
    for row in labels:
        row["source_url"] = indexed[row["local_file"]]["url"]
        row["local_file"] = "data/real_private/" + row["local_file"]
    with (ROOT / "data/real_coverage_example_labels.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(labels[0]))
        writer.writeheader()
        writer.writerows(labels)
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    print(f"Imported {import_corpus(parser.parse_args().source)} private files; manifest contains metadata only.")
