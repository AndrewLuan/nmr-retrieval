# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import resource
import sys
import time
D = workspace()
REPO = repository()
EXPECTED_MANIFEST_SHA = binding('verify_H_frozen_cache_artifacts.sha_or_identity.1')
WIDTH_SHA = binding('verify_H_frozen_cache_artifacts.sha_or_identity.2')
CLASSES = ['aliphatic_CH3', 'aliphatic_CH2', 'aliphatic_CH', 'aromatic_CH', 'aldehyde_CH', 'NH', 'OH', 'SH', 'other']

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def need(ok, message):
    if not ok:
        raise ValueError(message)

def rows(path):
    with Path(path).open('rb') as f:
        for lineno, literal in enumerate(f, 1):
            if literal.strip():
                yield (lineno, literal, json.loads(literal))

def snapshot(mol):
    return dict(atoms=[dict(index=a.GetIdx(), z=a.GetAtomicNum(), isotope=a.GetIsotope(), charge=a.GetFormalCharge(), radicals=a.GetNumRadicalElectrons(), aromatic=a.GetIsAromatic(), chiral_tag=str(a.GetChiralTag())) for a in mol.GetAtoms()], bonds=[dict(a=b.GetBeginAtomIdx(), b=b.GetEndAtomIdx(), kind=str(b.GetBondType()), aromatic=b.GetIsAromatic(), stereo=str(b.GetStereo()), stereo_atoms=list(b.GetStereoAtoms())) for b in mol.GetBonds()])

def h_class(atom, Chem):
    z = atom.GetAtomicNum()
    if z in (7, 8, 16):
        return {7: 5, 8: 6, 16: 7}[z]
    tag = 8
    if z == 6:
        nh = sum((n.GetAtomicNum() == 1 for n in atom.GetNeighbors()))
        if nh in (1, 2, 3):
            tag = {3: 0, 2: 1, 1: 2}[nh]
        if atom.GetIsAromatic():
            tag = 3
        carbonyl = any((b.GetBondType() == Chem.BondType.DOUBLE and b.GetOtherAtom(atom).GetAtomicNum() == 8 for b in atom.GetBonds()))
        if carbonyl and nh > 0:
            tag = 4
    return tag

