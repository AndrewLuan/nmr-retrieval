# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
REPO = repository()
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from nmr_assignment.derived_observation import build_serialized_value_bins
from nmr_assignment.mapping import FrozenCapacityPredictions, make_joint_mapping, project_assignment
from nmr_assignment.metrics import evaluate_assignment, reference_digest

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def text_digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all((c in '0123456789abcdef' for c in value))

def _payload(receipt):
    if not isinstance(receipt, dict) or not isinstance(receipt.get('payload'), dict):
        raise ValueError('explicit frozen receipt payload required')
    if receipt.get('sha256') != digest(receipt['payload']):
        raise ValueError('receipt payload SHA mismatch')
    return receipt['payload']

def _lineage_digest(lineage):
    restored = dict(lineage)
    for name in ('source_suppressed_H_by_parent', 'target_suppressed_H_by_parent'):
        if name in restored:
            restored[name] = {int(k): v for k, v in restored[name].items()}
    return digest(restored)

def _gold_payload(gold):
    return dict(input_id=gold['input_id'], binding=gold['binding'], joint_gold_parent_sets=gold.get('joint_gold_parent_sets', ()))

def build_reference(gold, public, *, batch_admission_receipt, source_cohort_sha256):
    """Return metric reference with independently pre-frozen eligibility.

    batch receipt payload binds exact input_id, all eight source binding fields,
    reference_payload_sha256, admitted, joint_nontrivial, rule_version,
    implementation_sha256 and evidence_ids. It is a final batch admission artifact,
    not the earlier transport-component PASS. Receipt authenticity is an external
    responsibility; this pure adapter checks exact content and bound proof shapes.
    """
    if public['input_id'] != gold['input_id'] or public['nucleus'] != gold['binding']['nucleus']:
        raise ValueError('public/gold identity mismatch')
    binding = gold['binding']
    if binding['cohort_identity_manifest_sha256'] != source_cohort_sha256:
        raise ValueError('cohort SHA mismatch')
    if gold.get('truth_basis') != 'source_relative_current_serialization' or gold.get('reference_basis') != 'source_asserted_encoded_graph' or gold.get('trust_basis') != 'internal_source_consistency' or (gold.get('trusted_experimental') is not False):
        raise ValueError('reference track mismatch')
    raw = gold['source_raw_line']
    if text_digest(raw) != binding['row_sha256']:
        raise ValueError('raw row SHA mismatch')
    row = json.loads(raw)
    identity = (row['source_ref'], row['nucleus'], row['record_id'], row.get('structure_id') or text_digest(row['smiles']))
    if identity != tuple((binding[k] for k in ('source', 'nucleus', 'record_id', 'structure_id'))):
        raise ValueError('raw row identity mismatch')
    derived = build_serialized_value_bins(raw)
    if list(derived.anonymous_payload()) != public['observations']:
        raise ValueError('public anonymous bins differ from bound raw')
    obs = tuple((b.bin_id for b in derived.inference_bins))
    reasons = []
    proof_ok = False
    transport = gold.get('transport', {})
    variants = []
    try:
        if not all((transport.get(k) == v for k, v in binding.items())):
            raise ValueError('transport binding mismatch')
        if not (transport.get('complete') is True and transport.get('enumeration_truncated') is False):
            raise ValueError('transport family incomplete')
        lineage = transport['graph_lineage_evidence']
        proof = transport['completeness_evidence']
        snapshot = gold['baseline_structure_snapshot']
        if lineage.get('canonical_smiles') != public['smiles'] or snapshot.get('canonical_smiles') != public['smiles'] or lineage.get('baseline_graph') != {k: snapshot[k] for k in ('atoms', 'bonds')}:
            raise ValueError('baseline graph snapshot differs from transport lineage')
        if _lineage_digest(lineage) != transport['graph_lineage_evidence_sha256'] or digest(proof) != transport['completeness_evidence_sha256'] or proof['graph_lineage_evidence_sha256'] != _lineage_digest(lineage) or (proof.get('enumeration_truncated') is not False):
            raise ValueError('transport evidence digest mismatch')
        from nmr_assignment.source_transport import restore_joint_map_keys
        maps = restore_joint_map_keys(transport)['joint_maps']
        if not maps or any((set(m) != set(range(derived.source_slot_count)) for m in maps)):
            raise ValueError('transport source-slot domain mismatch')
        family = sorted(set((tuple((m[i] for i in range(derived.source_slot_count))) for m in maps)))
        if family != sorted(set((tuple(v) for v in proof['parent_projection_rows']))):
            raise ValueError('transport whole-family proof mismatch')
        states = set()
        for mapping in maps:
            states.add(tuple(((b.bin_id, tuple(sorted({mapping[i] for i, _ in b.members}))) for b in derived.hidden_provenance)))
        variants = [dict(v) for v in sorted(states)]
        supplied = [dict(((o, tuple(sorted(set(t)))) for o, t in v)) for v in gold.get('joint_gold_parent_sets', ())]
        if reference_digest(variants, target_semantics='set') != reference_digest(supplied, target_semantics='set'):
            raise ValueError('hidden gold differs from proof-bound joint SET projection')
        proof_ok = True
    except (KeyError, ValueError, TypeError) as exc:
        reasons.append('pregold:' + str(exc))
    admission = None
    try:
        admission = _payload(batch_admission_receipt)
        if admission['input_id'] != gold['input_id'] or admission['binding'] != binding or admission['reference_payload_sha256'] != digest(_gold_payload(gold)) or (admission.get('transport_completeness_evidence_sha256') != transport.get('completeness_evidence_sha256')) or (admission.get('transport_implementation_sha256') != transport.get('graph_lineage_evidence', {}).get('implementation_sha256')) or (not _sha(admission['implementation_sha256'])) or (not isinstance(admission['rule_version'], str)) or (not admission['rule_version']) or (not admission['evidence_ids']):
            raise ValueError('final admission binding missing')
        if type(admission['admitted']) is not bool or type(admission['joint_nontrivial']) is not bool:
            raise ValueError('explicit admission booleans required')
    except (KeyError, ValueError, TypeError) as exc:
        admission = None
        reasons.append('pregold:' + str(exc))
    admitted = bool(proof_ok and derived.reported_slot_count and (gold.get('scoreable') is True) and admission and (admission['admitted'] is True))
    if not admitted:
        reasons.append('pregold:not_admitted_or_unscoreable')
    if not derived.reported_slot_count:
        reasons.append('pregold:no_known_labels')
    admission_sha = batch_admission_receipt.get('sha256') if admission else digest(dict(status='missing_final_admission', input_id=gold['input_id']))
    rule = admission['rule_version'] if admission else 'unadmitted-reference'
    implementation = admission['implementation_sha256'] if admission else '0' * 64
    evidence = tuple(admission['evidence_ids']) if admission else ('unavailable:final-batch-admission',)
    complete = bool(proof_ok)
    whole_digest = reference_digest(variants, target_semantics='set')
    completeness_body = dict(complete=complete, transport_completeness_sha256=transport.get('completeness_evidence_sha256'), admission_receipt_sha256=admission_sha, whole_joint_targets_sha256=whole_digest, source_row_sha256=binding['row_sha256'], source_cohort_sha256=source_cohort_sha256)
    reference = dict(input_observation_ids=obs, whole_joint_targets=variants, observation_admission={o: dict(admitted=admitted, rule_version=rule, implementation_sha256=implementation, admission_receipt_sha256=admission_sha, evidence_ids=evidence, core_evidence={}) for o in obs}, joint_reference_complete=complete, joint_nontrivial=bool(admission and admission['joint_nontrivial']), joint_evidence_ids=evidence, gold_completeness_receipt=dict(complete=complete, receipt_sha256=digest(completeness_body), whole_joint_targets_sha256=whole_digest, proof_kind='complete_projection_quotient', evidence_ids=evidence + (('sha256:' + transport['completeness_evidence_sha256'],) if proof_ok else ())), strict_full_spectrum_evidence={})
    return (reference, tuple(reasons))

