"""功能概述：用纯合成容量和载体验证 costs，不读真实谱或标签。
主要职责：覆盖 C 双分量单容量、B0/B1 最小载体、B2 归一混合及不重归一门控、
异方差、稳定求和、积分契约和预算失败；不重复 solver 的全局优化测试。
代码库关系：使用 mapping 构建合法冻结预测，检查 Candidate 的 unit IDs 和费用。
输入输出与副作用：标准 unittest，无模型、网络或持久化副作用。
"""
import math
import unittest
from time import monotonic
from nmr_assignment.solver import solve_assignment
from nmr_assignment.mapping import build_capacity_layout, attach_prediction_carriers
from nmr_assignment.costs import (
    Observation as O, build_b1, build_b2, local_nearest, GenerationLimit, b2_missing_costs, unit_normalizers,
)


def prediction(rows, nucleus="13C"):
    owners = sorted({r[0] for r in rows})
    layout = build_capacity_layout(dict(nucleus=nucleus, parent_mass={p: 1 for p in owners},
        isotope_count_verified=True, evidence_ids=["synthetic"], partition_hypothesis_id="synthetic"))
    return attach_prediction_carriers(layout, [dict(component_id=str(i), owner_id=p,
        center_ppm=center, mass=weight, sigma_ppm=sigma, sigma_source="synthetic")
        for i, (p, center, weight, sigma) in enumerate(rows)])


