"""功能概述：验证源相对结构 transport 的完整联合父节点投影与有界回退。
主要职责：构造标签无关的合成图，检查重编号、跨 parent 联合置换、H 压缩证明、
同位素/立体约束和 source_reference 接线。测试不用模型、外部数据或真实位移。
关系：只调用 source_transport 的公开接口；额外结构审计可运行本文件的
--reviewed-structures PATH 入口，它仅选取已审记录的结构白名单字段，不计算准确率。
输入输出与副作用：单元测试只读现有 RDKit；检查入口输出结构 receipt 摘要。
"""
import hashlib
import json
from pathlib import Path
import sys
import unittest

from rdkit import Chem, rdBase
from nmr_assignment.source_transport import (
    build_source_transport, restore_joint_map_keys, HASH_FIELDS)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def record(smiles, permutation=None):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    permutation = list(range(mol.GetNumAtoms())) if permutation is None else list(permutation)
    return dict(smiles=smiles, source_ref="synthetic", nucleus="1H", record_id="synthetic-id",
        atoms=[mol.GetAtomWithIdx(i).GetSymbol() for i in permutation],
        atom_order=dict(basis="source_mol", source_to_canonical=permutation,
            atomic_numbers=[mol.GetAtomWithIdx(i).GetAtomicNum() for i in permutation]))


def binding(row):
    return dict(source=row["source_ref"], nucleus=row["nucleus"], record_id=row["record_id"],
        structure_id=row.get("structure_id") or digest(row["smiles"]),
        **{k: digest(k) for k in HASH_FIELDS})


def transport(row, **kwargs):
    return build_source_transport(row, binding=binding(row), time_limit_seconds=10, **kwargs)


def family(result):
    return {tuple(m[i] for i in range(len(m))) for m in result["joint_maps"]}


