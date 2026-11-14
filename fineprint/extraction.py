"""Replaceable clause extraction boundary. No network calls in the offline provider."""

import json
from dataclasses import dataclass
from typing import Callable, Protocol

from .models import ModelError, Policy, decode


@dataclass(frozen=True)
class ExtractionResult:
    policy: Policy
    provider: str
    warnings: list[str]
    review_required: bool


class PolicyExtractor(Protocol):
    def extract(self, document: str) -> ExtractionResult: ...


class StructuredPolicyExtractor:
    """Offline fallback accepts curated policy JSON, never guesses prose semantics."""

    def extract(self, document: str) -> ExtractionResult:
        try:
            value = json.loads(document)
        except json.JSONDecodeError as exc:
            raise ModelError("Offline extraction requires structured policy JSON. Transcribe clauses with source locations; arbitrary PDFs/prose require a reviewed provider.") from exc
        return ExtractionResult(decode(Policy, value, "policy"), "structured-offline", [], False)


class ProviderPolicyExtractor:
    """Inject any LLM or document service as a callable: text -> policy JSON dict.

    Provider transport, credentials and consent belong to the caller. Output is
    schema-checked here, then semantically checked by validation before evaluation.
    Human approval/provenance storage must be added before production ingestion.
    """

    def __init__(self, provider: Callable[[str], dict], name: str):
        self.provider, self.name = provider, name

    def extract(self, document: str) -> ExtractionResult:
        policy = decode(Policy, self.provider(document), "policy")
        return ExtractionResult(policy, self.name,
                                ["Provider-generated rules require human verification against the source clauses."], True)
