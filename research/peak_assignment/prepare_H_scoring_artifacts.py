# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：将既有 H1408 reference/cache 包成 runner 输入证据，不运行评分或模型。\n默认 --checkonly 仅核对已冻结代码和批次审查元数据；--execute 要求 cache 独审 PASS 的\n精确 SHA/字段绑定，才读取既有 public/gold/ledger/cache。不会执行任何 solver 或造执行证书。\n每个 source row 保留原 public 顺序 input_id；gold/public 原字节复制，ledger roles/connectivity\n原值保留。source row 不是原 query 分母替代物；unknown/restricted 仍保留且不准入。\n准入只封装已通过的 repaired 整批 application review，不把早期 component PASS 当 reference PASS。\nprediction lineage 仅比较已持久 native atoms/bonds/canonical/version 与 gold baseline snapshot，\n并校验 FrozenCapacityPredictions、layout、attachment、原 artifact/行 SHA；不选择任何身份映射，\n不计算预测与标签的位移差。唯一 JSON canonical digest 来自冻结 execution.canonical_digest。\n输出 fresh H_scoring_inputs 的七份同序 unique-input_id JSONL 及 manifest。admissions/lineages\n的 receipt={payload,sha256}；cache_input_ledger 使用 ready 等 runner 状态，原状态单独保留。\n--self-test 只用合成图/标签验证包装与负例，无真实数据、模型、solver 或科学评价。\n'
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
D = workspace()
EXECUTION_SHA = binding('prepare_H_scoring_artifacts.sha_or_identity.1')
ADAPTER_SHA = binding('prepare_H_scoring_artifacts.sha_or_identity.2')
SOURCE_REF_SHA = binding('prepare_H_scoring_artifacts.sha_or_identity.3')
REFERENCE_REVIEW_SHA = binding('prepare_H_scoring_artifacts.sha_or_identity.4')
REFERENCE_MANIFEST_SHA = binding('prepare_H_scoring_artifacts.sha_or_identity.5')
HANDOFF_SHA = binding('prepare_H_scoring_artifacts.sha_or_identity.6')
PREDICTION_SHA = binding('prepare_H_scoring_artifacts.sha_or_identity.7')
CACHE_INPUT_SHA = binding('prepare_H_scoring_artifacts.sha_or_identity.8')

def require(value, message):
    if not value:
        raise ValueError(message)

def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def byte_sha(value):
    return hashlib.sha256(value).hexdigest()

def load_api(repo):
    require(file_sha(repo / 'nmr_assignment/execution.py') == EXECUTION_SHA, 'execution exact version changed')
    require(file_sha(artifact_path('assignment_evaluation_adapter.py')) == ADAPTER_SHA, 'evaluation adapter exact version changed')
    require(file_sha(repo / 'nmr_assignment/source_reference.py') == SOURCE_REF_SHA, 'source reference exact version changed')
    sys.path.insert(0, str(repo))
    from nmr_assignment.execution import canonical_digest, _predictions
    spec = importlib.util.spec_from_file_location('frozen_H_packaging_adapter', artifact_path('assignment_evaluation_adapter.py'))
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return (canonical_digest, _predictions, adapter)

def nested(value, path):
    for key in json.loads(path):
        value = value[key]
    return value

