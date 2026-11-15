"""BLIND AUTHORING ONLY. Literal hand-worked answers; never imports Fineprint.

All people, insurers, providers and documents are fictional and SYNTHETIC.
Money in the authoring table is USD; serialized money is integer cents.
Do not regenerate after the freeze or after looking at pipeline output.
"""
from decimal import Decimal
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
def cents(value):
    return int(Decimal(str(value)) * 100)

def benefit(code, description, deductible=False, copay=0, coins=20,
            network="in", covered=True):
    return dict(code=code, description=description, network=network,
                covered=covered, deductible=deductible, copay=cents(copay),
                coinsurance_percent=coins)

def line(code, charge, allowed, observed, expected, *, network="in",
         bill=None, paid=0, facts="", actual_code=None):
    # observed = deductible, copay, coinsurance, noncovered, excess balance.
    return dict(code=code, charge=cents(charge), allowed=cents(allowed),
                observed=list(map(cents, observed)), expected=cents(expected),
                network=network, bill=cents(bill) if bill is not None else None,
                paid=cents(paid), facts=facts, actual_code=actual_code)

CASES = []
def case(title, benefits, lines, total, rationale, *, error=False,
         opening=(0,0,0,0), terms=(1000,5000,2000,10000,True), extra=""):
    CASES.append(dict(title=title, benefits=benefits, lines=lines,
                      expected_total=cents(total), rationale=rationale,
                      true_error=error, opening=list(map(cents, opening)),
                      terms=terms, extra=extra))

# 01--16: correct bills. All gold dollar amounts below are hand calculated.
case("Deductible crossing on an MRI", [benefit("70551","MRI",True)],
     [line("70551",1600,1000,(300,0,140,0,0),440)],440,
     "$1,000 - $700 leaves $300 deductible; $300 + 20% of $700 = $440.",
     opening=(700,900,0,0))
case("Primary care with a deductible waiver", [benefit("99213","Office visit",copay=35,coins=0)],
     [line("99213",210,130,(0,35,0,0,0),35)],35,
     "The $35 copay replaces all other cost sharing for this visit.")
case("Routine preventive screening", [benefit("77067","Routine preventive mammogram",coins=0)],
     [line("77067",600,250,(0,0,0,0,0),0)],0,
     "The stipulated screening is preventive, in network, and covered without cost sharing.")
case("Last dollars before the out-of-pocket ceiling", [benefit("72148","Diagnostic MRI",coins=20)],
     [line("72148",2200,1000,(0,0,75,0,0),75)],75,
     "$5,000 - $4,925 = $75 remaining OOP; nominal $200 sharing is capped at $75.",
     opening=(1000,4925,0,0))
case("Permitted out-of-network excess", [benefit("29881","Elective surgery",True,coins=40,network="out")],
     [line("29881",1500,1000,(500,0,200,0,500),1200,network="out")],1200,
     "$500 deductible + 40% of $500 + $500 permitted excess = $1,200.",
     opening=(0,0,1500,1800))
case("Explicit cosmetic exclusion", [benefit("15829","Elective cosmetic procedure",coins=0,covered=False)],
     [line("15829",800,800,(0,0,0,800,0),800)],800,
     "This explicitly excluded service is the patient's full $800 charge; it does not accrue to OOP.")
case("Two dates share one remaining deductible", [benefit("74177","CT scan",True),benefit("76700","Ultrasound",True)],
     [line("74177",1800,1000,(100,0,180,0,0),280),line("76700",700,500,(0,0,100,0,0),100)],380,
     "First line uses $100 remaining deductible and $180 coinsurance; the next uses $100 coinsurance. Total $380.",
     opening=(900,1200,0,0))
case("Two distinct office visits", [benefit("99212","Office visit",copay=25,coins=0)],
     [line("99212",140,90,(0,25,0,0,0),25),line("99212",140,90,(0,25,0,0,0),25)],50,
     "These are separate documented visits on separate dates: two $25 copays, total $50.")
