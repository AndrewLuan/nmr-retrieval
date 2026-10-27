"""功能概述：对冻结源相对参考与共享预测作有界、只读的前向误差和失败诊断。
主要职责：shared_forward 按完整结构联合关联计算单中心误差、固定混合权重偏差和
联合歧义界；candidate_diagnostics 只在完整候选与参考选择 receipt 下判断局部可表达性；
validate_witness 验证已有解的容量、候选、dummy 与成本，不搜索或求解；
objective_diagnostic 要求绑定同一候选图、result snapshot、tau 与实际执行凭证的证书，
重算 best/witness 成本并核验原 backend attempt；不从自报 certified 创建证据。admission_summary 与 baseline_actions
分别统计准入证据与算法动作，二者均不把大残差解释为标签错误或天然缺峰/重叠。
关系：消费 mapping.FrozenCapacityPredictions、BaselineResult 及调用者审过的 typed
receipt；不导入模型、solver 或数据加载器。完整性 receipt 的真实性仍由外部独审负责，
本模块检查绑定、引用、联合注入、attachment 置换闭合和证据形状，布尔字段不认证化学。
输入输出：ForwardTarget 已由结构证据去重为每个报告环境一条；缺原子级关联必须传
不完整 association。返回可序列化摘要，不改变推理、gold 或分母。一个记录应复用同一
DiagnosticBudget（默认 50000 checks、载入后 0.25 秒）；耗尽时返回 unknown，不补算。
无文件、网络、训练、前向、MILP、持久化或全局缓存副作用。
"""
from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
from math import fsum, isclose, isfinite
import re
from time import monotonic

from .mapping import FrozenCapacityPredictions


TRUTH_BASES = ("source_relative_current_serialization", "source_report_supported", "trusted_experimental")


def _text(value):
    if not isinstance(value, str) or not value:
        raise ValueError("nonempty text required")
    return value


def _ids(values, *, empty=True):
    if isinstance(values, (str, bytes)):
        raise ValueError("ID sequence required")
    values = tuple(_text(v) for v in values)
    if len(set(values)) != len(values) or (not empty and not values):
        raise ValueError("distinct IDs required")
    return values


def _number(value):
    if isinstance(value, (bool, str, bytes)):
        raise ValueError("finite number required")
    value = float(value)
    if not isfinite(value):
        raise ValueError("finite number required")
    return value


def _hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("SHA256 required")
    return value


def _bool(value):
    if type(value) is not bool:
        raise ValueError("explicit boolean required")
    return value


def payload_digest(payload):
    """Hash exact typed receipt payload; hash validity is not evidence authenticity."""
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
        allow_nan=False, ensure_ascii=False, default=lambda x: asdict(x) if is_dataclass(x) else list(x)).encode()).hexdigest()


@dataclass(frozen=True)
class DiagnosticBinding:
    record_id: str
    truth_basis: str
    nucleus: str
    task_semantics: str
    prediction_sha256: str
    reference_sha256: str
    config_sha256: str
    target_level: str = "parent"
    target_semantics: str = "set"

    def __post_init__(self):
        _text(self.record_id)
        if self.truth_basis not in TRUTH_BASES or self.nucleus not in ("1H", "13C"):
            raise ValueError("unknown diagnostic stratum")
        if self.task_semantics not in ("derived_serialized_value_bin", "natural_resonance"):
            raise ValueError("unknown observation semantics")
        if self.target_level not in ("atom", "parent", "group") or self.target_semantics not in ("set", "nuclear_multiset"):
            raise ValueError("unknown target projection semantics")
        for value in (self.prediction_sha256, self.reference_sha256, self.config_sha256):
            _hash(value)


@dataclass(frozen=True)
class PayloadReceipt:
    complete: bool
    payload_sha256: str
    evidence_ids: tuple

    def __post_init__(self):
        _bool(self.complete)
        _hash(self.payload_sha256)
        _ids(self.evidence_ids, empty=False)


class DiagnosticLimit(Exception):
    pass


class DiagnosticBudget:
    """Reuse one instance for all diagnostic calls on one already-loaded record."""
    def __init__(self, max_checks=50000, time_limit_seconds=.25):
        if type(max_checks) is not int or not 0 <= max_checks <= 50000:
            raise ValueError("max_checks must be in [0,50000]")
        limit = _number(time_limit_seconds)
        if not 0 < limit <= .25:
            raise ValueError("diagnostic time limit must be in (0,.25]")
        self.max_checks = max_checks
        self.checks = 0
        self.deadline = monotonic() + limit

    def step(self, count=1):
        self.checks += count
        if self.checks > self.max_checks or monotonic() >= self.deadline:
            raise DiagnosticLimit("diagnostic_budget")


