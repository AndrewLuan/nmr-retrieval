# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：只包装 C native-val 已审 reference 与未来 frozen cache，默认 check-only。\nnormalize_gold 显式转换 C 外层 schema，保留原 raw、binding、完整 joint tuples 和 transport；\npackage_row 复核 typed layout/attachment/native graph 与独审证据，不计算残差、不造 solver 证书。\nexecute 要求独立 cache PASS exact SHA 和字段绑定；输出 scorequeue3740，coverage ledger3745，\n无 public 的5条保持 unknown，绝不伪造峰。\nfailed_cache_row 将 failed_retained 保留为 cache_failed；source_admission 不依赖预测，失败仍保留 gold 分母。原 policy_missing/historical unknown 留在 ledger/gold。\n依赖冻结 execution.canonical_digest 与 assignment_evaluation_adapter；不修改 H caller/core。\nmain 的 --self-test 只测合成 schema/拒绝逻辑；--checkonly 仅读 manifest/review，无模型/评分。\n'
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
D = workspace()
EXECUTION_SHA = binding('prepare_C_scoring_artifacts.sha_or_identity.1')
ADAPTER_SHA = binding('prepare_C_scoring_artifacts.sha_or_identity.2')
SOURCE_REF_SHA = binding('prepare_C_scoring_artifacts.sha_or_identity.3')
C_PRODUCER_SHA = binding('prepare_C_scoring_artifacts.sha_or_identity.4')
REFERENCE_MANIFEST_SHA = binding('prepare_C_scoring_artifacts.sha_or_identity.5')
REFERENCE_REVIEW_SHA = binding('prepare_C_scoring_artifacts.sha_or_identity.6')

def require(value, message):
    if not value:
        raise ValueError(message)

def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def byte_sha(value):
    return hashlib.sha256(value).hexdigest()

def wrap(payload, digest):
    return dict(payload=payload, sha256=digest(payload))

def nested(value, path):
    for key in json.loads(path):
        value = value[key]
    return value

def jsonl(path, key):
    rows = []
    index = {}
    with Path(path).open('rb') as f:
        for ordinal, raw in enumerate(f):
            require(bool(raw.strip()), 'blank JSONL')
            row = json.loads(raw)
            iid = row[key]
            require(iid not in index, 'duplicate identity')
            item = dict(row=row, raw=raw, raw_sha256=byte_sha(raw), ordinal=ordinal)
            rows.append(item)
            index[iid] = item
    return (rows, index)

def load_api(repo):
    require(file_sha(repo / 'nmr_assignment/execution.py') == EXECUTION_SHA, 'execution drift')
    require(file_sha(artifact_path('assignment_evaluation_adapter.py')) == ADAPTER_SHA, 'adapter drift')
    require(file_sha(repo / 'nmr_assignment/source_reference.py') == SOURCE_REF_SHA, 'reference drift')
    sys.path.insert(0, str(repo))
    from nmr_assignment.execution import canonical_digest, _predictions
    spec = importlib.util.spec_from_file_location('C_frozen_eval', artifact_path('assignment_evaluation_adapter.py'))
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return (canonical_digest, _predictions, adapter)

def normalize_gold(gold, ledger, digest):
    hidden = gold['reference_hidden']
    native = gold['native_graph_snapshot']
    require(gold['input_id'] == ledger['input_id'], 'C gold/ledger identity')
    require(hidden['binding']['nucleus'] == '13C', 'C-only reference')
    require(hidden['raw_json_line'] == gold['raw_json_line'], 'C raw evidence mismatch')
    require(hidden['joint_gold_variants'] == gold['known_mask_joint_gold'], 'C joint family mismatch')
    snapshot = dict(canonical_smiles=native['canonical_smiles'], rdkit_version=native['rdkit_version'], atoms=native['graph_snapshot']['atoms'], bonds=native['graph_snapshot']['bonds'])
    quality = hidden['quality_receipt']
    admitted = ledger['scoreable_proposal'] is True and quality['decision'] == 'source_relative_keep' and all((quality['gate_outcomes'].get('C' + str(i), {}).get('passed') is True for i in range(1, 9)))
    normalized = dict(input_id=gold['input_id'], binding=hidden['binding'], source_raw_line=gold['raw_json_line'], joint_gold_parent_sets=gold['known_mask_joint_gold'], transport=hidden['transport'], scoreable=admitted, ledger_class=ledger['ledger_class'], truth_basis='source_relative_current_serialization', reference_basis='source_asserted_encoded_graph', trust_basis='internal_source_consistency', trusted_experimental=False, baseline_structure_snapshot=snapshot, baseline_structure_snapshot_sha256=digest(snapshot), C_original_reference_provenance=dict(quality_receipt=quality, policy_missing=ledger['policy_missing'], historical_C_quality_policy_status=ledger['historical_C_quality_policy_status']))
    return (normalized, dict(ledger, scoreable=admitted, roles=[ledger['native_role']]))