def check_metadata(args, *, execute=False):
    require(file_sha(args.reference_review) == REFERENCE_REVIEW_SHA, 'repaired application review exact SHA changed')
    review = json.loads(args.reference_review.read_text())
    require(review['decision'] == 'PASS_H_REPAIRED_SAME_1408_APPLICATION_DELTA', 'whole repaired application review PASS required')
    require(review['new_manifest_sha256'] == REFERENCE_MANIFEST_SHA and review['counts']['records'] == binding('prepare_H_scoring_artifacts.cohort_count.9'), 'review batch binding mismatch')
    require(file_sha(args.reference_dir / 'manifest.json') == REFERENCE_MANIFEST_SHA, 'repaired reference manifest changed')
    manifest = json.loads((args.reference_dir / 'manifest.json').read_text())
    require(manifest['source_reference_implementation_sha256'] == SOURCE_REF_SHA, 'reference implementation binding mismatch')
    require(file_sha(args.handoff) == HANDOFF_SHA, 'author handoff exact SHA changed')
    handoff = json.loads(args.handoff.read_text())
    require(handoff['actual_exit'] == 0 and handoff['counts']['public_inputs'] == binding('prepare_H_scoring_artifacts.cohort_count.10') and (handoff['counts']['joined_inputs'] == binding('prepare_H_scoring_artifacts.cohort_count.11')) and (handoff['counts']['unique_predictions'] == binding('prepare_H_scoring_artifacts.cohort_count.12')), 'full-row handoff count mismatch')
    load_api(args.repo)
    ready = all((args.cache_review, args.cache_review_sha256, args.cache_review_decision_path, args.cache_review_prediction_sha_path, args.cache_review_input_count_path))
    if not ready:
        require(not execute, 'execute requires exact cache independent PASS receipt and explicit content field bindings')
        return (manifest, handoff, dict(status='REFERENCE_APPLICATION_PASS_CACHE_INDEPENDENT_REVIEW_PENDING', actual_rows_opened=False))
    cache_review = Path(args.cache_review)
    require(file_sha(cache_review) == args.cache_review_sha256, 'cache independent review SHA mismatch')
    cache = json.loads(cache_review.read_text())
    decision = nested(cache, args.cache_review_decision_path)
    require(isinstance(decision, str) and decision.startswith('PASS'), 'cache independent review must PASS')
    require(nested(cache, args.cache_review_prediction_sha_path) == PREDICTION_SHA, 'cache review does not bind actual upstream prediction artifact')
    require(nested(cache, args.cache_review_input_count_path) == binding('prepare_H_scoring_artifacts.cohort_count.13'), 'cache independent review must cover all 1408 inputs')
    return (manifest, handoff, dict(status='REFERENCE_AND_CACHE_PASS_METADATA_CHECKED_NO_SCORING', actual_rows_opened=False, cache_independent_review_sha256=args.cache_review_sha256))

def jsonl(path, key):
    ordered = []
    index = {}
    with Path(path).open('rb') as stream:
        for ordinal, raw in enumerate(stream):
            if not raw.strip():
                raise ValueError('blank source JSONL line')
            row = json.loads(raw)
            identity = row[key]
            require(identity not in index, 'duplicate ' + key + ' in ' + str(path))
            item = dict(row=row, raw=raw, raw_sha256=byte_sha(raw), ordinal=ordinal)
            ordered.append(item)
            index[identity] = item
    return (ordered, index)

def wrap(payload, digest):
    return dict(payload=payload, sha256=digest(payload))

def package_row(public, gold, ledger, cache_input, cache_prediction, *, digest, typed, adapter, source_artifacts, reference_review_sha, cache_review_sha):
    iid = public['input_id']
    require(iid == gold['input_id'] == ledger['input_id'] == cache_input['input_id'], 'per-row input identity mismatch')
    require(public['nucleus'] == gold['binding']['nucleus'] == '1H' and cache_prediction['nucleus'] == '1H', 'H-only wrapper')
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
    require(public['smiles'] == actual_snapshot['canonical_smiles'], 'public canonical structure mismatch')
    admitted = gold['scoreable'] is True and ledger['ledger_class'] in ('admitted', 'ambiguous') and bool(public['observations']) and (gold['transport'].get('complete') is True)
    joint = gold.get('joint_gold_parent_sets', ())
    nontrivial = admitted and bool(joint) and all((bool(targets) for variant in joint for _, targets in variant))
    admission_payload = dict(input_id=iid, binding=gold['binding'], reference_payload_sha256=digest(adapter._gold_payload(gold)), admitted=admitted, joint_nontrivial=bool(nontrivial), rule_version='source-reference:' + SOURCE_REF_SHA, implementation_sha256=SOURCE_REF_SHA, evidence_ids=['sha256:' + reference_review_sha, 'sha256:' + source_artifacts['reference_manifest_sha256']], transport_completeness_evidence_sha256=gold['transport'].get('completeness_evidence_sha256'), transport_implementation_sha256=gold['transport'].get('graph_lineage_evidence', {}).get('implementation_sha256'), independent_application_review_sha256=reference_review_sha, reference_manifest_sha256=source_artifacts['reference_manifest_sha256'], source_artifact_bindings=source_artifacts, reference_track='source_relative_current_serialization', trusted_experimental=False)
    admission = wrap(admission_payload, digest)
    reference, reasons = adapter.build_reference(gold, public, batch_admission_receipt=admission, source_cohort_sha256=gold['binding']['cohort_identity_manifest_sha256'])
    if admitted:
        require(all((v['admitted'] for v in reference['observation_admission'].values())) and (not reasons), 'source admission proof verification failed: ' + repr(reasons))
    lineage_payload = dict(input_id=iid, complete=True, baseline_structure_snapshot_sha256=gold['baseline_structure_snapshot_sha256'], native_structure_snapshot_sha256=digest(actual_snapshot), native_graph_snapshot_sha256=cache_prediction['native_graph_snapshot_sha256'], prediction_payload_sha256=digest(serialized), layout_sha256=digest(asdict(pred.layout)), attachment_sha256=digest(dict(blocks=pred.attachment_blocks, evidence_ids=pred.attachment_evidence_ids)), prediction_artifact_sha256=source_artifacts['prediction_artifact_sha256'], cache_key=cache_input['cache_key'], original_prediction_row_sha256=source_artifacts['prediction_row_sha256'], original_cache_input_row_sha256=source_artifacts['cache_input_row_sha256'], evidence_ids=['sha256:' + cache_review_sha, 'sha256:' + source_artifacts['prediction_artifact_sha256'], 'sha256:' + source_artifacts['prediction_row_sha256']], independent_cache_review_sha256=cache_review_sha, canonical_graph_recipe=cache_prediction.get('native_graph_recipe'), source_artifact_bindings=source_artifacts)
    lineage = wrap(lineage_payload, digest)
    adapter.prediction_mapping(pred, input_id=iid, gold=gold, prediction_lineage_receipt=lineage)
    normalized_input = dict(cache_input, input_id=iid, status='ready', upstream_status=cache_input['status'], roles=list(ledger['roles']), original_input_line_sha256=source_artifacts['cache_input_row_sha256'])
    prediction = dict(input_id=iid, predictions=serialized, native_structure_snapshot=actual_snapshot, original_cache_key=cache_input['cache_key'], prediction_artifact_sha256=source_artifacts['prediction_artifact_sha256'], original_prediction_row_sha256=source_artifacts['prediction_row_sha256'])
    return dict(admission=dict(input_id=iid, receipt=admission), lineage=dict(input_id=iid, receipt=lineage), prediction=prediction, cache_input_ledger=normalized_input)