def prediction_mapping(predictions, *, input_id, gold, prediction_lineage_receipt):
    """Canonical baseline capacities plus latent whole attachment permutations.

    Source automorphisms are already retained in the gold whole-family. This side
    uses canonical parent IDs from layout, never a gold-chosen source permutation.
    """
    if type(predictions) is not FrozenCapacityPredictions:
        raise ValueError('FrozenCapacityPredictions required')
    p = _payload(prediction_lineage_receipt)
    if p.get('input_id') != input_id or p.get('complete') is not True or p.get('baseline_structure_snapshot_sha256') != gold.get('baseline_structure_snapshot_sha256') or (p.get('layout_sha256') != digest(asdict(predictions.layout))) or (p.get('attachment_sha256') != digest(dict(blocks=predictions.attachment_blocks, evidence_ids=predictions.attachment_evidence_ids))) or (p.get('prediction_payload_sha256') != digest(asdict(predictions))) or (not p.get('evidence_ids')) or (not _sha(p.get('prediction_artifact_sha256'))):
        raise ValueError('canonical prediction lineage incomplete or unbound')
    if digest(gold['baseline_structure_snapshot']) != gold['baseline_structure_snapshot_sha256']:
        if text_digest(json.dumps(gold['baseline_structure_snapshot'], sort_keys=True)) != gold['baseline_structure_snapshot_sha256']:
            raise ValueError('baseline snapshot digest mismatch')
    layout = predictions.layout
    ids = tuple((u.unit_id for u in layout.units))
    targets = {u.unit_id: tuple((parent for parent, mass in u.parent_mass for _ in range(mass))) for u in layout.units}
    return make_joint_mapping(layout, targets, (ids,), level='parent', complete=True, basis='latent_attachment_ambiguity' if predictions.attachment_blocks else 'provenance_lineage', evidence_ids=tuple(p['evidence_ids']), target_universe=tuple((parent for parent, _ in layout.parent_mass_totals)), completeness_evidence_id='sha256:' + prediction_lineage_receipt['sha256'], attachment_blocks=predictions.attachment_blocks, attachment_evidence_ids=predictions.attachment_evidence_ids)

