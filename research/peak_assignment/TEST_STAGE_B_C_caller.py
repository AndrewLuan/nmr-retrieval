# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：Stage B独立native_test C B0/B1/B2入口；不调用Cval的run/check_plan。
逐记录执行段从冻结Cval caller原文继承，保持10/2/2/5/1、candidate50000、真实bytes/证书/失败分母。
check_plan绑定实际A闭包、已审cache及打包应用、root唯一baseline release；C3637总账与A派生队列均保留。
bind_Cval_rule_contract显式读取原35ea规则文件，核其numeric引用等于当前/A的012f，再核artifact axis.rule；不把两类SHA混用。
test只可apply原Cval已审frozen threshold，同完整语义轴不符/缺artifact则off；本文件无calibrate/fit/bootstrap。
默认check-only只展示接口，无真实test读取；--execute在将来的完整放行后才可运行一次，不部署、不重跑。
"""
import argparse, json, os, resource, sys, time, hashlib, math
from pathlib import Path
from dataclasses import asdict, replace
import TEST_STAGE_B_control as ctl
D = workspace()
REPO = repository()
METHODS = ('B0', 'B1', 'B2')
OWNER_RELEASE = None
BASE = ctl.load_base('run_frozen_C_assignment_baselines.py', ctl.BASE_CALLER_SHA)
FROZEN_EXECUTION_SHA = BASE.FROZEN_EXECUTION_SHA
FROZEN_EVALUATION_SHA = BASE.FROZEN_EVALUATION_SHA
sha = ctl.sha
durable = BASE.durable
load_adapter = BASE.load_adapter
bound_snapshot = BASE.bound_snapshot
anonymous_payload = BASE.anonymous_payload
strip_late_support = BASE.strip_late_support
evaluate_one = BASE.evaluate_one

def digest(v):
    return ctl.digest(v)

def bind_source_cohort(plan, packaging, data, stage_A):
    """Reject cohort drift before initial evaluate_one; never turn bad gold into zero eligible."""
    cohort = packaging.get('source_cohort_sha256')
    ids = plan['input_ids']
    if not ids:
        item = plan.get('stage_A_derived_C_context')
        context = ctl.load(item)
        value = stage_A['source_review']
        path = plan.get('stage_A_derived_C_context_review_path')
        ctl.need(isinstance(path, list) and path, 'empty_queue_A_cohort_review_binding_required')
        for key in path:
            value = value[key]
        ctl.need(value == item['sha256'], 'empty_queue_A_cohort_actual_review_SHA')
        text = context['cohort_text']
        derived = context['cohort_sha256']
        ctl.need(hashlib.sha256(text.encode()).hexdigest() == derived, 'A_derived_cohort_text_SHA')
        declared = json.loads(text)
        ctl.need(declared.get('native_partition') == 'test' and declared.get('native_role') == 'native_test' and (declared.get('nucleus_scope') == '13C') and (len(declared.get('records', [])) == binding('TEST_STAGE_B_C_caller.frozen_identity_count.1')), 'A_derived_C3637_cohort_scope')
        ctl.need(cohort == derived, 'empty_queue_package_cohort_must_equal_reviewed_A_derived_cohort')
    ctl.need(isinstance(cohort, str) and len(cohort) == 64 and all((c in '0123456789abcdef' for c in cohort)), 'package_source_cohort_actual_SHA_required')
    ctl.need(plan.get('source_cohort_sha256') == cohort, 'plan_package_source_cohort_SHA_mismatch')
    for iid in ids:
        ctl.need(data['gold'][iid]['binding'].get('cohort_identity_manifest_sha256') == cohort, 'gold_package_source_cohort_SHA_mismatch:' + iid)
    return cohort
CVAL_RULE_CONTRACT_SHA = binding('TEST_STAGE_B_C_caller.exact_SHA_or_identity.2')

def bind_Cval_rule_contract(plan, artifacts, stage_A):
    """绑定原Cval规则文件35ea与其numeric012f引用；二者语义及字节SHA分开。"""
    item = plan.get('Cval_scoring_rule_contract')
    ctl.need(isinstance(item, dict) and item.get('sha256') == CVAL_RULE_CONTRACT_SHA, 'original_Cval_rule_contract_SHA_required')
    rule = ctl.load(item)
    numeric_sha = plan['inputs']['numeric_config']['sha256']
    ctl.need(rule.get('nucleus') == '13C' and rule.get('numeric_config', {}).get('sha256') == numeric_sha == stage_A['extraction']['numeric_config']['sha256'], 'Cval_rule_numeric_current_A_binding')
    ctl.need(all((a.get('axis', {}).get('rule_sha256') == item['sha256'] for a in artifacts)), 'same_calibration_rule_contract_snapshot')
    return item['sha256']

def check_plan(path, expected_sha):
    ctl.need(expected_sha and sha(path) == expected_sha, 'test_plan_SHA')
    plan = json.loads(Path(path).read_text())
    ctl.need(plan['schema'] == 'TEST_STAGE_B_C_baseline_plan_v1' and plan['allow_test'] is True and (tuple(plan['methods']) == METHODS), 'test_specific_plan_scope')
    ctl.stage_B_release(OWNER_RELEASE, expected_sha, 'baseline_once', sha(__file__))
    global REPO
    REPO = repository()
    sys.path.insert(0, str(REPO))
    os.environ['PYTHONPATH'] = str(REPO)
    for item in plan['implementations']:
        ctl.bound(item)
    for item in plan['inputs'].values():
        ctl.bound(item)
    pm = ctl.load(plan['packaging_manifest'])
    ctl.need(pm['schema'] == 'TEST_STAGE_B_C_packaging_v1' and pm['status'] == 'PACKAGED_NO_BASELINE_SCORES', 'B_packaging_actual')
    a = ctl.bind_stage_A(plan)
    ctl.need(plan['input_ids'] == a['queue'] and len(a['ordered_C_ids']) == binding('TEST_STAGE_B_C_caller.frozen_identity_count.3'), 'B_original_A_queue_order')
    ctl.need(pm['ordered_input_ids_sha256'] == digest(a['queue']) and pm['ordered_full_identity_ids_sha256'] == digest(a['ordered_C_ids']), 'B_package_identity_binding')
    ctl.need(pm['stage_A_receipt_sha256'] == plan['stage_A_output_manifest']['sha256'] and pm['source_application_review_sha256'] == plan['stage_A_actual_admission_review']['sha256'], 'B_packaged_source_chain')
    review = ctl.load(plan['packaging_application_review'])
    ctl.need(str(review.get('decision', '')).startswith('PASS') and review.get('packaging_manifest_sha256') == plan['packaging_manifest']['sha256'], 'B_packaging_application_PASS')
    for name, item in pm['inputs'].items():
        ctl.need(name in plan['inputs'] and item['sha256'] == plan['inputs'][name]['sha256'], 'B_packaged_input_closure:' + name)
    for name in ('evaluation_adapter', 'numeric_config'):
        ctl.bound(plan['inputs'][name])
    ctl.need(plan['inputs']['numeric_config']['sha256'] == a['extraction']['numeric_config']['sha256'], 'no_test_numeric_change')
    from nmr_assignment.execution import numeric_config_from_frozen
    config = json.loads(Path(plan['inputs']['numeric_config']['path']).read_text())
    numeric = numeric_config_from_frozen(config)
    b = numeric['budgets']
    ctl.need([b[k] for k in ('per_record_wall_seconds', 'mapping_and_candidates_seconds', 'B1_solver_seconds', 'B2_solver_seconds', 'result_validation_reserve_seconds', 'max_candidates_per_global_problem')] == [10, 2, 2, 5, 1, 50000], 'fixed_original_numeric_budgets')
    data = {n: BASE.index(plan['inputs'][n]['path']) for n in ('public', 'gold', 'ledger', 'admissions', 'cache_input_ledger', 'predictions', 'lineages', 'coverage_ledger')}
    bind_source_cohort(plan, pm, data, a)
    ids = set(plan['input_ids'])
    for n in ('public', 'gold', 'ledger', 'admissions', 'cache_input_ledger'):
        ctl.need(set(data[n]) == ids, 'test_package_full_queue:' + n)
    ctl.need(set(data['predictions']) <= ids and set(data['lineages']) <= ids, 'no_foreign_prediction')
    ctl.need(list(data['coverage_ledger']) == a['ordered_C_ids'], 'full_test3637_order')
    for iid in ids:
        ctl.need(data['ledger'][iid]['roles'] == ['native_test'] and data['cache_input_ledger'][iid]['roles'] == ['native_test'], 'test_role_only')
        ctl.need(data['public'][iid]['nucleus'] == '13C', 'C_only')
        ctl.need(data['cache_input_ledger'][iid]['status'] in ('ready', 'cache_failed'), 'retained_cache_failure')
    for iid in a['ordered_C_ids']:
        c = data['coverage_ledger'][iid]
        ctl.need(c['native_role'] == 'native_test' and c['public_available'] is (iid in ids), 'full_coverage_unchanged')
    plan['_frozen_calibration'] = []
    plan['_calibration_origin'] = None
    item = plan.get('Cval_frozen_calibration')
    if item is not None:
        origin = a['extraction']['validation']['C']
        ctl.need(item['sha256'] == origin['threshold_artifact']['sha256'], 'test_threshold_must_equal_preA_Cval_frozen_artifact')
        artifacts = ctl.load(item)
        artifacts = artifacts if isinstance(artifacts, list) else artifacts['axes']
        cr = ctl.load(plan['Cval_calibration_application_review'])
        paths = plan['Cval_review_fields']

        def at(obj, p):
            for k in p:
                obj = obj[k]
            return obj
        ctl.need(str(at(cr, paths['decision'])).startswith('PASS') and at(cr, paths['threshold_artifact_sha256']) == item['sha256'] and (at(cr, paths['validation_result_sha256']) == origin['validation_result']['sha256']), 'Cval_frozen_calibration_actual_review')
        bind_Cval_rule_contract(plan, artifacts, a)
        plan['_frozen_calibration'] = artifacts
    return (plan, data, config, numeric, None)

def apply_frozen_threshold(adapter, row, bundle, plan, numeric):
    off = dict(observation_id=row.observation_id, baseline=dict(row.context)['baseline'], publication_enabled=False, status='off_no_matching_reviewed_Cval_artifact', threshold=None, refit=False)
    if not plan['_frozen_calibration'] or row.metric != 'compatible_observation' or bundle.get('pipeline_status') is None:
        return off
    context = dict(row.context)
    semantic = dict(method=context['baseline'], nucleus=context['nucleus'], truth_basis=context['truth_basis'], task_semantics=context['task_semantics'], target_level=context['target_level'], target_semantics=context['target_semantics'], endpoint='per_peak_compatibility', sampling_unit='observation')
    matching = [a for a in plan['_frozen_calibration'] if all((a.get('axis', {}).get(k) == v for k, v in semantic.items()))]
    if len(matching) != 1:
        return off
    origin = matching[0]['axis']
    record = adapter.calibration_record_from_evaluation(row, bundle, cohort_sha256=origin['cohort_sha256'], source_sha256=origin['source_sha256'], label_sha256=origin['label_sha256'], rule_sha256=origin['rule_sha256'], relative_tolerance=numeric['tie_relative_tolerance'])
    axis = asdict(record.axis)
    gate = ctl.frozen_axis_gate(axis, plan['_frozen_calibration'])
    publish = gate['publication_enabled'] and record.gold_eligible and record.prediction_supported and record.margin_certified and (type(record.margin) in (int, float)) and math.isfinite(record.margin) and (record.margin > 0) and (record.margin >= gate['threshold'])
    return dict(off, **{k: v for k, v in gate.items() if k != 'publication_enabled'}, publication_enabled=bool(publish), frozen_threshold_available=gate['publication_enabled'], frozen_threshold_axis=axis, test_semantic_axis=semantic, margin=record.margin, margin_certified=record.margin_certified)

def run(plan_path, expected_sha):
    plan, data, config, numeric, policy = check_plan(plan_path, expected_sha)
    if not any((item['path'] == str(Path(__file__).resolve()) and item['sha256'] == sha(Path(__file__)) for item in plan['implementations'])):
        raise ValueError('frozen runner implementation SHA missing')
    if plan.get('execution_authorized') is not True or not expected_sha:
        raise ValueError('execution_authorized true and explicit frozen plan SHA required')
    if sha(REPO / 'nmr_assignment/execution.py') != FROZEN_EXECUTION_SHA or plan['inputs']['evaluation_adapter']['sha256'] != FROZEN_EVALUATION_SHA:
        raise ValueError('unified frozen producer/consumer source drift')
    adapter = load_adapter(plan['inputs']['evaluation_adapter']['path'])
    output = Path(plan['output_directory'])
    output.mkdir(exist_ok=False)
    (output / 'raw').mkdir()
    (output / 'evaluation').mkdir()
    durable(output / 'full_original_identity_coverage.json', dict(original_identity_denominator=binding('TEST_STAGE_B_C_caller.frozen_identity_count.4'), scorequeue=len(plan['input_ids']), public_unavailable=binding('TEST_STAGE_B_C_caller.frozen_identity_count.5') - len(plan['input_ids']), rows=[data['coverage_ledger'][i] for i in data['coverage_ledger']], unavailable_semantics='unknown_not_admitted_no_observations_no_solver_input'))
    from nmr_assignment.execution import execute_record
    from nmr_assignment.metrics import summarize
    start = time.monotonic()
    queue = [dict(input_id=iid, methods={m: 'not_started' for m in METHODS}, gold_artifact_sha256=plan['inputs']['gold']['sha256'], admission_artifact_sha256=plan['inputs']['admissions']['sha256']) for iid in plan['input_ids']]
    durable(output / 'initial_not_started_fixed_denominators.json', dict(queue=queue, fixed_gold_denominator_artifacts={k: plan['inputs'][k] for k in ('gold', 'admissions', 'ledger')}, policy='All queued identities remain in denominator even if no worker completion file exists.'))
    rows_by_partition = {'test': []}
    threshold_application_rows = []
    record_events = []
    from nmr_assignment.diagnostics import DiagnosticBudget
    for iid in plan['input_ids']:
        record_started = time.monotonic()
        record_deadline = record_started + numeric['budgets']['per_record_wall_seconds']
        preprocessing_deadline = min(record_started + numeric['budgets']['mapping_and_candidates_seconds'], record_deadline - numeric['budgets']['result_validation_reserve_seconds'])
        one = {name: {iid: data[name][iid]} if iid in data[name] else {} for name in ('public', 'gold', 'ledger', 'admissions', 'cache_input_ledger')}
        cache_state = one['cache_input_ledger'][iid]
        pred = None
        payload = None
        payload_sha = None
        raw = dict(status=cache_state.get('status', 'not_started'), result=None, timed_out=False)
        initial_bundles = evaluate_one(adapter, iid, one, None, dict(status='not_started', result=None), plan=plan, approved_numeric_config=numeric)
        durable(output / 'evaluation' / (iid + '.not_started.json'), {m: [asdict(row) for row in b['rows']] for m, b in initial_bundles.items()})
        if cache_state.get('status') == 'ready':
            try:
                one['predictions'] = {iid: data['predictions'][iid]}
                one['lineages'] = {iid: data['lineages'][iid]}
                cache = one['predictions'][iid]
                lineage = one['lineages'][iid]['receipt']
                if cache.get('input_id') != iid or lineage['payload']['input_id'] != iid:
                    raise ValueError('cache input identity mismatch')
                snapshot = bound_snapshot(cache, lineage)
                payload, pred = anonymous_payload(one['public'][iid], cache['predictions'], snapshot, numeric)
                payload_sha = hashlib.sha256(payload).hexdigest()
                payload_path = output / 'raw' / (iid + '.payload.json')
                with payload_path.open('xb') as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                raw = execute_record(payload, approved_numeric_config=numeric, input_id=iid, prediction_artifact_sha256=lineage['payload']['prediction_artifact_sha256'], record_started_at=record_started, record_deadline=record_deadline, preprocessing_deadline=preprocessing_deadline)
            except Exception as exc:
                raw = dict(status='unsupported_cache_or_input', result=None, timed_out=False, detail=type(exc).__name__ + ':' + str(exc))
                pred = None
        if 'lineages' not in one:
            one['lineages'] = {}
        durable(output / 'raw' / (iid + '.json'), dict(input_id=iid, raw_execution=raw, anonymous_payload_sha256=payload_sha, cache_input_state=cache_state, record_started_at=record_started, record_deadline=record_deadline, preprocessing_deadline=preprocessing_deadline, plan_sha256=expected_sha))
        remaining = record_deadline - time.monotonic()
        evaluation_execution = raw if remaining > 0 else dict(status='total_deadline', result=None, timed_out=True, reason='late_read_parse_or_durable_consumer')
        budget = DiagnosticBudget(max_checks=50000, time_limit_seconds=min(0.25, max(1e-06, remaining)))
        bundles = evaluate_one(adapter, iid, one, pred, evaluation_execution, plan=plan, execution_payload=payload, approved_numeric_config=numeric, diagnostic_budget=budget)
        if time.monotonic() >= record_deadline:
            strip_late_support(bundles)
        partition = 'test'
        evaluated = {}
        for method, bundle in bundles.items():
            rows_by_partition[partition].extend(bundle['rows'])
            evaluated[method] = dict(rows=[asdict(r) for r in bundle['rows']], metadata=bundle['metadata'], pipeline_status=bundle['pipeline_status'])
            for row in bundle['rows']:
                if row.metric == 'compatible_observation':
                    threshold_application_rows.append(dict(input_id=iid, **apply_frozen_threshold(adapter, row, bundle, plan, numeric)))
        durable(output / 'evaluation' / (iid + '.json'), evaluated)
        record_events.append(dict(input_id=iid, status=raw['status'], partition=partition, roles=one['ledger'][iid]['roles'], record_elapsed_seconds=time.monotonic() - record_started, record_deadline_overshoot_seconds=max(0.0, time.monotonic() - record_deadline)))
        durable(output / 'record_completion_ledger.json', record_events)
    durable(output / 'frozen_Cval_threshold_application.json', threshold_application_rows)
    summaries = {partition: summarize(rows) for partition, rows in rows_by_partition.items()}
    final = dict(status='FROZEN_ASSIGNMENT_EXECUTION_COMPLETED', input_records=len(plan['input_ids']), original_identity_denominator=binding('TEST_STAGE_B_C_caller.frozen_identity_count.6'), public_unavailable=binding('TEST_STAGE_B_C_caller.frozen_identity_count.7') - len(plan['input_ids']), methods=METHODS, record_ledger=record_events, summaries=summaries, elapsed_seconds=time.monotonic() - start, plan_sha256=expected_sha, max_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024), calibration_fit_calls=0, frozen_Cval_apply_only=True, retry_count=0, actual_window_policy='unknown_None', model_forwards=0, test_inputs=len(plan['input_ids']))
    durable(output / 'manifest.json', final)
    print(json.dumps(final))

def main():
    authorize()
    p = argparse.ArgumentParser()
    p.add_argument('--plan')
    p.add_argument('--plan-sha256')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--owner-release')
    p.add_argument('--owner-release-sha256')
    a = p.parse_args()
    if not a.execute:
        print(json.dumps(ctl.contract(), indent=2))
        return
    for n in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[n] = '1'
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    global OWNER_RELEASE
    OWNER_RELEASE = dict(path=a.owner_release, sha256=a.owner_release_sha256)
    run(a.plan, a.plan_sha256)
if __name__ == '__main__':
    main()
