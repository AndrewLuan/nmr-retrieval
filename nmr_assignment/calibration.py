"""功能概述：按冻结 validation connectivity 分组校准置信阈值，不执行数据或模型评估。
主要职责：CalibrationAxis 包含完整评价轨道与 cohort/source/label/rule SHA；EvaluationRecord
接上游已评结果。calibrate 按完整轴分别工作，calibration 选择阈值，audit 固定阈值验收。
门槛只取有限正认证 margin，>= 保留整个同分块；unsupported 合格记录仍在 coverage 分母。
CalibrationPolicy 所有数字显式传入；policy_from_frozen_config 只读取结构化已批准配置，
不解析说明文字。connectivity_partition 固定按 namespace+group 的 SHA256 第一 bit 分组。
cluster_bootstrap 在 connectivity 层重采样，整个组的记录一起进入；CI 为 percentile，
不是 precision>=0.90 的置信下界保证。没有 published 支持时 precision 与其 CI 都为 None。
代码库关系：纯标准库，供 metrics/evaluation 的 validation 输出调用；不会读取真实数据、
源结构、模型、test 或文件。source_relative 只标 source-assertion compatibility，不冒充
trusted experimental accuracy。whole-input endpoint 保留 atom/parent/group 与 set/multiset，另以 record sampling 轴分轨，不混逐峰样本。
输入输出与副作用：不可变输入/输出 dataclass；非法字段或重复评价单位抛 ValueError。
各轨独立 evidence，audit 失败关闭发布且不回调阈值；基础 ranked 输出由上游保留不受影响。
"""
from dataclasses import dataclass
from collections import defaultdict
from hashlib import sha256
from math import isfinite, floor
import random


def _name(value):
    if not isinstance(value,str) or not value:
        raise ValueError("nonempty identity required")


def _digest(value):
    if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("provenance SHA256 must be lowercase hex")


@dataclass(frozen=True,order=True)
class CalibrationAxis:
    method: str
    nucleus: str
    task_semantics: str
    target_level: str
    truth_basis: str
    endpoint: str
    target_semantics: str
    sampling_unit: str
    cohort_sha256: str
    source_sha256: str
    label_sha256: str
    rule_sha256: str

    def __post_init__(self):
        if self.method not in ("B0","B1","B2") or self.nucleus not in ("1H","13C"):
            raise ValueError("unsupported baseline/nucleus")
        if self.task_semantics not in ("natural_resonance","derived_serialized_value_bin"):
            raise ValueError("explicit task semantics required")
        if self.truth_basis not in ("trusted_experimental","source_relative_current_serialization","source_report_supported"):
            raise ValueError("explicit approved truth basis required")
        if self.truth_basis=="source_report_supported":
            raise ValueError("source_report_supported calibration unsupported pending independent definition; retain metrics only")
        if self.truth_basis=="trusted_experimental" and self.endpoint not in ("per_peak","all_input_reported_peaks_exact"):
            raise ValueError("trusted experimental calibration requires exact observation or approved exact whole-input endpoint")
        if self.target_level not in ("atom","parent","group"):
            raise ValueError("target_level must preserve atom/parent/group semantics")
        if self.target_semantics not in ("set","nuclear_multiset"):
            raise ValueError("explicit target set/multiset semantics required")
        if self.endpoint in ("per_peak","per_peak_compatibility"):
            if self.sampling_unit!="observation":
                raise ValueError("per-peak endpoints require observation sampling units")
        elif self.endpoint in ("all_input_reported_peaks_exact","strict_full_spectrum"):
            if self.sampling_unit!="record":
                raise ValueError("whole-input endpoints require independent record sampling units")
        else:
            raise ValueError("unsupported calibration endpoint")
        for value in (self.cohort_sha256,self.source_sha256,self.label_sha256,self.rule_sha256):
            _digest(value)

    @property
    def precision_metric(self):
        return {"source_relative_current_serialization":"source_assertion_compatibility_precision",
                "source_report_supported":"source_report_supported_precision",
                "trusted_experimental":"experimental_exact_set_precision"}[self.truth_basis]



