# 功能概述：合成证据验证准入边界，不使用真实谱或模型。
# 主要职责：fixture 构造完整旁表；测试独立复核、联合候选、映射截断和谱真实性。
# 代码关系：仅调用 nmr_assignment.admission；不改变 InferenceInput。
# 输入输出：pytest 临时内存映射和断言，无文件副作用。
from copy import deepcopy
import pytest
import hashlib
import json
from nmr_assignment.admission import compare_reviews, resolve_review_requirement, validate_admission

SHA = "a" * 64


def receipt():
    return {"rule_version": "frozen-v1", "implementation_sha256": SHA, "evidence_sha256": SHA}


@pytest.fixture
def row():
    audit = dict(receipt(), batch_audit_receipt_sha256=SHA)
    return {
        "record_key": {"source": "synthetic", "record_id": "1", "nucleus": "1H"},
        "source_sha256": SHA, "source_evidence_locator": "record:1",
        "structure_id": "synthetic-structure", "original_split": "train",
        "source_authenticity": "confirmed", "spectrum_authenticity": "confirmed",
        "spectrum_evidence": receipt(),
        "mapping": {"original_heavy_indices": [0], "original_H_indices": [1],
            "index_base": 0, "source_parent": {"1": 0},
            "graph_fingerprint_before_AddHs": "before", "graph_fingerprint_after_AddHs": "after",
            "stepwise_atom_mapping": [{"1": 1}], "allowed_mapping_set": [{"1": 1}],
            "mapping_status": "verified", "mapping_enumeration_complete": True,
            "assignment_invariant_across_all_valid_maps": True, "enumeration_truncated": False,
            "graph_validation": dict(receipt(), status="externally_verified"), "automation_audit": audit},
        "observation": {"observation_id": "o1", "original_value_literal": "1.20",
            "original_decimal_precision": 2, "unit": "ppm", "observation_semantics": "peak",
            "integration_semantics": "unknown", "mask": True, "frequency_window": "unknown",
            "measurement_completeness": "partial"},
        "label": {"label_class": "trusted_atom", "atom_or_group_assignment": [1],
            "atoms": [1], "groups": [], "joint_allowed_assignment_sets": [[[1]]],
            "equivalence_basis": None, "ambiguity_kind": None,
            "condition_hypotheses": [], "conflict_reason": None},
        "evidence_assessment": "supported", "disputed": False}


def review(row, session):
    label = row["label"]
    return {"session_id": session, "conclusion_sha256": SHA, "evidence_sha256": SHA,
        "action": "admit", "claims": {"class": label["label_class"], "atoms": label["atoms"],
        "groups": label["groups"], "allowed_sets": label["joint_allowed_assignment_sets"],
        "observation_semantics": row["observation"]["observation_semantics"],
        "evidence_assessment": row["evidence_assessment"]}}


def test_missing_evidence_and_coverage_flag_do_not_create_gold():
    assert validate_admission({}).label_class == "unknown"
    assert not validate_admission({"full_atom_labels": True}).atom_eligible


def test_automatic_undisputed_mapping(row):
    result = validate_admission(row)
    assert result.atom_eligible and result.spectrum_eligible
    assert result.review_resolution.reviews == ()
    assert result.proof_scope == "declared_evidence_shape_only"
    del row["mapping"]["automation_audit"]
    assert not validate_admission(row).atom_eligible


@pytest.mark.parametrize("key,value", [
    ("mapping_enumeration_complete", False),
    ("assignment_invariant_across_all_valid_maps", False),
    ("enumeration_truncated", True)])
def test_unique_requires_all_mapping_conditions(row, key, value):
    row["mapping"][key] = value
    assert "unique_mapping_not_established" in validate_admission(row).pending_reasons
    assert not validate_admission(row).atom_eligible


def test_no_boolean_graph_self_certificate(row):
    row["mapping"]["graph_validation"] = True
    result = validate_admission(row)
    assert result.label_class == "unknown"
    assert "external_graph_proof_pending" in result.pending_reasons


@pytest.mark.parametrize("field,value", [("atoms", [2]), ("allowed_sets", [[[2]]]),
    ("groups", [[2, 3]]), ("observation_semantics", "range"),
    ("evidence_assessment", "unsupported"), ("class", "unknown")])
