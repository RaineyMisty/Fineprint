"""Bound provider input using source sections, without gold or insurer-specific rules."""
import re


def select_sections(document, *, threshold=24000, budget=60000):
    """Return unchanged slices and an auditable selection manifest (no private text).

    SBC question/event tables and network/limit notes have priority. Long EOCs
    use ranked cost-sharing pages; omitted material is explicitly unresolved.
    Coverage illustrations are excluded from rule extraction, including their
    patient totals. All returned quotes are later located in the FULL source.
    """
    ranges = []
    if len(document) <= threshold:
        ranges = [(0, len(document), 1)]
    else:
        pages = []
        offset = 0
        for page, contents in enumerate(document.split("\f"), 1):
            # Non-paginated long uploads use bounded sections as well.
            for start in range(0, len(contents), 6000):
                text = contents[start:start + 6000]
                lower = text.lower()
                # Exclude illustrations, even when "deductible" appears often.
                illustration = any(term in lower for term in (
                    "about these coverage examples", "about these coverage", "managing joe", "peg is having", "mia's simple"))
                score = (100 * bool(re.search(r"important\s+questions|common\s+medical\s+event", lower))
                         + 120 * bool(re.search(r"(?:summary|schedule)\s+of\s+(?:benefits|cost\s+sharing)|cost\s+shar(?:e|ing)\s+summary", lower))
                         + 80 * bool(re.search(r"deductibles\s+and\s+out-of-pocket\s+maximums", lower))
                         + 40 * bool(re.search(r"balance\s+billing|participating\s+providers|plan\s+providers", lower))
                         + 8 * sum(term in lower for term in ("deductible", "out-of-pocket", "network", "balance bill"))
                         + min(30, 3 * len(re.findall(r"\$\s*[\d,]+", text))))
                # Contents/index pages cannot establish executable terms.
                if len(re.findall(r"\.{4,}", text)) > 5:
                    score = 0
                if not illustration and text.strip():
                    pages.append((score, offset + start, offset + start + len(text), page))
            offset += len(contents) + 1
        selected, used = [], 0
        # Keep identifying context, then select cost-sharing sections by rank.
        for score, start, end, page in sorted(pages, key=lambda p: (p[1] != 0, -p[0], p[1])):
            if (score > 0 or start == 0) and used + end - start <= budget:
                selected.append((start, end, page))
                used += end - start
        ranges = sorted(selected)
    selected_chars = sum(end - start for start, end, _ in ranges)
    omitted = selected_chars < len(document.replace("\f", ""))
    text = "\n".join(document[start:end] for start, end, _ in ranges)
    return text, dict(method="ranked source sections" if len(document) > threshold else "complete source",
                      source_characters=len(document), selected_characters=selected_chars,
                      omitted=omitted, selected_ranges=[dict(start=s, end=e, page=p) for s, e, p in ranges],
                      evidence_validation="Full original source; whitespace normalization only")


def numbered_source_lines(document, selection):
    """Number original physical lines so providers can cite without transcribing tables."""
    result, offset = [], 0
    ranges = selection["selected_ranges"]
    for number, line in enumerate(document.splitlines(keepends=True), 1):
        end = offset + len(line)
        if line.strip() and any(offset < r["end"] and end > r["start"] for r in ranges):
            result.append(dict(line=number, text=line.rstrip()))
        offset = end
    return result