def verify_cache_inputs_binding(review, path, claimed_sha, inputs_path):
    """独审字段、CLI声明及实际 inputs 字节三方相等；CLI 自报不能替代审查。"""
    reviewed_sha = nested(review, path)
    require(reviewed_sha == claimed_sha, 'C cache inputs artifact not bound by independent review')
    require(file_sha(inputs_path) == reviewed_sha, 'C actual cache inputs artifact differs from independent review')

def check_metadata(args, execute=False):
    require(file_sha(args.reference_dir / 'manifest.json') == REFERENCE_MANIFEST_SHA, 'C reference manifest drift')
    require(file_sha(args.reference_review) == REFERENCE_REVIEW_SHA, 'C application review drift')
    manifest = json.loads((args.reference_dir / 'manifest.json').read_text())
    review = json.loads(args.reference_review.read_text())
    require(review['decision'] == 'PASS_C3745_SOURCE_RELATIVE_APPLICATION', 'whole C application PASS required')
    require(review['batch_manifest_sha256'] == REFERENCE_MANIFEST_SHA, 'C batch review binding')
    require((manifest['all_identity_denominator'], manifest['public_count'], manifest['public_unavailable']) == (binding('prepare_C_scoring_artifacts.cohort_count.7'), binding('prepare_C_scoring_artifacts.cohort_count.8'), binding('prepare_C_scoring_artifacts.cohort_count.additional_5')), 'C denominator changed')
    load_api(args.repo)
    ready = all((args.cache_review, args.cache_review_sha256, args.prediction_sha256, args.cache_input_sha256, args.cache_review_decision_path, args.cache_review_prediction_sha_path, args.cache_review_input_count_path, args.cache_review_inputs_sha_path))
    if ready:
        require(file_sha(args.cache_review) == args.cache_review_sha256, 'C cache review SHA mismatch')
        review = json.loads(Path(args.cache_review).read_text())
        decision = nested(review, args.cache_review_decision_path)
        require(isinstance(decision, str) and decision.startswith('PASS'), 'C cache independent PASS required')
        require(nested(review, args.cache_review_prediction_sha_path) == args.prediction_sha256, 'C prediction review binding')
        require(nested(review, args.cache_review_input_count_path) == binding('prepare_C_scoring_artifacts.cohort_count.9'), 'C cache complete model-input review required')
        verify_cache_inputs_binding(review, args.cache_review_inputs_sha_path, args.cache_input_sha256, args.cache_dir / 'inputs.jsonl')
    require(ready or not execute, 'C cache independent PASS bindings pending; execution refused')
    return (manifest, dict(status='C_REFERENCE_PASS_CACHE_PENDING' if not ready else 'C_REFERENCE_CACHE_PASS_NO_SCORING', original_denominator=binding('prepare_C_scoring_artifacts.cohort_count.10'), scorequeue=binding('prepare_C_scoring_artifacts.cohort_count.11'), public_unavailable=binding('prepare_C_scoring_artifacts.cohort_count.additional_5'), actual_rows_opened=False, scores=0, models=0))