def _budget(budget):
    return DiagnosticBudget() if budget is None else budget


def _binding(binding):
    if type(binding) is not DiagnosticBinding:
        raise ValueError("DiagnosticBinding required")
    return asdict(binding)


def _proof(receipt, payload, budget):
    budget.step()
    if receipt is None:
        return False
    if type(receipt) is not PayloadReceipt:
        raise ValueError("PayloadReceipt required")
    digest = payload_digest(payload)
    budget.step()
    if digest != receipt.payload_sha256:
        raise ValueError("receipt_payload_mismatch")
    return receipt.complete


def _unknown(reason, **values):
    return dict(status="unknown", reason_codes=(reason,), **values)


@dataclass(frozen=True)
class ForwardTarget:
    target_id: str
    ppm: float
    source_slot_ids: tuple
    evidence_ids: tuple

    def __post_init__(self):
        _text(self.target_id)
        _number(self.ppm)
        _ids(self.source_slot_ids, empty=False)
        _ids(self.evidence_ids, empty=False)


@dataclass(frozen=True)
class ForwardAssociation:
    targets: tuple
    # Each state is a tuple of (target_id, unit_id), a complete joint injection.
    states: tuple
    partition_hypothesis_id: str
    receipt: object = None

    def payload(self, binding):
        return dict(kind="forward_association", binding=_binding(binding),
            targets=self.targets, states=self.states,
            partition_hypothesis_id=self.partition_hypothesis_id)


