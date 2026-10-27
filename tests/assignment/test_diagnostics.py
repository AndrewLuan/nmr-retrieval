"""功能概述：用合成结构与冻结数值验证诊断不偷选身份、不丢分母且不追加求解。
主要职责：测试固定 q 多载体、联合误差界、attachment 完整性、来源槽守恒、候选
receipt、已有 witness 容量/成本、同分与未认证回退。全部输入在本文件生成。
关系：只调用 diagnostics/mapping；BaselineResult 用同字段合成对象代替，不调用模型、
solver 或真实数据。结果只证明这些算法边界，不提供科研准确率。
"""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from nmr_assignment.mapping import (build_capacity_layout, FrozenCarrier, FrozenCapacityPredictions)
from nmr_assignment.diagnostics import (
    DiagnosticBinding, PayloadReceipt, DiagnosticBudget, ForwardTarget, ForwardAssociation,
    TraceCandidate, CandidateTrace, ReferenceChoices, AssignmentCompatibility, AdmissionEntry,
    payload_digest, shared_forward, candidate_diagnostics, validate_witness,
    objective_diagnostic, admission_summary, baseline_actions, SolverResultCertificate,
    result_snapshot_digest)


BIND = DiagnosticBinding("record", "source_relative_current_serialization", "13C",
    "derived_serialized_value_bin", "1"*64, "2"*64, "3"*64)


def predictions(specs, *, nucleus="13C", masses=None, registry=True, attachment=()):
    masses = masses or [1]*len(specs)
    evidence = dict(nucleus=nucleus, parent_mass={str(i):m for i,m in enumerate(masses)},
        isotope_count_verified=True, evidence_ids=["structure"],
        partition_hypothesis_id="structure-v1", partition_evidence_ids=["registry"])
    groups = dict(groups=[dict(unit_id="u"+str(i),parents={str(i):m},mass=m) for i,m in enumerate(masses)]) if registry else None
    layout = build_capacity_layout(evidence, groups)
    carriers = []
    for unit, rows in zip(layout.units,specs):
        for index,(center,weight) in enumerate(rows):
            name=unit.unit_id+"c"+str(index)
            carriers.append(FrozenCarrier(name,unit.unit_id,center,weight,None,"unknown",(name,)))
    return FrozenCapacityPredictions(layout,tuple(carriers),attachment,("attachment",) if attachment else ())


def target(name, value, slots=None):
    return ForwardTarget(name,value,slots or ("slot:"+name,), ("source-env:"+name,))


def receipt(payload, complete=True):
    return PayloadReceipt(complete,payload_digest(payload),("audited-evidence",))


def association(targets,states,*,binding=BIND,complete=True):
    a=ForwardAssociation(tuple(targets),tuple(tuple(sorted(s.items())) for s in states),"structure-v1")
    return replace(a,receipt=receipt(a.payload(binding),complete))


def trace(method="B2", candidates=(), *, observations=("o",), units=("u0","u1"), complete=True):
    t=CandidateTrace(method,observations,units,tuple(TraceCandidate(*c) for c in candidates),
        tuple((u,.2) for u in units) if method!="B0" else (),
        tuple((o,4.) for o in observations) if method!="B0" else (),
        "reduced" if method=="B2" else "fixed_distance")
    return replace(t,receipt=receipt(t.payload(BIND),complete))


def choices(sets, *, method="B2", oid="o",complete=True):
    c=ReferenceChoices(oid,tuple(sets))
    return replace(c,receipt=receipt(c.payload(BIND,method),complete))


def compatibility(assignment,compatible=True,complete=True):
    c=AssignmentCompatibility(tuple(sorted((o,tuple(sorted(us))) for o,us in assignment.items())),compatible)
    return replace(c,receipt=receipt(c.payload(BIND),complete))