def canonical_reference_view(public, gold, digest, adapter):
    """验证已审 source→native transport 后供 adapter 使用临时结构视图；public 原件不变。"""
    raw = gold['source_raw_line']
    require(byte_sha(raw.encode()) == gold['binding']['row_sha256'], 'C source raw binding mismatch')
    source = json.loads(raw)
    transport = gold['transport']
    lineage = transport['graph_lineage_evidence']
    payload = lineage['source_structure_payload']
    order = source['atom_order']
    expected = dict(smiles=source['smiles'], atoms=source['atoms'], atom_order={k: order[k] for k in ('basis', 'source_to_canonical', 'atomic_numbers')})
    require(payload == expected and public['smiles'] == source['smiles'], 'C public/source transport payload mismatch')
    require(public['input_id'] == gold['input_id'] and public['nucleus'] == gold['binding']['nucleus'] == '13C', 'C view identity mismatch')
    require(all((transport.get(k) == v for k, v in gold['binding'].items())), 'C view transport binding mismatch')
    require(transport.get('complete') is True and transport.get('enumeration_truncated') is False, 'C view incomplete transport')
    proof = transport['completeness_evidence']
    line_sha = adapter._lineage_digest(lineage)
    require(line_sha == transport['graph_lineage_evidence_sha256'] and digest(proof) == transport['completeness_evidence_sha256'] and (proof['graph_lineage_evidence_sha256'] == line_sha) and (proof.get('enumeration_truncated') is False), 'C view graph/projection evidence digest mismatch')
    snapshot = gold['baseline_structure_snapshot']
    require(lineage['canonical_smiles'] == snapshot['canonical_smiles'] and lineage['rdkit_version'] == snapshot['rdkit_version'] and (lineage['baseline_graph'] == {k: snapshot[k] for k in ('atoms', 'bonds')}), 'C view baseline graph mismatch')
    return dict(public, smiles=snapshot['canonical_smiles'])

def source_admission(public, gold, ledger, *, digest, adapter, source_artifacts, reference_review_sha):
    """只由 reference/application review 准入；失败预测仍保留相同 goldeligible 分母。"""
    iid = public['input_id']
    reference_public = canonical_reference_view(public, gold, digest, adapter)
    admitted = gold['scoreable'] is True and ledger['scoreable'] is True and bool(public['observations']) and (gold['transport'].get('complete') is True)
    joint = gold.get('joint_gold_parent_sets', ())
    nontrivial = admitted and bool(joint) and all((bool(targets) for variant in joint for _, targets in variant))
    admission_payload = dict(input_id=iid, binding=gold['binding'], reference_payload_sha256=digest(adapter._gold_payload(gold)), admitted=admitted, joint_nontrivial=bool(nontrivial), rule_version='C-current-serialization-direct-quality-v1', implementation_sha256=C_PRODUCER_SHA, evidence_ids=['sha256:' + reference_review_sha, 'sha256:' + source_artifacts['reference_manifest_sha256']], transport_completeness_evidence_sha256=gold['transport'].get('completeness_evidence_sha256'), transport_implementation_sha256=gold['transport'].get('graph_lineage_evidence', {}).get('implementation_sha256'), independent_application_review_sha256=reference_review_sha, reference_manifest_sha256=source_artifacts['reference_manifest_sha256'], source_artifact_bindings=source_artifacts, reference_track='source_relative_current_serialization', trusted_experimental=False)
    admission = wrap(admission_payload, digest)
    reference, reasons = adapter.build_reference(gold, reference_public, batch_admission_receipt=admission, source_cohort_sha256=gold['binding']['cohort_identity_manifest_sha256'])
    if admitted:
        require(all((v['admitted'] for v in reference['observation_admission'].values())) and (not reasons), 'source admission proof verification failed: ' + repr(reasons))
    return admission

def failed_cache_row(public, gold, ledger, cache_input, *, digest, adapter, source_artifacts, reference_review_sha):
    """失败缓存只输出准入和 cache_failed，不伪造 prediction、layout 或 lineage。"""
    require(cache_input['input_id'] == public['input_id'] == gold['input_id'] == ledger['input_id'], 'failed cache identity mismatch')
    require(cache_input['status'] == 'failed_retained', 'explicit failed_retained cache status required')
    admission = source_admission(public, gold, ledger, digest=digest, adapter=adapter, source_artifacts=source_artifacts, reference_review_sha=reference_review_sha)
    normalized = dict(cache_input, status='cache_failed', upstream_status=cache_input['status'], roles=list(ledger['roles']), original_input_line_sha256=source_artifacts['cache_input_row_sha256'])
    return dict(admission=dict(input_id=public['input_id'], receipt=admission), cache_input_ledger=normalized)

