# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：Stage B native_test独立冻结report adaptor，不复用val3745/3740封装或伪装validation角色。
只读取completed评分、逐文件output inventory与原initial/final EvaluationRow；资格/成功原样保留。
复用已冻9d estimators的connectivity_estimates、paired_gain和固定CI常量，native_test独立输出。
不调用被限定train/validation的estimate_report入口；不重算gold/候选/solve，不fit/reselect阈值。
validate_threshold_applications核保存compatible逐峰域、完整冻结axis、off状态/阈值，缺失/重复/foreign或虚假stored证据拒绝。
完整C3637及H1371unavailable另账；Hg/cache失败仍在原gold eligible分母，public不可用不造峰。
phase监督保证600s/8GiB；本入口还核phase suite/owner/A闭包和source hashes，默认check-only。
"""
from pathlib import Path
from collections import defaultdict, Counter
from dataclasses import fields
import argparse, importlib.util, json, sys
import TEST_STAGE_B_execution_contract as contract
D = workspace()

def freeze(v):
    if isinstance(v, list):
        return tuple((freeze(x) for x in v))
    if isinstance(v, dict):
        return {k: freeze(x) for k, x in v.items()}
    return v

def estimator(path):
    p = contract.bound(path)
    contract.need(contract.sha(p) == contract.ESTIMATOR_SHA, 'frozen9d_estimator_required')
    spec = importlib.util.spec_from_file_location('TEST_STAGE_B_frozen9d', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def estimate_native_test(rows, helper):
    rows = tuple(sorted(rows, key=lambda r: (helper._group(r), dict(r.context)['record_id'], '' if r.observation_id is None else r.observation_id)))
    grouped = defaultdict(list)
    for row in rows:
        grouped[helper._group(row)].append(row)
    summary = []
    for legacy in helper.summarize(rows):
        stratum = legacy['stratum']
        key = tuple(((k, stratum[k]) for k in helper.GROUP_FIELDS)) + (('metric', stratum['metric']),)
        estimates = helper.connectivity_estimates(grouped[key])
        contract.need(estimates['determinate_assignment_success_rate'] == legacy['precision'], 'fixed_denominator_disagrees')
        clean = {k: v for k, v in legacy.items() if k != 'precision'}
        clean['stratum'] = dict(stratum, role='native_test')
        clean.update(estimates)
        clean.update(chemical_quotient_top3=None, chemical_quotient_top3_status='unsupported', truth_scope='source assertion consistency, not trusted experimental accuracy')
        summary.append(clean)
    gains = []
    for higher, lower in helper.COMPARISONS:
        for item in helper.paired_gain(rows, lower, higher, replicates=helper.REPLICATES, seed=helper.SEED, confidence=helper.CONFIDENCE):
            gains.append(dict(item, comparison=higher + '-' + lower, stratum=dict(item['stratum'], role='native_test')))
    return dict(schema='TEST_STAGE_B_frozen_native_test_estimators_v1', role='native_test', contract_sha256=helper.CONTRACT_SHA256, summaries=summary, paired_gains=gains, estimator_source_sha256=contract.ESTIMATOR_SHA, comparison_estimand='same frozen9d paired fixed-eligible micro gain; connectivity cluster bootstrap', whole_input_and_strict_full_separate=True, chemical_quotient_top3=None, real_experiment_truth_promoted=False, test_threshold_fit_calls=0)

def inventory_domain(rows):
    inv = {}
    for value in rows:
        key = (value['metric'], value['observation_id'])
        contract.need(key not in inv, 'duplicate_saved_metric_observation')
        inv[key] = (value['context'], value['eligible'], value['eligibility_reason_codes'], value['eligibility_determinator'])
    return inv

def validate_threshold_applications(applied, expected, frozen):
    """保存compatible域严格一对一；只核冻结元数据，绝不重新拟合或评价。"""
    need = contract.need
    semantic = tuple(contract.component.SEMANTIC_AXES)
    full = set(semantic) | {'cohort_sha256', 'source_sha256', 'label_sha256', 'rule_sha256'}
    frozen = frozen if isinstance(frozen, list) else frozen['axes']
    need(isinstance(frozen, list) and len(frozen) == 3, 'suite_three_frozen_method_artifacts')
    need({a.get('axis', {}).get('method') for a in frozen} == {'B0', 'B1', 'B2'}, 'suite_frozen_method_domain')
    for a in frozen:
        axis = a.get('axis', {})
        need(set(axis) == full and all((isinstance(axis[k], str) and axis[k] for k in full)), 'suite_complete_frozen_axis')
        need(isinstance(a.get('status'), str) and a['status'].startswith('off_') and (a.get('published_ids') == []), 'suite_frozen_off_publication')
    need(isinstance(applied, list), 'threshold_application_list')
    actual = {}
    for value in applied:
        need(isinstance(value, dict), 'threshold_application_object')
        key = tuple((value.get(k) for k in ('input_id', 'baseline', 'observation_id')))
        need(key not in actual, 'duplicate_threshold_application')
        actual[key] = value
    need(set(actual) == set(expected), 'threshold_application_exact_compatible_domain')
    for key, evidence in expected.items():
        value = actual[key]
        axis = evidence['semantic_axis']
        need(value.get('publication_enabled') is False and value.get('refit') is False, 'frozen_highconfidence_off_must_not_change')
        matches = [a for a in frozen if all((a['axis'][k] == axis[k] for k in semantic))]
        fallback = value.get('status') == 'off_no_matching_reviewed_Cval_artifact'
        if fallback:
            need(not evidence['pipeline_available'] or len(matches) != 1, 'threshold_fallback_requires_unavailable_or_no_matching_axis')
            need(value.get('threshold') is None and (not any((k in value for k in ('stored_status', 'stored_threshold', 'frozen_threshold_axis', 'test_semantic_axis', 'frozen_threshold_available')))), 'fallback_must_not_assert_stored_provenance')
            continue
        need(evidence['pipeline_available'] and len(matches) == 1, 'stored_application_requires_pipeline_matching_axis')
        artifact = matches[0]
        need(value.get('frozen_threshold_axis') == artifact['axis'] and value.get('test_semantic_axis') == axis, 'threshold_complete_frozen_axis_binding')
        need(value.get('status') == value.get('stored_status') == artifact['status'], 'threshold_frozen_status_binding')
        need('stored_threshold' in value and value['stored_threshold'] == artifact.get('threshold') and (value.get('threshold') is None), 'threshold_frozen_value_binding')
        need(value.get('frozen_threshold_available') is False, 'threshold_frozen_off_available_flag')
    return dict(expected_applications=len(expected), validated_applications=len(actual), frozen_method_artifacts=3, stored_statuses_preserved=True)

def report(config_item, suite_item, release_item):
    suite, a = contract.bind_suite(suite_item, release_item)
    config = contract.load(config_item)
    contract.need(config['suite_manifest_sha256'] == suite_item['sha256'], 'report_suite_binding')
    plan = contract.load(config['scoring_plan'])
    manifest = contract.load(config['completed_scoring_manifest'])
    queue = a['queue']
    contract.need(plan['input_ids'] == queue, 'report_fixed_A_queue')
    contract.need(manifest['status'] == 'FROZEN_ASSIGNMENT_EXECUTION_COMPLETED' and manifest['input_records'] == len(queue) and (manifest['original_identity_denominator'] == binding('TEST_STAGE_B_report.frozen_identity_count.1')), 'completed_test_scoring_required')
    contract.need(manifest['plan_sha256'] == config['scoring_plan']['sha256'] and [r['input_id'] for r in manifest['record_ledger']] == queue, 'completed_order_plan_SHA')
    inv = contract.load(config['scoring_output_inventory'])
    contract.need(inv['child_exit'] == 0 and inv['outer_exit'] == 0, 'complete_scoring_supervisor_exit')
    root = Path(config['completed_scoring_manifest']['path']).parent
    used = {}

    def saved(rel):
        p = root / rel
        entry = inv['output_sha256'].get(rel)
        contract.need(entry is not None, 'saved_output_not_in_frozen_inventory:' + rel)
        contract.need(contract.sha(p) == entry['sha256'], 'saved_output_SHA:' + rel)
        used[str(p)] = entry['sha256']
        return p
    sys.path.insert(0, str(Path(plan['repo'])))
    from nmr_assignment.metrics import EvaluationRow
    helper = estimator(config['estimators'])
    rows = []
    status = Counter()
    cache_status = Counter()
    expected_applications = {}
    fields_expected = {v.name for v in fields(EvaluationRow)}
    packaged_ledger = contract.load(plan['packaging_manifest'])
    contract.need(packaged_ledger['original_identity_denominator'] == binding('TEST_STAGE_B_report.frozen_identity_count.2') and packaged_ledger['scorequeue'] == len(queue), 'packaged_dynamic_domain')
    cohort_ledger = contract.component.unique(list(contract.component.rows(contract.bound(plan['inputs']['ledger']))))
    cache = contract.component.unique(list(contract.component.rows(contract.bound(plan['inputs']['cache_input_ledger']))))
    contract.need(set(cohort_ledger) == set(cache) == set(queue), 'report_join_domain')
    for iid in queue:
        raw = json.loads(saved('raw/' + iid + '.json').read_text())
        evaluated = json.loads(saved('evaluation/' + iid + '.json').read_text())
        initial = json.loads(saved('evaluation/' + iid + '.not_started.json').read_text())
        contract.need(raw['input_id'] == iid and raw['plan_sha256'] == config['scoring_plan']['sha256'], 'saved_raw_identity_plan')
        status[raw['raw_execution']['status']] += 1
        cache_status[cache[iid]['status']] += 1
        contract.need(set(evaluated) == set(initial) == set(('B0', 'B1', 'B2')), 'three_saved_methods')
        for method, bundle in evaluated.items():
            contract.need(bundle['metadata']['input_id'] == iid and list(bundle['metadata']['roles']) == ['native_test'], 'native_test_only_no_pool')
            contract.need(inventory_domain(bundle['rows']) == inventory_domain(initial[method]), 'fixed_initial_final_eligibility_changed')
            for v in bundle['rows']:
                contract.need(set(v) == fields_expected, 'EvaluationRow_schema_drift')
                row = EvaluationRow(**{k: freeze(x) for k, x in v.items()})
                c = dict(row.context)
                contract.need(c['baseline'] == method and c['truth_basis'] == 'source_relative_current_serialization' and (c['nucleus'] == '13C') and (c['task_semantics'] == 'derived_serialized_value_bin') and (c['target_level'] == 'parent') and (c['target_semantics'] == 'set'), 'frozen_test_semantic_axis')
                contract.need(c['record_id'] == cohort_ledger[iid]['record_id'] and c['connectivity_id'] == cohort_ledger[iid]['connectivity_sha256'], 'saved_source_identity')
                if row.metric == 'compatible_observation':
                    key = (iid, method, row.observation_id)
                    contract.need(key not in expected_applications, 'duplicate_saved_compatible_application')
                    semantic = dict(method=method, nucleus=c['nucleus'], truth_basis=c['truth_basis'], task_semantics=c['task_semantics'], target_level=c['target_level'], target_semantics=c['target_semantics'], endpoint='per_peak_compatibility', sampling_unit='observation')
                    expected_applications[key] = dict(semantic_axis=semantic, pipeline_available=bundle.get('pipeline_status') is not None)
                rows.append(row)
    applied = json.loads(saved('frozen_Cval_threshold_application.json').read_text())
    used[suite['Cval_frozen_calibration']['path']] = suite['Cval_frozen_calibration']['sha256']
    application_validation = validate_threshold_applications(applied, expected_applications, contract.load(suite['Cval_frozen_calibration']))
    metrics = estimate_native_test(rows, helper)
    out = Path(config['output_directory'])
    contract.need(not out.exists(), 'new_report_directory')
    out.mkdir(parents=True, exist_ok=False)
    coverage = dict(original_C_identity_denominator=binding('TEST_STAGE_B_report.frozen_identity_count.3'), public_scoring_queue=len(queue), public_unavailable_unknown=binding('TEST_STAGE_B_report.frozen_identity_count.4') - len(queue), all_source_identity_rows=a['full_C'], H_original_identity_denominator=binding('TEST_STAGE_B_report.frozen_identity_count.5'), H_assignment_status='unavailable_no_model_no_assignment_metrics', cache_lifecycle_counts=dict(cache_status), raw_execution_status_counts=dict(status), cache_failed_gold_denominator_policy='Retained saved eligible rows; no replacement/retry; source unknown never minted observations')
    result = dict(schema='TEST_STAGE_B_native_test_report_v1', status='FROZEN_TEST_REPORT_PENDING_INDEPENDENT_ACTUAL_APPLICATION_AUDIT', source_relative_only=True, native_test=metrics, coverage=coverage, highconfidence=dict(published=0, application_validation=application_validation, stored_statuses_preserved=True, Cval_artifact_sha256=suite['Cval_frozen_calibration']['sha256'], Cval_actual_review_sha256=suite['Cval_actual_application_review']['sha256'], test_fit_calls=0), input_hashes=used, new_models=0, new_solves=0, new_gold_evaluations=0, new_mapping_search=0, no_test_threshold_reselection=True)
    for p, h in used.items():
        contract.need(contract.sha(p) == h, 'post_saved_output_SHA')
    contract.write(out / 'report.json', result)
    contract.write(out / 'report_receipt.json', dict(status=result['status'], report_sha256=contract.sha(out / 'report.json'), scoring_manifest_sha256=config['completed_scoring_manifest']['sha256'], scoring_inventory_sha256=config['scoring_output_inventory']['sha256'], source_suite_sha256=suite_item['sha256'], used_output_sha256=used, new_threshold_fit=0, new_models=0, new_solves=0))
    return result

def main():
    authorize()
    p = argparse.ArgumentParser()
    p.add_argument('--plan')
    p.add_argument('--plan-sha256')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not a.execute:
        print(json.dumps(contract.contract(), indent=2))
        return
    cfgitem = dict(path=a.plan, sha256=a.plan_sha256)
    cfg = contract.load(cfgitem)
    report(cfgitem, cfg['suite_manifest'], cfg['owner_suite_release'])
if __name__ == '__main__':
    main()