def baseline(assignment, objective=.2, *, timed_out=False, certified=True, separated=True,method="B2"):
    used={u for us in assignment.values() for u in us}
    best=SimpleNamespace(assignments=assignment,objective=objective,
        unobserved=tuple(sorted({"u0","u1"}-used)),
        unexplained=tuple(sorted(o for o,us in assignment.items() if not us)),certified=certified)
    margins={o:SimpleNamespace(status="optimal",certified=certified,value=1. if separated else 0.,
        alternative_objective=objective+(1. if separated else 0.)) for o in assignment}
    def attempt(purpose, value):
        return SimpleNamespace(purpose=purpose,status="optimal",raw_status=0,message="synthetic fixture",
            optimal=certified,timed_out=timed_out,objective=value,mip_gap=0.,dual_bound=value)
    attempts=(attempt("best",objective),)+tuple(attempt("margin:"+o,m.alternative_objective) for o,m in margins.items())
    raw=SimpleNamespace(best=best,optimal=certified,timed_out=timed_out,margins=margins,
        status="optimal",identification_quotient="none",top_k_certified=True,exhausted=False,
        alternatives=(),attempts=attempts)
    return SimpleNamespace(method=method,status="optimal",certified=certified,timed_out=timed_out,
        solver_result=raw,observation_determinate={o:separated for o in assignment},
        cost_convention="reduced" if method=="B2" else "fixed_distance")


def synthetic_certificate(result, candidate_trace, *, tolerance=1e-7, offset=0., complete=True):
    # Synthetic test evidence only. Production certificates come from the actual
    # audited execution wrapper, never from this convenience fixture.
    cert=SolverResultCertificate(candidate_trace.receipt.payload_sha256,
        result_snapshot_digest(result),tolerance,offset,"5"*64,"6"*64)
    return replace(cert,receipt=receipt(cert.payload(BIND),complete))


def diagnose(result, compat, witness, candidate_trace):
    return objective_diagnostic(result,compat,witness,binding=BIND,trace=candidate_trace,
        result_certificate=synthetic_certificate(result,candidate_trace))