case("Payment already credited correctly", [benefit("99214","Specialist visit",copay=40,coins=0)],
     [line("99214",300,180,(0,40,0,0,0),40,paid=15)],40,
     "Liability is $40. The $15 receipt leaves $25 still owed.")
case("Entire small allowance falls under deductible", [benefit("73610","Diagnostic X-ray",True)],
     [line("73610",420,150,(150,0,0,0,0),150)],150,
     "The $150 allowance is smaller than the $1,000 unmet deductible, so responsibility is $150.")
case("Exclusion survives a satisfied OOP maximum", [benefit("15829","Cosmetic procedure",coins=0,covered=False),benefit("71046","Chest radiograph")],
     [line("15829",1200,1200,(0,0,0,1200,0),1200),line("71046",300,100,(0,0,0,0,0),0)],1200,
     "Covered sharing is $0 because OOP is met; the $1,200 cosmetic exclusion stays outside the cap.",
     opening=(1000,5000,0,0))
case("Half-up cents on a 15 percent benefit", [benefit("93306","Echocardiogram",coins=15)],
     [line("93306",600,333.33,(0,0,50,0,0),50)],50,
     "$333.33 times 15% = $49.9995, rounded half up to $50.00.")
case("Copay precedes coinsurance", [benefit("97110","Therapeutic exercise",copay=20,coins=20)],
     [line("97110",360,200,(0,20,36,0,0),56)],56,
     "$20 copay plus 20% of the remaining $180 = $56.")
case("Out-of-network contract prohibits excess", [benefit("93000","Electrocardiogram",coins=50,network="out")],
     [line("93000",900,400,(0,0,200,0,0),200,network="out")],200,
     "50% of the $400 allowance is $200; this contract expressly prohibits the $500 excess.",
     terms=(1000,5000,2000,10000,False))
case("Sequential lines consume the last OOP dollars", [benefit("80053","Lab panel"),benefit("85025","Blood count")],
     [line("80053",600,400,(0,0,80,0,0),80),line("85025",300,200,(0,0,10,0,0),10)],90,
     "$90 OOP remains: first line owes $80; second owes only the last $10, for $90 total.",
     opening=(1000,4910,0,0))
case("Authorized advanced imaging", [benefit("70553","Authorized MRI")],
     [line("70553",1400,600,(0,0,120,0,0),120,facts="Prior authorization SYN-A16 approved before service.")],120,
     "Authorization is documented. 20% of $600 is $120.",
     extra="Advanced MRI code 70553 requires prior authorization; this member has approval SYN-A16.")

# 17--40: real discrepancies, including underbilling and unsupported relationships.
case("Deductible charged a second time", [benefit("70551","MRI",True)],
     [line("70551",1600,1000,(300,0,140,0,0),360)],360,
     "Only $200 deductible remains: $200 + 20% of $800 = $360, not $440.",
     error=True,opening=(800,1100,0,0))
case("Coinsurance added to an exclusive copay", [benefit("99213","Office visit",copay=30,coins=0)],
     [line("99213",400,300,(0,30,54,0,0),30)],30,
     "The visit owes only $30; adding 20% of $270 invents $54 of liability.",error=True)
case("Preventive mammogram treated as diagnostic", [benefit("77067","Routine screening",coins=0)],
     [line("77067",700,500,(0,0,100,0,0),0)],0,
     "The documented routine preventive service has zero patient sharing, not $100.",error=True)
case("OOP ceiling ignored", [benefit("72148","MRI")],
     [line("72148",1800,1000,(0,0,200,0,0),20)],20,
     "Only $20 remains under the $5,000 maximum, so nominal $200 is capped at $20.",
     error=True,opening=(1000,4980,0,0))
case("Verified participating provider assigned wrong tier", [benefit("74177","CT scan"),benefit("74177","CT scan",coins=40,network="out")],
     [line("74177",1200,400,(0,0,160,0,320),80,facts="Signed participation roster verifies in-network on the service date.")],80,
     "Verified in-network status gives 20% of $400 = $80; neither out-tier sharing nor excess is permitted.",error=True)