def shared_forward(predictions, association, *, binding, budget=None):
    """Score once, before matching; ambiguous maps yield bounds, never chosen IDs."""
    b = _budget(budget)
    _binding(binding)
    if type(association) is not ForwardAssociation:
        raise ValueError("ForwardAssociation required")
    rows = []
    try:
        targets, slots = {}, set()
        for target in association.targets:
            b.step()
            if type(target) is not ForwardTarget or target.target_id in targets:
                raise ValueError("distinct typed forward targets required")
            b.step(len(target.source_slot_ids) + len(target.evidence_ids))
            if slots.intersection(target.source_slot_ids):
                raise ValueError("source_slot_reused_across_environments")
            slots.update(target.source_slot_ids)
            targets[target.target_id] = target
        fixed_count = len(targets)
        def fail(reason):
            return _unknown(reason, shared_forward=True, fixed_reference_targets=fixed_count,
                rows=tuple(dict(target_id=t, status="unknown", reason_codes=(reason,)) for t in targets),
                scalar_count=0, mixture_count=0, bounded_count=0)
        # Preflight the full state count before canonical payload hashing.
        for state in association.states:
            b.step(len(state))
        if not _proof(association.receipt, association.payload(binding), b):
            return fail("association_completeness_unknown")
        if predictions is None:
            return fail("prediction_missing")
        if type(predictions) is not FrozenCapacityPredictions:
            raise ValueError("FrozenCapacityPredictions required")
        if predictions.layout.nucleus != binding.nucleus or association.partition_hypothesis_id != predictions.layout.partition_hypothesis_id:
            raise ValueError("prediction_association_layout_mismatch")
        units = {u.unit_id: u for u in predictions.layout.units}
        states = set()
        for pairs in association.states:
            b.step(len(pairs))
            mapping = dict(pairs)
            if len(mapping) != len(pairs) or set(mapping) != set(targets):
                raise ValueError("joint_state_target_domain_invalid")
            values = _ids(mapping.values())
            if not set(values) <= set(units):
                raise ValueError("joint_state_unknown_unit")
            for tid, uid in mapping.items():
                if len(targets[tid].source_slot_ids) > units[uid].nucleus_mass:
                    raise ValueError("reported_source_slots_exceed_unit_nuclear_mass")
            states.add(tuple(sorted(mapping.items())))
        if not states:
            return fail("joint_state_missing")
        # Adjacent transpositions generate every independent attachment block.
        # Testing closure avoids enumerating a new factorial family.
        for state in states:
            for block in predictions.attachment_blocks:
                for left, right in zip(block, block[1:]):
                    b.step(len(state))
                    transformed = tuple((t, right if u == left else left if u == right else u) for t, u in state)
                    if transformed not in states:
                        return fail("attachment_joint_family_not_complete")
        carriers = {u: [] for u in units}
        for c in predictions.carriers:
            b.step()
            carriers[c.unit_id].append(c)
        state_errors = []
        unresolved_targets = set()
        for state in sorted(states):
            errors = {}
            for tid, uid in state:
                b.step(len(carriers[uid]))
                if units[uid].partition_status == "unresolved_parent_pool":
                    unresolved_targets.add(tid)
                    continue
                errors[tid] = fsum(c.mixture_weight * abs(c.center_ppm - targets[tid].ppm) for c in carriers[uid])
            state_errors.append(errors)
        for tid in targets:
            b.step(len(states))
            if tid in unresolved_targets:
                rows.append(dict(target_id=tid, status="unknown", reason_codes=("environment_partition_unknown",)))
                continue
            associated = {dict(state)[tid] for state in states}
            values = [errors[tid] for errors in state_errors]
            if len(associated) > 1:
                rows.append(dict(target_id=tid, status="ambiguity_bounds", lower=min(values), upper=max(values),
                                 identity_unique=False, reason_codes=()))
                continue
            uid = next(iter(associated))
            centers = {c.center_ppm for c in carriers[uid]}
            if len(centers) == 1:
                error = next(iter(centers)) - targets[tid].ppm
                rows.append(dict(target_id=tid, status="scalar", unit_id=uid,
                    signed_error=error, absolute_error=abs(error), identity_unique=True, reason_codes=()))
            else:
                rows.append(dict(target_id=tid, status="mixture", unit_id=uid,
                    mixture_expected_absolute_deviation=values[0], identity_unique=True, reason_codes=()))
        scalar = [r for r in rows if r["status"] == "scalar"]
        mixture = [r for r in rows if r["status"] == "mixture"]
        record_bound = None
        if fixed_count and not unresolved_targets:
            means = [fsum(errors.values()) / fixed_count for errors in state_errors]
            record_bound = dict(lower=min(means), upper=max(means), count=fixed_count,
                                metric="joint_distribution_AE_envelope")
        b.step()
        result = dict(status="complete", shared_forward=True, binding=_binding(binding),
            fixed_reference_targets=fixed_count, rows=tuple(rows),
            scalar_count=len(scalar), mixture_count=len(mixture),
            bounded_count=sum(r["status"] == "ambiguity_bounds" for r in rows),
            unknown_count=sum(r["status"] == "unknown" for r in rows),
            scalar_mae=fsum(r["absolute_error"] for r in scalar)/len(scalar) if scalar else None,
            scalar_bias=fsum(r["signed_error"] for r in scalar)/len(scalar) if scalar else None,
            mixture_mean=fsum(r["mixture_expected_absolute_deviation"] for r in mixture)/len(mixture) if mixture else None,
            record_joint_bound=record_bound, evidence_ids=association.receipt.evidence_ids,
            association_payload_sha256=association.receipt.payload_sha256,
            prediction_payload_sha256=payload_digest(predictions))
        result["artifact_sha256"] = payload_digest(result)
        b.step()
        return result
    except DiagnosticLimit:
        # Never publish a partial error table as a complete forward diagnostic.
        return _unknown("diagnostic_budget", shared_forward=True,
            fixed_reference_targets=len(association.targets), rows=())


@dataclass(frozen=True)
class TraceCandidate:
    observation_id: str
    unit_ids: tuple
    cost: float


@dataclass(frozen=True)
class CandidateTrace:
    method: str
    observation_ids: tuple
    unit_ids: tuple
    candidates: tuple
    # Missing cost is the actual solver cost (including A_u in raw convention).
    missing_costs: tuple
    unexplained_costs: tuple
    cost_convention: str
    receipt: object = None

    def payload(self, binding):
        return dict(kind="candidate_trace", binding=_binding(binding), method=self.method,
            observation_ids=self.observation_ids, unit_ids=self.unit_ids, candidates=self.candidates,
            missing_costs=self.missing_costs, unexplained_costs=self.unexplained_costs,
            cost_convention=self.cost_convention)