class ForwardTests(unittest.TestCase):
    def test_scalar_sign_and_same_artifact_across_arms(self):
        p=predictions([[(3.,1.)]])
        a=association([target("t",1.)],[{"t":"u0"}])
        values=[shared_forward(p,a,binding=BIND) for _ in ("B0","B1","B2")]
        self.assertEqual(len({v["artifact_sha256"] for v in values}),1)
        self.assertEqual(values[0]["scalar_mae"],2.)
        self.assertEqual(values[0]["scalar_bias"],2.)
        self.assertEqual(values[0]["fixed_reference_targets"],1)

    def test_fixed_mixture_is_not_mean_or_nearest_identity(self):
        p=predictions([[(-1.,.5),(1.,.5)]])
        a=association([target("t",0.)],[{"t":"u0"}])
        out=shared_forward(p,a,binding=BIND)
        self.assertIsNone(out["scalar_mae"])
        self.assertEqual(out["mixture_mean"],1.)
        self.assertEqual(out["mixture_count"],1)
        self.assertNotIn("chosen_carrier",out["rows"][0])

    def test_identical_score_does_not_hide_different_prediction_payload(self):
        a=association([target("t",0.)],[{"t":"u0"}])
        first=shared_forward(predictions([[(-1.,.5),(1.,.5)]]),a,binding=BIND)
        second=shared_forward(predictions([[(-2.,.25),(0.,.5),(2.,.25)]]),a,binding=BIND)
        self.assertEqual(first["mixture_mean"],second["mixture_mean"])
        self.assertNotEqual(first["prediction_payload_sha256"],second["prediction_payload_sha256"])
        self.assertNotEqual(first["artifact_sha256"],second["artifact_sha256"])

    def test_nonuniform_weights_retained(self):
        p=predictions([[(0.,.25),(4.,.75)]])
        a=association([target("t",0.)],[{"t":"u0"}])
        self.assertEqual(shared_forward(p,a,binding=BIND)["mixture_mean"],3.)

    def test_joint_bounds_do_not_sum_incompatible_pointwise_minima(self):
        p=predictions([[(0.,1.)],[(10.,1.)]])
        a=association([target("a",0.),target("b",0.)],
            [{"a":"u0","b":"u1"},{"a":"u1","b":"u0"}])
        out=shared_forward(p,a,binding=BIND)
        self.assertEqual([(r["lower"],r["upper"]) for r in out["rows"]],[(0.,10.),(0.,10.)])
        self.assertEqual(out["record_joint_bound"]["lower"],5.)
        self.assertEqual(out["record_joint_bound"]["upper"],5.)
        self.assertEqual(out["scalar_count"],0)

    def test_equal_numeric_error_does_not_make_identity_unique(self):
        p=predictions([[(1.,1.)],[(1.,1.)]])
        a=association([target("t",0.)],[{"t":"u0"},{"t":"u1"}])
        row=shared_forward(p,a,binding=BIND)["rows"][0]
        self.assertEqual(row["status"],"ambiguity_bounds")
        self.assertFalse(row["identity_unique"])
        self.assertEqual(row["lower"],row["upper"])

    def test_attachment_family_requires_permutation_closure(self):
        p=predictions([[(0.,1.)],[(10.,1.)]],attachment=(("u0","u1"),))
        a=association([target("t",0.)],[{"t":"u0"}])
        out=shared_forward(p,a,binding=BIND)
        self.assertEqual(out["status"],"unknown")
        self.assertIn("attachment_joint_family_not_complete",out["reason_codes"])
        a=association([target("t",0.)],[{"t":"u0"},{"t":"u1"}])
        self.assertEqual(shared_forward(p,a,binding=BIND)["bounded_count"],1)

    def test_source_slots_and_unit_injection_conserve_capacity(self):
        p=predictions([[(0.,1.)],[(1.,1.)]])
        bad=[association([target("a",0.),target("b",0.)],[{"a":"u0","b":"u0"}]),
             association([target("a",0.,("s",)),target("b",0.,("s",))],[{"a":"u0","b":"u1"}]),
             association([target("a",0.,("s0","s1"))],[{"a":"u0"}])]
        for a in bad:
            with self.assertRaises(ValueError): shared_forward(p,a,binding=BIND)

    def test_methyl_representative_not_expanded_and_parent_unknown(self):
        bind=replace(BIND,nucleus="1H")
        p=predictions([[(1.,1.)],[(3.,1.)]],nucleus="1H",masses=[3,2])
        a=association([target("methyl",1.,("h0","h1","h2")),target("ch2",2.,("h3",))],
                      [{"methyl":"u0","ch2":"u1"}],binding=bind)
        out=shared_forward(p,a,binding=bind)
        self.assertEqual(out["scalar_count"],2)
        self.assertEqual(out["scalar_mae"],.5)
        p=predictions([[(1.,1.)]],nucleus="1H",masses=[2],registry=False)
        a=association([target("h",0.)],[{"h":"parent:0"}],binding=bind)
        out=shared_forward(p,a,binding=bind)
        self.assertEqual(out["unknown_count"],1)
        self.assertIsNone(out["record_joint_bound"])

    def test_incomplete_or_missing_predictions_keep_reference_count(self):
        a=association([target("a",0.)],[{"a":"u0"}],complete=False)
        out=shared_forward(predictions([[(1.,1.)]]),a,binding=BIND)
        self.assertEqual(out["status"],"unknown")
        self.assertEqual(out["fixed_reference_targets"],1)
        a=association([target("a",0.)],[{"a":"u0"}])
        self.assertEqual(shared_forward(None,a,binding=BIND)["fixed_reference_targets"],1)

    def test_hash_mismatch_and_budget_fail_closed(self):
        p=predictions([[(1.,1.)]])
        a=association([target("t",0.)],[{"t":"u0"}])
        with self.assertRaises(ValueError):
            shared_forward(p,replace(a,states=()),binding=BIND)
        out=shared_forward(p,a,binding=BIND,budget=DiagnosticBudget(max_checks=0))
        self.assertEqual(out["status"],"unknown")
        self.assertEqual(out["fixed_reference_targets"],1)
        self.assertNotIn("scalar_mae",out)