def package_row(public, gold, ledger, cache_input, cache_prediction, *, digest, typed, adapter, source_artifacts, reference_review_sha, cache_review_sha):
    iid = public['input_id']
    require(iid == gold['input_id'] == ledger['input_id'] == cache_input['input_id'], 'per-row input identity mismatch')
    require(public['nucleus'] == gold['binding']['nucleus'] == '13C' and cache_prediction['nucleus'] == '13C', 'C-only wrapper')
    require(cache_input['cache_key'] == cache_prediction['cache_key'], 'cache key join mismatch')
    require(cache_input['status'] == 'ok', 'this verified full cache requires original ok input status')
    require(gold['scoreable'] is ledger['scoreable'], 'gold/ledger eligibility disagreement')
    require(gold['ledger_class'] == ledger['ledger_class'], 'gold/ledger classification disagreement')
    require(gold['binding']['row_sha256'] == byte_sha(gold['source_raw_line'].encode()), 'original raw-line hash mismatch')
    pred = typed(cache_prediction['predictions'])
    serialized = asdict(pred)
    require(digest(serialized) == digest(cache_prediction['predictions']), 'typed predictions changed frozen payload')
    require(digest(cache_prediction['native_graph_snapshot']) == cache_prediction['native_graph_snapshot_sha256'], 'upstream native graph digest mismatch')
    actual_snapshot = dict(canonical_smiles=cache_prediction['canonical_smiles'], rdkit_version=cache_prediction['rdkit_version'], atoms=cache_prediction['native_graph_snapshot']['atoms'], bonds=cache_prediction['native_graph_snapshot']['bonds'])
    snapshot = gold['baseline_structure_snapshot']
    require(actual_snapshot == snapshot, 'native atoms/bonds/canonical/RDKit snapshot differs from frozen gold baseline')
    old_recipe = byte_sha(json.dumps(snapshot, sort_keys=True).encode())
    require(gold['baseline_structure_snapshot_sha256'] in (digest(snapshot), old_recipe), 'baseline snapshot SHA recipe mismatch')
    admission = source_admission(public, gold, ledger, digest=digest, adapter=adapter, source_artifacts=source_artifacts, reference_review_sha=reference_review_sha)
    lineage_payload = dict(input_id=iid, complete=True, baseline_structure_snapshot_sha256=gold['baseline_structure_snapshot_sha256'], native_structure_snapshot_sha256=digest(actual_snapshot), native_graph_snapshot_sha256=cache_prediction['native_graph_snapshot_sha256'], prediction_payload_sha256=digest(serialized), layout_sha256=digest(asdict(pred.layout)), attachment_sha256=digest(dict(blocks=pred.attachment_blocks, evidence_ids=pred.attachment_evidence_ids)), prediction_artifact_sha256=source_artifacts['prediction_artifact_sha256'], cache_key=cache_input['cache_key'], original_prediction_row_sha256=source_artifacts['prediction_row_sha256'], original_cache_input_row_sha256=source_artifacts['cache_input_row_sha256'], evidence_ids=['sha256:' + cache_review_sha, 'sha256:' + source_artifacts['prediction_artifact_sha256'], 'sha256:' + source_artifacts['prediction_row_sha256']], independent_cache_review_sha256=cache_review_sha, canonical_graph_recipe=cache_prediction.get('native_graph_recipe'), source_artifact_bindings=source_artifacts)
    lineage = wrap(lineage_payload, digest)
    adapter.prediction_mapping(pred, input_id=iid, gold=gold, prediction_lineage_receipt=lineage)
    normalized_input = dict(cache_input, input_id=iid, status='ready', upstream_status=cache_input['status'], roles=list(ledger['roles']), original_input_line_sha256=source_artifacts['cache_input_row_sha256'])
    prediction = dict(input_id=iid, predictions=serialized, native_structure_snapshot=actual_snapshot, original_cache_key=cache_input['cache_key'], prediction_artifact_sha256=source_artifacts['prediction_artifact_sha256'], original_prediction_row_sha256=source_artifacts['prediction_row_sha256'])
    return dict(admission=dict(input_id=iid, receipt=admission), lineage=dict(input_id=iid, receipt=lineage), prediction=prediction, cache_input_ledger=normalized_input)

