# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
import argparse
from collections import Counter, defaultdict
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
D = workspace()
REPO = repository()
CONTRACT_SHA = binding('summarize_frozen_C_assignment_outputs.sha_or_identity.1')
HELPER_SHA = binding('summarize_frozen_C_assignment_outputs.sha_or_identity.2')
METHODS = ('B0', 'B1', 'B2')
ALLOWED_ROLES = {'native_val'}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def need(ok, message):
    if not ok:
        raise ValueError(message)

def freeze(value):
    if isinstance(value, list):
        return tuple((freeze(v) for v in value))
    return value

def helper():
    need(sha(artifact_path('report_estimand_contract.json')) == CONTRACT_SHA, 'estimand contract drift')
    path = artifact_path('frozen_report_estimators.py')
    need(sha(path) == HELPER_SHA, 'approved report helper drift')
    spec = importlib.util.spec_from_file_location('approved_frozen_report_estimators', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def require_complete(manifest, plan, plan_sha):
    need(manifest.get('status') == 'FROZEN_ASSIGNMENT_EXECUTION_COMPLETED', 'batch final manifest not completed')
    need(manifest.get('plan_sha256') == plan_sha, 'completed batch uses a different frozen plan')
    ids = plan['input_ids']
    need(manifest.get('input_records') == len(ids), 'batch input count differs from plan')
    need(len(ids) == binding('summarize_frozen_C_assignment_outputs.cohort_count.3') and manifest.get('original_identity_denominator') == binding('summarize_frozen_C_assignment_outputs.cohort_count.4') and (manifest.get('public_unavailable') == binding('summarize_frozen_C_assignment_outputs.cohort_count.additional_5')), 'C original/public denominator mismatch')
    events = manifest['record_ledger']
    need([r['input_id'] for r in events] == ids and len(set(ids)) == len(ids), 'fixed queue incomplete or replaced')
    need(tuple(manifest['methods']) == METHODS, 'three fixed methods required')
    need(manifest.get('retry_count') == 0 and manifest.get('test_inputs') == 0 and (manifest.get('model_forwards') == 0), 'forbidden retry/test/model activity')
    return events

def original_query_identity_link():
    path = artifact_path('C_policy_handoff.json')
    receipt = json.loads(path.read_text())
    need((receipt['train_identity_only'], receipt['val_rows'], receipt['test_identity_only'], receipt['invalid_unpartitioned']) == (binding('summarize_frozen_C_assignment_outputs.cohort_count.5'), binding('summarize_frozen_C_assignment_outputs.cohort_count.6'), binding('summarize_frozen_C_assignment_outputs.cohort_count.7'), binding('summarize_frozen_C_assignment_outputs.cohort_count.additional_36')), 'original C identity ledger changed')
    return dict(metadata_receipt_path=str(path), metadata_receipt_sha256=sha(path), ledger_path=receipt['identity_ledger']['path'], ledger_sha256=receipt['identity_ledger']['sha256'], original_identity_counts=dict(train=binding('summarize_frozen_C_assignment_outputs.cohort_count.8'), validation=binding('summarize_frozen_C_assignment_outputs.cohort_count.9'), test=binding('summarize_frozen_C_assignment_outputs.cohort_count.10'), invalid_unpartitioned=binding('summarize_frozen_C_assignment_outputs.cohort_count.additional_36')), role='native_val', interpretation='historical nonblind C control, not independent blind validation', identity_only_test_link=True, test_labels_or_results_read=False)

def native_val_estimate(report_helper, rows):
    report = report_helper.estimate_report(rows, role='validation')
    report['role'] = 'native_val'
    report['helper_role_api_category'] = 'validation'
    report['actual_cohort_role'] = 'native_val'
    report['single_cohort_no_role_pooling'] = True
    for item in report['summaries'] + report['paired_gains']:
        item['stratum']['role'] = 'native_val'
    return report

def full_coverage(results, plan):
    item = plan['inputs']['coverage_ledger']
    need(sha(item['path']) == item['sha256'], 'C full coverage bytes changed')
    original = read_index(item['path'])
    need(len(original) == binding('summarize_frozen_C_assignment_outputs.cohort_count.11'), 'C full coverage denominator')
    ordered = list(original)
    queue = plan['input_ids']
    need([i for i in ordered if i in set(queue)] == queue, 'C queue not original ordered subset')
    unknown = [i for i in ordered if i not in set(queue)]
    need(len(unknown) == binding('summarize_frozen_C_assignment_outputs.cohort_count.additional_5'), 'public unavailable count')
    for iid, row in original.items():
        need(row['native_role'] == 'native_val', 'C coverage role changed')
        need(row.get('policy_missing') is True and row.get('historical_C_quality_policy_status') == 'unknown', 'historical C policy unknown must not be promoted')
        if iid in unknown:
            need(row['scorequeue_status'] == 'public_unavailable_unknown' and row['public_available'] is False and (row['pregold_status'] == 'unknown_not_admitted'), 'unavailable identity improperly admitted')
            need(not (results / 'raw' / (iid + '.payload.json')).exists(), 'unavailable source got fake solver payload')
    completed = json.loads((results / 'full_original_identity_coverage.json').read_text())
    need((completed['original_identity_denominator'], completed['scorequeue'], completed['public_unavailable']) == (binding('summarize_frozen_C_assignment_outputs.cohort_count.12'), binding('summarize_frozen_C_assignment_outputs.cohort_count.13'), binding('summarize_frozen_C_assignment_outputs.cohort_count.additional_5')), 'completed C coverage denominator drift')
    completed_rows = completed['rows']
    need(len(completed_rows) == len(original), 'completed C coverage list multiplicity changed')
    completed_ids = [r['input_id'] for r in completed_rows]
    need(len(set(completed_ids)) == len(completed_ids) and set(completed_ids) == set(original), 'completed C coverage identity domain or uniqueness changed')
    need({r['input_id']: r for r in completed['rows']} == original, 'completed C coverage ledger changed')
    return dict(original_identity_denominator=binding('summarize_frozen_C_assignment_outputs.cohort_count.14'), public_scoring_queue=binding('summarize_frozen_C_assignment_outputs.cohort_count.15'), public_unavailable_unknown=binding('summarize_frozen_C_assignment_outputs.cohort_count.additional_5'), unavailable_input_ids=unknown, observations_fabricated_for_unavailable=0, quality_history=dict(policy_missing_preserved=binding('summarize_frozen_C_assignment_outputs.cohort_count.16'), historical_C_quality_unknown_preserved=binding('summarize_frozen_C_assignment_outputs.cohort_count.17')), coverage_ledger_path=item['path'], coverage_ledger_sha256=item['sha256'], completed_coverage_sha256=sha(results / 'full_original_identity_coverage.json'))

def nested(obj, key):
    for part in key.split('.'):
        obj = obj[part]
    return obj

def cache_gate(plan, *, review_path, review_sha, count_key, prediction_key, prediction_sha):
    need(review_path and review_sha and prediction_sha, 'C actual cache fullrow review SHA gate required')
    need(sha(review_path) == review_sha, 'C cache review bytes drift')
    review = json.loads(Path(review_path).read_text())
    decision = review.get('decision', review.get('status', ''))
    need(isinstance(decision, str) and decision.startswith('PASS'), 'C actual cache gate not PASS')
    need(nested(review, count_key) == binding('summarize_frozen_C_assignment_outputs.cohort_count.18'), 'C fullrow cache reviewed input count')
    need(nested(review, prediction_key) == prediction_sha, 'C actual reviewed prediction bytes binding')
    need(any((r['sha256'] == review_sha for r in plan['reviews'])), 'C cache PASS not in executed frozen plan')
    packaging = plan['packaged_manifest']
    need(sha(packaging['path']) == packaging['sha256'], 'C packaging manifest changed')
    packaged = json.loads(Path(packaging['path']).read_text())
    need(prediction_sha in packaged['upstream_sha256'].values(), 'C raw prediction artifact not in packaging closure')
    return dict(review_path=str(review_path), review_sha256=review_sha, decision=decision, reviewed_input_count=binding('summarize_frozen_C_assignment_outputs.cohort_count.19'), reviewed_prediction_artifact_sha256=prediction_sha, count_field=count_key, prediction_hash_field=prediction_key)

def read_index(path):
    rows = {}
    for literal in Path(path).read_text().splitlines():
        if literal.strip():
            row = json.loads(literal)
            need(row['input_id'] not in rows, 'duplicate immutable input')
            rows[row['input_id']] = row
    return rows

def load_evaluation(results, plan):
    sys.path.insert(0, str(REPO))
    from nmr_assignment.metrics import EvaluationRow
    ledger_item = plan['inputs']['ledger']
    need(sha(ledger_item['path']) == ledger_item['sha256'], 'source ledger bytes drift')
    ledger = read_index(ledger_item['path'])
    ids = plan['input_ids']
    need(set(ledger) == set(ids), 'immutable ledger domain mismatch')
    by_role = defaultdict(list)
    calibration_expected = {}
    frozen_rows = {}
    observed_files = {}
    status_counts = Counter()
    for iid in ids:
        rawpath = results / 'raw' / (iid + '.json')
        evalpath = results / 'evaluation' / (iid + '.json')
        need(rawpath.is_file() and evalpath.is_file(), 'completed input lacks durable raw/evaluation:' + iid)
        raw = json.loads(rawpath.read_text())
        need(raw['input_id'] == iid and raw['plan_sha256'] == sha(plan['_plan_path']), 'raw input/plan binding')
        status_counts[raw['raw_execution']['status']] += 1
        if raw.get('anonymous_payload_sha256') is not None:
            payloadpath = results / 'raw' / (iid + '.payload.json')
            need(payloadpath.is_file() and sha(payloadpath) == raw['anonymous_payload_sha256'], 'submitted bytes digest mismatch')
            observed_files[str(payloadpath)] = sha(payloadpath)
        decoded = json.loads(evalpath.read_text())
        initialpath = results / 'evaluation' / (iid + '.not_started.json')
        need(initialpath.is_file(), 'independent initial fixed denominator missing')
        initial = json.loads(initialpath.read_text())
        observed_files[str(initialpath)] = sha(initialpath)
        need(set(initial) == set(METHODS), 'initial method inventory mismatch')
        need(set(decoded) == set(METHODS), 'evaluation method domain mismatch')
        roles = ledger[iid]['roles']
        need(roles and set(roles) <= ALLOWED_ROLES, 'test or unknown report role')
        input_method_rows = {}
        for method in METHODS:
            data = decoded[method]
            need(data['metadata']['input_id'] == iid and tuple(data['metadata']['roles']) == tuple(roles), 'evaluation input/role binding')
            rr = []
            for value in data['rows']:
                need(set(value) == {f.name for f in fields(EvaluationRow)}, 'EvaluationRow field schema drift')
                row = EvaluationRow(**{k: freeze(v) for k, v in value.items()})
                context = dict(row.context)
                need(context['baseline'] == method and context['nucleus'] == '13C' and (context['truth_basis'] == 'source_relative_current_serialization') and (context['task_semantics'] == 'derived_serialized_value_bin') and (context['target_level'] == 'parent') and (context['target_semantics'] == 'set'), 'unexpected report stratum')
                need(context['record_id'] == ledger[iid]['record_id'] and context['connectivity_id'] == ledger[iid]['connectivity_sha256'], 'evaluation immutable source identity')
                rr.append(row)
                for role in roles:
                    by_role[role].append(row)
                if set(roles) & {'native_val'} and row.metric == 'compatible_observation':
                    identity = json.dumps((context['record_id'], row.observation_id), ensure_ascii=False, separators=(',', ':'))
                    need((method, identity) not in calibration_expected, 'duplicate compatible identity')
                    calibration_expected[method, identity] = dict(connectivity_id=context['connectivity_id'], gold_eligible=row.eligible, prediction_supported=row.prediction_supported, correct=row.success if row.eligible else None)
            initial_rows = initial[method]

            def inventory(values):
                inv = {}
                for v in values:
                    k = (v['metric'], v['observation_id'])
                    need(k not in inv, 'duplicate metric observation')
                    inv[k] = (v['context'], v['eligible'], v['eligibility_reason_codes'], v['eligibility_determinator'])
                return inv
            need(inventory(data['rows']) == inventory(initial_rows), 'final domain differs from independent initial fixed denominator')
            input_method_rows[method] = rr
        domains = []
        for method in METHODS:
            domains.append({(r.metric, r.observation_id): r.eligible for r in input_method_rows[method]})
        need(domains[0] == domains[1] == domains[2], 'baseline fixed gold denominator mismatch')
        frozen_rows[iid] = domains[0]
        observed_files[str(rawpath)] = sha(rawpath)
        observed_files[str(evalpath)] = sha(evalpath)
    return (by_role, ledger, calibration_expected, observed_files, dict(status_counts))

def verify_fixed_publication(artifact, rows, policy):
    """核既定阈值与固定连接体分区；不选择阈值、不调用calibrate。"""
    import math
    from nmr_assignment.calibration import connectivity_partition
    threshold = artifact['threshold']
    need(threshold is None or (isinstance(threshold, (float, int)) and (not isinstance(threshold, bool)) and math.isfinite(threshold) and (threshold > 0)), 'invalid frozen threshold')
    if threshold is not None:
        calibration_scores = {r['margin'] for r in rows if connectivity_partition(r['connectivity_id'], split_namespace=policy['split_namespace']) == 'calibration' and r['gold_eligible'] and r['prediction_supported'] and r['margin_certified'] and (type(r['margin']) in (float, int)) and math.isfinite(r['margin']) and (r['margin'] > 0)}
        need(threshold in calibration_scores, 'stored threshold not an original calibration publishable score')
    rebuilt = {}
    for split in ('calibration', 'audit'):
        rr = [r for r in rows if connectivity_partition(r['connectivity_id'], split_namespace=policy['split_namespace']) == split]
        need(artifact[split + '_evidence_ids'] == sorted((r['item_id'] for r in rr)), 'fixed split evidence identity mismatch')
        pub = [r for r in rr if threshold is not None and r['gold_eligible'] and r['prediction_supported'] and r['margin_certified'] and isinstance(r['margin'], (float, int)) and (not isinstance(r['margin'], bool)) and math.isfinite(r['margin']) and (r['margin'] > 0) and (r['margin'] >= threshold)]
        n = sum((r['gold_eligible'] for r in rr))
        summary = dict(eligible_count=n, published_count=len(pub), correct_count=sum((r['correct'] for r in pub)), published_connectivity_groups=len({r['connectivity_id'] for r in pub}), precision=sum((r['correct'] for r in pub)) / len(pub) if pub else None, coverage=len(pub) / n if n else 0.0, published_ids=sorted((r['item_id'] for r in pub)))
        need(all((artifact[split][k] == v for k, v in summary.items())), 'fixed threshold split summary mismatch')
        rebuilt[split] = summary

    def accepted(s):
        return s['published_count'] >= policy['minimum_published_units'] and s['published_connectivity_groups'] >= policy['minimum_connectivity_groups'] and (s['precision'] is not None) and (s['precision'] >= policy['minimum_precision'])
    if threshold is not None:
        need(accepted(rebuilt['calibration']), 'stored threshold fails calibration support/precision')
    a = rebuilt['audit']
    status = 'off_insufficient_support' if threshold is None else 'on_audit_passed' if accepted(a) else 'off_insufficient_support' if a['published_count'] < policy['minimum_published_units'] or a['published_connectivity_groups'] < policy['minimum_connectivity_groups'] else 'off_audit_rejected'
    need(artifact['status'] == status, 'publication status not justified by fixed threshold evidence')
    published = sorted(rebuilt['calibration']['published_ids'] + a['published_ids']) if status == 'on_audit_passed' else []
    need(artifact['published_ids'] == published, 'publication set mismatch')
    correct = sum((s['correct_count'] for s in rebuilt.values()))
    eligible = sum((s['eligible_count'] for s in rebuilt.values()))
    need(artifact['publication_precision'] == (correct / len(published) if published else None) and artifact['publication_coverage'] == (len(published) / eligible if eligible else 0.0), 'publication rate mismatch')

def calibration_audit(results, plan, expected_items):
    """Read and bind completed calibration only; never call calibrate or refit."""
    inputs_path = results / 'calibration_inputs.json'
    artifact_path = results / 'calibration_artifacts.json'
    inputs = json.loads(inputs_path.read_text())
    artifacts = json.loads(artifact_path.read_text())
    seen, axis_inputs = (set(), defaultdict(list))
    for row in inputs:
        axis = row['axis']
        need(row['partition'] == 'validation', 'training/test calibration input forbidden')
        need(axis['cohort_sha256'] == plan['validation_cohort_sha256'] and axis['source_sha256'] == plan['source_sha256'] and (axis['label_sha256'] == plan['label_sha256']) and (axis['rule_sha256'] == plan['rule_sha256']), 'calibration provenance axis mismatch')
        need(axis['truth_basis'] == 'source_relative_current_serialization' and axis['endpoint'] == 'per_peak_compatibility' and (axis['sampling_unit'] == 'observation') and (axis['nucleus'] == '13C') and (axis['method'] in METHODS) and (axis['target_level'] == 'parent') and (axis['target_semantics'] == 'set') and (axis['task_semantics'] == 'derived_serialized_value_bin'), 'calibration endpoint/track mismatch')
        identity = (axis['method'], row['item_id'])
        need(identity not in seen, 'duplicate calibration input')
        need(isinstance(expected_items, dict), 'calibration requires independently evaluated evidence binding')
        expected = expected_items[identity]
        need(all((row[k] == v for k, v in expected.items())), 'calibration input differs from evaluated source ledger evidence')
        seen.add(identity)
        axis_inputs[json.dumps(axis, sort_keys=True)].append(row)
    need(seen == set(expected_items), 'validation calibration domain not exactly evaluated compatible rows')
    sys.path.insert(0, str(REPO))
    from nmr_assignment.calibration import policy_from_frozen_config
    from dataclasses import asdict
    config_item = plan['inputs']['numeric_config']
    need(sha(config_item['path']) == config_item['sha256'], 'numeric config drift')
    expected_policy = asdict(policy_from_frozen_config(json.loads(Path(config_item['path']).read_text())))
    summaries, seen_axes = ([], set())
    for artifact in artifacts:
        axis = artifact['axis']
        key = json.dumps(axis, sort_keys=True)
        need(key in axis_inputs and key not in seen_axes, 'calibration artifact axis mismatch')
        seen_axes.add(key)
        rr = axis_inputs[key]
        need(artifact['policy'] == expected_policy, 'calibration selection/seed/namespace altered')
        need(artifact['precision_metric'] == 'source_assertion_compatibility_precision', 'source-relative is not experimental accuracy')
        verify_fixed_publication(artifact, rr, expected_policy)
        eligible = sum((r['gold_eligible'] for r in rr))
        need(artifact['calibration']['eligible_count'] + artifact['audit']['eligible_count'] == eligible, 'calibration fixed denominator mismatch')
        published = artifact['published_ids']
        need(len(published) == len(set(published)) and set(published) <= {r['item_id'] for r in rr}, 'publication identity mismatch')
        if artifact['status'] != 'on_audit_passed':
            need(not published, 'failed audit cannot publish')
        summaries.append(dict(axis=axis, status=artifact['status'], threshold=artifact['threshold'], precision_metric=artifact['precision_metric'], publication_precision=artifact['publication_precision'], publication_coverage=artifact['publication_coverage'], published_count=len(published), calibration=artifact['calibration'], audit=artifact['audit'], thresholds_reselected=False))
    need(seen_axes == set(axis_inputs), 'missing frozen calibration artifact')
    return dict(input_file_sha256=sha(inputs_path), artifact_file_sha256=sha(artifact_path), validation_only=True, threshold_selection_calls=0, input_count=len(inputs), axes=summaries)

def aggregate(plan_path, manifest_path, manifest_sha, out, *, plan_sha, cache_args):
    started = time.monotonic()
    report_helper = helper()
    need(manifest_sha and sha(manifest_path) == manifest_sha, 'explicit final manifest SHA required')
    manifest = json.loads(Path(manifest_path).read_text())
    plan_path = Path(plan_path)
    need(plan_sha and sha(plan_path) == plan_sha, 'explicit frozen C plan SHA required')
    plan = json.loads(plan_path.read_text())
    plan['_plan_path'] = str(plan_path)
    events = require_complete(manifest, plan, sha(plan_path))
    results = Path(manifest_path).parent
    original = original_query_identity_link()
    actual_cache_gate = cache_gate(plan, **cache_args)
    coverage = full_coverage(results, plan)
    by_role, ledger, expected_items, observed_files, statuses = load_evaluation(results, plan)
    reports = {role: native_val_estimate(report_helper, rows) for role, rows in sorted(by_role.items())}
    calibration = calibration_audit(results, plan, expected_items)
    need(not Path(out).exists(), 'new report output directory required')
    Path(out).mkdir()
    report = dict(schema='completed_C_frozen_assignment_report_v1', generated_utc=datetime.now(timezone.utc).isoformat(), source_row_records=len(plan['input_ids']), original_C_identity_coverage=coverage, actual_C_cache_independent_gate=actual_cache_gate, control_scope='historical nonblind C native_val control; not blind independent data', source_row_roles=dict(Counter((role for x in ledger.values() for role in x['roles']))), source_row_coverage_by_role={role: dict(Counter((x['ledger_class'] for x in ledger.values() if role in x['roles']))) for role in sorted({r for x in ledger.values() for r in x['roles']})}, original_query_identity_ledger=original, reports_by_existing_role=reports, truth_basis='source_relative_current_serialization', trusted_experimental=False, original_C3745_coverage_replaced_by3740=False, test_scores=0, calibration_audit=calibration, chemical_quotient_top3=None, chemical_quotient_top3_status='unsupported', strict_full_spectrum_is_separate_endpoint=True, completed_manifest_sha256=manifest_sha, plan_sha256=sha(plan_path), estimand_contract_sha256=CONTRACT_SHA, report_helper_sha256=HELPER_SHA)
    reportpath = Path(out) / 'report.json'
    reportpath.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    handoff = dict(schema='completed_C_report_handoff_v1', status='AGGREGATED_EXISTING_COMPLETED_OUTPUTS', actual_exit=0, elapsed_seconds=time.monotonic() - started, completed_records=len(events), raw_status_counts=statuses, report_path=str(reportpath), report_sha256=sha(reportpath), completed_manifest_path=str(manifest_path), completed_manifest_sha256=manifest_sha, plan_sha256=sha(plan_path), source_record_denominator=len(plan['input_ids']), original_C_identity_coverage=coverage, actual_C_cache_independent_gate=actual_cache_gate, original_query_identity_ledger=original, observed_output_sha256=observed_files, calibration_inputs_sha256=calibration['input_file_sha256'], calibration_artifacts_sha256=calibration['artifact_file_sha256'], implementation_sha256=sha(__file__), report_helper_sha256=HELPER_SHA, estimand_contract_sha256=CONTRACT_SHA, solver_calls=0, model_forwards=0, new_threshold_selection_calls=0, test_rows_read=0)
    (Path(out) / 'handoff.json').write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: handoff[k] for k in ('status', 'actual_exit', 'elapsed_seconds', 'completed_records', 'report_sha256')}))

