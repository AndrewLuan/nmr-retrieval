# 功能概述：已审H父诊断/聚合或Stage A科学入口的公开迁移副本，非历史actual-run字节。
# 接口：显式runtime授权及独立冻结plan/source/review/release；路径/身份/SHA从external bindings取得。
# 关系：直接依赖同publictree或现有nmr_assignment；保留原数值算法、完整分母、预算及失败协议。
from portable_runtime import binding, workspace, artifact_path, repository, _config
"""功能概述：对一个已冻结 H 记录作纯后处理；不读数据文件、不生成映射/候选、不求解。
process_record 是批次层的唯一入口，接收原始匿名 bytes、已审 source/gold/policy、预测
lineage、执行结果和 EvidenceAnchor，返回固定参考分母、共享位移误差、候选/见证诊断。
EvidenceAnchor 绑定批次层已核文件中的行内容；它不是化学真实性或执行授权。调用者必须
先核原制品、独审 SHA 和来源链。joint_family 只接受此前物化的完整状态表并检查闭包，
不补枚举；缺表且 attachment 改变 parent 投影时返回 unknown。
source_targets 从 source mask 与明确等价证据建目标；association 只把可确定完整父容量
接到已有 unit，无法区分同 parent 多 unit 时保守回退。local_tags 仅由既有结构图产生
N/O/S 局部描述及结构性可交换假设，不认证真实交换行为。method_diagnostics 只检验已
保存候选和 best/最多三条 alternatives，唯一结构选择可直接拼一条见证；无搜索。
关系：复用冻结 assignment_evaluation_adapter.build_reference、execution 的原始输入/
执行证书校验及 diagnostics API。全记录共享 .25 秒/50000 checks，超限不重试，保留
已建立的 gold/参考分母；非法绑定拒绝而不伪造完整性 receipt。无数据写入、网络、模型、
solver、训练、阈值选择或全局缓存；JSON 汇总/运行收据由 summarize_frozen_diagnostics 管理。
"""
from collections import Counter
from dataclasses import dataclass, replace, asdict
from decimal import Decimal
from hashlib import sha256
from itertools import chain
import json
from math import isfinite
from assignment_evaluation_adapter import build_reference, digest, _payload
from nmr_assignment.execution import _predictions, verify_execution_method, canonical_digest
from nmr_assignment.derived_observation import build_serialized_value_bins
from nmr_assignment.diagnostics import DiagnosticBinding, DiagnosticBudget, DiagnosticLimit, PayloadReceipt, ForwardTarget, ForwardAssociation, shared_forward, ReferenceChoices, candidate_diagnostics, AssignmentCompatibility, validate_witness, objective_diagnostic, payload_digest
INPUT_NAMES = ('public', 'gold', 'policy', 'admission_receipt', 'prediction_row', 'lineage_receipt', 'raw_result', 'numeric_config', 'roles')
TRUTH = 'source_relative_current_serialization'
REQUIRED_IMPLEMENTATIONS = {'assignment_evaluation_adapter.py': binding('frozen_reference_postprocessor.exact_SHA_or_identity.1'), 'nmr_assignment/diagnostics.py': binding('frozen_reference_postprocessor.exact_SHA_or_identity.2'), 'nmr_assignment/execution.py': binding('frozen_reference_postprocessor.exact_SHA_or_identity.3'), 'nmr_assignment/mapping.py': binding('frozen_reference_postprocessor.exact_SHA_or_identity.4'), 'nmr_assignment/source_reference.py': binding('frozen_reference_postprocessor.exact_SHA_or_identity.5'), 'nmr_assignment/source_transport.py': binding('frozen_reference_postprocessor.exact_SHA_or_identity.6')}

@dataclass(frozen=True)
class EvidenceAnchor:
    """Batch-reviewed canonical row hashes, not an authorization or authenticity proof."""
    payload_sha256: dict
    raw_payload_sha256: str
    source_application_review_sha256: str
    cache_application_review_sha256: str
    source_cohort_sha256: str
    evidence_ids: tuple
    joint_family_sha256: str = None

def _need(value, reason):
    if not value:
        raise ValueError(reason)

def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all((c in '0123456789abcdef' for c in value))