class SourceTransportTests(unittest.TestCase):
    def complete(self, value):
        self.assertTrue(value["complete"], value.get("reason_codes"))
        self.assertFalse(value["enumeration_truncated"])
        self.assertEqual(value["truth_basis"], "source_relative_current_serialization")
        self.assertFalse(value["experimental_atom_order_verified"])
        self.assertEqual(value["original_stereo_status"], "unknown")
        return value

    def test_ch3_ch2_oh_parent_projection(self):
        row = record("CCO")
        out = self.complete(transport(row, max_maps=1))
        self.assertEqual(out["parent_projection_count"], 1)
        mapping = out["joint_maps"][0]
        mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
        for atom in mol.GetAtoms():
            parent = atom.GetNeighbors()[0].GetIdx() if atom.GetAtomicNum() == 1 else atom.GetIdx()
            self.assertEqual(mapping[atom.GetIdx()], str(parent))
        self.assertEqual(sorted(len(v) for v in out["graph_lineage_evidence"]["source_suppressed_H_by_parent"].values()), [1, 2, 3])

    def test_cross_parent_orbit_keeps_joint_alternatives(self):
        row = record("CC")
        out = self.complete(transport(row))
        self.assertEqual(out["parent_projection_count"], 2)
        mol = Chem.AddHs(Chem.MolFromSmiles("CC"))
        for mapping in out["joint_maps"]:
            self.assertNotEqual(mapping[0], mapping[1])
            for atom in mol.GetAtoms():
                if atom.GetAtomicNum() == 1:
                    self.assertEqual(mapping[atom.GetIdx()], mapping[atom.GetNeighbors()[0].GetIdx()])
        self.assertEqual({(m[0], m[1]) for m in out["joint_maps"]}, {("0", "1"), ("1", "0")})

    def test_source_slot_renumbering_transports_entire_family(self):
        row = record("CC")
        original = self.complete(transport(row))
        permutation = list(reversed(range(len(row["atoms"]))))
        reordered = self.complete(transport(record("CC", permutation)))
        expected = {tuple(m[i] for i in permutation) for m in original["joint_maps"]}
        self.assertEqual(family(reordered), expected)

    def test_input_graph_order_not_canonical_parent_order(self):
        row = record("OCC")
        out = self.complete(transport(row))
        self.assertEqual(out["canonical_smiles"], "CCO")
        self.assertEqual(tuple(out["joint_maps"][0][i] for i in range(3)), ("2", "1", "0"))

    def test_H_factorial_does_not_consume_parent_map_budget(self):
        out = self.complete(transport(record("CCCCCCO"), max_maps=1))
        self.assertEqual(out["completeness_evidence"]["raw_compressed_matches_returned"], 1)
        self.assertGreater(out["source_atom_count"], 20)
        self.assertEqual(out["completeness_evidence"]["compressed_source_atoms"], 7)

    def test_cap_is_unknown_even_with_partial_maps(self):
        out = transport(record("CC"), max_maps=1)
        self.assertFalse(out["complete"])
        self.assertTrue(out["enumeration_truncated"])
        self.assertIsNone(out["completeness_evidence_sha256"])
        self.assertIn("mapping_cap_hit", out["reason_codes"])

    def test_isotope_breaks_parent_symmetry(self):
        out = self.complete(transport(record("[13CH3]C")))
        self.assertEqual(out["parent_projection_count"], 1)
        out = self.complete(transport(record("[2H]CC")))
        self.assertEqual(out["parent_projection_count"], 1)
        self.assertEqual(out["completeness_evidence"]["compressed_source_atoms"], 3)
        # Deuterium remains in the retained graph, but evaluation maps it to parent.
        self.assertEqual(out["joint_maps"][0][0], out["joint_maps"][0][1])

    def test_chiral_graph_renumbering_preserves_parity(self):
        for smiles in ("F[C@](Cl)(Br)I", "C[C@H](O)Cl", "F[C@@](Cl)(Br)I"):
            with self.subTest(smiles=smiles):
                self.complete(transport(record(smiles)))
        # A different enantiomer is not accepted as the expected baseline graph.
        out = transport(record("F[C@](Cl)(Br)I"), baseline_smiles="F[C@@](Cl)(Br)I")
        self.assertFalse(out["complete"])

    def test_alkene_aromatic_charge_and_exchange_H(self):
        for smiles in ("F/C=C/F", "F/C=C\\F", "[nH]1cccc1", "C[NH2+]C", "NC=O"):
            with self.subTest(smiles=smiles):
                self.complete(transport(record(smiles)))

    def test_DMF_N_methyls_remain_joint_parent_orbit(self):
        out = self.complete(transport(record("CN(C)C=O")))
        self.assertEqual(out["parent_projection_count"], 2)
        self.assertEqual({m[0] for m in out["joint_maps"]}, {"0", "2"})
        self.assertEqual({(m[0], m[2]) for m in out["joint_maps"]}, {("0", "2"), ("2", "0")})

    def test_wrong_or_missing_order_declaration_rejected(self):
        for mutation in ("basis", "permutation", "elements", "atoms"):
            row = record("CO")
            if mutation == "basis":
                row["atom_order"].pop("basis")
            elif mutation == "permutation":
                row["atom_order"]["source_to_canonical"][0] = 1
            elif mutation == "elements":
                row["atom_order"]["atomic_numbers"][0] = 8
            else:
                row["atoms"][0] = "O"
            with self.subTest(mutation=mutation):
                self.assertFalse(transport(row)["complete"])

    def test_equal_elements_do_not_certify_original_order(self):
        row = record("CCC", [2, 1, 0] + list(range(3, 11)))
        out = self.complete(transport(row))
        self.assertFalse(out["graph_lineage_evidence"]["source_original_graph_verified"])
        self.assertEqual(out["parent_projection_count"], 2)

    def test_baseline_ID_domain_and_version(self):
        row = record("CO")
        out = self.complete(transport(row, baseline_parent_ids={0: "C0", 1: "O1"}, expected_rdkit_version=rdBase.rdkitVersion))
        self.assertEqual(set(out["joint_maps"][0].values()), {"C0", "O1"})
        for kwargs in ({"baseline_parent_ids": {0: "same", 1: "same"}},
                       {"baseline_parent_ids": {0: "C0"}},
                       {"expected_rdkit_version": "not-current"},
                       {"baseline_smiles": "OC"}):
            self.assertFalse(transport(row, **kwargs)["complete"])

    def test_unsupported_graph_forms_fail_closed(self):
        for smiles in ("C.C", "[CH3:1]O", "[H][H]", "F[Pt@SP1](Cl)(Br)I"):
            with self.subTest(smiles=smiles):
                self.assertFalse(transport(record(smiles))["complete"])

    def test_does_not_access_labels_coordinates_or_inchikey(self):
        class StructureOnly(dict):
            def __getitem__(self, key):
                if key in {"atom_targets", "atom_target_mask", "spectrum", "coordinates", "source_inchikey"}:
                    raise AssertionError("forbidden field read")
                return super().__getitem__(key)
            def get(self, key, default=None):
                return self[key] if key in self else default
        row = StructureOnly(record("CCO"))
        for key in ("atom_targets", "atom_target_mask", "spectrum", "coordinates", "source_inchikey"):
            row[key] = object()
        self.complete(transport(row))

    def test_timeout_and_bad_budgets(self):
        row = record("CC")
        out = build_source_transport(row, binding=binding(row), time_limit_seconds=1e-9)
        self.assertFalse(out["complete"])
        self.assertIn("transport_time_limit", out["reason_codes"])
        for kwargs in ({"max_maps": True}, {"max_maps": 0}, {"max_maps": 10001}, {"time_limit_seconds": float("inf")}):
            with self.assertRaises(ValueError):
                build_source_transport(row, binding=binding(row), **kwargs)

    def test_binding_and_json_map_restoration(self):
        row = record("CO")
        bad = binding(row)
        bad["record_id"] = "another"
        self.assertFalse(build_source_transport(row, binding=bad)["complete"])
        out = self.complete(transport(row))
        self.assertEqual(family(out), family(restore_joint_map_keys(json.loads(json.dumps(out)))))
        for mapping in ({"01": "a"}, {"1": "a"}, {True: "a"}, {0: "a", "0": "b"}):
            with self.assertRaises(ValueError):
                restore_joint_map_keys({"joint_maps": [mapping]})

    def test_source_reference_integration_preserves_joint_orbit(self):
        from nmr_assignment.source_reference import build_source_reference
        row = record("CC")
        n = len(row["atoms"])
        row.update(coordinates=[[0, 0, 0]] * n, atom_targets=[None] * n,
                   atom_target_mask=[0] * n, spectrum=[])
        # Purely synthetic distinct reported H values; transport never receives them.
        for i, value in ((2, 1), (5, 2)):
            row["atom_targets"][i] = value
            row["atom_target_mask"][i] = 1
            row["spectrum"].append(dict(atom_index=i, shift=value))
        raw = json.dumps(row) + "\n"
        b = binding(row)
        b["row_sha256"] = digest(raw)
        identity = {k: b[k] for k in ("source", "nucleus", "record_id", "structure_id")}
        policy = json.dumps(dict(identity, row_sha256=b["row_sha256"],
            keep_atom_parent_supervision=True, disposition="source_relative_keep")) + "\n"
        b["policy_sha256"] = digest(policy)
        manifest = json.dumps(dict(source_sha256=b["source_sha256"], policy_sha256=b["policy_sha256"],
            records=[dict(identity, row_sha256=b["row_sha256"])]))
        b["cohort_identity_manifest_sha256"] = digest(manifest)
        t = self.complete(build_source_transport(row, binding=b, time_limit_seconds=10))
        ref = build_source_reference(raw, source_sha256=b["source_sha256"], policy_jsonl=policy,
            policy_sha256=b["policy_sha256"], cohort_manifest_json=manifest,
            cohort_identity_manifest_sha256=b["cohort_identity_manifest_sha256"], transport=t)
        self.assertEqual(ref.reasons, ())
        self.assertEqual(ref.classification, "parent_mapping_ambiguous")
        self.assertEqual(len(ref.hidden["joint_gold_variants"]), 2)


def reviewed_structures(path):
    """Structure-only audit entry point for the already reviewed twelve rows."""
    output = []
    for literal in Path(path).read_text().splitlines():
        obj = json.loads(literal)
        row = {k: obj[k] for k in ("smiles", "source_ref", "nucleus", "record_id", "atoms", "atom_order")}
        if obj.get("structure_id"):
            row["structure_id"] = obj["structure_id"]
        b = binding(row)
        b["row_sha256"] = digest(literal)
        result = build_source_transport(row, binding=b, time_limit_seconds=10)
        output.append({k: result.get(k) for k in ("record_id", "nucleus", "status", "complete",
            "source_atom_count", "baseline_parent_count", "parent_projection_count", "reason_codes",
            "rdkit_version", "graph_lineage_evidence_sha256", "completeness_evidence_sha256")})
    print(json.dumps(dict(kind="reviewed_structure_only_not_accuracy", records=output), sort_keys=True))
    return 0 if all(row["complete"] for row in output) else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--reviewed-structures":
        raise SystemExit(reviewed_structures(sys.argv[2]))
    unittest.main()