case("Excluded procedure incorrectly paid as covered", [benefit("15829","Cosmetic exclusion",coins=0,covered=False)],
     [line("15829",700,700,(0,0,140,0,0),700)],700,
     "Explicit exclusion makes the full $700 payable; $140 is an underbill of $560.",error=True)
case("Prohibited excess balance added to a bill", [benefit("93000","ECG",network="out")],
     [line("93000",900,200,(0,0,40,0,0),40,network="out",bill=700)],40,
     "The plan and provider agreement prohibit excess: 20% of $200 = $40, regardless of the $900 charge.",
     error=True,terms=(1000,5000,2000,10000,False))
case("Emergency surprise bill with stipulated protection", [benefit("99285","Emergency department",True),benefit("99285","Emergency department",True,coins=40,network="out")],
     [line("99285",2200,1200,(0,0,1000,0,0),400,network="out",facts="Emergency at nonparticipating facility; qualifying federal surprise-billing protection stipulated. No notice-and-consent exception.")],400,
     "The supplied protected recognized amount is $1,200. In-network terms apply: $200 remaining deductible plus 20% of $1,000 = $400; no excess.",
     error=True,opening=(800,1200,0,0),extra="For this qualifying protected emergency, apply in-network deductible, coinsurance and OOP to the supplied recognized amount, regardless of provider participation. Excess balance billing is prohibited. These applicability facts are stipulated, not inferred.")
case("Protected ancillary anesthesiologist", [benefit("00840","Anesthesia"),benefit("00840","Anesthesia",coins=40,network="out")],
     [line("00840",1600,600,(0,0,720,0,0),120,network="out",facts="Nonparticipating ancillary anesthesia at participating facility; surprise-billing protection stipulated; no valid waiver.")],120,
     "Protected ancillary anesthesia uses 20% in-network sharing on the supplied $600 recognized amount = $120, with no balance bill.",
     error=True,extra="Qualifying ancillary anesthesia at a participating facility is subject to in-network cost sharing on the recognized amount and no excess billing. For this case legal applicability is stipulated and cannot be waived.")
case("Provider failed to obtain authorization", [benefit("70553","MRI")],
     [line("70553",900,600,(0,0,0,900,0),0,facts="No prior authorization; participating provider's contractual liability; no member undertaking.")],0,
     "The explicit provider-liability clause bars transferring the $900 authorization denial to the patient.",
     error=True,extra="Prior authorization is required for 70553. If the participating provider fails to obtain it, that provider bears the denial and may not bill the member. No member undertaking exists here.")
case("Patient expressly elects nonauthorized service", [benefit("70553","MRI")],
     [line("70553",1400,1000,(0,0,280,0,0),1400,facts="Member requested nonauthorized elective service and signed the plan's valid advance financial undertaking.")],1400,
     "The stipulated valid advance undertaking invokes this plan's exclusion: full $1,400, outside OOP, rather than $280.",
     error=True,extra="MRI requires authorization. A member who voluntarily elects nonauthorized elective MRI after a valid advance financial undertaking owes the full charge as excluded care. This case stipulates that undertaking is valid.")
case("A duplicated office charge", [benefit("99213","Office visit",copay=45,coins=0)],
     [line("99213",180,100,(0,45,0,0,0),45),line("99213",180,100,(0,45,0,0,0),0,facts="Exact duplicate of L01; same encounter, not a second visit or unit.")],45,
     "Only one encounter occurred; one $45 copay is due. The duplicated line has $0 responsibility.",error=True,
     extra="A single encounter may be billed once. A documented exact duplicate has no additional allowance or member liability.")
case("Documented low-complexity visit upcoded", [benefit("99212","Low complexity visit",copay=20,coins=0),benefit("99215","High complexity visit",copay=70,coins=0)],
     [line("99215",350,220,(0,70,0,0,0),20,actual_code="99212",facts="Signed encounter record establishes 99212; provider acknowledges 99215 was a transcription error.")],20,
     "The acknowledged correct service is 99212, which owes $20, not the billed 99215's $70.",error=True,
     extra="If an acknowledged code-entry error is documented, liability follows the actual performed service and its benefit, not the erroneous submitted code.")