def _unknown(reason):
    return dict(status='unknown', reason_codes=[reason])

def _charge(value, budget):
    """Charge supplied tree traversal before hashing/parsing other evidence."""
    budget.step()
    if isinstance(value, dict):
        for k, v in value.items():
            _charge(v, budget)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _charge(v, budget)

def _receipt(payload, evidence):
    return PayloadReceipt(True, payload_digest(payload), tuple(evidence))

def _anchor_header(anchor):
    _need(type(anchor) is EvidenceAnchor, 'EvidenceAnchor_required')
    _need(anchor.evidence_ids and all((isinstance(e, str) and e for e in anchor.evidence_ids)), 'anchor_evidence_missing')
    for name in ('source_application_review_sha256', 'cache_application_review_sha256', 'source_cohort_sha256'):
        _need(_hash(getattr(anchor, name)), 'anchor_review_or_cohort_hash_missing')
    _need(set(anchor.payload_sha256) == set(INPUT_NAMES), 'anchor_input_domain')

def _source_slot_ledger(gold, anchor):
    """Bounded atomic source bookkeeping, before any prediction/execution work.

    At most 1 MiB JSON, 50000 encoder chunks and 50000 source slots. The caller
    charges the returned work immediately to its SAME budget, after retaining
    the already verified ledger. This is not a second budget or a retry. A
    source exceeding this integrity-preflight bound is rejected; the batch must
    retain its independently frozen ledger on rejection as on any ValueError.
    """
    _anchor_header(anchor)
    encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    hasher, nbytes, work = (sha256(), 0, 0)
    for chunk in encoder.iterencode(gold):
        encoded = chunk.encode()
        nbytes += len(encoded)
        work += 1
        _need(nbytes <= 1048576 and work <= 50000, 'source_ledger_preflight_bound')
        hasher.update(encoded)
    _need(hasher.hexdigest() == anchor.payload_sha256['gold'], 'anchor_mismatch:gold')
    rawline = gold['source_raw_line']
    _need(sha256(rawline.encode()).hexdigest() == gold['binding']['row_sha256'], 'source_raw_row_hash_mismatch')
    raw = json.loads(rawline, parse_float=Decimal)
    atoms, mask, values = (raw['atoms'], raw['atom_target_mask'], raw['atom_targets'])
    _need(len(atoms) == len(mask) == len(values) and len(atoms) <= 50000, 'source_column_length_or_bound')
    _need(all((atoms[i] == 'H' for i, m in enumerate(mask) if m)), 'non_H_reported_slot')
    slots = tuple(('slot:' + str(i) for i, m in enumerate(mask) if m))
    ledger = dict(source_known_H_slots=len(slots), source_known_H_slot_ids=slots, reference_environment_targets=None, unresolved_source_environment_slots=len(slots), source_partition_unknown=[dict(source_slot_ids=slots, reason='source_environment_formation_unverified')], source_conflict_targets=None, source_reference_admitted=None, eligible_reference_environment_targets=None, source_environment_formation_status='unknown', source_row_sha256=gold['binding']['row_sha256'], source_gold_payload_sha256=anchor.payload_sha256['gold'])
    return (ledger, work + len(atoms))

def _anchors(values, raw_payload, anchor, budget, names=INPUT_NAMES, check_raw=True):
    _anchor_header(anchor)
    for name in names:
        _charge(values[name], budget)
        _need(canonical_digest(values[name]) == anchor.payload_sha256[name], 'anchor_mismatch:' + name)
    if check_raw:
        _need(type(raw_payload) is bytes, 'exact_raw_payload_bytes_required')
        _need(sha256(raw_payload).hexdigest() == anchor.raw_payload_sha256, 'anchor_raw_bytes_mismatch')
        budget.step()

