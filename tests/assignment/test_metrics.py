"""功能概述：以合成结构、whole-joint gold 与审核receipt形状验证metrics边界。
MetricsTests 覆盖三证据轨隔离、单峰歧义隔离、每map parent-set化、whole联合反例、
固定失败分母、可信gold额外门禁、完整集合证据绑定、整输入与完整谱区别、成簇CI和NA。
_fixture/reference/status 仅制造标为synthetic的证据定位符，不代表真实实验认证。
依赖：stdlib unittest 与 mapping/metrics；baseline读取测试使用SimpleNamespace模拟输出。
输入输出及副作用：不读真实数据、不加载模型、不拟合参数、不访问API或修改文件。
"""
import unittest
from types import SimpleNamespace
from dataclasses import replace
from nmr_assignment.mapping import build_capacity_layout, make_joint_mapping
from nmr_assignment.metrics import (evaluate_assignment, summarize, paired_gain,
                                    reference_digest, baseline_assignment, raw_topk_unit_hit_bounds)


def _context(**changes):
    out=dict(truth_basis="source_relative_current_serialization",nucleus="13C",
             task_semantics="derived_serialized_value_bin",target_level="parent",
             target_semantics="set",baseline="B1",record_id="synthetic:r",
             connectivity_id="synthetic:connectivity")
    out.update(changes)
    return out


def _core():
    names=("spectrum_authentic","observation_semantics_verified","independent_gold_verified",
           "assignment_provenance_verified","stereo_scope_verified","isotope_scope_verified",
           "parent_assignment_verified","joint_allowed_set_verified","joint_allowed_set_nontrivial")
    return dict({key:True for key in names},gold_evidence_ids=["synthetic:experimental-audit"])


def _reference(obs, variants, *, complete=True, admitted=True, core=None):
    entries={o:dict(admitted=admitted,rule_version="synthetic:rule",
                   implementation_sha256="a"*64,admission_receipt_sha256="b"*64,
                   evidence_ids=["synthetic:admission"],core_evidence=core or {}) for o in obs}
    return dict(input_observation_ids=obs,whole_joint_targets=variants,
                observation_admission=entries,joint_reference_complete=complete,
                joint_nontrivial=bool(variants),joint_evidence_ids=["synthetic:joint-audit"],
                gold_completeness_receipt=dict(complete=complete,receipt_sha256="c"*64,
                    whole_joint_targets_sha256=reference_digest(variants,target_semantics="set"),
                    proof_kind="complete_enumeration",evidence_ids=["synthetic:all-gold-maps"]),
                strict_full_spectrum_evidence={})


def _mapping(swapped=False):
    layout=build_capacity_layout(dict(nucleus="13C",parent_mass={"0":1,"1":1,"2":1},
        isotope_count_verified=True,evidence_ids=["synthetic:graph"],partition_hypothesis_id="synthetic:p"))
    ids=tuple(u.unit_id for u in layout.units)
    maps=(ids,(ids[1],ids[0],ids[2])) if swapped else (ids,)
    mapping=make_joint_mapping(layout,{u:(t,) for u,t in zip(ids,("A","B","C"))},
        maps,level="parent",complete=True,basis="graph_mapping_ambiguity",
        evidence_ids=["synthetic:maps"],target_universe=("A","B","C"),
        completeness_evidence_id="synthetic:complete-maps")
    return ids,mapping


def _status(**changes):
    out=dict(certified=True,timed_out=False,status="synthetic:complete",reuse_semantics="global_exclusive",
             observation_determinate={o:True for o in ("p","q","amb","stable")})
    out.update(changes)
    return out


def _find(rows, metric, observation=None):
    return next(r for r in rows if r.metric==metric and r.observation_id==observation)


