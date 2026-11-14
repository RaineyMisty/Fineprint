"""Versioned, provider-neutral domain model and strict JSON boundary.

Money uses nonnegative integer USD cents; coinsurance uses integer basis points.
No binary floating point enters the calculation engine.
"""

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date
from types import UnionType
from typing import Literal, Union, get_args, get_origin, get_type_hints

Network = Literal["in", "out"]


@dataclass(frozen=True)
class Clause:
    id: str
    text: str
    location: str


@dataclass(frozen=True)
class NetworkTerms:
    deductible_cents: int
    oop_max_cents: int
    balance_billing: bool
    deductible_clause: str
    oop_clause: str
    network_clause: str


@dataclass(frozen=True)
class Benefit:
    id: str
    label: str
    codes: list[str]
    network: Network
    covered: bool
    deductible_applies: bool
    copay_cents: int
    coinsurance_bps: int
    clause_ids: list[str]
    # Multiple benefits for a code/network MUST share a nonempty ambiguity group.
    ambiguity_group: str


@dataclass(frozen=True)
class Policy:
    id: str
    insurer: str
    name: str
    member_id: str
    effective_from: str
    effective_to: str
    currency: Literal["USD"]
    networks: dict[str, NetworkTerms]
    benefits: list[Benefit]
    clauses: list[Clause]


@dataclass(frozen=True)
class Accumulator:
    # Immediately BEFORE this claim; network-specific individual annual pools.
    deductible_paid_cents: int | None
    oop_paid_cents: int | None


@dataclass(frozen=True)
class Adjudication:
    allowed_cents: int
    deductible_cents: int
    copay_cents: int
    coinsurance_cents: int
    noncovered_cents: int
    balance_cents: int
    insurer_paid_cents: int
    adjustment_cents: int

    @property
    def patient_cents(self) -> int:
        return (self.deductible_cents + self.copay_cents + self.coinsurance_cents
                + self.noncovered_cents + self.balance_cents)


@dataclass(frozen=True)
class ClaimLine:
    id: str
    provider_id: str
    service_date: str
    code: str
    description: str
    network: Literal["in", "out", "unknown"]
    billed_cents: int
    insurer: Adjudication


@dataclass(frozen=True)
class Claim:
    id: str
    policy_id: str
    member_id: str
    accumulators: dict[str, Accumulator]
    lines: list[ClaimLine]


@dataclass(frozen=True)
class BillLine:
    id: str
    claim_line_id: str
    provider_id: str
    service_date: str
    code: str
    charged_cents: int
    insurance_paid_cents: int
    adjustment_cents: int
    patient_paid_cents: int
    balance_due_cents: int

    @property
    def patient_total_cents(self) -> int:
        return self.patient_paid_cents + self.balance_due_cents


@dataclass(frozen=True)
class Bill:
    id: str
    claim_id: str
    member_id: str
    lines: list[BillLine]


@dataclass(frozen=True)
class AllowedEvidence:
    # Separate from the EOB so Fineprint need not trust the adjudicated allowance.
    allowed_cents: int | None
    source: Literal["contract", "eob", "unknown"]
    reference: str


@dataclass(frozen=True)
class Case:
    schema_version: Literal["1.0"]
    id: str
    title: str
    synthetic: bool
    policy: Policy
    claim: Claim
    bill: Bill
    allowed_evidence: dict[str, AllowedEvidence]


class ModelError(ValueError):
    """Input does not satisfy the structural schema."""


def decode(cls, value, path="case"):
    """Strict recursive decoder: no coercion, ignored keys, floats, or bool-as-int."""
    origin, args = get_origin(cls), get_args(cls)
    if origin in (Union, UnionType):
        for option in args:
            try:
                return decode(option, value, path)
            except ModelError:
                pass
        raise ModelError(f"{path}: expected {' or '.join(str(a) for a in args)}")
    if origin is Literal:
        if value not in args or type(value) is not type(args[0]):
            raise ModelError(f"{path}: expected one of {args}")
        return value
    if is_dataclass(cls):
        if not isinstance(value, dict):
            raise ModelError(f"{path}: expected object")
        names = {f.name for f in fields(cls)}
        if set(value) != names:
            raise ModelError(f"{path}: missing {sorted(names - set(value))}; unknown {sorted(set(value) - names)}")
        hints = get_type_hints(cls)
        result = {k: decode(hints[k], v, f"{path}.{k}") for k, v in value.items()}
        for key, item in result.items():
            if key.endswith("_cents") and item is not None and not 0 <= item <= 10**12:
                raise ModelError(f"{path}.{key}: cents must be between 0 and 10^12")
            if key == "coinsurance_bps" and not 0 <= item <= 10000:
                raise ModelError(f"{path}.{key}: basis points must be between 0 and 10000")
            if key in ("service_date", "effective_from", "effective_to"):
                try:
                    if date.fromisoformat(item).isoformat() != item:
                        raise ValueError()
                except ValueError as exc:
                    raise ModelError(f"{path}.{key}: expected YYYY-MM-DD") from exc
        return cls(**result)
    if origin is list:
        if not isinstance(value, list):
            raise ModelError(f"{path}: expected array")
        return [decode(args[0], v, f"{path}[{i}]") for i, v in enumerate(value)]
    if origin is dict:
        if not isinstance(value, dict):
            raise ModelError(f"{path}: expected object")
        return {decode(args[0], k, path): decode(args[1], v, f"{path}.{k}") for k, v in value.items()}
    if cls is type(None):
        if value is not None:
            raise ModelError(f"{path}: expected null")
    elif type(value) is not cls:
        raise ModelError(f"{path}: expected {cls.__name__}")
    elif cls is str and not value.strip():
        # Empty ambiguity_group is the one intentionally empty field.
        if not path.endswith(".ambiguity_group"):
            raise ModelError(f"{path}: text must not be empty")
    return value


def case_from_dict(data: dict) -> Case:
    return decode(Case, data)


def to_dict(value):
    return asdict(value)