def _local_tags(snapshot, parents):
    atoms = {str(a['index']): a['z'] for a in snapshot['atoms']}
    neighbors = {p: set() for p in atoms}
    for bond in snapshot['bonds']:
        a, b = (str(bond['a']), str(bond['b']))
        neighbors[a].add(b)
        neighbors[b].add(a)
    variants = []
    for parent in parents:
        z = atoms[parent]
        tags = dict(direct_H_parent_elements=[e for e, n in (('N', 7), ('O', 8), ('S', 16)) if z == n], carbon_parent_neighbor_elements=[e for e, n in (('N', 7), ('O', 8), ('S', 16)) if z == 6 and any((atoms[q] == n for q in neighbors[parent]))], exchangeable_structural_hypothesis=z in (7, 8, 16))
        variants.append(tags)
    if not variants:
        return _unknown('structural_parent_unknown')
    unique = {canonical_digest(v): v for v in variants}
    if len(unique) != 1:
        return dict(status='ambiguous', variants=list(unique.values()), actual_exchange='unknown')
    return dict(status='complete', **variants[0], actual_exchange='unknown')

def source_targets(gold, policy, maps, budget):
    """Source-only denominator before inspecting prediction centers; no theory fields used."""
    raw = json.loads(gold['source_raw_line'], parse_float=Decimal)
    values, mask, atoms = (raw['atom_targets'], raw['atom_target_mask'], raw['atoms'])
    _need(len(values) == len(mask) == len(atoms), 'source_column_length')
    known = {i for i, m in enumerate(mask) if m and atoms[i] == 'H'}
    _need(all((atoms[i] == 'H' for i, m in enumerate(mask) if m)), 'non_H_reported_slot')
    _need(policy.get('index_basis') == 'source_array', 'source_policy_index_basis')
    _need(policy.get('shift_values_imputed') is False, 'imputed_source_values_not_allowed')
    for key in ('record_id', 'row_sha256', 'source', 'nucleus', 'structure_id'):
        _need(policy.get(key) == gold['binding'][key], 'source_policy_binding:' + key)
    seen, targets, unknown = (set(), [], [])
    for group in policy.get('source_atom_groups', []):
        budget.step()
        slots = group['source_H']
        observed = group['observed_source_H']
        _need(len(slots) == len(set(slots)) and all((type(i) is int and 0 <= i < len(atoms) and (atoms[i] == 'H') for i in slots)), 'invalid_source_H_group')
        _need(not seen.intersection(slots), 'overlapping_source_groups')
        seen.update(slots)
        _need(set(observed) == set(slots) & known, 'reported_group_mask_mismatch')
        if not observed:
            continue
        proven = len(slots) == 1 or (len(slots) == 3 and group.get('ordinary_methyl') is True and (group.get('equivalence') == 'fast_methyl_rotation_assumption'))
        if not proven:
            unknown.append(dict(source_slot_ids=observed, reason='source_environment_partition_unknown'))
            continue
        tid = 'source-env:' + ','.join((str(i) for i in sorted(slots)))
        vals = [Decimal(str(values[i])) for i in observed]
        _need(all((v.is_finite() for v in vals)), 'source_value_nonfinite')
        target = dict(target_id=tid, source_slot_ids=tuple(('slot:' + str(i) for i in observed)), structural_slots=tuple(slots), source_parent=str(group['source_parent']), equivalence_assumption=group.get('equivalence'), ppm=float(vals[0]), source_conflict=len(set(vals)) != 1)
        parents = []
        for mapping in maps:
            budget.step(len(slots))
            ps = {mapping[str(i)] for i in slots}
            if len(ps) == 1:
                parents.append(next(iter(ps)))
        if maps:
            budget.step(len(gold['baseline_structure_snapshot']['atoms']) + len(gold['baseline_structure_snapshot']['bonds']))
        target['local_structure_tags'] = _local_tags(gold['baseline_structure_snapshot'], parents) if maps and len(parents) == len(maps) else _unknown('structural_parent_unknown')
        targets.append(target)
    missing = known - seen
    if missing:
        unknown.append(dict(source_slot_ids=sorted(missing), reason='source_group_evidence_missing'))
    return (targets, dict(source_known_H_slots=len(known), reference_environment_targets=len(targets), unresolved_source_environment_slots=sum((len(v['source_slot_ids']) for v in unknown)), source_partition_unknown=unknown, source_conflict_targets=sum((t['source_conflict'] for t in targets))))

