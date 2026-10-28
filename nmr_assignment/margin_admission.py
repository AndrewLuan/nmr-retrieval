"""功能概述：来源含噪 A/B 的内部编号与完整联合约束准入，不认证实验真值。

build_margin_admission 接受固定 train 身份、原文参考、当前策略及结构容量；复用精确
decimal bins、已存 source_transport 和 make_joint_mapping，不做预测、求解或训练。
每个 source/model map 都保持整份关联；G 消费两族的联合存在量词，d/M 只消费不变
parent SET。未知与旧 hold/mask/weak 不生成硬约束或缺峰负标签。返回纯 JSON，供独立
loss 模块消费，不与 loss 互相导入；此门禁结果仍须批量核验与 owner 放行。
"""
from collections.abc import Mapping
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import re

from .derived_observation import build_serialized_value_bins
from .mapping import CapacityLayout, CapacityUnit, make_joint_mapping
from .source_reference import _atomic_number, _load, text_sha256
from .source_transport import restore_joint_map_keys


IDENTITY = ("source", "nucleus", "record_id", "structure_id")
HASHES = ("source_sha256", "row_sha256", "policy_sha256",
          "cohort_identity_manifest_sha256")


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _need(condition, reason):
    if not condition:
        raise ValueError(reason)


def _is_sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _layout(value):
    if isinstance(value, CapacityLayout):
        value = asdict(value)
    _need(isinstance(value, Mapping), "model_layout_missing")
    units = tuple(CapacityUnit(unit_id=u["unit_id"], environment_id=u["environment_id"],
        parent_mass=tuple(tuple(x) for x in u["parent_mass"]), nucleus_mass=u["nucleus_mass"],
        partition_status=u["partition_status"], evidence_ids=tuple(u["evidence_ids"]))
        for u in value["units"])
    return CapacityLayout(value["nucleus"], units,
        tuple(tuple(x) for x in value["parent_mass_totals"]),
        value["structural_environment_count"], value["partition_hypothesis_id"])


def _policy_reasons(policy, binding):
    if not isinstance(policy, Mapping):
        return ["current_policy_unknown"]
    identity = policy.get("source_binding", policy)
    if any(identity.get(k) != binding[k] for k in IDENTITY + ("row_sha256",)):
        return ["current_policy_identity_mismatch"]
    disposition = policy.get("review_disposition", policy.get("disposition", policy.get("quality")))
    reasons = []
    if policy.get("keep_atom_parent_supervision") is not True:
        reasons.append("historical_hard_supervision_disabled")
    if disposition not in ("no_detected_local_conflict", "source_relative_keep",
            "reviewed_source_relative_keep", "cross_version_corrected", "source_report_corrected"):
        reasons.append("historical_hold_mask_weak_or_unknown")
    if policy.get("weak_supervision") is True or policy.get("weak_supervision_enabled") is True:
        reasons.append("historical_weak_not_hard")
    if policy.get("shift_values_imputed") is True:
        reasons.append("imputed_values_not_hard")
    if policy.get("_normalization", {}).get("restriction"):
        reasons.append("historical_reference_choice_restricted")
    return reasons


