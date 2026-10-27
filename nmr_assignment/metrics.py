"""功能概述：对冻结归属结果作分轨评价，保持外部审核确定的 reference/gold 分母。
evaluate_assignment 先独立冻结exact/compatibility gold准入：缺完整gold映射不进分母，
完整多个备选仅进compatibility，目标层投影唯一才进exact。随后逐峰用同一 JointMapping
的单峰投影检查预测支持度；完整gold下的预测失败仍留分母。联合指标仅比较
whole tuple 备选，禁止逐峰独立交集拼成整份成功；未知与超时不删除已准入分母。
baseline_assignment 读取 BaselineResult 的最佳解或 B0唯一局部最佳，不使用 raw Top3
去重推断 chemical quotient。summarize 分层统计 record/connectivity/observation 支持；
paired_gain 显式按 connectivity 整簇重采样，种子和重复数由调用方提供，不拟合校准。
reference_digest 绑定规范化 whole reference；raw_topk_unit_hit_bounds 只给完整原始
单位排名的命中上下界，不能认证 chemical quotient Top3。
代码库关系：复用 mapping.project_assignment/metric_eligibility；兼容 baselines 输出，
不导入模型、求解器、训练或真实数据。EvaluationRow 为不可变的单项评价对象。
输入边界：source-relative/source-report 分母由外部冻结 admitted+rule_version+
implementation_sha256+admission_receipt_sha256+evidence_ids 给出；trusted_experimental
另执行核心 gold eligibility。格式校验只检查 receipt 形状，不认证证据真实性、来源
转换、实验正确性或 reviewed boolean。三种 truth_basis 与 derived/natural 任务不混用。
中心残差不参与 gold 判定或失败归因。失败标签必须带外部 evidence 字符串，缺失保留
unknown，可多标签。all_input_reported_peaks_exact 只谈输入峰；strict_full_spectrum
另需可信实验测量完整性与窗口证据。无文件、网络、拟合、参数冻结或全局缓存副作用。
"""
from collections import defaultdict
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from math import floor, ceil
from random import Random
import re
from .mapping import project_assignment, metric_eligibility, ProjectedAssignment

TRUTH_BASES = ("source_relative_current_serialization", "source_report_supported",
               "trusted_experimental")
TASKS = ("derived_serialized_value_bin", "natural_resonance")
GROUP_FIELDS = ("truth_basis", "nucleus", "task_semantics", "target_level",
                "target_semantics", "baseline")


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty text required")
    return value


def _proofs(values):
    if isinstance(values, str):
        raise ValueError("evidence IDs require a sequence")
    values = tuple(values)
    if not values or len(set(values)) != len(values):
        raise ValueError("explicit evidence locators required")
    for value in values:
        _text(value)
    return values


def _bool(value):
    if type(value) is not bool:
        raise ValueError("explicit boolean required")
    return value


def _context(context):
    result = {k: _text(context[k]) for k in GROUP_FIELDS + ("record_id", "connectivity_id")}
    if (result["truth_basis"] not in TRUTH_BASES or result["task_semantics"] not in TASKS
            or result["nucleus"] not in ("1H", "13C")
            or result["target_level"] not in ("atom", "parent", "group")
            or result["target_semantics"] not in ("set", "nuclear_multiset")
            or result["baseline"] not in ("B0", "B1", "B2")):
        raise ValueError("invalid evaluation stratum")
    return result


def _admission(entry):
    """Validate audit receipt shape; never manufacture an experimental proof."""
    admitted = _bool(entry["admitted"])
    _text(entry["rule_version"])
    for key in ("implementation_sha256", "admission_receipt_sha256"):
        if not isinstance(entry[key], str) or not re.fullmatch("[0-9a-f]{64}", entry[key]):
            raise ValueError("audit SHA256 requires 64 lowercase hex characters")
    _proofs(entry["evidence_ids"])
    return admitted


def _targets(values, semantics):
    if isinstance(values, str):
        raise ValueError("targets require a sequence")
    values = tuple(_text(v) for v in values)
    return tuple(sorted(set(values) if semantics == "set" else values))


def _variant(values, semantics):
    return tuple(sorted((obs, _targets(target, semantics)) for obs, target in values.items()))



