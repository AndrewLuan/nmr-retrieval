"""功能概述：把当前序列化源的声明图映到 baseline canonical 图，供源相对父节点集合评价。
本模块只证明 source_asserted_encoded_graph 内部的结构 transport，不证明原始实验 mol、
真实 H 身份、丢失立体信息或天然峰语义。源图约定复用 h_labels.source_groups 与
h_assignment_audit.inspect_record：AddHs(MolFromSmiles(smiles))；声明的
source_to_canonical 实际索引该展开图。baseline 复用 data.identity 的 RemoveHs、
canonical isomeric SMILES 再 AddHs 约定，不导入读取标签或模型的旧模块。
主要职责：build_source_transport 接收结构白名单和 source_reference 的 binding，
在有界独立进程中构图并枚举联合 parent 映射；_compressed 保留 RemoveHs 的原子
lineage，对被移除的普通终端 H 建完整计数证据，避免同 parent H 排列的阶乘展开。
_matches 验证 isotope/charge/radical/H邻域、所有键及 chirality 匹配；完整性只对
当前编码图的 parent 投影成立。跨 parent 的图同构仍保留为同一个全局 map 的关联。
restore_joint_map_keys 仅恢复 JSON 持久化后的规范整数 slot key，不改变映射语义。
关系：输出 joint_maps 为完整 source slot -> baseline parent ID，直接适配
nmr_assignment.source_reference.build_source_reference；parent ID 默认是十进制
canonical graph node，与 native_adapter 一致。proof SHA 绑定图、规则、RDKit版本和
完整投影；source_reference 仍负责原行、policy、cohort 的独立哈希与质量门禁。
输入输出与副作用：只访问 smiles/atoms/atom_order 及 binding 身份元数据，完全不读
targets、mask、shift、spectrum、coordinates 或 InChIKey。使用本机已有 RDKit，不
训练或前向；只读取本模块源码生成实现SHA，不写文件/网络。超时或枚举截断返回
unknown/complete=False，绝不自动补位。独立进程在返回前回收，不留下后台任务。
"""
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import re
import time
from collections.abc import Mapping


RULE = "serialized-source-parent-transport-v1"
REFERENCE_BASIS = "source_asserted_encoded_graph"
TRUTH_BASIS = "source_relative_current_serialization"
HASH_FIELDS = ("source_sha256", "row_sha256", "policy_sha256",
               "cohort_identity_manifest_sha256")
IDENTITY_FIELDS = ("source", "nucleus", "record_id", "structure_id")
INDEX_PROPERTY = "_source_transport_full_index"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode()).hexdigest()


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _base(binding):
    return dict(binding, status="unknown", complete=False, enumeration_truncated=False,
                structure_only=True, joint_maps=(), completeness_evidence_sha256=None,
                graph_lineage_evidence_sha256=None, truth_basis=TRUTH_BASIS,
                reference_basis=REFERENCE_BASIS, trust_basis="internal_source_consistency",
                experimental_atom_order_verified=False, original_stereo_status="unknown",
                used_coordinates=False, used_labels=False, reason_codes=())


def _atom_signature(atom, full=None):
    # Chiral tag orientation changes under renumbering; RDKit's chirality-aware
    # matcher checks its parity. Here we check specified-vs-unspecified only.
    h_neighbors = ()
    if full is not None:
        original = full.GetAtomWithIdx(atom.GetIntProp(INDEX_PROPERTY))
        h_neighbors = tuple(sorted((n.GetIsotope(), n.GetFormalCharge(),
            n.GetNumRadicalElectrons(), str(full.GetBondBetweenAtoms(original.GetIdx(), n.GetIdx()).GetBondType()))
            for n in original.GetNeighbors() if n.GetAtomicNum() == 1))
    return (atom.GetAtomicNum(), atom.GetIsotope(), atom.GetFormalCharge(),
            atom.GetNumRadicalElectrons(), bool(atom.GetIsAromatic()),
            str(atom.GetChiralTag()) != "CHI_UNSPECIFIED", h_neighbors)


