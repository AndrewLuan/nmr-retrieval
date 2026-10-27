# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：只读核验已完成C缓存的全行哈希、join、结构容量及数值接口；不调用模型或求解器。\n关系：读取frozen cache/result与已冻结C public/native graph；输出作者核验和独审交接，不能替代科学独审。\n'
from pathlib import Path
import json, hashlib, math, collections
D = workspace()
R = artifact_path('C_frozen_cache_artifacts/result')

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for x in iter(lambda: f.read(1048576), b''):
            h.update(x)
    return h.hexdigest()

def dig(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def rows(p):
    with p.open() as f:
        for l in f:
            if l.strip():
                yield json.loads(l)
m = json.loads((R / 'manifest.json').read_text())
r = json.loads((R / 'receipt.json').read_text())
for rel, h in m['outputs'].items():
    assert sha(R / rel) == h, rel
assert r['pre_hashes'] == r['post_hashes']
assert r['model_loads'] == {'13C': 1} and r['updates'] == 0
assert (r['forward_started'], r['forward_completed'], r['forward_validated']) == (binding('verify_C_frozen_cache_artifacts.expected_count.3219'), binding('verify_C_frozen_cache_artifacts.expected_count.3219'), binding('verify_C_frozen_cache_artifacts.expected_count.3219'))
public = {v['input_id']: v for v in rows(artifact_path('C_reference_batch/public.jsonl'))}
joins = list(rows(R / 'inputs.jsonl'))
assert len(joins) == binding('verify_C_frozen_cache_artifacts.cohort_count.1') and {x['input_id'] for x in joins} == set(public)
assert len({x['input_id'] for x in joins}) == binding('verify_C_frozen_cache_artifacts.cohort_count.2')
pred = {}
carrier_count = 0
components = 0
multi = 0
graphs = {v['exact_smiles']: v['graph_snapshot_sha256'] for v in rows(artifact_path('C_reference_inputs/val_graph_snapshots.jsonl'))}
for p in rows(R / 'predictions.jsonl'):
    key = p['cache_key']
    assert key not in pred
    pred[key] = p
    assert p['nucleus'] == '13C' and p['rdkit_version'] == '2026.03.6'
    assert dig(p['native_graph_snapshot']) == p['native_graph_snapshot_sha256'] == graphs[p['canonical_smiles']]
    assert key == dig({k: p[k] for k in ('nucleus', 'canonical_smiles', 'native_cond', 'recovered_condition_vector')})
    assert p['center_scale'] == 200 and p['native_sigma_ppm'] is None and (p['native_sigma_source'] == 'no_trained_native_sigma_head')
    assert p['recovered_condition_vector'] is None
    assert len(p['native_values']) == len(p['centers_ppm']) == len(p['owners']) == len(p['component_mass'])
    assert all((math.isfinite(v) and c == v * 200 for v, c in zip(p['native_values'], p['centers_ppm'])))
    assert all((v == 2.0 for v in p['assignment_width_ppm'])) and all((v is None for v in p['assignment_width_class']))
    assert p['assignment_width_source'] == binding('verify_C_frozen_cache_artifacts.embedded_sha_identity.1')
    carbons = {str(a['index']) for a in p['native_graph_snapshot']['atoms'] if a['z'] == 6}
    units = p['predictions']['layout']['units']
    assert {str(v['parent_mass'][0][0]) for v in units} == carbons
    assert all((v['nucleus_mass'] == 1 and len(v['parent_mass']) == 1 and (v['parent_mass'][0][1] == 1) for v in units))
    assert dict(p['predictions']['layout']['parent_mass_totals']) == {x: 1 for x in carbons}
    own = collections.defaultdict(list)
    for i, (o, mass) in enumerate(zip(p['owners'], p['component_mass'])):
        own[str(o)].append((i, mass))
    assert set(own) == carbons and all((math.isclose(sum((x[1] for x in v)), 1, abs_tol=1e-08) for v in own.values()))
    for v in own.values():
        assert [x[1] for x in v] in ([1.0], [0.5, 0.5])
    carriers = p['predictions']['carriers']
    assert len(carriers) == len(p['owners'])
    seen = set()
    for c in carriers:
        assert len(c['source_component_ids']) == 1
        i = int(c['source_component_ids'][0].split(':')[1])
        seen.add(i)
        assert c['center_ppm'] == p['centers_ppm'][i] and c['sigma_ppm'] == 2.0 and (c['sigma_source'] == p['assignment_width_source'])
        assert c['unit_id'] == 'parent:' + str(p['owners'][i]) and c['mixture_weight'] == p['component_mass'][i]
    assert seen == set(range(len(p['owners'])))
    assert not p['predictions']['attachment_blocks']
    carrier_count += len(carriers)
    components += len(p['owners'])
    multi += sum((len(v) == 2 for v in own.values()))
assert len(pred) == binding('verify_C_frozen_cache_artifacts.expected_count.3219')
failed = []
dedup = 0
for j in joins:
    assert j['nucleus'] == '13C' and j['actual_conditions_sha256'] == dig(public[j['input_id']]['actual_conditions']) and (j['cache_key_semantics'] == 'native_encoded_features_only')
    if j['status'] == 'ok':
        assert j['cache_key'] in pred
        dedup += int(j['deduplicated'])
    else:
        failed.append(j)
assert dedup == binding('verify_C_frozen_cache_artifacts.expected_count.520') and len(failed) == 1
assert failed[0]['input_id'] == binding('verify_C_frozen_cache_artifacts.embedded_sha_identity.2') and failed[0]['error'] == 'ValueError:unsupported_feature:79/54'
stages = list(rows(R / 'stages.jsonl'))
start = [s for s in stages if s['stage'] == 'forward_started']
complete = [s for s in stages if s['stage'] == 'forward_completed']
valid = [s for s in stages if s['stage'] == 'forward_validated']
assert len(start) == len(complete) == len(valid) == binding('verify_C_frozen_cache_artifacts.expected_count.3219')
assert all((s.get('input_id') != failed[0]['input_id'] for s in start))
for suffix, h in [('nmr_transfer/data.py', ''), ('build_frozen_prediction_cache.py', binding('verify_C_frozen_cache_artifacts.sha_or_identity.3'))]:
    vals = [v for k, v in r['pre_hashes'].items() if k.endswith(suffix)]
    assert len(vals) == 1
    if h:
        assert vals == [h]
report = dict(schema='C_frozen_cache_author_check_v1', status='AUTHOR_FULL_ARTIFACT_CHECK_PASS_RETAINED_FAILURE_APPLICATION_REVIEW_PENDING', manifest_sha256=sha(R / 'manifest.json'), receipt_sha256=sha(R / 'receipt.json'), output_sha256=m['outputs'], counts=dict(inputs=binding('verify_C_frozen_cache_artifacts.cohort_count.4'), ok=3739, failed=1, forwards_started=binding('verify_C_frozen_cache_artifacts.expected_count.3219'), completed=binding('verify_C_frozen_cache_artifacts.expected_count.3219'), validated=binding('verify_C_frozen_cache_artifacts.expected_count.3219'), dedup=binding('verify_C_frozen_cache_artifacts.expected_count.520'), H_loads=0, C_loads=1, components=components, carriers=carrier_count, multi_carbon_owners=multi), checks={k: 'PASS' for k in ['manifest_output_hashes', 'pre_post_hash_equality', 'all3740_input_joins', 'full_actual_condition_digest', 'native_feature_cache_keys', 'native_graph_frozen_snapshot_and_RDKit', 'carbon_parent_unit_mass', 'component_mass_preserved_not_observed_integral', 'center_scale200_once', 'assignment_sigma2_fixed_prior_native_sigmaNone', 'carrier_component_identity', 'stage_counter_and_pre_forward_failure']}, failure=failed[0], failure_structure=public[failed[0]['input_id']]['smiles'], failure_policy='Retain all methods eligible gold denominators; prediction unknown/unsupported; no retry or model/source modification.', scope='Source-relative reference evaluation only. Structural element-site capacity is not sample isotope abundance; no trusted-experimental certification.', receipt_status=r['status'], new_model_calls=0, new_mappings=0, new_solver_calls=0, independent_application_review_pass=False)
artifact_path('C_frozen_cache_author_check.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
