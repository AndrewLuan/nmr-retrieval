"""功能概述：验证纯标准库容量和联合映射核心的科学边界，不执行模型前向。
MappingTests 用独立的小分子抽象输入覆盖 CH3/CH2、跨母节点 latent 置换、13C
双半质量载体、未知分区、同位素计数、重复资源和质量缺损。重编号测试同时转换
单位、母节点、观测及完整映射，并比较还原后的全体投影，避免用任意 tie 代表判唯一。
辅助函数 structure/components/mapping 构造显式证据，未读取任何实验谱或真实 test。
测试依赖 nmr_assignment.mapping 和 unittest；无网络、训练、文件输出或异步等待。
"""
import unittest
from dataclasses import replace
from nmr_assignment.mapping import (
    build_capacity_layout, attach_prediction_carriers, make_joint_mapping,
    project_assignment, metric_eligibility,
)


def structure(parent_mass, nucleus="1H"):
    return dict(nucleus=nucleus, parent_mass=parent_mass, evidence_ids=("graph-proof",),
                isotope_count_verified=True, partition_hypothesis_id="frozen-partition",
                partition_evidence_ids=("registry-sha",))


def component(cid, owner, center, mass=1.):
    return dict(component_id=cid, owner_id=owner, center_ppm=center, mass=mass)


def ch2():
    return build_capacity_layout(structure({"p": 2}), {"groups": [
        dict(unit_id="a", parents={"p": 1}, mass=1),
        dict(unit_id="b", parents={"p": 1}, mass=1)]})


def mapping(layout, target, level="atom", maps=None, **kwargs):
    ids = tuple(u.unit_id for u in layout.units)
    return make_joint_mapping(layout, target, maps or (ids,), level=level,
        complete=True, basis="graph_mapping_ambiguity", evidence_ids=("source-map",),
        target_universe=tuple(sorted({x for xs in target.values() for x in xs})),
        completeness_evidence_id="enumeration-proof", **kwargs)