class CandidateWitnessTests(unittest.TestCase):
    def test_gate_exclusion_needs_complete_trace_and_choices(self):
        t=trace(candidates=[("o",("u1",),1.)])
        out=candidate_diagnostics(t,choices([("u0",)]),binding=BIND)
        self.assertTrue(out["local_reference_representable"])
        self.assertTrue(out["numerical_gate_excluded"])
        self.assertEqual(out["global_feasibility"],"unknown")
        for missing in (replace(t,receipt=None),replace(t,receipt=receipt(t.payload(BIND),False))):
            self.assertEqual(candidate_diagnostics(missing,choices([("u0",)]),binding=BIND)["status"],"unknown")
        self.assertEqual(candidate_diagnostics(t,choices([("u0",)],complete=False),binding=BIND)["status"],"unknown")

    def test_surviving_candidate_not_excluded_empty_choices_not_gate(self):
        t=trace(candidates=[("o",("u0",),1.)])
        out=candidate_diagnostics(t,choices([("u0",),("u1",)]),binding=BIND)
        self.assertTrue(out["local_reference_candidate_emitted"])
        self.assertFalse(out["numerical_gate_excluded"])
        out=candidate_diagnostics(t,choices([]),binding=BIND)
        self.assertFalse(out["local_reference_representable"])
        self.assertFalse(out["numerical_gate_excluded"])

    def test_B0_B1_cannot_claim_distance_gate(self):
        for method in ("B0","B1"):
            t=trace(method=method,candidates=[("o",("u0",),0.),("o",("u1",),100.)])
            self.assertFalse(candidate_diagnostics(t,choices([("u1",)],method=method),binding=BIND)["numerical_gate_excluded"])
            t=trace(method=method,candidates=[("o",("u0",),0.)])
            with self.assertRaises(ValueError):
                candidate_diagnostics(t,choices([("u1",)],method=method),binding=BIND)

    def test_receipt_binding_and_duplicate_candidates(self):
        t=trace(candidates=[("o",("u0",),0.)])
        with self.assertRaises(ValueError):
            candidate_diagnostics(t,choices([("u0",)]),binding=replace(BIND,reference_sha256="4"*64))
        t=trace(candidates=[("o",("u0",),0.),("o",("u0",),1.)])
        with self.assertRaises(ValueError): candidate_diagnostics(t,choices([("u0",)]),binding=BIND)

    def test_local_correct_candidates_do_not_prove_global_feasibility(self):
        t=trace(candidates=[("a",("u0",),0.),("b",("u0",),0.)],observations=("a","b"))
        for oid in ("a","b"):
            self.assertTrue(candidate_diagnostics(t,choices([("u0",)],oid=oid),binding=BIND)["local_reference_candidate_emitted"])
        assignment={"a":("u0",),"b":("u0",)}
        out=validate_witness(assignment,t,compatibility(assignment),binding=BIND)
        self.assertFalse(out["feasible"])
        self.assertEqual(out["reason_codes"],("capacity_reuse",))

    def test_existing_witness_uses_exact_candidate_and_dummy_costs(self):
        t=trace(candidates=[("a",("u0",),1.),("b",("u1",),2.)],observations=("a","b"))
        assignment={"a":("u0",),"b":()}
        out=validate_witness(assignment,t,compatibility(assignment),binding=BIND)
        self.assertTrue(out["compatible"])
        self.assertAlmostEqual(out["objective"],5.2)
        self.assertEqual(out["missing_unit_ids"],("u1",))
        self.assertEqual(out["unexplained_observation_ids"],("b",))
        self.assertEqual(validate_witness(assignment,t,None,binding=BIND)["status"],"unknown")
        bad={"a":("u1",),"b":()}
        self.assertFalse(validate_witness(bad,t,compatibility(bad),binding=BIND)["feasible"])

    def test_raw_normalizers_are_not_subtracted_again(self):
        t=trace(candidates=[("o",("u0",),11.)])
        t=replace(t,missing_costs=(("u0",10.2),("u1",20.2)),cost_convention="raw",receipt=None)
        t=replace(t,receipt=receipt(t.payload(BIND)))
        a={"o":("u0",)}
        self.assertAlmostEqual(validate_witness(a,t,compatibility(a),binding=BIND)["objective"],31.2)

    def test_objective_certificate_reuses_existing_margins(self):
        t=trace(candidates=[("o",("u0",),1.),("o",("u1",),0.)])
        correct={"o":("u0",)}
        wrong={"o":("u1",)}
        witness=validate_witness(correct,t,compatibility(correct),binding=BIND)
        self.assertEqual(witness["candidate_trace_payload_sha256"],t.receipt.payload_sha256)
        out=diagnose(baseline(wrong),compatibility(wrong,False),witness,t)
        self.assertTrue(out["certified_incompatible_choice_with_reference_witness"])
        self.assertAlmostEqual(out["witness_minus_best"],1.)
        self.assertEqual(out["candidate_trace_payload_sha256"],t.receipt.payload_sha256)
        for r in (baseline(wrong,separated=False),baseline(wrong,timed_out=True),baseline(wrong,certified=False)):
            self.assertEqual(diagnose(r,compatibility(wrong,False),witness,t)["status"],"unknown")
        self.assertEqual(diagnose(baseline(wrong),None,witness,t)["status"],"unknown")
        bad=dict(witness,objective=0.)
        with self.assertRaises(ValueError): diagnose(baseline(wrong),compatibility(wrong,False),bad,t)

    def test_compatible_best_is_not_objective_failure(self):
        t=trace(candidates=[("o",("u0",),1.)])
        a={"o":("u0",)}
        witness=validate_witness(a,t,compatibility(a),binding=BIND)
        out=diagnose(baseline(a,objective=1.2),compatibility(a),witness,t)
        self.assertFalse(out["certified_incompatible_choice_with_reference_witness"])

    def test_original_cross_trace_false_best_is_rejected(self):
        # Independent-review D1: true T cost of u1 is 2.2, not the claimed .2.
        t=trace(candidates=[("o",("u0",),1.),("o",("u1",),2.)])
        good={"o":("u0",)}
        wrong={"o":("u1",)}
        witness=validate_witness(good,t,compatibility(good),binding=BIND)
        fake=baseline(wrong,objective=.2)
        with self.assertRaisesRegex(ValueError,"best_objective_trace_mismatch"):
            diagnose(fake,compatibility(wrong,False),witness,t)
        # Without an explicit execution certificate the old call is unknown.
        out=objective_diagnostic(fake,compatibility(wrong,False),witness,binding=BIND)
        self.assertEqual(out["status"],"unknown")
        self.assertEqual(out["reason_codes"],("same_trace_execution_certificate_required",))

    def test_trace_certificate_cannot_be_reused_for_another_problem(self):
        t=trace(candidates=[("o",("u0",),1.),("o",("u1",),2.)])
        other=trace(candidates=[("o",("u0",),1.),("o",("u1",),0.)])
        good={"o":("u0",)}
        wrong={"o":("u1",)}
        witness=validate_witness(good,t,compatibility(good),binding=BIND)
        result=baseline(wrong)
        cert=synthetic_certificate(result,other)
        with self.assertRaisesRegex(ValueError,"candidate_trace_binding_mismatch"):
            objective_diagnostic(result,compatibility(wrong,False),witness,binding=BIND,
                trace=t,result_certificate=cert)
        with self.assertRaisesRegex(ValueError,"candidate_trace_binding_mismatch"):
            objective_diagnostic(result,compatibility(wrong,False),witness,binding=BIND,
                trace=other,result_certificate=cert)

    def test_result_and_margin_snapshots_are_immutable_bindings(self):
        t=trace(candidates=[("o",("u0",),1.),("o",("u1",),0.)])
        good={"o":("u0",)}
        wrong={"o":("u1",)}
        witness=validate_witness(good,t,compatibility(good),binding=BIND)
        for mutation in ("best", "margin", "attempt"):
            r=baseline(wrong)
            cert=synthetic_certificate(r,t)
            if mutation=="best": r.solver_result.best.objective=.3
            elif mutation=="margin": r.solver_result.margins["o"].value=3.
            else: r.solver_result.attempts[-1].objective=3.
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError,"solver_result_certificate_binding_mismatch"):
                objective_diagnostic(r,compatibility(wrong,False),witness,binding=BIND,
                    trace=t,result_certificate=cert)

    def test_tau_and_execution_receipt_are_required_and_bound(self):
        t=trace(candidates=[("o",("u0",),1.),("o",("u1",),0.)])
        good={"o":("u0",)}
        wrong={"o":("u1",)}
        witness=validate_witness(good,t,compatibility(good),binding=BIND)
        r=baseline(wrong)
        cert=synthetic_certificate(r,t)
        for missing in (replace(cert,receipt=None),synthetic_certificate(r,t,complete=False)):
            self.assertEqual(objective_diagnostic(r,compatibility(wrong,False),witness,binding=BIND,
                trace=t,result_certificate=missing)["status"],"unknown")
        with self.assertRaisesRegex(ValueError,"receipt_payload_mismatch"):
            objective_diagnostic(r,compatibility(wrong,False),witness,binding=BIND,trace=t,
                result_certificate=replace(cert,tie_relative_tolerance=1.))
        self.assertEqual(objective_diagnostic(r,compatibility(wrong,False),witness,binding=BIND,
            trace=t,result_certificate=synthetic_certificate(r,t,tolerance=2.))["status"],"unknown")
        with self.assertRaisesRegex(ValueError,"nonraw_objective_offset"):
            objective_diagnostic(r,compatibility(wrong,False),witness,binding=BIND,trace=t,
                result_certificate=synthetic_certificate(r,t,offset=1.))

    def test_backend_attempts_and_margin_arithmetic_required(self):
        t=trace(candidates=[("o",("u0",),1.),("o",("u1",),0.)])
        good={"o":("u0",)}
        wrong={"o":("u1",)}
        witness=validate_witness(good,t,compatibility(good),binding=BIND)
        for mutation in ("missing_best", "missing_margin", "gap_arithmetic", "unoptimal_attempt"):
            r=baseline(wrong)
            if mutation=="missing_best": r.solver_result.attempts=r.solver_result.attempts[1:]
            elif mutation=="missing_margin": r.solver_result.attempts=r.solver_result.attempts[:1]
            elif mutation=="gap_arithmetic": r.solver_result.margins["o"].value=.5
            else: r.solver_result.attempts[-1].optimal=False
            with self.subTest(mutation=mutation):
                self.assertEqual(diagnose(r,compatibility(wrong,False),witness,t)["status"],"unknown")

    def test_best_candidate_dummy_and_domains_revalidated(self):
        t=trace(candidates=[("o",("u0",),1.),("o",("u1",),0.)])
        good={"o":("u0",)}
        wrong={"o":("u1",)}
        witness=validate_witness(good,t,compatibility(good),binding=BIND)
        for mutation in ("missing", "unexplained", "unknown_unit", "unknown_observation"):
            r=baseline(wrong)
            if mutation=="missing": r.solver_result.best.unobserved=()
            elif mutation=="unexplained": r.solver_result.best.unexplained=("o",)
            elif mutation=="unknown_unit": r.solver_result.best.assignments={"o":("x",)}
            else: r.solver_result.best.assignments={"x":("u1",)}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                diagnose(r,compatibility(r.solver_result.best.assignments,False),witness,t)
        no_candidate=trace(candidates=[("o",("u0",),1.)])
        witness=validate_witness(good,no_candidate,compatibility(good),binding=BIND)
        with self.assertRaisesRegex(ValueError,"candidate_not_emitted"):
            diagnose(baseline(wrong),compatibility(wrong,False),witness,no_candidate)

    def test_correct_cost_with_better_reference_witness_never_attributed(self):
        t=trace(candidates=[("o",("u0",),1.),("o",("u1",),2.)])
        good={"o":("u0",)}
        wrong={"o":("u1",)}
        witness=validate_witness(good,t,compatibility(good),binding=BIND)
        # Even fake positive backend claims cannot override a cheaper feasible witness.
        out=diagnose(baseline(wrong,objective=2.2),compatibility(wrong,False),witness,t)
        self.assertEqual(out["status"],"unknown")

    def test_shared_budget_exhaustion_is_unknown(self):
        b=DiagnosticBudget(max_checks=0)
        t=trace(candidates=[("o",("u0",),1.)])
        self.assertEqual(candidate_diagnostics(t,choices([("u0",)]),binding=BIND,budget=b)["status"],"unknown")
        a={"o":("u0",)}
        self.assertEqual(validate_witness(a,t,compatibility(a),binding=BIND,budget=b)["status"],"unknown")