def verify():
    started = time.monotonic()
    started_utc = datetime.now(timezone.utc).isoformat()
    result_dir = artifact_path('H_frozen_cache_artifacts/result')
    bundle = artifact_path('frozen_H_cache_deploy_bundle')
    collection_path = artifact_path('H_frozen_cache_collection.json')
    collection = json.loads(collection_path.read_text())
    files = {}
    for name, item in collection['files'].items():
        p = artifact_path('H_frozen_cache_artifacts') / name
        actual = sha(p)
        need(actual == item['sha256'] and p.stat().st_size == item['bytes'], 'collected bytes mismatch:' + name)
        files[str(p)] = dict(sha256=actual, bytes=p.stat().st_size)
    manifest = json.loads((result_dir / 'manifest.json').read_text())
    need(sha(result_dir / 'manifest.json') == EXPECTED_MANIFEST_SHA, 'manifest freeze mismatch')
    need(manifest['status'] == 'complete', 'cache not complete')
    for name, expected in manifest['outputs'].items():
        need(sha(result_dir / name) == expected, 'manifest output hash mismatch')
    receipt = json.loads((result_dir / 'receipt.json').read_text())
    need(receipt['pre_hashes'] == receipt['post_hashes'], 'source/checkpoint pre/post drift')
    need(all((len(h) == 64 for h in receipt['pre_hashes'].values())), 'invalid tracked hash')
    need(receipt['status'] == 'complete', 'producer receipt not complete')
    need(receipt['input_count'] == receipt['input_success'] == binding('verify_H_frozen_cache_artifacts.cohort_count.3') and receipt['input_failed'] == receipt['input_not_started'] == 0, 'input counts')
    need(receipt['forward_started'] == receipt['forward_completed'] == receipt['forward_validated'] == binding('verify_H_frozen_cache_artifacts.cohort_count.4'), 'forward start/complete/validated mismatch')
    need(receipt['model_loads'] == {'1H': 1} and receipt['updates'] == 0 and (receipt['GPU_devices'] == 0) and (receipt['dedup_hits'] == binding('verify_H_frozen_cache_artifacts.cohort_count.additional_71')), 'model/load/update accounting')
    need(manifest['forwards'] == dict(started=binding('verify_H_frozen_cache_artifacts.cohort_count.5'), completed=binding('verify_H_frozen_cache_artifacts.cohort_count.6'), validated=binding('verify_H_frozen_cache_artifacts.cohort_count.7')), 'manifest forward counts')
    closure = receipt['pre_hashes']
    categories = {name: [p for p in closure if suffix in p] for name, suffix in (('source_py', '.py'), ('checkpoint', '.pt'), ('registry', 'registry'), ('width', 'H211_width_fit.json'), ('numeric_config', 'numerical_implementation_config.json'))}
    need(all((categories[k] for k in categories)), 'incomplete expected tracked source/checkpoint/registry/width/config closure')
    assets_path = bundle / 'assets.json'
    public_path = bundle / 'H_anonymous_records.jsonl'
    width_path = bundle / 'frozen_assets/H211_width_fit.json'
    nomination_path = bundle / 'frozen_assets/predictor_nomination_astra.json'
    config_path = bundle / 'frozen_assets/numerical_implementation_config.json'
    for path, expected in ((public_path, manifest['cohort_sha256']), (assets_path, manifest['assets_sha256']), (width_path, WIDTH_SHA)):
        need(sha(path) == expected, 'local metadata freeze mismatch:' + path.name)
        files[str(path)] = dict(sha256=sha(path), bytes=path.stat().st_size)
    assets = json.loads(assets_path.read_text())
    for name in ('H_width', 'numeric_config', 'nomination'):
        local = bundle / 'frozen_assets' / Path(assets['files'][name]['path']).name
        need(sha(local) == assets['files'][name]['sha256'], 'frozen metadata asset mismatch:' + name)
        need(closure[assets['files'][name]['path']] == sha(local), 'producer asset closure mismatch:' + name)
        files[str(local)] = dict(sha256=sha(local), bytes=local.stat().st_size)
    nomination = json.loads(nomination_path.read_text())
    width = json.loads(width_path.read_text())
    config = json.loads(config_path.read_text())
    need(width['classes'] == CLASSES and len(width['selected_ppm']) == 9, 'H class order')
    need([config['source_frozen_information']['H_widths_ppm'][c] for c in CLASSES] == width['selected_ppm'], 'config exact original float H widths')
    registry = nomination['H']['registry']
    need(closure[registry['path']] == registry['sha256'], 'registry frozen closure')
    need(closure[nomination['H']['checkpoint']] == nomination['H']['sha256'], 'H checkpoint frozen closure')
    need(closure[nomination['H']['training_config']] == nomination['H']['training_config_sha256'], 'training config frozen closure')
    sys.path.insert(0, str(REPO))
    from rdkit import Chem, rdBase
    from nmr_assignment.native_adapter import adapt_native_predictions
    need(rdBase.rdkitVersion == receipt['rdkit_version'] == '2026.03.6', 'same RDKit required')
    for name in ('native_adapter.py', 'mapping.py'):
        local = REPO / 'nmr_assignment' / name
        targets = [v for p, v in closure.items() if p.endswith('/nmr_assignment/' + name)]
        need(len(targets) == 1 and sha(local) == targets[0], 'pure adapter source freeze mismatch:' + name)
        files[str(local)] = dict(sha256=sha(local), bytes=local.stat().st_size)
    need('torch' not in sys.modules, 'model framework imported')
    public = {}
    for _, _, row in rows(public_path):
        iid = row['input_id']
        need(iid not in public, 'duplicate public input')
        need(set(row) == {'input_id', 'smiles', 'nucleus', 'actual_conditions', 'observations'}, 'public whitelist')
        need(row['nucleus'] == '1H' and row['actual_conditions'] == {}, 'this verifier is frozen H empty-condition cohort scoped')
        need(all((set(b) == {'bin_id', 'ppm_decimal'} and isinstance(b['ppm_decimal'], str) for b in row['observations'])), 'anonymous bin schema')
        public[iid] = row
    need(len(public) == binding('verify_H_frozen_cache_artifacts.cohort_count.8'), 'public population')
    raw_cache = {}
    interfaces = {}
    width_counts = Counter()
    known_counts = Counter()
    for lineno, literal, raw in rows(result_dir / 'predictions.jsonl'):
        ck = raw['cache_key']
        need(ck not in raw_cache and raw['nucleus'] == '1H', 'duplicate cache key or C branch')
        need(raw['center_scale'] == 10 and raw['native_sigma_ppm'] is None and (raw['native_sigma_source'] == 'no_trained_native_sigma_head'), 'H native unit/sigma contract')
        n = len(raw['native_values'])
        need(n > 0 and all((len(raw[k]) == n for k in ('centers_ppm', 'component_mass', 'owners', 'groups', 'assignment_width_ppm', 'assignment_width_class'))), 'component lengths')
        need(all((type(v) in (int, float) and math.isfinite(v) for v in raw['native_values'])), 'native values finite')
        need(raw['centers_ppm'] == [float(v) * 10 for v in raw['native_values']], 'H unit scale exactly once')
        need(raw['groups'] == [0] * n, 'single graph groups')
        mol0 = Chem.MolFromSmiles(raw['canonical_smiles'])
        need(mol0 is not None and Chem.MolToSmiles(Chem.RemoveHs(mol0), isomericSmiles=True) == raw['canonical_smiles'], 'native canonical graph convention')
        mol = Chem.AddHs(Chem.MolFromSmiles(raw['canonical_smiles']))
        snap = snapshot(mol)
        need(raw['rdkit_version'] == rdBase.rdkitVersion and raw['native_graph_snapshot'] == snap and (raw['native_graph_snapshot_sha256'] == digest(snap)), 'native full graph snapshot mismatch')
        parents = {}
        for atom in mol.GetAtoms():
            count = sum((a.GetAtomicNum() == 1 for a in atom.GetNeighbors())) if atom.GetAtomicNum() != 1 else 0
            if atom.GetAtomicNum() == 1 and (not any((a.GetAtomicNum() != 1 for a in atom.GetNeighbors()))):
                count = 1
            if count:
                parents[str(atom.GetIdx())] = count
        need(set(raw['owners']) == {int(k) for k in parents}, 'all eligible parent owner coverage')
        for parent, total in parents.items():
            mass = sum((m for m, o in zip(raw['component_mass'], raw['owners']) if o == int(parent)))
            need(math.isclose(mass, total, rel_tol=0, abs_tol=1e-05), 'parent mass total mismatch')
        tags = [h_class(mol.GetAtomWithIdx(owner), Chem) for owner in raw['owners']]
        need(raw['assignment_width_class'] == tags and raw['assignment_width_ppm'] == [width['selected_ppm'][tag] for tag in tags], 'H9 original float class width mismatch')
        width_counts.update((CLASSES[tag] for tag in tags))
        source = 'historical_H211_train_parent_class_width:' + WIDTH_SHA
        need(raw['assignment_width_source'] == source, 'width provenance')
        layout = raw['layout']
        known = bool(layout.get('equivalence_known', [False])[0])
        known_counts[str(known)] += 1
        evidence = dict(nucleus='1H', parent_mass=parents, isotope_count_verified=True, evidence_ids=['native_graph:' + ck + ':' + rdBase.rdkitVersion], partition_hypothesis_id='H_registry:' + registry['sha256'] if known else 'unresolved_parent_pool')
        if known:
            evidence['partition_evidence_ids'] = ['H_registry:' + registry['sha256']]
        pred = adapt_native_predictions(evidence, centers_ppm=raw['centers_ppm'], masses=raw['component_mass'], owners=raw['owners'], graph_indices=raw['groups'], sigma_ppm=raw['assignment_width_ppm'], sigma_sources=[source] * n, known_h_layout=known, layout_evidence_ids=['native_layout:' + ck] if known else [], attachment_evidence_ids=['native_preserved_orbits:' + ck] if known else [], equivalence_ids=layout.get('equivalence_ids'), preserved_group_orbits=layout['preserved_group_orbits'][0] if known else None, preserved_group_ordinal=layout['preserved_group_ordinal'][0] if known else None, preserved_group_sizes=layout['preserved_group_sizes'][0] if known else None)
        adapted = json.loads(json.dumps(asdict(pred)))
        need(adapted == raw['predictions'], 'full pure adapted dataclass differs')
        for unit in pred.layout.units:
            weights = [c.mixture_weight for c in pred.carriers if c.unit_id == unit.unit_id]
            need(math.isclose(sum(weights), 1.0, rel_tol=1e-09, abs_tol=1e-09), 'carrier qnorm mismatch')
        cond, vector = ([[0.0, 0.0, 0.0, 0.0]], [[1.0] + [0.0] * 26])
        need(raw['native_cond'] == cond and raw['recovered_condition_vector'] == vector, 'effective unknown condition features')
        need(ck == digest(dict(nucleus='1H', canonical_smiles=raw['canonical_smiles'], native_cond=cond, recovered_condition_vector=vector)), 'effective native dedup key')
        interfaces[ck] = dict(cache_key=ck, prediction_payload_sha256=digest(adapted), native_graph_snapshot_sha256=raw['native_graph_snapshot_sha256'], rdkit_version=rdBase.rdkitVersion, raw_prediction_line_sha256=hashlib.sha256(literal).hexdigest(), source_line=lineno, structural_parent_mass=parents, layout_sha256=digest(adapted['layout']), attachment_sha256=digest(dict(blocks=adapted['attachment_blocks'], evidence_ids=adapted['attachment_evidence_ids'])))
        raw_cache[ck] = raw
    need(len(raw_cache) == binding('verify_H_frozen_cache_artifacts.cohort_count.9'), 'unique cache population')
    inputs, join_rows = ({}, [])
    referenced = Counter()
    for _, _, row in rows(result_dir / 'inputs.jsonl'):
        iid = row['input_id']
        need(iid in public and iid not in inputs and (row['status'] == 'ok') and (row['nucleus'] == '1H'), 'input exact identity join')
        need(row['actual_conditions_sha256'] == digest(public[iid]['actual_conditions']) and row['cache_key_semantics'] == 'native_encoded_features_only', 'actual condition identity binding')
        ck = row['cache_key']
        need(ck in raw_cache, 'input references absent cache key')
        canonical = Chem.MolToSmiles(Chem.RemoveHs(Chem.MolFromSmiles(public[iid]['smiles'])), isomericSmiles=True)
        need(canonical == raw_cache[ck]['canonical_smiles'], 'input/cache exact canonical graph')
        referenced[ck] += 1
        inputs[iid] = row
        join_rows.append(dict(input_id=iid, cache_key=ck, actual_conditions_sha256=row['actual_conditions_sha256'], **{k: v for k, v in interfaces[ck].items() if k != 'cache_key'}))
    need(set(inputs) == set(public) and set(referenced) == set(raw_cache), 'full exact public/cache accounting')
    need(sum((row['deduplicated'] is True for row in inputs.values())) == binding('verify_H_frozen_cache_artifacts.cohort_count.additional_71'), 'dedup join count')
    need(sum(referenced.values()) - len(referenced) == binding('verify_H_frozen_cache_artifacts.cohort_count.additional_71'), 'effective key uniqueness')
    stages = list(rows(result_dir / 'stages.jsonl'))
    stage_counts = Counter((row['stage'] for _, _, row in stages))
    for name in ('forward_started', 'forward_completed', 'forward_validated'):
        need(stage_counts[name] == binding('verify_H_frozen_cache_artifacts.cohort_count.10'), 'stage event count:' + name)
    supervisor = json.loads(artifact_path('H_frozen_cache_artifacts/SUPERVISOR_ACTUAL_RECEIPT.json').read_text())
    need(collection['collection_actual_exit'] == 0, 'collection actual exit')
    need(supervisor['leader_exit_code'] == 0 and supervisor['leader_reaped'] is True and (supervisor['retries'] == 0) and (supervisor['prepost_hash_complete'] is True) and (supervisor['pre_file_sha256'] == supervisor['post_file_sha256']), 'supervisor actual exit/hash closure')
    return dict(schema='H_cache_artifact_author_handoff_v1', status='FULLROW_FROZEN_PREDICTION_INTERFACE_VERIFIED_INDEPENDENT_AUDIT_PENDING', started_utc=started_utc, completed_utc=datetime.now(timezone.utc).isoformat(), actual_exit=0, seconds=time.monotonic() - started, verifier_peakRSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024), producer_seconds=receipt['seconds'], producer_peakRSS_bytes=receipt['peakRSS_bytes'], producer_operational_exit=supervisor['leader_exit_code'], supervisor_wall_with_cleanup_seconds=supervisor['actual_wall_with_cleanup_seconds'], producer_started_utc=supervisor['started_utc'], producer_finished_utc=supervisor['finished_utc'], counts=dict(public_inputs=binding('verify_H_frozen_cache_artifacts.cohort_count.11'), joined_inputs=binding('verify_H_frozen_cache_artifacts.cohort_count.12'), unique_predictions=binding('verify_H_frozen_cache_artifacts.cohort_count.13'), dedup_hits=binding('verify_H_frozen_cache_artifacts.cohort_count.additional_71'), forward_started=binding('verify_H_frozen_cache_artifacts.cohort_count.14'), forward_completed=binding('verify_H_frozen_cache_artifacts.cohort_count.15'), forward_validated=binding('verify_H_frozen_cache_artifacts.cohort_count.16'), H_model_loads=1, C_model_loads=0, updates=0), complete_files=files, source_prepost_equal=True, producer_prepost_hashes=closure, tracked_categories=categories, width_class_component_counts=dict(width_counts), known_layout_rows=dict(known_counts), interface_contract=dict(raw_centers='native_values *10 exactly once', mass='component_mass retained; not observed integration', assignment_sigma='original H9 class float widths, separate from absent native sigma', canonical_graph='same RDKit RemoveHs canonical isomeric -> AddHs; full atoms/bonds checked', adapted_predictions='complete asdict(FrozenCapacityPredictions) independently reconstructed per row', actual_conditions='all 1408 frozen public {} -> native zero cond/recovered unknown vector', keys='nucleus+canonical+effective_native_cond+condition_vector; no observation values'), input_interfaces=join_rows, cache_interfaces=interfaces, missing_adapter_lineage_evidence=['No final per-input prediction lineage receipt is minted here.', 'prediction_payload_sha256 values supplied as handoff metadata for root-reviewed lineage producer.', 'Native graph snapshot digest covers atoms/bonds only; final adapter wrapper must preserve exact snapshot recipe and canonical SMILES without relabeling this raw digest.', 'No source experimental assignment, gold admission, solver candidate/result certificate or model accuracy is verified.'], truth_scope='frozen_prediction_interface_only', scientific_certificate_minted=False, independent_review_completed=False, real_scores_computed=0, residuals_computed=0, model_loads_by_verifier=0, verifier_sha256=sha(Path(__file__)), collection_sha256=sha(collection_path))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-author-verification', action='store_true')
    args = parser.parse_args()
    if not args.execute_author_verification:
        print(json.dumps(dict(status='VERIFIER_READY_NO_FULLROW_RUN', files_root=str(artifact_path('H_frozen_cache_artifacts/result')), model_loads=0, score_execution=0)))
        return
    output = artifact_path('H_cache_artifact_handoff.json')
    need(not output.exists(), 'handoff exists; no automatic overwrite/retry')
    try:
        result = verify()
    except Exception as exc:
        result = dict(schema='H_cache_artifact_author_handoff_v1', status='AUTHOR_VERIFICATION_FAILED', actual_exit=1, completed_utc=datetime.now(timezone.utc).isoformat(), error=type(exc).__name__ + ':' + str(exc), verifier_sha256=sha(Path(__file__)), real_scores_computed=0, model_loads_by_verifier=0)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result))
        raise
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'actual_exit', 'seconds', 'counts', 'verifier_peakRSS_bytes', 'verifier_sha256')}))
if __name__ == '__main__':
    main()
