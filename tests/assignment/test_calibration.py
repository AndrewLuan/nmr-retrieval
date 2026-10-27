"""功能概述：纯合成验证冻结 validation 校准合同，不读取真实 train/val/test。
主要职责：验证哈希分组、同分块、audit 不重拟合、完整轴分轨、unsupported 分母、
cluster CI 与无支持关闭语义；全数字由显式合成 policy 传入，不运行阈值科学验证。
代码库关系：依赖 calibration 与仓库内 fixtures/identity_free_config.json 的合成冻结schema；
配置fixture只含数值合同，不含源身份、校准产物或私有运行路径；无网络、模型副作用。
"""
from dataclasses import replace
from hashlib import sha256
import unittest
from nmr_assignment.calibration import (CalibrationAxis,EvaluationRecord,CalibrationPolicy,
    connectivity_partition,calibrate,cluster_bootstrap,policy_from_frozen_config,evaluation_record_from_row)


AXIS=CalibrationAxis("B2","1H","derived_serialized_value_bin","parent","source_relative_current_serialization","per_peak",
                     "set","observation",
                     "a"*64,"b"*64,"c"*64,"d"*64)
POLICY=CalibrationPolicy(.9,2,2,2000,173,.95,"assignment-confidence-173|")


def groups(part,count):
    result=[]
    index=0
    while len(result)<count:
        group="synthetic-"+str(index)
        if connectivity_partition(group,split_namespace=POLICY.split_namespace)==part:
            result.append(group)
        index+=1
    return result


