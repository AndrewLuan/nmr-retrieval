# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：Stage B专用C打包入口，直接消费Stage A已完成的五表协议与后续已审cache。
A.public仅作observation_id到bin_id字段转换，不改峰值/顺序；full C3637身份与unknown均保留。
normalize_stage_A_C桥接A.hidden.computed_reference，不构新transport或joint family。
成功预测复用原Cval package_row/lineage校验；failed_retained只复用source admission，不造payload。
只有A实际/source PASS、B独立release、cache实际PASS后才可打包；默认check-only，不访问test。
"""
from pathlib import Path
import argparse, json, os
import TEST_STAGE_B_control as ctl
D = workspace()

def write(p, v):
    with Path(p).open('x') as f:
        f.write(json.dumps(v, ensure_ascii=False, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())

def normalize_stage_A_C(iid, hidden, ledger, base, digest):
    need = ctl.need
    evidence = hidden['evidence']
    computed = evidence['computed_reference']
    rh = computed['hidden']
    need(hidden['input_id'] == ledger['input_id'] == iid, 'A_hidden_ledger_identity')
    need(ledger['nucleus'] == '13C' and hidden['identity']['historical_partition'] == 'test', 'A_C_test_identity')
    need(ledger['reference_admitted'] is True, 'public_reference_not_admitted')
    reference = dict(input_id=iid, reference_hidden=rh, native_graph_snapshot=evidence['native_graph_snapshot'], raw_json_line=evidence['raw_json_line'], known_mask_joint_gold=rh['joint_gold_variants'])
    l = dict(rh['binding'], input_id=iid, scoreable_proposal=True, ledger_class=computed['classification'], native_role='native_test', policy_missing=True, historical_C_quality_policy_status='unknown', connectivity_sha256=hidden['identity']['connectivity_sha256'])
    return base.normalize_gold(reference, l, digest)

def prepare_public(plan):
    a = ctl.bind_stage_A(plan)
    return (a, [ctl.cache_public(a['public'][iid]) for iid in a['queue']])

def package_source_cohort(plan, stage_A, normalized_gold):
    if normalized_gold:
        return normalized_gold[0]['binding']['cohort_identity_manifest_sha256']
    item = plan.get('stage_A_derived_C_context')
    context = ctl.load(item)
    path = plan.get('stage_A_derived_C_context_review_path')
    ctl.need(isinstance(path, list) and path, 'empty_queue_A_cohort_review_binding_required')
    reviewed = stage_A['source_review']
    for key in path:
        reviewed = reviewed[key]
    ctl.need(reviewed == item['sha256'], 'empty_queue_A_cohort_actual_review_SHA')
    text = context['cohort_text']
    cohort = context['cohort_sha256']
    ctl.need(__import__('hashlib').sha256(text.encode()).hexdigest() == cohort, 'A_derived_cohort_text_SHA')
    declared = json.loads(text)
    ctl.need(declared.get('native_partition') == 'test' and declared.get('native_role') == 'native_test' and (declared.get('nucleus_scope') == '13C') and (len(declared.get('records', [])) == binding('TEST_STAGE_B_package.frozen_identity_count.1')), 'A_derived_C3637_cohort_scope')
    return cohort

def package(plan, plan_sha, owner_release):
    ctl.need(plan.get('execution_authorized') is True, 'packaging_plan_not_released')
    ctl.stage_B_release(owner_release, plan_sha, 'package_after_cache_review', ctl.sha(__file__))
    a, public = prepare_public(plan)
    ci, cp = ctl.bind_cache_review(plan, a['queue'])
    base = ctl.load_base('prepare_C_scoring_artifacts.py', ctl.BASE_PACKAGER_SHA)
    digest, typed, adapter = base.load_api(Path(plan['repo']))
    base.C_PRODUCER_SHA = a['receipt']['codes']['C_test_producer']['sha256']
    hidden_rows = ctl.read_artifacts(a['receipt'], ('hidden',), a['artifact_paths'])['hidden']
    hi = ctl.unique(hidden_rows)
    ctl.need(set(hi) == set((v['input_id'] for v in a['data']['ledger'])), 'A_hidden_full_identity_domain')

    def raw_hashes(path, key):
        result = {}
        with Path(path).open('rb') as stream:
            for raw in stream:
                row = json.loads(raw)
                result[row[key]] = __import__('hashlib').sha256(raw).hexdigest()
        return result
    artifact = lambda name: a['artifact_paths'].get(name, a['receipt']['artifacts'][name])['path']
    ph = raw_hashes(artifact('public'), 'input_id')
    gh = raw_hashes(artifact('hidden'), 'input_id')
    lh = raw_hashes(artifact('ledger'), 'input_id')
    ih = raw_hashes(ctl.bound(plan['cache_inputs']), 'input_id')
    ch = raw_hashes(ctl.bound(plan['cache_predictions']), 'cache_key')
    original = {v['input_id']: v for v in a['full_C']}
    output = Path(plan['output_directory'])
    ctl.need(not output.exists(), 'new_package_output')
    result = {k: [] for k in ('public', 'gold', 'ledger', 'admissions', 'predictions', 'lineages', 'cache_input_ledger', 'coverage_ledger')}
    for p in public:
        iid = p['input_id']
        g, l = normalize_stage_A_C(iid, hi[iid], original[iid], base, digest)
        state = ci[iid]
        native = cp.get(state.get('cache_key')) if state['status'] == 'ok' else None
        bindings = dict(reference_manifest_sha256=plan['stage_A_output_manifest']['sha256'], public_artifact_sha256=a['receipt']['artifacts']['public']['sha256'], gold_artifact_sha256=a['receipt']['artifacts']['hidden']['sha256'], ledger_artifact_sha256=a['receipt']['artifacts']['ledger']['sha256'], prediction_artifact_sha256=plan['cache_predictions']['sha256'], cache_input_artifact_sha256=plan['cache_inputs']['sha256'], public_row_sha256=ph[iid], gold_row_sha256=gh[iid], ledger_row_sha256=lh[iid], cache_input_row_sha256=ih[iid], prediction_row_sha256=ch[native['cache_key']] if native else None, row_hash_recipe='sha256 exact original artifact JSONL bytes including newline; public observation_id field rename separately declared')
        if state['status'] == 'failed_retained':
            wrapped = base.failed_cache_row(p, g, l, state, digest=digest, adapter=adapter, source_artifacts=bindings, reference_review_sha=plan['stage_A_actual_admission_review']['sha256'])
        else:
            wrapped = base.package_row(p, g, l, state, native, digest=digest, typed=typed, adapter=adapter, source_artifacts=bindings, reference_review_sha=plan['stage_A_actual_admission_review']['sha256'], cache_review_sha=plan['cache_application_review']['sha256'])
        result['public'].append(p)
        result['gold'].append(g)
        result['ledger'].append(l)
        result['admissions'].append(wrapped['admission'])
        result['cache_input_ledger'].append(wrapped['cache_input_ledger'])
        if 'prediction' in wrapped:
            result['predictions'].append(wrapped['prediction'])
            result['lineages'].append(wrapped['lineage'])
    q = set(a['queue'])
    for row in a['full_C']:
        iid = row['input_id']
        result['coverage_ledger'].append(dict(row, native_role='native_test', roles=['native_test'], public_available=iid in q, scorequeue_status='queued' if iid in q else 'public_unavailable_unknown', pregold_status='reviewed_reference_present' if iid in q else 'unknown_not_admitted'))
    source_cohort = package_source_cohort(plan, a, result['gold'])
    output.mkdir(parents=True, exist_ok=False)
    assets = {}
    for name, values in result.items():
        p = output / (name + '.jsonl')
        with p.open('x') as f:
            for row in values:
                f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        assets[name] = dict(path=str(p.resolve()), sha256=ctl.sha(p), rows=len(values), bytes=p.stat().st_size)
    manifest = dict(schema='TEST_STAGE_B_C_packaging_v1', status='PACKAGED_NO_BASELINE_SCORES', original_identity_denominator=binding('TEST_STAGE_B_package.frozen_identity_count.2'), scorequeue=len(a['queue']), public_unavailable=binding('TEST_STAGE_B_package.frozen_identity_count.3') - len(a['queue']), ordered_input_ids_sha256=digest(a['queue']), ordered_full_identity_ids_sha256=digest(a['ordered_C_ids']), inputs=assets, source_cohort_sha256=source_cohort, owner_release_sha256=owner_release['sha256'], packaging_plan_sha256=plan_sha, stage_A_receipt_sha256=plan['stage_A_output_manifest']['sha256'], source_application_review_sha256=plan['stage_A_actual_admission_review']['sha256'], cache_application_review_sha256=plan['cache_application_review']['sha256'], cache_predictions_sha256=plan['cache_predictions']['sha256'], cache_inputs_sha256=plan['cache_inputs']['sha256'], all_original_identities_retained=True, calibration_fit_calls=0, models=0, scores=0, new_transport_calls=0, test_scope=True)
    write(output / 'manifest.json', manifest)
    return manifest

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
    ctl.need(a.plan and a.plan_sha256 and (ctl.sha(a.plan) == a.plan_sha256), 'frozen_package_plan_SHA')
    package(json.loads(Path(a.plan).read_text()), a.plan_sha256, dict(path=a.owner_release, sha256=a.owner_release_sha256))
if __name__ == '__main__':
    main()
