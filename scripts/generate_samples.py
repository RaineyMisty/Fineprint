"""Rebuild entirely fictional fixtures from authored numbers, without using the engine.

Run from the repository root: python3 scripts/generate_samples.py
Expected policy results live separately in tests/test_samples.py.
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "fineprint" / "samples"
NOTICE = "SYNTHETIC / FICTIONAL DEMONSTRATION ONLY. No real people, insurers, providers or claims."


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def benefit(id, label, codes, network="in", *, covered=True, ded=True, copay=0, coins=2000, clause="B1", group=""):
    return {"id": id, "label": label, "codes": codes, "network": network, "covered": covered,
            "deductible_applies": ded, "copay_cents": copay, "coinsurance_bps": coins,
            "clause_ids": [clause], "ambiguity_group": group}


def terms(ded, oop, balance, net):
    return {"deductible_cents": ded, "oop_max_cents": oop, "balance_billing": balance,
            "deductible_clause": f"D-{net}", "oop_clause": f"O-{net}", "network_clause": f"N-{net}"}


def policy(insurer, id, member, name, networks, benefits, extra_clauses):
    clauses = []
    for net, t in networks.items():
        for code, text in (
            (f"D-{net}", f"Individual annual {net}-network deductible: ${money(t['deductible_cents'])}. Apply to covered allowance before copay and coinsurance unless the benefit explicitly waives it."),
            (f"O-{net}", f"Individual annual {net}-network OOP maximum: ${money(t['oop_max_cents'])}. Cap covered deductible, copay and coinsurance together. Exclusions and permitted balance bills do not count. Network pools are separate."),
            (f"N-{net}", "Out-of-network charges above the allowed amount may be balance billed under this fictional plan; outside OOP." if t["balance_billing"] else "Covered participating-provider charges above the allowed amount must be written off; no balance billing."),
        ):
            clauses.append({"id": code, "text": text, "location": f"Synthetic SBC §{code}"})
    clauses += [{"id": id, "text": text, "location": f"Synthetic SBC §{id}"} for id, text in extra_clauses]
    clauses.append({"id": "ORDER", "text": "One visit/unit per line. Apply deductible, then copay, then member coinsurance on the remaining allowance. Round coinsurance half up to cents. Apply OOP cap in that order. Process by service date, then line ID. Excluded services are member liability at full charge. This is an illustrative individual USD plan only.", "location": "Synthetic SBC §ORDER"})
    for b in benefits:
        b["clause_ids"].append("ORDER")
    return {"id": id, "insurer": insurer, "name": name, "member_id": member,
            "effective_from": "2026-01-01", "effective_to": "2026-12-31", "currency": "USD",
            "networks": networks, "benefits": benefits, "clauses": clauses}


def line(id, code, description, billed, allowed, *, ded=0, copay=0, coins=0, noncovered=0, balance=0, paid=0, adjustment=0, net="in", date="2026-05-10", provider="PROVIDER-SYN-001"):
    return {"id": id, "code": code, "description": description, "billed_cents": billed, "network": net,
            "service_date": date, "provider_id": provider,
            "insurer": {"allowed_cents": allowed, "deductible_cents": ded, "copay_cents": copay,
                        "coinsurance_cents": coins, "noncovered_cents": noncovered, "balance_cents": balance,
                        "insurer_paid_cents": paid, "adjustment_cents": adjustment}}


def make_case(id, title, summary, p, claim_id, acc, lines, bills, format="aurora-csv-v1", missing=False):
    directory = ROOT / id
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "policy.json", p)
    header = f"# {p['insurer']} — {p['name']}\n\n> {NOTICE}\n\nPolicy: {p['id']} | Member: {p['member_id']} | Period: 2026-01-01 to 2026-12-31 | USD\n\n"
    if format == "aurora-csv-v1":
        body = "## Summary of benefits (grid format)\n\n| Clause | Terms |\n| --- | --- |\n" + "\n".join(f"| {c['id']} | {c['text']} |" for c in p["clauses"])
    else:
        body = "## Benefit booklet (numbered narrative format)\n\n" + "\n\n".join(f"### {i}. {c['id']}\n{c['text']}" for i, c in enumerate(p["clauses"], 1))
    (directory / "policy.md").write_text(header + body + "\n", encoding="utf-8")
    context = {"id": claim_id, "policy_id": p["id"], "member_id": p["member_id"], "accumulators": acc}
    if format == "aurora-csv-v1":
        claim_file = "eob.csv"
        with (directory / claim_file).open("w", newline="", encoding="utf-8") as handle:
            cols = ["synthetic", "line_ref", "provider", "service_day", "cpt_hcpcs", "description", "network", "charge", "allowed", "deductible", "copay", "coinsurance", "noncovered", "balance", "plan_paid", "adjustment"]
            writer = csv.DictWriter(handle, fieldnames=cols)
            writer.writeheader()
            for cl in lines:
                row = {"synthetic": NOTICE, "line_ref": cl["id"], "provider": cl["provider_id"], "service_day": cl["service_date"], "cpt_hcpcs": cl["code"], "description": cl["description"], "network": cl["network"], "charge": money(cl["billed_cents"])}
                row.update({key: money(cl["insurer"][f"{key}_cents"]) for key in ("allowed", "deductible", "copay", "coinsurance", "noncovered", "balance", "adjustment")})
                row["plan_paid"] = money(cl["insurer"]["insurer_paid_cents"])
                writer.writerow(row)
    else:
        claim_file = "eob-ledger.json"
        services = []
        for cl in lines:
            e = cl["insurer"]
            services.append({"ref": cl["id"], "facility": cl["provider_id"], "date": cl["service_date"], "procedure": cl["code"], "label": cl["description"], "participation": cl["network"], "submittedCents": cl["billed_cents"], "recognizedCents": e["allowed_cents"],
                             "memberShare": {"deductible": e["deductible_cents"], "fixed": e["copay_cents"], "percentage": e["coinsurance_cents"], "excluded": e["noncovered_cents"], "excess": e["balance_cents"]}, "planRemittanceCents": e["insurer_paid_cents"], "writeOffCents": e["adjustment_cents"]})
        write_json(directory / claim_file, {"synthetic": True, "notice": NOTICE, "claimReference": claim_id, "planRef": p["id"], "subscriberRef": p["member_id"], "priorSpend": acc, "services": services})
    with (directory / "bill.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["synthetic", "id", "claim_line_id", "provider_id", "service_date", "code", "charged", "insurance_paid", "adjustment", "patient_paid", "balance_due"])
        writer.writeheader()
        for cl, (adj, paid, due) in zip(lines, bills):
            writer.writerow({"synthetic": NOTICE, "id": f"BL-{cl['id']}", "claim_line_id": cl["id"], "provider_id": cl["provider_id"], "service_date": cl["service_date"], "code": cl["code"], "charged": money(cl["billed_cents"]), "insurance_paid": money(cl["insurer"]["insurer_paid_cents"]), "adjustment": money(adj), "patient_paid": money(paid), "balance_due": money(due)})
    evidence = {cl["id"]: {"allowed_cents": None if missing else cl["insurer"]["allowed_cents"], "source": "unknown" if missing else "contract", "reference": "Synthetic contract not supplied; EOB allowance not independently verified" if missing else f"Synthetic negotiated-rate exhibit RATE-{cl['id']}: {cl['code']} allowance ${money(cl['insurer']['allowed_cents'])}"} for cl in lines}
    write_json(directory / "manifest.json", {"id": id, "title": title, "summary": summary, "insurer": p["insurer"], "synthetic": True,
                                            "policy_rules": "policy.json", "policy_document": "policy.md", "claim_document": claim_file,
                                            "claim_format": format, "claim_context": context, "bill_document": "bill.csv",
                                            "bill_context": {"id": f"BILL-{claim_id}", "claim_id": claim_id, "member_id": p["member_id"]}, "allowed_evidence": evidence})


def main():
    p = policy("Aurora Mutual (fictional)", "POL-SYN-A01", "MEMBER-SYN-A01", "Synthetic Clear PPO",
               {"in": terms(100000, 300000, False, "in"), "out": terms(200000, 600000, True, "out")},
               [benefit("office", "Office copay", ["99213"], ded=False, copay=2500, coins=0),
                benefit("imaging", "Diagnostic imaging", ["70551"], clause="B2"),
                benefit("out", "Out-of-network office and imaging", ["99213", "70551"], "out", coins=4000, clause="B3")],
               [("B1", "In-network office visit (99213): $25 copay; deductible waived; no coinsurance."),
                ("B2", "In-network diagnostic imaging (70551): deductible then 20% member coinsurance."),
                ("B3", "Out-of-network office and imaging (99213, 70551): deductible then 40% coinsurance, plus permitted balance billing.")])
    make_case("aurora-imaging", "A deductible charged twice", "Office + MRI: verify remaining deductible, then reconcile a missing hospital credit.", p, "CLAIM-SYN-A01",
              {"in": {"deductible_paid_cents": 80000, "oop_paid_cents": 100000}, "out": {"deductible_paid_cents": 0, "oop_paid_cents": 0}},
              [line("A1", "99213", "Synthetic office visit", 24000, 15000, copay=2500, paid=12500, adjustment=9000),
               line("A2", "70551", "Synthetic diagnostic MRI", 160000, 100000, ded=30000, coins=14000, paid=56000, adjustment=60000)],
              [(9000, 0, 2500), (56000, 10000, 38000)])

    p = policy("Mosaic Health (fictional)", "POL-SYN-M01", "MEMBER-SYN-M01", "Synthetic Horizon Choice",
               {"in": terms(50000, 150000, False, "in"), "out": terms(100000, 300000, True, "out")},
               [benefit("surgery", "Ambulatory procedure", ["29881"], clause="B1"),
                benefit("excluded", "Elective cosmetic exclusion", ["15820"], covered=False, ded=False, coins=0, clause="X1"),
                benefit("transport", "Nonemergency transport", ["A0428"], "out", coins=5000, clause="B2")],
               [("B1", "Covered in-network ambulatory procedure (29881): deductible then 20% coinsurance; subject to OOP maximum."),
                ("X1", "In-network elective cosmetic service (15820) is excluded at full billed charge; no deductible or OOP credit."),
                ("B2", "Out-of-network nonemergency transport (A0428): deductible then 50% member coinsurance; permitted balance billing applies.")])
    make_case("mosaic-oop", "The out-of-pocket limit matters", "An OOP cap correction, an explicit exclusion, and a separate out-of-network pool.", p, "CLAIM-SYN-M01",
              {"in": {"deductible_paid_cents": 50000, "oop_paid_cents": 145000}, "out": {"deductible_paid_cents": 0, "oop_paid_cents": 0}},
              [line("M1", "29881", "Synthetic ambulatory procedure", 180000, 100000, coins=20000, paid=80000, adjustment=80000, provider="PROVIDER-SYN-002"),
               line("M2", "15820", "Synthetic excluded cosmetic service", 30000, 0, noncovered=30000, provider="PROVIDER-SYN-002"),
               line("M3", "A0428", "Synthetic nonemergency transport", 65000, 40000, ded=40000, balance=25000, net="out", provider="PROVIDER-SYN-003")],
              [(80000, 0, 20000), (0, 0, 30000), (0, 0, 65000)], format="mosaic-ledger-v1")

    p = policy("Mosaic Health (fictional)", "POL-SYN-M02", "MEMBER-SYN-M02", "Synthetic Therapy Choice",
               {"in": terms(50000, 150000, False, "in"), "out": terms(100000, 300000, True, "out")},
               [benefit("therapy-ded", "Deductible then 20%", ["97110"], clause="T1", group="therapy-wording"),
                benefit("therapy-copay", "Fixed $40 copay, deductible waived", ["97110"], ded=False, copay=4000, coins=0, clause="T2", group="therapy-wording"),
                benefit("therapy-out", "Out-of-network therapy", ["97110"], "out", coins=5000, clause="T3")],
               [("T1", "Therapy schedule: in-network therapeutic exercise (97110) is subject to deductible then 20% coinsurance."),
                ("T2", "Therapy endorsement: in-network therapeutic exercise (97110) has a $40 copay and waived deductible; no coinsurance. The document does not state whether this endorsement supersedes T1: both interpretations require review."),
                ("T3", "Out-of-network therapeutic exercise (97110): deductible then 50% coinsurance, plus permitted balance billing.")])
    make_case("mosaic-therapy", "When the policy needs clarification", "Compare conflicting therapy clauses; resolve unknown network, allowance and prior spending.", p, "CLAIM-SYN-M02",
              {"in": {"deductible_paid_cents": None, "oop_paid_cents": None}, "out": {"deductible_paid_cents": 0, "oop_paid_cents": 0}},
              [line("T1", "97110", "Synthetic therapeutic exercise (one unit)", 30000, 20000, coins=4000, paid=16000, adjustment=10000, net="unknown", provider="PROVIDER-SYN-004")],
              [(10000, 0, 4000)], format="mosaic-ledger-v1", missing=True)


if __name__ == "__main__":
    main()