case("Panel component unbundled a second time", [benefit("80053","Comprehensive lab panel"),benefit("80051","Electrolyte component")],
     [line("80053",300,100,(0,0,20,0,0),20),line("80051",90,60,(0,0,12,0,0),0,facts="Same specimen and encounter as L01; component expressly included in the panel.")],20,
     "Panel sharing is $20. Its already included electrolyte component carries no additional $12.",error=True,
     extra="80051 performed on the same specimen as 80053 is included in the 80053 allowance. There is no separate allowance or patient cost for that component.")
case("Correct EOB but unexplained bill surcharge", [benefit("99214","Specialist visit",copay=55,coins=0)],
     [line("99214",400,240,(0,55,0,0,0),55,bill=95)],55,
     "EOB and contract agree on $55; the bill adds an unsupported $40.",error=True)
case("Insurance credit omitted from statement", [benefit("74177","CT")],
     [line("74177",1500,1000,(0,0,200,0,0),200,bill=700)],200,
     "20% of $1,000 is $200. The bill's $700 reflects $500 of missing insurer credit.",error=True)
case("Receipt not applied to remaining balance", [benefit("70551","MRI")],
     [line("70551",1000,600,(0,0,120,0,0),120,bill=220,paid=100)],120,
     "Total liability is $120; documented $100 payment leaves $20, not the statement's $120 balance.",error=True)
case("Opening deductible history understated", [benefit("76700","Ultrasound",True)],
     [line("76700",900,500,(450,0,10,0,0),220)],220,
     "Verified prior deductible $850 leaves $150, then 20% of $350 = $70: total $220, not $460.",
     error=True,opening=(850,1000,0,0))
case("OOP cap also limits deductible collection", [benefit("72148","MRI",True)],
     [line("72148",2000,700,(500,0,0,0,0),30)],30,
     "Although $500 deductible remains, only $30 OOP remains. Covered responsibility cannot exceed $30.",
     error=True,opening=(500,4970,0,0))
case("Excluded cosmetic spending wrongly consumes OOP", [benefit("15829","Cosmetic exclusion",coins=0,covered=False),benefit("74177","CT")],
     [line("15829",600,600,(0,0,0,600,0),600),line("74177",1800,1000,(0,0,0,0,0),200)],800,
     "The $600 exclusion does not consume the $500 remaining OOP. Covered CT still owes $200; total $800.",
     error=True,opening=(1000,4500,0,0))
case("Contractual adjustment partially reversed on bill", [benefit("93000","ECG")],
     [line("93000",700,400,(0,0,80,0,0),80,bill=180)],80,
     "20% of $400 is $80; reversing $100 of the mandatory in-network adjustment is erroneous.",error=True)
case("Coinsurance assessed before subtracting copay", [benefit("97110","Therapy",True,copay=25,coins=20)],
     [line("97110",600,250,(100,25,30,0,0),150)],150,
     "$100 deductible, then $25 copay, then 20% of $125 = $25. Total $150, not $155.",
     error=True,opening=(900,1500,0,0))
case("Referral omission is provider liability", [benefit("99214","Referred specialist",copay=50,coins=0)],
     [line("99214",250,150,(0,0,0,250,0),0,facts="Participating primary provider omitted mandatory referral; member followed referral instructions and has no financial undertaking.")],0,
     "The explicit plan clause assigns this procedural denial to the participating provider, leaving $0 to the member.",error=True,
     extra="Specialist visits require a referral. If the participating primary provider omits it despite the member following instructions, the provider bears the denial and cannot bill the member; no patient cost sharing applies.")
case("Separate network pools and omitted permitted excess", [benefit("74177","CT",True),benefit("70551","Elective MRI",True,coins=40,network="out")],
     [line("74177",1000,600,(100,0,100,0,0),200),line("70551",1300,1000,(500,0,200,0,0),1000,network="out")],1200,
     "In network: $100 + 20% of $500 = $200. Out network: separate $500 deductible + 40% of $500 + $300 permitted balance = $1,000. Total $1,200; the $900 statement is an underbill.",
     error=True,opening=(900,1500,1500,2000))

