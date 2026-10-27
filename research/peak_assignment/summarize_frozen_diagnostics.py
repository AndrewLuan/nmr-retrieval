# 功能概述：已审H父诊断/聚合或Stage A科学入口的公开迁移副本，非历史actual-run字节。
# 接口：显式runtime授权及独立冻结plan/source/review/release；路径/身份/SHA从external bindings取得。
# 关系：直接依赖同publictree或现有nmr_assignment；保留原数值算法、完整分母、预算及失败协议。
from portable_runtime import binding, workspace, artifact_path, repository, _config
"""功能概述：只读汇总冻结evaluation/raw/diagnostics的原始结局与分层；默认check-only。
主要职责：summarize消费已保存EvaluationRow，不重新评价gold、求解、模型推理或身份映射。
按完整truth/task/target/role轴固定eligible分母；transition对同input/obs配对三基线，保留
ineligible/unsupported/unknown状态，并区分compatible成功但exact失败或exact未准入。
代码库关系：独立标准库CLI；completed manifest及原report handoff提供逐文件SHA闭包。
条件/NOS使用显式SHA绑定public/cache sidecar；物理缺峰/交换/天然overlap仅接受绑定来源的
source_explicit+locator证据，结构假设另轨。相同serialized bin不证明天然overlap，残差不证明labelwrong。
输入输出：check-only不读真实输入；--execute还需独审contract approval。新目录输出报告与receipt，
绝不改active制品；gold资格/成功只读取原rows。多标签层可重叠，不得相加解释为互斥占比。
"""
import argparse, collections, hashlib, itertools, json
from pathlib import Path
AXES = ('truth_basis', 'nucleus', 'task_semantics', 'target_level', 'target_semantics')
METHODS = ('B0', 'B1', 'B2')
CONTRACT = dict(schema='frozen_diagnostics_contract_v1', status='DRAFT_OWNER_REVIEW_REQUIRED', estimand='saved-row descriptive aggregation only; no scientific re-evaluation', axes=list(AXES), pair_key=['role', 'metric'] + list(AXES) + ['input_id', 'observation_id'], denominator='saved eligible unchanged, all unsupported/timeout/unknown predictions retained', counts=['all_rows', 'eligible', 'eligible_prediction_supported', 'eligible_success', 'eligible_failure', 'records', 'connectivities', 'eligible_records', 'eligible_connectivities'], multilabel='overlapping evidence strata, not additive attribution', transitions='all eligibility/outcome states; separate both-eligible success/failure 2x2; paired baseline state strata', compatible_vs_exact=['compatible_success_exact_eligible_failure', 'compatible_success_exact_ineligible', 'compatible_success_exact_missing'], source='bound metadata.source_binding.source; absence unknown', conditions='full actual_conditions with SHA bound public; empty or all-null unknown; no fabricated bins', NOS='multi-label structural N7/O8/S16 present or absent from bound native graph; not exchange/missing mechanism', mechanisms='missing_peak/natural_overlap/exchange require source_explicit evidence+locator; structural_hypothesis separate; otherwise unknown', coverage='cache input status/error separate from reference errors; Hg feature unsupported is model coverage', raw_diagnostics='saved candidate graph counts and saved failure_labels/reason_codes only; no residual causal labeling', chemical_quotient_top3='unsupported; no additional solve', raw_projection_states='Saved raw per_observation_status and solver_result.margins (or raw margins) retained separately from pipeline observation_determinate; no gap/tau recomputation. abstain_tie with projection true is a distinct descriptive state, never blanket chemical ambiguity or timeout/missing.', whole_record_raw_states='For observation_id null retain full saved raw status/margin mappings rather than inventing one observation gap', execution='completed manifest+SHA, report handoff+SHA closure and approved exact contract SHA required')

def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def sha(p):
    _config()
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def load(p):
    _config()
    return json.loads(Path(p).read_text())

def lines(p):
    with Path(p).open() as f:
        for l in f:
            if l.strip():
                yield json.loads(l)