def execute(args):
    manifest, gate = check_metadata(args, execute=True)
    digest, typed, adapter = load_api(args.repo)
    require(not args.output.exists() and args.output.name == 'C_scoring_inputs', 'fresh C_scoring_inputs required')
    required = {args.reference_dir / 'manifest.json': REFERENCE_MANIFEST_SHA, args.reference_review: REFERENCE_REVIEW_SHA, Path(args.cache_review): args.cache_review_sha256}
    for rel, item in manifest['artifacts'].items():
        required[args.reference_dir / rel] = item['sha256']
    predpath = args.cache_dir / 'predictions.jsonl'
    inputpath = args.cache_dir / 'inputs.jsonl'
    required[predpath] = args.prediction_sha256
    required[inputpath] = args.cache_input_sha256
    for path, expected in required.items():
        require(file_sha(path) == expected, 'upstream SHA mismatch:' + str(path))
    public, pi = jsonl(args.reference_dir / 'public.jsonl', 'input_id')
    gold, gi = jsonl(args.reference_dir / 'hidden/reference_gold.jsonl', 'input_id')
    ledger, li = jsonl(args.reference_dir / 'hidden/ledger.jsonl', 'input_id')
    unavailable, ui = jsonl(args.reference_dir / 'public_unavailable.jsonl', 'input_id')
    _, ci = jsonl(inputpath, 'input_id')
    _, predi = jsonl(predpath, 'cache_key')
    ids = [v['row']['input_id'] for v in public]
    fullids = [v['row']['input_id'] for v in ledger]
    require(len(ids) == binding('prepare_C_scoring_artifacts.cohort_count.12') and len(fullids) == binding('prepare_C_scoring_artifacts.cohort_count.13') and (len(ui) == binding('prepare_C_scoring_artifacts.cohort_count.additional_5')), 'C full denominators changed')
    require(set(ids).isdisjoint(ui) and set(ids) | set(ui) == set(fullids), 'C public/unavailable partition incomplete')
    require(set(gi) == set(fullids) and set(ci) == set(ids), 'C gold/cache identity closure')
    require(all((v['row']['native_role'] == 'native_val' for v in ledger)), 'C native role mismatch')
    records = {k: [] for k in ('gold', 'ledger', 'admissions', 'lineages', 'predictions', 'cache_input_ledger')}
    for value in public:
        p = value['row']
        iid = p['input_id']
        native_input = ci[iid]
        state = native_input['row']['status']
        require(state in ('ok', 'failed_retained'), 'unsupported actual C cache lifecycle status')
        key = native_input['row'].get('cache_key')
        native = predi.get(key) if state == 'ok' else None
        require(state != 'ok' or native is not None, 'C ok cache missing native prediction')
        original = gi[iid]
        g, l = normalize_gold(original['row'], li[iid]['row'], digest)
        g['C_original_gold_row_sha256'] = original['raw_sha256']
        bindings = dict(reference_manifest_sha256=REFERENCE_MANIFEST_SHA, public_artifact_sha256=required[args.reference_dir / 'public.jsonl'], gold_artifact_sha256=required[args.reference_dir / 'hidden/reference_gold.jsonl'], ledger_artifact_sha256=required[args.reference_dir / 'hidden/ledger.jsonl'], prediction_artifact_sha256=args.prediction_sha256, cache_input_artifact_sha256=args.cache_input_sha256, public_row_sha256=value['raw_sha256'], gold_row_sha256=original['raw_sha256'], ledger_row_sha256=li[iid]['raw_sha256'], cache_input_row_sha256=native_input['raw_sha256'], prediction_row_sha256=native['raw_sha256'] if native else None)
        if state == 'failed_retained':
            wrapped = failed_cache_row(p, g, l, native_input['row'], digest=digest, adapter=adapter, source_artifacts=bindings, reference_review_sha=REFERENCE_REVIEW_SHA)
            records['gold'].append(g)
            records['ledger'].append(l)
            records['admissions'].append(wrapped['admission'])
            records['cache_input_ledger'].append(wrapped['cache_input_ledger'])
            continue
        wrapped = package_row(p, g, l, native_input['row'], native['row'], digest=digest, typed=typed, adapter=adapter, source_artifacts=bindings, reference_review_sha=REFERENCE_REVIEW_SHA, cache_review_sha=args.cache_review_sha256)
        records['gold'].append(g)
        records['ledger'].append(l)
        for name, key in (('admissions', 'admission'), ('lineages', 'lineage'), ('predictions', 'prediction'), ('cache_input_ledger', 'cache_input_ledger')):
            records[name].append(wrapped[key])
    coverage = []
    for item in ledger:
        r = item['row']
        iid = r['input_id']
        coverage.append(dict(r, scorequeue_status='queued' if iid in pi else 'public_unavailable_unknown', original_ledger_ordinal=item['ordinal'], original_ledger_row_sha256=item['raw_sha256'], public_available=iid in pi, pregold_status='reviewed_reference_present' if iid in pi else 'unknown_not_admitted', unavailable_evidence=ui[iid]['row'] if iid in ui else None))
    for path, expected in required.items():
        require(file_sha(path) == expected, 'upstream mutated during packaging')
    args.output.mkdir()
    import shutil
    shutil.copyfile(args.reference_dir / 'public.jsonl', args.output / 'public.jsonl')
    shutil.copyfile(args.reference_dir / 'public_unavailable.jsonl', args.output / 'public_unavailable.jsonl')
    records['coverage_ledger'] = coverage
    for name, rows in records.items():
        with (args.output / (name + '.jsonl')).open('x') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n')
    files = {p.stem: dict(path=str(p.resolve()), sha256=file_sha(p), bytes=p.stat().st_size) for p in args.output.iterdir()}
    result = dict(schema='C_scoring_input_evidence_packaging_v1', status='EVIDENCE_PACKAGED_NO_SCORING', records=binding('prepare_C_scoring_artifacts.cohort_count.14'), original_identity_denominator=binding('prepare_C_scoring_artifacts.cohort_count.15'), public_unavailable=binding('prepare_C_scoring_artifacts.cohort_count.additional_5'), ordered_input_ids_sha256=digest(ids), ordered_full_identity_ids_sha256=digest(fullids), inputs=files, upstream_sha256={str(p): v for p, v in required.items()}, source_cohort_sha256=records['gold'][0]['binding']['cohort_identity_manifest_sha256'], source_reference_implementation_sha256=SOURCE_REF_SHA, C_producer_implementation_sha256=C_PRODUCER_SHA, execution_implementation_sha256=EXECUTION_SHA, evaluation_adapter_implementation_sha256=ADAPTER_SHA, packager_sha256=file_sha(Path(__file__)), policy_missing_preserved=True, historical_C_quality_unknown_preserved=True, admitted_rows=sum((r['receipt']['payload']['admitted'] for r in records['admissions'])), cache_lifecycle_counts={state: sum((r['status'] == state for r in records['cache_input_ledger'])) for state in ('ready', 'cache_failed')}, prediction_rows=len(records['predictions']), lineage_rows=len(records['lineages']), all_original_ledger_rows_retained=True, trusted_experimental=False, solver_certificates_created=0, models=0, scores=0, test_reads=False)
    (args.output / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return dict(status=result['status'], records=binding('prepare_C_scoring_artifacts.cohort_count.16'), original_identity_denominator=binding('prepare_C_scoring_artifacts.cohort_count.17'), manifest_sha256=file_sha(args.output / 'manifest.json'), models=0, scores=0)

def synthetic_full(args):
    digest, typed, adapter = load_api(args.repo)
    from nmr_assignment.mapping import build_capacity_layout, FrozenCapacityPredictions, FrozenCarrier
    raw = json.dumps(dict(source_ref='synthetic', nucleus='13C', record_id='synthetic', smiles='[CH3][CH3]', atoms=['C', 'C'], atom_order=dict(basis='source_mol', source_to_canonical=[0, 1], atomic_numbers=[6, 6]), atom_targets=[1, 2], atom_target_mask=[1, 1]))
    binding = dict(source='synthetic', nucleus='13C', record_id='synthetic', structure_id=byte_sha(b'[CH3][CH3]'), source_sha256='1' * 64, row_sha256=byte_sha(raw.encode()), policy_sha256='2' * 64, cohort_identity_manifest_sha256='3' * 64)
    snapshot = dict(canonical_smiles='CC', rdkit_version='synthetic', atoms=[], bonds=[])
    graphline = dict(implementation_sha256='4' * 64, canonical_smiles='CC', rdkit_version='synthetic', source_structure_payload={k: json.loads(raw)[k] for k in ('smiles', 'atoms', 'atom_order')}, baseline_graph=dict(atoms=[], bonds=[]))
    proof = dict(graph_lineage_evidence_sha256=digest(graphline), enumeration_truncated=False, parent_projection_rows=[['0', '1']])
    transport = dict(binding, complete=True, enumeration_truncated=False, graph_lineage_evidence=graphline, graph_lineage_evidence_sha256=digest(graphline), completeness_evidence=proof, completeness_evidence_sha256=digest(proof), joint_maps=[{'0': '0', '1': '1'}])
    gold = dict(input_id='synthetic-only', binding=binding, source_raw_line=raw, joint_gold_parent_sets=[[['bin:0', ['0']], ['bin:1', ['1']]]], transport=transport, scoreable=True, ledger_class='unique_parent', truth_basis='source_relative_current_serialization', reference_basis='source_asserted_encoded_graph', trust_basis='internal_source_consistency', trusted_experimental=False, baseline_structure_snapshot=snapshot, baseline_structure_snapshot_sha256=digest(snapshot))
    public = dict(input_id=gold['input_id'], nucleus='13C', smiles='[CH3][CH3]', observations=[dict(bin_id='bin:0', ppm_decimal='1'), dict(bin_id='bin:1', ppm_decimal='2')])
    layout = build_capacity_layout(dict(nucleus='13C', parent_mass={'0': 1, '1': 1}, isotope_count_verified=True, evidence_ids=['synthetic-counts'], partition_hypothesis_id='synthetic'))
    pred = FrozenCapacityPredictions(layout, tuple((FrozenCarrier('c' + str(i), u.unit_id, float(i), 1.0, None, 'unknown', ('x' + str(i),)) for i, u in enumerate(layout.units))), (), ())
    ledger = dict(input_id=gold['input_id'], scoreable=True, ledger_class='unique_parent', roles=['synthetic-val'], connectivity_sha256='5' * 64)
    ci = dict(input_id=gold['input_id'], cache_key='synthetic-cache', status='ok')
    native = dict(cache_key=ci['cache_key'], nucleus='13C', canonical_smiles='CC', rdkit_version='synthetic', native_graph_snapshot=dict(atoms=[], bonds=[]), native_graph_snapshot_sha256=digest(dict(atoms=[], bonds=[])), predictions=asdict(pred))
    bindings = dict(reference_manifest_sha256='6' * 64, prediction_artifact_sha256='7' * 64, prediction_row_sha256='8' * 64, cache_input_row_sha256='9' * 64)
    kwargs = dict(digest=digest, typed=typed, adapter=adapter, source_artifacts=bindings, reference_review_sha='a' * 64, cache_review_sha='b' * 64)
    original_public = json.loads(json.dumps(public))
    result = package_row(public, gold, ledger, ci, native, **kwargs)
    require(public == original_public and public['smiles'] != snapshot['canonical_smiles'], 'source public must remain unchanged')
    bad_public = dict(public, smiles='unbound-source')
    try:
        package_row(bad_public, gold, ledger, ci, native, **kwargs)
    except ValueError:
        pass
    else:
        raise AssertionError('unbound source serialization accepted')
    require(result['lineage']['receipt']['payload']['prediction_payload_sha256'] == digest(asdict(pred)), 'canonical prediction payload binding')
    require(result['cache_input_ledger']['status'] == 'ready' and result['cache_input_ledger']['roles'] == ledger['roles'], 'runner cache status and roles')
    require(result['admission']['receipt']['payload']['admitted'] is True, 'synthetic whole-review admission')
    failed = failed_cache_row(public, gold, ledger, dict(ci, status='failed_retained', error='ValueError:unsupported_feature:79/54'), digest=digest, adapter=adapter, source_artifacts=bindings, reference_review_sha='a' * 64)
    require(failed['admission'] == result['admission'], 'cache failure must not alter source admission')
    require(failed['cache_input_ledger']['status'] == 'cache_failed' and failed['cache_input_ledger']['error'] == 'ValueError:unsupported_feature:79/54', 'failure reason/status retained')
    require(set(failed) == {'admission', 'cache_input_ledger'}, 'failed row cannot mint prediction/lineage')
    for method in ('B0', 'B1', 'B2'):
        bundle = adapter.evaluate_record(gold, canonical_reference_view(public, gold, digest, adapter), None, dict(status='cache_failed', result=None, timed_out=False), method=method, roles=('native_val',), source_cohort_sha256=gold['binding']['cohort_identity_manifest_sha256'], connectivity_sha256='f' * 64, batch_admission_receipt=failed['admission']['receipt'])
        exact = [r for r in bundle['rows'] if r.metric == 'exact_observation']
        require(len(exact) == 2 and all((r.eligible and (not r.prediction_supported) and (not r.success) for r in exact)), 'failed cache must retain all-method goldeligible observation denominator')
        require(bundle['pipeline_status'] is not None, 'actual failed-cache observations retain unsupported pipeline')
        for row in bundle['rows']:
            if row.metric != 'compatible_observation':
                continue
            cal = adapter.calibration_record_from_evaluation(row, bundle, cohort_sha256='1' * 64, source_sha256='2' * 64, label_sha256='3' * 64, rule_sha256='4' * 64, relative_tolerance=1e-07)
            require(cal.gold_eligible and (not cal.prediction_supported) and (not cal.margin_certified) and (cal.margin is None), 'existing calibration bridge must retain failed eligible denominator without publication')
    restricted = dict(gold, scoreable=False, ledger_class='restricted')
    denied = package_row(public, restricted, dict(ledger, scoreable=False, ledger_class='restricted'), ci, native, **kwargs)
    require(denied['admission']['receipt']['payload']['admitted'] is False, 'restricted row must remain unadmitted')
    corrupted = dict(native, canonical_smiles='different')
    try:
        package_row(public, gold, ledger, ci, corrupted, **kwargs)
    except ValueError:
        pass
    else:
        raise AssertionError('native graph mismatch accepted')
    return dict(status='SYNTHETIC_EVIDENCE_PACKAGING_PASS', checks=binding('prepare_C_scoring_artifacts.cohort_count.additional_5'), scores=0, models=0, real_rows_opened=False)

def synthetic(args):
    synthetic_full(args)
    digest, typed, adapter = load_api(args.repo)
    hidden = dict(binding={'nucleus': '13C'}, raw_json_line='synthetic', joint_gold_variants=[[['bin:0', ['0']]]], transport={}, quality_receipt=dict(decision='source_relative_keep', gate_outcomes={'C' + str(i): {'passed': True} for i in range(1, 9)}))
    gold = dict(input_id='C-' + '1' * 64, reference_hidden=hidden, raw_json_line='synthetic', known_mask_joint_gold=hidden['joint_gold_variants'], native_graph_snapshot=dict(canonical_smiles='C', rdkit_version='synthetic', graph_snapshot=dict(atoms=[], bonds=[])))
    ledger = dict(input_id=gold['input_id'], scoreable_proposal=True, ledger_class='unique_parent', native_role='native_val', policy_missing=True, historical_C_quality_policy_status='unknown')
    g, l = normalize_gold(gold, ledger, digest)
    require(g['scoreable'] and l['roles'] == ['native_val'] and (g['joint_gold_parent_sets'] == gold['known_mask_joint_gold']), 'C conversion')
    require(g['C_original_reference_provenance']['policy_missing'] is True, 'missing policy must survive')
    denied, _ = normalize_gold(gold, dict(ledger, scoreable_proposal=False), digest)
    require(denied['scoreable'] is False, 'unscoreable not admitted')
    broken = dict(gold, known_mask_joint_gold=[])
    try:
        normalize_gold(broken, ledger, digest)
    except ValueError:
        pass
    else:
        raise AssertionError('joint family changed accepted')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='C_review_inputs_synthetic_') as tmp:
        artifact = Path(tmp) / 'inputs.jsonl'
        artifact.write_bytes(b'synthetic-original')
        reviewed = file_sha(artifact)
        review = {'files': {'inputs': reviewed}}
        verify_cache_inputs_binding(review, '["files","inputs"]', reviewed, artifact)
        artifact.write_bytes(b'synthetic-replaced')
        try:
            verify_cache_inputs_binding(review, '["files","inputs"]', file_sha(artifact), artifact)
        except ValueError:
            pass
        else:
            raise AssertionError('CLI local hash bypassed independent inputs review')
        try:
            verify_cache_inputs_binding(review, '["files","inputs"]', reviewed, artifact)
        except ValueError:
            pass
        else:
            raise AssertionError('modified actual inputs artifact accepted')
    return dict(status='C_SYNTHETIC_SCHEMA_AND_EVIDENCE_PASS', checks=23, scores=0, models=0, real_rows_opened=False)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--execute', action='store_true')
    p.add_argument('--checkonly', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--repo', type=Path, default=repository())
    p.add_argument('--reference-dir', type=Path, default=artifact_path('C_reference_batch'))
    p.add_argument('--reference-review', type=Path, default=artifact_path('reviews/C_batch_application_independent_review_astra.json'))
    p.add_argument('--cache-dir', type=Path, default=artifact_path('C_frozen_cache_artifacts/result'))
    p.add_argument('--output', type=Path, default=artifact_path('C_scoring_inputs'))
    for name in ('cache-review', 'cache-review-sha256', 'prediction-sha256', 'cache-input-sha256', 'cache-review-decision-path', 'cache-review-prediction-sha-path', 'cache-review-input-count-path', 'cache-review-inputs-sha-path'):
        p.add_argument('--' + name)
    a = p.parse_args()
    result = synthetic(a) if a.self_test else execute(a) if a.execute else check_metadata(a)[1]
    result['source_sha256'] = file_sha(Path(__file__))
    print(json.dumps(result, ensure_ascii=False))
if __name__ == '__main__':
    main()