INSURERS = ["Aster Lantern Mutual", "Juniper Kite Assurance", "Velvet Compass Health",
            "Opal Orchard Cooperative", "Silver Thimble Benefits", "Wren Harbor Mutual",
            "Copper Meadow Assurance", "Linden Comet Health"]

def policy_text(n, c):
    d, o, od, oo, bal = c["terms"]
    header = (f"SYNTHETIC — fictional Summary of Benefits and Coverage\n"
              f"Insurer: SYNTHETIC {INSURERS[(n-1)%len(INSURERS)]}\n"
              f"Policy ID: SYN-B{n:02d}; Member ID: SYN-M{n:02d}\n"
              "Coverage period: 2026-01-01 through 2026-12-31. Currency: USD.\n"
              "Individual annual benefit; no family pool. One visit/unit per line unless explicitly documented as a duplicate.\n")
    network_rows = [f"In-network | ${d:,.2f} | ${o:,.2f} | prohibited",
                    f"Out-of-network | ${od:,.2f} | ${oo:,.2f} | {'permitted' if bal else 'prohibited'}"]
    if n % 4 == 0:
        terms = ("\nFinancial overview\n| Network | Annual deductible | Annual out-of-pocket maximum | Excess balance billing |\n"
                 "| --- | --- | --- | --- |\n" + "\n".join('| '+r+' |' for r in network_rows))
    elif n % 4 == 1:
        terms = (f"\nSection A — participating providers: annual deductible ${d:,.2f}; annual out-of-pocket limit ${o:,.2f}. No excess balance billing.\n"
                 f"Section B — nonparticipating providers: annual deductible ${od:,.2f}; annual out-of-pocket limit ${oo:,.2f}. Excess balance billing is {'permitted' if bal else 'prohibited'}.\n")
    elif n % 4 == 2:
        terms = (f"\nFinancial reference card\nIN NETWORK: deductible = ${d:,.2f}; OOP maximum = ${o:,.2f}; balance billing = no.\n"
                 f"OUT OF NETWORK: deductible = ${od:,.2f}; OOP maximum = ${oo:,.2f}; balance billing = {'yes' if bal else 'no'}.\n")
    else:
        terms = (f"\nWhat must I pay before benefits? The individual deductible is ${d:,.2f} in network and ${od:,.2f} out of network.\n"
                 f"What is my annual limit? Covered sharing stops at ${o:,.2f} in network and ${oo:,.2f} out of network.\n"
                 f"Can providers collect excess charges? Participating providers cannot. Nonparticipating providers {'may' if bal else 'may not'}.\n")
    rules = ("\nCalculation and accumulation rules: For covered care apply any remaining deductible first, "
             "then the stated copay, then member coinsurance to the remaining allowed amount. "
             "Round coinsurance half up to cents. Apply the remaining annual OOP cap to deductible, copay and coinsurance in that order. "
             "Only actually assessed covered sharing accrues. In- and out-of-network annual pools are separate. "
             "Permitted excess equals charge minus allowance and is outside OOP. "
             "Excluded care is full-charge patient liability outside deductible and OOP, with no insurer payment. "
             "No excess billing is allowed in network. A waived deductible means no deductible applies to that benefit.\n")
    benefit_text = "\nBenefits — amounts are per visit/unit\n"
    for i,b in enumerate(c['benefits'],1):
        coverage = ('covered' if b['covered'] else 'excluded; full charge, no covered sharing')
        benefit_text += (f"B{i}: {b['description']} (CPT/HCPCS {b['code']}), {b['network']}-network: {coverage}; "
                         f"deductible {'applies' if b['deductible'] else 'waived'}; "
                         f"member copay ${b['copay']/100:.2f}; member coinsurance {b['coinsurance_percent']}%.\n")
    return header+terms+rules+benefit_text+"\nSpecial provisions: "+(c['extra'] or "None.")+"\n"

