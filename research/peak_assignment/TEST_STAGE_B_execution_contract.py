# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：Stage B执行合同增量层；保留已锁四组件，新增分阶段资源、实际闭包和一次授权连接。
claim_phase以suite/owner绑定root及release_id+phase原子占用；preparation独立once，空队列也占prediction执行claim。
suite只绑定A实际完成/source PASS及已审代码、数字、原Cval发布off；不包含未来cache产物SHA。
phase manifest在前序实际产物/独审后单独冻结，监督层只启动此manifest构造的固定argv。
prepare_prediction复用builder5f与原220源码/nomination/countassets；仅A.public→结构实际条件，H不推理。
默认打印metadata合同，不读取真实test；所有实际入口须A完整/source独审、精确suite和owner B release。
"""
import argparse, hashlib, json, math, os, shutil, sys
from pathlib import Path
import TEST_STAGE_B_control as component
D = workspace()
BUILDER_SHA = binding('TEST_STAGE_B_execution_contract.exact_SHA_or_identity.1')
C_CKPT = binding('TEST_STAGE_B_execution_contract.exact_SHA_or_identity.2')
NOM_SHA = binding('TEST_STAGE_B_execution_contract.exact_SHA_or_identity.3')
ESTIMATOR_SHA = binding('TEST_STAGE_B_execution_contract.exact_SHA_or_identity.4')
LOCKED = {'TEST_STAGE_B_control.py': binding('TEST_STAGE_B_execution_contract.exact_SHA_or_identity.5'), 'TEST_STAGE_B_package.py': binding('TEST_STAGE_B_execution_contract.exact_SHA_or_identity.6'), 'TEST_STAGE_B_C_caller.py': binding('TEST_STAGE_B_execution_contract.exact_SHA_or_identity.7'), 'TEST_STAGE_B_tests.py': binding('TEST_STAGE_B_execution_contract.exact_SHA_or_identity.8')}
BUDGETS = {'prediction': dict(CPU_threads=2, GPU=0, RSS_bytes=8589934592, total_wall_seconds=900, record_workers=1, cleanup_seconds=60), 'package': dict(CPU_threads=1, GPU=0, RSS_bytes=8589934592, total_wall_seconds=300, record_workers=1, cleanup_seconds=60), 'score': dict(CPU_threads=1, GPU=0, RSS_bytes=8589934592, total_wall_seconds=7200, record_workers=1, cleanup_seconds=60), 'report': dict(CPU_threads=1, GPU=0, RSS_bytes=8589934592, total_wall_seconds=600, record_workers=1, cleanup_seconds=60)}
need = component.need
sha = component.sha
digest = component.digest
bound = component.bound
load = component.load

def item(p):
    return dict(path=str(Path(p).resolve()), sha256=sha(p), bytes=Path(p).stat().st_size)

def write(p, v):
    with Path(p).open('x') as f:
        json.dump(v, f, ensure_ascii=False, allow_nan=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())

def same_item(left, right):
    return isinstance(left, dict) and isinstance(right, dict) and (left.get('sha256') == right.get('sha256')) and (Path(left['path']).resolve() == Path(right['path']).resolve())

def verify_locked():
    for n, h in LOCKED.items():
        need(sha(artifact_path(n)) == h, 'locked_component_drift:' + n)

def claim_phase(suite_item, release_item, phase, *, scope='execution'):
    """suite/release绑定的持久原子claim；失败不删除，更换监督/输出目录无效。"""
    need(phase in BUDGETS and scope in ('execution', 'preparation'), 'once_phase_scope')
    suite = load(suite_item)
    release = load(release_item)
    root = Path(suite['once_claim_root'])
    need(root.is_absolute() and str(root) == release.get('once_claim_root'), 'owner_suite_once_root_binding')
    need(suite.get('execution_authorized') is True and release.get('schema') == 'original_owner_test_stage_B_execution_release_v1' and (release.get('decision') == 'ALLOW_ONCE_C_FIXED_TEST_STAGE_B') and (release.get('suite_manifest_sha256') == suite_item['sha256']) and (release.get('no_retry') is True) and isinstance(release.get('release_id'), str) and release['release_id'], 'once_exact_suite_release')
    root.mkdir(parents=True, exist_ok=True)
    need(root.resolve() == root, 'once_root_no_symlink_alias')
    key = hashlib.sha256((release['release_id'] + '\x00' + phase + '\x00' + scope).encode()).hexdigest()
    path = root / (key + '.json')
    import datetime
    write(path, dict(schema='TEST_STAGE_B_persistent_once_claim_v1', suite_manifest_sha256=suite_item['sha256'], owner_release_sha256=release_item['sha256'], release_id=release['release_id'], phase=phase, scope=scope, claimed_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(), claim_PID=os.getpid(), retained_on_all_failures=True))
    return item(path)

def bind_suite(suite_item, release_item):
    suite = load(suite_item)
    release = load(release_item)
    verify_locked()
    need(suite['schema'] == 'TEST_STAGE_B_execution_suite_v1' and suite['execution_authorized'] is True, 'suite_not_released')
    need(release.get('schema') == 'original_owner_test_stage_B_execution_release_v1' and release.get('decision') == 'ALLOW_ONCE_C_FIXED_TEST_STAGE_B', 'owner_B_once_execution_release')
    need(release.get('suite_manifest_sha256') == suite_item['sha256'] and release.get('C_fixed_identity_count') == binding('TEST_STAGE_B_execution_contract.frozen_identity_count.9') and (release.get('H_fixed_identity_count') == binding('TEST_STAGE_B_execution_contract.frozen_identity_count.10')), 'suite_release_domain')
    need(release.get('no_retry') is True and release.get('owner_authorization_evidence_sha256') and release.get('release_id'), 'owner_B_once_evidence')
    need(Path(suite['once_claim_root']).is_absolute() and suite['once_claim_root'] == release.get('once_claim_root'), 'owner_suite_once_root_binding')
    need(suite['budget'] == BUDGETS and set(suite['authorized_phases']) == set(BUDGETS), 'frozen_phase_budgets')
    required = {'execution_contract': artifact_path('TEST_STAGE_B_execution_contract.py'), 'phase_supervisor': artifact_path('TEST_STAGE_B_phase_supervisor.py'), 'report_adaptor': artifact_path('TEST_STAGE_B_report.py'), 'locked_control': artifact_path('TEST_STAGE_B_control.py'), 'locked_package': artifact_path('TEST_STAGE_B_package.py'), 'locked_caller': artifact_path('TEST_STAGE_B_C_caller.py'), 'builder': artifact_path('build_frozen_prediction_cache.py'), 'estimators': artifact_path('frozen_report_estimators.py'), 'base_caller': artifact_path('run_frozen_C_assignment_baselines.py'), 'base_packager': artifact_path('prepare_C_scoring_artifacts.py')}
    need(set(required) <= set(suite['implementations']), 'execution_runtime_code_closure_required')
    for name, it in suite['implementations'].items():
        bound(it)
    for name, path in required.items():
        need(Path(suite['implementations'][name]['path']).resolve() == path.resolve(), 'runtime_code_path:' + name)
    need(suite['implementations']['builder']['sha256'] == BUILDER_SHA and suite['implementations']['estimators']['sha256'] == ESTIMATOR_SHA, 'frozen_builder_estimator')
    need(release['implementation_sha256'] == {n: v['sha256'] for n, v in suite['implementations'].items()}, 'owner_exact_code_closure')
    review = load(suite['execution_contract_independent_review'])
    fields = suite['execution_review_fields']

    def at(v, path):
        for k in path:
            v = v[k]
        return v
    need(str(at(review, fields['decision'])).startswith('PASS'), 'execution_contract_not_component_PASS')
    need(at(review, fields['source_sha256']) == {n: v['sha256'] for n, v in suite['implementations'].items()}, 'execution_review_exact_closure')
    a = component.bind_stage_A(suite['stage_A_binding'])
    H_rows = [v for v in a['data']['ledger'] if v['nucleus'] == '1H']
    need(len(H_rows) == binding('TEST_STAGE_B_execution_contract.frozen_identity_count.11') and all((v['public_available'] is False and v['reference_admitted'] is False for v in H_rows)), 'H1371_unavailable_no_inference')
    need(suite['phase_python']['prediction'] == suite['prediction_python'], 'prediction_python_consistency')
    need(suite['numeric_config']['sha256'] == a['extraction']['numeric_config']['sha256'], 'suite_numeric_fixed_before_test')
    bound(suite['numeric_config'])
    frozen = load(suite['Cval_frozen_calibration'])
    frozen = frozen if isinstance(frozen, list) else frozen['axes']
    need(suite['Cval_frozen_calibration']['sha256'] == a['extraction']['validation']['C']['threshold_artifact']['sha256'], 'A_B_identical_Cval_threshold_artifact')
    need(all((v.get('status') != 'on_audit_passed' and (not v.get('published_ids')) for v in frozen)), 'frozen_highconfidence_must_stay_off')
    rule = load(suite['Cval_scoring_rule_contract'])
    need(suite['Cval_scoring_rule_contract']['sha256'] == binding('TEST_STAGE_B_execution_contract.exact_SHA_or_identity.12') and rule['numeric_config']['sha256'] == suite['numeric_config']['sha256'] and all((v['axis']['rule_sha256'] == suite['Cval_scoring_rule_contract']['sha256'] for v in frozen)), 'suite_original_Cval_rule_numeric_binding')
    cr = load(suite['Cval_actual_application_review'])
    cf = suite['Cval_review_fields']
    need(str(at(cr, cf['decision'])).startswith('PASS') and at(cr, cf['calibration_artifacts_sha256']) == suite['Cval_frozen_calibration']['sha256'] and (at(cr, cf['validation_result_sha256']) == a['extraction']['validation']['C']['validation_result']['sha256']), 'Cval_actual_review_exact_off_artifact')
    return (suite, a)

def canonical_argv(phase, config, config_item):
    python = config['python_executable']
    need(Path(python).is_absolute(), 'explicit_python')
    if phase == 'prediction':
        b = bound(config['builder'])
        need(sha(b) == BUILDER_SHA, 'builder5f_required')
        for key in ('cohort', 'assets', 'builder_plan'):
            bound(config[key])
        return with_runtime([python, '-B', str(b), '--cohort', config['cohort']['path'], '--cohort-sha256', config['cohort']['sha256'], '--assets-manifest', config['assets']['path'], '--assets-sha256', config['assets']['sha256'], '--plan', config['builder_plan']['path'], '--plan-sha256', config['builder_plan']['sha256'], '--out', config['output_directory']])
    entry = {'package': 'TEST_STAGE_B_package.py', 'score': 'TEST_STAGE_B_C_caller.py', 'report': 'TEST_STAGE_B_report.py'}[phase]
    it = config['entrypoint']
    p = bound(it)
    need(p == Path(artifact_path(entry)).resolve(), 'fixed_phase_entrypoint')
    if phase in ('package', 'score'):
        return with_runtime([python, '-B', str(p), '--plan', config['delegate_plan']['path'], '--plan-sha256', config['delegate_plan']['sha256'], '--owner-release', config['delegate_owner_release']['path'], '--owner-release-sha256', config['delegate_owner_release']['sha256'], '--execute'])
    return with_runtime([python, '-B', str(p), '--plan', config_item['path'], '--plan-sha256', config_item['sha256'], '--execute'])

def validate_phase(suite_item, release_item, phase_item):
    suite, a = bind_suite(suite_item, release_item)
    phase = load(phase_item)
    need(phase['schema'] == 'TEST_STAGE_B_execution_phase_v1' and phase['execution_authorized'] is True, 'phase_manifest')
    name = phase['phase']
    need(name in BUDGETS and phase['suite_manifest_sha256'] == suite_item['sha256'], 'phase_suite_binding')
    need(phase['budget'] == BUDGETS[name], 'phase_budget_unchanged')
    config_item = phase['config']
    config = load(config_item)
    queue = a['queue']
    need(config['ordered_input_ids'] == queue and config['original_C_identity_count'] == binding('TEST_STAGE_B_execution_contract.frozen_identity_count.13'), 'dynamic_A_queue_original3637')
    need(config['stage_A_receipt_sha256'] == suite['stage_A_binding']['stage_A_output_manifest']['sha256'], 'phase_A_actual_binding')
    need(not Path(config['output_directory']).exists(), 'phase_new_output_only')
    need(config['python_executable'] == suite['phase_python'][name], 'phase_python_frozen')
    if name != 'prediction':
        source_name = {'package': 'locked_package', 'score': 'locked_caller', 'report': 'report_adaptor'}[name]
        need(config['entrypoint']['sha256'] == suite['implementations'][source_name]['sha256'], 'phase_entrypoint_reviewed_source')
    if name == 'prediction':
        need(config['expected_H_model_loads'] == 0 and config['expected_C_model_loads'] == int(bool(queue)), 'C_only_model_load')
        bp = load(config['builder_plan'])
        need(bp['wall_seconds_total'] == 900 and bp['CPU_threads'] == 2 and (bp['GPU_devices'] == 0) and (bp['RSS_limit_bytes'] == 8589934592) and (bp['input_count'] == len(queue)) and (bp['max_forward_started'] == len(queue)), 'dynamic_cache_budget')
        need(bp['load_seconds_per_model'] + bp['forward_seconds_per_model'] <= 900, 'shared_load_forward900')
        public = list(component.rows(bound(config['cohort'])))
        need([r['input_id'] for r in public] == queue and public == [component.cache_public(a['public'][iid]) for iid in queue], 'A_public_only_no_hidden_model_inputs')
        assets = load(config['assets'])
        need(assets['runner_sha256'] == BUILDER_SHA, 'cache_builder_asset_SHA')
        nom = load(assets['files']['nomination'])
        need(assets['files']['nomination']['sha256'] == NOM_SHA and nom['C']['sha256'] == C_CKPT, 'fixed_C_nomination')
        need(len(assets['source_files']) == 220 and assets['source_files'] == suite['prediction_source_files'], 'same_native220_closure')
        need(assets['files']['numeric_config']['sha256'] == suite['numeric_config']['sha256'], 'same_prediction_numeric')
        scope = load(assets['files']['scope_release'])
        need(scope['checkpoint_sha256'] == {'1H': nom['H']['sha256'], '13C': C_CKPT} and scope['cohort_sha256'] == config['cohort']['sha256'] and (scope['production_cache_authorized'] is True), 'builder_scope_exact_models_cohort')
    elif name in ('package', 'score'):
        dp = load(config['delegate_plan'])
        bound(config['delegate_owner_release'])
        need(dp['output_directory'] == config['output_directory'], 'delegate_output_directory')
        need(dp['stage_A_output_manifest']['sha256'] == suite['stage_A_binding']['stage_A_output_manifest']['sha256'], 'delegate_same_A')
        if name == 'package':
            component.bind_cache_review(dp, queue)
        else:
            pm = load(dp['packaging_manifest'])
            rv = load(dp['packaging_application_review'])
            need(pm['scorequeue'] == len(queue) and pm['original_identity_denominator'] == binding('TEST_STAGE_B_execution_contract.frozen_identity_count.14') and (rv['packaging_manifest_sha256'] == dp['packaging_manifest']['sha256']) and str(rv['decision']).startswith('PASS'), 'score_requires_actual_package_PASS')
            need(dp['Cval_frozen_calibration']['sha256'] == suite['Cval_frozen_calibration']['sha256'], 'score_frozen_off_artifact')
            need(same_item(dp['Cval_scoring_rule_contract'], suite['Cval_scoring_rule_contract']), 'score_same_Cval_rule_contract')
    else:
        need(same_item(config['suite_manifest'], suite_item) and same_item(config['owner_suite_release'], release_item), 'report_same_owner_suite')
        need(config['estimators']['sha256'] == ESTIMATOR_SHA, 'report_frozen_estimators')
        actual = load(config['scoring_actual_supervisor_receipt'])
        need(actual.get('actual_inner_exit') == actual.get('actual_worker_exit') == actual.get('actual_outer_exit') == 0 and actual.get('last_worker_stage') == 'inventory_completed' and (actual.get('child_output_inventory', {}).get('sha256') == config['scoring_output_inventory']['sha256']), 'report_actual_final_score_exit_inventory')
        completed = load(config['completed_scoring_manifest'])
        need(completed['status'] == 'FROZEN_ASSIGNMENT_EXECUTION_COMPLETED' and completed['input_records'] == len(queue) and (completed['original_identity_denominator'] == binding('TEST_STAGE_B_execution_contract.frozen_identity_count.15')), 'report_completed_dynamic_queue')
    return (suite, a, phase, config, canonical_argv(name, config, config_item))

def prepare_prediction(suite_item, release_item, out):
    suite, a = bind_suite(suite_item, release_item)
    preparation_claim = claim_phase(suite_item, release_item, 'prediction', scope='preparation')
    out = Path(out)
    need(not out.exists(), 'new_prediction_preparation')
    out.mkdir(parents=True, exist_ok=False)
    coverage = dict(original_C_identity_count=binding('TEST_STAGE_B_execution_contract.frozen_identity_count.16'), C_rows=a['full_C'], H_original_fixed_count=binding('TEST_STAGE_B_execution_contract.frozen_identity_count.17'), H_assignment='unavailable_no_model_no_fake_peaks', H_rows=[r for r in a['data']['ledger'] if r['nucleus'] == '1H'])
    write(out / 'fixed_source_identity_coverage.json', coverage)
    public = out / 'C_public_cache.jsonl'
    with public.open('x') as f:
        for iid in a['queue']:
            f.write(json.dumps(component.cache_public(a['public'][iid]), ensure_ascii=False, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    if not a['queue']:
        execution_claim = claim_phase(suite_item, release_item, 'prediction')
        result = out / 'result'
        result.mkdir()
        for name in ('predictions.jsonl', 'inputs.jsonl'):
            with (result / name).open('xb') as f:
                f.flush()
                os.fsync(f.fileno())
        receipt = dict(once_claim=execution_claim, preparation_claim=preparation_claim, schema='TEST_STAGE_B_empty_cache_actual_v1', status='EMPTY_QUEUE_NO_INFERENCE_PENDING_APPLICATION_AUDIT', source_identity_count=binding('TEST_STAGE_B_execution_contract.frozen_identity_count.18'), H_unavailable=binding('TEST_STAGE_B_execution_contract.frozen_identity_count.19'), input_count=0, H_model_loads=0, C_model_loads=0, forward_started=0, forward_completed=0, forward_validated=0, child_started=False, actual_inner_exit=None, actual_outer_exit=0, no_retry=True, source_suite_sha256=suite_item['sha256'], stage_A_receipt_sha256=suite['stage_A_binding']['stage_A_output_manifest']['sha256'], output_sha256={n: item(result / n) for n in ('predictions.jsonl', 'inputs.jsonl')})
        write(result / 'receipt.json', receipt)
        return dict(status=receipt['status'], coverage=item(out / 'fixed_source_identity_coverage.json'), receipt=item(result / 'receipt.json'), cache_predictions=item(result / 'predictions.jsonl'), cache_inputs=item(result / 'inputs.jsonl'), actual_cache_application_review_still_required=True)
    template = load(suite['prediction_asset_template'])
    need(template['source_files'] == suite['prediction_source_files'], 'frozen_template_source_closure')
    source = Path(template['bundle_root'])
    bundle = out / 'source_bundle'
    shutil.copytree(source, bundle, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for rel, h in template['source_files'].items():
        need(sha(bundle / rel) == h, 'copied_source_closure:' + rel)
    builder = bound(suite['builder'])
    need(sha(builder) == BUILDER_SHA, 'frozen_builder')
    need(builder.resolve() == (Path(__file__).resolve().parent / 'build_frozen_prediction_cache.py').resolve(), 'public_builder_dependency_closure_path')
    assets = dict(template, bundle_root=str(bundle.resolve()), runner_sha256=BUILDER_SHA, files=dict(template['files']))
    scope_path = out / 'prediction_scope.json'
    nom = load(template['files']['nomination'])
    write(scope_path, dict(schema='prediction_cache_scope_release_v1', production_cache_authorized=True, cohort_sha256=sha(public), checkpoint_sha256={'1H': nom['H']['sha256'], '13C': C_CKPT}, only_nucleus='13C', input_count=len(a['queue']), H_loads_max=0, C_loads_max=int(bool(a['queue'])), owner_suite_sha256=suite_item['sha256']))
    assets['files']['scope_release'] = item(scope_path)
    write(out / 'assets.json', assets)
    bp = dict(schema='frozen_prediction_cache_plan_v1', execution_authorized=True, CPU_threads=2, GPU_devices=0, RSS_limit_bytes=8589934592, python_executable=suite['prediction_python'], wall_seconds_total=900, load_seconds_per_model=300, forward_seconds_per_model=600, max_forward_started=len(a['queue']), input_count=len(a['queue']), expected_H_model_loads=0, expected_C_model_loads=int(bool(a['queue'])), outer_cleanup_max_seconds=60, retries=0)
    write(out / 'builder_plan.json', bp)
    config = dict(preparation_claim=preparation_claim, schema='TEST_STAGE_B_prediction_phase_config_v1', python_executable=suite['prediction_python'], ordered_input_ids=a['queue'], original_C_identity_count=binding('TEST_STAGE_B_execution_contract.frozen_identity_count.20'), stage_A_receipt_sha256=suite['stage_A_binding']['stage_A_output_manifest']['sha256'], expected_H_model_loads=0, expected_C_model_loads=1, builder=item(builder), cohort=item(public), assets=item(out / 'assets.json'), builder_plan=item(out / 'builder_plan.json'), output_directory=str(out / 'result'))
    write(out / 'prediction_phase_config.json', config)
    phase = dict(schema='TEST_STAGE_B_execution_phase_v1', execution_authorized=True, phase='prediction', suite_manifest_sha256=suite_item['sha256'], budget=BUDGETS['prediction'], config=item(out / 'prediction_phase_config.json'))
    write(out / 'prediction_phase.json', phase)
    return dict(status='PREDICTION_METADATA_PREPARED_NO_CHILD_STARTED', phase=item(out / 'prediction_phase.json'), future_cache_SHA_required=False)

def contract():
    return dict(schema='TEST_STAGE_B_execution_contract_v1', status='PREPARATION_ONLY_COMPONENT_PASS_NOT_EXECUTION_READY', budgets=BUDGETS, original_C=binding('TEST_STAGE_B_execution_contract.frozen_identity_count.21'), original_H_unavailable=binding('TEST_STAGE_B_execution_contract.frozen_identity_count.22'), queue='actual A source-admitted public order <=3637', phase_order=['actualA+sourcePASS+owneronce', 'prediction once', 'actualcache applicationPASS', 'package', 'packagePASS', 'score once', 'frozen report'], cache_source='builder5f + same native220 + fixedC d968 + same nomination/config/assets', calibration='reviewed stored off mandatory; no testfit/reselect', release='suite SHA has no future cache SHA; actual downstream artifacts bound only after prior phase; delegated locked releases remain explicit external files', actual_execution_authorized=False, once_scope='required absolute canonical once_claim_root equal in suite and owner release; release_id+phase atomic execution claim retained on success/failure; separate once preparation; empty prediction consumes execution claim', outer_boundary='phase-name selects fixed budget before manifest reads; preflight worker and output inventory share active wall/RSS; final outer receipt after inventory/cleanup')

def main():
    authorize()
    p = argparse.ArgumentParser()
    p.add_argument('--suite')
    p.add_argument('--suite-sha256')
    p.add_argument('--owner-release')
    p.add_argument('--owner-release-sha256')
    p.add_argument('--prepare-prediction')
    a = p.parse_args()
    if not a.prepare_prediction:
        print(json.dumps(contract(), indent=2))
        return
    r = prepare_prediction(dict(path=a.suite, sha256=a.suite_sha256), dict(path=a.owner_release, sha256=a.owner_release_sha256), a.prepare_prediction)
    print(json.dumps(r, indent=2))
if __name__ == '__main__':
    main()
