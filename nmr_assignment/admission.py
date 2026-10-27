# 功能概述：逐共振指认证据旁表准入；不证明分子图、不修复标签。
# 主要职责：compare_reviews 比较实质主张；resolve_review_requirement 核对独立复核和裁决引用；
# validate_admission 返回 AdmissionResult 的分层资格、待补原因及完整联合候选。
# 依赖关系：仅标准库，依据 gold_admission_contract.json，与 InferenceInput 无依赖。
# 输入输出：读取元数据映射，不读取数据或模型、不写文件、不改变原输入；缺证据返回 unknown。
# 所有可评分类别均需完整映射族或外部完整投影proof；proof绑定联合候选SHA。
# 格式校验不认证科学真实性；截断枚举本身不能证明group/ambiguous准入。
from dataclasses import dataclass
from collections.abc import Mapping
from copy import deepcopy
import re
import hashlib
import json

CLASSES = {"trusted_atom", "equivalent_group", "ambiguous", "conflict", "unknown"}
CLAIMS = ("class", "atoms", "groups", "allowed_sets", "observation_semantics", "evidence_assessment")


def _sha(v):
    return isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) is not None


def _present(v):
    return v is not None and v != "" and v != [] and v != {}


def _receipt(v):
    return (isinstance(v, Mapping) and _present(v.get("rule_version"))
            and _sha(v.get("implementation_sha256")) and _sha(v.get("evidence_sha256")))


def _review(v):
    return (isinstance(v, Mapping) and _present(v.get("session_id"))
            and _sha(v.get("conclusion_sha256")) and _sha(v.get("evidence_sha256"))
            and isinstance(v.get("claims"), Mapping) and all(k in v["claims"] for k in CLAIMS))


def compare_reviews(first, second):
    return tuple(k for k in CLAIMS if k not in first.get("claims", {})
                 or k not in second.get("claims", {}) or first["claims"][k] != second["claims"][k])


@dataclass(frozen=True)
class ReviewResolution:
    accepted: bool
    reasons: tuple
    reviews: tuple
    adjudication: object = None
    claims: object = None


def resolve_review_requirement(disputed, reviews=(), adjudication=None):
    reviews = tuple(deepcopy(reviews)) if isinstance(reviews, (list, tuple)) else ()
    adjudication = deepcopy(adjudication)
    def result(ok, reason=(), claims=None):
        return ReviewResolution(ok, reason, reviews, adjudication, claims)
    if not disputed:
        return result(True)
    if len(reviews) != 2 or not all(_review(r) for r in reviews):
        return result(False, ("two_frozen_reviews_required",))
    ids = [r["session_id"] for r in reviews]
    if ids[0] == ids[1]:
        return result(False, ("review_sessions_not_independent",))
    if not compare_reviews(*reviews):
        return result(True, claims=reviews[0]["claims"])
    if not _review(adjudication):
        return result(False, ("third_independent_adjudication_required",))
    if adjudication["session_id"] in ids:
        return result(False, ("adjudicator_not_independent",))
    refs = [{k: r[k] for k in ("session_id", "conclusion_sha256", "evidence_sha256")} for r in reviews]
    if adjudication.get("source_reviews") != refs:
        return result(False, ("adjudication_source_reviews_not_preserved",))
    return result(True, claims=adjudication["claims"])


@dataclass(frozen=True)
class AdmissionResult:
    label_class: str
    atom_eligible: bool
    group_eligible: bool
    ambiguity_eligible: bool
    spectrum_eligible: bool
    pending_reasons: tuple
    joint_allowed_assignment_sets: tuple
    review_resolution: ReviewResolution
    proof_scope: str = "declared_evidence_shape_only"