def structural_family(pred, maps, joint_family, anchor, budget):
    """Validate a supplied finite family; never enumerate missing permutations."""
    ids = tuple((u.unit_id for u in pred.layout.units))
    units = {u.unit_id: u for u in pred.layout.units}
    blocks = pred.attachment_blocks
    if joint_family is None:
        if any((len({units[u].parent_mass for u in block}) > 1 for block in blocks)):
            return (None, 'materialized_cross_parent_attachment_family_missing')
        return ([(i, dict(zip(ids, ids))) for i in range(len(maps))], 'parent_projection_invariant')
    _need(anchor.joint_family_sha256 and canonical_digest(joint_family) == anchor.joint_family_sha256, 'stored_joint_family_anchor_mismatch')
    _need(joint_family.get('complete') is True and joint_family.get('evidence_ids'), 'stored_joint_family_completeness_missing')
    _need(joint_family.get('transport_family_sha256') == canonical_digest(maps), 'stored_source_family_mismatch')
    _need(joint_family.get('attachment_sha256') == canonical_digest(dict(blocks=pred.attachment_blocks, evidence_ids=pred.attachment_evidence_ids)), 'stored_attachment_binding_mismatch')
    states = set()
    block_of = {u: set(block) for block in blocks for u in block}
    for state in joint_family['states']:
        budget.step(len(ids))
        i, permutation = (state['source_map_index'], tuple(state['unit_permutation']))
        _need(type(i) is int and 0 <= i < len(maps) and (len(permutation) == len(ids)) and (set(permutation) == set(ids)), 'stored_joint_state_invalid')
        _need(all((v in block_of.get(u, {u}) for u, v in zip(ids, permutation))), 'stored_permutation_crosses_attachment_block')
        states.add((i, permutation))
    _need(states, 'stored_joint_family_empty')
    for i, perm in states:
        for source_index in range(len(maps)):
            budget.step()
            _need((source_index, perm) in states, 'stored_source_state_missing')
        for block in blocks:
            for a, b in zip(block, block[1:]):
                budget.step(len(ids))
                transformed = tuple((b if v == a else a if v == b else v for v in perm))
                _need((i, transformed) in states, 'stored_attachment_closure_missing')
    return ([(i, dict(zip(ids, p))) for i, p in sorted(states)], 'stored_complete_family')

def forward_association(pred, targets, maps, family, family_kind, binding, evidence, budget):
    units = {u.unit_id: u for u in pred.layout.units}
    attached = set(chain.from_iterable(pred.attachment_blocks))
    selected, unknown, target_states = ([], [], {})
    for target in targets:
        budget.step()
        reason, choices = (None, [])
        if target['source_conflict']:
            reason = 'source_registry_value_disagreement'
        elif family is None:
            reason = 'joint_family_unknown'
        else:
            for map_index, permutation in family:
                budget.step(len(units))
                parents = {maps[map_index][str(s)] for s in target['structural_slots']}
                if len(parents) != 1:
                    reason = 'source_environment_parent_unknown'
                    break
                parent = next(iter(parents))
                possible = [uid for uid in units if units[permutation[uid]].parent_mass == ((parent, len(target['structural_slots'])),) and dict(pred.layout.parent_mass_totals).get(parent) == len(target['structural_slots'])]
                if len(possible) != 1:
                    reason = 'source_to_unit_partition_unknown'
                    break
                uid = possible[0]
                if units[uid].partition_status == 'unresolved_parent_pool':
                    reason = 'environment_partition_unknown'
                    break
                if family_kind != 'stored_complete_family' and uid in attached:
                    reason = 'forward_attachment_family_missing'
                    break
                choices.append(uid)
        if reason:
            unknown.append(dict(target_id=target['target_id'], status='unknown', reason_codes=[reason]))
        else:
            selected.append(target)
            target_states[target['target_id']] = choices
    collisions = set()
    for i in range(len(family or ())):
        by_unit = {}
        for t in selected:
            budget.step()
            by_unit.setdefault(target_states[t['target_id']][i], []).append(t['target_id'])
        collisions.update(chain.from_iterable((v for v in by_unit.values() if len(v) > 1)))
    selected = [t for t in selected if t['target_id'] not in collisions]
    unknown.extend((dict(target_id=t, status='unknown', reason_codes=['source_environment_unit_collision']) for t in sorted(collisions)))
    ts = tuple((ForwardTarget(t['target_id'], t['ppm'], t['source_slot_ids'], tuple(evidence)) for t in selected))
    states = tuple((tuple(((t['target_id'], target_states[t['target_id']][i]) for t in selected)) for i in range(len(family or ()))))
    association = ForwardAssociation(ts, states, pred.layout.partition_hypothesis_id)
    association = replace(association, receipt=_receipt(association.payload(binding), evidence)) if states else association
    return (association, unknown)