class MetricsTests(unittest.TestCase):
    def test_per_observation_projection_does_not_inherit_other_ambiguity(self):
        ids,mapping=_mapping(swapped=True)
        ref=_reference(("amb","stable"),[{"amb":["A"],"stable":["C"]}])
        rows=evaluate_assignment({"amb":(ids[0],),"stable":(ids[2],)},mapping,
            context=_context(),reference=ref,pipeline_status=_status())
        self.assertFalse(_find(rows,"exact_observation","amb").prediction_supported)
        self.assertTrue(_find(rows,"exact_observation","stable").success)

    def test_source_relative_does_not_mint_experimental_flags(self):
        ids,mapping=_mapping()
        ref=_reference(("p",),[{"p":["A"]}])
        source=evaluate_assignment({"p":(ids[0],)},mapping,context=_context(),
                                   reference=ref,pipeline_status=_status())
        trusted=evaluate_assignment({"p":(ids[0],)},mapping,
            context=_context(truth_basis="trusted_experimental"),reference=ref,pipeline_status=_status())
        self.assertTrue(_find(source,"exact_observation","p").success)
        self.assertFalse(_find(trusted,"exact_observation","p").eligible)
        self.assertEqual(ref["observation_admission"]["p"]["core_evidence"],{})

    def test_timeout_and_missing_mapping_keep_gold_denominator(self):
        ids,mapping=_mapping()
        for basis,core in (("source_relative_current_serialization",{}),
                           ("trusted_experimental",_core())):
            ref=_reference(("p",),[{"p":["A"]}],core=core)
            rows=evaluate_assignment(None,None,context=_context(truth_basis=basis),reference=ref,
                                     pipeline_status=_status(certified=False,timed_out=True))
            p=_find(rows,"exact_observation","p")
            self.assertTrue(p.eligible)
            self.assertFalse(p.success)
            self.assertTrue(_find(rows,"all_input_reported_peaks_exact").eligible)

    def test_joint_gold_alternatives_cannot_be_independently_mixed(self):
        ids,mapping=_mapping()
        ref=_reference(("p","q"),[{"p":["A"],"q":["B"]},{"p":["B"],"q":["A"]}])
        rows=evaluate_assignment({"p":(ids[0],),"q":(ids[0],)},mapping,context=_context(baseline="B0"),
            reference=ref,pipeline_status=_status(reuse_semantics="independent_local"))
        self.assertTrue(_find(rows,"compatible_observation","p").success)
        self.assertTrue(_find(rows,"compatible_observation","q").success)
        self.assertFalse(_find(rows,"all_input_joint_compatible").success)
        self.assertFalse(_find(rows,"all_input_reported_peaks_exact").success)

    def test_gold_ambiguity_compatibility_is_not_unique_exact(self):
        ids,mapping=_mapping()
        ref=_reference(("p",),[{"p":["A"]},{"p":["B"]}])
        rows=evaluate_assignment({"p":(ids[0],)},mapping,context=_context(),reference=ref,pipeline_status=_status())
        self.assertTrue(_find(rows,"compatible_observation","p").success)
        self.assertFalse(_find(rows,"exact_observation","p").success)
        self.assertFalse(_find(rows,"exact_observation","p").eligible)
        self.assertTrue(_find(rows,"compatible_observation","p").eligible)

    def test_unknown_or_incomplete_gold_no_vacuous_credit(self):
        ids,mapping=_mapping()
        ref=_reference(("p",),[],admitted=False)
        rows=evaluate_assignment({"p":(ids[0],)},mapping,context=_context(),reference=ref,pipeline_status=_status())
        self.assertFalse(any(r.success for r in rows))
        ref=_reference(("p",),[{"p":["A"]}],complete=False)
        rows=evaluate_assignment({"p":(ids[0],)},mapping,context=_context(),reference=ref,pipeline_status=_status())
        p=_find(rows,"compatible_observation","p")
        self.assertFalse(p.eligible)
        self.assertFalse(p.success)
        self.assertIn("gold:mapping_family_incomplete",p.eligibility_reason_codes)


    def test_gold_eligibility_frozen_independently_of_prediction_outcome(self):
        ids,mapping=_mapping()
        for complete in (True,False):
            ref=_reference(("p",),[{"p":["A"]}],complete=complete)
            good=evaluate_assignment({"p":(ids[0],)},mapping,context=_context(),
                reference=ref,pipeline_status=_status())
            failed=evaluate_assignment(None,None,context=_context(),reference=ref,
                pipeline_status=_status(certified=False,timed_out=True))
            for metric in ("exact_observation","compatible_observation"):
                a,b=_find(good,metric,"p"),_find(failed,metric,"p")
                self.assertEqual(a.eligible,complete)
                self.assertEqual(a.eligible,b.eligible)
                self.assertEqual(a.eligibility_reason_codes,b.eligibility_reason_codes)
                self.assertEqual(a.eligibility_determinator,b.eligibility_determinator)
                self.assertFalse(b.success)

    def test_complete_ambiguous_gold_only_enters_compatibility_denominator(self):
        ids,mapping=_mapping()
        ref=_reference(("p","stable"),[{"p":["A"],"stable":["C"]},
                                       {"p":["B"],"stable":["C"]}])
        rows=evaluate_assignment({"p":(ids[0],),"stable":(ids[2],)},mapping,
            context=_context(),reference=ref,pipeline_status=_status())
        self.assertFalse(_find(rows,"exact_observation","p").eligible)
        self.assertTrue(_find(rows,"compatible_observation","p").eligible)
        self.assertTrue(_find(rows,"exact_observation","stable").eligible)
        self.assertTrue(_find(rows,"all_input_joint_compatible").eligible)
        self.assertTrue(_find(rows,"all_input_joint_compatible").success)
        self.assertFalse(_find(rows,"all_input_reported_peaks_exact").eligible)

    def test_completeness_receipt_bound_to_whole_states(self):
        ids,mapping=_mapping()
        ref=_reference(("p",),[{"p":["A"]}])
        ref["whole_joint_targets"]=[{"p":["B"]}]
        with self.assertRaisesRegex(ValueError,"not bound"):
            evaluate_assignment({"p":(ids[0],)},mapping,context=_context(),reference=ref,pipeline_status=_status())

    def test_parent_set_normalization_is_per_joint_map(self):
        structure=dict(nucleus="1H",parent_mass={"0":3,"1":3},
            isotope_count_verified=True,evidence_ids=["synthetic:graph"],
            partition_hypothesis_id="synthetic:p",partition_evidence_ids=["synthetic:registry"])
        layout=build_capacity_layout(structure,{"groups":[
            dict(unit_id="u0",parents={"0":2,"1":1},mass=3),
            dict(unit_id="u1",parents={"0":1,"1":2},mass=3)]})
        mapping=make_joint_mapping(layout,{"u0":("P","P","Q"),"u1":("P","Q","Q")},
            (("u0","u1"),("u1","u0")),level="parent",complete=True,
            basis="graph_mapping_ambiguity",evidence_ids=["synthetic:maps"],
            target_universe=("P","Q"),completeness_evidence_id="synthetic:all")
        ref=_reference(("p",),[{"p":["P","Q"]}])
        rows=evaluate_assignment({"p":("u0",)},mapping,context=_context(nucleus="1H"),
                                 reference=ref,pipeline_status=_status())
        self.assertTrue(_find(rows,"exact_observation","p").success)

    def test_all_input_exact_does_not_require_full_spectrum_window(self):
        ids,mapping=_mapping()
        ref=_reference(("p",),[{"p":["A"]}],core=_core())
        rows=evaluate_assignment({"p":(ids[0],)},mapping,
            context=_context(truth_basis="trusted_experimental",task_semantics="natural_resonance"),
            reference=ref,pipeline_status=_status())
        self.assertTrue(_find(rows,"all_input_reported_peaks_exact").success)
        self.assertFalse(_find(rows,"strict_full_spectrum").eligible)

    def test_summary_keeps_all_truth_and_task_strata_and_na(self):
        ids,mapping=_mapping()
        rows=[]
        for basis in ("source_relative_current_serialization","source_report_supported","trusted_experimental"):
            for task in ("derived_serialized_value_bin","natural_resonance"):
                rows.extend(evaluate_assignment({"p":(ids[0],)},mapping,
                    context=_context(truth_basis=basis,task_semantics=task),
                    reference=_reference(("p",),[{"p":["A"]}]),pipeline_status=_status()))
        summaries=[r for r in summarize(rows) if r["stratum"]["metric"]=="exact_observation"]
        self.assertEqual(len(summaries),6)
        self.assertEqual(sum(r["precision"] is None for r in summaries),2)
        self.assertTrue(all(r["support_status"]=="off" for r in summaries if r["precision"] is None))

    def test_failure_labels_require_external_evidence_and_allow_multiple(self):
        ids,mapping=_mapping()
        ref=_reference(("p",),[{"p":["B"]}])
        ref["failure_evidence"]={"p":[dict(label="source_conflict",evidence_ids=["synthetic:source-report"]),
                                     dict(label="mapping_unknown",evidence_ids=["synthetic:map-review"])]}
        rows=evaluate_assignment({"p":(ids[0],)},mapping,context=_context(),reference=ref,pipeline_status=_status())
        self.assertEqual(_find(rows,"exact_observation","p").failure_labels,
                         ("source_conflict","mapping_unknown"))
        ref["failure_evidence"]["p"][0]["evidence_ids"]=[]
        with self.assertRaises(ValueError):
            evaluate_assignment({"p":(ids[0],)},mapping,context=_context(),reference=ref,pipeline_status=_status())

    def test_cluster_paired_gain_reproducible_and_mismatch_rejected(self):
        ids,mapping=_mapping()
        rows=[]
        for record,connectivity in (("r1","c1"),("r2","c1"),("r3","c2")):
            for method,target in (("B1",ids[1]),("B2",ids[0])):
                rows.extend(evaluate_assignment({"p":(target,)},mapping,
                    context=_context(record_id=record,connectivity_id=connectivity,baseline=method),
                    reference=_reference(("p",),[{"p":["A"]}]),pipeline_status=_status()))
        first=paired_gain(rows,"B1","B2",replicates=50,seed=7,confidence=.9)
        self.assertEqual(first,paired_gain(rows,"B1","B2",replicates=50,seed=7,confidence=.9))
        entry=next(x for x in first if x["stratum"]["metric"]=="exact_observation")
        self.assertEqual((entry["gain"],entry["CI"],entry["connectivities"]),(1.,(1.,1.),2))
        altered=list(rows)
        altered[0]=replace(altered[0],eligible=False,success=False)
        with self.assertRaisesRegex(ValueError,"denominator"):
            paired_gain(altered,"B1","B2",replicates=50,seed=7,confidence=.9)

    def test_single_cluster_ci_support_off(self):
        ids,mapping=_mapping()
        rows=[]
        for method in ("B1","B2"):
            rows.extend(evaluate_assignment({"p":(ids[0],)},mapping,context=_context(baseline=method),
                reference=_reference(("p",),[{"p":["A"]}]),pipeline_status=_status()))
        self.assertTrue(all(x["CI"] is None and x["support_status"]=="off"
                            for x in paired_gain(rows,"B1","B2",replicates=10,seed=2,confidence=.9)))


    def test_certified_tie_abstains_but_compatibility_is_separate(self):
        ids,mapping=_mapping()
        ref=_reference(("p",),[{"p":["A"]}])
        rows=evaluate_assignment({"p":(ids[0],)},mapping,context=_context(),reference=ref,
            pipeline_status=_status(observation_determinate={"p":False}))
        self.assertTrue(_find(rows,"exact_observation","p").eligible)
        self.assertFalse(_find(rows,"exact_observation","p").success)
        self.assertTrue(_find(rows,"compatible_observation","p").success)
        rows=evaluate_assignment({"p":(ids[0],)},mapping,context=_context(),reference=ref,
            pipeline_status=_status(observation_determinate={}))
        self.assertFalse(_find(rows,"exact_observation","p").success)

    def test_b0_complete_raw_tie_can_be_parent_invariant_but_not_atom(self):
        layout=build_capacity_layout(dict(nucleus="1H",parent_mass={"0":2},
            isotope_count_verified=True,evidence_ids=["synthetic:graph"],
            partition_hypothesis_id="synthetic:p",partition_evidence_ids=["synthetic:registry"]),
            {"groups":[dict(unit_id="u0",parents={"0":1},mass=1),
                       dict(unit_id="u1",parents={"0":1},mass=1)]})
        status=_status(reuse_semantics="independent_local",observation_determinate={"p":False},
            observation_alternatives={"p":("u0","u1")},
            observation_alternatives_complete={"p":True})
        for level,targets,truth,expect in (
            ("parent",{"u0":("P",),"u1":("P",)},["P"],True),
            ("atom",{"u0":("H0",),"u1":("H1",)},["H0"],False)):
            mapping=make_joint_mapping(layout,targets,(("u0","u1"),),
                level=level,complete=True,basis="provenance_lineage",
                evidence_ids=["synthetic:maps"],target_universe=tuple(set(sum(targets.values(),()))),
                completeness_evidence_id="synthetic:complete")
            rows=evaluate_assignment({"p":("u0",)},mapping,
                context=_context(nucleus="1H",baseline="B0",target_level=level),
                reference=_reference(("p",),[{"p":truth}]),pipeline_status=status)
            self.assertEqual(_find(rows,"exact_observation","p").success,expect)



    def test_raw_top3_cutoff_tie_reports_bounds_not_id_selected_accuracy(self):
        ranks=(("a",1,1),("b",2,5),("c",2,5),("d",2,5),("e",2,5))
        bound=raw_topk_unit_hit_bounds(ranks,{"b"},k=3,complete=True,
                                      evidence_ids=["synthetic:full-raw-rank"])
        self.assertEqual((bound["lower"],bound["upper"]),(0,1))
        bound=raw_topk_unit_hit_bounds(ranks,{"b","c","d"},k=3,complete=True,
                                      evidence_ids=["synthetic:full-raw-rank"])
        self.assertEqual((bound["lower"],bound["upper"]),(1,1))
        self.assertEqual(bound["chemical_quotient_top3"],"unsupported")
        self.assertIsNone(raw_topk_unit_hit_bounds(ranks,{"b"},k=3,complete=False,
                            evidence_ids=["synthetic:truncated"])["lower"])

    def test_baseline_reader_never_deduplicates_top3_ties(self):
        result=SimpleNamespace(method="B0",status="local_complete",certified=True,timed_out=False,
            reuse_semantics="independent_local",local=[SimpleNamespace(observation_id="p",
            best_unique=False,local_top3=(("u0",1.),("u1",1.),("u2",2.)))])
        assignment,status=baseline_assignment(result)
        self.assertEqual(assignment,{"p":()})
        self.assertTrue(status["certified"])


if __name__=="__main__":
    unittest.main()