@dataclass(frozen=True)
class EvaluationRecord:
    """margin_certified attests determinate gap>tau admission, not raw MILP optimality."""
    axis: CalibrationAxis
    item_id: str
    connectivity_id: str
    partition: str
    gold_eligible: bool
    prediction_supported: bool
    margin_certified: bool
    margin: object
    correct: object

    def __post_init__(self):
        if type(self.axis) is not CalibrationAxis:
            raise ValueError("typed calibration axis required")
        _name(self.item_id); _name(self.connectivity_id)
        if self.partition!="validation":
            raise ValueError("calibration accepts fixed validation records only")
        if any(type(v) is not bool for v in (self.gold_eligible,self.prediction_supported,self.margin_certified)):
            raise ValueError("explicit eligibility/support/certificate booleans required")
        if self.margin is not None and (isinstance(self.margin,(bool,str,bytes)) or not isinstance(self.margin,(float,int))):
            raise ValueError("margin must be numeric or NA")
        if self.correct is not None and type(self.correct) is not bool:
            raise ValueError("evaluated correctness must be boolean or NA")
        if self.gold_eligible and self.prediction_supported and self.correct is None:
            raise ValueError("eligible supported evaluation needs a correctness outcome")


@dataclass(frozen=True)
class CalibrationPolicy:
    minimum_precision: float
    minimum_published_units: int
    minimum_connectivity_groups: int
    bootstrap_replicates: int
    bootstrap_seed: int
    confidence_level: float
    split_namespace: str

    def __post_init__(self):
        for value in (self.minimum_precision,self.confidence_level):
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not isfinite(value) or not 0<value<1:
                raise ValueError("precision/confidence must be finite and between zero and one")
        for value in (self.minimum_published_units,self.minimum_connectivity_groups,self.bootstrap_replicates):
            if type(value) is not int or value<=0:
                raise ValueError("support and bootstrap counts must be positive integers")
        if type(self.bootstrap_seed) is not int:
            raise ValueError("bootstrap_seed must be an integer")
        _name(self.split_namespace)


def policy_from_frozen_config(config):
    """Read structured config only; calling this does not approve a configuration."""
    c=config["machine_calibration_contract"]
    return CalibrationPolicy(minimum_precision=c["precision_threshold"],
        minimum_published_units=c["min_published_units"],
        minimum_connectivity_groups=c["min_connectivity_groups"],
        bootstrap_replicates=c["bootstrap_replicates"],bootstrap_seed=c["seed"],
        confidence_level=c["confidence_level"],split_namespace=c["split_namespace"])


