# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys
import platform
import time
D = workspace()
REPO = repository()
SALT = 'source-relative-admission-audit-173-v1'
PARENT_POLICY_SHA = binding('build_H_source_reference_batch.sha_or_identity.1')
CORRECTED_IDS = (binding('build_H_source_reference_batch.sha_or_identity.2'), binding('build_H_source_reference_batch.sha_or_identity.3'))

def digest(data):
    return hashlib.sha256(data).hexdigest()

def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + '\n')

def file_sha(path):
    return digest(path.read_bytes())

def check_inputs():
    path = artifact_path('H_reference_batch_identity_manifest.json')
    batch = json.loads(path.read_text())
    release = json.loads(artifact_path('scientific_reference_release.json').read_text())
    assert file_sha(artifact_path('scientific_reference_release.json')) == batch['scientific_release_sha256']
    assert release['admission_execution_allowed'] is True
    assert release['reference_choice'] == batch['reference_choice'] == 'raw'
    assert release['source_sha256'] == batch['source_sha256']
    assert batch['selected_count'] == binding('build_H_source_reference_batch.cohort_count.4')
    assert release['original_H_policy_sha256'] == PARENT_POLICY_SHA
    binding_path = artifact_path('H_reference_policy_subset_binding.json')
    binding = json.loads(binding_path.read_text())
    assert binding['extraction_manifest_sha256'] == file_sha(path)
    assert binding['original_full_artifact_sha256'] == PARENT_POLICY_SHA
    texts = {}
    for kind in ('raw', 'policy'):
        item = batch['hidden_artifacts'][kind]
        artifact_path = Path(item['path'])
        if not artifact_path.exists():
            artifact_path = artifact_path('hidden') / artifact_path.name
        data = artifact_path.read_bytes()
        assert digest(data) == item['sha256']
        assert len(data.splitlines()) == item['rows'] == binding('build_H_source_reference_batch.cohort_count.5')
        texts[kind] = data.decode('utf-8')
    assert digest(texts['policy'].encode()) == binding['subset_sha256']
    raw = texts['raw'].splitlines(keepends=True)
    policy = texts['policy'].splitlines(keepends=True)
    selected = {(r['source'], r['nucleus'], r['record_id']): r for r in batch['selected']}
    assert len(selected) == binding('build_H_source_reference_batch.cohort_count.6')
    proofs = {(r['source'], r['record_id']): r for r in binding['row_bindings']}
    assert len(proofs) == binding('build_H_source_reference_batch.cohort_count.7')
    for line in raw:
        row = json.loads(line)
        key = (row['source_ref'], row['nucleus'], row['record_id'])
        assert key in selected and row['nucleus'] == '1H'
        proof = proofs[key[0], key[2]]
        assert digest(line.encode()) == proof['source_raw_line_sha256']
    for line in policy:
        row = json.loads(line)
        proof = proofs[row['source'], row['record_id']]
        assert digest(line.encode()) == proof['original_policy_line_sha256']
    return (batch, binding, texts, selected)

def require_transport_review(args):
    if not (args.transport_review and args.review_sha256 and args.transport_implementation_sha256):
        raise ValueError('execute requires explicit frozen PASS review and implementation SHA')
    review_path = Path(args.transport_review)
    assert file_sha(review_path) == args.review_sha256
    review = json.loads(review_path.read_text())
    assert review.get('schema') == 'source_transport_independent_review_astra_v1'
    assert review.get('decision') == 'PASS_SOURCE_TRANSPORT_COMPONENT_BATCH_ADMISSION_AUDIT_PENDING'
    assert review.get('scope', {}).get('full_batch_admission_reviewed') is False
    assert review.get('snapshot_before', {}).get('nmr_assignment/source_transport.py') == args.transport_implementation_sha256
    assert review.get('snapshot_after', {}).get('nmr_assignment/source_transport.py') == args.transport_implementation_sha256
    assert file_sha(REPO / 'nmr_assignment/source_transport.py') == args.transport_implementation_sha256
    return review

