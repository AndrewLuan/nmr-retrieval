"""功能概述：纯合成数组验证 native_adapter 与 mapping 容量核心的接线。
NativeAdapterTests 覆盖 CH3重复发射、CH2与跨parent轨道整体歧义、未知H池、
C双0.5载体、逐成分sigma保留及质量/顺序/证据错误；不运行模型或读取真实谱。
_fixture 生成显式标为synthetic的结构证据；_adapt 仅为测试填入已声明的人工数组。
代码库关系：使用 unittest 和 nmr_assignment.native_adapter，不改 mapping.py。
输入输出与副作用：测试无外部API、模型、持久化或训练；失败通过断言报告。
"""
import unittest
from nmr_assignment.native_adapter import adapt_native_predictions


def _fixture(nucleus, parents):
    return dict(nucleus=nucleus, parent_mass=parents, isotope_count_verified=True,
                evidence_ids=["synthetic:graph-isotope-count"],
                partition_hypothesis_id="synthetic:partition",
                partition_evidence_ids=["synthetic:registry"])


def _adapt(evidence, owners, centers, masses, **kwargs):
    n = len(owners)
    options = dict(graph_indices=[0] * n, sigma_ppm=[None] * n,
                   sigma_sources=["unknown"] * n, known_h_layout=False,
                   layout_evidence_ids=[], attachment_evidence_ids=[])
    options.update(kwargs)
    return adapt_native_predictions(evidence, centers_ppm=centers, masses=masses,
                                    owners=owners, **options)


