"""Author synthetic benchmark fixtures without importing compiler or engine.

Held-out formats were authored after the compiler freeze commit bd9f7ab. Gold is
written from explicit contractual terms and hand-worked cents, never engine output.
This is an author-created format holdout, not a blinded evaluation.
"""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'fineprint' / 'benchmark'
SAMPLES = ROOT / 'fineprint' / 'samples'


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def benefit(id, code, net, *, copay=0, coin=0, ded=False):
    return dict(id=id, label=f'Synthetic {code} {net}', codes=[code], network=net, covered=True,
                deductible_applies=ded, copay_cents=copay, coinsurance_bps=coin, clause_ids=[id, 'ORDER'], ambiguity_group='')


def line_gold(id, net, allowed, ded=0, copay=0, coin=0, noncovered=0, balance=0, insurer=0, adjustment=0):
    return dict(claim_line_id=id, network=net, allowed_cents=allowed, deductible_cents=ded, copay_cents=copay,
                coinsurance_cents=coin, noncovered_cents=noncovered, balance_cents=balance,
                insurer_paid_cents=insurer, adjustment_cents=adjustment,
                patient_cents=ded+copay+coin+noncovered+balance)


def sample_spec(id, gold, *, discrepancy=True, conditional=False, count=1):
    return dict(id=id, policy=id, sample=id, gold_outcomes=gold, gold_scenario_count=count,
                gold_discrepancy=None if conditional else discrepancy, gold_conditional=conditional)


def new_case(id, policy, code, allowed, eob_patient, *, net='in', ded_paid=0, oop_paid=0):
    # These EOBs deliberately report a fixed patient amount; Fineprint never uses
    # the components below as its independent answer.
    charged = allowed + 10000
    line = dict(id='L1', provider_id='PROVIDER-SYN-BENCH', service_date='2026-06-01', code=code,
                description='SYNTHETIC benchmark service', network=net, billed_cents=charged,
                insurer=dict(allowed_cents=allowed, deductible_cents=0, copay_cents=eob_patient,
                             coinsurance_cents=0, noncovered_cents=0, balance_cents=0,
                             insurer_paid_cents=allowed-eob_patient, adjustment_cents=10000))
    return dict(schema_version='1.0', id=id, title='SYNTHETIC ' + id, synthetic=True, policy=policy,
                claim=dict(id='CLAIM-'+id, policy_id=policy['id'], member_id=policy['member_id'],
                           accumulators={n:dict(deductible_paid_cents=ded_paid if n=='in' else 0,
                                                oop_paid_cents=oop_paid if n=='in' else 0) for n in ('in','out')}, lines=[line]),
                bill=dict(id='BILL-'+id, claim_id='CLAIM-'+id, member_id=policy['member_id'], lines=[dict(
                    id='BL1', claim_line_id='L1', provider_id=line['provider_id'], service_date=line['service_date'],
                    code=code, charged_cents=charged, insurance_paid_cents=allowed-eob_patient,
                    adjustment_cents=10000, patient_paid_cents=0, balance_due_cents=eob_patient)]),
                allowed_evidence={'L1':dict(allowed_cents=allowed, source='contract', reference='SYNTHETIC independently supplied rate exhibit')})