def record(name,group,margin=2,correct=True,axis=AXIS,**changes):
    kw=dict(axis=axis,item_id=name,connectivity_id=group,partition="validation",gold_eligible=True,
            prediction_supported=True,margin_certified=True,margin=margin,correct=correct)
    return EvaluationRecord(**dict(kw,**changes))


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.c=groups("calibration",4)
        self.a=groups("audit",4)

    def passing(self):
        return [record("c"+str(i),g) for i,g in enumerate(self.c[:2])]+[
                record("a"+str(i),g) for i,g in enumerate(self.a[:2])]

    def test_first_sha_bit_and_whole_connectivity_partition(self):
        for g in self.c+self.a:
            expected="audit" if sha256((POLICY.split_namespace+g).encode()).digest()[0]&128 else "calibration"
            self.assertEqual(connectivity_partition(g,split_namespace=POLICY.split_namespace),expected)
        self.assertEqual(calibrate(self.passing(),policy=POLICY)[0].status,"on_audit_passed")

    def test_threshold_keeps_tied_blocks_and_never_splits_for_precision(self):
        rows=self.passing()+[record("c-low-yes",self.c[2],1,True),record("c-low-no",self.c[3],1,False)]
        artifact=calibrate(rows,policy=POLICY)[0]
        self.assertEqual(artifact.threshold,2)
        self.assertEqual(artifact.calibration.published_ids,("c0","c1"))
        self.assertEqual(artifact.calibration.coverage,.5)
        self.assertEqual(artifact.precision_metric,"source_assertion_compatibility_precision")
        all_tied=[record("tie"+str(i),g,1,i!=3) for i,g in enumerate(self.c)]
        failed=calibrate(all_tied,policy=POLICY)[0]
        self.assertIsNone(failed.threshold)
        self.assertEqual(failed.status,"off_insufficient_support")
        self.assertEqual(failed.published_ids,())
        self.assertIsNone(failed.publication_precision)

    def test_audit_rejection_does_not_refit_to_a_higher_working_threshold(self):
        rows=[record("c"+str(i),g,2) for i,g in enumerate(self.c[:2])]
        rows += [record("audit-high"+str(i),g,3) for i,g in enumerate(self.a[:2])]
        rows += [record("audit-low"+str(i),g,2,False) for i,g in enumerate(self.a[2:])]
        artifact=calibrate(rows,policy=POLICY)[0]
        self.assertEqual(artifact.threshold,2)
        self.assertEqual(artifact.audit.precision,.5)
        self.assertEqual(artifact.status,"off_audit_rejected")
        self.assertEqual(artifact.published_ids,())
        self.assertIsNone(artifact.publication_precision)
        self.assertEqual(artifact.publication_coverage,0)

    def test_no_pooling_across_truth_basis_or_endpoint_or_source_sha(self):
        rows=self.passing()
        variants=[replace(AXIS,truth_basis="trusted_experimental"),
                  replace(AXIS,endpoint="all_input_reported_peaks_exact",sampling_unit="record"),
                  replace(AXIS,source_sha256="e"*64),replace(AXIS,nucleus="13C")]
        for index,axis in enumerate(variants):
            rows.extend([record("single-c"+str(index),self.c[0],axis=axis),
                         record("single-a"+str(index),self.a[0],axis=axis)])
        artifacts=calibrate(rows,policy=POLICY)
        self.assertEqual(len(artifacts),5)
        self.assertEqual(sum(a.status=="on_audit_passed" for a in artifacts),1)
        for artifact in artifacts:
            if artifact.axis!=AXIS:
                self.assertEqual(artifact.status,"off_insufficient_support")
                self.assertIsNone(artifact.threshold)
        with self.assertRaises(ValueError): replace(AXIS,endpoint="all_input_reported_peaks_exact")

    def test_unsupported_eligible_records_remain_denominator(self):
        rows=self.passing()+[record("unsupported",self.c[2],None,None,
            prediction_supported=False,margin_certified=False)]
        artifact=calibrate(rows,policy=POLICY)[0]
        self.assertEqual(artifact.calibration.eligible_count,3)
        self.assertEqual(artifact.calibration.published_count,2)
        self.assertAlmostEqual(artifact.calibration.coverage,2/3)
        self.assertAlmostEqual(artifact.publication_coverage,4/5)
        self.assertIn("unsupported",artifact.calibration_evidence_ids)

    def test_cluster_bootstrap_keeps_whole_groups_and_zero_support_precision_na(self):
        rows=[record("one",self.c[0],2),record("two",self.c[0],2)]
        ci=cluster_bootstrap(rows,threshold=2,policy=POLICY)
        self.assertEqual(ci,((1.,1.),(1.,1.),2000))
        self.assertEqual(cluster_bootstrap(rows,threshold=None,policy=POLICY),(None,(0.,0.),0))
        self.assertEqual(cluster_bootstrap([],threshold=None,policy=POLICY),(None,None,0))
        # A group with one failure and one success always retains both items.
        mixed=[record("yes",self.c[0],2),record("no",self.c[0],2,False)]
        self.assertEqual(cluster_bootstrap(mixed,threshold=2,policy=POLICY)[0],(.5,.5))

    def test_nonpositive_nonfinite_and_uncertified_scores_never_publish(self):
        rows=[record(str(i),self.c[i%4],margin,margin_certified=cert) for i,(margin,cert) in
              enumerate(((0,True),(-1,True),(float("inf"),True),(float("nan"),True),(2,False)))]
        artifact=calibrate(rows,policy=POLICY)[0]
        self.assertEqual(artifact.calibration.eligible_count,5)
        self.assertIsNone(artifact.threshold)
        self.assertIsNone(artifact.calibration.precision)
        self.assertIsNone(artifact.calibration.precision_ci)
        self.assertEqual(artifact.publication_coverage,0)

    def test_actual_frozen_schema_metrics_adapter_preserves_all_axes(self):
        import json
        from pathlib import Path
        from nmr_assignment.metrics import EvaluationRow
        # Repository-local synthetic schema only; no private config, dataset or calibration result.
        path=Path(__file__).resolve().parent/"fixtures/identity_free_config.json"
        policy=policy_from_frozen_config(json.loads(path.read_text()))
        self.assertEqual((policy.minimum_precision,policy.minimum_published_units,
            policy.minimum_connectivity_groups,policy.bootstrap_replicates,policy.bootstrap_seed),(.9,100,30,2000,173))
        context=dict(baseline="B2",nucleus="1H",task_semantics="derived_serialized_value_bin",
            target_level="parent",target_semantics="set",truth_basis="source_relative_current_serialization",
            record_id="synthetic-record",connectivity_id=self.c[0])
        row=EvaluationRow(tuple(context.items()),"exact_observation","p0",True,True,True,(),())
        kwargs=dict(margin=2,margin_certified=True,cohort_sha256="a"*64,source_sha256="b"*64,
                    label_sha256="c"*64,rule_sha256="d"*64,margin_tolerance=1e-7,
                    pipeline_status={"certified":True,"timed_out":False,"observation_determinate":{"p0":True}})
        records=[evaluation_record_from_row(row,**kwargs)]
        for changes,metric,obs in (({"target_semantics":"nuclear_multiset"},"exact_observation","p0"),
            ({},"all_input_reported_peaks_exact",None),
            ({"truth_basis":"trusted_experimental"},"exact_observation","p0")):
            extra=dict(kwargs)
            if obs is None:
                extra.update(margin=None,margin_tolerance=None,input_observation_ids=("p0",),
                    observation_scores={"p0":dict(margin=2,margin_certified=True,margin_tolerance=1e-7)})
            records.append(evaluation_record_from_row(replace(row,context=tuple(dict(context,**changes).items()),
                metric=metric,observation_id=obs),**extra))
        artifacts=calibrate(records,policy=policy)
        self.assertEqual(len(artifacts),4)
        self.assertTrue(all(a.threshold is None for a in artifacts))
        self.assertTrue(all(a.axis.target_level=="parent" for a in artifacts))
        self.assertEqual({a.axis.sampling_unit for a in artifacts},{"record","observation"})
        self.assertEqual({a.axis.target_semantics for a in artifacts},{"set","nuclear_multiset"})
        self.assertEqual(len({a.axis.truth_basis for a in artifacts}),2)

    def test_adapter_rejects_certified_numeric_tie_and_incomplete_whole_score(self):
        from nmr_assignment.metrics import EvaluationRow
        context=dict(baseline="B2",nucleus="1H",task_semantics="derived_serialized_value_bin",
            target_level="parent",target_semantics="set",truth_basis="source_relative_current_serialization",
            record_id="synthetic-record",connectivity_id=self.c[0])
        row=EvaluationRow(tuple(context.items()),"compatible_observation","p0",True,True,True,(),())
        common=dict(cohort_sha256="a"*64,source_sha256="b"*64,label_sha256="c"*64,rule_sha256="d"*64,
            pipeline_status={"certified":True,"timed_out":False,"observation_determinate":{"p0":True,"p1":True}})
        tied=evaluation_record_from_row(row,margin=5e-8,margin_certified=True,margin_tolerance=1e-7,**common)
        self.assertFalse(tied.margin_certified)
        self.assertTrue(tied.gold_eligible)
        self.assertIsNone(calibrate([tied],policy=POLICY)[0].threshold)
        whole=replace(row,metric="all_input_reported_peaks_exact",observation_id=None)
        missing=evaluation_record_from_row(whole,margin=None,margin_certified=True,margin_tolerance=None,
            input_observation_ids=("p0","p1"),observation_scores={"p0":dict(margin=2,margin_certified=True,margin_tolerance=1e-7)},**common)
        self.assertIsNone(missing.margin)
        self.assertFalse(missing.margin_certified)
        complete=evaluation_record_from_row(whole,margin=None,margin_certified=True,margin_tolerance=None,
            input_observation_ids=("p0","p1"),observation_scores={
                "p0":dict(margin=2,margin_certified=True,margin_tolerance=1e-7),
                "p1":dict(margin=1,margin_certified=True,margin_tolerance=1e-7)},**common)
        self.assertEqual(complete.margin,1)
        self.assertTrue(complete.margin_certified)
        status=dict(common["pipeline_status"],observation_determinate={"p0":False})
        abstain=evaluation_record_from_row(row,margin=2,margin_certified=True,margin_tolerance=1e-7,
            **dict(common,pipeline_status=status))
        self.assertFalse(abstain.margin_certified)

    def test_trusted_compatibility_and_source_report_calibration_are_guarded(self):
        with self.assertRaisesRegex(ValueError,"requires exact"):
            replace(AXIS,truth_basis="trusted_experimental",endpoint="per_peak_compatibility")
        with self.assertRaisesRegex(ValueError,"independent definition"):
            replace(AXIS,truth_basis="source_report_supported")
        self.assertEqual(replace(AXIS,endpoint="per_peak_compatibility").precision_metric,
                         "source_assertion_compatibility_precision")
        self.assertEqual(replace(AXIS,truth_basis="trusted_experimental").precision_metric,
                         "experimental_exact_set_precision")

    def test_strict_validation_and_explicit_policy_config(self):
        with self.assertRaises(ValueError): record("test",self.c[0],partition="test")
        with self.assertRaises(ValueError): calibrate(self.passing()*2,policy=POLICY)
        with self.assertRaises(ValueError): replace(POLICY,bootstrap_replicates=0)
        machine=dict(precision_threshold=.9,min_published_units=2,min_connectivity_groups=2,
            bootstrap_replicates=2000,seed=173,confidence_level=.95,split_namespace=POLICY.split_namespace,
            audit_refit=False,threshold_tie_break="largerthreshold for samecoverage")
        self.assertEqual(policy_from_frozen_config({"machine_calibration_contract":machine}),POLICY)


if __name__=="__main__": unittest.main()
