"""功能概述：用原始合成 JSON token 检查 derived-observation 的匿名与精度边界。
主要职责：检验十进制精确合并、literal provenance、mask 覆盖、字段拒绝，以及联合
映射整份备选不能被并集替换；不认证真实来源或 gold，不运行真实样本或模型。
代码库关系：仅依赖 derived_observation；标准 unittest，无持久化或网络副作用。
"""
import unittest
from nmr_assignment.derived_observation import (
    AnonymousBin, build_serialized_value_bins as build, project_hidden_membership as project,
)


class DerivedObservationTests(unittest.TestCase):
    def test_decimal_precision_and_equal_numeric_literals(self):
        result = build('{"atom_targets":[0.1,0.10000000000000001,1,1.0,1e0],"atom_target_mask":[1,1,1,1,1]}')
        self.assertEqual(len(result.inference_bins), 3)
        self.assertEqual(result.inference_bins[0].ppm_decimal, "1e-1")
        self.assertEqual(result.inference_bins[1].ppm_decimal, "10000000000000001e-17")
        self.assertEqual(result.hidden_provenance[2].members, ((2,"1"),(3,"1.0"),(4,"1e0")))
        self.assertEqual(result.original_precision, "unknown")
        self.assertEqual(result.gold_status, "not_trusted_gold")

    def test_anonymous_boundary_only_id_and_value(self):
        result = build('{"atom_targets":[1,1],"atom_target_mask":[true,true],"source":"hidden","gold":true}')
        self.assertEqual(result.anonymous_payload(), ({"bin_id":"bin:0","ppm_decimal":"1"},))
        for key in ("members", "source", "record", "gold", "capacity", "integrals"):
            with self.assertRaises(ValueError):
                AnonymousBin.from_mapping(dict(result.anonymous_payload()[0], **{key:1}))
        self.assertNotIn("members", repr(result))

    def test_mask_missing_empty_partial_are_explicit(self):
        with self.assertRaises(ValueError): build('{"atom_targets":[1]}')
        partial = build('{"atom_targets":[1,null,2],"atom_target_mask":[1,0,0]}')
        self.assertEqual(partial.mask_coverage, "partial")
        self.assertEqual(partial.reported_slot_count, 1)
        empty = build('{"atom_targets":[null],"atom_target_mask":[false]}')
        self.assertEqual(empty.mask_coverage, "empty")
        self.assertEqual(empty.anonymous_payload(), ())
        self.assertEqual(build('{"atom_targets":[],"atom_target_mask":[]}').mask_coverage,"empty")

    def test_joint_alternatives_remain_whole_and_deduplicate_whole(self):
        result = build('{"atom_targets":[1,2],"atom_target_mask":[1,1]}')
        a, b = {0:"H0",1:"H1"}, {0:"H1",1:"H0"}
        variants = project(result, [a,b,a])
        self.assertEqual(len(variants), 2)
        self.assertEqual(variants, (
            (("bin:0",("H0",)),("bin:1",("H1",))),
            (("bin:0",("H1",)),("bin:1",("H0",))),
        ))
        for invalid in ([], [{0:"H0"}], [{0:"H0",1:"H0"}]):
            with self.assertRaises(ValueError): project(result, invalid)

    def test_unreported_slots_still_require_complete_external_mapping(self):
        result = build('{"atom_targets":[1,null],"atom_target_mask":[1,0]}')
        with self.assertRaises(ValueError): project(result,[{0:"H0"}])
        self.assertEqual(project(result,[{0:"H0",1:"H1"}]), ((("bin:0",("H0",)),),))

    def test_source_permutation_preserves_anonymous_payload_and_joint_projection(self):
        a = build('{"atom_targets":[2.0,1,2,null],"atom_target_mask":[1,1,1,0]}')
        b = build('{"atom_targets":[null,2,2.00,1.0],"atom_target_mask":[0,1,1,1]}')
        self.assertEqual(a.anonymous_payload(), b.anonymous_payload())
        self.assertEqual(a.anonymous_payload(), (
            {"bin_id":"bin:0","ppm_decimal":"1"},
            {"bin_id":"bin:1","ppm_decimal":"2"}))
        maps_a = [{0:"H0",1:"H1",2:"H2",3:"H3"},
                  {0:"H1",1:"H0",2:"H2",3:"H3"}]
        # New slots reference old slots [3,2,0,1]; move the complete maps together.
        maps_b = [{new:m[old] for new,old in enumerate([3,2,0,1])} for m in maps_a]
        self.assertEqual(project(a,maps_a), project(b,maps_b))
        self.assertEqual(len(project(b,maps_b)), 2)
        # No context-dependent normalize(): all significant digits survive.
        precise = build('{"atom_targets":[123456789012345678901234567890.00],"atom_target_mask":[1]}')
        self.assertEqual(precise.inference_bins[0].ppm_decimal, "12345678901234567890123456789e1")

    def test_invalid_json_numeric_and_column_shape(self):
        for raw in ('{"atom_targets":[NaN],"atom_target_mask":[1]}',
                    '{"atom_targets":["1"],"atom_target_mask":[1]}',
                    '{"atom_targets":[[1]],"atom_target_mask":[1]}',
                    '{"atom_targets":[1],"atom_target_mask":[2]}',
                    '{"atom_targets":[1],"atom_target_mask":[]}',
                    '{"atom_targets":[1],"atom_targets":[2],"atom_target_mask":[1]}'):
            with self.assertRaises(ValueError): build(raw)


if __name__ == "__main__": unittest.main()