@dataclass(frozen=True)
class ReferenceChoices:
    observation_id: str
    # All legal reference-compatible PRE-gate unit sets for this single observation.
    unit_sets: tuple
    receipt: object = None

    def payload(self, binding, method):
        return dict(kind="local_reference_choices", binding=_binding(binding), method=method,
                    observation_id=self.observation_id, unit_sets=self.unit_sets)


def _trace(trace, binding, b):
    if trace is None:
        return None
    if type(trace) is not CandidateTrace or trace.method not in ("B0", "B1", "B2"):
        raise ValueError("typed candidate trace required")
    b.step(len(trace.observation_ids) + len(trace.unit_ids) + len(trace.missing_costs) + len(trace.unexplained_costs))
    obs, units = set(_ids(trace.observation_ids)), set(_ids(trace.unit_ids))
    index = {}
    for c in trace.candidates:
        b.step()
        if type(c) is not TraceCandidate:
            raise ValueError("TraceCandidate required")
        b.step(len(c.unit_ids))
        members = tuple(sorted(_ids(c.unit_ids, empty=False)))
        key = c.observation_id, members
        if c.observation_id not in obs or not set(members) <= units or len(members) > (2 if trace.method == "B2" else 1):
            raise ValueError("candidate_domain_invalid")
        if key in index:
            raise ValueError("duplicate_candidate")
        index[key] = _number(c.cost)
    missing, unexplained = dict(trace.missing_costs), dict(trace.unexplained_costs)
    if len(missing) != len(trace.missing_costs) or len(unexplained) != len(trace.unexplained_costs):
        raise ValueError("duplicate_dummy_ID")
    if trace.method == "B0":
        if missing or unexplained:
            raise ValueError("B0_has_no_dummies")
    elif set(missing) != units or set(unexplained) != obs:
        raise ValueError("dummy_domain_invalid")
    for cost in list(missing.values()) + list(unexplained.values()):
        b.step()
        _number(cost)
    expected_conventions = ("raw", "reduced") if trace.method == "B2" else ("fixed_distance",)
    if trace.cost_convention not in expected_conventions:
        raise ValueError("unknown_cost_convention")
    if not _proof(trace.receipt, trace.payload(binding), b):
        return None
    return index, missing, unexplained


def candidate_diagnostics(trace, choices, *, binding, budget=None):
    """Local existential compatibility only; no simultaneous feasibility claim."""
    b = _budget(budget)
    _binding(binding)
    try:
        data = _trace(trace, binding, b)
        if data is None or type(choices) is not ReferenceChoices:
            return _unknown("complete_candidate_and_reference_receipts_required")
        if not _proof(choices.receipt, choices.payload(binding, trace.method), b):
            return _unknown("reference_choices_incomplete")
        if choices.observation_id not in trace.observation_ids:
            raise ValueError("reference_observation_unknown")
        sets = set()
        for members in choices.unit_sets:
            b.step()
            members = tuple(sorted(_ids(members, empty=False)))
            if len(members) > (2 if trace.method == "B2" else 1) or not set(members) <= set(trace.unit_ids):
                raise ValueError("reference_choice_not_method_legal")
            sets.add(members)
        present = tuple(sorted(s for s in sets if (choices.observation_id, s) in data[0]))
        # For B0/B1, a complete graph cannot numerically gate a legal singleton.
        if trace.method in ("B0", "B1") and len(present) != len(sets):
            raise ValueError("ungated_method_complete_trace_missing_reference_candidate")
        return dict(status="complete", local_reference_representable=bool(sets),
            local_reference_candidate_emitted=bool(present),
            numerical_gate_excluded=bool(sets) and not present if trace.method == "B2" else False,
            compatible_candidate_count=len(present), global_feasibility="unknown",
            evidence_ids=trace.receipt.evidence_ids + choices.receipt.evidence_ids)
    except DiagnosticLimit:
        return _unknown("diagnostic_budget")


@dataclass(frozen=True)
class AssignmentCompatibility:
    assignments: tuple
    compatible: bool
    receipt: object = None

    def payload(self, binding):
        return dict(kind="whole_joint_assignment_compatibility", binding=_binding(binding),
                    assignments=self.assignments, compatible=self.compatible)


def _compatibility(proof, assignments, binding, b):
    if type(proof) is not AssignmentCompatibility:
        return None
    _bool(proof.compatible)
    if dict(proof.assignments) != assignments or len(dict(proof.assignments)) != len(proof.assignments):
        raise ValueError("compatibility_receipt_assignment_mismatch")
    if not _proof(proof.receipt, proof.payload(binding), b):
        return None
    return proof.compatible


