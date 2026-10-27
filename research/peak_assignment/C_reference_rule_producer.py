# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：实现C1–C8的13C当前序列化源相对直接质量receipt producer；不执行真实batch。\nproduce_C_reference以原行/空C政策/冻结cohort/structure-only transport及JJ图快照为输入，\n先复用source_reference无quality路径核验数组、mask、Decimal、谱对应与联合分箱，再独立\n检查C1/C4/C6/C7证据。只有全部直接gate通过才生成source_relative_keep并二次调用既有入口。\n历史C质量保持unknown和policy_missing；空政策真实SHA不伪造H keep。known C conflicts须\n独立SHA绑定，缺失如实unavailable；不把共享record_id的H冲突当C证据。\npublic_payload只含opaque input_id、nucleus、smiles、扁平实际条件与匿名bins，匹配共享cache。\nevidence_bundle及quality_receipt含完整gate/原行/图/proof/config绑定，仅留evaluator-side。\n关系：只依赖已审nmr_assignment.source_reference和source_transport的外部receipt契约；\n不修改core、不读模型/预测、无训练/评分/新源扫描。validate_only入口仅打印实现SHA。\n输入输出：严格绑定SHA和完整图族；失效/冲突/空/不完整均保留ledger，不替换或修复原值。\nshape/hash验证不是独立实验正确性认证。源码与合成fixture先交独审，真实3745执行另由root批准。\n'
import argparse, hashlib, json, re, math
from decimal import Decimal
from pathlib import Path
from collections import Counter
from nmr_assignment import source_reference as core
RULE_ID = 'C-current-serialization-direct-quality-v1'
RULE_REVIEW_SHA = binding('C_reference_rule_producer.sha_or_identity.1')
EMPTY_POLICY_SHA = hashlib.sha256(b'').hexdigest()
CONDITION_KEYS = ('solvent', 'frequency', 'pH', 'ph', 'temperature')