def execution_assignment(execution_result, *, method, observation_ids, verified=None):
    """Use the shared execution verifier; no free-standing certification flags."""
    if method not in ('B0', 'B1', 'B2'):
        raise ValueError('baseline must be B0/B1/B2')
    envelope = execution_result if isinstance(execution_result, dict) else {}
    raw = (envelope.get('result') or {}).get('methods', {}).get(method, {})
    supported = isinstance(verified, dict) and verified.get('status') == 'complete' and (verified.get('certified') is True)
    timeout = envelope.get('timed_out') is True or raw.get('timed_out') is True
    status = dict(status='verified_execution' if supported else 'execution_unverified', certified=supported, timed_out=timeout, reuse_semantics='independent_local' if method == 'B0' else 'global_exclusive', observation_determinate={o: False for o in observation_ids}, observation_alternatives={}, observation_alternatives_complete={})
    if not supported:
        return ({}, status, raw)
    status['observation_determinate'] = dict(verified['observation_determinate'])
    status['observation_alternatives'] = dict(verified.get('observation_alternatives', {}))
    status['observation_alternatives_complete'] = dict(verified.get('observation_alternatives_complete', {}))
    return (dict(verified['assignments']), status, raw)

def margin_scores(method_result, *, relative_tolerance, verified_execution=None):
    """Only expose scores already rechecked against the exact bound backend trace."""
    if isinstance(relative_tolerance, bool) or not math.isfinite(relative_tolerance) or relative_tolerance < 0:
        raise ValueError('explicit finite nonnegative tie tolerance required')
    ids = (method_result.get('solver_result') or {}).get('margins', {})
    empty = {o: dict(margin=None, margin_certified=False, margin_tolerance=0.0) for o in ids}
    verified = verified_execution or {}
    if verified.get('status') != 'complete' or verified.get('certified') is not True or verified.get('tie_relative_tolerance') != relative_tolerance or (verified.get('method_result_sha256') != digest(method_result)):
        return empty
    return {o: dict(verified.get('margin_scores', {}).get(o, empty[o])) for o in ids}

