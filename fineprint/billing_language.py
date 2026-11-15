"""Recognize explicit excess-billing evidence without inferring protections.

This only validates an extracted boolean against its cited text. It neither
selects benefits nor decides whether a legal billing protection applies.
"""
import re


_TOPIC = r"(?:balance[\s-]+bill(?:ing|ed|s)?|excess\s+(?:balance\s+)?(?:bill(?:ing|ed|s)?|charges))"
_NETWORK = re.compile(r"\b(?:(out[\s-]*(?:of[\s-]*)?network|non[\s-]*participating)|(in[\s-]*network|participating))\b")


def _networks(text):
    return {"out" if match[1] else "in" for match in _NETWORK.finditer(text)}


def _cell_value(text):
    text = text.strip().rstrip(".")
    if re.fullmatch(r"(?:no|prohibited|not (?:allowed|permitted)|forbidden)", text):
        return False
    if re.fullmatch(r"(?:yes|allowed|permitted)", text):
        return True
    return None


def explicit_balance_values(quotes, network=None):
    """Return supported values, respecting network scope and table columns.

    Conflicting evidence yields both values, so callers cannot silently select
    a favorable reading. A generic benefit or network heading proves nothing.
    """
    values = set()
    rows = []
    for quote in quotes:
        for line in quote.splitlines():
            if "|" in line:
                rows.append([cell.strip().casefold() for cell in line.strip().strip("|").split("|")])
    # Row-based and transposed SBC tables; require an explicit billing heading.
    for i, header in enumerate(rows):
        for j, heading in enumerate(header):
            if not re.search(_TOPIC, heading):
                continue
            for row in rows[i + 1:]:
                if len(row) != len(header):
                    continue
                scope = _networks(row[0])
                if not scope or network is not None and scope != {network}:
                    continue
                value = _cell_value(row[j])
                if value is not None:
                    values.add(value)
        for j, heading in enumerate(header):
            scope = _networks(heading)
            if not scope or network is not None and scope != {network}:
                continue
            for row in rows[i + 1:]:
                if len(row) == len(header) and re.search(_TOPIC, row[0]):
                    value = _cell_value(row[j])
                    if value is not None:
                        values.add(value)
    for quote in quotes:
        # Keep sentence boundaries: an unrelated "no" must not negate a
        # permission later in a paragraph, or a different network's rule.
        text = " ".join(quote.casefold().replace("\u2011", "-").split())
        if "|" in text:
            continue  # evaluated using table headings, never flattened cells
        scope = set()
        billing_question = False
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            named = _networks(sentence)
            if len(named) > 1:
                continue  # cannot assign a mixed-network sentence by proximity
            if named:
                scope = named
            if "?" in sentence:
                billing_question = bool(re.search(_TOPIC, sentence))
                continue
            if network is not None and scope and scope != {network}:
                continue
            if billing_question and named:
                answer = re.fullmatch(r"(?:non[\s-]*participating|participating|(?:in|out)[\s-]*(?:of[\s-]*)?network)\s+providers?\s+(may not|cannot|can't|may|can)\.?", sentence)
                if answer:
                    values.add(answer[1] in ("may", "can"))
                    continue
            if not re.search(_TOPIC, sentence):
                continue
            negative = (re.search(r"\b(?:no|never|cannot|can't|may not|must not|not permitted to|not allowed to|prohibited from|forbidden from)\s+(?:[a-z-]+\s+){0,4}" + _TOPIC, sentence)
                        or re.search(_TOPIC + r"\s*(?:is\s+|are\s+|=\s*|:\s*)?(?:prohibited|forbidden|not (?:permitted|allowed)|no)\b", sentence))
            positive = (re.search(r"\b(?:may|can|permitted to|allowed to)\s+(?:[a-z-]+\s+){0,3}" + _TOPIC, sentence)
                        or re.search(_TOPIC + r"\s*(?:is\s+|are\s+|=\s*|:\s*)?(?:permitted|allowed|yes)\b", sentence))
            if negative:
                values.add(False)
            elif positive:
                values.add(True)
    return values