def _projection(members, permutation, units):
    return tuple(sorted({p for u in members for p, _ in units[permutation[u]].parent_mass}))

def _reference_states(derived, maps, family, budget):
    result = []
    for i, perm in family:
        budget.step(derived.reported_slot_count)
        reference = {v.bin_id: tuple(sorted({maps[i][str(s)] for s, _ in v.members})) for v in derived.hidden_provenance}
        result.append((reference, perm))
    return result

def _compatible(assignment, states, units, eligible, budget):
    for ref, perm in states:
        budget.step(sum((len(v) for v in assignment.values())) + len(eligible))
        if all((_projection(assignment[o], perm, units) == ref[o] for o in eligible)):
            return True
    return False

def _compatibility_proof(assignment, states, units, eligible, binding, evidence, budget):
    value = AssignmentCompatibility(tuple(sorted(((o, tuple(sorted(us))) for o, us in assignment.items()))), _compatible(assignment, states, units, eligible, budget))
    return replace(value, receipt=_receipt(value.payload(binding), evidence))

def _unique_prechoices(oid, states, units, limit, budget):
    """Unique structural sets and all-state counts; never search alternative sets."""
    choices, required = (set(), [])
    for ref, perm in states:
        budget.step(len(units))
        target = set(ref[oid])
        chosen = set()
        for parent in target:
            owners = [uid for uid in units if parent in dict(units[perm[uid]].parent_mass)]
            if len(owners) != 1:
                return (None, None)
            chosen.add(owners[0])
        if not chosen or set(_projection(chosen, perm, units)) != target:
            return (None, None)
        required.append(len(chosen))
        if len(chosen) <= limit:
            choices.add(tuple(sorted(chosen)))
    proof = None
    if required and all((count > limit for count in required)):
        proof = dict(reason='method_cardinality_limit', method_capacity_limit=limit, required_unit_counts_by_existing_state=required, minimum_required_units=min(required), maximum_required_units=max(required), existing_state_count=len(states), every_existing_state_exceeds_limit=True, proof='unique_structural_owner_per_parent_in_complete_existing_states', state_family_sha256=canonical_digest(states))
    return (tuple(sorted(choices)), proof)