def synthetic_checks():
    from dataclasses import asdict
    sys.path.insert(0, str(REPO))
    from nmr_assignment.metrics import EvaluationRow
    ids = ['C-' + format(i, '064x') for i in range(binding('summarize_frozen_C_assignment_outputs.cohort_count.20'))]
    plan = dict(input_ids=ids, methods=METHODS)
    completed = dict(status='FROZEN_ASSIGNMENT_EXECUTION_COMPLETED', plan_sha256='a' * 64, input_records=binding('summarize_frozen_C_assignment_outputs.cohort_count.21'), original_identity_denominator=binding('summarize_frozen_C_assignment_outputs.cohort_count.22'), public_unavailable=binding('summarize_frozen_C_assignment_outputs.cohort_count.additional_5'), record_ledger=[dict(input_id=i) for i in ids], methods=METHODS, retry_count=0, test_inputs=0, model_forwards=0)
    require_complete(completed, plan, 'a' * 64)
    try:
        require_complete(dict(completed, status='running'), plan, 'a' * 64)
    except ValueError:
        pass
    else:
        raise AssertionError('partial batch aggregated')
    report_helper = helper()
    rows = []
    for method in METHODS:
        for record, connectivity, success in (('one', 'A', True), ('two', 'B', False)):
            context = dict(truth_basis='source_relative_current_serialization', nucleus='13C', task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', baseline=method, record_id=record, connectivity_id=connectivity)
            row = EvaluationRow(tuple(context.items()), 'exact_observation', 'bin:0', True, success, success, (), (), (), ())
            rebuilt = EvaluationRow(**{k: freeze(v) for k, v in json.loads(json.dumps(asdict(row))).items()})
            need(rebuilt == row, 'typed JSON row round-trip')
            rows.append(rebuilt)
    result = native_val_estimate(report_helper, rows)
    need(all((x['stratum']['role'] == 'native_val' for x in result['summaries'])), 'C role relabel')
    need(all((x['eligible_units'] == 2 and x['determinate_assignment_success_rate'] == 0.5 and (x['conditional_accuracy_among_supported_outputs'] == 1) and (x['supported_eligible_units'] == 1) for x in result['summaries'])), 'fixed vs conditional denominators')
    need(all((x['conditional_accuracy_among_supported_outputs_CI95'] is None for x in result['summaries'])), 'one-supported-connectivity conditional CI must remain NA')
    return dict(status='SYNTHETIC_C_REPORT_ADAPTER_PASS', actual_exit=0, checks=['C3740_completed_gate_and3745_identity', 'public_unavailable5_no_fake_observations', 'native_val_single_role_explicit_validation_API', 'completed_manifest_gate', 'partial_batch_rejected', 'typed_evaluation_roundtrip', 'frozen_helper_called', 'unsupported_fixed_denominator', 'conditionalCI_NA'], implementation_sha256=sha(__file__), helper_sha256=HELPER_SHA, contract_sha256=CONTRACT_SHA, real_result_rows_read=0, real_scores_reported=0, solver_calls=0, model_forwards=0)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--aggregate', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--receipt')
    p.add_argument('--plan', default=str(artifact_path('C_trainval_scoring_plan.json')))
    p.add_argument('--plan-sha256')
    p.add_argument('--cache-review')
    p.add_argument('--cache-review-sha256')
    p.add_argument('--cache-reviewed-count-key', default='counts.inputs')
    p.add_argument('--cache-prediction-hash-key', default='frozen_artifacts.predictions_sha256')
    p.add_argument('--cache-prediction-artifact-sha256')
    p.add_argument('--completed-manifest', default=str(artifact_path('C_native_val_assignment_results/manifest.json')))
    p.add_argument('--completed-manifest-sha256')
    p.add_argument('--out', default=str(artifact_path('C_frozen_assignment_report')))
    args = p.parse_args()
    if args.self_test:
        result = synthetic_checks()
        if args.receipt:
            Path(args.receipt).write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    elif args.aggregate:
        aggregate(args.plan, args.completed_manifest, args.completed_manifest_sha256, args.out, plan_sha=args.plan_sha256, cache_args=dict(review_path=args.cache_review, review_sha=args.cache_review_sha256, count_key=args.cache_reviewed_count_key, prediction_key=args.cache_prediction_hash_key, prediction_sha=args.cache_prediction_artifact_sha256))
    else:
        helper()
        print(json.dumps(dict(status='CHECK_ONLY_READY_NO_RUNNING_OUTPUT_READ', required_gate='C completed manifest+SHA, plan+SHA, cache actual fullrow independent PASS+predictionSHA', helper_sha256=HELPER_SHA, contract_sha256=CONTRACT_SHA, solver_calls=0, model_forwards=0, real_scores_reported=0)))
if __name__ == '__main__':
    main()
