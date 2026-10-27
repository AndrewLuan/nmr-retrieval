"""功能概述：有限交付verifier的纯合成元数据检查，不读取真实test谱值/JSONL。
fixture生成1371/3637合成身份与四阶段receipt/once/inventory/review/输出链；expectedH/C保持真实None，加载计数来自独立builder receipt。positive
只验证结构契约，不代表真实交付完成。负例单改H假pass、身份顺序、C预测退出洗白、
缺实际输出、独审subject、重复执行、假allmetrics与未完成域，确保不靠泛布尔完成。
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import verify_source_relative_finite_delivery as v

class FiniteTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  def write(name,doc):
   p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True)
   p.write_text(json.dumps(doc,ensure_ascii=False));return {"path":str(p),"sha256":v.digest(p)}
  self.write=write
  h=[{"nucleus":"1H","query_id":"H"+str(i),"ordinal":i} for i in range(1371)]
  c=[{"nucleus":"13C","input_id":"C"+str(i),"ordinal":i} for i in range(3637)]
  fixed=write("ids.json",{"identities":h+c});self.fixed_sha=fixed["sha256"]
  a=write("A.json",dict(H_asset_mode="unavailable",original_H_fixed_test_completion=False,H_fixed_test_assignment_metrics="unavailable",models=0,scores=0))
  def reviewed(name,item):
   return dict(artifact=write(name,dict(decision="PASS_SYNTHETIC_METADATA_ONLY",snapshot={"subject":item["sha256"]})),subject_sha256_path=["snapshot","subject"])
  H=dict(original_identity_count=1371,historical_identity_counts=dict(observed=1000,frequency_crop=200,peak_dropout=171),
   identity_order_sha256=v.canonical(h),retained_ids=[x["query_id"] for x in h],H_fixed_test_scoring_runs=0,H_fixed_test_model_calls=0,
   H_fixed_test_assignment_complete=False,assignment_metrics=None,status="unavailable",replacement_observations=False,
   A_actual=a,A_application_review=reviewed("A-review.json",a),unevaluable_retained_not_replaced=True)
  suite=write("suite.json",dict(execution_authorized=True))
  release=write("release.json",dict(decision="ALLOW_ONCE_C_FIXED_TEST_STAGE_B",suite_manifest_sha256=suite["sha256"],no_retry=True))
  queue=[x["input_id"] for x in c[:-1]]
  report=dict(schema="TEST_STAGE_B_native_test_report_v1",source_relative_only=True,no_test_threshold_reselection=True,
   coverage=dict(original_C_identity_denominator=3637,public_scoring_queue=3636,public_unavailable_unknown=1,H_original_identity_denominator=1371,H_assignment_status="unavailable_no_model_no_assignment_metrics"),
   highconfidence=dict(published=0,test_fit_calls=0))
  outputs=dict(prediction={"status":"synthetic_failed_retained"},
   package=dict(original_identity_denominator=3637,scorequeue=3636,public_unavailable=1,inputs={"predictions":{"rows":3635}}),
   score=dict(status="FROZEN_ASSIGNMENT_EXECUTION_COMPLETED",input_records=3636,original_identity_denominator=3637,record_ledger=[{"input_id":x} for x in queue]),report=report)
  builder=write("builder-receipt.json",dict(model_loads={"13C":1},input_count=3636,input_success=3635,input_failed=1,input_not_started=0))
  self.prediction_receipt_sha=builder["sha256"]
  phases={}
  for name,doc in outputs.items():
   out=write(name+"-output.json",doc)
   claim=write(name+"-claim.json",dict(schema="TEST_STAGE_B_persistent_once_claim_v1",phase=name,scope="execution",retained_on_all_failures=True,suite_manifest_sha256=suite["sha256"],owner_release_sha256=release["sha256"]))
   code=1 if name=="prediction" else 0
   inventory_outputs={"primary.json":out}
   if name=="prediction":inventory_outputs["prediction_preparation/result/receipt.json"]=builder
   inv=write(name+"-inventory.json",dict(child_exit=code,outer_exit=code,once_claim=claim,output_sha256=inventory_outputs))
   receipt=write(name+"-receipt.json",dict(phase=name,actual_inner_exit=code,actual_worker_exit=code,actual_outer_exit=code,input_hashes_unchanged=True,leader_reaped=True,owned_survivors=[],expected_H_model_loads=None,expected_C_model_loads=None,child_output_inventory=inv,once_claim=claim))
   phases[name]=dict(actual_receipt=receipt,primary_output=out,primary_output_inventory_key="primary.json",application_review=reviewed(name+"-review.json",receipt))
  phases["prediction"].update(prediction_receipt=builder,prediction_receipt_inventory_key="prediction_preparation/result/receipt.json")
  C=dict(original_identity_count=3637,identity_order_sha256=v.canonical(c),retained_ids=[x["input_id"] for x in c],
   scorequeue=3636,source_unknown=1,prediction_available=3635,prediction_failed_retained=1,
   unevaluable_retained_not_replaced=True,cache_failed_eligible_retained=True,
   actual_prediction_runs=1,actual_package_runs=1,actual_scoring_runs=1,actual_report_runs=1,
   suite_manifest=suite,owner_release=release,freeze_before_evaluation_verified=True,phases=phases,scorequeue_ids=queue)
  self.t=dict(schema="source_relative_fixed_test_H_unavailable_C_complete_v1",scope_acceptance_sha256=v.AUTH_SHA,fixed_identity_manifest=fixed,H_fixed_test=H,C_native_test=C)
  proof=write("metric-proof.json",{"synthetic":"descriptive_evidence_only"})
  names=v.SUPPORTED|v.UNFINISHED|{"high_confidence","H_fixed_test_assignment"}
  statuses={n:("supported" if n in v.SUPPORTED else "unknown") for n in names}
  statuses.update(high_confidence="off",H_fixed_test_assignment="unavailable",chemical_quotient_top3="unsupported")
  self.metrics=dict(metric_domain_coverage={n:dict(status=statuses[n],scope="source_relative_only",evidence=[proof]) for n in names},original_goal_unfinished_domains=sorted(v.UNFINISHED|{"trusted_experimental","H_fixed_test_assignment"}))
 def tearDown(self):self.tmp.cleanup()
 def verify(self,t=None):
  with patch.multiple(v,IDENTITY_SHA=self.fixed_sha,PREDICTION_RECEIPT_SHA=self.prediction_receipt_sha):return v.verify_test(t or self.t)
 def test_positive_metadata_contract_not_real_completion(self):
  self.assertEqual(set(self.verify()),{"prediction","package","score","report"})
  v.verify_coverage(self.metrics)
 def test_H_fake_pass_rejected(self):
  for k,val in [("H_fixed_test_scoring_runs",1),("H_fixed_test_model_calls",1),("H_fixed_test_assignment_complete",True),("assignment_metrics",{"accuracy":1}),("replacement_observations",True)]:
   t=copy.deepcopy(self.t);t["H_fixed_test"][k]=val
   with self.subTest(k=k),self.assertRaises(ValueError):self.verify(t)
 def test_generic_test_pass_cannot_imply_H_pass(self):
  self.t["fixed_test_passes"]=1
  with self.assertRaisesRegex(ValueError,"generic_H_test_pass_forbidden"):self.verify()
 def test_changed_identity_or_order_rejected(self):
  for axis in ["H_fixed_test","C_native_test"]:
   t=copy.deepcopy(self.t);t[axis]["retained_ids"][0],t[axis]["retained_ids"][1]=t[axis]["retained_ids"][1],t[axis]["retained_ids"][0]
   with self.subTest(axis=axis),self.assertRaises(ValueError):self.verify(t)
  self.t["H_fixed_test"]["identity_order_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"original_identity_order_SHA"):self.verify()
 def test_prediction_actual_failure_cannot_be_washed_zero(self):
  phase=self.t["C_native_test"]["phases"]["prediction"]
  r=v.load(phase["actual_receipt"]["path"])
  r.update(actual_inner_exit=0,actual_worker_exit=0,actual_outer_exit=0)
  phase["actual_receipt"]=self.write("washed-receipt.json",r)
  with self.assertRaisesRegex(ValueError,"actual_exit:prediction"):self.verify()
 def test_claimed_Czero_without_actual_output_rejected(self):
  phase=self.t["C_native_test"]["phases"]["score"]
  Path(phase["primary_output"]["path"]).unlink()
  with self.assertRaisesRegex(ValueError,"evidence_SHA"):self.verify()
 def test_output_not_in_actual_inventory_rejected(self):
  phase=self.t["C_native_test"]["phases"]["score"]
  phase["primary_output_inventory_key"]="imaginary-output.json"
  with self.assertRaises(KeyError):self.verify()
 def test_independent_review_subject_binding_required(self):
  phase=self.t["C_native_test"]["phases"]["report"]
  phase["application_review"]=dict(artifact=self.write("wrong-subject.json",dict(decision="PASS",snapshot={"subject":"0"*64})),subject_sha256_path=["snapshot","subject"])
  with self.assertRaisesRegex(ValueError,"application_review_subject"):self.verify()
 def test_no_repeat_or_bool_as_once_integer(self):
  for val in [2,True]:
   t=copy.deepcopy(self.t);t["C_native_test"]["actual_scoring_runs"]=val
   with self.assertRaisesRegex(ValueError,"once_C"):self.verify(t)
 def test_denominator_domains_not_interchangeable(self):
  for key,val in [("source_unknown",0),("prediction_available",3636),("cache_failed_eligible_retained",False),("original_identity_count",3636)]:
   t=copy.deepcopy(self.t);t["C_native_test"][key]=val
   with self.subTest(key=key),self.assertRaises(ValueError):self.verify(t)
 def test_blanket_allmetrics_and_fake_supported_rejected(self):
  self.metrics["required_metric_families_complete"]=True
  with self.assertRaisesRegex(ValueError,"blanket_all_metrics"):v.verify_coverage(self.metrics)
  del self.metrics["required_metric_families_complete"]
  for name in v.UNFINISHED:
   m=copy.deepcopy(self.metrics);m["metric_domain_coverage"][name]["status"]="supported"
   with self.subTest(name=name),self.assertRaisesRegex(ValueError,"uncompleted_metric"):v.verify_coverage(m)
 def test_original_unfinished_domains_must_remain(self):
  self.metrics["original_goal_unfinished_domains"]=[]
  with self.assertRaisesRegex(ValueError,"original_unfinished_scope"):v.verify_coverage(self.metrics)
 def test_wrong_scope_acceptance_rejected(self):
  self.t["scope_acceptance_sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"scope_acceptance_SHA"):self.verify()
 def full_delivery_fixture(self):
  # These are temporary synthetic artifacts only, never D completion files.
  auth=self.root/"SOURCE_RELATIVE_FINITE_H_UNAVAILABLE_SCOPE_AUTHORIZATION.txt";auth.write_text("synthetic-authority-only")
  strong=self.root/"strong.py";strong.write_text("# synthetic unchanged strong predicate")
  decision=self.write("SOURCE_RELATIVE_COMPLETION_SCOPE_DECISION.json",dict(original_strong_predicate=dict(path=str(strong),sha256=v.digest(strong))))
  authsha=v.digest(auth);self.t["scope_acceptance_sha256"]=authsha
  self.write("test_evaluation.json",self.t);self.write("stratified_metrics.json",self.metrics)
  self.write("source_relative_benchmark_manifest.json",dict(truth_basis="source_relative_current_serialization",reference_basis="source_asserted_encoded_graph",trust_basis="internal_source_consistency",trusted_experimental=False,trusted_experimental_records=0,original_labels_unchanged=True,**{"13C_support_audited":True},unevaluable_identities_retained=True,source_relative_1H_records=2))
  self.write("frozen_definition.json",dict(status="FROZEN_BY_ORIGINAL_SCIENTIFIC_OWNER"))
  self.write("baseline_comparison.json",dict(baseline_runs=[dict(baseline=b,shared_prediction_manifest_sha256="1"*64,status="COMPLETE",inputs_unchanged=True,training_updates=0,all_frozen_input_ids_accounted_for=True,actual_inner_exit=0,actual_external_exit=0) for b in ("B0","B1","B2")]))
  self.write("confidence_calibration.json",dict(selection_split="validation",denominators_and_confidence_intervals_reported=True,truth_bases_not_pooled=True))
  self.write("code_publication.json",dict(repository="https://github.com/AndrewLuan/nmr-retrieval",head_sha="1"*40,remote_main_sha="1"*40,github_main_sha="1"*40,tests_actual_exit=0,actual_execution_scripts_published=True))
  (self.root/"report.md").write_text("Synthetic source-relative report; not real completion")
  (self.root/"demonstrations").mkdir();(self.root/"demonstrations/index.html").write_text("synthetic")
  subjects=[self.root/n for n in v.REQUIRED if n not in {"source_relative_completion.json","source_relative_final_independent_review.json"}]+[auth,Path(decision["path"])]
  closure={str(p.resolve()):v.digest(p) for p in subjects}
  done=dict(status=v.STATUS,scope_acceptance_sha256=authsha,overall_user_goal_fully_met=False,trusted_experimental_benchmark_complete=False,H_fixed_test_assignment_complete=False,missing_original_annotation_evidence=["synthetic unavailable"],training_updates=0,external_LLM_API_calls=0,SpatialShift_weights_or_pseudolabels_used=False,test_used_for_parameter_selection=False,historical_test_blind_claim=False,evidence_sha256=closure)
  self.write("source_relative_completion.json",done)
  self.write("source_relative_final_independent_review.json",dict(status="PASS_SOURCE_RELATIVE_DELIVERY",independent=True,trusted_experimental_benchmark_complete=False,scope_acceptance_sha256=authsha,reviewed_evidence_sha256=closure))
  return dict(AUTH_SHA=authsha,DECISION_SHA=decision["sha256"],STRONG_SHA=v.digest(strong),IDENTITY_SHA=self.fixed_sha,PREDICTION_RECEIPT_SHA=self.prediction_receipt_sha)
 def test_full_synthetic_metadata_validation_only(self):
  bindings=self.full_delivery_fixture()
  with patch.multiple(v,**bindings):self.assertTrue(v.validate(self.root))
 def test_finite_completion_never_promotes_strong_or_trusted_or_H(self):
  bindings=self.full_delivery_fixture();path=self.root/"source_relative_completion.json";done=v.load(path)
  for key in ("overall_user_goal_fully_met","trusted_experimental_benchmark_complete","H_fixed_test_assignment_complete"):
   changed=copy.deepcopy(done);changed[key]=True;path.write_text(json.dumps(changed))
   with self.subTest(key=key),patch.multiple(v,**bindings),self.assertRaisesRegex(ValueError,"strong_goal_not_met"):v.validate(self.root)
 def test_final_review_must_bind_whole_actual_closure(self):
  bindings=self.full_delivery_fixture();p=self.root/"source_relative_final_independent_review.json";doc=v.load(p);doc["reviewed_evidence_sha256"]={};p.write_text(json.dumps(doc))
  with patch.multiple(v,**bindings),self.assertRaisesRegex(ValueError,"final_review_exact_closure"):v.validate(self.root)
 def update_builder(self,doc,inventory_sha=None):
  phase=self.t["C_native_test"]["phases"]["prediction"]
  builder=self.write("builder-receipt-changed.json",doc);phase["prediction_receipt"]=builder
  self.prediction_receipt_sha=builder["sha256"]
  receipt=v.load(phase["actual_receipt"]["path"]);inv=v.load(receipt["child_output_inventory"]["path"])
  inv["output_sha256"][phase["prediction_receipt_inventory_key"]]={"sha256":inventory_sha or builder["sha256"]}
  receipt["child_output_inventory"]=self.write("updated-inventory.json",inv)
  phase["actual_receipt"]=self.write("updated-receipt.json",receipt)
  phase["application_review"]=dict(artifact=self.write("updated-review.json",dict(decision="PASS_SYNTHETIC_METADATA_ONLY",snapshot={"subject":phase["actual_receipt"]["sha256"]})),subject_sha256_path=["snapshot","subject"])
 def test_production_shape_null_expectations_use_actual_C_only_builder(self):
  phases=self.t["C_native_test"]["phases"]
  for phase in phases.values():
   receipt=v.load(phase["actual_receipt"]["path"])
   self.assertIsNone(receipt["expected_H_model_loads"]);self.assertIsNone(receipt["expected_C_model_loads"])
  self.assertEqual(v.load(phases["prediction"]["prediction_receipt"]["path"])["model_loads"],{"13C":1})
  self.verify()
 def test_actual_H_one_or_missing_C_load_reject(self):
  base=v.load(self.t["C_native_test"]["phases"]["prediction"]["prediction_receipt"]["path"])
  for loads in [{"1H":1,"13C":1},{},{"13C":0},{"1H":False,"13C":1}]:
   doc=copy.deepcopy(base);doc["model_loads"]=loads;self.update_builder(doc)
   with self.subTest(loads=loads),self.assertRaises((ValueError,KeyError)):self.verify()
 def test_explicit_actual_H_zero_is_supported(self):
  doc=v.load(self.t["C_native_test"]["phases"]["prediction"]["prediction_receipt"]["path"])
  doc["model_loads"]={"1H":0,"13C":1};self.update_builder(doc);self.verify()
 def test_missing_actual_prediction_receipt_is_not_expectation_zero(self):
  del self.t["C_native_test"]["phases"]["prediction"]["prediction_receipt"]
  with self.assertRaises(KeyError):self.verify()
 def test_actual_prediction_counts_and_missing_fields_rejected(self):
  base=v.load(self.t["C_native_test"]["phases"]["prediction"]["prediction_receipt"]["path"])
  for key,number in [("input_count",3635),("input_success",3634),("input_failed",0),("input_not_started",1)]:
   doc=copy.deepcopy(base);doc[key]=number;self.update_builder(doc)
   with self.subTest(key=key),self.assertRaisesRegex(ValueError,"actual_prediction_count"):self.verify()
  del doc["input_failed"];self.update_builder(doc)
  with self.assertRaises(KeyError):self.verify()
 def test_actual_receipt_SHA_and_inventory_both_required(self):
  base=v.load(self.t["C_native_test"]["phases"]["prediction"]["prediction_receipt"]["path"])
  self.update_builder(base,inventory_sha="0"*64)
  with self.assertRaisesRegex(ValueError,"prediction_receipt_inventory_binding"):self.verify()
  self.update_builder(base)
  self.t["C_native_test"]["phases"]["prediction"]["prediction_receipt"]["sha256"]="0"*64
  with self.assertRaisesRegex(ValueError,"evidence_SHA"):self.verify()
 def test_zero_expectation_never_overrides_actual_H_one(self):
  phase=self.t["C_native_test"]["phases"]["prediction"]
  receipt=v.load(phase["actual_receipt"]["path"]);receipt["expected_H_model_loads"]=0
  phase["actual_receipt"]=self.write("expected-zero-receipt.json",receipt)
  doc=v.load(phase["prediction_receipt"]["path"]);doc["model_loads"]={"1H":1,"13C":1}
  self.update_builder(doc)
  with self.assertRaisesRegex(ValueError,"actual_fixed_H_model_loads"):self.verify()
if __name__=="__main__":unittest.main()
