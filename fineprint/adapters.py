"""Fictional insurer adapters. Normalize presentation, never adjudicate here."""

import csv
import io
import json
from decimal import Decimal, InvalidOperation
from typing import Protocol

from .models import Claim, ModelError, decode


def dollars(text: str) -> int:
    try:
        value = Decimal(text)
        if not value.is_finite() or value < 0 or value * 100 != (value * 100).to_integral_value():
            raise ValueError()
        return int(value * 100)
    except (InvalidOperation, ValueError) as exc:
        raise ModelError(f"Invalid exact dollar amount: {text!r}") from exc


class ClaimAdapter(Protocol):
    def __call__(self, document: str, context: dict) -> Claim: ...


def aurora_csv(document: str, context: dict) -> Claim:
    lines = []
    for row in csv.DictReader(io.StringIO(document)):
        lines.append({"id": row["line_ref"], "provider_id": row["provider"],
                      "service_date": row["service_day"], "code": row["cpt_hcpcs"],
                      "description": row["description"], "network": row["network"],
                      "billed_cents": dollars(row["charge"]),
                      "insurer": {f"{key}_cents": dollars(row[column]) for key, column in {
                          "allowed": "allowed", "deductible": "deductible", "copay": "copay",
                          "coinsurance": "coinsurance", "noncovered": "noncovered", "balance": "balance",
                          "insurer_paid": "plan_paid", "adjustment": "adjustment"}.items()}})
    return decode(Claim, {**context, "lines": lines}, "claim")


def mosaic_ledger(document: str, context: dict) -> Claim:
    source = json.loads(document)
    lines = []
    for row in source["services"]:
        sharing = row["memberShare"]
        lines.append({"id": row["ref"], "provider_id": row["facility"], "service_date": row["date"],
                      "code": row["procedure"], "description": row["label"], "network": row["participation"],
                      "billed_cents": row["submittedCents"],
                      "insurer": {"allowed_cents": row["recognizedCents"], "deductible_cents": sharing["deductible"],
                                  "copay_cents": sharing["fixed"], "coinsurance_cents": sharing["percentage"],
                                  "noncovered_cents": sharing["excluded"], "balance_cents": sharing["excess"],
                                  "insurer_paid_cents": row["planRemittanceCents"], "adjustment_cents": row["writeOffCents"]}})
    return decode(Claim, {"id": source["claimReference"], "policy_id": source["planRef"],
                          "member_id": source["subscriberRef"], "accumulators": source["priorSpend"], "lines": lines}, "claim")


CLAIM_ADAPTERS: dict[str, ClaimAdapter] = {"aurora-csv-v1": aurora_csv, "mosaic-ledger-v1": mosaic_ledger}


def bill_csv(document: str, context: dict) -> dict:
    lines = []
    for row in csv.DictReader(io.StringIO(document)):
        lines.append({key: row[key] for key in ("id", "claim_line_id", "provider_id", "service_date", "code")}
                     | {f"{key}_cents": dollars(row[key]) for key in
                        ("charged", "insurance_paid", "adjustment", "patient_paid", "balance_due")})
    return {**context, "lines": lines}