class CostsTests(unittest.TestCase):
    def setUp(self):
        self.pred = prediction([("x", 0, .5, 1), ("x", 10, .5, 1), ("y", 2, 1, 2)])
        self.ids = tuple(u.unit_id for u in self.pred.layout.units)
        self.kw = dict(nucleus="13C", delta=1, smin=1, lambda_merge=3,
                       member_gate=20, pair_span=20, gate_mode="absolute_ppm",
                       normalizer_convention="raw",integral_policy="disabled",max_candidates=100)

    def costs(self, pred=None, peak=0, **changes):
        return {c.environment_ids: c.cost for c in build_b2(
            [O("a", peak)], self.pred if pred is None else pred, **dict(self.kw, **changes))}

    def test_carbon_two_half_components_one_capacity_and_min_carrier(self):
        x, y = self.ids
        self.assertEqual(len(self.pred.layout.units), 2)
        local = local_nearest([O("a", 9), O("b", 9)], self.pred, scale=1, tie_relative_tolerance=1e-7, max_candidates=6)
        self.assertEqual(local[0].local_top3, ((x, 1), (y, 7)))
        self.assertEqual(local[1].local_top3, local[0].local_top3)
        candidates = build_b1([O("a", 9)], self.pred, scale=2, max_candidates=3)
        self.assertEqual([(c.environment_ids, c.cost) for c in candidates], [((x,), .5), ((y,), 3.5)])
        self.assertEqual({len(k) for k in self.costs()}, {1, 2})

    def test_normalized_mixture_not_pseudocenter(self):
        x, y = self.ids
        costs = self.costs()
        self.assertAlmostEqual(costs[(x,)], -math.log(.5 + .5*math.exp(-9.5)))
        self.assertAlmostEqual(costs[(y,)], .5+math.log(2))
        self.assertAlmostEqual(costs[(x,y)], costs[(x,)]+costs[(y,)]+3)

    def test_gate_discards_probability_without_renormalization(self):
        x, y = self.ids
        costs = self.costs(member_gate=3)
        self.assertAlmostEqual(costs[(x,)], math.log(2))
        self.assertAlmostEqual(costs[(x,y)], math.log(2)+.5+math.log(2)+3)
        self.assertNotIn((x,y), self.costs(pair_span=1))

    def test_same_center_invariance_and_distinct_scales(self):
        a = prediction([("x", 0, 1, 1)])
        b = prediction([("x", 0, .5, 1), ("x", 0, .5, 1)])
        self.assertEqual(self.costs(a, peak=2), self.costs(b, peak=2))
        c = prediction([("x", 0, .5, 1), ("x", 0, .5, 2)])
        self.assertEqual(len(c.carriers), 2)
        self.assertAlmostEqual(next(iter(self.costs(c).values())), -math.log(.5+.25))
        self.assertTrue(math.isfinite(next(iter(self.costs(a, peak=10000, member_gate=20000).values()))))

    def test_b0_no_distance_gate_and_preserves_ties(self):
        pred = prediction([("x", -1, 1, 1), ("y", 1, 1, 1)])
        rows = local_nearest([O("a", 0)], pred, scale=1, tie_relative_tolerance=1e-7, max_candidates=2)[0].local_top3
        self.assertEqual([v for _, v in rows], [1, 1])
        self.assertEqual(len(local_nearest([O("a", 10000)], pred, scale=1, tie_relative_tolerance=1e-7, max_candidates=2)[0].local_top3), 2)

    def test_local_top3_keeps_complete_boundary_and_minimum_tie_blocks(self):
        pred=prediction([(str(i),0,1,1) for i in range(5)])
        row=local_nearest([O("a",0)],pred,scale=2,tie_relative_tolerance=1e-7,max_candidates=5)[0]
        self.assertEqual(len(row.local_top3),5)
        self.assertEqual(len(row.minimum_unit_ids),5)
        self.assertTrue(all((lower,upper)==(1,5) for _,lower,upper in row.rank_bounds))
        renamed=prediction([(str(i+10),0,1,1) for i in range(5)])
        other=local_nearest([O("a",0)],renamed,scale=2,tie_relative_tolerance=1e-7,max_candidates=5)[0]
        self.assertEqual([cost for _,cost in row.local_top3],[cost for _,cost in other.local_top3])

    def test_first_round_integrals_disabled_for_both_nuclei(self):
        for nucleus in ("1H","13C"):
            pred=prediction([("x",0,1,1)],nucleus=nucleus)
            for extra in ({"integral_penalties":{}},{"integral_policy":"enabled"}):
                with self.assertRaisesRegex(ValueError,"disabled"):
                    self.costs(pred,nucleus=nucleus,**extra)

    def test_budget_and_deadline_no_partial_graph(self):
        for call in (
            lambda: local_nearest([O("a",0)], self.pred, scale=1, tie_relative_tolerance=1e-7, max_candidates=1),
            lambda: build_b1([O("a",0)], self.pred, scale=1, max_candidates=1),
            lambda: self.costs(max_candidates=0, member_gate=0),
            lambda: self.costs(deadline=monotonic()-1),
        ):
            with self.assertRaises(GenerationLimit):
                call()

    def test_standardized_member_span_and_floor(self):
        broad=prediction([("x",0,1,2)])
        self.assertEqual(len(self.costs(broad,peak=4,gate_mode="standardized",member_gate=3)),1)
        self.assertEqual(len(self.costs(broad,peak=4,gate_mode="absolute_ppm",member_gate=3)),0)
        pair=prediction([("x",0,1,1),("y",4,1,2)])
        self.assertTrue(any(len(k)==2 for k in self.costs(pair,peak=2,gate_mode="standardized",member_gate=3,pair_span=2)))
        floor=prediction([("x",0,1,.01)])
        self.assertEqual(next(iter(self.costs(floor,smin=.05).values())),0)

    def test_wide_perfect_pair_raw_reduced_gauge_and_margins(self):
        for widths in ((1,1),(1.5,20),(.01,2)):
            pred=prediction([("x",0,1,widths[0]),("y",0,1,widths[1])])
            ids=tuple(u.unit_id for u in pred.layout.units)
            kappa={uid:math.log(3) for uid in ids}
            configs=dict(self.kw,delta=1.5,smin=.05,lambda_merge=math.log(2),
                         member_gate=3,pair_span=2,gate_mode="standardized")
            solves=[]
            for convention in ("raw","reduced"):
                candidates=build_b2([O("a",0)],pred,**dict(configs,normalizer_convention=convention))
                missing=b2_missing_costs(pred,kappa,smin=.05,normalizer_convention=convention)
                solves.append(solve_assignment(["a"],ids,candidates,missing,{"a":3.375},
                                               top_k=3,time_limit=10,compute_margins=True))
            raw,reduced=solves
            constant=sum(unit_normalizers(pred,smin=.05).values())
            self.assertEqual(raw.best.assignments,reduced.best.assignments)
            self.assertEqual(len(raw.best.assignments["a"]),2)
            self.assertAlmostEqual(reduced.best.objective,math.log(2))
            self.assertAlmostEqual(raw.best.objective-reduced.best.objective,constant)
            self.assertAlmostEqual(raw.margins["a"].value,reduced.margins["a"].value)
            self.assertAlmostEqual(reduced.margins["a"].value,math.log(3/2))
            self.assertEqual(len(raw.alternatives),len(reduced.alternatives))
            for left,right in zip(raw.alternatives,reduced.alternatives):
                self.assertAlmostEqual(left.objective-right.objective,constant)
            # Reduced reporting potential provides no reward to consume the second unit.
            missing=b2_missing_costs(pred,{uid:0 for uid in ids},smin=.05,normalizer_convention="reduced")
            candidates=build_b2([O("a",0)],pred,**dict(configs,normalizer_convention="reduced"))
            exchange=solve_assignment(["a"],ids,candidates,missing,{"a":3.375},time_limit=10)
            self.assertEqual(len(exchange.best.assignments["a"]),1)

    def test_emitted_cap_is_independent_of_examined_carrier_combinations(self):
        # Three singleton components and two pair components are examined; only
        # one zero-residual singleton survives. A candidate cap of one must pass.
        batch=build_b2([O("a",0)],self.pred,**dict(self.kw,member_gate=0,max_candidates=1))
        self.assertEqual((batch.examined_count,batch.emitted_count,len(batch)),(5,1,1))
        with self.assertRaises(GenerationLimit) as failure:
            build_b2([O("a",0)],self.pred,**dict(self.kw,max_candidates=1))
        self.assertEqual(failure.exception.emitted_count,1)
        self.assertGreater(failure.exception.examined_count,1)
        # Rejected combinations still obey the absolute generation deadline.
        from unittest.mock import patch
        with patch("nmr_assignment.costs.monotonic",side_effect=lambda:2):
            with self.assertRaisesRegex(GenerationLimit,"deadline"):
                build_b2([O("a",0)],self.pred,**dict(self.kw,member_gate=0,max_candidates=1,deadline=1))

    def test_pair_enumeration_is_lazy_and_checks_deadline_before_work(self):
        from itertools import combinations as real_combinations
        from unittest.mock import patch
        pred=prediction([(str(i),0,1,1) for i in range(40)])
        pair_visits=[]
        def observed_combinations(pool,size):
            for members in real_combinations(pool,size):
                if size==2:
                    pair_visits.append(members)
                yield members
        # Deadline expires on the first yielded pair. Eager tuple construction
        # would consume all 780 pairs before it next observes the deadline.
        with patch("nmr_assignment.costs.combinations",side_effect=observed_combinations), \
             patch("nmr_assignment.costs.monotonic",side_effect=lambda:2 if pair_visits else 0):
            with self.assertRaisesRegex(GenerationLimit,"deadline") as failure:
                build_b2([O("a",0)],pred,**dict(self.kw,max_candidates=1000,deadline=1))
        self.assertEqual(len(pair_visits),1)
        self.assertEqual(failure.exception.examined_count,40)
        self.assertEqual(failure.exception.emitted_count,40)
        pair_visits.clear()
        with patch("nmr_assignment.costs.combinations",side_effect=observed_combinations):
            empty=build_b2([],pred,**self.kw)
        self.assertEqual((len(empty),empty.examined_count,empty.emitted_count),(0,0,0))
        self.assertEqual(pair_visits,[])

    def test_invalid_inputs(self):
        for val in (math.nan, math.inf, True, "1"):
            with self.assertRaises(ValueError): O("a", val)
        for change in ({"delta":0}, {"smin":0}, {"lambda_merge":0}, {"member_gate":-1}, {"pair_span":math.inf}):
            with self.assertRaises(ValueError): self.costs(**change)
        with self.assertRaises(ValueError):
            build_b1([O("a",0), O("a",1)], self.pred, scale=1, max_candidates=20)
        with self.assertRaises(ValueError):
            build_b1([O("a",0)], [], scale=1, max_candidates=20)


if __name__ == "__main__": unittest.main()
