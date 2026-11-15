"""Offline-first, end-to-end evaluation. Gold is never an input to compilation.

Run: python3 -m fineprint.eval [--provider fallback] [--output-dir reports]
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .compiler import get_compiler, rule_paths
from .extraction import StructuredPolicyExtractor
from .models import Policy, case_from_dict, decode
from .repository import load_case
from .service import analyze

BENCHMARK = Path(__file__).parent / 'benchmark'
MONEY_FIELDS = ('allowed_cents','deductible_cents','copay_cents','coinsurance_cents','noncovered_cents',
                'balance_cents','patient_cents','insurer_paid_cents','adjustment_cents')


def field_facts(policy):
    """Multiset of semantic fields; ignore cosmetic rule IDs, labels and ordering.

    Each service-code/network interpretation contributes five scored fields.
    An overlap's ambiguity is scored as a boolean; arbitrary group names do not
    affect accuracy. Duplicate facts remain counted, so duplicate rules cannot
    inflate precision. Every network contributes three financial fields.
    """
    facts=[]
    for net,t in policy.networks.items():
        for field in ('deductible_cents','oop_max_cents','balance_billing'):
            facts.append(('network',net,field,json.dumps(getattr(t,field))))
    for b in policy.benefits:
        for code in b.codes:
            for field in ('covered','deductible_applies','copay_cents','coinsurance_bps','ambiguous'):
                value=bool(b.ambiguity_group) if field=='ambiguous' else getattr(b,field)
                facts.append(('benefit',code,b.network,field,json.dumps(value)))
    return Counter(facts)


def extraction_counts(predicted, gold):
    p=field_facts(predicted) if predicted else Counter()
    g=field_facts(gold)
    return dict(tp=sum((p & g).values()),fp=sum((p-g).values()),fn=sum((g-p).values()))


def outcome_signature(lines):
    return tuple(sorted((line['claim_line_id'],line['network'],*(line[f] for f in MONEY_FIELDS)) for line in lines))


RECONCILIATION_FIELDS = ('fineprint_patient_cents','eob_patient_cents','bill_patient_cents',
                         'already_paid_cents','bill_balance_due_cents','fineprint_remaining_cents',
                         'potential_refund_cents','potential_overpayment_cents','eob_difference_cents','bill_eob_difference_cents')


def gold_reconciliation(case, lines):
    """Independent bill oracle from authored line liabilities and source payments."""
    liabilities={line['claim_line_id']:line['patient_cents'] for line in lines}
    supported=sum(liabilities.values())
    eob=sum(line.insurer.patient_cents for line in case.claim.lines)
    billed=sum(line.patient_paid_cents+line.balance_due_cents for line in case.bill.lines)
    return dict(fineprint_patient_cents=supported,eob_patient_cents=eob,bill_patient_cents=billed,
                already_paid_cents=sum(line.patient_paid_cents for line in case.bill.lines),
                bill_balance_due_cents=sum(line.balance_due_cents for line in case.bill.lines),
                fineprint_remaining_cents=sum(max(0,liabilities[line.claim_line_id]-line.patient_paid_cents) for line in case.bill.lines),
                potential_refund_cents=sum(max(0,line.patient_paid_cents-liabilities[line.claim_line_id]) for line in case.bill.lines),
                potential_overpayment_cents=max(0,billed-supported),eob_difference_cents=eob-supported,
                bill_eob_difference_cents=billed-eob)


def reconciliation_signature(comparison):
    return tuple(comparison[field] for field in RECONCILIATION_FIELDS)


def ratio(n,d):
    return n/d if d else None


def aggregate(policies, cases):
    tp=sum(p['fields']['tp'] for p in policies)
    fp=sum(p['fields']['fp'] for p in policies)
    fn=sum(p['fields']['fn'] for p in policies)
    labeled=[c for c in cases if c['gold_discrepancy'] is not None]
    dtp=sum(c['predicted_discrepancy'] is True and c['gold_discrepancy'] is True for c in labeled)
    dfp=sum(c['predicted_discrepancy'] is True and c['gold_discrepancy'] is False for c in labeled)
    dfn=sum(c['predicted_discrepancy'] is not True and c['gold_discrepancy'] is True for c in labeled)
    dtn=sum(c['predicted_discrepancy'] is False and c['gold_discrepancy'] is False for c in labeled)
    emitted=sum(p['emitted_rules'] for p in policies)
    valid=sum(p['traceable_rules'] for p in policies)
    expected=sum(p['gold_rules'] for p in policies)
    exact=sum(c['calculation_exact'] for c in cases)
    success=sum(c['end_to_end_success'] for c in cases)
    return dict(policies=len(policies),cases=len(cases),
                extraction=dict(tp=tp,fp=fp,fn=fn,precision=ratio(tp,tp+fp),recall=ratio(tp,tp+fn)),
                calculation=dict(exact=exact,total=len(cases),accuracy=ratio(exact,len(cases))),
                discrepancy=dict(tp=dtp,fp=dfp,fn=dfn,tn=dtn,precision=ratio(dtp,dtp+dfp),recall=ratio(dtp,dtp+dfn),
                                 false_positive_rate=ratio(dfp,sum(c['gold_discrepancy'] is False for c in labeled)),
                                 labeled_cases=len(labeled),resolved_labeled_cases=sum(c['predicted_discrepancy'] is not None for c in labeled),
                                 abstentions=sum(c['predicted_discrepancy'] is None for c in cases)),
                evidence=dict(valid_rules=valid,emitted_rules=emitted,gold_rules=expected,
                              traceability_rate=ratio(valid,emitted),coverage_rate=ratio(valid,expected)),
                end_to_end=dict(success=success,total=len(cases),rate=ratio(success,len(cases))))


def run_evaluation(compiler=None, root=BENCHMARK, progress=None):
    compiler=compiler or get_compiler()
    manifest=json.loads((root/'manifest.json').read_text())
    policy_rows=[]
    compilations={}
    hasher=hashlib.sha256((root/'manifest.json').read_bytes())
    for spec in manifest['policies']:
        text=(root/spec['document']).read_text(encoding='utf-8')
        gold_text=(root/spec['gold']).read_text(encoding='utf-8')
        hasher.update(text.encode());hasher.update(gold_text.encode())
        error=None
        compilation=None
        started=time.monotonic()
        if progress: progress(f"Compiling {spec['id']} ({spec['split']})")
        try:
            compilation=compiler.compile(text,spec['id'])
            compilations[spec['id']]=compilation
        except (ValueError,TypeError) as exc:
            error=str(exc)
        elapsed=round(time.monotonic()-started,3)
        if progress: progress(f"{spec['id']}: {'validated' if compilation else 'failed'} in {elapsed}s")
        gold=decode(Policy,json.loads(gold_text))
        fields=extraction_counts(compilation.policy if compilation else None,gold)
        # A successfully compiled output has already passed quote/span validation.
        emitted=len(compilation.output.rule_evidence) if compilation else 0
        traceable=sum(bool(r.evidence) and all(e.source_document_id==spec['id'] and 0<=e.start<e.end<=len(text)
                      and text[e.start:e.end]==e.quote for e in r.evidence) for r in compilation.output.rule_evidence) if compilation else 0
        policy_rows.append(dict(id=spec['id'],split=spec['split'],insurer=gold.insurer,fields=fields,
                                extraction_exact=fields['fp']==fields['fn']==0,emitted_rules=emitted,traceable_rules=traceable,
                                gold_rules=len(rule_paths(gold)),error=error,
                                unresolved=compilation.output.unresolved if compilation else [],
                                compilation=compilation.as_dict() if compilation else None,
                                elapsed_seconds=elapsed,
                                backend=compilation.backend if compilation else compiler.name))
    policy_map={p['id']:p for p in policy_rows}
    case_rows=[]
    for spec in manifest['cases']:
        if 'sample' in spec:
            original,_=load_case(spec['sample'],extractor=StructuredPolicyExtractor())
            # Include source adapters' inputs/manifest in the evaluation fingerprint.
            sample_dir=Path(__file__).parent/'samples'/spec['sample']
            for path in sorted(sample_dir.iterdir()):
                hasher.update(path.read_bytes())
        else:
            raw=(root/spec['case']).read_bytes();hasher.update(raw)
            original=case_from_dict(json.loads(raw))
        compilation=compilations.get(spec['policy'])
        row=policy_map[spec['policy']]
        report=None
        error=row['error']
        if compilation and not compilation.output.unresolved:
            # Authored gold measures the contract formulas independently of a
            # possibly wrong provider bill. Do not let a bill ceiling hide an
            # arithmetic error. Patient-facing /check remains document-bounded.
            report=analyze(replace(original,policy=compilation.policy), policy_audit=True)
            if report['status']=='blocked':error=report['blocked_reason']
        elif compilation:
            error='Unresolved policy clauses: '+'; '.join(compilation.output.unresolved)
        scenarios=report['scenarios'] if report else []
        predicted={outcome_signature(s['lines']) for s in scenarios}
        expected={outcome_signature(lines) for lines in spec['gold_outcomes']}
        conditional=any(s['conditional'] for s in scenarios)
        exact=bool(scenarios) and predicted==expected and len(scenarios)==spec['gold_scenario_count'] and conditional==spec['gold_conditional']
        discrepancy=None
        if scenarios and not conditional:
            discrepancy=any(line['eob_difference_cents']!=0 for line in report['comparisons'][0]['lines'])
        decision_correct=(bool(scenarios) and conditional) if spec['gold_discrepancy'] is None else discrepancy is spec['gold_discrepancy']
        actual_reconciliations={reconciliation_signature(c) for c in report['comparisons']} if report else set()
        expected_reconciliations={reconciliation_signature(gold_reconciliation(original,lines)) for lines in spec['gold_outcomes']}
        reconciliation_exact=bool(scenarios) and actual_reconciliations==expected_reconciliations
        success=exact and reconciliation_exact and row['extraction_exact'] and row['traceable_rules']==row['gold_rules'] and decision_correct
        case_rows.append(dict(id=spec['id'],policy=spec['policy'],split=row['split'],calculation_exact=exact,bill_reconciliation_exact=reconciliation_exact,
                              scenario_count=len(scenarios),gold_scenario_count=spec['gold_scenario_count'],
                              actual_patient_totals_cents=sorted({s['patient_cents'] for s in scenarios}),
                              gold_patient_totals_cents=sorted({sum(l['patient_cents'] for l in ls) for ls in spec['gold_outcomes']}),
                              conditional=conditional if scenarios else None,predicted_discrepancy=discrepancy,
                              gold_discrepancy=spec['gold_discrepancy'],end_to_end_success=success,error=error))
    groups={name:aggregate([p for p in policy_rows if name=='all' or p['split']==name],
                           [c for c in case_rows if name=='all' or c['split']==name]) for name in ('seen','held_out','all')}
    try:
        revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):revision='unavailable'
    digest=hashlib.sha256(Path(__file__).with_name('compiler.py').read_bytes()).hexdigest()
    return dict(backend=compiler.name,synthetic=True,generated_at=datetime.now(timezone.utc).isoformat(),
                evaluation_scope="Uncapped policy-formula and reconciliation audit; not the patient-facing document-bounded amount",
                revision=revision,corpus_sha256=hasher.hexdigest(),parser_sha256=digest,
                parser_matches_holdout_freeze=digest==manifest['parser_sha256'],
                model=getattr(compiler,'model',None) if compiler.name!='fallback' else None,
                provider_sha256=hashlib.sha256(Path(__file__).with_name('providers.py').read_bytes()).hexdigest(),
                request_config=compiler.request_config if compiler.name=='deepseek' else None,
                methodology=[
                    'Author-created format holdout; not blinded and not evidence of real-world performance.',
                    'Extraction micro precision/recall: financial fields per network and per code/network interpretation; each policy scored once; IDs/labels/order ignored.',
                    'Calculation exactness: all nine integer-cent fields on every line, network, complete distinct scenario outcome set, scenario count and conditional status.',
                    'Discrepancy: any EOB patient-total difference per line in a nonconditional case. Ambiguous/missing-fact cases abstain and are excluded from labeled precision/recall.',
                    'Compilation failures remain in extraction recall, calculation and end-to-end denominators; positive failures count as false negatives. Negative failures abstain, not true negatives; FPR denominator is all gold-negative cases.',
                    'Traceability is valid spans / emitted rules; coverage also counts missing rules from failed policies.',
                    'End-to-end success requires exact extraction, exact calculations and final bill reconciliation, complete evidence and correct discrepancy decision or justified conditional abstention.',
                    'No live LLM measurement unless backend explicitly names a real configured provider. No LLM used for arithmetic.',
                    'Synthetic compiler outputs, exact source spans and attempts are saved per policy; claim/EOB/bill data and gold policy answers are never sent to the model.',
                    'The shared LLM prompt was not tuned on held-out insurers or their gold answers; validation retries use local validation errors only.'
                ],groups=groups,policies=policy_rows,cases=case_rows)


def markdown_report(report):
    def pct(value):return 'n/a' if value is None else f'{value:.1%}'
    lines=['# Fineprint evaluation', '', f"Backend: **{report['backend']}**. **Synthetic data only**. Generated {report['generated_at']}.",
           '',f"Model: **{report.get('model') or 'none (offline)'}**. Request configuration: `{json.dumps(report.get('request_config'))}`.",
           '',f"Parser matches pre-holdout freeze: **{report['parser_matches_holdout_freeze']}**.",
           '', '| Split | Policies / cases | Extraction P / R | Exact calculation | Discrepancy P / R | FPR | Traceability / coverage | End-to-end |',
           '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for name,g in report['groups'].items():
        lines.append(f"| {name} | {g['policies']} / {g['cases']} | {pct(g['extraction']['precision'])} / {pct(g['extraction']['recall'])} | {g['calculation']['exact']}/{g['calculation']['total']} ({pct(g['calculation']['accuracy'])}) | {pct(g['discrepancy']['precision'])} / {pct(g['discrepancy']['recall'])} | {pct(g['discrepancy']['false_positive_rate'])} | {pct(g['evidence']['traceability_rate'])} / {pct(g['evidence']['coverage_rate'])} | {g['end_to_end']['success']}/{g['end_to_end']['total']} ({pct(g['end_to_end']['rate'])}) |")
    lines+=['','| Case | Split | Fineprint patient totals (USD) | Gold patient totals (USD) | Exact | Discrepancy (predicted / gold) | Success |',
            '| --- | --- | --- | --- | --- | --- | --- |']
    for c in report['cases']:
        def dollars(vals):return ', '.join(f'${v/100:.2f}' for v in vals) or 'blocked'
        lines.append(f"| {c['id']} | {c['split']} | {dollars(c['actual_patient_totals_cents'])} | {dollars(c['gold_patient_totals_cents'])} | {c['calculation_exact']} | {c['predicted_discrepancy']} / {c['gold_discrepancy']} | {c['end_to_end_success']} |")
    lines+=['','Failures / unresolved policies:','']
    lines += [f"- {p['id']}: {p['error'] or '; '.join(p['unresolved'])}" for p in report['policies'] if p['error'] or p['unresolved']]
    lines+=['','Methodology:','']+['- '+m for m in report['methodology']]
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider',choices=['fallback','openai','anthropic','bedrock','deepseek'])
    parser.add_argument('--output-dir',type=Path,default=Path('reports'))
    parser.add_argument('--report-name',default='evaluation',help='Report basename (without extension)')
    args=parser.parse_args()
    if Path(args.report_name).name != args.report_name or args.report_name in ('', '.', '..'):
        parser.error('--report-name must be a simple filename without directories')
    report=run_evaluation(get_compiler(args.provider),progress=lambda message:print(message,file=sys.stderr,flush=True))
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/(args.report_name+'.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    markdown=markdown_report(report)
    (args.output_dir/(args.report_name+'.md')).write_text(markdown,encoding='utf-8')
    print(markdown)


if __name__=='__main__':main()