def evaluation_record_from_row(row, *, margin, margin_certified, cohort_sha256,
                               source_sha256, label_sha256, rule_sha256, pipeline_status,
                               margin_tolerance, input_observation_ids=None, observation_scores=None):
    """Adapt one canonical metrics.EvaluationRow; whole-record score supplied upstream.

    A raw margin certificate is insufficient: pipeline per-observation determinate
    status and explicit reduced-objective tau are required. A whole endpoint needs
    every input observation score/certificate/tau, exact input coverage, and all
    determinate flags; its score is their minimum. Missing/timeout/tied peaks remain
    in the eligible denominator but cannot publish. Provenance remains separate.
    """
    from .metrics import EvaluationRow
    if type(row) is not EvaluationRow:
        raise ValueError("typed metrics EvaluationRow required")
    c=dict(row.context)
    if len(c)!=len(row.context):
        raise ValueError("duplicate evaluation context fields")
    endpoints={"exact_observation":("per_peak","observation"),
               "compatible_observation":("per_peak_compatibility","observation"),
               "all_input_reported_peaks_exact":("all_input_reported_peaks_exact","record"),
               "strict_full_spectrum":("strict_full_spectrum","record")}
    if row.metric not in endpoints:
        raise ValueError("evaluation endpoint has no approved calibration adapter")
    endpoint,sampling=endpoints[row.metric]
    if sampling=="record" and row.observation_id is not None:
        raise ValueError("whole-record evaluation must not contain an observation ID")
    if sampling=="observation":
        _name(row.observation_id)
    axis=CalibrationAxis(method=c["baseline"],nucleus=c["nucleus"],task_semantics=c["task_semantics"],
        target_level=c["target_level"],truth_basis=c["truth_basis"],endpoint=endpoint,
        target_semantics=c["target_semantics"],sampling_unit=sampling,cohort_sha256=cohort_sha256,
        source_sha256=source_sha256,label_sha256=label_sha256,rule_sha256=rule_sha256)
    if not isinstance(pipeline_status,dict):
        raise ValueError("baseline pipeline status required for confidence admission")
    ready=pipeline_status.get("certified") is True and pipeline_status.get("timed_out") is False
    determinate=pipeline_status.get("observation_determinate",{})
    if not isinstance(determinate,dict):
        raise ValueError("per-observation baseline determinate map required")
    def certified_score(value,certificate,tolerance,oid):
        return (ready and determinate.get(oid) is True and certificate is True and
            type(value) in (float,int) and isfinite(value) and type(tolerance) in (float,int)
            and isfinite(tolerance) and tolerance>=0 and value>tolerance)
    if sampling=="observation":
        margin_certified=certified_score(margin,margin_certified,margin_tolerance,row.observation_id)
    else:
        ids=tuple(input_observation_ids or ())
        if len(ids)!=len(set(ids)):
            raise ValueError("whole-record input observation IDs must be distinct")
        scores=observation_scores if isinstance(observation_scores,dict) else {}
        complete=bool(ids) and set(scores)==set(ids)
        values=[]
        if complete:
            for oid in ids:
                score=scores[oid]
                if (not isinstance(score,dict) or set(score)!={"margin","margin_certified","margin_tolerance"}
                        or not certified_score(score["margin"],score["margin_certified"],score["margin_tolerance"],oid)):
                    complete=False
                    break
                values.append(score["margin"])
        computed=min(values) if complete else None
        if computed is not None and margin is not None and margin!=computed:
            raise ValueError("whole-record score must equal minimum complete determinate input score")
        margin=computed
        margin_certified=complete and margin_certified is True
    # Length-safe encoding avoids record/observation ID concatenation collisions.
    import json
    item=json.dumps((c["record_id"],row.observation_id),ensure_ascii=False,separators=(",",":"))
    return EvaluationRecord(axis,item,c["connectivity_id"],"validation",row.eligible,
        row.prediction_supported,margin_certified,margin,row.success if row.eligible else None)


def connectivity_partition(connectivity_id, *, split_namespace):
    _name(connectivity_id); _name(split_namespace)
    digest=sha256((split_namespace+connectivity_id).encode("utf-8")).digest()
    return "audit" if digest[0]&128 else "calibration"


def _publishable(record):
    return (record.gold_eligible and record.prediction_supported and record.margin_certified
            and record.margin is not None and isfinite(record.margin) and record.margin>0)


@dataclass(frozen=True)
class SplitSummary:
    eligible_count: int
    published_count: int
    correct_count: int
    published_connectivity_groups: int
    precision: object
    coverage: float
    published_ids: tuple
    precision_ci: object
    coverage_ci: object
    precision_defined_bootstrap_replicates: int


@dataclass(frozen=True)
class CalibrationArtifact:
    axis: CalibrationAxis
    policy: CalibrationPolicy
    status: str
    threshold: object
    calibration: SplitSummary
    audit: SplitSummary
    published_ids: tuple
    publication_precision: object
    publication_coverage: float
    precision_metric: str
    calibration_evidence_ids: tuple
    audit_evidence_ids: tuple
    ci_interpretation: str = "percentile connectivity-cluster bootstrap; no precision lower-bound guarantee"


def _counts(rows,threshold):
    eligible=tuple(r for r in rows if r.gold_eligible)
    published=tuple(r for r in eligible if threshold is not None and _publishable(r) and r.margin>=threshold)
    correct=sum(r.correct is True for r in published)
    return eligible,published,correct


def _accepted(rows,threshold,policy):
    _,published,correct=_counts(rows,threshold)
    return (len(published)>=policy.minimum_published_units and
            len({r.connectivity_id for r in published})>=policy.minimum_connectivity_groups and
            correct/len(published)>=policy.minimum_precision)