def execute(args):
    manifest, handoff, gate = check_metadata(args, execute=True)
    digest, typed, adapter = load_api(args.repo)
    require(not args.output.exists() and args.output.name == 'H_scoring_inputs', 'fresh H_scoring_inputs directory required')
    required = {args.reference_dir / 'manifest.json': REFERENCE_MANIFEST_SHA, args.reference_review: REFERENCE_REVIEW_SHA, args.handoff: HANDOFF_SHA, Path(args.cache_review): args.cache_review_sha256}
    for name, item in manifest['files'].items():
        required[args.reference_dir / name] = item['sha256']
    predpath = args.cache_dir / 'predictions.jsonl'
    inputpath = args.cache_dir / 'inputs.jsonl'
    required[predpath] = PREDICTION_SHA
    required[inputpath] = CACHE_INPUT_SHA
    for path, expected in required.items():
        require(file_sha(path) == expected, 'frozen upstream artifact SHA changed: ' + str(path))
    pubpath = args.reference_dir / 'public/anonymous_records.jsonl'
    goldpath = args.reference_dir / 'hidden/gold_and_source_evidence.jsonl'
    public, pubindex = jsonl(pubpath, 'input_id')
    gold, goldindex = jsonl(goldpath, 'input_id')
    rawinputs, inputindex = jsonl(inputpath, 'input_id')
    _, predictionindex = jsonl(predpath, 'cache_key')
    ledger = json.loads((args.reference_dir / 'hidden/ledger.json').read_text())
    require(len(ledger) == binding('prepare_H_scoring_artifacts.cohort_count.14') and len({r['input_id'] for r in ledger}) == binding('prepare_H_scoring_artifacts.cohort_count.15'), 'full unique reference ledger required')
    ledgerindex = {r['input_id']: r for r in ledger}
    ids = [v['row']['input_id'] for v in public]
    require(len(ids) == binding('prepare_H_scoring_artifacts.cohort_count.16') and set(ids) == set(goldindex) == set(ledgerindex) == set(inputindex), 'all 1408 input IDs must be preserved')
    require([v['row']['input_id'] for v in gold] == ids and [r['input_id'] for r in ledger] == ids, 'reference input ordering changed')
    require(len(predictionindex) == binding('prepare_H_scoring_artifacts.cohort_count.17'), 'actual deduplicated native cache cardinality mismatch')
    packaged = []
    for value in public:
        p = value['row']
        iid = p['input_id']
        g = goldindex[iid]['row']
        l = ledgerindex[iid]
        ci = inputindex[iid]
        require(ci['row']['cache_key'] in predictionindex, 'input cache key missing prediction row')
        native = predictionindex[ci['row']['cache_key']]
        bindings = dict(reference_manifest_sha256=REFERENCE_MANIFEST_SHA, public_artifact_sha256=required[pubpath], gold_artifact_sha256=required[goldpath], ledger_artifact_sha256=required[args.reference_dir / 'hidden/ledger.json'], prediction_artifact_sha256=PREDICTION_SHA, cache_input_artifact_sha256=CACHE_INPUT_SHA, public_row_sha256=value['raw_sha256'], gold_row_sha256=goldindex[iid]['raw_sha256'], cache_input_row_sha256=ci['raw_sha256'], prediction_row_sha256=native['raw_sha256'])
        packaged.append(package_row(p, g, l, ci['row'], native['row'], digest=digest, typed=typed, adapter=adapter, source_artifacts=bindings, reference_review_sha=REFERENCE_REVIEW_SHA, cache_review_sha=args.cache_review_sha256))
    for path, expected in required.items():
        require(file_sha(path) == expected, 'upstream artifact mutated during packaging')
    args.output.mkdir()
    shutil.copyfile(pubpath, args.output / 'public.jsonl')
    shutil.copyfile(goldpath, args.output / 'gold.jsonl')
    records = dict(ledger=[ledgerindex[iid] for iid in ids], admissions=[p['admission'] for p in packaged], lineages=[p['lineage'] for p in packaged], predictions=[p['prediction'] for p in packaged], cache_input_ledger=[p['cache_input_ledger'] for p in packaged])
    for name, rows in records.items():
        with (args.output / (name + '.jsonl')).open('x') as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
    files = {p.stem: dict(path=str(p.resolve()), sha256=file_sha(p), bytes=p.stat().st_size) for p in args.output.iterdir()}
    require(files['public']['sha256'] == required[pubpath] and files['gold']['sha256'] == required[goldpath], 'copied public/gold bytes differ from frozen original')
    artifact = dict(schema='H_scoring_input_evidence_packaging_v1', status='EVIDENCE_PACKAGED_NO_SCORING', records=binding('prepare_H_scoring_artifacts.cohort_count.18'), ordered_input_ids_sha256=digest(ids), unique_native_cache_rows=binding('prepare_H_scoring_artifacts.cohort_count.19'), unique_prediction_payloads=len({p['lineage']['receipt']['payload']['prediction_payload_sha256'] for p in packaged}), inputs=files, upstream_sha256={str(p): v for p, v in required.items()}, source_cohort_sha256=gold[0]['row']['binding']['cohort_identity_manifest_sha256'], source_reference_implementation_sha256=SOURCE_REF_SHA, execution_implementation_sha256=EXECUTION_SHA, evaluation_adapter_implementation_sha256=ADAPTER_SHA, packager_sha256=file_sha(Path(__file__)), source_rows_not_original_query_denominator=True, all_ledger_rows_retained=True, admitted_rows=sum((p['admission']['receipt']['payload']['admitted'] for p in packaged)), trusted_experimental=False, solver_certificates_created=0, models=0, scores=0, test_reads=False)
    with (args.output / 'manifest.json').open('x') as stream:
        json.dump(artifact, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return dict(status=artifact['status'], records=binding('prepare_H_scoring_artifacts.cohort_count.20'), admitted_rows=artifact['admitted_rows'], manifest=str(args.output / 'manifest.json'), manifest_sha256=file_sha(args.output / 'manifest.json'), scores=0, models=0)

def synthetic(args):
    digest, typed, adapter = load_api(args.repo)
    from nmr_assignment.mapping import build_capacity_layout, FrozenCapacityPredictions, FrozenCarrier
    raw = json.dumps(dict(source_ref='synthetic', nucleus='1H', record_id='synthetic', smiles='CC', atom_targets=[1, 2], atom_target_mask=[1, 1]))
    binding = dict(source='synthetic', nucleus='1H', record_id='synthetic', structure_id=byte_sha(b'CC'), source_sha256='1' * 64, row_sha256=byte_sha(raw.encode()), policy_sha256='2' * 64, cohort_identity_manifest_sha256='3' * 64)
    snapshot = dict(canonical_smiles='CC', rdkit_version='synthetic', atoms=[], bonds=[])
    graphline = dict(implementation_sha256='4' * 64, canonical_smiles='CC', baseline_graph=dict(atoms=[], bonds=[]))
    proof = dict(graph_lineage_evidence_sha256=digest(graphline), enumeration_truncated=False, parent_projection_rows=[['0', '1']])
    transport = dict(binding, complete=True, enumeration_truncated=False, graph_lineage_evidence=graphline, graph_lineage_evidence_sha256=digest(graphline), completeness_evidence=proof, completeness_evidence_sha256=digest(proof), joint_maps=[{'0': '0', '1': '1'}])
    gold = dict(input_id='synthetic-only', binding=binding, source_raw_line=raw, joint_gold_parent_sets=[[['bin:0', ['0']], ['bin:1', ['1']]]], transport=transport, scoreable=True, ledger_class='admitted', truth_basis='source_relative_current_serialization', reference_basis='source_asserted_encoded_graph', trust_basis='internal_source_consistency', trusted_experimental=False, baseline_structure_snapshot=snapshot, baseline_structure_snapshot_sha256=digest(snapshot))
    public = dict(input_id=gold['input_id'], nucleus='1H', smiles='CC', observations=[dict(bin_id='bin:0', ppm_decimal='1'), dict(bin_id='bin:1', ppm_decimal='2')])
    layout = build_capacity_layout(dict(nucleus='1H', parent_mass={'0': 1, '1': 1}, isotope_count_verified=True, evidence_ids=['synthetic-counts'], partition_hypothesis_id='synthetic'))
    pred = FrozenCapacityPredictions(layout, tuple((FrozenCarrier('c' + str(i), u.unit_id, float(i), 1.0, None, 'unknown', ('x' + str(i),)) for i, u in enumerate(layout.units))), (), ())
    ledger = dict(input_id=gold['input_id'], scoreable=True, ledger_class='admitted', roles=['synthetic-val'], connectivity_sha256='5' * 64)
    ci = dict(input_id=gold['input_id'], cache_key='synthetic-cache', status='ok')
    native = dict(cache_key=ci['cache_key'], nucleus='1H', canonical_smiles='CC', rdkit_version='synthetic', native_graph_snapshot=dict(atoms=[], bonds=[]), native_graph_snapshot_sha256=digest(dict(atoms=[], bonds=[])), predictions=asdict(pred))
    bindings = dict(reference_manifest_sha256='6' * 64, prediction_artifact_sha256='7' * 64, prediction_row_sha256='8' * 64, cache_input_row_sha256='9' * 64)
    kwargs = dict(digest=digest, typed=typed, adapter=adapter, source_artifacts=bindings, reference_review_sha='a' * 64, cache_review_sha='b' * 64)
    result = package_row(public, gold, ledger, ci, native, **kwargs)
    require(result['lineage']['receipt']['payload']['prediction_payload_sha256'] == digest(asdict(pred)), 'canonical prediction payload binding')
    require(result['cache_input_ledger']['status'] == 'ready' and result['cache_input_ledger']['roles'] == ledger['roles'], 'runner cache status and roles')
    require(result['admission']['receipt']['payload']['admitted'] is True, 'synthetic whole-review admission')
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
    return dict(status='SYNTHETIC_EVIDENCE_PACKAGING_PASS', checks=5, scores=0, models=0, real_rows_opened=False)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--checkonly', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--repo', type=Path, default=repository())
    parser.add_argument('--reference-dir', type=Path, default=artifact_path('H_reference_batch_repaired'))
    parser.add_argument('--reference-review', type=Path, default=artifact_path('reviews/H_repaired_application_delta_independent_review_astra.json'))
    parser.add_argument('--cache-dir', type=Path, default=artifact_path('H_frozen_cache_artifacts/result'))
    parser.add_argument('--handoff', type=Path, default=artifact_path('H_cache_artifact_handoff.json'))
    parser.add_argument('--output', type=Path, default=artifact_path('H_scoring_inputs'))
    parser.add_argument('--cache-review')
    parser.add_argument('--cache-review-sha256')
    parser.add_argument('--cache-review-decision-path')
    parser.add_argument('--cache-review-prediction-sha-path')
    parser.add_argument('--cache-review-input-count-path')
    args = parser.parse_args()
    if args.self_test:
        result = synthetic(args)
    elif args.execute:
        result = execute(args)
    else:
        _, _, result = check_metadata(args)
        result.update(source_sha256=file_sha(Path(__file__)), scores=0, models=0)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
if __name__ == '__main__':
    main()
