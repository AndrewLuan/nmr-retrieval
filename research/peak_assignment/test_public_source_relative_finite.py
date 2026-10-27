"""功能概述：有限交付verifier的纯合成元数据检查，不读取真实test谱值/JSONL。
fixture生成1371/3637合成身份与四阶段receipt/once/inventory/review/输出链；expectedH/C保持真实None，加载计数来自独立builder receipt。positive
只验证结构契约，不代表真实交付完成。新增segmentedfixture只创建临时合成文件，覆盖None终态、tmp、第三段、N0、完整root闭包与同原10s时钟。负例单改H假pass、身份顺序、C预测退出洗白、
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

def build_segmented_fixture(base):
 import hashlib,os
 from datetime import datetime
 root=base.root;write=base.write;t=copy.deepcopy(base.t);C=t["C_native_test"]
 auth=write("conditional-authority.json",{"synthetic":"7268-control-only"})
 t.update(schema=v.SEGMENTED_SCHEMA,conditional_scope_authorization=auth)
 queue=C["scorequeue_ids"];prefix=queue[:-3];boundary=queue[-3:-2];suffix=queue[-2:]
 once=root/"once";once.mkdir();partial=root/"original";partial.mkdir()
 impl=write("frozen-control-source.json",{"synthetic":"unchanged"})
 cval=write("Cval-off.json",{"axes":"synthetic-off-metadata"})
 suite=write("seg-suite.json",dict(execution_authorized=True,once_claim_root=str(once),
  implementations={"control":impl},budget={"score":{"total_wall_seconds":7200}},Cval_frozen_calibration=cval))
 owner=write("seg-owner.json",dict(schema="original_owner_test_stage_B_execution_release_v1",decision="ALLOW_ONCE_C_FIXED_TEST_STAGE_B",suite_manifest_sha256=suite["sha256"],no_retry=True,release_id="synthetic-once",once_claim_root=str(once)))
 C.update(suite_manifest=suite,owner_release=owner,execution_protocol="original_partial_plus_one_completion_segment",
  original_single7200_complete=False,actual_completion_segments=1)
 # Rebind original two producer-shaped phase proofs to the same immutable suite/owner.
 for name in ("prediction","package"):
  ph=C["phases"][name];r=v.load(ph["actual_receipt"]["path"]);oldclaim=v.load(r["once_claim"]["path"])
  oldclaim.update(suite_manifest_sha256=suite["sha256"],owner_release_sha256=owner["sha256"])
  claim=write("seg-"+name+"-claim.json",oldclaim);inv=v.load(r["child_output_inventory"]["path"]);inv["once_claim"]=claim
  r.update(once_claim=claim,child_output_inventory=write("seg-"+name+"-inventory.json",inv))
  ph["actual_receipt"]=write("seg-"+name+"-receipt.json",r)
  ph["application_review"]=dict(artifact=write("seg-"+name+"-review.json",dict(decision="PASS_SYNTHETIC",subject=ph["actual_receipt"]["sha256"])),subject_sha256_path=["subject"])
 C["phases"]={k:C["phases"][k] for k in ("prediction","package")}
 inp=write("frozen-input-metadata.json",{"input":"synthetic"})
 original_plan=write("original-plan.json",dict(input_ids=queue,inputs={"metadata":inp},implementations=[impl],output_directory=str(partial)))
 config=write("score-config.json",dict(ordered_input_ids=queue,original_C_identity_count=3637,delegate_plan=original_plan,output_directory=str(partial)))
 phase=write("original-phase.json",dict(schema="TEST_STAGE_B_execution_phase_v1",phase="score",suite_manifest_sha256=suite["sha256"],budget={"total_wall_seconds":7200},config=config))
 request=dict(suite=suite,release=owner,phase=phase)
 expected={x["path"]:x["sha256"] for x in (suite,owner,phase,config,impl,original_plan)}
 key=hashlib.sha256(b"synthetic-once\0score\0execution").hexdigest()
 claim=write("once/"+key+".json",dict(schema="TEST_STAGE_B_persistent_once_claim_v1",phase="score",scope="execution",suite_manifest_sha256=suite["sha256"],owner_release_sha256=owner["sha256"],release_id="synthetic-once",claim_PID=123))
 terminal=write("original-terminal.json",dict(schema="TEST_STAGE_B_phase_actual_v1",phase="score",status="FAILED_OR_PARTIAL_RETAINED_NO_RETRY",
  started_UTC="2026-10-27T00:00:00+00:00",finished_UTC="2026-10-27T02:00:00+00:00",
  actual_inner_exit=None,actual_worker_exit=-9,actual_outer_exit=1,termination_reason="wall_limit",budget={"total_wall_seconds":7200},
  leader_reaped=True,owned_survivors=[],child_PID=123,request_items=request,phase_input_sha256=expected,once_claim=claim))
 (partial/"record_completion_ledger.json").write_text(json.dumps([{"input_id":i,"status":"any_saved_outcome"} for i in prefix]))
 dummy=root/"saved-only.json";dummy.write_text('{"synthetic_saved_control":true}')
 (partial/"raw").mkdir();(partial/"evaluation").mkdir()
 # Shared hardlinked synthetic bytes avoid repeated payload IO; identity/provenance is metadata-only here.
 for iid in prefix:
  for rel in ("raw/"+iid+".json","raw/"+iid+".payload.json","evaluation/"+iid+".json","evaluation/"+iid+".not_started.json"):
   os.link(dummy,partial/rel)
 (partial/"evaluation"/(boundary[0]+".not_started.json")).write_text('{"B0":[],"B1":[],"B2":[]}')
 def seal(name,directory):
  return write(name,{"output_sha256":{str(p.relative_to(directory)):v.digest(p) for p in directory.rglob("*") if p.is_file()}})
 partial_inv=seal("partial-inventory.json",partial)
 inputs=write("input-seal.json",dict(input_sha256={inp["path"]:inp["sha256"],impl["path"]:impl["sha256"]}))
 def reviewed(name,item,**extra):
  return dict(artifact=write(name,dict(decision="PASS_SYNTHETIC",subject=item["sha256"],**extra)),subject_sha256_path=["subject"])
 C["original_score"]=dict(actual_receipt=terminal,claim=claim,scoring_plan=original_plan,partial_inventory=partial_inv,
  input_inventory=inputs,output_root=str(partial),application_review=reviewed("original-application-review.json",terminal,partial_inventory=partial_inv["sha256"],input_inventory=inputs["sha256"]))
 C["original_score"]["application_review"].update(partial_inventory_sha256_path=["partial_inventory"],input_inventory_sha256_path=["input_inventory"])
 parts=dict(prefix=prefix,boundary=boundary,suffix=suffix,recovered_complete_ids=[],original_queue_sha256=v.canonical(queue),touched_ids=prefix+boundary)
 partref=write("partition.json",parts);C["partition"]=partref
 C["partition_application_review"]=reviewed("partition-review.json",partref,saved_eligibility_domains_unchanged=True,no_started_record_retried=True,partial_inventory=partial_inv["sha256"])
 C["partition_application_review"]["partial_inventory_sha256_path"]=["partial_inventory"]
 src={k:write("control-"+k+".json",{"synthetic_source":k}) for k in v.SEGMENT_SOURCE_SHAS}
 src_hash={k:x["sha256"] for k,x in src.items()}
 src_review=write("source-review.json",dict(decision="PASS_SYNTHETIC",source_sha256=src_hash))
 C["completion_sources"]=dict(sources=src,independent_source_review=src_review)
 work=root/"completion_segment_2";output=work/"result";started=work/"started";output.mkdir(parents=True);started.mkdir()
 budget=dict(CPU_threads=1,GPU=0,RSS_bytes=8589934592,total_wall_seconds=15*len(suffix)+600,record_workers=1,cleanup_seconds=60)
 sp=write("segment-plan.json",dict(schema="TEST_STAGE_B_conditional_completion_plan_v1",segment_index=2,third_segment_allowed=False,
  ordered_suffix_ids=suffix,interrupted_unknown_ids=boundary,original_terminal_receipt=terminal,original_partial_inventory=partial_inv,
  original_scoring_plan=original_plan,original_suite=suite,original_claim=claim,original_input_inventory=inputs,budget=budget,
  output_directory=str(output),started_directory=str(started),segment_claim_path=str(once/"CONDITIONAL_COMPLETION_SEGMENT_2.json")))
 release=write("segment-release.json",dict(schema="TEST_STAGE_B_completion_once_release_v1",plan_sha256=sp["sha256"],entrypoint_sha256=src_hash["completion"],execution_authorized=True,independent_review=src_review))
 segment_claim=write("once/CONDITIONAL_COMPLETION_SEGMENT_2.json",dict(schema="TEST_STAGE_B_completion_claim_v1",segment_index=2,no_retry=True,
  plan_sha256=sp["sha256"],original_score_claim=claim,release_sha256=release["sha256"]))
 for iid in suffix:
  common=dict(input_id=iid,original_ordinal=queue.index(iid),segment_plan_sha256=sp["sha256"],input_sha256={"metadata":inp["sha256"]})
  write(str((started/(iid+".read_started.json")).relative_to(root)),dict(common,stage="input_binding_read_started"))
  write(str((started/(iid+".execution_started.json")).relative_to(root)),dict(common,stage="record_execution_started",record_started_at=2.0,record_deadline=12.0,preprocessing_deadline=4.0))
 started_inv=seal("started-inventory.json",started)
 manifest=write(str((output/"manifest.json").relative_to(root)),dict(status="FROZEN_ASSIGNMENT_EXECUTION_COMPLETED",input_records=len(suffix),record_ledger=[{"input_id":i} for i in suffix]))
 result=write(str((output/"completion_segment_receipt.json").relative_to(root)),dict(schema="TEST_STAGE_B_completion_segment_completed_v1",
  segment_index=2,suffix_count=len(suffix),prefix_count=len(prefix),boundary_unknown=boundary,original_C=3637,H_unavailable=1371,
  completion_plan=sp,original_terminal_receipt=terminal,original_outer_exit=1,raw_segment_manifest=manifest))
 actual=write("segment-actual.json",dict(schema="TEST_STAGE_B_phase_actual_v1",status="CHILD_COMPLETED_PENDING_ARTIFACT_AUDIT",elapsed_seconds=1.0,peak_tree_RSS_bytes=1024,phase="completion",actual_inner_exit=0,actual_outer_exit=0,leader_reaped=True,owned_survivors=[],
  input_hashes_unchanged=True,budget=budget,input_sha256={sp["path"]:sp["sha256"],release["path"]:release["sha256"]}))
 execution=dict(phase="completion",actual_receipt=actual,output_root=str(output),output_inventory=seal("segment-inventory.json",output),
  primary_output=result,primary_output_inventory_key="completion_segment_receipt.json",application_review=reviewed("segment-application.json",actual))
 execution["application_review"]=reviewed("segment-application.json",actual,output_inventory=execution["output_inventory"]["sha256"],primary_output=result["sha256"],started_inventory=started_inv["sha256"])
 execution["application_review"].update(output_inventory_sha256_path=["output_inventory"],primary_output_sha256_path=["primary_output"],started_inventory_sha256_path=["started_inventory"])
 C["completion_segment"]=dict(plan=sp,release=release,claim=segment_claim,started_inventory=started_inv,execution=execution)
 reportroot=root/"segmented-report";reportroot.mkdir()
 rp=write("report-plan.json",dict(schema="TEST_STAGE_B_completion_final_report_plan_v1",completion_plan=sp,completion_actual_receipt=actual,completion_output_inventory=execution["output_inventory"],output_directory=str(reportroot),original_owner_suite_release=owner))
 rr=write("report-release.json",dict(schema="TEST_STAGE_B_completion_report_once_release_v1",execution_authorized=True,plan_sha256=rp["sha256"],entrypoint_sha256=src_hash["completion_report"],independent_review=src_review))
 key=hashlib.sha256(b"synthetic-once\0report\0execution").hexdigest()
 reportclaim=write("once/"+key+".json",dict(phase="report",scope="execution",suite_manifest_sha256=suite["sha256"],owner_release_sha256=owner["sha256"]))
 frozen={k:write("report-source-"+k+".json",{"frozen_report":k}) for k in v.FROZEN_REPORT_SHAS}
 report=write("segmented-report/report.json",dict(schema="TEST_STAGE_B_segmented_native_test_report_v1",source_relative_only=True,original_score_rewritten=False,
  native_test=dict(role="native_test",estimator_source_sha256=frozen["estimators"]["sha256"],whole_input_and_strict_full_separate=True,chemical_quotient_top3=None,real_experiment_truth_promoted=False,test_threshold_fit_calls=0),report_claim=reportclaim,original_execution=dict(receipt=terminal,outer_exit=1),completion_execution=dict(receipt=actual,outer_exit=0),
  coverage=dict(original_C_identity_denominator=3637,H_original_identity_denominator=1371,H_assignment_status="unavailable_no_model_no_assignment_metrics",
   public_scoring_queue=3636,public_unavailable_unknown=1,partition={k:parts[k] for k in ("prefix","boundary","suffix")},
   origin_counts={"original_completed":len(prefix),"boundary_saved_initial_unknown":1,"completion_completed":len(suffix)}),
  highconfidence=dict(published=0,test_fit_calls=0,stored_statuses_preserved=True,Cval_artifact_sha256=cval["sha256"],
   reconstructed_fixed_off_metadata_from_saved_rows=True,reconstructed_margins=False,reconstructed_target_invariance=False,
   application_validation=dict(expected_applications=2,validated_applications=2,frozen_method_artifacts=3)),
  new_models=0,new_solves=0,new_gold_evaluations=0,new_mapping_search=0))
 reportactual=write("report-actual.json",dict(schema="TEST_STAGE_B_phase_actual_v1",status="CHILD_COMPLETED_PENDING_ARTIFACT_AUDIT",elapsed_seconds=1.0,peak_tree_RSS_bytes=1024,phase="completion_report",actual_inner_exit=0,actual_outer_exit=0,leader_reaped=True,owned_survivors=[],
  input_hashes_unchanged=True,input_sha256={rp["path"]:rp["sha256"],rr["path"]:rr["sha256"]},budget=dict(CPU_threads=1,GPU=0,RSS_bytes=8589934592,total_wall_seconds=600,record_workers=1,cleanup_seconds=60)))
 frozen={k:write("report-source-"+k+".json",{"frozen_report":k}) for k in v.FROZEN_REPORT_SHAS}
 C["segmented_report"]=dict(plan=rp,release=rr,frozen_implementations=frozen,execution=dict(phase="completion_report",
  actual_receipt=reportactual,output_root=str(reportroot),output_inventory=seal("report-inventory.json",reportroot),
  primary_output=report,primary_output_inventory_key="report.json",application_review=reviewed("report-application.json",reportactual)))
 re=C["segmented_report"]["execution"]
 re["application_review"]=reviewed("report-application.json",reportactual,output_inventory=re["output_inventory"]["sha256"],primary_output=report["sha256"])
 re["application_review"].update(output_inventory_sha256_path=["output_inventory"],primary_output_sha256_path=["primary_output"])
 bindings=dict(IDENTITY_SHA=base.fixed_sha,PREDICTION_RECEIPT_SHA=base.prediction_receipt_sha,SEGMENT_AUTH_SHA=auth["sha256"],
  ORIGINAL_BINDINGS=dict(suite=suite["sha256"],phase=phase["sha256"],owner=owner["sha256"],scoring_plan=original_plan["sha256"]),
  SEGMENT_SOURCE_SHAS=src_hash,FROZEN_REPORT_SHAS={k:x["sha256"] for k,x in frozen.items()})
 return t,bindings


def build_segmented_root_fixture(base,template,bindings):
 extra=base.full_delivery_fixture();root=base.root
 payload=copy.deepcopy(template);payload["scope_acceptance_sha256"]=extra["AUTH_SHA"]
 base.write("test_evaluation.json",payload)
 runs=v.load(root/"baseline_comparison.json")
 for row in runs["baseline_runs"]:
  row.update(status="COMPLETE_ACCOUNTING_SEGMENTED",execution_protocol="original_partial_plus_one_completion_segment",
   original_actual_inner_exit=None,original_actual_external_exit=1,completion_actual_inner_exit=0,completion_actual_external_exit=0)
  row.pop("actual_inner_exit",None);row.pop("actual_external_exit",None)
 base.write("baseline_comparison.json",runs)
 done=v.load(root/"source_relative_completion.json")
 done.update(execution_protocol="original_partial_plus_one_completion_segment",batch_execution_protocol_amended=True,original_single7200_complete=False)
 closure=done["evidence_sha256"]
 for path in list(closure):closure[path]=v.digest(path)
 auth=payload["conditional_scope_authorization"];closure[str(Path(auth["path"]).resolve())]=auth["sha256"]
 base.write("source_relative_completion.json",done)
 review=v.load(root/"source_relative_final_independent_review.json");review["reviewed_evidence_sha256"]=closure
 base.write("source_relative_final_independent_review.json",review)
 merged=dict(extra);merged.update(bindings)
 return merged


class SegmentedFiniteTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.base=FiniteTests("test_positive_metadata_contract_not_real_completion");cls.base.setUp()
  cls.template,cls.bindings=build_segmented_fixture(cls.base)
  cls.root_bindings=build_segmented_root_fixture(cls.base,cls.template,cls.bindings)
 @classmethod
 def tearDownClass(cls):cls.base.tearDown()
 def setUp(self):self.t=copy.deepcopy(self.template)
 def verify(self):
  with patch.multiple(v,**self.bindings):return v.verify_test(self.t)
 def replace_terminal(self,**changes):
  C=self.t["C_native_test"];o=C["original_score"];doc=v.load(o["actual_receipt"]["path"]);doc.update(changes)
  o["actual_receipt"]=self.base.write(self._testMethodName+"-terminal.json",doc)
 def test_complete_synthetic_segmented_metadata_contract(self):
  result=self.verify();self.assertIsNone(result["original_terminal"]["actual_inner_exit"]);self.assertEqual(result["original_terminal"]["actual_outer_exit"],1)
  self.assertEqual(len(result["partition"]["suffix"]),2)
 def test_original_zero_or_wrong_phase_or_unfinished_rejected(self):
  for change in [dict(actual_outer_exit=0),dict(phase="prediction"),dict(finished_UTC="invalid")]:
   self.t=copy.deepcopy(self.template);self.replace_terminal(**change)
   with self.subTest(change=change),self.assertRaises((ValueError,KeyError)):self.verify()
 def test_foreign_request_owner_or_inputclosure_rejected(self):
  C=self.t["C_native_test"];doc=v.load(C["original_score"]["actual_receipt"]["path"])
  request=copy.deepcopy(doc["request_items"]);request["release"]=self.base.write("foreign-owner.json",{"synthetic":"foreign"})
  self.replace_terminal(request_items=request)
  with self.assertRaisesRegex(ValueError,"original_exact_request"):self.verify()
 def test_started_boundary_cannot_enter_suffix(self):
  C=self.t["C_native_test"];parts=v.load(C["partition"]["path"]);parts["suffix"]=[parts["boundary"][0]]+parts["suffix"]
  C["partition"]=self.base.write("bad-partition.json",parts)
  with self.assertRaisesRegex(ValueError,"conservative_exact_partition"):self.verify()
 def test_tmp_touch_outside_boundary_rejected(self):
  C=self.t["C_native_test"];o=C["original_score"];root=Path(o["output_root"])
  tmp=root/"evaluation"/(C["scorequeue_ids"][-1]+".not_started.json.tmp")
  try:
   tmp.write_bytes(b"malformed write establishes touch")
   inv={str(p.relative_to(root)):v.digest(p) for p in root.rglob("*") if p.is_file()}
   o["partial_inventory"]=self.base.write("tmp-partial-inventory.json",{"output_sha256":inv})
   oldreview=v.load(o["application_review"]["artifact"]["path"]);oldreview["partial_inventory"]=o["partial_inventory"]["sha256"]
   o["application_review"]["artifact"]=self.base.write("tmp-original-audit.json",oldreview)
   with self.assertRaisesRegex(ValueError,"started_or_tmp_outside_boundary"):self.verify()
  finally:tmp.unlink(missing_ok=True)
 def test_source_PASS_required_not_changesrequired(self):
  self.t["C_native_test"]["completion_sources"]["independent_source_review"]=self.base.write("source-blocked.json",{"decision":"CHANGES_REQUIRED","source_sha256":self.bindings["SEGMENT_SOURCE_SHAS"]})
  with self.assertRaisesRegex(ValueError,"segment_source_independent_PASS"):self.verify()
 def test_second_segment_partial_cannot_complete(self):
  C=self.t["C_native_test"];e=C["completion_segment"]["execution"];r=v.load(e["actual_receipt"]["path"]);r["actual_inner_exit"]=1
  e["actual_receipt"]=self.base.write("failed-segment.json",r)
  with self.assertRaisesRegex(ValueError,"segment_actual_exit"):self.verify()
 def test_segment_application_audit_required(self):
  e=self.t["C_native_test"]["completion_segment"]["execution"]
  e["application_review"]["artifact"]=self.base.write("bad-application-review.json",dict(v.load(e["application_review"]["artifact"]["path"]),decision="PENDING"))
  with self.assertRaisesRegex(ValueError,"application_review_PASS"):self.verify()
 def test_changed_budget_or_third_segment_rejected(self):
  C=self.t["C_native_test"];sp=v.load(C["completion_segment"]["plan"]["path"]);sp["budget"]["total_wall_seconds"]+=1
  C["completion_segment"]["plan"]=self.base.write("wrong-budget.json",sp)
  with self.assertRaisesRegex(ValueError,"fixed_segment2_budget"):self.verify()
 def test_extra_third_claim_rejected(self):
  C=self.t["C_native_test"];root=Path(v.load(C["suite_manifest"]["path"])["once_claim_root"])
  extra=root/"CONDITIONAL_COMPLETION_SEGMENT_3.json"
  try:
   extra.write_text("{}")
   with self.assertRaisesRegex(ValueError,"no_third_segment_claim"):self.verify()
  finally:extra.unlink(missing_ok=True)
 def test_H_metric_or_replacement_not_allowed_segmented(self):
  self.t["H_fixed_test"]["assignment_metrics"]={"invented_accuracy":1}
  with self.assertRaisesRegex(ValueError,"segmented_H_unavailable"):self.verify()
 def test_missing_journal_or_saved_prefix_bytes_rejected(self):
  C=self.t["C_native_test"];C["completion_segment"]["started_inventory"]=self.base.write("empty-journal-inventory.json",{"output_sha256":{}})
  with self.assertRaisesRegex(ValueError,"sealed_complete_file_inventory"):self.verify()


 def test_full_segmented_root_closure_preserves_original_failure(self):
  with patch.multiple(v,**self.root_bindings):self.assertTrue(v.validate(self.base.root))
 def test_root_false_original_zero_baseline_claim_rejected(self):
  p=self.base.root/"baseline_comparison.json";saved=p.read_bytes()
  try:
   doc=v.load(p);doc["baseline_runs"][0]["original_actual_external_exit"]=0;p.write_text(json.dumps(doc))
   with patch.multiple(v,**self.root_bindings),self.assertRaisesRegex(ValueError,"baseline_original_exit_preserved"):v.validate(self.base.root)
  finally:p.write_bytes(saved)
 def test_report_inventory_without_actual_application_binding_rejects(self):
  proof=self.t["C_native_test"]["segmented_report"]["execution"]
  doc=v.load(proof["application_review"]["artifact"]["path"]);doc["output_inventory"]="0"*64
  proof["application_review"]["artifact"]=self.base.write("wrong-report-inventory-audit.json",doc)
  with self.assertRaisesRegex(ValueError,"actual_application_inventory_output_binding"):self.verify()
 def test_missing_original_request_input_seal_rejected(self):
  C=self.t["C_native_test"];r=v.load(C["original_score"]["actual_receipt"]["path"]);r["phase_input_sha256"]={}
  self.replace_terminal(phase_input_sha256={})
  with self.assertRaisesRegex(ValueError,"original_phase_input_closure"):self.verify()
 def test_Nzero_never_invents_segment_or_unreviewed_report(self):
  import os
  C=self.t["C_native_test"];o=C["original_score"];root=Path(o["output_root"]);queue=C["scorequeue_ids"]
  ledger=root/"record_completion_ledger.json";old=ledger.read_bytes();created=[]
  dummy=self.base.root/"saved-only.json"
  try:
   ledger.write_text(json.dumps([{"input_id":i} for i in queue[:-1]]))
   for iid in queue[-3:-1]:
    for rel in ("raw/"+iid+".json","raw/"+iid+".payload.json","evaluation/"+iid+".json","evaluation/"+iid+".not_started.json"):
     p=root/rel
     if not p.exists():os.link(dummy,p);created.append(p)
   p=root/"evaluation"/(queue[-1]+".not_started.json");os.link(dummy,p);created.append(p)
   inv={str(p.relative_to(root)):v.digest(p) for p in root.rglob("*") if p.is_file()}
   o["partial_inventory"]=self.base.write("N0-original-seal.json",{"output_sha256":inv})
   audit=v.load(o["application_review"]["artifact"]["path"]);audit["partial_inventory"]=o["partial_inventory"]["sha256"]
   o["application_review"]["artifact"]=self.base.write("N0-original-audit.json",audit)
   parts=dict(prefix=queue[:-1],boundary=queue[-1:],suffix=[],recovered_complete_ids=[],original_queue_sha256=v.canonical(queue),touched_ids=queue)
   C["partition"]=self.base.write("N0-partition.json",parts)
   pa=v.load(C["partition_application_review"]["artifact"]["path"]);pa.update(subject=C["partition"]["sha256"],partial_inventory=o["partial_inventory"]["sha256"])
   C["partition_application_review"]["artifact"]=self.base.write("N0-partition-audit.json",pa)
   with self.assertRaisesRegex(ValueError,"empty_suffix_no_invented_segment"):self.verify()
   C["completion_segment"]=None
   with self.assertRaisesRegex(ValueError,"empty_suffix_no_approved_current_native_report_path"):self.verify()
  finally:
   ledger.write_bytes(old)
   for p in created:p.unlink(missing_ok=True)

 def test_reset_record_clock_rejected_with_complete_journal_seal(self):
  C=self.t["C_native_test"];seg=C["completion_segment"];sp=v.load(seg["plan"]["path"]);directory=Path(sp["started_directory"])
  iid=sp["ordered_suffix_ids"][0];path=directory/(iid+".execution_started.json");old=path.read_bytes()
  try:
   j=v.load(path);j["record_deadline"]=j["record_started_at"]+11;path.write_text(json.dumps(j))
   inv={str(p.relative_to(directory)):v.digest(p) for p in directory.rglob("*") if p.is_file()}
   seg["started_inventory"]=self.base.write("wrong-clock-started-seal.json",{"output_sha256":inv})
   with self.assertRaisesRegex(ValueError,"same_original_record_clock"):self.verify()
  finally:path.write_bytes(old)

 def test_segment_actual_wall_or_RSS_excess_not_hidden_by_plan(self):
  base=self.t["C_native_test"]["completion_segment"]["execution"]
  original=v.load(base["actual_receipt"]["path"])
  for key,number in [("elapsed_seconds",original["budget"]["total_wall_seconds"]+61),("peak_tree_RSS_bytes",8589934593)]:
   doc=copy.deepcopy(original);doc[key]=number
   base["actual_receipt"]=self.base.write("bad-resource-"+key+".json",doc)
   with self.subTest(key=key),self.assertRaisesRegex(ValueError,"actual_segment_resource_bounds"):self.verify()


 def rebind_report_native_fields(self,updates=None,missing=(),input_map=None,drop_map=False):
  ri=self.t["C_native_test"]["segmented_report"]
  plan=v.load(ri["plan"]["path"]);plan.update(updates or {})
  for field in missing:plan.pop(field,None)
  serial=getattr(self,"_rebind_serial",0)+1;self._rebind_serial=serial
  tag=self._testMethodName+"-"+str(serial)
  ri["plan"]=self.base.write(tag+"-report-plan.json",plan)
  release=v.load(ri["release"]["path"]);release["plan_sha256"]=ri["plan"]["sha256"]
  ri["release"]=self.base.write(tag+"-report-release.json",release)
  proof=ri["execution"];actual=v.load(proof["actual_receipt"]["path"])
  if drop_map:actual.pop("input_sha256",None)
  else:actual["input_sha256"]=input_map if input_map is not None else {ri["plan"]["path"]:ri["plan"]["sha256"],ri["release"]["path"]:ri["release"]["sha256"]}
  proof["actual_receipt"]=self.base.write(tag+"-report-actual.json",actual)
  audit=v.load(proof["application_review"]["artifact"]["path"]);audit["subject"]=proof["actual_receipt"]["sha256"]
  proof["application_review"]["artifact"]=self.base.write(tag+"-report-application.json",audit)
 def test_production_report_fixture_full_reference_joins_positive(self):
  C=self.t["C_native_test"];ri=C["segmented_report"];rp=v.load(ri["plan"]["path"])
  sp=v.load(C["completion_segment"]["plan"]["path"])
  self.assertEqual(sp["original_input_inventory"],C["original_score"]["input_inventory"])
  self.assertEqual(rp["completion_output_inventory"],C["completion_segment"]["execution"]["output_inventory"])
  self.assertEqual(rp["output_directory"],ri["execution"]["output_root"])
  actual=v.load(ri["execution"]["actual_receipt"]["path"])
  self.assertEqual(actual["input_sha256"],{ri["plan"]["path"]:ri["plan"]["sha256"],ri["release"]["path"]:ri["release"]["sha256"]})
  self.verify()
 def test_report_foreign_or_missing_actual_plan_release_map_rejected(self):
  for wrong in [{},{"foreign-plan":"0"*64},None]:
   self.t=copy.deepcopy(self.template)
   self.rebind_report_native_fields(input_map=wrong,drop_map=wrong is None)
   with self.subTest(wrong=wrong),self.assertRaisesRegex(ValueError,"report_actual_plan_release_input_map"):self.verify()
 def test_foreign_or_missing_report_suffix_inventory_rejected(self):
  C=self.t["C_native_test"];foreign=C["original_score"]["partial_inventory"]
  self.rebind_report_native_fields(updates={"completion_output_inventory":foreign})
  with self.assertRaisesRegex(ValueError,"report_completion_output_inventory_join"):self.verify()
  self.t=copy.deepcopy(self.template);self.rebind_report_native_fields(missing=["completion_output_inventory"])
  with self.assertRaises(KeyError):self.verify()
 def test_foreign_or_missing_report_output_directory_rejected(self):
  self.rebind_report_native_fields(updates={"output_directory":str(self.base.root/"not-selected-report-root")})
  with self.assertRaisesRegex(ValueError,"report_actual_output_directory_join"):self.verify()
  self.t=copy.deepcopy(self.template);self.rebind_report_native_fields(missing=["output_directory"])
  with self.assertRaises(KeyError):self.verify()
 def test_foreign_or_missing_segment_original_input_inventory_rejected(self):
  for missing in (False,True):
   self.t=copy.deepcopy(self.template);C=self.t["C_native_test"];seg=C["completion_segment"];sp=v.load(seg["plan"]["path"])
   if missing:sp.pop("original_input_inventory")
   else:sp["original_input_inventory"]=C["original_score"]["partial_inventory"]
   seg["plan"]=self.base.write(self._testMethodName+str(missing)+"-segment-plan.json",sp)
   with self.subTest(missing=missing):
    if missing:
     with self.assertRaises(KeyError):self.verify()
    else:
     with self.assertRaisesRegex(ValueError,"segment_original_input_inventory_join"):self.verify()
 def test_same_digest_foreign_inventory_path_not_selected_proof(self):
  proof=self.t["C_native_test"]["completion_segment"]["execution"]["output_inventory"]
  path=self.base.root/"samebytes-foreign-inventory.json";path.write_bytes(Path(proof["path"]).read_bytes())
  foreign=dict(path=str(path),sha256=v.digest(path));self.assertEqual(foreign["sha256"],proof["sha256"])
  self.rebind_report_native_fields(updates={"completion_output_inventory":foreign})
  with self.assertRaisesRegex(ValueError,"report_completion_output_inventory_join"):self.verify()

if __name__=="__main__":unittest.main()