def _graph_snapshot(mol):
    atoms = [dict(index=a.GetIdx(), z=a.GetAtomicNum(), isotope=a.GetIsotope(),
                  charge=a.GetFormalCharge(), radicals=a.GetNumRadicalElectrons(),
                  aromatic=a.GetIsAromatic(), chiral_tag=str(a.GetChiralTag()))
             for a in mol.GetAtoms()]
    bonds = [dict(a=b.GetBeginAtomIdx(), b=b.GetEndAtomIdx(), kind=str(b.GetBondType()),
                  aromatic=b.GetIsAromatic(), stereo=str(b.GetStereo()),
                  stereo_atoms=list(b.GetStereoAtoms())) for b in mol.GetBonds()]
    return dict(atoms=atoms, bonds=bonds)


def _compressed(full, Chem):
    supported_chiral = {"CHI_UNSPECIFIED", "CHI_TETRAHEDRAL_CW", "CHI_TETRAHEDRAL_CCW"}
    supported_bond_stereo = {"STEREONONE", "STEREOANY", "STEREOZ", "STEREOE", "STEREOCIS", "STEREOTRANS"}
    if any(str(a.GetChiralTag()) not in supported_chiral for a in full.GetAtoms()):
        raise ValueError("non_tetrahedral_stereo_requires_separate_rule")
    if any(str(b.GetStereo()) not in supported_bond_stereo for b in full.GetBonds()):
        raise ValueError("unsupported_bond_stereo_requires_separate_rule")
    marked = Chem.Mol(full)
    for atom in marked.GetAtoms():
        atom.SetIntProp(INDEX_PROPERTY, atom.GetIdx())
    reduced = Chem.RemoveHs(marked)
    retained = {a.GetIntProp(INDEX_PROPERTY): a.GetIdx() for a in reduced.GetAtoms()}
    suppressed = {}
    for atom in full.GetAtoms():
        if atom.GetIdx() in retained:
            continue
        if (atom.GetAtomicNum() != 1 or atom.GetIsotope() != 0 or atom.GetDegree() != 1
                or atom.GetFormalCharge() != 0 or atom.GetNumRadicalElectrons() != 0):
            raise ValueError("unsupported_removed_atom")
        parent = atom.GetNeighbors()[0]
        bond = full.GetBondBetweenAtoms(atom.GetIdx(), parent.GetIdx())
        if parent.GetAtomicNum() == 1 or str(bond.GetBondType()) != "SINGLE":
            raise ValueError("unsupported_removed_H_attachment")
        if parent.GetIdx() not in retained:
            raise ValueError("removed_H_parent_not_retained")
        suppressed.setdefault(parent.GetIdx(), []).append(atom.GetIdx())
    if any(a.GetAtomMapNum() for a in reduced.GetAtoms()):
        raise ValueError("atom_map_annotations_require_separate_provenance_rule")
    if list(reduced.GetStereoGroups()):
        raise ValueError("enhanced_stereo_requires_separate_rule")
    return reduced, retained, suppressed


def _matches(source, target, source_full, target_full, match):
    if (len(match) != source.GetNumAtoms() or len(set(match)) != len(match)
            or source.GetNumAtoms() != target.GetNumAtoms()
            or source.GetNumBonds() != target.GetNumBonds()):
        return False
    for i, j in enumerate(match):
        if _atom_signature(source.GetAtomWithIdx(i), source_full) != _atom_signature(target.GetAtomWithIdx(j), target_full):
            return False
    for bond in source.GetBonds():
        other = target.GetBondBetweenAtoms(match[bond.GetBeginAtomIdx()], match[bond.GetEndAtomIdx()])
        if other is None or (str(bond.GetBondType()), bond.GetIsAromatic(), str(bond.GetStereo())) != (
                str(other.GetBondType()), other.GetIsAromatic(), str(other.GetStereo())):
            return False
    return True