def method_diagnostics(method, verified, reference, states, pred, binding, evidence, budget):
    if verified.get('status') != 'complete':
        return dict(status='unknown', reason_codes=verified.get('reason_codes', ['execution_unverified']))
    if states is None:
        return _unknown('joint_state_family_unavailable')
    trace = verified['trace']
    units = {u.unit_id: u for u in pred.layout.units}
    eligible = tuple((o for o, v in reference['observation_admission'].items() if v['admitted']))
    if not eligible:
        return _unknown('no_admitted_reference_observations')
    membership, complete_choices = ([], {})
    for oid in eligible:
        matches = set()
        for c in trace.candidates:
            budget.step()
            if c.observation_id != oid:
                continue
            for ref, perm in states:
                budget.step(len(c.unit_ids))
                if _projection(c.unit_ids, perm, units) == ref[oid]:
                    matches.add(tuple(sorted(c.unit_ids)))
                    break
        sets, cardinality = _unique_prechoices(oid, states, units, 2 if method == 'B2' else 1, budget)
        row = dict(observation_id=oid, gold_eligible=True, reference_candidate_present=bool(matches), compatible_emitted_unitset_count=len(matches), candidate_generation_complete=True, reference_state_family_complete=True, pre_gate_representable='unknown', numerical_gate_excluded='unknown')
        if cardinality is not None:
            row['method_cardinality_limit'] = cardinality
        if sets is not None:
            choices = ReferenceChoices(oid, sets)
            choices = replace(choices, receipt=_receipt(choices.payload(binding, method), evidence))
            diagnostic = candidate_diagnostics(trace, choices, binding=binding, budget=budget)
            row['pre_gate_diagnostic'] = diagnostic
            if diagnostic['status'] == 'complete':
                row['pre_gate_representable'] = diagnostic['local_reference_representable']
                row['numerical_gate_excluded'] = diagnostic['numerical_gate_excluded']
                complete_choices[oid] = tuple((s for s in sets if s in matches))
        row['gate_subtype'] = 'unknown_no_saved_rejection_reason'
        membership.append(row)
    obj = verified['result_object']
    saved = [obj.solver_result.best] + list(obj.solver_result.alternatives[:3])
    witnesses, selected = ([], None)
    for index, solution in enumerate(saved):
        if solution is None:
            continue
        assignment = dict(solution.assignments)
        compat = _compatibility_proof(assignment, states, units, eligible, binding, evidence, budget)
        witness = validate_witness(assignment, trace, compat, binding=binding, budget=budget)
        witnesses.append(dict(origin='saved_best' if index == 0 else 'saved_alternative:' + str(index), validation=witness))
        if witness.get('status') == 'complete' and witness.get('compatible'):
            selected = witness
            break
    if selected is None and set(complete_choices) == set(eligible) and all((len(v) == 1 for v in complete_choices.values())):
        assignment = {o: complete_choices[o][0] if o in complete_choices else () for o in trace.observation_ids}
        compat = _compatibility_proof(assignment, states, units, eligible, binding, evidence, budget)
        witness = validate_witness(assignment, trace, compat, binding=binding, budget=budget)
        witnesses.append(dict(origin='structurally_unique_direct', validation=witness))
        if witness.get('status') == 'complete' and witness.get('compatible'):
            selected = witness
    objective = _unknown('validated_reference_witness_required')
    if selected is not None:
        best = _compatibility_proof(verified['assignments'], states, units, eligible, binding, evidence, budget)
        objective = objective_diagnostic(obj, best, selected, binding=binding, trace=trace, result_certificate=verified['result_certificate'], budget=budget)
    return dict(status='complete', candidate_membership=membership, witness_found=True if selected else 'unknown', witness_attempts=witnesses, objective_diagnostic=objective, raw_actions=dict(unexplained=list(obj.solver_result.best.unexplained), unobserved=list(obj.solver_result.best.unobserved)), execution_receipt_sha256=verified['execution_receipt_sha256'], interpretation='nonexclusive_operational_diagnostics_not_causal_proportions')