def reference_digest(whole_joint_targets, *, target_semantics):
    """Hash normalized whole alternatives; a digest is not a completeness proof."""
    if target_semantics not in ("set", "nuclear_multiset"):
        raise ValueError("explicit target semantics required")
    states = sorted(set(_variant(v, target_semantics) for v in whole_joint_targets))
    return sha256(json.dumps(states, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _normalized_projection(projection, semantics):
    # 每个完整map单独投影；只合并该任务语义下相同的whole状态，绝不跨峰拼候选。
    variants = tuple(sorted(set(_variant(dict(v), semantics) for v in projection.variants)))
    observations = tuple(o for o, _ in variants[0]) if variants else ()
    exact = tuple((o, projection.mapping_complete and
                   len({dict(v)[o] for v in variants}) == 1) for o in observations)
    return replace(projection, variants=variants, per_observation_exact=exact,
                   joint_exact=projection.mapping_complete and len(variants) == 1)


def _completeness(reference, semantics):
    proof = reference["gold_completeness_receipt"]
    _proofs(proof["evidence_ids"])
    for key in ("receipt_sha256", "whole_joint_targets_sha256"):
        if not isinstance(proof[key], str) or not re.fullmatch("[0-9a-f]{64}", proof[key]):
            raise ValueError("gold completeness receipt requires SHA256 binding")
    if proof["proof_kind"] not in ("complete_enumeration", "complete_projection_quotient"):
        raise ValueError("unsupported completeness proof kind")
    if proof["whole_joint_targets_sha256"] != reference_digest(
            reference["whole_joint_targets"], target_semantics=semantics):
        raise ValueError("gold completeness receipt is not bound to reference states")
    complete = _bool(reference["joint_reference_complete"])
    if _bool(proof["complete"]) != complete:
        raise ValueError("gold completeness assertions disagree")
    return complete


def _failure_labels(entries):
    if not entries:
        return ("unknown",)
    result = []
    for entry in entries:
        result.append(_text(entry["label"]))
        _proofs(entry["evidence_ids"])
    return tuple(dict.fromkeys(result))


@dataclass(frozen=True)
class EvaluationRow:
    context: tuple
    metric: str
    observation_id: object
    eligible: bool
    prediction_supported: bool
    success: bool
    reason_codes: tuple
    failure_labels: tuple
    eligibility_reason_codes: tuple = ()
    eligibility_determinator: tuple = ()

    def __post_init__(self):
        for value in (self.eligible, self.prediction_supported, self.success):
            _bool(value)
        if self.success and not (self.eligible and self.prediction_supported):
            raise ValueError("success requires fixed eligibility and prediction support")


def baseline_assignment(result):
    """Read only best output; returns assignment and explicit pipeline status.

    A tied B0 local decision becomes unassigned. No alternatives/Top3 are promoted
    to chemical quotient support. Failed or timed-out best is retained for audit,
    but pipeline status prevents scoring it as a certified success.
    """
    status = dict(status=result.status, certified=result.certified,
                  timed_out=result.timed_out, reuse_semantics=result.reuse_semantics,
                  observation_determinate=dict(getattr(result, "observation_determinate", {})),
                  observation_alternatives=dict(getattr(result, "observation_alternatives", {})),
                  observation_alternatives_complete={})
    if result.method == "B0":
        assignment = {}
        for row in result.local:
            block = tuple(getattr(row, "minimum_tie_block", ()))
            complete = getattr(row, "minimum_tie_complete", False) is True
            status["observation_alternatives_complete"][row.observation_id] = complete
            if block and complete:
                status["observation_alternatives"][row.observation_id] = block
                assignment[row.observation_id] = (block[0],)
            else:
                assignment[row.observation_id] = ((row.local_top3[0][0],)
                    if row.best_unique and row.local_top3 else ())
    else:
        raw = result.solver_result
        best = None if raw is None else raw.best
        assignment = None if best is None else dict(best.assignments)
        if best is not None and not best.certified:
            status["certified"] = False
    return assignment, status


def evaluate_assignment(assignment, joint_mapping, *, context, reference, pipeline_status):
    """Return rows for exact/compatible observations, all-input and strict full spectrum.

    reference: input_observation_ids; whole_joint_targets=[{obs:[target IDs]}];
    observation_admission={obs:audit receipt plus core_evidence};
    joint_reference_complete; joint_nontrivial; joint_evidence_ids;
    gold_completeness_receipt={complete,receipt_sha256,whole_joint_targets_sha256,
    proof_kind:complete_enumeration|complete_projection_quotient,evidence_ids};
    strict_full_spectrum_evidence (core flags/locators or an empty dict).
    Each whole variant has the same known-observation domain; unknown observations
    may be absent. An admitted observation must have a nonempty reference target.
    pipeline_status carries certified,timed_out,status,reuse_semantics and per-obs
    observation_determinate (absent means abstain); B0 may also carry complete
    observation_alternatives minimum unit blocks and observation_alternatives_complete.
    The evaluator tests every tied unit under every complete joint map. B1/B2
    determinate is the external certified gap>tau decision, never assumed from best.
    Failure evidence is optional {obs:[{label,evidence_ids}]} and never inferred.
    """
    c = _context(context)
    obs = tuple(reference["input_observation_ids"])
    if not obs or len(obs) != len(set(obs)):
        raise ValueError("distinct nonempty input observations required")
    for name in obs:
        _text(name)
    admissions = reference["observation_admission"]
    if set(admissions) != set(obs):
        raise ValueError("admission must cover all input observations, including exclusions")
    admitted = {o: _admission(admissions[o]) for o in obs}
    complete = _bool(reference["joint_reference_complete"])
    nontrivial = _bool(reference["joint_nontrivial"])
    _proofs(reference["joint_evidence_ids"])
    semantics = c["target_semantics"]
    complete = _completeness(reference, semantics)
    gold = tuple(sorted(set(_variant(v, semantics) for v in reference["whole_joint_targets"])))
    domains = {tuple(o for o, _ in v) for v in gold}
    if len(domains) > 1 or any(set(o for o, _ in v)-set(obs) for v in gold):
        raise ValueError("whole-reference variants must share one known input domain")
    local_gold = {o: {dict(v)[o] for v in gold if o in dict(v)} for o in obs}
    for o in obs:
        if admitted[o] and (not local_gold[o] or any(not t for t in local_gold[o])):
            raise ValueError("admitted observation needs known nonempty reference targets")
    # Gold gates are frozen from reference evidence before examining any prediction.
    gold_only_projection = ProjectedAssignment(c["target_level"], (), (), False, False,
                                               (), "global_exclusive", ())
    exact_gold, compatibility_gold, exact_gold_reasons, compatibility_gold_reasons = {}, {}, {}, {}
    for o in obs:
        common_reasons = []
        if not admitted[o]:
            common_reasons.append("gold:not_admitted_by_frozen_audit")
        if not complete:
            common_reasons.append("gold:mapping_family_incomplete")
        if not local_gold[o]:
            common_reasons.append("gold:reference_unknown")
        exact_reasons = list(common_reasons)
        compatibility_reasons = list(common_reasons)
        if len(local_gold[o]) != 1:
            exact_reasons.append("gold:advertised_target_not_unique")
        if not nontrivial:
            compatibility_reasons.append("gold:joint_constraint_not_informative")
        if c["truth_basis"] == "trusted_experimental":
            exact_gate = metric_eligibility(admissions[o].get("core_evidence", {}),
                                             gold_only_projection, metric="exact_"+c["target_level"])
            compatibility_gate = metric_eligibility(admissions[o].get("core_evidence", {}),
                                                     gold_only_projection, metric="compatibility")
            exact_reasons.extend(code for code in exact_gate.reason_codes if code.startswith("gold:"))
            compatibility_reasons.extend(code for code in compatibility_gate.reason_codes if code.startswith("gold:"))
        exact_gold[o], compatibility_gold[o] = not exact_reasons, not compatibility_reasons
        exact_gold_reasons[o] = tuple(exact_reasons) or ("gold:complete_unique_advertised_reference",)
        compatibility_gold_reasons[o] = tuple(compatibility_reasons) or ("gold:complete_informative_joint_reference",)
    certified = _bool(pipeline_status["certified"])
    timed_out = _bool(pipeline_status["timed_out"])
    _text(pipeline_status["status"])
    reuse = pipeline_status["reuse_semantics"]
    if reuse not in ("global_exclusive", "independent_local"):
        raise ValueError("explicit reuse semantics required")
    ready = certified and not timed_out and joint_mapping is not None
    if assignment is None:
        assignment = {}
    if set(assignment)-set(obs):
        raise ValueError("prediction references a non-input observation")
    assignment = {o: tuple(assignment.get(o, ())) for o in obs}
    determinate = pipeline_status.get("observation_determinate", {})
    if any(type(value) is not bool for value in determinate.values()):
        raise ValueError("per-observation determinate status must be boolean")
    alternatives = pipeline_status.get("observation_alternatives", {})
    alternatives_complete = pipeline_status.get("observation_alternatives_complete", {})
    metric = "exact_" + c["target_level"]
    failure = reference.get("failure_evidence", {})
    if set(failure)-set(obs):
        raise ValueError("failure evidence references unknown observation")
    unknown_projection = ProjectedAssignment(c["target_level"], (), (), False, False, (), reuse, ())
    rows = []
    eligible_exact = {}
    supported_exact = {}
    b0_all_ties_invariant = True
    def row(name, observation, eligible, supported, success, reasons=(), gold_reasons=()):
        labels = _failure_labels(failure.get(observation, ())) if observation else ("unknown",)
        return EvaluationRow(tuple(c.items()), name, observation, bool(eligible),
                             bool(supported), bool(success), tuple(reasons),
                             () if success else labels, tuple(gold_reasons),
                             (("rule_version","metric-gold-gates-v2"),
                              ("truth_basis",c["truth_basis"]),
                              ("target_level",c["target_level"]),
                              ("target_semantics",semantics),
                              ("reference_sha256",reference["gold_completeness_receipt"]["whole_joint_targets_sha256"]),
                              ("completeness_receipt_sha256",reference["gold_completeness_receipt"]["receipt_sha256"]),
                              ("admission_receipt_sha256",admissions[observation]["admission_receipt_sha256"]
                               if observation is not None else tuple(admissions[o]["admission_receipt_sha256"] for o in obs))))
    for o in obs:
        projection = None if joint_mapping is None else project_assignment(
            {o: assignment[o]}, joint_mapping, reuse_semantics=reuse)
        local_determinate = determinate.get(o, False)
        block_complete = True
        if c["baseline"] == "B0" and o in alternatives:
            block = tuple(alternatives[o])
            block_complete = alternatives_complete.get(o) is True
            if not block or len(set(block)) != len(block):
                raise ValueError("B0 minimum block must contain distinct unit IDs")
            if joint_mapping is not None and block_complete:
                projections = [project_assignment({o:(unit,)}, joint_mapping,
                               reuse_semantics=reuse) for unit in block]
                projection = replace(projections[0], variants=tuple(
                    v for p in projections for v in p.variants))
                projection = _normalized_projection(projection, semantics)
                local_determinate = projection.joint_exact
            else:
                local_determinate = False
        if projection is not None:
            projection = _normalized_projection(projection, semantics)
        if c["baseline"] == "B0" and not local_determinate:
            b0_all_ties_invariant = False
        core = metric_eligibility(admissions[o].get("core_evidence", {}),
                                  projection or unknown_projection, metric=metric)
        eligible = exact_gold[o]
        eligible_exact[o] = eligible
        supported = ready and core.prediction_supported and local_determinate
        supported_exact[o] = supported
        predicted = set() if projection is None else {
            _targets(dict(v)[o], semantics) for v in projection.variants}
        exact = (eligible and supported and len(predicted) == len(local_gold[o]) == 1
                 and predicted == local_gold[o])
        reasons = ("pipeline:timeout",) if timed_out else ()
        if not supported:
            reasons += ("prediction:unsupported_or_uncertified",)
        rows.append(row("exact_observation", o, eligible, supported, exact, reasons, exact_gold_reasons[o]))
        # Compatibility permits ambiguity, but must retain a complete mapping and a
        # nontrivial externally constrained reference. It never substitutes for exact.
        compat_support = (ready and projection is not None and projection.mapping_complete
                          and projection.level == c["target_level"])
        compat_eligible = compatibility_gold[o]
        compat_support = compat_support and block_complete
        compat = compat_eligible and compat_support and bool(predicted & local_gold[o])
        rows.append(row("compatible_observation", o, compat_eligible, compat_support, compat, reasons, compatibility_gold_reasons[o]))
    full = None if joint_mapping is None else project_assignment(
        assignment, joint_mapping, reuse_semantics=reuse)
    if full is not None:
        full = _normalized_projection(full, semantics)
    predicted_joint = set() if full is None else {
        _variant(dict(v), semantics) for v in full.variants}
    gold_full = {v for v in gold if set(dict(v)) == set(obs)}
    joint_match = bool(predicted_joint & gold_full)
    all_eligible = all(eligible_exact.values()) and complete and bool(gold_full)
    all_support = all(supported_exact.values()) and ready and full is not None and full.mapping_complete
    all_exact = (all_eligible and all_support and len(predicted_joint) == len(gold_full) == 1
                 and joint_match)
    rows.append(row("all_input_reported_peaks_exact", None, all_eligible, all_support, all_exact,
                    gold_reasons=("gold:all_inputs_complete_unique_reference",) if all_eligible
                    else ("gold:some_input_not_exact_eligible",)))
    joint_eligible = all(compatibility_gold.values()) and complete and bool(gold_full)
    joint_support = (ready and full is not None and full.mapping_complete
                     and full.level == c["target_level"] and b0_all_ties_invariant)
    rows.append(row("all_input_joint_compatible", None, joint_eligible, joint_support,
                    joint_eligible and joint_support and joint_match,
                    gold_reasons=("gold:all_inputs_complete_joint_reference",) if joint_eligible
                    else ("gold:some_input_not_compatibility_eligible",)))
    strict_e = reference["strict_full_spectrum_evidence"]
    strict_core = metric_eligibility(strict_e, full or unknown_projection, metric="whole_molecule")
    strict_eligible = (all_eligible and c["truth_basis"] == "trusted_experimental"
                       and c["task_semantics"] == "natural_resonance"
                       and strict_core.gold_eligible)
    strict_support = ready and strict_core.prediction_supported
    rows.append(row("strict_full_spectrum", None, strict_eligible, strict_support,
                    strict_eligible and strict_support and all_exact,
                    gold_reasons=("gold:trusted_complete_spectrum_reference",) if strict_eligible
                    else ("gold:full_spectrum_evidence_not_established",)))
    return tuple(rows)


def _stratum(row):
    context = dict(row.context)
    return tuple((key, context[key]) for key in GROUP_FIELDS) + (("metric", row.metric),)


def summarize(rows):
    """Fixed-denominator micro rates and independent record/connectivity/obs support."""
    grouped = defaultdict(list)
    seen = set()
    for row in rows:
        key = (_stratum(row), dict(row.context)["record_id"], row.observation_id)
        if key in seen:
            raise ValueError("duplicate evaluation unit in stratum")
        seen.add(key)
        grouped[_stratum(row)].append(row)
    output = []
    for stratum, items in sorted(grouped.items()):
        eligible = [r for r in items if r.eligible]
        correct = sum(r.success for r in eligible)
        output.append(dict(stratum=dict(stratum), eligible=len(eligible), successes=correct,
            precision=None if not eligible else correct/len(eligible),
            support_status="off" if not eligible else "on",
            records=len({dict(r.context)["record_id"] for r in items}),
            connectivities=len({dict(r.context)["connectivity_id"] for r in items}),
            observations=len({(dict(r.context)["record_id"],r.observation_id)
                              for r in items if r.observation_id is not None}),
            eligible_records=len({dict(r.context)["record_id"] for r in eligible}),
            eligible_connectivities=len({dict(r.context)["connectivity_id"] for r in eligible}),
            supported=sum(r.prediction_supported for r in eligible)))
    return tuple(output)


def paired_gain(rows, baseline_a, baseline_b, *, replicates, seed, confidence):
    """Paired micro-rate gain B-A with percentile connectivity-cluster bootstrap.

    Every eligible unit and connectivity must match across baselines; failures remain.
    Groups exclude baseline only. CI support is off for fewer than two clusters.
    No hyperparameters are selected here; repeats/seed/confidence must be explicit.
    """
    if type(replicates) is not int or replicates < 1 or type(seed) is not int:
        raise ValueError("positive replicates and integer seed required")
    if isinstance(confidence, (bool,str)) or not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")
    if baseline_a == baseline_b or any(b not in ("B0","B1","B2") for b in (baseline_a,baseline_b)):
        raise ValueError("two distinct baselines required")
    groups = defaultdict(lambda: {baseline_a:{}, baseline_b:{}})
    for row in rows:
        c = dict(row.context)
        if c["baseline"] not in (baseline_a,baseline_b):
            continue
        stratum = tuple((k,v) for k,v in _stratum(row) if k != "baseline")
        identity = (c["record_id"],row.observation_id)
        target = groups[stratum][c["baseline"]]
        if identity in target:
            raise ValueError("duplicate paired unit")
        target[identity] = row
    output = []
    for stratum, sides in sorted(groups.items()):
        a,b = sides[baseline_a],sides[baseline_b]
        if set(a) != set(b):
            raise ValueError("paired cohorts differ")
        clusters = defaultdict(list)
        for identity in a:
            x,y = a[identity],b[identity]
            if x.eligible != y.eligible or dict(x.context)["connectivity_id"] != dict(y.context)["connectivity_id"]:
                raise ValueError("paired frozen denominator or connectivity differs")
            if x.eligible:
                clusters[dict(x.context)["connectivity_id"]].append(int(y.success)-int(x.success))
        n = sum(len(v) for v in clusters.values())
        estimate = None if not n else sum(sum(v) for v in clusters.values())/n
        ci = None
        if len(clusters) >= 2:
            rng = Random(seed);values = list(clusters.values());draws=[]
            for _ in range(replicates):
                chosen=[values[rng.randrange(len(values))] for _ in values]
                draws.append(sum(sum(v) for v in chosen)/sum(len(v) for v in chosen))
            draws.sort()
            def quantile(p):
                at=(len(draws)-1)*p;lo=floor(at);hi=ceil(at)
                return draws[lo]+(draws[hi]-draws[lo])*(at-lo)
            ci=(quantile((1-confidence)/2),quantile((1+confidence)/2))
        output.append(dict(stratum=dict(stratum), baseline_a=baseline_a,baseline_b=baseline_b,
                           eligible=n,connectivities=len(clusters),gain=estimate,CI=ci,
                           support_status="on" if ci is not None else "off",
                           replicates=replicates,seed=seed,confidence=confidence))
    return tuple(output)


def raw_topk_unit_hit_bounds(rank_bounds, acceptable_unit_ids, *, k, complete, evidence_ids):
    """Diagnostic hit interval for a full raw-unit rank tie partition, not chemistry.

    rank_bounds contains (unit_id, lowest_rank, highest_rank) for every unit.
    Complete tied blocks can cross k; lower bound requires every legal ordering
    to contain at least one declared acceptable unit. No fixed-ID tie selection.
    """
    _bool(complete);_proofs(evidence_ids)
    if type(k) is not int or k < 1:
        raise ValueError("k must be a positive integer")
    ranks=tuple(rank_bounds);units=[];blocks=defaultdict(list)
    for uid, low, high in ranks:
        _text(uid)
        if type(low) is not int or type(high) is not int or not 1 <= low <= high:
            raise ValueError("raw rank bounds must be positive integer intervals")
        units.append(uid);blocks[(low,high)].append(uid)
    if len(units)!=len(set(units)):
        raise ValueError("duplicate ranked unit")
    acceptable=set(acceptable_unit_ids)
    if acceptable-set(units):
        raise ValueError("acceptable unit outside raw ranking")
    if not complete:
        return dict(lower=None,upper=None,status="unsupported_incomplete_raw_ranking",
                    chemical_quotient_top3="unsupported")
    expected=1;lower=False;upper=False
    for (low,high),block in sorted(blocks.items()):
        if low!=expected or high-low+1!=len(block):
            raise ValueError("complete raw ties must partition all rank positions")
        expected=high+1
        available=max(0,min(k,high)-low+1)
        hits=len(acceptable.intersection(block))
        upper=upper or bool(available and hits)
        lower=lower or available > len(block)-hits
    return dict(lower=int(lower),upper=int(upper),status="raw_unit_ranking_diagnostic",
                chemical_quotient_top3="unsupported")