class MappingTests(unittest.TestCase):
    def test_ch3_repeated_emission_is_one_capacity(self):
        layout = build_capacity_layout(structure({"p": 3}), {"groups": [
            dict(unit_id="methyl", parents={"p": 3}, mass=3)]})
        pred = attach_prediction_carriers(layout,
            [component(str(i), "p", 1.2) for i in range(3)])
        self.assertEqual((len(layout.units), layout.units[0].nucleus_mass), (1, 3))
        self.assertEqual(len(pred.carriers), 1)
        self.assertEqual(pred.carriers[0].mixture_weight, 1.)
        joint = mapping(layout, {"methyl": ("p", "p", "p")}, level="parent")
        with self.assertRaisesRegex(ValueError, "two observations"):
            project_assignment({"x": ("methyl",), "y": ("methyl",)}, joint)

    def test_ch2_two_capacities_do_not_name_hydrogens(self):
        layout = ch2()
        raw = [component("c0", "p", 1.), component("c1", "p", 2.)]
        with self.assertRaisesRegex(ValueError, "explicit model-layout"):
            attach_prediction_carriers(layout, raw)
        pred = attach_prediction_carriers(layout, raw, dict(
            component_unit_ids={"c0": "a", "c1": "b"},
            attachment_blocks=(("a", "b"),), attachment_evidence_ids=("orbit",)))
        self.assertEqual(len(pred.layout.units), 2)
        joint = mapping(layout, {"a": ("Ha",), "b": ("Hb",)},
            attachment_blocks=pred.attachment_blocks,
            attachment_evidence_ids=pred.attachment_evidence_ids)
        result = project_assignment({"x": ("a",), "y": ("b",)}, joint)
        self.assertEqual(len(result.variants), 2)
        self.assertFalse(result.joint_exact)
        self.assertEqual(dict(result.per_observation_exact), {"x": False, "y": False})

    def test_parent_projection_remains_exact_with_anonymous_ch2(self):
        joint = mapping(ch2(), {"a": ("p",), "b": ("p",)}, level="parent",
            attachment_blocks=(("a", "b"),), attachment_evidence_ids=("orbit",),
            max_joint_maps=1)
        result = project_assignment({"x": ("a",), "y": ("b",)}, joint)
        self.assertTrue(result.joint_exact)
        self.assertTrue(joint.complete)

    def test_cross_parent_orbit_is_joint_and_not_chemical_equivalence(self):
        layout = build_capacity_layout(structure({"p": 1, "q": 1}, "13C"))
        joint = mapping(layout, {"parent:p": ("p",), "parent:q": ("q",)},
            level="parent", attachment_blocks=(("parent:p", "parent:q"),),
            attachment_evidence_ids=("orbit",))
        result = project_assignment({"x": ("parent:p",), "y": ("parent:q",)}, joint)
        self.assertEqual(len(result.variants), 2)
        self.assertFalse(result.joint_exact)
        # A Cartesian combination could choose p for both peaks; no legal whole map does.
        self.assertNotIn((("x", ("p",)), ("y", ("p",))), result.variants)
        self.assertEqual(joint.basis, "graph_mapping_ambiguity")

    def test_carbon_half_components_preserve_distribution_and_one_nucleus(self):
        layout = build_capacity_layout(structure({"C": 1}, "13C"))
        pred = attach_prediction_carriers(layout,
            [component("left", "C", 25., .5), component("right", "C", 35., .5)])
        self.assertEqual(layout.units[0].nucleus_mass, 1)
        self.assertEqual([(r.center_ppm, r.mixture_weight) for r in pred.carriers],
                         [(25., .5), (35., .5)])
        self.assertEqual(pred.branch_semantics, "owner_marginal")
        joint = mapping(layout, {"parent:C": ("C",)})
        with self.assertRaises(ValueError):
            project_assignment({"x": ("parent:C",), "y": ("parent:C",)}, joint)

    def test_unknown_partition_retains_parent_pool_and_all_carriers(self):
        layout = build_capacity_layout(structure({"p": 2}))
        pred = attach_prediction_carriers(layout,
            [component("h0", "p", 1.), component("h1", "p", 2.)])
        self.assertIsNone(layout.structural_environment_count)
        self.assertEqual(layout.units[0].partition_status, "unresolved_parent_pool")
        self.assertEqual(len(pred.carriers), 2)
        self.assertEqual(len(layout.units), 1)
        self.assertEqual([r.mixture_weight for r in pred.carriers], [.5, .5])

    def test_hydrogen_conservation_underflow_overflow_and_duplicates(self):
        for mass in (1, 3):
            with self.subTest(mass=mass), self.assertRaisesRegex(ValueError, "conserve"):
                build_capacity_layout(structure({"p": 2}), {"groups": [
                    dict(unit_id="a", parents={"p": mass}, mass=mass)]})
        with self.assertRaises(ValueError):
            build_capacity_layout(structure({"p": 2}), {"groups": [
                dict(unit_id="a", parents={"p": 1}, mass=1),
                dict(unit_id="a", parents={"p": 1}, mass=1)]})
        with self.assertRaises(ValueError):
            build_capacity_layout(structure({"p": 2}), {"groups": [
                dict(unit_id="a", parents={"p": 2}, mass=1)]})

    def test_isotope_count_and_carbon_mass_must_be_verified(self):
        ev = structure({"p": 2})
        ev["isotope_count_verified"] = False
        with self.assertRaisesRegex(ValueError, "isotope"):
            build_capacity_layout(ev)
        with self.assertRaises(ValueError):
            build_capacity_layout(structure({"C": 2}, "13C"))
        with self.assertRaises(ValueError):
            build_capacity_layout(structure({"H": .5}))

    def test_component_mass_and_binding_must_match_both_parent_and_unit(self):
        layout = ch2()
        with self.assertRaisesRegex(ValueError, "parent nuclear mass"):
            attach_prediction_carriers(layout, [component("c0", "p", 1., .5)],
                {"component_unit_ids": {"c0": "a"}})
        with self.assertRaisesRegex(ValueError, "unit parent mass"):
            attach_prediction_carriers(layout,
                [component("c0", "p", 1.), component("c1", "p", 2.)],
                {"component_unit_ids": {"c0": "a", "c1": "a"}})
        with self.assertRaises(ValueError):
            attach_prediction_carriers(layout,
                [component("dup", "p", 1.), component("dup", "p", 2.)])

    def test_mapping_bijection_target_domain_and_atom_reuse_are_checked(self):
        layout = ch2()
        for targets, maps in [({"a": ("H",), "b": ("H",)}, (("a", "b"),)),
                              ({"a": ("Ha",), "b": ("Hb",)}, (("a", "a"),))]:
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                mapping(layout, targets, maps=maps)
        joint = mapping(layout, {"a": ("Ha",), "b": ("Hb",)})
        with self.assertRaises(ValueError):
            replace(joint, target_by_unit=(("a", ("outside",)), ("b", ("Hb",))))
        with self.assertRaises(ValueError):
            replace(joint, complete=False)

    def test_truncated_attachment_enumeration_stays_unknown(self):
        joint = mapping(ch2(), {"a": ("Ha",), "b": ("Hb",)},
            attachment_blocks=(("a", "b"),), attachment_evidence_ids=("orbit",),
            max_joint_maps=1)
        result = project_assignment({"x": ("a",)}, joint)
        self.assertFalse(joint.complete)
        self.assertIsNone(joint.completeness_evidence_id)
        self.assertFalse(result.joint_exact)
        self.assertFalse(dict(result.per_observation_exact)["x"])

    def test_joint_composition_budget_counts_duplicate_states_too(self):
        joint = mapping(ch2(), {"a": ("Ha",), "b": ("Hb",)},
            maps=(("a", "b"), ("b", "a")),
            attachment_blocks=(("a", "b"),), attachment_evidence_ids=("orbit",),
            max_joint_maps=2)
        self.assertEqual(len(joint.unit_permutations), 2)
        self.assertFalse(joint.complete)

    def test_renumbering_compares_whole_projection_sets_not_tie_representatives(self):
        layout = build_capacity_layout(structure({"p": 1, "q": 1}, "13C"))
        maps = (("parent:p", "parent:q"), ("parent:q", "parent:p"))
        original = project_assignment({"x": ("parent:p",), "y": ("parent:q",)},
            mapping(layout, {"parent:p": ("p",), "parent:q": ("q",)},
                    level="parent", maps=maps))
        renamed = build_capacity_layout(structure({"9": 1, "2": 1}, "13C"))
        renamed_maps = (("parent:2", "parent:9"), ("parent:9", "parent:2"))
        changed = project_assignment({"Y": ("parent:2",), "X": ("parent:9",)},
            mapping(renamed, {"parent:9": ("9",), "parent:2": ("2",)},
                    level="parent", maps=renamed_maps))
        obs = {"X": "x", "Y": "y"}
        atom = {"9": "p", "2": "q"}
        restored = {tuple(sorted((obs[o], tuple(sorted(atom[t] for t in ts)))
                                for o, ts in variant)) for variant in changed.variants}
        self.assertEqual(set(original.variants), restored)
        self.assertFalse(original.joint_exact)
        self.assertFalse(changed.joint_exact)

    def test_carriers_cannot_determine_source_h_identity(self):
        layout = ch2()
        model = dict(component_unit_ids={"a0": "a", "b0": "b"},
                     attachment_blocks=(("a", "b"),), attachment_evidence_ids=("orbit",))
        projections = []
        for centers in ((1., 2.), (2., 1.)):
            pred = attach_prediction_carriers(layout,
                [component("a0", "p", centers[0]), component("b0", "p", centers[1])], model)
            joint = mapping(layout, {"a": ("Ha",), "b": ("Hb",)},
                attachment_blocks=pred.attachment_blocks,
                attachment_evidence_ids=pred.attachment_evidence_ids)
            projections.append(project_assignment({"x": ("a",)}, joint))
        self.assertEqual(projections[0], projections[1])

    def test_exact_denominator_does_not_shrink_for_ambiguous_prediction(self):
        joint = mapping(ch2(), {"a": ("Ha",), "b": ("Hb",)},
                        maps=(("a", "b"), ("b", "a")))
        projection = project_assignment({"x": ("a",)}, joint)
        gold = dict(spectrum_authentic=True, observation_semantics_verified=True,
                    independent_gold_verified=True, assignment_provenance_verified=True,
                    stereo_scope_verified=True, isotope_scope_verified=True, atom_assignment_verified=True,
                    gold_evidence_ids=("admitted-gold",))
        eligibility = metric_eligibility(gold, projection, metric="exact_atom")
        self.assertTrue(eligibility.gold_eligible)
        self.assertFalse(eligibility.prediction_supported)
        gold["independent_gold_verified"] = False
        self.assertFalse(metric_eligibility(gold, projection, metric="exact_atom").gold_eligible)

    def test_unknown_gold_does_not_get_vacuous_compatibility_credit(self):
        joint = mapping(ch2(), {"a": ("p",), "b": ("p",)}, level="parent")
        projection = project_assignment({"x": ("a",)}, joint)
        gold = dict(spectrum_authentic=True, observation_semantics_verified=True,
                    independent_gold_verified=True, assignment_provenance_verified=True,
                    stereo_scope_verified=True, isotope_scope_verified=True, joint_allowed_set_verified=True,
                    joint_allowed_set_nontrivial=False, gold_evidence_ids=("gold",))
        self.assertFalse(metric_eligibility(gold, projection, metric="compatibility").gold_eligible)

    def test_missing_complement_pair_reuse_and_local_reuse_are_explicit(self):
        joint = mapping(ch2(), {"a": ("Ha",), "b": ("Hb",)})
        pair = project_assignment({"x": ("a", "b")}, joint, missing_unit_ids=())
        self.assertFalse(pair.missing_unit_ids)
        with self.assertRaises(ValueError):
            project_assignment({"x": ("a",)}, joint, missing_unit_ids=())
        with self.assertRaises(ValueError):
            project_assignment({"x": ("a", "a")}, joint)
        local = project_assignment({"x": ("a",), "y": ("a",)}, joint,
                                   reuse_semantics="independent_local")
        self.assertEqual(local.reuse_semantics, "independent_local")

    def test_unknown_parent_pool_supports_parent_but_not_invented_atom_resolution(self):
        layout = build_capacity_layout(structure({"p": 2}))
        atom_map = mapping(layout, {"parent:p": ("Ha", "Hb")})
        result = project_assignment({"x": ("parent:p",)}, atom_map)
        gold = dict(spectrum_authentic=True, observation_semantics_verified=True,
                    independent_gold_verified=True, assignment_provenance_verified=True,
                    stereo_scope_verified=True, isotope_scope_verified=True, atom_assignment_verified=True,
                    parent_assignment_verified=True, gold_evidence_ids=("gold",))
        atom = metric_eligibility(gold, result, metric="exact_atom")
        self.assertTrue(atom.gold_eligible)
        self.assertFalse(atom.prediction_supported)
        parent_map = mapping(layout, {"parent:p": ("p", "p")}, level="parent")
        parent = metric_eligibility(gold, project_assignment({"x": ("parent:p",)}, parent_map),
                                    metric="exact_parent")
        self.assertTrue(parent.prediction_supported)

    def test_nonfinite_centers_unknown_bindings_and_bad_orbits_fail(self):
        layout = build_capacity_layout(structure({"C": 1}, "13C"))
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                attach_prediction_carriers(layout, [component("c", "C", value)])
        with self.assertRaises(ValueError):
            attach_prediction_carriers(layout, [component("c", "C", 1.)],
                                       {"component_unit_ids": {"ghost": "parent:C"}})
        with self.assertRaises(ValueError):
            mapping(ch2(), {"a": ("Ha",), "b": ("Hb",)},
                attachment_blocks=(("a", "b"), ("a", "b")),
                attachment_evidence_ids=("orbit",))


if __name__ == "__main__":
    unittest.main()