class NativeAdapterTests(unittest.TestCase):
    def test_ch3_repeated_emissions_one_capacity(self):
        pred = _adapt(_fixture("1H", {"0": 3}), [0]*3, [1.2]*3, [1]*3,
                      known_h_layout=True, layout_evidence_ids=["synthetic:layout"],
                      equivalence_ids=[[0, 0, 0, -1, -1, -1]],
                      preserved_group_orbits=[0], preserved_group_ordinal=[0],
                      preserved_group_sizes=[1])
        self.assertEqual(len(pred.layout.units), 1)
        self.assertEqual(pred.layout.units[0].nucleus_mass, 3)
        self.assertEqual(len(pred.carriers), 1)
        self.assertEqual(pred.carriers[0].center_ppm, 1.2)
        self.assertEqual(pred.carriers[0].mixture_weight, 1)
        self.assertEqual(pred.carriers[0].source_component_ids,
                         ("component:0", "component:1", "component:2"))

    def test_ch2_two_anonymous_units_and_whole_attachment_block(self):
        pred = _adapt(_fixture("1H", {"0": 2}), [0, 0], [2., 1.], [1, 1],
                      known_h_layout=True, layout_evidence_ids=["synthetic:layout"],
                      attachment_evidence_ids=["synthetic:model-orbit"],
                      equivalence_ids=[[1, 0, -1, -1, -1, -1]],
                      preserved_group_orbits=[0, 0],
                      preserved_group_ordinal=[1, 0], preserved_group_sizes=[2, 2])
        self.assertEqual(pred.attachment_blocks, (("group:0", "group:1"),))
        self.assertEqual({r.unit_id: r.center_ppm for r in pred.carriers},
                         {"group:0": 1., "group:1": 2.})
        self.assertEqual(pred.branch_semantics, "owner_marginal")

    def test_cross_parent_orbit_is_preserved(self):
        pred = _adapt(_fixture("1H", {"0": 3, "1": 3}),
                      [0]*3+[1]*3, [1.]*3+[2.]*3, [1]*6,
                      known_h_layout=True, layout_evidence_ids=["synthetic:layout"],
                      attachment_evidence_ids=["synthetic:cross-parent-orbit"],
                      equivalence_ids=[[0,0,0,-1,-1,-1],[1,1,1,-1,-1,-1]],
                      preserved_group_orbits=[4,4], preserved_group_ordinal=[0,1],
                      preserved_group_sizes=[2,2])
        self.assertEqual(pred.attachment_blocks, (("group:0", "group:1"),))
        self.assertEqual(pred.layout.parent_mass_totals, (("0",3),("1",3)))
        self.assertEqual([u.nucleus_mass for u in pred.layout.units], [3,3])

    def test_unknown_h_retains_parent_pool_all_centers(self):
        pred = _adapt(_fixture("1H", {"7": 2}), [7,7], [1.3,2.1], [1,1])
        self.assertIsNone(pred.layout.structural_environment_count)
        self.assertEqual(pred.layout.units[0].partition_status,"unresolved_parent_pool")
        self.assertEqual(pred.layout.units[0].nucleus_mass,2)
        self.assertEqual([r.mixture_weight for r in pred.carriers],[.5,.5])

    def test_c_dual_carrier_capacity_one_no_sigma_average(self):
        pred = _adapt(_fixture("13C", {"2": 1}), [2,2], [35.,37.], [.5,.5],
                      sigma_ppm=[.3,.8], sigma_sources=["fixed:C-a","fixed:C-b"])
        self.assertEqual(pred.layout.units[0].nucleus_mass,1)
        self.assertEqual(len(pred.carriers),2)
        self.assertEqual([c.center_ppm for c in pred.carriers],[35.,37.])
        self.assertEqual([c.sigma_ppm for c in pred.carriers],[.3,.8])
        self.assertEqual([c.mixture_weight for c in pred.carriers],[.5,.5])

    def test_equal_centers_distinct_sigmas_not_averaged(self):
        pred = _adapt(_fixture("13C", {"2": 1}),[2,2],[35.,35.],[.5,.5],
                      sigma_ppm=[.3,.8],sigma_sources=["fixed:C","fixed:C"])
        self.assertEqual(len(pred.carriers),2)

    def test_bad_h_mass_or_layout_parent_order_rejected(self):
        with self.assertRaisesRegex(ValueError,"mass"):
            _adapt(_fixture("1H",{"0":2}),[0],[1.],[1.])
        with self.assertRaisesRegex(ValueError,"order"):
            _adapt(_fixture("1H",{"0":1,"1":1}),[1,0],[1.,2.],[1,1],
                   known_h_layout=True,layout_evidence_ids=["synthetic:layout"],
                   equivalence_ids=[[0,-1,-1,-1,-1,-1],[1,-1,-1,-1,-1,-1]],
                   preserved_group_orbits=[0,1],preserved_group_ordinal=[0,0],
                   preserved_group_sizes=[1,1])

    def test_known_h_wrong_component_mass_rejected(self):
        with self.assertRaisesRegex(ValueError,"mass one"):
            _adapt(_fixture("1H",{"0":1}),[0],[1.],[.5],
                   known_h_layout=True,layout_evidence_ids=["synthetic:layout"],
                   equivalence_ids=[[0,-1,-1,-1,-1,-1]],
                   preserved_group_orbits=[0],preserved_group_ordinal=[0],
                   preserved_group_sizes=[1])

    def test_c_mass_and_unknown_owner_rejected(self):
        with self.assertRaisesRegex(ValueError,"mass"):
            _adapt(_fixture("13C",{"2":1}),[2,2],[1.,2.],[1.,1.])
        with self.assertRaisesRegex(ValueError,"unknown parent"):
            _adapt(_fixture("13C",{"2":1}),[3],[1.],[1.])

    def test_required_evidence_not_generated(self):
        evidence = _fixture("1H",{"0":1})
        evidence.pop("isotope_count_verified")
        with self.assertRaisesRegex(ValueError,"verified"):
            _adapt(evidence,[0],[1.],[1.])
        with self.assertRaisesRegex(ValueError,"evidence"):
            _adapt(_fixture("1H",{"0":1}),[0],[1.],[1.],known_h_layout=True)

    def test_orbit_invalid_ordinal_or_missing_attachment_proof(self):
        kwargs=dict(known_h_layout=True,layout_evidence_ids=["synthetic:layout"],
                    equivalence_ids=[[0,1,-1,-1,-1,-1]],
                    preserved_group_orbits=[0,0],preserved_group_ordinal=[0,1],
                    preserved_group_sizes=[2,2])
        with self.assertRaisesRegex(ValueError,"explicit evidence"):
            _adapt(_fixture("1H",{"0":2}),[0,0],[1.,2.],[1,1],**kwargs)
        kwargs["attachment_evidence_ids"]=["synthetic:orbit"]
        kwargs["preserved_group_ordinal"]=[0,0]
        with self.assertRaisesRegex(ValueError,"ordinal"):
            _adapt(_fixture("1H",{"0":2}),[0,0],[1.,2.],[1,1],**kwargs)

    def test_arrays_graph_sigma_and_unknown_layout_rejected(self):
        for kwargs in (dict(graph_indices=[1]),dict(sigma_ppm=[]),
                       dict(sigma_ppm=[.2],sigma_sources=["unknown"]),
                       dict(equivalence_ids=[[0,-1,-1,-1,-1,-1]])):
            with self.assertRaises(ValueError):
                _adapt(_fixture("1H",{"0":1}),[0],[1.],[1.],**kwargs)


if __name__ == "__main__":
    unittest.main()