def process_record(*, input_id, public, gold, policy, admission_receipt, prediction_row, lineage_receipt, raw_result, raw_payload, numeric_config, roles, evidence_anchor, joint_family=None, budget=None):
    """Pure one-record bridge. ValueError means integrity failure; unknown preserves denominator.

    roles must be a list containing only the existing non-test roles. The batch
    driver must write its fixed identity ledger before invoking this function.
    This function neither fits thresholds nor changes any saved evaluation row.
    """
    b = DiagnosticBudget() if budget is None else budget
    out = dict(schema='frozen_reference_postprocessing_record_v1', input_id=input_id, roles=roles, truth_basis=TRUTH, methods={m: _unknown('not_processed') for m in ('B1', 'B2')}, shared_forward=_unknown('not_processed'), reference_denominators=None, gold_eligible_observations=None, natural_missing='unknown', natural_overlap='unknown', label_error='unknown', new_model_calls=0, new_solver_calls=0, new_mapping_search=0)
    try:
        _need(isinstance(roles, list) and roles and (len(set(roles)) == len(roles)) and (set(roles) <= {'fixed_train8192', 'tune', 'original_val'}), 'non_test_roles_required')
        values = dict(public=public, gold=gold, policy=policy, admission_receipt=admission_receipt, prediction_row=prediction_row, lineage_receipt=lineage_receipt, raw_result=raw_result, numeric_config=numeric_config, roles=roles)
        denominator, source_work = _source_slot_ledger(gold, evidence_anchor)
        out['reference_denominators'] = denominator
        out['source_record_id'] = gold['binding']['record_id']
        b.step(source_work)
        _anchors(values, raw_payload, evidence_anchor, b, names=('public', 'policy', 'admission_receipt', 'roles'), check_raw=False)
        _need(input_id == public['input_id'] == gold['input_id'], 'input_identity_mismatch')
        _need(public['nucleus'] == '1H', 'H_scope_only')
        admission = _payload(admission_receipt)
        _need(admission.get('independent_application_review_sha256') == evidence_anchor.source_application_review_sha256, 'source_application_review_mismatch')
        targets, formed = source_targets(gold, policy, [], b)
        denominator.update(formed, source_environment_formation_status='complete')
        out['reference_targets'] = [{k: v for k, v in t.items() if k not in ('ppm', 'structural_slots')} for t in targets]
        reference, reasons = build_reference(gold, public, batch_admission_receipt=admission_receipt, source_cohort_sha256=evidence_anchor.source_cohort_sha256)
        out['gold_eligible_observations'] = sum((v['admitted'] for v in reference['observation_admission'].values()))
        out['source_record_id'] = gold['binding']['record_id']
        out['reference_sha256'] = canonical_digest(reference)
        admitted = bool(reference['observation_admission']) and all((v['admitted'] for v in reference['observation_admission'].values()))
        denominator['source_reference_admitted'] = admitted
        denominator['eligible_reference_environment_targets'] = len(targets) if admitted else 0
        b.step()
        if not reference['joint_reference_complete']:
            out.update(status='unknown', reason_codes=list(reasons))
            return out
        maps = gold['transport']['joint_maps']
        for target in targets:
            parents = []
            for mapping in maps:
                b.step(len(target['structural_slots']))
                ps = {mapping[str(i)] for i in target['structural_slots']}
                if len(ps) == 1:
                    parents.append(next(iter(ps)))
            b.step(len(gold['baseline_structure_snapshot']['atoms']) + len(gold['baseline_structure_snapshot']['bonds']))
            target['local_structure_tags'] = _local_tags(gold['baseline_structure_snapshot'], parents) if len(parents) == len(maps) else _unknown('environment_has_multiple_parents')
        normalization = policy.get('_normalization', {})
        out['source_correction_metadata'] = dict(reference_choice=normalization.get('reference_choice', 'unknown'), correction_overlay_sha256=normalization.get('correction_overlay_sha256'), interpretation='source_policy_overlay_metadata_not_proof_of_chemical_label_error')
        out['reference_targets'] = [{k: v for k, v in t.items() if k not in ('ppm', 'structural_slots')} for t in targets]
        if not admitted:
            out['shared_forward'] = _unknown('source_reference_not_admitted')
            out.update(status='unknown', reason_codes=list(reasons))
            return out
        _anchors(values, raw_payload, evidence_anchor, b, names=('prediction_row', 'lineage_receipt', 'raw_result', 'numeric_config'))
        if prediction_row is None:
            out['shared_forward'] = _unknown('prediction_missing')
            out.update(status='unknown', reason_codes=['prediction_missing'])
            return out
        _need(prediction_row['input_id'] == input_id, 'prediction_input_identity')
        pred = _predictions(prediction_row['predictions'])
        lineage = _payload(lineage_receipt)
        _need(lineage.get('input_id') == input_id and lineage.get('complete') is True, 'prediction_lineage_incomplete')
        _need(lineage.get('independent_cache_review_sha256') == evidence_anchor.cache_application_review_sha256, 'cache_review_mismatch')
        _need(lineage['baseline_structure_snapshot_sha256'] == gold['baseline_structure_snapshot_sha256'], 'baseline_snapshot_lineage_mismatch')
        snapshot = prediction_row['native_structure_snapshot']
        _need(snapshot == gold['baseline_structure_snapshot'] and snapshot['canonical_smiles'] == public['smiles'], 'native_baseline_graph_mismatch')
        _need(lineage['native_structure_snapshot_sha256'] == digest(snapshot) and lineage['native_graph_snapshot_sha256'] == digest({k: snapshot[k] for k in ('atoms', 'bonds')}), 'native_snapshot_hash_mismatch')
        _need(gold['baseline_structure_snapshot_sha256'] in (digest(snapshot), sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()), 'baseline_snapshot_hash_mismatch')
        _need(lineage['prediction_payload_sha256'] == digest(asdict(pred)) and lineage['layout_sha256'] == digest(asdict(pred.layout)) and (lineage['attachment_sha256'] == digest(dict(blocks=pred.attachment_blocks, evidence_ids=pred.attachment_evidence_ids))), 'prediction_payload_lineage_mismatch')
        _need(lineage['prediction_artifact_sha256'] == prediction_row['prediction_artifact_sha256'], 'prediction_artifact_lineage_mismatch')
        _need(lineage.get('evidence_ids'), 'prediction_lineage_evidence_missing')
        raw = json.loads(raw_payload)
        _need(raw['predictions'] == prediction_row['predictions'] and raw['numeric_config'] == numeric_config, 'raw_prediction_or_config_mismatch')
        _need(raw['observations'] == [dict(observation_id=o['bin_id'], ppm=float(o['ppm_decimal'])) for o in public['observations']], 'raw_observation_mismatch')
        binding = DiagnosticBinding(gold['binding']['record_id'], TRUTH, '1H', 'derived_serialized_value_bin', prediction_row['prediction_artifact_sha256'], out['reference_sha256'], canonical_digest(numeric_config))
        evidence = tuple(evidence_anchor.evidence_ids) + tuple(lineage['evidence_ids']) + ('transport:' + gold['transport']['completeness_evidence_sha256'],)
        family, family_kind = structural_family(pred, maps, joint_family, evidence_anchor, b)
        association, association_unknown = forward_association(pred, targets, maps, family, family_kind, binding, evidence, b)
        forward = shared_forward(pred, association, binding=binding, budget=b)
        forward['source_reference_target_count'] = len(targets)
        forward['association_unknown_rows'] = association_unknown
        forward['domain_scope'] = 'full_reference_targets' if len(association.targets) == len(targets) else 'structurally_identified_subset'
        forward['local_structure_tags'] = {t['target_id']: t['local_structure_tags'] for t in targets}
        accounted = {r['target_id']: r for r in list(forward.get('rows', ())) + association_unknown}
        for t in targets:
            accounted.setdefault(t['target_id'], dict(target_id=t['target_id'], status='unknown', reason_codes=forward.get('reason_codes', ['diagnostic_unknown'])))
        forward['accounted_target_rows'] = [accounted[t['target_id']] for t in targets]
        counts = Counter((r['status'] for r in accounted.values()))
        forward['coverage'] = dict(reference_targets=len(targets), scalar=counts['scalar'], mixture=counts['mixture'], ambiguity_bounds=counts['ambiguity_bounds'], unknown=counts['unknown'])
        for row in forward.get('rows', ()):
            if row.get('status') == 'scalar':
                widths = {c.sigma_ppm for c in pred.carriers if c.unit_id == row['unit_id']}
                if len(widths) == 1 and None not in widths:
                    width = next(iter(widths))
                    row['fixed_width_ppm'] = width
                    row['fixed_scale_3width_exceeded'] = row['absolute_error'] > 3 * width
        forward.pop('artifact_sha256', None)
        forward['artifact_sha256'] = canonical_digest(forward)
        out['shared_forward'] = forward
        derived = build_serialized_value_bins(gold['source_raw_line'])
        states = _reference_states(derived, maps, family, b) if family is not None else None
        envelope = raw_result.get('raw_execution', raw_result)
        for method in ('B1', 'B2'):
            b.step()
            verified = verify_execution_method(envelope, raw_payload, approved_numeric_config=numeric_config, input_id=input_id, prediction_artifact_sha256=prediction_row['prediction_artifact_sha256'], method=method, binding=binding, budget=b)
            out['methods'][method] = method_diagnostics(method, verified, reference, states, pred, binding, evidence, b)
            out['methods'][method]['shared_forward_artifact_sha256'] = forward['artifact_sha256']
        out.update(status='complete', reason_codes=list(reasons), joint_family_kind=family_kind)
    except DiagnosticLimit:
        out.update(status='unknown', reason_codes=['diagnostic_budget'])
    finally:
        out['budget_checks'] = b.checks
    return out