def _assignment_cost(assignments, trace, data, b):
    """Validate one full assignment against the exact emitted graph, without search."""
    pairs = tuple(assignments.items()) if hasattr(assignments, "items") else tuple(assignments)
    assignment = dict(pairs)
    b.step(len(pairs))
    if len(assignment) != len(pairs) or set(assignment) != set(trace.observation_ids):
        raise ValueError("assignment_observation_domain_invalid")
    normalized, used, costs = {}, set(), []
    for oid, members in assignment.items():
        b.step()
        members = tuple(sorted(_ids(members)))
        normalized[oid] = members
        if used.intersection(members):
            return None, "capacity_reuse"
        used.update(members)
        if members:
            cost = data[0].get((oid, members))
            if cost is None:
                return None, "candidate_not_emitted"
            costs.append(cost)
        else:
            costs.append(data[2][oid])
    missing = tuple(sorted(set(trace.unit_ids) - used))
    b.step(len(missing))
    costs.extend(data[1][u] for u in missing)
    unexplained = tuple(sorted(o for o, us in normalized.items() if not us))
    return (normalized, missing, unexplained, _number(fsum(costs))), None


def validate_witness(assignments, trace, compatibility, *, binding, budget=None):
    """Check a caller-provided existing witness; never construct or search one."""
    b = _budget(budget)
    _binding(binding)
    try:
        data = _trace(trace, binding, b)
        if data is None:
            return _unknown("complete_candidate_receipt_required")
        if trace.method == "B0":
            return _unknown("global_witness_not_applicable_to_B0")
        checked, reason = _assignment_cost(assignments, trace, data, b)
        if checked is None:
            return dict(status="invalid_witness", reason_codes=(reason,), feasible=False)
        normalized, missing, unexplained, objective = checked
        compatible = _compatibility(compatibility, normalized, binding, b)
        if compatible is None:
            return _unknown("whole_joint_compatibility_receipt_required", feasible=True)
        b.step()
        result = dict(status="complete", feasible=True, compatible=compatible,
            assignments=tuple(sorted(normalized.items())), missing_unit_ids=missing,
            unexplained_observation_ids=unexplained,
            objective=objective, method=trace.method, cost_convention=trace.cost_convention,
            candidate_trace_payload_sha256=trace.receipt.payload_sha256,
            binding=_binding(binding), evidence_ids=trace.receipt.evidence_ids + compatibility.receipt.evidence_ids)
        result["validation_sha256"] = payload_digest(result)
        b.step()
        return result
    except DiagnosticLimit:
        return _unknown("diagnostic_budget")


def _solution_snapshot(solution, b):
    if solution is None:
        return None
    b.step(len(solution.assignments) + len(solution.unobserved) + len(solution.unexplained))
    return dict(objective=solution.objective,
        assignments=tuple(sorted((o, tuple(sorted(us))) for o, us in solution.assignments.items())),
        unobserved=tuple(sorted(solution.unobserved)), unexplained=tuple(sorted(solution.unexplained)),
        certified=solution.certified)


def _result_snapshot(result, b):
    """Exact solver/certification inputs consumed here, including all backend attempts."""
    raw = result.solver_result
    b.step(len(raw.margins) + len(raw.attempts) + len(raw.alternatives))
    margins = tuple((o, dict(value=m.value, status=m.status, certified=m.certified,
                            alternative_objective=m.alternative_objective))
                    for o, m in sorted(raw.margins.items()))
    attempts = tuple({k: getattr(a, k) for k in (
        "purpose", "status", "raw_status", "message", "optimal", "timed_out",
        "objective", "mip_gap", "dual_bound")} for a in raw.attempts)
    return dict(method=result.method, status=result.status, cost_convention=result.cost_convention,
        certified=result.certified, timed_out=result.timed_out,
        solver=dict(status=raw.status, optimal=raw.optimal, timed_out=raw.timed_out,
            identification_quotient=raw.identification_quotient, top_k_certified=raw.top_k_certified,
            exhausted=raw.exhausted, best=_solution_snapshot(raw.best, b),
            alternatives=tuple(_solution_snapshot(a, b) for a in raw.alternatives),
            margins=margins, attempts=attempts))