def _percentile(values,q):
    ordered=sorted(values)
    pos=(len(ordered)-1)*q
    lower=floor(pos); upper=min(lower+1,len(ordered)-1)
    return ordered[lower]+(ordered[upper]-ordered[lower])*(pos-lower)


def cluster_bootstrap(records, *, threshold, policy):
    """Fixed-threshold CI; resample whole eligible connectivity groups, including failures."""
    groups=defaultdict(list)
    for record in records:
        if record.gold_eligible:
            groups[record.connectivity_id].append(record)
    stats=[]
    for gid in sorted(groups):
        eligible,published,correct=_counts(groups[gid],threshold)
        stats.append((len(eligible),len(published),correct))
    if not stats:
        return None,None,0
    rng=random.Random(policy.bootstrap_seed)
    precision,coverage=[],[]
    for _ in range(policy.bootstrap_replicates):
        e=p=c=0
        for _ in stats:
            ei,pi,ci=stats[rng.randrange(len(stats))]
            e+=ei; p+=pi; c+=ci
        coverage.append(p/e if e else 0.)
        if p:
            precision.append(c/p)
    tail=(1-policy.confidence_level)/2
    pci=(_percentile(precision,tail),_percentile(precision,1-tail)) if precision else None
    cci=(_percentile(coverage,tail),_percentile(coverage,1-tail))
    return pci,cci,len(precision)


def _summary(rows,threshold,policy):
    eligible,published,correct=_counts(rows,threshold)
    pci,cci,defined=cluster_bootstrap(rows,threshold=threshold,policy=policy)
    return SplitSummary(len(eligible),len(published),correct,len({r.connectivity_id for r in published}),
        correct/len(published) if published else None,len(published)/len(eligible) if eligible else 0.,
        tuple(sorted(r.item_id for r in published)),pci,cci,defined)


def calibrate(records, *, policy):
    """Return independent artifacts per complete axis, without cross-stratum pooling.

    Input is evaluation evidence for existing validation units. Whole-input scores
    and outcomes must already be constructed upstream at record level. A failed
    audit keeps the chosen threshold for diagnosis but closes all publication.
    """
    if type(policy) is not CalibrationPolicy:
        raise ValueError("explicit CalibrationPolicy required")
    grouped=defaultdict(list)
    seen=set()
    for record in records:
        if type(record) is not EvaluationRecord:
            raise ValueError("typed evaluation records required")
        key=record.axis,record.item_id
        if key in seen:
            raise ValueError("duplicate evaluation item in one stratum")
        seen.add(key); grouped[record.axis].append(record)
    artifacts=[]
    for axis,rows in sorted(grouped.items()):
        calibration=tuple(r for r in rows if connectivity_partition(r.connectivity_id,
            split_namespace=policy.split_namespace)=="calibration")
        audit=tuple(r for r in rows if connectivity_partition(r.connectivity_id,
            split_namespace=policy.split_namespace)=="audit")
        candidates=sorted({float(r.margin) for r in calibration if _publishable(r)})
        feasible=[t for t in candidates if _accepted(calibration,t,policy)]
        threshold=max(feasible,key=lambda t:(len(_counts(calibration,t)[1]),t)) if feasible else None
        cs,aus=_summary(calibration,threshold,policy),_summary(audit,threshold,policy)
        if threshold is None:
            status="off_insufficient_support"
        elif _accepted(audit,threshold,policy):
            status="on_audit_passed"
        elif (aus.published_count<policy.minimum_published_units or
              aus.published_connectivity_groups<policy.minimum_connectivity_groups):
            status="off_insufficient_support"
        else:
            status="off_audit_rejected"
        on=status=="on_audit_passed"
        published=tuple(sorted(cs.published_ids+aus.published_ids)) if on else ()
        total=cs.eligible_count+aus.eligible_count
        precision=(cs.correct_count+aus.correct_count)/len(published) if published else None
        artifacts.append(CalibrationArtifact(axis,policy,status,threshold,cs,aus,published,precision,
            len(published)/total if total else 0.,axis.precision_metric,
            tuple(sorted(r.item_id for r in calibration)),tuple(sorted(r.item_id for r in audit))))
    return tuple(artifacts)