def packed(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def state(r):
    return 'ineligible' if not r['eligible'] else 'success' if r['success'] else 'failure'

def saved_mapping(value, path):
    if value is None:
        return {}
    need(isinstance(value, dict), 'malformed_saved_mapping:' + path)
    return value

def saved_execution_parts(raw):
    execution = saved_mapping(raw.get('raw_execution'), 'raw_execution')
    result = saved_mapping(execution.get('result'), 'raw_execution.result')
    methods = saved_mapping(result.get('methods'), 'raw_execution.result.methods')
    diagnostics = saved_mapping(result.get('candidate_diagnostics'), 'raw_execution.result.candidate_diagnostics')
    availability = 'available' if execution.get('result') is not None else 'raw_result_unavailable'
    return (execution, result, methods, diagnostics, availability)

def raw_observation_state(method, obs):
    method = saved_mapping(method, 'method')
    statuses = method.get('per_observation_status', {})
    if isinstance(statuses, list):
        statuses = dict(statuses)
    statuses = saved_mapping(statuses, 'method.per_observation_status')
    solver = saved_mapping(method.get('solver_result'), 'method.solver_result')
    margins = solver.get('margins', method.get('margins', {}))
    margins = saved_mapping(margins, 'method.margins')
    return dict(per_observation_status=statuses.get(obs, 'unknown') if obs is not None else statuses, margin=margins.get(obs, 'unknown') if obs is not None else margins)

def raw_projection_combination(r):
    raw = r.get('raw_observation', {})
    status = raw.get('per_observation_status', 'unknown')
    projection = r['pipeline'].get('observation_determinate', {}).get(r['observation_id'], 'unknown')
    return packed(dict(raw_status=status, projection_observation_determinate=projection, timed_out=r['pipeline'].get('timed_out', 'unknown')))

def pstate(r):
    p = r['pipeline']
    obs = r['observation_id']
    return dict(prediction_supported=r['prediction_supported'], reason_codes=sorted(r.get('reason_codes', [])), observation_determinate=p.get('observation_determinate', {}).get(obs, 'unknown'), timed_out=p.get('timed_out', 'unknown'), status=p.get('status', 'unknown'), model_coverage=r['strata']['model_coverage'], raw_observation=r.get('raw_observation', {'per_observation_status': 'unknown', 'margin': 'unknown'}), raw_result_availability=r.get('raw_result_availability', 'unknown'), raw_projection_combination=raw_projection_combination(r))

def group_axes(r):
    return {k: r['context'].get(k, 'unknown') for k in AXES}

def basekey(r):
    return dict(role=r['role'], metric=r['metric'], **group_axes(r))

def pairkey(r):
    return packed(dict(basekey(r), input_id=r['input_id'], observation_id=r['observation_id']))

def strata(metadata, raw, public=None, cache=None, evidence=None):
    binding = metadata.get('source_binding', {})
    source = binding.get('source') or binding.get('source_ref') or 'unknown'
    cond = (public or {}).get('actual_conditions', {})
    conditions = packed(cond) if cond and any((v is not None and v != '' for v in cond.values())) else 'unknown'
    atoms = (cache or {}).get('native_graph_snapshot', {}).get('atoms')
    nos = ['structural_' + name + ('_present' if any((a.get('z') == z for a in atoms)) else '_absent') for name, z in (('N', 7), ('O', 8), ('S', 16))] if atoms is not None else ['unknown']
    result = dict(source=[source], conditions=[conditions], NOS=nos)
    for name in ('missing_peak', 'natural_overlap', 'exchange'):
        result[name] = ['unknown']
        result[name + '_structural_hypothesis'] = ['unknown']
    if evidence:
        need(evidence.get('source_binding_sha256') == digest(binding), 'mechanism_evidence_source_binding')
        for v in evidence.get('labels', []):
            need(v.get('dimension') in ('missing_peak', 'natural_overlap', 'exchange') and isinstance(v.get('label'), str) and v['label'] and v.get('locator'), 'mechanism_explicit_label_locator')
            need(v.get('basis') in ('source_explicit', 'structural_hypothesis'), 'mechanism_basis')
            key = v['dimension'] + ('_structural_hypothesis' if v['basis'] == 'structural_hypothesis' else '')
            if result[key] == ['unknown']:
                result[key] = []
            result[key].append(v['label'])
    inp = raw.get('cache_input_state', {})
    result['model_coverage'] = [packed(dict(status=inp.get('upstream_status', inp.get('status', 'unknown')), error=inp.get('error', 'unknown')))]
    return result

def aggregate(rows):
    n = len(rows)
    eligible = [r for r in rows if r['eligible']]
    success = sum((r['success'] for r in eligible))
    return dict(all_rows=n, eligible=len(eligible), eligible_prediction_supported=sum((r['prediction_supported'] for r in eligible)), eligible_success=success, eligible_failure=len(eligible) - success, success_rate=success / len(eligible) if eligible else None, records=len({r['input_id'] for r in rows}), connectivities=len({r['context']['connectivity_id'] for r in rows if r['context'].get('connectivity_id')}), eligible_records=len({r['input_id'] for r in eligible}), eligible_connectivities=len({r['context']['connectivity_id'] for r in eligible if r['context'].get('connectivity_id')}), unknown_connectivity_rows=sum((not r['context'].get('connectivity_id') for r in rows)))

def summarize(rows):
    groups = collections.defaultdict(list)
    pairs = collections.defaultdict(dict)
    exact = {}
    compat = []
    diag = collections.Counter()
    for r in rows:
        need(type(r['eligible']) is bool and type(r['success']) is bool and (type(r['prediction_supported']) is bool), 'saved_row_bool')
        need(not r['success'] or r['eligible'], 'success_on_ineligible_row')
        b = dict(basekey(r), baseline=r['baseline'])
        groups[packed(dict(b, dimension='all', label='all'))].append(r)
        groups[packed(dict(b, dimension='raw_projection_combination', label=raw_projection_combination(r)))].append(r)
        for dim, labels in r['strata'].items():
            for label in set(labels):
                groups[packed(dict(b, dimension=dim, label=label))].append(r)
        for label in set(r.get('failure_labels', []) or ['unknown']):
            groups[packed(dict(b, dimension='saved_failure_label', label=label))].append(r)
        for label in set(r.get('reason_codes', []) or ['none_saved']):
            groups[packed(dict(b, dimension='saved_reason_code', label=label))].append(r)
        key = pairkey(r)
        need(r['baseline'] not in pairs[key], 'duplicate_saved_pair_baseline')
        pairs[key][r['baseline']] = r
        other = dict(b)
        other.pop('metric')
        other.update(input_id=r['input_id'], observation_id=r['observation_id'])
        if r['metric'] == 'exact_observation':
            exact[packed(other)] = r
        elif r['metric'] == 'compatible_observation' and r['eligible'] and r['success']:
            compat.append((packed(other), r))
    transitions = collections.defaultdict(list)
    missing = collections.Counter()
    eligibility_mismatch = []
    for key, methods in pairs.items():
        for a, b in itertools.combinations(METHODS, 2):
            if a not in methods or b not in methods:
                missing[a + '->' + b] += 1
                continue
            x, y = (methods[a], methods[b])
            if x['eligible'] != y['eligible']:
                eligibility_mismatch.append(dict(pair=json.loads(key), baselines=[a, b]))
            g = dict(basekey(x), from_baseline=a, to_baseline=b, from_outcome=state(x), to_outcome=state(y), both_eligible=x['eligible'] and y['eligible'], from_pipeline=pstate(x), to_pipeline=pstate(y))
            transitions[packed(g)].append(x)
    comparisons = collections.defaultdict(list)
    for key, r in compat:
        e = exact.get(key)
        label = 'compatible_success_exact_missing' if e is None else 'compatible_success_exact_ineligible' if not e['eligible'] else 'compatible_success_exact_eligible_failure' if not e['success'] else 'compatible_success_exact_success'
        comparisons[packed(dict(basekey(r), baseline=r['baseline'], comparison=label))].append(r)
    return dict(stratified_metrics=[dict(group=json.loads(k), counts=aggregate(v)) for k, v in sorted(groups.items())], transitions=[dict(group=json.loads(k), counts=aggregate(v)) for k, v in sorted(transitions.items())], transition_missing_pairs=dict(missing), eligibility_mismatch=eligibility_mismatch, compatible_exact_comparisons=[dict(group=json.loads(k), counts=aggregate(v)) for k, v in sorted(comparisons.items())], chemical_quotient_top3='unsupported', causal_attribution='not_identified')

def execute(request):
    checked = {}

    def bound(item):
        p = Path(item['path']).resolve()
        need(sha(p) == item['sha256'], 'input_SHA:' + str(p))
        checked[str(p)] = item['sha256']
        return p
    manifest = bound(request['completed_manifest'])
    m = load(manifest)
    need(m.get('status') == 'FROZEN_ASSIGNMENT_EXECUTION_COMPLETED', 'completed_manifest_required')
    approval = load(bound(request['contract_approval']))
    need(approval.get('decision') == 'PASS_FROZEN_DIAGNOSTICS_CONTRACT' and approval.get('contract_sha256') == digest(CONTRACT), 'contract_review_required')
    handoff = load(bound(request['report_handoff']))
    need(handoff.get('completed_manifest_sha256') == sha(manifest), 'handoff_manifest_binding')
    closure = handoff['observed_output_sha256']
    root = manifest.parent

    def existing(rel):
        p = (root / rel).resolve()
        need(str(p) in closure, 'saved_output_missing_hash:' + rel)
        return bound(dict(path=str(p), sha256=closure[str(p)]))
    public = {}
    cache = {}
    evidence = {}
    if request.get('public'):
        public = {r['input_id']: r for r in lines(bound(request['public']))}
    if request.get('cache_predictions'):
        cache = {r['cache_key']: r for r in lines(bound(request['cache_predictions']))}
    if request.get('source_evidence'):
        evidence = {r['input_id']: r for r in lines(bound(request['source_evidence']))}
    rows = []
    saved_diagnostics = []
    for entry in m['record_ledger']:
        iid = entry['input_id']
        ev = load(existing('evaluation/' + iid + '.json'))
        raw = load(existing('raw/' + iid + '.json'))
        execution, saved_result, saved_methods, saved_diag, raw_availability = saved_execution_parts(raw)
        for baseline, obj in ev.items():
            if baseline not in METHODS:
                continue
            meta = obj['metadata']
            need(meta.get('input_id') == iid, 'evaluation_input_binding')
            graph = cache.get(raw.get('cache_input_state', {}).get('cache_key'))
            if public:
                need(iid in public, 'public_input_missing')
                expected = raw.get('cache_input_state', {}).get('actual_conditions_sha256')
                actual = hashlib.sha256(json.dumps(public[iid]['actual_conditions'], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
                need(expected == actual, 'public_actual_conditions_binding')
            if graph:
                actual = hashlib.sha256(json.dumps(graph['native_graph_snapshot'], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
                need(graph['native_graph_snapshot_sha256'] == actual, 'native_graph_snapshot_digest')
            st = strata(meta, raw, public.get(iid), graph, evidence.get(iid))
            for row in obj['rows']:
                context = dict(row['context'])
                need(context.get('baseline') == baseline, 'baseline_axis_binding')
                for role in meta.get('roles', ['unknown']):
                    method = saved_methods.get(baseline)
                    rows.append(dict(row, context=context, role=role, baseline=baseline, input_id=iid, pipeline=obj.get('pipeline_status', {}), strata=st, raw_observation=raw_observation_state(method, row.get('observation_id')), raw_result_availability=raw_availability))
        diag = saved_diag
        for k, v in diag.items():
            saved_mapping(v, 'candidate_diagnostics.' + k)
        saved_diagnostics.append(dict(input_id=iid, raw_result_availability=raw_availability, saved_execution_status=execution.get('status', 'unknown'), available_methods=sorted(diag), methods={k: dict(saved_candidate_count=len(v.get('candidates', [])), saved_scalar_fields={a: b for a, b in v.items() if b is None or isinstance(b, (str, int, float, bool))}) for k, v in diag.items() if isinstance(v, dict)}, raw_sha256=sha(root / 'raw' / (iid + '.json'))))
    result = summarize(rows)
    result.update(schema='frozen_diagnostics_summary_v1', contract_sha256=digest(CONTRACT), record_manifest_count=len(m['record_ledger']), saved_diagnostic_inventory=saved_diagnostics, NOS_scope='molecule_contains', original_gold_rows_reused=True, source_hashes=checked, model_calls=0, solver_calls=0, new_mapping_calls=0)
    for p, h in checked.items():
        need(sha(p) == h, 'post_input_SHA:' + p)
    out = Path(request['out'])
    out.mkdir(parents=True, exist_ok=False)
    (out / 'report.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    (out / 'receipt.json').write_text(json.dumps(dict(status='READONLY_SAVED_ROWS_AGGREGATED', report_sha256=sha(out / 'report.json'), source_hashes=checked), indent=2) + '\n')
    return result

def self_test():
    base = dict(context={k: 'synthetic' for k in AXES} | {'connectivity_id': 'g'}, role='val', input_id='i', observation_id='p', metric='exact_observation', eligible=True, prediction_supported=True, success=True, reason_codes=[], failure_labels=['unknown'], pipeline={}, strata={'source': ['synthetic'], 'model_coverage': ['unknown']})
    rows = [dict(base, baseline='B0'), dict(base, baseline='B1', success=False, prediction_supported=False), dict(base, baseline='B2', success=False)]
    out = summarize(rows)
    assert any((v['group']['from_outcome'] == 'success' and v['group']['to_outcome'] == 'failure' for v in out['transitions']))
    assert next((v for v in out['stratified_metrics'] if v['group']['baseline'] == 'B1' and v['group']['dimension'] == 'all'))['counts']['eligible'] == 1
    rows += [dict(base, baseline='B1', metric='compatible_observation'), dict(base, baseline='B2', metric='compatible_observation')]
    rows[2]['eligible'] = False
    labels = {v['group']['comparison'] for v in summarize(rows)['compatible_exact_comparisons']}
    assert 'compatible_success_exact_eligible_failure' in labels and 'compatible_success_exact_ineligible' in labels
    s = strata({}, {'cache_input_state': {'status': 'failed', 'error': 'unsupported_feature:79/54'}}, public={'actual_conditions': {}}, cache={'native_graph_snapshot': {'atoms': [{'z': 7}, {'z': 8}]}})
    assert s['conditions'] == ['unknown'] and s['natural_overlap'] == ['unknown'] and (len(s['NOS']) == 3)
    assert aggregate([])['success_rate'] is None
    raw = raw_observation_state({'per_observation_status': [['p', 'abstain_tie']], 'solver_result': {'margins': {'p': {'value': 0, 'certified': True, 'status': 'optimal', 'alternative_objective': 1}}}}, 'p')
    assert raw['per_observation_status'] == 'abstain_tie' and raw['margin']['value'] == 0
    a = dict(base, baseline='B0', raw_observation=raw, pipeline={'observation_determinate': {'p': True}, 'timed_out': False})
    b = dict(a, baseline='B1', pipeline={'observation_determinate': {'p': False}, 'timed_out': False})
    assert raw_projection_combination(a) != raw_projection_combination(b)
    assert pstate(a)['observation_determinate'] is True and pstate(a)['raw_observation']['per_observation_status'] == 'abstain_tie'
    groups = summarize([a, b])['stratified_metrics']
    assert len([x for x in groups if x['group']['dimension'] == 'raw_projection_combination']) == 2
    assert raw_observation_state({}, 'p') == {'per_observation_status': 'unknown', 'margin': 'unknown'}
    return dict(status='SYNTHETIC_PASS', checks=12, real_rows_read=0, model_calls=0, solver_calls=0)

def main():
    _config()
    p = argparse.ArgumentParser()
    p.add_argument('--check-only', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--request')
    p.add_argument('--request-sha256')
    p.add_argument('--receipt')
    a = p.parse_args()
    if a.self_test:
        r = self_test()
    elif a.execute:
        need(a.request and a.request_sha256 and (sha(a.request) == a.request_sha256), 'request_SHA_required')
        r = execute(load(a.request))
    else:
        r = dict(status='CHECK_ONLY_NO_REAL_INPUT_READ', contract=CONTRACT, contract_sha256=digest(CONTRACT), execution_authorized=False)
    if a.receipt:
        Path(a.receipt).write_text(json.dumps(r, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(r if not a.execute else {'status': 'READONLY_SAVED_ROWS_AGGREGATED'}, indent=2, ensure_ascii=False))
if __name__ == '__main__':
    main()