def result_snapshot_digest(result, *, budget=None):
    """For an audited execution adapter; computing this hash NEVER issues a certificate."""
    b = _budget(budget)
    digest = payload_digest(_result_snapshot(result, b))
    b.step()
    return digest


@dataclass(frozen=True)
class SolverResultCertificate:
    candidate_trace_payload_sha256: str
    result_payload_sha256: str
    tie_relative_tolerance: float
    reduced_objective_offset: float
    solver_implementation_sha256: str
    execution_receipt_sha256: str
    # Issued only by the audited execution adapter, never by objective_diagnostic.
    receipt: object = None

    def __post_init__(self):
        for value in (self.candidate_trace_payload_sha256, self.result_payload_sha256,
                      self.solver_implementation_sha256, self.execution_receipt_sha256):
            _hash(value)
        if _number(self.tie_relative_tolerance) < 0 or _number(self.reduced_objective_offset) < 0:
            raise ValueError("nonnegative_frozen_tau_and_offset_required")

    def payload(self, binding):
        return dict(kind="audited_best_and_forbidden_best_margins", binding=_binding(binding),
            candidate_trace_payload_sha256=self.candidate_trace_payload_sha256,
            result_payload_sha256=self.result_payload_sha256,
            tie_relative_tolerance=self.tie_relative_tolerance,
            reduced_objective_offset=self.reduced_objective_offset,
            solver_implementation_sha256=self.solver_implementation_sha256,
            execution_receipt_sha256=self.execution_receipt_sha256)


def _cost_equal(first, second):
    # Arithmetic consistency tolerance, not a chemical gate or selection tie rule.
    return isclose(_number(first), _number(second), rel_tol=1e-9, abs_tol=1e-9)


def verify_solver_result(result, trace, result_certificate, *, binding, budget=None):
    """Shared by evaluation and attribution: verify existing execution, never solve."""
    b = _budget(budget)
    _binding(binding)
    try:
        if type(result_certificate) is not SolverResultCertificate or trace is None:
            return _unknown("same_trace_execution_certificate_required")
        data = _trace(trace, binding, b)
        if data is None:
            return _unknown("complete_candidate_receipt_required")
        trace_sha = trace.receipt.payload_sha256
        if result_certificate.candidate_trace_payload_sha256 != trace_sha:
            raise ValueError("candidate_trace_binding_mismatch")
        if not _proof(result_certificate.receipt, result_certificate.payload(binding), b):
            return _unknown("execution_certificate_incomplete")
        if trace.cost_convention != "raw" and result_certificate.reduced_objective_offset != 0:
            raise ValueError("nonraw_objective_offset_must_be_zero")
        raw = getattr(result, "solver_result", None)
        best = getattr(raw, "best", None)
        if raw is None or best is None:
            return _unknown("certified_best_missing")
        try:
            snapshot = result_snapshot_digest(result, budget=b)
        except (AttributeError, TypeError):
            return _unknown("complete_solver_result_snapshot_required")
        if snapshot != result_certificate.result_payload_sha256:
            raise ValueError("solver_result_certificate_binding_mismatch")
        if result.method != trace.method or result.cost_convention != trace.cost_convention:
            raise ValueError("baseline_trace_method_mismatch")
        if (result.certified is not True or result.timed_out is not False
                or raw.optimal is not True or raw.timed_out is not False or best.certified is not True):
            return _unknown("uncertified_or_timed_out_baseline")
        checked, reason = _assignment_cost(best.assignments, trace, data, b)
        if checked is None:
            raise ValueError("best_trace_" + reason)
        assignments, missing, unexplained, objective = checked
        if set(_ids(best.unobserved)) != set(missing) or set(_ids(best.unexplained)) != set(unexplained):
            raise ValueError("best_trace_dummy_partition_mismatch")
        if not _cost_equal(best.objective, objective):
            raise ValueError("best_objective_trace_mismatch")
        # k-best incumbents also belong to the same problem; they are never used
        # as unverified evidence from another graph.
        for alternate in raw.alternatives:
            checked_alt, reason = _assignment_cost(alternate.assignments, trace, data, b)
            if checked_alt is None:
                raise ValueError("alternative_trace_" + reason)
            _, am, au, ao = checked_alt
            if (set(_ids(alternate.unobserved)) != set(am) or set(_ids(alternate.unexplained)) != set(au)
                    or not _cost_equal(alternate.objective, ao)):
                raise ValueError("alternative_trace_cost_or_dummy_mismatch")
        attempts = {}
        for attempt in raw.attempts:
            b.step()
            if attempt.purpose in attempts:
                raise ValueError("duplicate_solver_attempt_purpose")
            attempts[attempt.purpose] = attempt
        def certified_attempt(purpose, cost):
            attempt = attempts.get(purpose)
            return (attempt is not None and attempt.optimal is True and attempt.timed_out is False
                and attempt.status == "optimal" and attempt.raw_status == 0 and attempt.objective is not None
                and _cost_equal(attempt.objective, cost))
        if not certified_attempt("best", objective):
            return _unknown("best_backend_certificate_missing_or_inconsistent")
        if set(raw.margins) - set(assignments):
            raise ValueError("margin_observation_domain_invalid")
        offset, tolerance = result_certificate.reduced_objective_offset, result_certificate.tie_relative_tolerance
        determinate, scores, reasons = {}, {}, {}
        for oid in assignments:
            b.step()
            margin = raw.margins.get(oid)
            determinate[oid] = False
            scores[oid] = dict(margin=None, margin_certified=False, margin_tolerance=0.)
            reasons[oid] = "tie_or_unverified_global_selection"
            if (margin is None or margin.certified is not True or margin.status != "optimal"
                    or margin.value is None or margin.alternative_objective is None):
                continue
            alt, gap = _number(margin.alternative_objective), _number(margin.value)
            if (gap < 0 or alt < objective or not certified_attempt("margin:" + oid, alt)
                    or not _cost_equal(gap, alt - objective)):
                reasons[oid] = "margin_backend_certificate_missing_or_inconsistent"
                continue
            tau = tolerance * max(1., abs(objective-offset), abs(alt-offset))
            scores[oid] = dict(margin=gap, margin_certified=True, margin_tolerance=tau)
            determinate[oid] = gap > tau
            reasons[oid] = "certified_separated_uncalibrated" if gap > tau else "abstain_tie"
        b.step()
        return dict(status="complete", certified=True, assignments=assignments, objective=objective,
            observation_determinate=determinate, margin_scores=scores, observation_reasons=reasons,
            candidate_trace_payload_sha256=trace_sha, result_payload_sha256=snapshot,
            execution_receipt_sha256=result_certificate.execution_receipt_sha256)
    except DiagnosticLimit:
        return _unknown("diagnostic_budget")