def digest(value):
    normalized = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def _lineage_digest(lineage):
    restored = dict(lineage)
    for name in ('source_suppressed_H_by_parent', 'target_suppressed_H_by_parent'):
        if name in restored:
            converted = {}
            for key, value in restored[name].items():
                if type(key) is int and key >= 0:
                    index = key
                elif isinstance(key, str) and key.isdecimal() and (str(int(key)) == key):
                    index = int(key)
                else:
                    raise ValueError('noncanonical_transport_lineage_key')
                if index in converted:
                    raise ValueError('duplicate_transport_lineage_key')
                converted[index] = value
            restored[name] = converted
    return hashlib.sha256(json.dumps(restored, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None

def _gate(gates, name, ok, reason):
    gates[name] = dict(passed=bool(ok), reasons=[] if ok else [reason])

def _whole_family_matches_proof(transport, proof, native, source_slots):
    atoms = native.get('graph_snapshot', {}).get('atoms', [])
    parent_domain = {str(atom['index']) for atom in atoms if atom['z'] != 1}
    observed = []
    for mapping in transport.get('joint_maps', ()):
        if not isinstance(mapping, dict) or any((type(i) is not int for i in mapping)) or set(mapping) != set(range(source_slots)) or any((not isinstance(v, str) or v not in parent_domain for v in mapping.values())):
            return False
        observed.append(tuple((mapping[i] for i in range(source_slots))))
    expected = proof.get('parent_projection_rows')
    if not isinstance(expected, (list, tuple)) or not expected:
        return False
    if any((not isinstance(row, (list, tuple)) or len(row) != source_slots or any((not isinstance(v, str) or v not in parent_domain for v in row)) for row in expected)):
        return False
    expected = [tuple(row) for row in expected]
    return len(observed) == len(set(observed)) and len(expected) == len(set(expected)) and (sorted(observed) == sorted(expected))

def _actual_conditions(row):
    nested = row.get('experimental_conditions') or row.get('conditions') or {}
    if not isinstance(nested, dict):
        raise ValueError('actual_conditions_not_mapping')
    out = {k: nested[k] for k in CONDITION_KEYS if k in nested}
    for k in ('solvent', 'frequency'):
        if k in row:
            out[k] = row[k]
    metadata = row.get('source_metadata') or {}
    if not isinstance(metadata, dict):
        raise ValueError('actual_source_metadata_not_mapping')
    if 'NMR_solvent' in metadata:
        out['NMR_solvent'] = metadata['NMR_solvent']
    for key, value in out.items():
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError('actual_conditions_nonfinite')
            out[key] = format(value, 'f')
        elif value is not None and (isinstance(value, bool) or not isinstance(value, (str, int, float))):
            raise ValueError('actual_conditions_scalar_required')
        elif isinstance(value, float) and (not math.isfinite(value)):
            raise ValueError('actual_conditions_nonfinite')
    return out

def produce_C_reference(raw_json_line, *, source_sha256, empty_C_policy_jsonl, empty_C_policy_sha256, cohort_manifest_json, cohort_identity_manifest_sha256, transport, native_graph_receipt, rule_config_json, rule_config_sha256, input_id, known_conflicts_json=None, known_conflicts_sha256=None):
    """Return {ledger,quality_receipt,evidence_bundle,reference,public_payload}.

    Config binds rule/review/source SHA, extraction+subset+identity ledger SHA,
    expected input identity count, RDKit and exact core/transport implementation.
    native_graph_receipt normalized fields: canonical_smiles,rdkit_version,
    graph_snapshot,graph_snapshot_sha256; receipt values come from frozen JJ
    structure extraction, never a graph selected by target agreement.
    known_conflicts_json is optional C-only registry document:
    {schema:C_known_source_conflicts_v1,nucleus_scope:13C,records:[source,nucleus,
    record_id,structure_id,restriction]}. None explicitly means unavailable.
    """
    gates = {}
    quality = None
    reference = None
    public = None
    extra = []
    conflict_status = 'unavailable_no_C_specific_registry'
    evidence = dict(rule_id=RULE_ID, implementation_sha256=file_sha(__file__), historical_C_quality_policy_status='unknown', policy_missing=True)
    binding = {}
    try:
        if not isinstance(raw_json_line, str):
            raise ValueError('raw_line_text_required')
        row = core._load(raw_json_line)
        if not isinstance(row, dict):
            raise ValueError('raw_line_object_required')
        sid = row.get('structure_id') or core.text_sha256(row['smiles'])
        binding = dict(source=row.get('source_ref'), nucleus=row.get('nucleus'), record_id=row.get('record_id'), structure_id=sid, source_sha256=source_sha256, row_sha256=core.text_sha256(raw_json_line), policy_sha256=empty_C_policy_sha256, cohort_identity_manifest_sha256=cohort_identity_manifest_sha256)
        if core.text_sha256(rule_config_json) != rule_config_sha256:
            raise ValueError('rule_config_SHA')
        config = json.loads(rule_config_json)
        config_ok = config['rule_id'] == RULE_ID and config['nucleus_scope'] == '13C' and (config['scientific_rule_review_sha256'] == RULE_REVIEW_SHA) and (config['source_sha256'] == source_sha256) and (config['source_reference_implementation_sha256'] == file_sha(core.__file__)) and _sha(config['transport_implementation_sha256']) and isinstance(config['expected_rdkit_version'], str) and (type(config['expected_cohort_identity_count']) is int) and (config['expected_cohort_identity_count'] > 0) and all((_sha(config[k]) for k in ('extraction_manifest_sha256', 'raw_subset_sha256', 'identity_ledger_sha256')))
        if not config_ok:
            raise ValueError('frozen_rule_config_binding')
        manifest = core._load(cohort_manifest_json)
        records = manifest['records']
        triples = Counter(((r.get('source'), r.get('nucleus'), r.get('record_id')) for r in records))
        matched = [r for r in records if all((r.get(k) == binding[k] for k in ('source', 'nucleus', 'record_id', 'structure_id')))]
        frozen_headers = manifest.get('source_sha256') == source_sha256 and manifest.get('policy_sha256') == empty_C_policy_sha256 and (manifest.get('native_partition') == 'val') and (manifest.get('nucleus_scope') == '13C') and (manifest.get('reference_choice') == 'raw') and all((manifest.get(k) == config[k] for k in ('extraction_manifest_sha256', 'raw_subset_sha256', 'identity_ledger_sha256')))
        c1 = core.text_sha256(cohort_manifest_json) == cohort_identity_manifest_sha256 and len(records) == config['expected_cohort_identity_count'] and frozen_headers and all((r.get('nucleus') == '13C' and r.get('native_legacy_hash_partition') == 'val' and _sha(r.get('row_sha256')) for r in records)) and all((count == 1 for count in triples.values())) and (len(matched) == 1) and (triples[binding['source'], '13C', binding['record_id']] == 1) and (matched[0].get('row_sha256') == binding['row_sha256']) and (matched[0].get('native_legacy_hash_partition') == 'val')
        _gate(gates, 'C1', c1, 'frozen_C_native_val_identity_or_raw_binding_invalid')
        c6 = empty_C_policy_jsonl == '' and empty_C_policy_sha256 == EMPTY_POLICY_SHA and (core.text_sha256(empty_C_policy_jsonl) == empty_C_policy_sha256) and (config.get('historical_C_quality_policy_status') == 'unknown') and (config.get('policy_absence_action') == 'direct_C_rule_preserve_unknown')
        _gate(gates, 'C6', c6, 'historical_C_policy_not_genuinely_empty_or_scope_misrepresented')
        if not c6:
            raise ValueError('C_policy_must_remain_empty_not_H_keep')
        provisional = core.build_source_reference(raw_json_line, source_sha256=source_sha256, policy_jsonl=empty_C_policy_jsonl, policy_sha256=empty_C_policy_sha256, cohort_manifest_json=cohort_manifest_json, cohort_identity_manifest_sha256=cohort_identity_manifest_sha256, transport=transport, quality_receipt=None)
        p_reasons = tuple(provisional.reasons)
        c2_bad = ('array_length_mismatch', 'atom_order_or_padding_invalid', 'nucleus_unsupported', 'nucleus_element_mismatch')
        c3_bad = ('mask_invalid', 'target_nonfinite_or_invalid', 'inactive_target_not_null', 'reported_target_missing', 'spectrum_target_mismatch')
        invalid = any((r.startswith('invalid_reference:') for r in p_reasons))
        _gate(gates, 'C2', row.get('nucleus') == '13C' and (not invalid) and (not any((r in c2_bad for r in p_reasons))), 'declared_C_graph_element_order_or_arrays_invalid_or_unsupported')
        _gate(gates, 'C3', not invalid and (not any((r in c3_bad for r in p_reasons))), 'exact_mask_target_spectrum_decimal_consistency_failed')
        t = transport if isinstance(transport, dict) else {}
        lineage = t.get('graph_lineage_evidence') or {}
        proof = t.get('completeness_evidence') or {}
        native = native_graph_receipt if isinstance(native_graph_receipt, dict) else {}
        payload = dict(smiles=row['smiles'], atoms=list(row['atoms']), atom_order={k: row['atom_order'][k] for k in ('basis', 'source_to_canonical', 'atomic_numbers')})
        c4 = t.get('complete') is True and t.get('enumeration_truncated') is False and (t.get('structure_only') is True) and bool(t.get('joint_maps')) and all((t.get(k) == v for k, v in binding.items())) and (t.get('graph_lineage_evidence_sha256') == _lineage_digest(lineage)) and (t.get('completeness_evidence_sha256') == digest(proof)) and (proof.get('enumeration_truncated') is False) and (proof.get('graph_lineage_evidence_sha256') == _lineage_digest(lineage)) and (lineage.get('implementation_sha256') == config['transport_implementation_sha256']) and (lineage.get('source_structure_payload') == payload) and (t.get('rdkit_version') == lineage.get('rdkit_version') == native.get('rdkit_version') == config['expected_rdkit_version']) and (t.get('canonical_smiles') == lineage.get('canonical_smiles') == native.get('canonical_smiles')) and (digest(native.get('graph_snapshot')) == native.get('graph_snapshot_sha256')) and (lineage.get('baseline_graph') == native.get('graph_snapshot')) and _whole_family_matches_proof(t, proof, native, len(row['atoms']))
        _gate(gates, 'C4', c4, 'complete_label_free_transport_or_JJ_native_graph_proof_invalid')
        derived = provisional.hidden.get('derived')
        c5 = derived is not None and derived.reported_slot_count > 0 and bool(provisional.hidden.get('joint_gold_variants')) and (not any((r in p_reasons for r in ('no_known_labels', 'joint_map_domain_invalid', 'joint_mapping_missing'))))
        _gate(gates, 'C5', c5, 'no_reported_C_bins_or_joint_projection_invalid')
        conflicts = []
        conflict_ok = True
        if known_conflicts_json is not None:
            if not _sha(known_conflicts_sha256) or core.text_sha256(known_conflicts_json) != known_conflicts_sha256:
                raise ValueError('known_C_conflict_input_SHA')
            registry = json.loads(known_conflicts_json)
            conflict_ok = registry.get('schema') == 'C_known_source_conflicts_v1' and registry.get('nucleus_scope') == '13C' and isinstance(registry.get('records'), list) and all((isinstance(r, dict) and r.get('nucleus') == '13C' and all((isinstance(r.get(k), str) and bool(r[k]) for k in ('source', 'record_id', 'structure_id', 'restriction'))) for r in registry['records']))
            if conflict_ok:
                keys = [tuple((r[k] for k in ('source', 'nucleus', 'record_id', 'structure_id'))) for r in registry['records']]
                conflict_ok = len(keys) == len(set(keys))
            if conflict_ok:
                conflict_status = 'C_specific_input_supplied_not_exhaustive_audit'
                conflicts = [r for r in registry['records'] if all((r.get(k) == binding[k] for k in ('source', 'nucleus', 'record_id', 'structure_id'))) and r.get('restriction')]
            else:
                conflict_status = 'wrong_nucleus_or_malformed_conflict_input_not_C_evidence'
        _gate(gates, 'C7', conflict_ok and (not conflicts), 'known_C_source_restriction' if conflicts else 'known_conflict_registry_scope_invalid')
        actual = None
        try:
            actual = _actual_conditions(row)
            _gate(gates, 'C8', isinstance(input_id, str) and bool(input_id), 'opaque_public_input_id_missing')
        except (ValueError, TypeError, AttributeError) as exc:
            _gate(gates, 'C8', False, 'public_actual_condition_schema_invalid:' + str(exc))
        allowed_missing = {'policy_missing', 'equivalent_quality_receipt_missing'}
        unresolved = [r for r in p_reasons if r not in allowed_missing]
        if unresolved:
            extra.extend(unresolved)
        evidence.update(binding=binding, rule_config_sha256=rule_config_sha256, rule_config=config, gate_outcomes=gates, provisional_reasons=p_reasons, known_conflict_input_sha256=known_conflicts_sha256, known_conflict_input_status=conflict_status, known_C_restrictions=conflicts, original_row_sha256=binding['row_sha256'], transport=transport, native_graph_receipt=native_graph_receipt, source_relative_only=True, trusted_experimental=False, natural_observation_verified=False, original_precision='unknown')
        passed = all((gates.get('C' + str(i), {}).get('passed') is True for i in range(1, 9))) and (not extra)
        if passed:
            quality = dict(binding, decision='source_relative_keep', rules_sha256=rule_config_sha256, evidence_sha256=digest(evidence), rule_id=RULE_ID, nucleus_scope='13C', implementation_sha256=file_sha(__file__), historical_C_quality_policy_status='unknown', policy_missing=True, known_conflict_input_sha256=known_conflicts_sha256, known_conflict_input_status=conflict_status, gate_outcomes=gates)
            reference = core.build_source_reference(raw_json_line, source_sha256=source_sha256, policy_jsonl=empty_C_policy_jsonl, policy_sha256=empty_C_policy_sha256, cohort_manifest_json=cohort_manifest_json, cohort_identity_manifest_sha256=cohort_identity_manifest_sha256, transport=transport, quality_receipt=quality)
            if reference.classification in ('unique_parent', 'parent_mapping_ambiguous'):
                public = dict(input_id=input_id, nucleus='13C', smiles=row['smiles'], actual_conditions=actual, observations=list(reference.anonymous_payload()))
            else:
                extra.extend(reference.reasons)
        else:
            reference = provisional
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError) as exc:
        extra.append(type(exc).__name__ + ':' + str(exc))
    for i in range(1, 9):
        gates.setdefault('C' + str(i), dict(passed=False, reasons=['not_evaluated_due_to_invalid_or_missing_prerequisite']))
    reasons = list(dict.fromkeys(['policy_missing', 'historical_C_quality_unknown'] + [reason for gate in gates.values() for reason in gate['reasons']] + extra))
    if quality is not None and public is None:
        quality = None
        reasons.append('quality_keep_withheld_public_payload_unavailable')
    if quality is None:
        evidence.update(binding=binding, gate_outcomes=gates, producer_reasons=reasons)
    candidate = public is not None and quality is not None
    ledger = dict(binding, input_id=input_id, status='C_direct_rule_reference_proposal' if candidate else 'unknown_or_restricted_retained', proposed_reference_class=reference.classification if reference is not None else 'unknown', reasons=reasons, gate_outcomes=gates, historical_C_quality_policy_status='unknown', policy_missing=True, known_conflict_input_status=conflict_status, known_conflict_input_sha256=known_conflicts_sha256, trusted_experimental=False, natural_observation_verified=False, original_precision='unknown', batch_application_review_required=True)
    return dict(ledger=ledger, quality_receipt=quality, evidence_bundle=evidence, reference=reference, public_payload=public)
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--validate-only', action='store_true')
    parser.parse_args()
    print(json.dumps(dict(status='SOURCE_ONLY_NO_BATCH_ENTRYPOINT', rule_id=RULE_ID, implementation_sha256=file_sha(__file__), empty_C_policy_sha256=EMPTY_POLICY_SHA, model_loads=0, model_forwards=0)))
