"""功能概述：合成端到端验证同一 mapping/costs 输入在 B0/B1/B2 下的资源语义。
主要职责：用独立小穷举比较 B1 最优目标；验证单 C 双 carrier 不扩容、B2 pair、
整体身份投影、并列与总超时/矩阵预算不能伪成功。mock 仅控制后端越界时钟情形。
代码库关系：连接 baselines、mapping 与 solver；不访问真实数据或模型，不写文件。
"""
import itertools
import unittest
from time import monotonic
from unittest.mock import patch
from nmr_assignment.costs import Observation as O
from nmr_assignment.mapping import (build_capacity_layout,attach_prediction_carriers,
                                   make_joint_mapping,project_assignment)
from nmr_assignment.baselines import run_baseline
from nmr_assignment.solver import SolveResult, Solution


def prediction(rows):
    parents = sorted({p for p,_,_ in rows})
    layout = build_capacity_layout(dict(nucleus="13C",parent_mass={p:1 for p in parents},
        isotope_count_verified=True,evidence_ids=["synthetic"],partition_hypothesis_id="synthetic"))
    return attach_prediction_carriers(layout,[dict(component_id=str(i),owner_id=p,
        center_ppm=c,mass=w,sigma_ppm=1,sigma_source="synthetic") for i,(p,c,w) in enumerate(rows)])


def run(method,obs,pred,**changes):
    kw = dict(parameters={"scale":1},max_candidates=100,
              max_variables=100,time_limit=10,total_deadline=monotonic()+20,
              top_k=3,compute_margins=True,tie_relative_tolerance=1e-7)
    if method!="B0":
        kw.update(missing_costs={u.unit_id:10 for u in pred.layout.units},
                  unexplained_costs={o.observation_id:10 for o in obs})
    return run_baseline(method,obs,pred,**dict(kw,**changes))