def objective_diagnostic(result, best_compatibility, witness, *, binding,
                         trace=None, result_certificate=None, budget=None):
    """Only attribute a verified same-trace separated optimum with a feasible witness.

    Certificates originate in the actual audited execution adapter. Hashing a
    self-reported optimal flag does not independently prove MILP optimality.
    """
    b = _budget(budget)
    _binding(binding)
    try:
        b.step()
        if (not witness or witness.get("status") != "complete" or witness.get("feasible") is not True
                or witness.get("compatible") is not True):
            return _unknown("validated_reference_witness_required")
        if type(result_certificate) is not SolverResultCertificate or trace is None:
            return _unknown("same_trace_execution_certificate_required")
        original = dict(witness)
        digest = original.pop("validation_sha256", None)
        if digest != payload_digest(original) or witness.get("binding") != _binding(binding):
            raise ValueError("witness_validation_binding_mismatch")
        if trace.receipt is None or witness.get("candidate_trace_payload_sha256") != trace.receipt.payload_sha256:
            raise ValueError("candidate_trace_binding_mismatch")
        verified = verify_solver_result(result, trace, result_certificate, binding=binding, budget=b)
        if verified["status"] != "complete":
            return verified
        if trace.method == "B0":
            return _unknown("global_objective_not_applicable_to_B0")
        if witness["method"] != trace.method or witness["cost_convention"] != trace.cost_convention:
            raise ValueError("baseline_witness_trace_method_mismatch")
        data = _trace(trace, binding, b)
        checked, reason = _assignment_cost(witness["assignments"], trace, data, b)
        if checked is None:
            raise ValueError("witness_trace_" + reason)
        _, missing, unexplained, wobjective = checked
        if (tuple(witness["missing_unit_ids"]) != missing or tuple(witness["unexplained_observation_ids"]) != unexplained
                or not _cost_equal(witness["objective"], wobjective)):
            raise ValueError("witness_trace_cost_or_dummy_mismatch")
        compatible = _compatibility(best_compatibility, verified["assignments"], binding, b)
        if compatible is None:
            return _unknown("best_whole_joint_compatibility_receipt_required")
        if compatible:
            return dict(status="complete", certified_incompatible_choice_with_reference_witness=False)
        if not verified["assignments"] or not all(verified["observation_determinate"].values()):
            return _unknown("tie_or_unverified_global_selection")
        offset, tolerance = result_certificate.reduced_objective_offset, result_certificate.tie_relative_tolerance
        objective = verified["objective"]
        difference = wobjective - objective
        if difference <= tolerance * max(1., abs(wobjective-offset), abs(objective-offset)):
            return _unknown("witness_objective_not_separated_or_certificate_contradiction")
        b.step()
        return dict(status="complete", certified_incompatible_choice_with_reference_witness=True,
            best_objective=objective, witness_objective=wobjective, witness_minus_best=difference,
            tau_by_observation={o:s["margin_tolerance"] for o,s in verified["margin_scores"].items()},
            candidate_trace_payload_sha256=verified["candidate_trace_payload_sha256"],
            result_payload_sha256=verified["result_payload_sha256"],
            execution_receipt_sha256=result_certificate.execution_receipt_sha256,
            evidence_ids=witness["evidence_ids"] + best_compatibility.receipt.evidence_ids + result_certificate.receipt.evidence_ids,
            interpretation="frozen_decision_rule_diagnostic_not_causal_attribution")
    except DiagnosticLimit:
        return _unknown("diagnostic_budget")


