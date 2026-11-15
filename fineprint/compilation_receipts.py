"""Process-local signed receipts let /check reuse /compile without another LLM call.

No policies, claims, or API keys are stored. A restart invalidates old receipts.
"""
import hashlib
import hmac
import json
import secrets

from .compiler import Compilation, validate_output
from .models import ModelError, decode

_KEY = secrets.token_bytes(32)


def sign(compilation):
    body = json.dumps(compilation, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hmac.new(_KEY, body, hashlib.sha256).hexdigest()


def verify(value, receipt, document):
    if not isinstance(value, dict) or not isinstance(receipt, str) or not hmac.compare_digest(sign(value), receipt):
        raise ModelError('Compilation receipt is invalid or expired; compile this policy again.')
    compiled = decode(Compilation, value, 'compilation')
    if hashlib.sha256(document.encode()).hexdigest() != compiled.source_sha256:
        raise ModelError('Policy text changed after compilation; compile it again.')
    validate_output(value['output'], document, compiled.source_document_id)
    return compiled