def _parent(full, index):
    atom = full.GetAtomWithIdx(index)
    if atom.GetAtomicNum() != 1:
        return index
    if atom.GetDegree() != 1 or atom.GetNeighbors()[0].GetAtomicNum() == 1:
        raise ValueError("source_H_has_no_single_heavy_parent")
    return atom.GetNeighbors()[0].GetIdx()


def _transport_impl(payload, binding, baseline_smiles, parent_ids, max_maps,
                    expected_rdkit_version, implementation_sha):
    from rdkit import Chem, rdBase
    if expected_rdkit_version is not None and rdBase.rdkitVersion != expected_rdkit_version:
        raise ValueError("rdkit_version_mismatch")
    smiles = payload["smiles"]
    parsed = Chem.MolFromSmiles(smiles)
    if parsed is None:
        raise ValueError("invalid_source_smiles")
    raw = Chem.AddHs(parsed)
    order = payload["atom_order"]
    if order.get("basis") != "source_mol":
        raise ValueError("undeclared_source_atom_order_basis")
    permutation = order["source_to_canonical"]
    numbers = order["atomic_numbers"]
    n = raw.GetNumAtoms()
    if (len(permutation) != n or any(type(i) is not int for i in permutation)
            or set(permutation) != set(range(n)) or len(numbers) != n
            or any(type(z) is not int or z <= 0 for z in numbers)):
        raise ValueError("source_order_not_full_permutation")
    if numbers != [raw.GetAtomWithIdx(i).GetAtomicNum() for i in permutation]:
        raise ValueError("declared_source_order_element_mismatch")
    atoms = payload["atoms"]
    if len(atoms) != n:
        raise ValueError("source_atom_array_length_mismatch")
    for source_slot, raw_index in enumerate(permutation):
        atom = raw.GetAtomWithIdx(raw_index)
        token = atoms[source_slot]
        if not ((type(token) is int and token == atom.GetAtomicNum()) or
                (isinstance(token, str) and token == atom.GetSymbol())):
            raise ValueError("source_atom_token_mismatch")
    # Exactly reproduce data.identity without importing torch or data loaders.
    canonical_base = Chem.RemoveHs(Chem.MolFromSmiles(smiles))
    canonical = Chem.MolToSmiles(canonical_base, isomericSmiles=True)
    if "." in canonical:
        raise ValueError("multicomponent_structure_unsupported")
    if baseline_smiles is not None and baseline_smiles != canonical:
        raise ValueError("baseline_not_exact_canonical_graph_convention")
    baseline = Chem.AddHs(Chem.MolFromSmiles(canonical))
    if raw.GetNumAtoms() != baseline.GetNumAtoms() or raw.GetNumBonds() != baseline.GetNumBonds():
        raise ValueError("canonicalization_changes_explicit_graph_size")
    heavy = {a.GetIdx() for a in baseline.GetAtoms() if a.GetAtomicNum() != 1}
    if parent_ids is None:
        parent_ids = {i: str(i) for i in heavy}
    if (set(parent_ids) != heavy or any(type(i) is not int for i in parent_ids)
            or any(not isinstance(v, str) or not v for v in parent_ids.values())
            or len(set(parent_ids.values())) != len(parent_ids)):
        raise ValueError("baseline_parent_ID_domain_invalid")
    source_q, source_retained, source_suppressed = _compressed(raw, Chem)
    target_q, target_retained, target_suppressed = _compressed(baseline, Chem)
    if source_q.GetNumAtoms() != target_q.GetNumAtoms() or source_q.GetNumBonds() != target_q.GetNumBonds():
        raise ValueError("compressed_graph_size_mismatch")
    # A capped raw match family is never treated as complete, even if projected
    # maps deduplicate. Explicit ordinary H permutations are absent by construction.
    matches = target_q.GetSubstructMatches(source_q, uniquify=False,
        useChirality=True, maxMatches=max_maps + 1)
    truncated = len(matches) > max_maps
    variants = set()
    rejected = 0
    for match in matches[:max_maps]:
        if not _matches(source_q, target_q, raw, baseline, match):
            rejected += 1
            continue
        projected = []
        for raw_index in permutation:
            source_parent = _parent(raw, raw_index)
            source_node = source_retained[source_parent]
            target_node = target_q.GetAtomWithIdx(match[source_node])
            target_parent = target_node.GetIntProp(INDEX_PROPERTY)
            projected.append(parent_ids[target_parent])
        variants.add(tuple(projected))
    if not variants:
        raise ValueError("no_verified_declared_graph_isomorphism")
    lineage = dict(rule=RULE, implementation_sha256=implementation_sha,
        rdkit_version=rdBase.rdkitVersion, reference_basis=REFERENCE_BASIS,
        raw_recipe="AddHs(MolFromSmiles(serialized_smiles))",
        baseline_recipe="AddHs(MolFromSmiles(MolToSmiles(RemoveHs(MolFromSmiles(serialized_smiles)),isomericSmiles=True)))",
        source_structure_payload=payload, canonical_smiles=canonical,
        source_graph=_graph_snapshot(raw), baseline_graph=_graph_snapshot(baseline),
        source_slot_to_raw_node=permutation,
        source_suppressed_H_by_parent=source_suppressed,
        target_suppressed_H_by_parent=target_suppressed,
        target_parent_ids=sorted(parent_ids.items()),
        source_original_graph_verified=False,
        source_order_meaning="declared_serialization_reference_not_original_experimental_proof")
    ordered = tuple(sorted(variants))
    proof = dict(rule=RULE, graph_lineage_evidence_sha256=_digest(lineage),
        compressed_source_atoms=source_q.GetNumAtoms(), compressed_target_atoms=target_q.GetNumAtoms(),
        raw_compressed_matches_returned=len(matches), rejected_attribute_mappings=rejected,
        max_maps=max_maps, enumeration_truncated=truncated,
        parent_projection_rows=ordered,
        argument="Every removed atom is an ordinary terminal H. Matching preserves each retained atom's full isotope-decorated H-neighbor multiset, full retained graph bonds and encoded stereo. Every retained-graph bijection therefore lifts to a full-graph parent projection; remaining ordinary-H permutations leave that projection unchanged. All retained-graph matches are enumerated unless truncated.")
    result = _base(binding)
    result.update(status="unknown" if truncated else "complete", complete=not truncated,
        enumeration_truncated=truncated,
        joint_maps=tuple(dict(enumerate(row)) for row in ordered),
        graph_lineage_evidence_sha256=_digest(lineage),
        completeness_evidence_sha256=None if truncated else _digest(proof),
        graph_lineage_evidence=lineage, completeness_evidence=proof,
        canonical_smiles=canonical, rdkit_version=rdBase.rdkitVersion,
        source_atom_count=n, baseline_parent_count=len(heavy),
        parent_projection_count=len(ordered),
        reason_codes=("mapping_cap_hit",) if truncated else ())
    return result


