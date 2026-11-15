"""Canonical executable meanings; labels are presentation, never identities."""
from dataclasses import replace


def normalize_benefits(benefits):
    canonical, aliases = [], {}
    meanings = {}
    for b in benefits:
        key = (b.network, tuple(sorted(b.codes)), b.service_category, tuple(sorted(set(b.conditions))),
               b.covered, b.deductible_applies, b.copay_cents, b.coinsurance_bps)
        if key in meanings:
            index = meanings[key]; kept = canonical[index]
            canonical[index] = replace(kept, clause_ids=list(dict.fromkeys([*kept.clause_ids, *b.clause_ids])))
            aliases[b.id] = kept.id
        else:
            meanings[key] = len(canonical); canonical.append(b); aliases[b.id] = b.id
    # Connected, overlapping source selectors become explicit alternatives.
    components = []
    for i, b in enumerate(canonical):
        joined = [c for c in components if any(
            canonical[j].network == b.network and
            ((b.codes and set(b.codes) & set(canonical[j].codes)) or
             (b.service_category is not None and b.service_category == canonical[j].service_category))
            for j in c)]
        component = {i}
        for c in joined:
            component.update(c); components.remove(c)
        components.append(component)
    for n, component in enumerate(components, 1):
        if len(component) < 2:
            i = next(iter(component)); canonical[i] = replace(canonical[i], ambiguity_group='')
            continue
        for reading, i in enumerate(sorted(component), 1):
            b = canonical[i]
            duplicate_label = sum(canonical[j].label == b.label for j in component) > 1
            canonical[i] = replace(b, ambiguity_group=f'source-alternatives-{n}',
                label=f'{b.label} (reading {reading})' if duplicate_label else b.label)
    return canonical, aliases


def normalize_case(case):
    benefits, _ = normalize_benefits(case.policy.benefits)
    return replace(case, policy=replace(case.policy, benefits=benefits))