def test_same_action_different_claim_requires_adjudication(row, field, value):
    first, second = review(row, "r1"), review(row, "r2")
    second["claims"] = deepcopy(second["claims"])
    second["claims"][field] = value
    assert field in compare_reviews(first, second)
    row.update(disputed=True, reviews=[first, second])
    result = validate_admission(row)
    assert result.label_class == "unknown"
    assert "third_independent_adjudication_required" in result.pending_reasons


def test_review_identity_and_third_preservation(row):
    first, second = review(row, "r1"), review(row, "r1")
    assert not resolve_review_requirement(True, [first, second]).accepted
    second["session_id"] = "r2"
    second["claims"] = deepcopy(second["claims"])
    second["claims"]["atoms"] = [2]
    third = review(row, "r3")
    assert not resolve_review_requirement(True, [first, second], third).accepted
    third["source_reviews"] = [{k: r[k] for k in
        ("session_id", "conclusion_sha256", "evidence_sha256")} for r in (first, second)]
    result = resolve_review_requirement(True, [first, second], third)
    assert result.accepted and result.reviews == (first, second)
    assert result.adjudication["source_reviews"] == third["source_reviews"]
    third["session_id"] = "r2"
    assert not resolve_review_requirement(True, [first, second], third).accepted


def test_source_unresolved_defers_spectrum(row):
    row["source_authenticity"] = "unknown"
    result = validate_admission(row)
    assert not result.spectrum_eligible and not result.atom_eligible


def test_assignment_conflict_retains_trusted_spectrum(row):
    row["label"]["label_class"] = "conflict"
    result = validate_admission(row)
    assert result.label_class == "unknown" and result.spectrum_eligible
    assert not result.atom_eligible
    row["reviews"] = [review(row, "r1"), review(row, "r2")]
    assert validate_admission(row).label_class == "conflict"


def test_joint_sets_preserved_and_review_must_match_sidecar(row):
    row["label"].update(label_class="ambiguous", ambiguity_kind="mapping_nonunique",
                         joint_allowed_assignment_sets=[[[1], [2]], [[2], [1]]])
    result = validate_admission(row)
    assert result.ambiguity_eligible
    assert result.joint_allowed_assignment_sets == ([[1], [2]], [[2], [1]])
    row.update(disputed=True, reviews=[review(row, "r1"), review(row, "r2")])
    for r in row["reviews"]:
        r["claims"] = deepcopy(r["claims"])
        r["claims"]["allowed_sets"] = [[[1], [1]]]
    assert not validate_admission(row).ambiguity_eligible


def test_sidecar_not_inference_input():
    with pytest.raises(TypeError):
        validate_admission(object())


@pytest.mark.parametrize("label_class", ["equivalent_group", "ambiguous"])
@pytest.mark.parametrize("field,value", [("mapping_enumeration_complete", False),
                                         ("enumeration_truncated", True)])
def test_all_scored_classes_reject_incomplete_mapping_family(row, label_class, field, value):
    row["label"].update(label_class=label_class, equivalence_basis="synthetic:group-proof",
                         ambiguity_kind="mapping_nonunique")
    row["mapping"][field] = value
    result=validate_admission(row)
    assert not result.group_eligible and not result.ambiguity_eligible
    assert "gold_mapping_family_completeness_pending" in result.pending_reasons


@pytest.mark.parametrize("label_class", ["equivalent_group", "ambiguous"])
def test_complete_external_projection_can_cover_raw_truncated_family(row, label_class):
    row["label"].update(label_class=label_class, equivalence_basis="synthetic:group-proof",
                         ambiguity_kind="mapping_nonunique")
    row["mapping"].update(mapping_enumeration_complete=False,enumeration_truncated=True)
    joint=row["label"]["joint_allowed_assignment_sets"]
    digest=hashlib.sha256(json.dumps(joint,sort_keys=True,separators=(",",":"),
                                    ensure_ascii=True).encode()).hexdigest()
    proof=dict(receipt(),status="externally_verified",proof_kind="complete_projection_quotient",
               scored_class=label_class,complete=True,projection_enumeration_truncated=False,
               assignment_sets_sha256=digest)
    row["mapping"]["complete_projection_proof"]=proof
    result=validate_admission(row)
    assert result.group_eligible if label_class=="equivalent_group" else result.ambiguity_eligible
    proof["assignment_sets_sha256"]="b"*64
    assert validate_admission(row).label_class=="unknown"
    proof["assignment_sets_sha256"]=digest
    proof["projection_enumeration_truncated"]=True
    assert validate_admission(row).label_class=="unknown"