def write_cases():
    assert len(CASES)==40 and sum(c['true_error'] for c in CASES)==24
    for n,c in enumerate(CASES,1):
        case_id=f"blind-{n:02d}"
        dest=ROOT/'cases'/case_id
        dest.mkdir(parents=True,exist_ok=False)
        (dest/'policy.md').write_text(policy_text(n,c))
        shared=dict(synthetic=True, case_id=case_id, policy_id=f"SYN-B{n:02d}",
                    member_id=f"SYN-M{n:02d}",claim_id=f"SYN-C{n:02d}",
                    insurer="SYNTHETIC "+INSURERS[(n-1)%len(INSURERS)])
        eob=dict(**shared,document_type="SYNTHETIC explanation of benefits",
                 title=c['title'],opening_accumulators_cents=dict(zip(
                     ['in_deductible','in_oop','out_deductible','out_oop'],c['opening'])),lines=[])
        bill=dict(**shared,document_type="SYNTHETIC itemized medical bill",bill_id=f"SYN-I{n:02d}",lines=[])
        gold=[]
        for j,l in enumerate(c['lines'],1):
            lid=f"L{j:02d}"
            day=10+j
            if n in (28,30): day=11
            identity=dict(line_id=lid,provider_id=f"SYN-P{n:02d}",
                          service_date=f"2026-06-{day:02d}",code=l['code'],units=1)
            components=dict(zip(['deductible_cents','copay_cents','coinsurance_cents',
                                 'noncovered_cents','balance_bill_cents'],l['observed']))
            observed=sum(l['observed'])
            insurer=0 if components['noncovered_cents'] else max(0,l['allowed']-sum(l['observed'][:3]))
            adjust=l['charge']-observed-insurer
            assert adjust>=0,(n,j,adjust)
            eob['lines'].append(dict(**identity,network=l['network'],charge_cents=l['charge'],
                allowed_amount_cents=l['allowed'],allowed_source="contract",
                allowed_reference=f"SYNTHETIC signed rate schedule SYN-R{n:02d}, line {lid}; protected recognized amount where stipulated",
                **components,insurer_payment_cents=insurer,adjustment_cents=adjust,
                patient_responsibility_cents=observed,documented_facts=l['facts'],
                actual_service_code=l['actual_code'] or l['code']))
            patient_total=observed if l['bill'] is None else l['bill']
            credit=min(insurer,l['charge']-patient_total)
            bill['lines'].append(dict(**identity,claim_line_id=lid,charge_cents=l['charge'],
                insurance_credit_cents=credit,adjustment_cents=l['charge']-patient_total-credit,
                patient_paid_cents=l['paid'],balance_due_cents=patient_total-l['paid'],
                documented_facts=l['facts']))
            gold.append(dict(line_id=lid,patient_responsibility_cents=l['expected'],
                             remaining_owed_cents=max(0,l['expected']-l['paid']),
                             refund_cents=max(0,l['paid']-l['expected'])))
        assert sum(x['patient_responsibility_cents'] for x in gold)==c['expected_total']
        true=sum(x['patient_paid_cents']+x['balance_due_cents'] for x in bill['lines'])!=c['expected_total']
        assert true==c['true_error'],n
        expected=dict(synthetic=True,case_id=case_id,true_error=c['true_error'],
                      lines=gold,total_patient_responsibility_cents=c['expected_total'],
                      total_remaining_owed_cents=sum(x['remaining_owed_cents'] for x in gold),
                      total_refund_cents=sum(x['refund_cents'] for x in gold),rationale=c['rationale'])
        for name,doc in [('eob.json',eob),('bill.json',bill),('expected.json',expected)]:
            (dest/name).write_text(json.dumps(doc,indent=2,ensure_ascii=False)+'\n')
    print('Authored 40 SYNTHETIC cases: 16 correct, 24 with an error. No app imports or calls.')

if __name__=='__main__':
    write_cases()