def build_margin_admission(reference_record, *, train_identity, current_policy,
        current_policy_sha256, model_structure_snapshot, model_layout,
        model_mapping_evidence, attachment_blocks=(), attachment_evidence_ids=(),
        max_joint_maps=4096):
    """Return a JSON gate. No file/data loading or scientific execution occurs.

    reference_record is the existing hidden H reference row, including exact
    source_raw_line/binding/transport/baseline_structure_snapshot. train_identity
    is a row of the independently frozen complete train identity ledger.
    model_mapping_evidence must bind input_id, native snapshot, layout and latent
    blocks with exact canonical digests, plus a nonempty evidence SHA locator.
    It documents the producer; structure/mass equality is checked here as well.
    Current policy needs an explicit identity+row binding; missing is unknown.
    Original source authenticity is deliberately not a gate in this scope.
    """
    out = dict(schema="exploratory_margin_internal_admission_v1",
        input_id=train_identity.get("input_id") if isinstance(train_identity, Mapping) else None,
        status="unknown", source_authenticity="unknown", trusted_experimental=False,
        source_family_complete=False, model_family_complete=False,
        allowed_joint_parent_sets=[], model_unit_parent_sets=[], invariant_parent_sets={},
        supervised_observation_count=0, assignment_negative_labels_generated=False,
        reasons=[], training_release=False)
    try:
        binding = reference_record["binding"]
        out["source_binding"] = dict(binding)
        _need(set(binding) == set(IDENTITY + HASHES), "exact_source_binding_required")
        _need(all(isinstance(binding[k], str) and binding[k] for k in IDENTITY)
              and all(_is_sha(binding[k]) for k in HASHES), "invalid_source_binding")
        _need(binding["nucleus"] == "1H", "H_only")
        _need(train_identity["input_id"] == reference_record["input_id"]
              and train_identity["source_binding"] == binding, "train_reference_join_mismatch")
        _need(train_identity["roles"] == ["fixed_train8192"], "fixed_train_role_required")
        _need(_is_sha(train_identity["normalized_connectivity_sha256"]), "connectivity_binding_missing")
        _need(_is_sha(current_policy_sha256), "current_policy_artifact_sha_missing")
        out["current_policy_sha256"] = current_policy_sha256
        out["current_policy_row_sha256"] = canonical_digest(current_policy)
        raw = reference_record["source_raw_line"]
        _need(text_sha256(raw) == binding["row_sha256"], "raw_row_sha_mismatch")
        row = _load(raw)
        sid = row.get("structure_id") or text_sha256(row["smiles"])
        _need((row["source_ref"], row["nucleus"], row["record_id"], sid)
              == tuple(binding[k] for k in IDENTITY), "raw_identity_mismatch")
        n = len(row["atoms"])
        _need(all(len(row[k]) == n for k in ("coordinates", "atom_targets", "atom_target_mask")),
              "source_array_lengths")
        order = row["atom_order"]
        numbers = order["atomic_numbers"]
        _need(order["basis"] == "source_mol" and len(numbers) == n
              and numbers == [_atomic_number(x) for x in row["atoms"]]
              and all(type(x) is int and 1 <= x <= 118 for x in numbers), "source_elements_invalid")
        _need(len(order["source_to_canonical"]) == n
              and all(type(i) is int for i in order["source_to_canonical"])
              and set(order["source_to_canonical"]) == set(range(n)), "source_order_invalid")
        expected = []
        for i, (value, active) in enumerate(zip(row["atom_targets"], row["atom_target_mask"])):
            _need(type(active) in (bool, int) and active in (0, 1), "mask_invalid")
            _need(value is None or (type(value) in (int, Decimal) and Decimal(value).is_finite()),
                  "nonfinite_target")
            _need(active or value is None, "inactive_target_not_null")
            if active:
                _need(value is not None and numbers[i] == 1, "active_H_target_invalid")
                expected.append((i, value))
        spectrum = [(x["atom_index"], x["shift"]) for x in row["spectrum"]]
        _need(all(type(i) is int for i, _ in spectrum) and sorted(spectrum) == expected,
              "spectrum_target_mismatch")
        derived = build_serialized_value_bins(raw)
        out["anonymous_observations"] = list(derived.anonymous_payload())
        out["reported_slot_count"] = derived.reported_slot_count
        _need(derived.reported_slot_count > 0, "no_known_labels")
        t = restore_joint_map_keys(reference_record["transport"])
        _need(all(t[k] == binding[k] for k in binding), "transport_binding_mismatch")
        _need(t["status"] == "complete" and t["complete"] is True
              and t["enumeration_truncated"] is False and t["structure_only"] is True,
              "source_family_incomplete")
        lineage = dict(t["graph_lineage_evidence"])
        # 旧 producer 在 JSON 持久化前按整数 parent key 排序计算 SHA；
        # 只恢复这两个已声明整数键域，拒绝别名，不更改旧 receipt 字节。
        for field in ("source_suppressed_H_by_parent", "target_suppressed_H_by_parent"):
            restored = {}
            for key, value in lineage[field].items():
                _need(type(key) is int or (isinstance(key, str) and key.isdecimal()
                    and str(int(key)) == key), "noncanonical_lineage_parent_key")
                index = int(key)
                _need(index >= 0 and index not in restored, "duplicate_lineage_parent_key")
                restored[index] = value
            lineage[field] = restored
        proof = t["completeness_evidence"]
        _need(canonical_digest(lineage) == t["graph_lineage_evidence_sha256"]
              and canonical_digest(proof) == t["completeness_evidence_sha256"], "transport_proof_sha_mismatch")
        payload = dict(smiles=row["smiles"], atoms=row["atoms"], atom_order={k: order[k]
            for k in ("basis", "source_to_canonical", "atomic_numbers")})
        _need(lineage["source_structure_payload"] == payload
              and proof["graph_lineage_evidence_sha256"] == t["graph_lineage_evidence_sha256"]
              and proof["enumeration_truncated"] is False, "structure_proof_join_mismatch")
        maps = t["joint_maps"]
        tuples = tuple(sorted(tuple(m[i] for i in range(n)) for m in maps))
        _need(maps and len(tuples) == len(set(tuples))
              and [list(x) for x in tuples] == [list(x) for x in proof["parent_projection_rows"]],
              "joint_projection_family_mismatch")
        snapshot = reference_record["baseline_structure_snapshot"]
        _need(text_sha256(json.dumps(snapshot, sort_keys=True))
              == reference_record["baseline_structure_snapshot_sha256"], "baseline_snapshot_sha_mismatch")
        _need(model_structure_snapshot == snapshot, "native_graph_snapshot_mismatch")
        _need(snapshot["atoms"] == lineage["baseline_graph"]["atoms"]
              and snapshot["bonds"] == lineage["baseline_graph"]["bonds"]
              and snapshot["canonical_smiles"] == lineage["canonical_smiles"]
              and snapshot["rdkit_version"] == lineage["rdkit_version"], "baseline_graph_lineage_mismatch")
        parent_ids = dict(lineage["target_parent_ids"])
        _need(all(type(i) is int and p == str(i) for i, p in parent_ids.items()),
              "non_native_parent_namespace")
        bonds = snapshot["bonds"]
        parent_mass = {}
        atoms = {a["index"]: a for a in snapshot["atoms"]}
        for atom in atoms.values():
            if atom["z"] != 1:
                continue
            neighbours = [b["b"] if b["a"] == atom["index"] else b["a"]
                for b in bonds if atom["index"] in (b["a"], b["b"])]
            _need(len(neighbours) == 1 and atoms[neighbours[0]]["z"] != 1,
                  "native_H_parent_invalid")
            parent = str(neighbours[0])
            parent_mass[parent] = parent_mass.get(parent, 0) + 1
        layout = _layout(model_layout)
        _need(layout.nucleus == "1H" and dict(layout.parent_mass_totals) == parent_mass,
              "native_parent_capacity_mismatch")
        evidence = model_mapping_evidence
        _need(evidence["input_id"] == out["input_id"]
              and evidence["structure_snapshot_sha256"] == canonical_digest(snapshot)
              and evidence["layout_sha256"] == canonical_digest(asdict(layout))
              and evidence["attachment_blocks_sha256"] == canonical_digest(attachment_blocks)
              and _is_sha(evidence["evidence_sha256"]), "model_mapping_evidence_join_missing")
        unit_targets = {u.unit_id: tuple(p for p, mass in u.parent_mass for _ in range(mass))
                        for u in layout.units}
        joint = make_joint_mapping(layout, unit_targets,
            [tuple(u.unit_id for u in layout.units)], level="parent", complete=True,
            basis="provenance_lineage", evidence_ids=(evidence["evidence_sha256"],),
            target_universe=tuple(sorted(parent_mass)),
            completeness_evidence_id=canonical_digest(evidence), attachment_blocks=attachment_blocks,
            attachment_evidence_ids=attachment_evidence_ids, max_joint_maps=max_joint_maps)
        _need(joint.complete, "model_attachment_family_truncated")
        targets = dict(joint.target_by_unit)
        for permutation in joint.unit_permutations:
            projection = {uid: sorted(set(targets[target]))
                          for uid, target in zip(joint.unit_ids, permutation)}
            out["model_unit_parent_sets"].append(dict(map_id="model:"+canonical_digest(projection),
                                                      unit_parent_sets=projection))
        family = []
        for mapping in maps:
            _need(set(mapping) == set(range(n)) and set(mapping.values()) <= set(parent_ids.values()),
                  "source_map_parent_domain")
            projection = {b.bin_id: sorted({mapping[i] for i, _ in b.members})
                          for b in derived.hidden_provenance}
            family.append(dict(map_id="source:"+canonical_digest(mapping),
                               observation_parent_sets=projection))
        # Keep complete maps separate, including maps with identical parent projections.
        out["source_family_complete"] = True
        out["model_family_complete"] = True
        out["known_layout"] = asdict(layout)
        out["proof_locators"] = dict(source_completeness=t["completeness_evidence_sha256"],
            graph_lineage=t["graph_lineage_evidence_sha256"], model_mapping=evidence["evidence_sha256"])
        restrictions = _policy_reasons(current_policy, binding)
        out["policy_restriction_reasons"] = restrictions
        if restrictions:
            out["status"] = "restricted"
            out["reasons"].extend(restrictions)
            out["model_unit_parent_sets"] = []
            return out
        out["allowed_joint_parent_sets"] = family
        for b in derived.inference_bins:
            values = {tuple(v["observation_parent_sets"][b.bin_id]) for v in family}
            if len(values) == 1:
                out["invariant_parent_sets"][b.bin_id] = list(next(iter(values)))
        out["supervised_observation_count"] = len(out["invariant_parent_sets"])
        out["status"] = "internal_mapping_ready_pending_batch_review"
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError) as exc:
        out["reasons"].append(str(exc) if isinstance(exc, ValueError) else type(exc).__name__+":"+str(exc))
        out["allowed_joint_parent_sets"] = []
        out["model_unit_parent_sets"] = []
        out["invariant_parent_sets"] = {}
        out["supervised_observation_count"] = 0
    return out