def evaluate_record(gold, public, predictions, execution_result, *, method, roles, source_cohort_sha256, connectivity_sha256, batch_admission_receipt, prediction_lineage_receipt=None, execution_payload=None, approved_numeric_config=None, diagnostic_budget=None):
    """Return metric rows and audit envelope without running real inference/scoring IO."""
    reference, pregold_reasons = build_reference(gold, public, batch_admission_receipt=batch_admission_receipt, source_cohort_sha256=source_cohort_sha256)
    metadata = dict(input_id=gold['input_id'], roles=tuple(roles), source_binding=gold['binding'], source_cohort_sha256=source_cohort_sha256, connectivity_sha256=connectivity_sha256, pregold_reasons=pregold_reasons, truth_basis='source_relative_current_serialization', task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', baseline=method, calibrated_publication=False)
    if not reference['input_observation_ids']:
        return dict(rows=(), metadata=metadata, reference=reference, pipeline_status=None)
    joint = None
    prediction_reasons = []
    if predictions is not None:
        try:
            joint = prediction_mapping(predictions, input_id=gold['input_id'], gold=gold, prediction_lineage_receipt=prediction_lineage_receipt)
        except (ValueError, KeyError, TypeError) as exc:
            prediction_reasons.append('prediction:' + str(exc))
    verified = dict(status='unknown', certified=False, reason_codes=('execution_input_evidence_missing',))
    if joint is not None:
        try:
            from nmr_assignment.execution import verify_execution_method, _decode
            from nmr_assignment.diagnostics import DiagnosticBinding
            payload = _decode(execution_payload)
            expected_obs = [dict(observation_id=o['bin_id'], ppm=float(o['ppm_decimal'])) for o in public['observations']]
            if digest(payload['observations']) != digest(expected_obs) or digest(payload['predictions']) != digest(asdict(predictions)) or payload['numeric_config'] != approved_numeric_config:
                raise ValueError('evaluation actual input/prediction/config mismatch')
            lineage = _payload(prediction_lineage_receipt)
            db = DiagnosticBinding(gold['binding']['record_id'], 'source_relative_current_serialization', gold['binding']['nucleus'], 'derived_serialized_value_bin', lineage['prediction_artifact_sha256'], digest(_gold_payload(gold)), digest(approved_numeric_config))
            verified = verify_execution_method(execution_result, execution_payload, approved_numeric_config=approved_numeric_config, input_id=public['input_id'], prediction_artifact_sha256=lineage['prediction_artifact_sha256'], method=method, binding=db, budget=diagnostic_budget)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            verified = dict(status='unknown', certified=False, reason_codes=(str(exc),))
    if verified.get('status') != 'complete':
        prediction_reasons.extend(('prediction:' + r for r in verified.get('reason_codes', ('execution_unverified',))))
    assignment, status, method_result = execution_assignment(execution_result, method=method, observation_ids=reference['input_observation_ids'], verified=verified)
    context = dict(truth_basis='source_relative_current_serialization', nucleus=gold['binding']['nucleus'], task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', baseline=method, record_id=gold['binding']['record_id'], connectivity_id=connectivity_sha256)
    rows = evaluate_assignment(assignment, joint, context=context, reference=reference, pipeline_status=status)
    metadata['prediction_reasons'] = tuple(prediction_reasons)
    return dict(rows=rows, metadata=metadata, reference=reference, pipeline_status=status, method_result=method_result, prediction_joint_mapping=joint, prediction_assignment=assignment, execution_verification=dict(status=verified.get('status'), certified=verified.get('certified', False), reason_codes=verified.get('reason_codes', ()), margin_scores=verified.get('margin_scores', {}), tie_relative_tolerance=verified.get('tie_relative_tolerance'), method_result_sha256=digest(method_result), execution_receipt_sha256=verified.get('execution_receipt_sha256'), candidate_trace_sha256=verified.get('source_candidate_trace_sha256')))

def _prediction_target_invariance(bundle):
    """Uniqueness of advertised prediction targets, independent of gold alternatives."""
    joint = bundle.get('prediction_joint_mapping')
    assignment = bundle.get('prediction_assignment') or {}
    status = bundle['pipeline_status']
    ids = bundle['reference']['input_observation_ids']
    semantics = bundle['metadata']['target_semantics']
    invariant = {o: False for o in ids}
    if joint is None or not joint.complete:
        return invariant
    for oid in ids:
        block = status.get('observation_alternatives', {}).get(oid)
        if block is not None:
            if status.get('observation_alternatives_complete', {}).get(oid) is not True:
                continue
            choices = tuple(((unit,) for unit in block))
        else:
            choices = (tuple(assignment.get(oid, ())),)
        targets = set()
        for units in choices:
            projection = project_assignment({oid: units}, joint, reuse_semantics=status['reuse_semantics'])
            if not projection.mapping_complete:
                continue
            for variant in projection.variants:
                value = dict(variant)[oid]
                normalized = tuple(sorted(set(value))) if semantics == 'set' else tuple(sorted(value))
                targets.add(normalized)
        invariant[oid] = len(targets) == 1 and bool(next(iter(targets)))
    return invariant

def calibration_record_from_evaluation(row, bundle, *, cohort_sha256, source_sha256, label_sha256, rule_sha256, relative_tolerance):
    """Bridge raw gap certificates to frozen calibration API; never fit a threshold.

    Caller selects an approved endpoint. Source-relative confidence publication
    uses compatibility_precision; the core API rejects experimental-accuracy
    endpoints for this track. Missing scores retain eligible denominator entries.
    """
    from nmr_assignment.calibration import evaluation_record_from_row
    scores = margin_scores(bundle.get('method_result', {}), relative_tolerance=relative_tolerance, verified_execution=bundle.get('execution_verification'))
    score = scores.get(row.observation_id, dict(margin=None, margin_certified=False, margin_tolerance=0.0))
    whole = row.observation_id is None
    invariant = _prediction_target_invariance(bundle)
    pipeline = dict(bundle['pipeline_status'])
    pipeline['observation_determinate'] = {oid: bundle['pipeline_status'].get('observation_determinate', {}).get(oid) is True and invariant.get(oid) is True for oid in bundle['reference']['input_observation_ids']}
    return evaluation_record_from_row(row, margin=None if whole else score['margin'], margin_certified=True if whole else score['margin_certified'], cohort_sha256=cohort_sha256, source_sha256=source_sha256, label_sha256=label_sha256, rule_sha256=rule_sha256, pipeline_status=pipeline, margin_tolerance=score['margin_tolerance'], input_observation_ids=bundle['reference']['input_observation_ids'] if whole else None, observation_scores=scores if whole else None)

def _synthetic_execution(public, predictions):
    """Test-only hand-authored backend log; no solver, model, or real data calls."""
    from math import log
    from time import monotonic
    from nmr_assignment.execution import _prepare_record, _candidate_diagnostics, _make_execution_receipt, canonical_digest
    costs = dict(B0_B1_reference_scale_ppm={'1H': 0.3, '13C': 2}, B2_cost_convention='reduced_scale_normalizer', B2_gate_mode='standardized', B2_member_gate_multiplier=3, B2_pair_span_error_scale_multiplier=2, B2_delta=1.5, B2_merge_cost=log(2), smin_ppm={'1H': 0.05, '13C': 0.5}, integral_policy='disabled_both_nuclei_first_round', missing_kappa_ordinary=log(3), missing_kappa_reduced_reporting=0, B1_unexplained=3, B2_unexplained=3.375, max_units_per_observation=2)
    config = dict(costs=costs, budgets=dict(per_record_wall_seconds=10, mapping_and_candidates_seconds=2, B1_solver_seconds=2, B2_solver_seconds=5, result_validation_reserve_seconds=1, max_candidates_per_global_problem=50000, top_k=3, compute_margins=True, input_bytes_limit=10485760), tie_relative_tolerance=1e-07)
    value = dict(observations=[dict(observation_id=o['bin_id'], ppm=float(o['ppm_decimal'])) for o in public['observations']], predictions=asdict(predictions), exchangeable_unit_ids=[], actual_window=None, numeric_config=config)
    raw = json.dumps(value, allow_nan=False).encode()
    now = monotonic()
    prepared = _prepare_record(raw, config, started=now, total_deadline=now + 10, pre_deadline=now + 2)
    assert prepared['status'] == 'prepared', prepared
    methods = prepared['methods']
    requests = {}
    for name, graph in prepared['candidates'].items():
        obs, units = (prepared['observation_ids'], prepared['unit_ids'])
        request = dict(observation_ids=obs, unit_ids=units, candidates=graph['values'], missing_costs=prepared['relative_missing_costs'], unexplained_costs={o: costs[name + '_unexplained'] for o in obs}, top_k=3, compute_margins=True, time_limit=1.0)
        requests[name] = request
        available = {(c['observation_id'], tuple(c['environment_ids'])): c['cost'] for c in graph['values']}
        assignments = {o: [units[i]] if i < len(units) and (o, (units[i],)) in available else [] for i, o in enumerate(obs)}
        used = {u for group in assignments.values() for u in group}
        missing = sorted(set(units) - used)
        unexplained = [o for o in obs if not assignments[o]]
        objective = sum((available[o, tuple(group)] if group else request['unexplained_costs'][o] for o, group in assignments.items())) + sum((request['missing_costs'][u] for u in missing))

        def attempt(purpose, cost):
            return dict(purpose=purpose, status='optimal', raw_status=0, message='SYNTHETIC backend receipt', optimal=True, timed_out=False, objective=cost, mip_gap=0.0, dual_bound=cost)
        best = dict(objective=objective, assignments=assignments, unobserved=missing, unexplained=unexplained, certified=True)
        result = dict(best=best, alternatives=[], status='optimal', optimal=True, timed_out=False, top_k_certified=False, exhausted=False, identification_quotient='none', margins={o: dict(value=1.0, status='optimal', certified=True, alternative_objective=objective + 1) for o in obs}, attempts=[attempt('best', objective)] + [attempt('margin:' + o, objective + 1) for o in obs])
        methods[name] = dict(method=name, status='optimal', certified=True, timed_out=False, cost_convention='reduced' if name == 'B2' else 'fixed_distance', solver_result=result, backend_problem_sha256=canonical_digest(request), local=[], per_observation_status=[(o, 'certified_separated_uncalibrated') for o in obs])
    body = dict(status='completed', methods=methods, relative_missing_costs=prepared['relative_missing_costs'], candidate_diagnostics=_candidate_diagnostics(prepared['candidates'], methods, requests))
    envelope = dict(status='completed', timed_out=False, process_reaped=True, exit_code=0, input_id=public['input_id'], prediction_artifact_sha256='5' * 64, result=body)
    envelope['execution_receipt'] = _make_execution_receipt(raw, config, envelope, input_id=public['input_id'], prediction_artifact_sha256='5' * 64)
    return (envelope, raw, config)

def synthetic_checks():
    """Pure in-memory fixtures; these certificates are deliberately synthetic."""
    from copy import deepcopy
    from nmr_assignment.mapping import build_capacity_layout, FrozenCarrier

    def fixture(ambiguous=False, attachment=False):
        raw = json.dumps(dict(source_ref='synthetic', nucleus='1H', record_id='synthetic-record', smiles='CC', atom_targets=[1, 2], atom_target_mask=[1, 1]))
        binding = dict(source='synthetic', nucleus='1H', record_id='synthetic-record', structure_id=text_digest('CC'), source_sha256='1' * 64, row_sha256=text_digest(raw), policy_sha256='2' * 64, cohort_identity_manifest_sha256='3' * 64)
        family = [('A', 'B'), ('B', 'A')] if ambiguous else [('A', 'B')]
        lineage = dict(implementation_sha256='4' * 64, canonical_smiles='CC', baseline_graph=dict(atoms=[], bonds=[]), source_suppressed_H_by_parent={2: [3], 10: [11]}, target_suppressed_H_by_parent={2: [3], 10: [11]})
        proof = dict(graph_lineage_evidence_sha256=_lineage_digest(lineage), enumeration_truncated=False, parent_projection_rows=family)
        transport = dict(binding, complete=True, enumeration_truncated=False, graph_lineage_evidence=lineage, graph_lineage_evidence_sha256=_lineage_digest(lineage), completeness_evidence=proof, completeness_evidence_sha256=digest(proof), joint_maps=[dict(enumerate(v)) for v in family])
        states = [[('bin:0', (a,)), ('bin:1', (b,))] for a, b in family]
        snapshot = dict(canonical_smiles='CC', rdkit_version='synthetic', atoms=[], bonds=[])
        gold = dict(input_id='opaque-synthetic', binding=binding, source_raw_line=raw, joint_gold_parent_sets=states, transport=transport, scoreable=True, truth_basis='source_relative_current_serialization', reference_basis='source_asserted_encoded_graph', trust_basis='internal_source_consistency', trusted_experimental=False, baseline_structure_snapshot=snapshot, baseline_structure_snapshot_sha256=digest(snapshot))
        public = dict(input_id=gold['input_id'], smiles='CC', nucleus='1H', actual_conditions={}, observations=list(build_serialized_value_bins(raw).anonymous_payload()))
        layout = build_capacity_layout(dict(nucleus='1H', parent_mass={'A': 1, 'B': 1}, evidence_ids=['synthetic:counts'], isotope_count_verified=True, partition_hypothesis_id='synthetic'))
        ids = tuple((u.unit_id for u in layout.units))
        blocks = (ids,) if attachment else ()
        evidence = ('synthetic:attachment',) if attachment else ()
        predictions = FrozenCapacityPredictions(layout, tuple((FrozenCarrier('carrier' + str(i), uid, float(i + 1), 1.0, None, 'unknown', ('component' + str(i),)) for i, uid in enumerate(ids))), blocks, evidence)
        pp = dict(input_id=gold['input_id'], complete=True, baseline_structure_snapshot_sha256=gold['baseline_structure_snapshot_sha256'], prediction_payload_sha256=digest(asdict(predictions)), layout_sha256=digest(asdict(layout)), attachment_sha256=digest(dict(blocks=blocks, evidence_ids=evidence)), evidence_ids=['synthetic:prediction-lineage'], prediction_artifact_sha256='5' * 64)
        pred_receipt = dict(payload=pp, sha256=digest(pp))
        ap = dict(input_id=gold['input_id'], binding=binding, reference_payload_sha256=digest(_gold_payload(gold)), admitted=True, joint_nontrivial=True, transport_completeness_evidence_sha256=transport['completeness_evidence_sha256'], transport_implementation_sha256=lineage['implementation_sha256'], implementation_sha256='6' * 64, rule_version='synthetic-only', evidence_ids=['synthetic:final-admission'])
        admission = dict(payload=ap, sha256=digest(ap))
        execution, execution_payload, numeric_config = _synthetic_execution(public, predictions)
        args = dict(method='B1', roles=('synthetic-validation',), source_cohort_sha256='3' * 64, connectivity_sha256='7' * 64, batch_admission_receipt=admission, prediction_lineage_receipt=pred_receipt, execution_payload=execution_payload, approved_numeric_config=numeric_config)
        return (gold, public, predictions, execution, args)
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    def exact(bundle):
        return [r for r in bundle['rows'] if r.metric == 'exact_observation']

    def run(values, **overrides):
        gold, public, pred, execution, args = values
        return evaluate_record(gold, public, pred, execution, **dict(args, **overrides))
    values = fixture()
    gold, public, pred, execution, args = values
    bundle = run(values)
    check('unique_source_relative_reference', all((r.eligible and r.success for r in exact(bundle))))
    check('not_experimental_accuracy', not bundle['reference']['observation_admission']['bin:0']['core_evidence'])
    for attack in ('carrier', 'identity', 'negative_margin', 'timeout', 'best_flag', 'status', 'no_receipt'):
        from dataclasses import replace
        corrupted = deepcopy(execution)
        changed_pred = pred
        if attack == 'carrier':
            changed_pred = replace(pred, carriers=tuple((replace(c, center_ppm=c.center_ppm + 100) for c in pred.carriers)))
        elif attack == 'identity':
            corrupted.update(input_id='other-input', prediction_artifact_sha256='f' * 64, candidate_trace_sha256='e' * 64)
        elif attack == 'negative_margin':
            for margin in corrupted['result']['methods']['B1']['solver_result']['margins'].values():
                margin.update(value=-1, alternative_objective=-1)
        elif attack == 'timeout':
            corrupted['timed_out'] = True
        elif attack == 'best_flag':
            corrupted['result']['methods']['B1']['solver_result']['best']['certified'] = False
        elif attack == 'status':
            corrupted['result']['methods']['B1']['per_observation_status'][0] = ('bin:0', 'abstain_tie')
        else:
            corrupted.pop('execution_receipt')
        failed = evaluate_record(gold, public, changed_pred, corrupted, **args)
        check(attack + '_rejected_gold_retained', all((r.eligible and (not r.prediction_supported) for r in exact(failed))))
    failed = evaluate_record(gold, public, None, dict(status='worker_error', result=None), **args)
    check('failed_prediction_keeps_gold_denominator', len(exact(failed)) == 2 and all((r.eligible and (not r.success) for r in exact(failed))))
    incomplete = deepcopy(gold)
    incomplete['transport']['complete'] = False
    check('incomplete_reference_ineligible', all((not r.eligible for r in evaluate_record(incomplete, public, pred, execution, **args)['rows'])))
    check('final_admission_required', all((not r.eligible for r in run(values, batch_admission_receipt=None)['rows'])))

    def changed(values, centers):
        gold, public, pred, execution, args = values
        pred = replace(pred, carriers=tuple((replace(c, center_ppm=v) for c, v in zip(pred.carriers, centers))))
        execution, raw, config = _synthetic_execution(public, pred)
        pp = dict(args['prediction_lineage_receipt']['payload'], prediction_payload_sha256=digest(asdict(pred)))
        args = dict(args, execution_payload=raw, approved_numeric_config=config, prediction_lineage_receipt=dict(payload=pp, sha256=digest(pp)))
        return (gold, public, pred, execution, args)
    repeated = changed(fixture(ambiguous=True), (1.5, 10.0))
    b0 = run(repeated, method='B0')
    check('B0_reuses_unit_without_capacity_or_dummy_penalty', b0['execution_verification']['certified'] and all((r.success for r in b0['rows'] if r.metric == 'compatible_observation')) and (not next((r.success for r in b0['rows'] if r.metric == 'all_input_joint_compatible'))))
    tie = run(changed(fixture(), (1.5, 1.5)), method='B0')
    check('B0_complete_parent_ambiguous_tie_abstains', all((not r.prediction_supported for r in exact(tie))))
    same_gold, same_public, same_pred, _, same_args = changed(fixture(), (1.5, 1.5))
    same_layout = build_capacity_layout(dict(nucleus='1H', parent_mass={'A': 2}, evidence_ids=['synthetic:counts'], partition_evidence_ids=['synthetic:registry'], isotope_count_verified=True, partition_hypothesis_id='synthetic'), dict(groups=[dict(unit_id=u.unit_id, parents={'A': 1}, mass=1) for u in same_pred.layout.units]))
    same_pred = replace(same_pred, layout=same_layout)
    same_gold['transport']['joint_maps'] = [{0: 'A', 1: 'A'}]
    same_gold['transport']['completeness_evidence']['parent_projection_rows'] = [('A', 'A')]
    same_gold['transport']['completeness_evidence_sha256'] = digest(same_gold['transport']['completeness_evidence'])
    same_gold['joint_gold_parent_sets'] = [[('bin:0', ('A',)), ('bin:1', ('A',))]]
    ap = dict(same_args['batch_admission_receipt']['payload'], reference_payload_sha256=digest(_gold_payload(same_gold)), transport_completeness_evidence_sha256=same_gold['transport']['completeness_evidence_sha256'])
    pp = dict(same_args['prediction_lineage_receipt']['payload'], layout_sha256=digest(asdict(same_layout)), prediction_payload_sha256=digest(asdict(same_pred)))
    same_execution, raw, config = _synthetic_execution(same_public, same_pred)
    same_args.update(batch_admission_receipt=dict(payload=ap, sha256=digest(ap)), prediction_lineage_receipt=dict(payload=pp, sha256=digest(pp)), execution_payload=raw, approved_numeric_config=config)
    same_bundle = evaluate_record(same_gold, same_public, same_pred, same_execution, **dict(same_args, method='B0'))
    check('B0_complete_tie_parent_invariant_supported', all((r.success for r in exact(same_bundle))))
    attached = run(fixture(attachment=True))
    check('attachment_ambiguity_preserved', all((not r.prediction_supported for r in exact(attached))))
    check('unbound_margin_api_cannot_certify', not margin_scores(execution['result']['methods']['B1'], relative_tolerance=1e-07)['bin:0']['margin_certified'])
    compat = next((r for r in bundle['rows'] if r.metric == 'compatible_observation'))
    calargs = dict(cohort_sha256='3' * 64, source_sha256='1' * 64, label_sha256='8' * 64, rule_sha256='9' * 64, relative_tolerance=1e-07)
    calibration = calibration_record_from_evaluation(compat, bundle, **calargs)
    check('bound_margin_available_but_not_publication', calibration.margin_certified and (not bundle['metadata']['calibrated_publication']))
    compat = next((r for r in attached['rows'] if r.metric == 'compatible_observation'))
    check('ambiguous_parent_cannot_publish', not calibration_record_from_evaluation(compat, attached, **calargs).margin_certified)
    multigold = run(fixture(ambiguous=True))
    compat = next((r for r in multigold['rows'] if r.metric == 'compatible_observation'))
    check('gold_alternatives_do_not_block_unique_prediction', calibration_record_from_evaluation(compat, multigold, **calargs).margin_certified)
    return checks

def main():
    import argparse
    import time
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--receipt')
    args = parser.parse_args()
    if not args.self_test:
        raise SystemExit('Only --self-test IO is enabled; real evaluation needs root-authorized runner.')
    started = time.monotonic()
    checks = synthetic_checks()
    result = dict(schema='assignment_evaluation_adapter_synthetic_receipt_v1', status='SYNTHETIC_CHECKS_PASS', checks=checks, count=len(checks), exit=0, elapsed_seconds=time.monotonic() - started, adapter_sha256=text_digest(Path(__file__).read_text()), real_gold_rows_read=0, real_scores_computed=0, model_loads=0, forwards=0, missing_real_wrapper_fields=['final independently audited per-row batch admission receipt', 'prediction cache canonical structure snapshot/layout/attachment lineage receipt', 'explicit connectivity_sha256 from immutable cohort ledger; not present in driver gold row', 'frozen relative margin tolerance plus calibration API; raw separated status is not calibrated publication'])
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
if __name__ == '__main__':
    main()