class BaselineTests(unittest.TestCase):
    def test_b0_reuses_unit_b1_matches_independent_exhaustive_oracle(self):
        pred=prediction([("x",0,.5),("x",10,.5),("y",2,1)])
        obs=[O("a",0),O("b",.1)]
        uids=tuple(u.unit_id for u in pred.layout.units)
        local=run("B0",obs,pred)
        self.assertEqual([d.local_top3[0][0] for d in local.local],[uids[0],uids[0]])
        self.assertEqual(local.reuse_semantics,"independent_local")
        global_result=run("B1",obs,pred)
        raw=global_result.solver_result
        centers={uids[0]:(0,10),uids[1]:(2,)}
        oracle=[]
        for choices in itertools.product((None,)+uids,repeat=2):
            used=[c for c in choices if c is not None]
            if len(used)!=len(set(used)): continue
            cost=sum(10 if c is None else min(abs(o.ppm-m) for m in centers[c]) for o,c in zip(obs,choices))
            cost+=10*(len(uids)-len(used))
            oracle.append(cost)
        self.assertTrue(global_result.certified)
        self.assertAlmostEqual(raw.best.objective,min(oracle))
        self.assertEqual(len({u for members in raw.best.assignments.values() for u in members}),2)
        joint=make_joint_mapping(pred.layout,{uids[0]:["C0"],uids[1]:["C1"]},[uids],
            level="atom",complete=True,basis="provenance_lineage",evidence_ids=["synthetic"],
            target_universe=["C0","C1"],completeness_evidence_id="synthetic",max_joint_maps=10)
        projected=project_assignment(raw.best.assignments,joint,missing_unit_ids=raw.best.unobserved)
        self.assertTrue(projected.joint_exact)
        self.assertEqual(raw.identification_quotient,"none")
        self.assertTrue(raw.attempts)

    def test_carbon_double_carrier_capacity_one(self):
        pred=prediction([("x",0,.5),("x",10,.5)])
        result=run("B1",[O("a",0),O("b",10)],pred)
        self.assertEqual(sum(bool(v) for v in result.solver_result.best.assignments.values()),1)
        self.assertEqual(result.candidate_count,2)

    def test_b2_pair_uses_two_distinct_units(self):
        pred=prediction([("x",0,1),("y",0,1)])
        params=dict(nucleus="13C",delta=1,smin=1,lambda_merge=1,member_gate=1,pair_span=1,gate_mode="standardized",
                    normalizer_convention="reduced",integral_policy="disabled")
        result=run("B2",[O("a",0)],pred,parameters=params)
        self.assertEqual(len(result.solver_result.best.assignments["a"]),2)
        self.assertEqual(result.solver_result.best.objective,1)

    def test_local_tie_does_not_claim_unique(self):
        pred=prediction([("x",-1,1),("y",1,1)])
        result=run("B0",[O("a",0)],pred)
        self.assertFalse(result.local[0].best_unique)
        self.assertIsNone(result.solver_result)

    def test_global_ties_abstain_and_local_full_blocks_survive(self):
        pred=prediction([(str(i),0,1) for i in range(5)])
        local=run("B0",[O("a",0)],pred)
        row=local.local[0]
        self.assertEqual(len(row.minimum_tie_block),5)
        self.assertTrue(row.minimum_tie_complete)
        self.assertEqual(len(local.observation_alternatives["a"]),5)
        self.assertFalse(local.observation_determinate["a"])
        global_result=run("B1",[O("a",0)],pred)
        self.assertEqual(dict(global_result.per_observation_status)["a"],"abstain_tie")
        self.assertFalse(global_result.observation_determinate["a"])
        self.assertEqual(global_result.global_top3_boundary,"cutoff_unverified")
        self.assertEqual(global_result.chemical_top3,"unsupported")

    def test_timeout_preserves_backend_result_without_success(self):
        pred=prediction([("x",0,1)])
        raw=SolveResult(Solution(0, {"a":(pred.layout.units[0].unit_id,)},(),(),True),(),
                        "optimal",True,False,True,True,{},())
        # Wrapper starts, checks generation deadline, computes remaining, then backend overruns.
        now=monotonic()
        with patch("nmr_assignment.baselines.monotonic",side_effect=[now,now,now,now,now+2,now+2]), \
             patch("nmr_assignment.baselines.solve_assignment",return_value=raw) as solver:
            result=run("B1",[O("a",0)],pred,total_deadline=now+1)
        self.assertEqual(result.status,"total_deadline")
        self.assertTrue(result.timed_out)
        self.assertFalse(result.certified)
        self.assertIs(result.solver_result,raw)
        self.assertEqual(solver.call_args.kwargs["time_limit"],1)
        expired=run("B1",[O("a",0)],pred,total_deadline=monotonic()-1)
        self.assertFalse(expired.certified)
        self.assertTrue(expired.timed_out)

    def test_pipeline_reports_examined_and_emitted_separately(self):
        pred=prediction([("x",0,.5),("x",10,.5),("y",2,1)])
        params=dict(nucleus="13C",delta=1.5,smin=.5,lambda_merge=.7,
                    member_gate=0,pair_span=2,gate_mode="standardized",
                    normalizer_convention="reduced",integral_policy="disabled")
        result=run("B2",[O("a",0)],pred,parameters=params,max_candidates=1)
        self.assertTrue(result.certified)
        self.assertEqual((result.examined_count,result.candidate_count),(5,1))
        failed=run("B2",[O("a",0)],pred,parameters=dict(params,member_gate=20),max_candidates=1)
        self.assertEqual(failed.status,"candidate_budget")
        self.assertIsNone(failed.solver_result)
        self.assertEqual(failed.candidate_count,1)
        self.assertGreater(failed.examined_count,1)

    def test_budget_and_exact_dummy_cover_and_no_scientific_defaults(self):
        pred=prediction([("x",0,1)])
        obs=[O("a",0)]
        self.assertEqual(run("B1",obs,pred,max_candidates=0).status,"candidate_budget")
        self.assertEqual(run("B1",obs,pred,max_variables=0).status,"matrix_budget")
        for changes in ({"missing_costs":{}},{"unexplained_costs":{}},
                        {"parameters":{}},{"time_limit":float("inf")},
                        {"parameters":{"scale":1,"gold":"leak"}}):
            with self.assertRaises(ValueError): run("B1",obs,pred,**changes)
        with self.assertRaises(ValueError): run("B0",obs,pred,missing_costs={})


if __name__=="__main__": unittest.main()