class LedgerActionTests(unittest.TestCase):
    def test_admission_counts_nonexclusive_provenance_reasons(self):
        rows=[AdmissionEntry("a",True,"unique",(),("source",)),
              AdmissionEntry("b",False,"unknown",("mapping_incomplete","original_mol_missing"),("source",))]
        out=admission_summary(rows)
        self.assertEqual(out["cohort_record_count"],2)
        self.assertEqual(out["counts"]["admitted"],1)
        self.assertTrue(out["reasons_nonexclusive"])
        with self.assertRaises(ValueError): admission_summary(rows+[rows[0]])

    def test_dummy_actions_do_not_claim_natural_missing_or_overlap(self):
        result=baseline({"o":()},objective=4.4)
        out=baseline_actions(result,observation_ids=("o",),unit_ids=("u0","u1"))
        self.assertEqual(out["chosen_missing_units"],2)
        self.assertEqual(out["chosen_unexplained_observations"],1)
        self.assertEqual(out["natural_missing_status"],"unknown")
        self.assertEqual(out["natural_overlap_status"],"unknown")
        result=baseline({"o":("u0",)},timed_out=True)
        self.assertEqual(baseline_actions(result,observation_ids=("o",),unit_ids=("u0","u1"))["action_status"],"uncertified_incumbent")

    def test_B0_actions_have_no_dummy_semantics(self):
        r=baseline({"o":("u0",)},method="B0")
        out=baseline_actions(r,observation_ids=("o",),unit_ids=("u0","u1"))
        self.assertIsNone(out["chosen_missing_units"])
        self.assertEqual(out["dummy_semantics"],"not_applicable")


if __name__ == "__main__":
    unittest.main()
