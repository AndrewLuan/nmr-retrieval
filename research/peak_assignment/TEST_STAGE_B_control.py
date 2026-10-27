# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：Stage B独立控制与I/O合同，直接接受已审Stage A的receipt/artifacts协议。
bind_stage_A只在真实A完整闭包及source独审后读取固定账本；C3637原序不变，public队列由A派生。
prediction_request不要求未来cache SHA；bind_cache_review只在一次预测之后绑定实际cache/独审，
随后package/caller才可进入。Stage A授权不放行B，owner release按阶段和精确plan/code绑定。
绑定原metadata-recovery bridge精确字节SHA，仅允许已审949外层源，保留五表和实际source独审检查。
默认仅check-only打印schema；不读真实test，不模型、不求解、不重拟合。合成测试复用本API。
"""
import argparse, hashlib, json, math, importlib.util
from pathlib import Path
D = workspace()
N = binding('TEST_STAGE_B_control.frozen_identity_count.1')
A_OUTER_SHA = binding('TEST_STAGE_B_control.exact_SHA_or_identity.2')
A_PROTOCOL_BRIDGE_SHA = binding('TEST_STAGE_B_control.exact_SHA_or_identity.3')
BASE_CALLER_SHA = binding('TEST_STAGE_B_control.exact_SHA_or_identity.4')
BASE_PACKAGER_SHA = binding('TEST_STAGE_B_control.exact_SHA_or_identity.5')
SEMANTIC_AXES = ('method', 'nucleus', 'truth_basis', 'task_semantics', 'target_level', 'target_semantics', 'endpoint', 'sampling_unit')

def need(ok, msg):
    if not ok:
        raise ValueError(msg)

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def bound(item):
    need(isinstance(item, dict) and item.get('path') and item.get('sha256'), 'pending_actual_artifact')
    p = Path(item['path'])
    need(sha(p) == item['sha256'], 'artifact_SHA:' + str(p))
    return p

def load(item):
    return json.loads(bound(item).read_text())

def rows(p):
    with Path(p).open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def unique(values, key='input_id'):
    out = {}
    for row in values:
        iid = row[key]
        need(iid not in out, 'duplicate_' + key)
        out[iid] = row
    return out

def read_artifacts(receipt, names, overrides=None):
    result = {}
    for name in names:
        item = receipt['artifacts'][name]
        actual = (overrides or {}).get(name, item)
        need(actual['sha256'] == item['sha256'], 'A_relocated_artifact_SHA:' + name)
        p = bound(actual)
        values = list(rows(p))
        need(len(values) == item['rows'], 'A_artifact_row_count:' + name)
        result[name] = values
    return result

def stage_B_release(item, plan_sha, phase, entry_sha):
    r = load(item)
    need(r.get('schema') == 'original_owner_test_stage_B_release_v1' and r.get('stage') == 'B' and (r.get('execution_authorized') is True), 'B_separate_owner_release')
    need(r.get('manifest_sha256') == plan_sha and r.get('entrypoint_sha256') == entry_sha, 'B_release_exact_plan_code')
    need(r.get('C_fixed_identity_count') == N and r.get('H_fixed_identity_count') == binding('TEST_STAGE_B_control.frozen_identity_count.6'), 'B_original_denominators')
    need(phase in r.get('authorized_phases', []) and r.get('no_retry') is True, 'B_phase_not_released')
    need(r.get('owner_authorization_evidence_sha256') and r.get('release_id'), 'B_owner_evidence')
    review = load(r['independent_implementation_review'])
    fields = r['implementation_review_fields']

    def at(obj, path):
        for key in path:
            obj = obj[key]
        return obj
    need(str(at(review, fields['decision'])).startswith('PASS') and at(review, fields['entrypoint_sha256']) == entry_sha, 'B_actual_implementation_review_exact_source')
    return r

def bind_stage_A(plan):
    a = load(plan['stage_A_output_manifest'])
    need(a.get('status') == 'complete' and a.get('exit_code') == 0 and (a.get('stage_B_authorized') is False), 'A_actual_complete_only')
    review = load(plan['stage_A_actual_admission_review'])
    need(str(review.get('decision', '')).startswith('PASS') and review.get('stage_A_output_manifest_sha256') == plan['stage_A_output_manifest']['sha256'], 'A_actual_source_review_binding')
    need(a.get('models') == a.get('solves') == a.get('scores') == 0, 'A_prediction_blind')
    outer = bound(plan['stage_A_outer'])
    need(sha(outer) == A_OUTER_SHA, 'A_reviewed_protocol_source')
    extraction = load(plan['stage_A_extraction_manifest'])
    need(plan['stage_A_extraction_manifest']['sha256'] == a['manifest_sha256'], 'A_actual_original_manifest')
    need(extraction['codes']['outer']['sha256'] == A_OUTER_SHA, 'A_actual_outer')
    for k in ('outer', 'C_test_producer', 'source_reference', 'source_transport'):
        need(a['codes'][k]['sha256'] == extraction['codes'][k]['sha256'], 'A_actual_source_code:' + k)
    bridge_item = plan.get('stage_A_protocol_bridge')
    need(isinstance(bridge_item, dict) and bridge_item.get('sha256') == A_PROTOCOL_BRIDGE_SHA, 'A_exact_metadata_recovery_bridge')
    bridge = load(bridge_item)
    closure = bridge['reviewed_stage_A_closure']
    need(bridge['decision'] == 'PASS_STAGE_A_METADATA_RECOVERY_CLOSURE_DELTA' and closure['code_sha256'] == {k: a['codes'][k]['sha256'] for k in ('outer', 'C_test_producer', 'source_reference', 'source_transport')}, 'A_bridge_actual_code_closure')
    need(closure['numeric_config_sha256'] == extraction['numeric_config']['sha256'] and closure['threshold_sha256']['C'] == extraction['validation']['C']['threshold_artifact']['sha256'], 'A_bridge_numeric_threshold')
    data = read_artifacts(a, ('ledger', 'public', 'unknown', 'lineage'), plan.get('stage_A_artifact_paths'))
    ledger = data['ledger']
    need(len(ledger) == binding('TEST_STAGE_B_control.frozen_identity_count.7'), 'A_H1371_C3637_denominator')
    ids = unique(ledger)
    C = [v for v in ledger if v['nucleus'] == '13C']
    H = [v for v in ledger if v['nucleus'] == '1H']
    need(len(C) == N and len(H) == binding('TEST_STAGE_B_control.frozen_identity_count.8'), 'A_nucleus_domains')
    need([v['identity_ordinal'] for v in ledger] == list(range(binding('TEST_STAGE_B_control.frozen_identity_count.9'))), 'A_original_identity_order')
    publics = unique(data['public'])
    unknown = unique(data['unknown'])
    lineages = unique(data['lineage'])
    need(set(publics) <= set(ids) and set(unknown) <= set(ids) and (set(lineages) == set(ids)), 'A_artifact_domains')
    for row in ledger:
        need(row['public_available'] is (row['input_id'] in publics), 'A_public_presence')
        if not row['reference_admitted']:
            need(row['input_id'] in unknown, 'A_unknown_retention')
    cids = [v['input_id'] for v in C]
    queue = [iid for iid in cids if iid in publics]
    need(len(queue) <= N, 'C_scorequeue_bound')
    for iid in queue:
        p = publics[iid]
        need(p['nucleus'] == '13C', 'C_public_only')
        need(set(p) == {'input_id', 'nucleus', 'observations', 'smiles', 'actual_conditions'}, 'A_public_schema')
        for o in p['observations']:
            need(set(o) == {'observation_id', 'ppm_decimal'}, 'A_observation_schema')
    return dict(receipt=a, data=data, full_C=C, ordered_C_ids=cids, queue=queue, public=publics, source_review=review, extraction=extraction, artifact_paths=plan.get('stage_A_artifact_paths', {}))

def cache_public(p):
    need(set(p) == {'input_id', 'nucleus', 'observations', 'smiles', 'actual_conditions'} and p['nucleus'] == '13C', 'public_only_C')
    need(isinstance(p['actual_conditions'], dict) and set(p['actual_conditions']) <= set(('solvent', 'frequency', 'pH', 'ph', 'temperature', 'NMR_solvent')), 'actual_conditions_whitelist')
    need(all((v is None or (type(v) in (str, int, float) and (type(v) is not float or math.isfinite(v))) for v in p['actual_conditions'].values())), 'actual_conditions_scalar')
    for o in p['observations']:
        need(set(o) == {'observation_id', 'ppm_decimal'} and isinstance(o['observation_id'], str) and isinstance(o['ppm_decimal'], str), 'public_observation_only')
    return dict(input_id=p['input_id'], nucleus='13C', smiles=p['smiles'], actual_conditions=p['actual_conditions'], observations=[dict(bin_id=o['observation_id'], ppm_decimal=o['ppm_decimal']) for o in p['observations']])

def prediction_request(plan, stage_A):
    return dict(schema='TEST_STAGE_B_C_prediction_request_v1', execution_authorized=False, ordered_input_ids=stage_A['queue'], max_forward_started=len(stage_A['queue']), expected_H_model_loads=0, expected_C_model_loads=int(bool(stage_A['queue'])), cache_builder_sha256=binding('TEST_STAGE_B_control.exact_SHA_or_identity.10'), public_projection='cache_public(A.public); observation_id -> bin_id only', model_inputs='structure + actual measurement whitelist only', future_prediction_sha256=None, future_cache_inputs_sha256=None, cache_application_review=None, resources=plan.get('prediction_resources'), status='PENDING_OWNER_PREDICTION_ONCE_AND_RESOURCE_RELEASE')

def materialize_prediction_inputs(plan, plan_sha, owner_release):
    need(plan.get('execution_authorized') is True, 'prediction_preparation_plan_not_released')
    stage_B_release(owner_release, plan_sha, 'prediction_once', sha(__file__))
    a = bind_stage_A(plan)
    need(isinstance(plan.get('prediction_resources'), dict), 'prediction_resource_plan_pending')
    out = Path(plan['prediction_preparation_directory'])
    need(not out.exists(), 'new_prediction_input_directory')
    numeric = bound(plan['stage_B_numeric_config'])
    need(plan['stage_B_numeric_config']['sha256'] == a['extraction']['numeric_config']['sha256'], 'same_preA_numeric_config')
    out.mkdir(parents=True, exist_ok=False)
    public = out / 'C_anonymous_records.jsonl'
    with public.open('x') as stream:
        for iid in a['queue']:
            stream.write(json.dumps(cache_public(a['public'][iid]), ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        __import__('os').fsync(stream.fileno())
    (out / 'fixed_C_identity_coverage.json').write_text(json.dumps(dict(original_identity_denominator=binding('TEST_STAGE_B_control.frozen_identity_count.11'), scorequeue=len(a['queue']), rows=a['full_C']), indent=2) + '\n')
    request = prediction_request(plan, a)
    request.update(public=dict(path=str(public.resolve()), sha256=sha(public), rows=len(a['queue'])), stage_A_receipt_sha256=plan['stage_A_output_manifest']['sha256'], source_admission_review_sha256=plan['stage_A_actual_admission_review']['sha256'], numeric_config_sha256=plan['stage_B_numeric_config']['sha256'], preparation_authorized=True, execution_authorized=False, builder_execution_gate='Existing frozen builder/supervisor + separate exact once model release; no execution by this entry')
    (out / 'prediction_request.json').write_text(json.dumps(request, indent=2) + '\n')
    return request

def bind_cache_review(plan, queue):
    prediction = bound(plan['cache_predictions'])
    inputs = bound(plan['cache_inputs'])
    review = load(plan['cache_application_review'])
    spec = plan['cache_review_fields']

    def at(obj, path):
        for k in path:
            obj = obj[k]
        return obj
    need(str(at(review, spec['decision'])).startswith('PASS'), 'cache_actual_application_PASS')
    need(at(review, spec['predictions_sha256']) == plan['cache_predictions']['sha256'], 'cache_prediction_review')
    need(at(review, spec['inputs_sha256']) == plan['cache_inputs']['sha256'], 'cache_inputs_review')
    need(at(review, spec['input_count']) == len(queue), 'cache_actual_queue_count')
    ci = unique(list(rows(inputs)))
    need(set(ci) == set(queue), 'cache_full_input_domain')
    cp = unique(list(rows(prediction)), 'cache_key')
    for iid in queue:
        row = ci[iid]
        need(row['status'] in ('ok', 'failed_retained'), 'cache_status_retained')
        if row['status'] == 'ok':
            need(row.get('cache_key') in cp, 'ok_cache_prediction_present')
    return (ci, cp)

def frozen_axis_gate(axis, artifacts):
    need(all((isinstance(axis.get(k), str) and axis[k] for k in SEMANTIC_AXES)), 'complete_calibration_semantic_axis')
    matches = [a for a in artifacts if all((a.get('axis', {}).get(k) == axis[k] for k in SEMANTIC_AXES))]
    if len(matches) != 1:
        return dict(status='off_no_matching_semantic_axis', publication_enabled=False, threshold=None)
    a = matches[0]
    t = a.get('threshold')
    ok = a.get('status') == 'on_audit_passed' and type(t) in (int, float) and math.isfinite(t) and (t > 0)
    return dict(status='on_exact_reviewed_semantic_axis' if ok else a.get('status', 'off_frozen_validation_status_unknown'), stored_status=a.get('status'), publication_enabled=ok, threshold=t if ok else None, stored_threshold=t, refit=False)

def load_base(name, expected):
    path = artifact_path(name)
    need(sha(path) == expected, 'inherited_source_drift:' + name)
    spec = importlib.util.spec_from_file_location('frozen_stage_B_' + name.replace('.', '_'), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def contract():
    return dict(schema='TEST_STAGE_B_interface_contract_v1', implementation_only=True, execution_authorized=False, StageA_protocol='TEST_STAGE_A_fixed_test_outer.write_stage_A_outputs + run_A receipt', fixed_C_identity_count=N, ordered_scorequeue='A complete ledger C order filtered by actual public presence; <=3637', gates=['A actual complete receipt + exact source admission review', 'root distinct B once prediction release (no future cache SHA required)', 'actual cache artifacts + independent application PASS', 'one baseline scoring release; no retry'], pending_actual_A=True, pending_Cval_frozen_calibration=True, calibration='apply only approved Cval frozen artifacts on all8 semantic axes; no matching support => off; no fit/refit/bootstrap', H_unavailable='retained source ledger, no inference', phase_resources='explicit root freeze; per-record numeric10/2/2/5/1 and cap50000 unchanged')

def main():
    authorize()
    ap = argparse.ArgumentParser()
    ap.add_argument('--check-only', action='store_true')
    ap.add_argument('--prepare-prediction', action='store_true')
    ap.add_argument('--plan')
    ap.add_argument('--plan-sha256')
    ap.add_argument('--owner-release')
    ap.add_argument('--owner-release-sha256')
    args = ap.parse_args()
    if args.prepare_prediction:
        need(args.plan and args.plan_sha256 and (sha(args.plan) == args.plan_sha256), 'frozen_prediction_preparation_plan_SHA')
        print(json.dumps(materialize_prediction_inputs(json.loads(Path(args.plan).read_text()), args.plan_sha256, dict(path=args.owner_release, sha256=args.owner_release_sha256)), indent=2))
    else:
        print(json.dumps(contract(), indent=2))
if __name__ == '__main__':
    main()