def validate_admission(sidecar):
    if not isinstance(sidecar, Mapping):
        raise TypeError("gold admission requires an evidence sidecar mapping")
    reasons = []
    def need(ok, reason):
        if not ok:
            reasons.append(reason)
        return bool(ok)
    def section(key):
        v = sidecar.get(key, {})
        return v if isinstance(v, Mapping) else {}
    record = section("record_key")
    common = need(all(_present(record.get(k)) for k in ("source", "record_id", "nucleus")),
                  "record_provenance_missing")
    common &= need(_sha(sidecar.get("source_sha256")) and all(_present(sidecar.get(k)) for k in
                   ("source_evidence_locator", "structure_id", "original_split")), "original_evidence_missing")
    spectrum = bool(common and sidecar.get("source_authenticity") == "confirmed"
                    and sidecar.get("spectrum_authenticity") == "confirmed"
                    and _receipt(sidecar.get("spectrum_evidence")))
    need(spectrum, "spectrum_authenticity_pending")
    mapping = section("mapping")
    mapping_ok = need(all(_present(mapping.get(k)) for k in
        ("original_heavy_indices", "original_H_indices", "source_parent",
         "graph_fingerprint_before_AddHs", "graph_fingerprint_after_AddHs",
         "stepwise_atom_mapping", "allowed_mapping_set"))
        and type(mapping.get("index_base")) is int and mapping["index_base"] in (0, 1)
        and mapping.get("mapping_status") == "verified", "mapping_provenance_pending")
    graph = mapping.get("graph_validation", {})
    mapping_ok &= need(_receipt(graph) and graph.get("status") == "externally_verified",
                       "external_graph_proof_pending")
    audit = mapping.get("automation_audit", {})
    mapping_ok &= need(_receipt(audit) and _sha(audit.get("batch_audit_receipt_sha256")),
                       "frozen_mapping_audit_missing")
    obs = section("observation")
    observation_ok = need(all(k in obs and obs[k] is not None for k in
        ("observation_id", "original_value_literal", "original_decimal_precision", "unit",
         "observation_semantics", "integration_semantics", "mask", "frequency_window",
         "measurement_completeness")) and isinstance(obs.get("original_value_literal"), str)
        and type(obs.get("original_decimal_precision")) is int and obs["original_decimal_precision"] >= 0
        and obs.get("unit") in ("ppm", "Hz"), "observation_evidence_missing")
    label = section("label")
    requested = label.get("label_class", "unknown")
    label_ok = need(isinstance(requested, str) and requested in CLASSES and all(k in label for k in
        ("atom_or_group_assignment", "joint_allowed_assignment_sets", "equivalence_basis",
         "ambiguity_kind", "condition_hypotheses", "conflict_reason")), "label_evidence_missing")
    joint = label.get("joint_allowed_assignment_sets", [])
    label_ok &= need(isinstance(joint, (list, tuple)), "joint_assignments_malformed")
    review = resolve_review_requirement(sidecar.get("disputed") is True or requested == "conflict",
                                        sidecar.get("reviews", ()), sidecar.get("adjudication"))
    reasons.extend(review.reasons)
    if review.accepted and review.claims is not None:
        expected = dict(zip(CLAIMS, (requested, label.get("atoms", []), label.get("groups", []), joint,
                                    obs.get("observation_semantics"), sidecar.get("evidence_assessment"))))
        label_ok &= need(all(review.claims[k] == expected[k] for k in CLAIMS), "review_claims_sidecar_mismatch")
    eligible = bool(common and spectrum and mapping_ok and observation_ok and label_ok and review.accepted)
    if requested in ("trusted_atom", "equivalent_group", "ambiguous"):
        complete_family = (mapping.get("mapping_enumeration_complete") is True
                           and mapping.get("enumeration_truncated") is False)
        proof = mapping.get("complete_projection_proof", {})
        joint_sha = hashlib.sha256(json.dumps(joint, sort_keys=True, separators=(",", ":"),
                                              ensure_ascii=True).encode()).hexdigest()
        complete_projection = (_receipt(proof) and proof.get("status") == "externally_verified"
            and proof.get("proof_kind") in ("complete_projection_quotient", "complete_symbolic_projection")
            and proof.get("scored_class") == requested and proof.get("complete") is True
            and proof.get("projection_enumeration_truncated") is False
            and proof.get("assignment_sets_sha256") == joint_sha)
        eligible &= need(complete_family or complete_projection,
                         "gold_mapping_family_completeness_pending")
    if requested == "trusted_atom":
        eligible &= need(mapping.get("mapping_enumeration_complete") is True
                         and mapping.get("assignment_invariant_across_all_valid_maps") is True
                         and mapping.get("enumeration_truncated") is False, "unique_mapping_not_established")
        eligible &= need(_present(label.get("atom_or_group_assignment")), "atom_assignment_missing")
    if requested == "equivalent_group":
        eligible &= need(_present(label.get("equivalence_basis"))
                         and _present(label.get("atom_or_group_assignment")), "equivalent_group_evidence_missing")
    if requested == "ambiguous":
        eligible &= need(bool(joint) and label.get("ambiguity_kind") in
                         ("mapping_nonunique", "experimentally_unresolved", "accidental_overlap", "unknown"),
                         "ambiguity_evidence_missing")
    if requested == "unknown":
        need(False, "assignment_evidence_unknown")
    admitted = requested if eligible else "unknown"
    return AdmissionResult(admitted, admitted == "trusted_atom", admitted == "equivalent_group",
        admitted == "ambiguous", spectrum, tuple(reasons),
        tuple(deepcopy(joint)) if isinstance(joint, (list, tuple)) else (), review)