def execute(args, checked):
    review = require_transport_review(args)
    batch, subset_binding, texts, selected = checked
    sys.path.insert(0, str(REPO))
    from rdkit import Chem, rdBase
    from nmr_assignment.source_reference import normalize_policy_rows, text_sha256, build_source_reference, compile_reference_context
    from nmr_assignment.source_transport import build_source_transport
    assert rdBase.rdkitVersion == args.expected_rdkit_version
    assert str(Path(sys.executable).resolve()) == str(Path(args.expected_python).resolve())
    assert args.execution_location == binding('build_H_source_reference_batch.ssh_host.8') and args.expected_python.startswith(binding('build_H_source_reference_batch.path.9'))
    runtime = dict(execution_location=binding('build_H_source_reference_batch.ssh_host.10'), hostname=platform.node(), python=sys.executable, rdkit_version=rdBase.rdkitVersion, repo=str(REPO), data_directory=str(D))

    def canonical(smiles):
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError('invalid canonical structure')
        return Chem.MolToSmiles(Chem.RemoveHs(mol), isomericSmiles=True)
    output = artifact_path('H_reference_batch')
    output.mkdir(exist_ok=False)
    hidden = output / 'hidden'
    public = output / 'public'
    hidden.mkdir()
    public.mkdir()
    start = time.monotonic()
    raw_lines = texts['raw'].splitlines(keepends=True)
    reference_sha = file_sha(REPO / 'nmr_assignment/source_reference.py')
    norm = normalize_policy_rows(raw_lines, original_policy_jsonl=texts['policy'], original_policy_sha256=text_sha256(texts['policy']), nucleus_scope='1H', canonicalize_structure=canonical, adapter_implementation_sha256=reference_sha, reference_choice='raw', correction_record_ids=CORRECTED_IDS, correction_overlay_sha256=binding('build_H_source_reference_batch.sha_or_identity.11'))
    subset_binding_sha = file_sha(artifact_path('H_reference_policy_subset_binding.json'))
    normalized_rows = [json.loads(x) for x in norm['policy_jsonl'].splitlines()]
    for row in normalized_rows:
        row['_full_parent_sha'] = PARENT_POLICY_SHA
        row['_verified_subset_binding_sha'] = subset_binding_sha
    policy_text = ''.join((json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in normalized_rows))
    policy_sha = text_sha256(policy_text)
    policy_path = hidden / 'normalized_policy.jsonl'
    policy_path.write_text(policy_text)
    records = []
    for raw in raw_lines:
        row = json.loads(raw)
        records.append(dict(source=row['source_ref'], nucleus=row['nucleus'], record_id=row['record_id'], structure_id=row.get('structure_id') or text_sha256(row['smiles']), row_sha256=text_sha256(raw)))
    cohort = dict(source_sha256=batch['source_sha256'], policy_sha256=policy_sha, normalized_policy_provenance=norm['manifest_bindings'], original_policy_artifact_scope='verified_full_join_subset', parent_full_policy_sha256=PARENT_POLICY_SHA, input_subset_sha256=text_sha256(texts['policy']), verified_subset_binding_sha256=subset_binding_sha, extraction_manifest_sha256=file_sha(artifact_path('H_reference_batch_identity_manifest.json')), records=records)
    cohort_text = json.dumps(cohort, ensure_ascii=False, sort_keys=True)
    cohort_sha = text_sha256(cohort_text)
    (hidden / 'cohort_identity_manifest.json').write_text(cohort_text)
    context = compile_reference_context(policy_text, policy_sha, cohort_text, cohort_sha)
    ledger, audits, counters = ([], {}, collections.Counter())
    hidden_path, public_path = (hidden / 'gold_and_source_evidence.jsonl', public / 'anonymous_records.jsonl')
    with hidden_path.open('x') as gold_file, public_path.open('x') as public_file:
        for raw, identity in zip(raw_lines, records):
            row = json.loads(raw)
            key = (identity['source'], identity['nucleus'], identity['record_id'])
            metadata = selected[key]
            binding = dict(identity, source_sha256=batch['source_sha256'], policy_sha256=policy_sha, cohort_identity_manifest_sha256=cohort_sha)
            structure = {k: row[k] for k in ('smiles', 'atoms', 'atom_order', 'source_ref', 'nucleus', 'record_id')}
            if 'structure_id' in row:
                structure['structure_id'] = row['structure_id']
            canonical_smiles = canonical(row['smiles'])
            transport = build_source_transport(structure, binding=binding, baseline_smiles=canonical_smiles, max_maps=4096, time_limit_seconds=2, expected_rdkit_version=args.expected_rdkit_version)
            reference = build_source_reference(raw, source_sha256=batch['source_sha256'], policy_jsonl=policy_text, policy_sha256=policy_sha, cohort_manifest_json=cohort_text, cohort_identity_manifest_sha256=cohort_sha, transport=transport, context=context)
            input_id = text_sha256('source-relative-anonymous-v1\n' + identity['row_sha256'])
            label_class = reference.classification
            scoreable = label_class in ('unique_parent', 'parent_mapping_ambiguous') and bool(reference.inference_bins)
            ledger_class = 'ambiguous' if label_class == 'parent_mapping_ambiguous' else 'admitted' if scoreable else 'restricted' if label_class == 'restricted' else 'no_known_labels' if 'no_known_labels' in reference.reasons else 'unknown'
            condition_keys = ('solvent', 'frequency', 'pH', 'ph', 'temperature', 'NMR_solvent')
            conditions = row.get('conditions', {})
            actual_conditions = {k: conditions[k] for k in condition_keys if isinstance(conditions, dict) and k in conditions}
            for k in condition_keys:
                if k not in actual_conditions and k in row:
                    actual_conditions[k] = row[k]
            baseline_mol = Chem.AddHs(Chem.MolFromSmiles(canonical_smiles))
            structure_snapshot = dict(canonical_smiles=canonical_smiles, rdkit_version=rdBase.rdkitVersion, atoms=[dict(index=a.GetIdx(), z=a.GetAtomicNum(), isotope=a.GetIsotope(), charge=a.GetFormalCharge(), radicals=a.GetNumRadicalElectrons(), aromatic=a.GetIsAromatic(), chiral_tag=str(a.GetChiralTag())) for a in baseline_mol.GetAtoms()], bonds=[dict(a=b.GetBeginAtomIdx(), b=b.GetEndAtomIdx(), kind=str(b.GetBondType()), aromatic=b.GetIsAromatic(), stereo=str(b.GetStereo()), stereo_atoms=list(b.GetStereoAtoms())) for b in baseline_mol.GetBonds()])
            pub = dict(input_id=input_id, smiles=canonical_smiles, nucleus=row['nucleus'], actual_conditions=actual_conditions, observations=list(reference.anonymous_payload()))
            public_file.write(json.dumps(pub, ensure_ascii=False) + '\n')
            gold = dict(input_id=input_id, binding=binding, source_raw_line=raw, baseline_structure_snapshot=structure_snapshot, baseline_structure_snapshot_sha256=text_sha256(json.dumps(structure_snapshot, sort_keys=True)), structure_whitelist_sha256=text_sha256(json.dumps(structure, sort_keys=True)), runtime=runtime, original_policy_parent_sha256=PARENT_POLICY_SHA, verified_subset_binding_sha256=subset_binding_sha, transport=transport, ledger_class=ledger_class, scoreable=scoreable, reasons=reference.reasons, joint_gold_parent_sets=reference.hidden.get('joint_gold_variants', ()) if scoreable else (), known_label_atoms=reference.hidden['derived'].reported_slot_count if 'derived' in reference.hidden else 0, truth_basis=reference.truth_basis, reference_basis=reference.reference_basis, trust_basis=reference.trust_basis, trusted_experimental=False, original_precision='unknown', representative_expansion=False)
            gold_file.write(json.dumps(gold, ensure_ascii=False) + '\n')
            slots = [z for z in row['atom_order']['atomic_numbers'] if z == 1]
            known = gold['known_label_atoms']
            scope = 'partial_known_nucleus_mask_semantics_unknown' if known < len(slots) else 'all_nucleus_slots_mask_semantics_unknown'
            entry = dict(input_id=input_id, **identity, connectivity_sha256=metadata['connectivity_sha256'], roles=metadata['reference_roles'], ledger_class=ledger_class, scoreable=scoreable, reasons=reference.reasons, bins=len(reference.inference_bins), known_label_atoms=known, representative_label_scope=scope, transport_complete=transport.get('complete') is True)
            ledger.append(entry)
            counters[ledger_class] += 1
            for split in metadata['reference_roles']:
                stratum = '|'.join((identity['nucleus'], identity['source'], split, ledger_class, scope))
                immutable_key = '|'.join(key) + '|' + identity['structure_id'] + '|' + identity['row_sha256']
                audit_hash = text_sha256(SALT + '\n' + immutable_key)
                candidate = dict(stratum=stratum, audit_hash=audit_hash, input_id=input_id)
                if stratum not in audits or audit_hash < audits[stratum]['audit_hash']:
                    audits[stratum] = candidate
    dump(hidden / 'ledger.json', ledger)
    dump(hidden / 'application_audit_selection.json', dict(salt=SALT, per_stratum=1, defines_cohort=False, entries=sorted(audits.values(), key=lambda x: x['stratum'])))
    files = {str(p.relative_to(output)): dict(sha256=file_sha(p), bytes=p.stat().st_size) for p in output.rglob('*') if p.is_file()}
    summary = dict(schema='H_source_relative_reference_batch_v1', status='REFERENCE_GATE_EXECUTED_NO_MODEL_SCORES', records=len(ledger), structures=len({r['connectivity_sha256'] for r in ledger}), bins=sum((r['bins'] for r in ledger)), known_label_atoms=sum((r['known_label_atoms'] for r in ledger)), scoreable_records=sum((r['scoreable'] for r in ledger)), scoreable_structures=len({r['connectivity_sha256'] for r in ledger if r['scoreable']}), transport_complete_records=sum((r['transport_complete'] for r in ledger)), scoreable_bins=sum((r['bins'] for r in ledger if r['scoreable'])), scoreable_known_label_atoms=sum((r['known_label_atoms'] for r in ledger if r['scoreable'])), classes=dict(counters), truth_basis='source_relative_current_serialization', reference_basis='source_asserted_encoded_graph', trust_basis='internal_source_consistency', trusted_experimental=False, whole_molecule_completeness_claim=False, model_scores=False, source_reference_implementation_sha256=reference_sha, source_transport_implementation_sha256=args.transport_implementation_sha256, independent_transport_review_sha256=args.review_sha256, input_manifest_sha256=file_sha(artifact_path('H_reference_batch_identity_manifest.json')), runtime=runtime, transport_component_review_verdict=review['decision'], full_batch_application_audit_passed=False, driver_sha256=file_sha(Path(__file__)), elapsed_seconds=time.monotonic() - start, files=files, public_directory='public', hidden_directory='hidden')
    dump(output / 'manifest.json', summary)
    print(json.dumps(summary, ensure_ascii=False))

def main():
    global D, REPO
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--data-dir', default=str(D))
    parser.add_argument('--repo', default=str(REPO))
    parser.add_argument('--expected-python', default=binding('build_H_source_reference_batch.path.12'))
    parser.add_argument('--expected-rdkit-version', default='2026.03.6')
    parser.add_argument('--execution-location', default=binding('build_H_source_reference_batch.ssh_host.13'))
    parser.add_argument('--transport-review')
    parser.add_argument('--review-sha256')
    parser.add_argument('--transport-implementation-sha256')
    args = parser.parse_args()
    D = workspace()
    REPO = repository()
    checked = check_inputs()
    if not args.execute:
        print(json.dumps(dict(status='INPUTS_READY_TRANSPORT_REVIEW_EXECUTION_PENDING', selected=checked[0]['selected_count'], gold_constructed=False)))
        return
    execute(args, checked)
if __name__ == '__main__':
    main()