def _worker(connection, args):
    try:
        connection.send((True, _transport_impl(*args)))
    except Exception as exc:
        connection.send((False, type(exc).__name__ + ":" + str(exc)))
    finally:
        connection.close()


def build_source_transport(structure_record, *, binding, baseline_smiles=None,
                           baseline_parent_ids=None, max_maps=4096,
                           time_limit_seconds=2.0, expected_rdkit_version=None):
    """Return a source_reference-compatible receipt for the declared graph only.

    Required structure fields: smiles, atoms, atom_order (basis/source_to_canonical/
    atomic_numbers), source_ref, nucleus, record_id; structure_id is optional.
    binding has source,nucleus,record_id,structure_id and the four HASH_FIELDS.
    The caller must extract structure_record from the exact hash-bound source row;
    this function cannot rehash a label-bearing row from its structural subset.
    Missing original mol/stereo never changes this result into experimental truth.
    Call from an import-safe main/thread, not a daemonic multiprocessing worker.
    """
    start = time.monotonic()
    if not isinstance(binding, Mapping) or set(binding) != set(IDENTITY_FIELDS + HASH_FIELDS):
        raise ValueError("exact_source_reference_binding_required")
    if (any(not isinstance(binding[k], str) or not binding[k] for k in IDENTITY_FIELDS)
            or any(not _sha(binding[k]) for k in HASH_FIELDS)):
        raise ValueError("invalid_reference_binding")
    if (type(max_maps) is not int or not 1 <= max_maps <= 10000
            or isinstance(time_limit_seconds, bool) or not isinstance(time_limit_seconds, (int, float))
            or not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0):
        raise ValueError("finite_positive_budget_and_bounded_map_limit_required")
    result = _base(binding)
    try:
        smiles = structure_record["smiles"]
        if not isinstance(smiles, str) or not smiles:
            raise ValueError("source_smiles_required")
        sid = structure_record.get("structure_id") or hashlib.sha256(smiles.encode()).hexdigest()
        actual = (structure_record["source_ref"], structure_record["nucleus"],
                  structure_record["record_id"], sid)
        if actual != tuple(binding[k] for k in IDENTITY_FIELDS):
            raise ValueError("source_identity_binding_mismatch")
        order = structure_record["atom_order"]
        # Explicit whitelist: never access coordinates, labels, mask, or spectrum.
        payload = dict(smiles=smiles, atoms=list(structure_record["atoms"]),
            atom_order={k: order[k] for k in ("basis", "source_to_canonical", "atomic_numbers")})
        payload = json.loads(json.dumps(payload, allow_nan=False))
        if len(json.dumps(payload)) > 1024 * 1024:
            raise ValueError("structure_payload_limit")
        if not 1 <= len(payload["atoms"]) <= 192:
            raise ValueError("structure_atom_limit")
        if expected_rdkit_version is not None and not isinstance(expected_rdkit_version, str):
            raise ValueError("rdkit_version_must_be_string")
        parent_ids = None if baseline_parent_ids is None else dict(baseline_parent_ids)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        result.update(status="invalid", reason_codes=(str(exc),))
        return result
    if multiprocessing.current_process().daemon:
        result["reason_codes"] = ("daemonic_worker_cannot_enforce_transport_subprocess_budget",)
        return result
    implementation_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(child, (payload, dict(binding), baseline_smiles,
        parent_ids, max_maps, expected_rdkit_version, implementation_sha)), daemon=True)
    try:
        process.start()
        child.close()
        remaining = time_limit_seconds - (time.monotonic() - start)
        if remaining <= 0 or not parent.poll(remaining):
            result["reason_codes"] = ("transport_time_limit",)
        else:
            ok, value = parent.recv()
            if time.monotonic() - start > time_limit_seconds:
                result["reason_codes"] = ("transport_time_limit",)
            elif ok:
                result = value
            else:
                result.update(status="invalid", reason_codes=(value,))
    except (OSError, EOFError, RuntimeError) as exc:
        result["reason_codes"] = ("transport_worker_failure:" + type(exc).__name__,)
    finally:
        if process.is_alive():
            process.terminate()
        if process.pid is not None:
            process.join(timeout=.2)
            if process.is_alive():
                process.kill()
                process.join(timeout=.2)
        parent.close()
        child.close()
    result["elapsed_seconds"] = time.monotonic() - start
    return result


def restore_joint_map_keys(receipt):
    """Restore exact integer slot keys after JSON; reject aliases such as '01'."""
    out = dict(receipt)
    restored = []
    for mapping in receipt.get("joint_maps", ()):
        converted = {}
        for key, value in mapping.items():
            if type(key) is int and key >= 0:
                index = key
            elif isinstance(key, str) and key.isdecimal() and str(int(key)) == key:
                index = int(key)
            else:
                raise ValueError("noncanonical_source_slot_key")
            if index in converted or not isinstance(value, str) or not value:
                raise ValueError("duplicate_or_invalid_source_slot")
            converted[index] = value
        if set(converted) != set(range(len(converted))):
            raise ValueError("source_slot_domain_not_complete")
        restored.append(converted)
    out["joint_maps"] = tuple(restored)
    return out
