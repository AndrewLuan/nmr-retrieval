# 功能概述：用合成行检验source_reference的限制传递、精确join及联合SET投影。
# 主要职责：fixture仅生成虚构源行/策略/身份/transport；各测试断言失败关闭及匿名边界。
# 代码库关系：仅调用nmr_assignment.source_reference，无真实trainval/test、文件数据或模型。
# 输入输出：内存合成JSON，无持久写入；不以合成通过宣称来源认证。
import json
import unittest
from nmr_assignment.source_reference import build_source_reference, text_sha256, coverage_ledger


class SourceReferenceTest(unittest.TestCase):
    def fixture(self, change=None, disposition="no_detected_local_conflict", absent=False):
        row = dict(source_ref="synthetic", nucleus="1H", record_id="r", smiles="CC",
                   atoms=["C", "H", "H", "H"], coordinates=[[0, 0, 0]] * 4,
                   atom_targets=[None, 1.0, 1.0, 2.0], atom_target_mask=[0, 1, 1, 1],
                   spectrum=[dict(atom_index=i, shift=v) for i, v in [(1, 1.0), (2, 1.0), (3, 2.0)]],
                   atom_order=dict(source_to_canonical=[0, 1, 2, 3], atomic_numbers=[6, 1, 1, 1]))
        if change:
            change(row)
        raw = json.dumps(row)
        identity = dict(source="synthetic", nucleus=row["nucleus"], record_id="r",
                        structure_id=text_sha256("CC"))
        policy = dict(identity, row_sha256=text_sha256(raw),
                      keep_atom_parent_supervision=True, quality=disposition)
        policy_text = "" if absent else json.dumps(policy)
        manifest = json.dumps(dict(source_sha256="a" * 64, policy_sha256=text_sha256(policy_text),
                                   records=[dict(identity, row_sha256=text_sha256(raw))]))
        binding = dict(identity, row_sha256=text_sha256(raw), source_sha256="a" * 64,
                       policy_sha256=text_sha256(policy_text),
                       cohort_identity_manifest_sha256=text_sha256(manifest))
        transport = dict(binding, complete=True, enumeration_truncated=False,
                         completeness_evidence_sha256="b" * 64, structure_only=True,
                         graph_lineage_evidence_sha256="c" * 64,
                         joint_maps=[{0: "c", 1: "A", 2: "A", 3: "B"},
                                     {0: "c", 1: "B", 2: "B", 3: "A"}])
        args = dict(source_sha256="a" * 64, policy_jsonl=policy_text,
                    policy_sha256=text_sha256(policy_text), cohort_manifest_json=manifest,
                    cohort_identity_manifest_sha256=text_sha256(manifest), transport=transport)
        return raw, args

    def test_joint_sets_preserve_global_alternatives(self):
        raw, args = self.fixture()
        result = build_source_reference(raw, **args)
        self.assertEqual(result.classification, "parent_mapping_ambiguous")
        self.assertEqual(result.hidden["joint_gold_variants"], (
            (("bin:0", ("A",)), ("bin:1", ("B",))),
            (("bin:0", ("B",)), ("bin:1", ("A",)))))
        self.assertEqual(set(result.anonymous_payload()[0]), {"bin_id", "ppm_decimal"})
        self.assertEqual(result.status, "proposed_receipt")
        self.assertFalse(result.hidden["trusted_experimental"])
        self.assertEqual(coverage_ledger([result])[0]["status"], "proposed_receipt")

    def test_same_parent_across_bins_and_mask_not_expanded(self):
        raw, args = self.fixture(lambda r: r.update(atom_targets=[None, 1.0, None, 2.0], atom_target_mask=[0, 1, 0, 1],
            spectrum=[dict(atom_index=1, shift=1.0), dict(atom_index=3, shift=2.0)]))
        args["transport"]["joint_maps"] = [{0: "c", 1: "A", 2: "UNLABELED", 3: "A"}]
        result = build_source_reference(raw, **args)
        self.assertEqual(result.hidden["joint_gold_variants"],
                         ((("bin:0", ("A",)), ("bin:1", ("A",))),))
        self.assertNotIn("UNLABELED", str(result.hidden["joint_gold_variants"]))

    def test_hold_mask_weak_preserved(self):
        for disposition in ["hold_experimental_domain_pending_provenance",
                            "mask_atom_keep_spectrum", "conditional_weak_supervision_candidate"]:
            raw, args = self.fixture(disposition=disposition)
            result = build_source_reference(raw, **args)
            self.assertEqual(result.classification, "restricted")
            self.assertIn("policy_restricted", result.reasons)

    def test_absent_policy_unknown(self):
        raw, args = self.fixture(absent=True)
        result = build_source_reference(raw, **args)
        self.assertEqual(result.classification, "unknown")
        self.assertIn("policy_missing", result.reasons)

    def test_padding_and_nucleus_rejected(self):
        for change, reason in [
            (lambda r: r["atom_order"]["atomic_numbers"].__setitem__(0, 0), "atom_order_or_padding_invalid"),
            (lambda r: r.update(nucleus="13C"), "nucleus_element_mismatch"),
            (lambda r: r["atom_order"].update(source_to_canonical=[0, 1, 1, 3]), "atom_order_or_padding_invalid"),
            (lambda r: r["atom_target_mask"].__setitem__(1, 2), "mask_invalid")]:
            raw, args = self.fixture(change)
            result = build_source_reference(raw, **args)
            self.assertEqual(result.classification, "unknown")
            self.assertIn(reason, result.reasons)

    def test_duplicate_join_rejected_even_identical(self):
        raw, args = self.fixture()
        args["policy_jsonl"] += "\n" + args["policy_jsonl"]
        args["policy_sha256"] = text_sha256(args["policy_jsonl"])
        args["transport"]["policy_sha256"] = args["policy_sha256"]
        result = build_source_reference(raw, **args)
        self.assertIn("policy_duplicate_conflicting_join", result.reasons)
        self.assertEqual(result.classification, "unknown")

    def test_complete_maps_do_not_prove_complete_set(self):
        raw, args = self.fixture()
        args["transport"]["complete"] = False
        result = build_source_reference(raw, **args)
        self.assertIn("joint_mapping_completeness_unknown", result.reasons)
        self.assertEqual(result.classification, "unknown")

    def test_incomplete_map_rejected(self):
        raw, args = self.fixture()
        del args["transport"]["joint_maps"][0][2]
        self.assertIn("joint_map_domain_invalid", build_source_reference(raw, **args).reasons)

    def test_empty_mask_has_no_scoreable_reference(self):
        raw, args = self.fixture(lambda r: r.update(
            atom_targets=[None, None, None, None],
            atom_target_mask=[0, 0, 0, 0], spectrum=[]))
        result = build_source_reference(raw, **args)
        self.assertIn("no_known_labels", result.reasons)
        self.assertEqual(result.classification, "unknown")
        self.assertEqual(result.inference_bins, ())
        self.assertNotEqual(result.classification, "unique_parent")

    def test_all_118_elements_for_H_and_C_reference_encoding(self):
        from nmr_assignment.source_reference import ELEMENT_SYMBOLS
        self.assertEqual(len(ELEMENT_SYMBOLS), 118)
        self.assertEqual(len(set(ELEMENT_SYMBOLS)), 118)
        for nucleus in ("1H", "13C"):
            for z, symbol in enumerate(ELEMENT_SYMBOLS, 1):
                for token in (symbol, z):
                    def change(row):
                        if nucleus == "13C":
                            row.update(nucleus="13C", atom_targets=[12, None, None, None],
                                atom_target_mask=[1, 0, 0, 0],
                                spectrum=[dict(atom_index=0, shift=12)])
                            slot = 1
                        else:
                            slot = 0
                        row["atoms"][slot] = token
                        row["atom_order"]["atomic_numbers"][slot] = z
                    raw, args = self.fixture(change)
                    result = build_source_reference(raw, **args)
                    self.assertNotIn("atom_order_or_padding_invalid", result.reasons, (nucleus, token))
                    self.assertNotIn("nucleus_element_mismatch", result.reasons, (nucleus, token))
                    self.assertIn(result.classification, ("unique_parent", "parent_mapping_ambiguous"))

    def test_element_tokens_and_numbers_reject_padding_bool_and_out_of_range(self):
        from nmr_assignment.source_reference import _atomic_number
        for token in (True, False, 0, -1, 119, 1.0, "0", "119", "X", "cl", "", None):
            self.assertIsNone(_atomic_number(token), repr(token))
        for token, number in ((True, 1), ("H", True), ("Og", 119), (0, 0),
                              (119, 119), ("Unknown", 6)):
            raw, args = self.fixture(lambda r: (r["atoms"].__setitem__(0, token),
                r["atom_order"]["atomic_numbers"].__setitem__(0, number)))
            self.assertIn("atom_order_or_padding_invalid", build_source_reference(raw, **args).reasons)

    def test_original_tokens_unchanged(self):
        raw, args = self.fixture()
        result = build_source_reference(raw, **args)
        self.assertEqual(result.hidden["raw_json_line"], raw)
        self.assertEqual(result.hidden["derived"].hidden_provenance[0].members,
                         ((1, "1.0"), (2, "1.0")))

    def normalize_fixture(self, *, quality="no_detected_local_conflict", corrections=()):
        from nmr_assignment.source_reference import normalize_policy_rows
        raw, args = self.fixture()
        original = json.dumps(dict(source="synthetic", record_id="r", smiles="CC",
            keep_atom_parent_supervision=True, quality=quality)) + "\n"
        norm = normalize_policy_rows([raw], original_policy_jsonl=original,
            original_policy_sha256=text_sha256(original), nucleus_scope="1H",
            canonicalize_structure=lambda s: s, adapter_implementation_sha256="d" * 64,
            correction_record_ids=corrections,
            correction_overlay_sha256="e" * 64 if corrections else None)
        args["policy_jsonl"] = norm["policy_jsonl"]
        args["policy_sha256"] = norm["policy_sha256"]
        manifest = json.loads(args["cohort_manifest_json"])
        manifest["policy_sha256"] = norm["policy_sha256"]
        manifest["normalized_policy_provenance"] = norm["manifest_bindings"]
        args["cohort_manifest_json"] = json.dumps(manifest)
        args["cohort_identity_manifest_sha256"] = text_sha256(args["cohort_manifest_json"])
        args["transport"].update(policy_sha256=args["policy_sha256"],
            cohort_identity_manifest_sha256=args["cohort_identity_manifest_sha256"])
        return raw, args, norm, original

    def test_normalized_legacy_schema_retains_raw_and_bindings(self):
        raw, args, norm, original = self.normalize_fixture()
        p = json.loads(norm["policy_jsonl"])
        self.assertEqual(p["_normalization"]["original_policy_line"], original)
        self.assertEqual(p["_normalization"]["original_policy_line_sha256"], text_sha256(original))
        self.assertEqual(p["row_sha256"], text_sha256(raw))
        self.assertEqual(p["quality"], "no_detected_local_conflict")
        self.assertEqual(build_source_reference(raw, **args).classification, "parent_mapping_ambiguous")

    def test_normalized_hold_and_raw_historical_correction_restricted(self):
        for quality, corrections in [("hold_experimental_domain_pending_provenance", ()),
                                     ("no_detected_local_conflict", ("r",))]:
            raw, args, norm, _ = self.normalize_fixture(quality=quality, corrections=corrections)
            self.assertEqual(json.loads(norm["policy_jsonl"])["quality"], quality)
            self.assertEqual(build_source_reference(raw, **args).classification, "restricted")

    def test_normalization_refuses_mismatch_duplicate_and_wrong_scope(self):
        from nmr_assignment.source_reference import normalize_policy_rows
        raw, _ = self.fixture()
        policy = json.dumps(dict(source="synthetic", record_id="r", smiles="DIFFERENT"))
        def call(text, canonical=lambda s: s, scope="1H"):
            return normalize_policy_rows([raw], original_policy_jsonl=text,
                original_policy_sha256=text_sha256(text), nucleus_scope=scope,
                canonicalize_structure=canonical, adapter_implementation_sha256="d" * 64)
        with self.assertRaisesRegex(ValueError, "canonical structure mismatch"):
            call(policy)
        with self.assertRaisesRegex(ValueError, "duplicate/conflicting"):
            call(policy + "\n" + policy)
        scoped = call(policy, scope="13C")
        self.assertEqual(scoped["policy_jsonl"], "")
        self.assertEqual(len(scoped["missing_policy_identities"]), 1)

    def test_normalized_quality_cannot_be_promoted(self):
        raw, args, _, _ = self.normalize_fixture(quality="mask_atom_keep_spectrum")
        policy = json.loads(args["policy_jsonl"])
        policy["quality"] = "no_detected_local_conflict"
        args["policy_jsonl"] = json.dumps(policy) + "\n"
        args["policy_sha256"] = text_sha256(args["policy_jsonl"])
        manifest = json.loads(args["cohort_manifest_json"])
        manifest["policy_sha256"] = args["policy_sha256"]
        args["cohort_manifest_json"] = json.dumps(manifest)
        args["cohort_identity_manifest_sha256"] = text_sha256(args["cohort_manifest_json"])
        args["transport"].update(policy_sha256=args["policy_sha256"],
            cohort_identity_manifest_sha256=args["cohort_identity_manifest_sha256"])
        result = build_source_reference(raw, **args)
        self.assertIn("normalized_policy_semantics_changed", result.reasons)
        self.assertEqual(result.classification, "unknown")

    def test_normalized_manifest_adapter_hash_required(self):
        raw, args, _, _ = self.normalize_fixture()
        manifest = json.loads(args["cohort_manifest_json"])
        del manifest["normalized_policy_provenance"]
        args["cohort_manifest_json"] = json.dumps(manifest)
        args["cohort_identity_manifest_sha256"] = text_sha256(args["cohort_manifest_json"])
        args["transport"]["cohort_identity_manifest_sha256"] = args["cohort_identity_manifest_sha256"]
        self.assertIn("normalized_policy_provenance_mismatch",
                      build_source_reference(raw, **args).reasons)

    def test_imputed_and_inactive_target_do_not_pass(self):
        raw, args = self.fixture()
        policy = json.loads(args["policy_jsonl"])
        policy["shift_values_imputed"] = True
        args["policy_jsonl"] = json.dumps(policy)
        args["policy_sha256"] = text_sha256(args["policy_jsonl"])
        manifest = json.loads(args["cohort_manifest_json"])
        manifest["policy_sha256"] = args["policy_sha256"]
        args["cohort_manifest_json"] = json.dumps(manifest)
        args["cohort_identity_manifest_sha256"] = text_sha256(args["cohort_manifest_json"])
        args["transport"].update(policy_sha256=args["policy_sha256"],
            cohort_identity_manifest_sha256=args["cohort_identity_manifest_sha256"])
        self.assertIn("policy_restricted", build_source_reference(raw, **args).reasons)
        raw, args = self.fixture(lambda r: r["atom_target_mask"].__setitem__(2, 0))
        self.assertIn("inactive_target_not_null", build_source_reference(raw, **args).reasons)

    def test_compiled_context_same_semantics_and_double_binding(self):
        from nmr_assignment.source_reference import compile_reference_context
        raw, args = self.fixture()
        context = compile_reference_context(args["policy_jsonl"], args["policy_sha256"],
            args["cohort_manifest_json"], args["cohort_identity_manifest_sha256"])
        first = build_source_reference(raw, **args)
        second = build_source_reference(raw, **args, context=context)
        self.assertEqual(first.reasons, second.reasons)
        self.assertEqual(first.hidden["joint_gold_variants"], second.hidden["joint_gold_variants"])
        self.assertEqual(first.classification, second.classification)
        args["policy_jsonl"] += " "
        rejected = build_source_reference(raw, **args, context=context)
        self.assertEqual(rejected.classification, "unknown")
        with self.assertRaises(ValueError):
            compile_reference_context(args["policy_jsonl"], args["policy_sha256"],
                args["cohort_manifest_json"], args["cohort_identity_manifest_sha256"])


if __name__ == "__main__":
    unittest.main()