@dataclass(frozen=True)
class AdmissionEntry:
    record_id: str
    admitted: bool
    classification: str
    reason_codes: tuple
    evidence_ids: tuple


def admission_summary(entries, *, budget=None):
    """Only upstream source-audit entries; no predictions or residuals accepted."""
    b = _budget(budget)
    counts, reasons, seen = Counter(), Counter(), set()
    try:
        for row in entries:
            b.step()
            if type(row) is not AdmissionEntry or row.record_id in seen:
                raise ValueError("distinct typed admission entries required")
            _text(row.record_id)
            seen.add(row.record_id)
            _bool(row.admitted)
            _text(row.classification)
            _ids(row.reason_codes)
            _ids(row.evidence_ids, empty=False)
            counts["admitted" if row.admitted else "not_admitted"] += 1
            counts["class:" + row.classification] += 1
            reasons.update(row.reason_codes)
        b.step()
        return dict(status="complete", cohort_record_count=len(seen), counts=dict(counts),
                    reason_counts=dict(reasons), reasons_nonexclusive=True)
    except DiagnosticLimit:
        return _unknown("diagnostic_budget")


def baseline_actions(result, *, observation_ids, unit_ids, budget=None):
    """Algorithm actions only; chosen dummies do not establish physical missingness."""
    b = _budget(budget)
    try:
        b.step(len(observation_ids) + len(unit_ids))
        obs, units = set(_ids(observation_ids)), set(_ids(unit_ids))
        if result.method not in ("B0", "B1", "B2"):
            raise ValueError("unknown baseline")
        out = dict(status="complete", method=result.method, baseline_status=result.status,
            certified=bool(result.certified), timed_out=bool(result.timed_out),
            chosen_missing_units=None, chosen_unexplained_observations=None,
            natural_missing_status="unknown", natural_overlap_status="unknown")
        if result.method == "B0":
            out["dummy_semantics"] = "not_applicable"
            return out
        raw = result.solver_result
        best = None if raw is None else raw.best
        if best is None:
            out["action_status"] = "no_incumbent"
            return out
        if set(best.assignments) != obs:
            raise ValueError("best_observation_domain_invalid")
        used = set()
        for members in best.assignments.values():
            b.step()
            values = set(_ids(members))
            if not values <= units or values.intersection(used):
                raise ValueError("best_capacity_domain_invalid")
            used.update(values)
        missing, unexplained = set(_ids(best.unobserved)), set(_ids(best.unexplained))
        if missing != units - used or unexplained != {o for o, us in best.assignments.items() if not us}:
            raise ValueError("best_dummy_partition_invalid")
        out.update(chosen_missing_units=len(missing), chosen_unexplained_observations=len(unexplained),
                   action_status="certified" if result.certified and not result.timed_out else "uncertified_incumbent")
        b.step()
        return out
    except DiagnosticLimit:
        return _unknown("diagnostic_budget")
