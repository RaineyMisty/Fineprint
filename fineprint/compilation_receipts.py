"""Signed receipts let /check reuse /compile without another LLM call.

No policies, claims, or API keys are stored. The signing key must be shared by every
server replica behind a load balancer, otherwise /compile and /check can land on
different replicas and the receipt fails. It comes from FINEPRINT_RECEIPT_KEY, else is
derived from DEEPSEEK_API_KEY (identical on every replica), else is process-local.
"""
import hashlib
import hmac
import json
import os
import secrets

from .compiler import Compilation, validate_output
from .models import ModelError, decode



def _load_key():
    explicit = os.environ.get('FINEPRINT_RECEIPT_KEY')
    if explicit:
        return hashlib.sha256(b'fineprint-receipt-v1:' + explicit.encode()).digest()
    shared = os.environ.get('DEEPSEEK_API_KEY')
    if shared:
        return hmac.new(shared.encode(), b'fineprint-compilation-receipt-v1', hashlib.sha256).digest()
    return secrets.token_bytes(32)


_KEY = _load_key()


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
