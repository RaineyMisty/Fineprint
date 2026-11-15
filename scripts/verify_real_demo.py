"""Measure the real-policy /extract -> /compile -> /check HTTP path.

Requires a running local server. Only the policy PDF is real; demo claim inputs
are explicitly synthetic. Saves measurements and source quotes, never full text.
"""
import argparse
import base64
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request(base, path, body=None):
    req = Request(base + path, data=None if body is None else json.dumps(body).encode(),
                  headers={} if body is None else {'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=900) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8765')
    parser.add_argument('--policy-pdf', type=Path, required=True)
    parser.add_argument('--demo-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), kind='real_policy_synthetic_claim_http_demo',
                  real_policy=True, synthetic_claim=True, synthetic_bill=True, endpoints=[], status='failed')
    started = time.monotonic()
    try:
        def call(path, body=None):
            status, result = request(args.base_url, path, body)
            report['endpoints'].append(dict(path=path, http_status=status))
            if status != 200:
                raise ValueError(result.get('error', 'HTTP request failed'))
            return result
        report['server'] = call('/api/status')
        sample = call('/api/demos/' + args.demo_id)
        if not sample['synthetic'] or not sample['requires_policy_upload']:
            raise ValueError('Expected a real-policy / synthetic-claim demo')
        pdf = args.policy_pdf.read_bytes()
        report['pdf_sha256'] = hashlib.sha256(pdf).hexdigest()
        extracted = call('/api/extract', dict(kind='policy', filename=args.policy_pdf.name,
                                             content_base64=base64.b64encode(pdf).decode()))
        report['extraction'] = {key: extracted[key] for key in ('filename', 'pages', 'chars', 'status', 'warnings')}
        compiled = call('/api/compile', dict(document=extracted['text'], document_id='uploaded-policy', provider='deepseek'))
        report['compilation'] = compiled['compilation']
        output = compiled['compilation']['output']
        assert all(extracted['text'][e['start']:e['end']] == e['quote'] for r in output['rule_evidence'] for e in r['evidence'])
        report['validated_rules'] = len(output['rule_evidence'])
        report['validated_quote_spans'] = sum(len(r['evidence']) for r in output['rule_evidence'])
        inputs = {**sample['inputs'], 'policy': extracted['text'], **compiled, 'synthetic': True}
        # This generated synthetic claim is explicitly attached to the uploaded plan.
        inputs['claim_context']['policy_id'] = output['policy']['id']
        checked = call('/api/check', inputs)
        report['case'], report['check'] = checked['case'], checked['report']
        if checked['report']['status'] != 'ready':
            raise ValueError(checked['report'].get('blocked_reason', 'Calculation blocked'))
        # Change adjudication and bill, conserving each document's arithmetic.
        # The same policy/independent contract inputs must produce the same result.
        changed = dict(inputs)
        for key, plus, minus in (('eob', 'copay', 'plan_paid'), ('bill', 'balance_due', 'insurance_paid')):
            reader = csv.DictReader(io.StringIO(inputs[key]))
            rows = list(reader)
            from decimal import Decimal
            rows[0][plus] = str(Decimal(rows[0][plus]) + Decimal('1.00'))
            rows[0][minus] = str(Decimal(rows[0][minus]) - Decimal('1.00'))
            stream = io.StringIO()
            writer = csv.DictWriter(stream, reader.fieldnames)
            writer.writeheader(); writer.writerows(rows)
            changed[key] = stream.getvalue()
        perturbed = call('/api/check', changed)
        original_totals = [s['patient_cents'] for s in checked['report']['scenarios']]
        changed_totals = [s['patient_cents'] for s in perturbed['report']['scenarios']]
        report['independence_check'] = dict(eob_and_bill_patient_increase_cents=100, original_totals=original_totals,
                                            perturbed_totals=changed_totals, passed=original_totals == changed_totals and bool(changed_totals))
        if not report['independence_check']['passed']:
            raise ValueError('Independent recalculation changed after changing only adjudication/bill')
        report['status'] = 'passed'
    except (ValueError, AssertionError) as exc:
        report['error'] = str(exc)
    finally:
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'elapsed_seconds', 'endpoints')}))
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