def main():
    for folder in ('policies', 'gold', 'cases'):
        (DEST / folder).mkdir(parents=True, exist_ok=True)
    policies=[]
    for id in ('aurora-imaging','mosaic-oop','mosaic-therapy'):
        policies.append(dict(id=id, split='seen', document=f'../samples/{id}/policy.md', gold=f'../samples/{id}/policy.json'))
    cases=[sample_spec('aurora-imaging', [[line_gold('A1','in',15000,copay=2500,insurer=12500,adjustment=9000),
                                         line_gold('A2','in',100000,ded=20000,coin=16000,insurer=64000,adjustment=60000)]]),
           sample_spec('mosaic-oop', [[line_gold('M1','in',100000,coin=5000,insurer=95000,adjustment=80000),
                                    line_gold('M2','in',0,noncovered=30000),
                                    line_gold('M3','out',40000,ded=40000,balance=25000)]]),
           sample_spec('mosaic-therapy', [[g] for g in [
               line_gold('T1','in',0,adjustment=30000),
               line_gold('T1','in',30000,ded=30000),
               line_gold('T1','in',30000,insurer=30000),
               line_gold('T1','in',30000,coin=6000,insurer=24000),
               line_gold('T1','in',30000,copay=4000,insurer=26000),
               line_gold('T1','out',0,balance=30000),
               line_gold('T1','out',30000,ded=30000)]], conditional=True,count=32)]
    aurora=json.loads((SAMPLES/'aurora-imaging/policy.json').read_text())
    for id, code, allowed, patient, gold, discrepancy in [
        ('aurora-correct','99213',15000,2500,line_gold('L1','in',15000,copay=2500,insurer=12500,adjustment=10000),False),
        ('aurora-coinsurance-on-copay','99213',15000,5000,line_gold('L1','in',15000,copay=2500,insurer=12500,adjustment=10000),True),
        ('aurora-wrong-network','70551',100000,40000,line_gold('L1','in',100000,coin=20000,insurer=80000,adjustment=10000),True)]:
        data=new_case(id,aurora,code,allowed,patient,ded_paid=100000,oop_paid=100000)
        if id=='aurora-wrong-network':
            # Verified participation is in-network; insurer used the 40% out tier.
            data['claim']['lines'][0]['insurer'].update(copay_cents=0,coinsurance_cents=40000)
        if id=='aurora-coinsurance-on-copay':
            data['claim']['lines'][0]['insurer'].update(copay_cents=2500,coinsurance_cents=2500)
        write(DEST/f'cases/{id}.json',data)
        cases.append(dict(id=id,policy='aurora-imaging',case=f'cases/{id}.json',gold_outcomes=[[gold]],gold_scenario_count=1,gold_discrepancy=discrepancy,gold_conditional=False))

    # HELD OUT: author these only after the compiler freeze. No parser edits based
    # on their contents/results. Cedar uses compact tagged schedule paragraphs.
    common=json.loads((SAMPLES/'mosaic-oop/policy.json').read_text())
    cedar=deepcopy(common)
    cedar.update(id='POL-SYN-C01',member_id='MEMBER-SYN-C01',insurer='Cedar Assurance (fictional)',name='Synthetic Everyday PPO')
    cedar['benefits']=[benefit('P1','99395','in'),benefit('S1','99214','in',copay=3500),benefit('S2','99214','out',ded=True,coin=5000)]
    cedar['clauses']=deepcopy(common['clauses'][:6])+[
        dict(id='P1',text='In-network preventive examination (99395): no charge; deductible does not apply.',location='Schedule P1'),
        dict(id='S1',text='In-network specialist consultation (99214): $35 copay only; deductible waived; no coinsurance.',location='Schedule S1'),
        dict(id='S2',text='Out-of-network specialist consultation (99214): deductible then 50% member coinsurance.',location='Schedule S2'),
        deepcopy(common['clauses'][-1])]
    header=f"# {cedar['insurer']} — {cedar['name']}\n\nSYNTHETIC FICTIONAL benchmark; no real people or contracts.\n\nPolicy: {cedar['id']} | Member: {cedar['member_id']} | Period: 2026-01-01 to 2026-12-31 | USD\n\n## Member cost schedule: compact reference cards\n\n"
    (DEST/'policies/cedar.md').write_text(header+'\n\n'.join(f"[{c['id']}] {c['text']}" for c in cedar['clauses'])+'\n')
    write(DEST/'gold/cedar.json',cedar)
    policies.append(dict(id='cedar',split='held_out',document='policies/cedar.md',gold='gold/cedar.json'))
    for id, code, allowed, patient, correct in [('cedar-preventive-charged','99395',20000,2500,0),('cedar-correct-specialist','99214',20000,3500,3500)]:
        write(DEST/f'cases/{id}.json',new_case(id,cedar,code,allowed,patient))
        cases.append(dict(id=id,policy='cedar',case=f'cases/{id}.json',gold_outcomes=[[line_gold('L1','in',allowed,copay=correct,insurer=allowed-correct,adjustment=10000)]],gold_scenario_count=1,gold_discrepancy=patient!=correct,gold_conditional=False))

    # Harbor is a transposed SBC matrix. Its semantics are explicit but its layout
    # was never used to develop the frozen parser. A failure must remain a failure.
    harbor=deepcopy(cedar)
    harbor.update(id='POL-SYN-H01',member_id='MEMBER-SYN-H01',insurer='Harbor Benefits Cooperative (fictional)',name='Synthetic Matrix Plan')
    harbor['benefits']=[benefit('H1','70551','in',ded=True,coin=2000),benefit('H2','99213','in',copay=2000)]
    harbor['clauses']=deepcopy(common['clauses'][:6])+[
        dict(id='H1',text='Diagnostic imaging (70551): deductible then 20% member coinsurance in network.',location='Benefits matrix'),
        dict(id='H2',text='Office visit (99213): $20 copay; deductible waived; no coinsurance in network.',location='Benefits matrix'),deepcopy(common['clauses'][-1])]
    text=f"# {harbor['insurer']} — {harbor['name']}\n\nSYNTHETIC / FICTIONAL only.\n\nPolicy: {harbor['id']} | Member: {harbor['member_id']} | Period: 2026-01-01 to 2026-12-31 | USD\n\n## Financial protection matrix\n\n| Individual annual terms | Participating | Nonparticipating |\n| --- | --- | --- |\n| Deductible | $500 | $1,000 |\n| Out-of-pocket maximum | $1,500 | $3,000 |\n\nParticipating means in-network; nonparticipating means out-of-network. Apply the deductible to covered allowance before copay and coinsurance unless waived. Separate network pools. Covered deductible, copay and coinsurance count toward the maximum; excluded services and permitted balance bills do not. Participating providers write off excess charges; nonparticipating providers may balance bill above the allowance outside OOP.\n\n## What you pay (individual annual coverage)\n\n| Service and billing code | Participating member share |\n| --- | --- |\n| Diagnostic imaging — 70551 | Deductible then 20% coinsurance |\n| Office visit — 99213 | $20 copay; deductible waived; no coinsurance |\n\n[ORDER] {common['clauses'][-1]['text']}\n"
    (DEST/'policies/harbor.md').write_text(text)
    write(DEST/'gold/harbor.json',harbor)
    policies.append(dict(id='harbor',split='held_out',document='policies/harbor.md',gold='gold/harbor.json'))
    for id,code,allowed,patient,correct,ded_paid,oop_paid in [('harbor-oop-ignored','70551',100000,20000,5000,50000,145000),('harbor-correct-office','99213',15000,2000,2000,0,0)]:
        write(DEST/f'cases/{id}.json',new_case(id,harbor,code,allowed,patient,ded_paid=ded_paid,oop_paid=oop_paid))
        gold=line_gold('L1','in',allowed,copay=correct if code=='99213' else 0,coin=correct if code=='70551' else 0,insurer=allowed-correct,adjustment=10000)
        cases.append(dict(id=id,policy='harbor',case=f'cases/{id}.json',gold_outcomes=[[gold]],gold_scenario_count=1,gold_discrepancy=patient!=correct,gold_conditional=False))
    write(DEST/'manifest.json',dict(synthetic=True,description='Author-created format holdout, not blinded; all data fictional',
          parser_freeze_commit='bd9f7ab',parser_sha256=hashlib.sha256((ROOT/'fineprint/compiler.py').read_bytes()).hexdigest(),policies=policies,cases=cases))


if __name__=='__main__': main()
