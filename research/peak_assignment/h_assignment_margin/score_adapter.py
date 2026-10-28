"""功能：对冻结四末模型中的一个242条缓存执行原B2归属，默认不执行。

training_gate先验证共同release的actual成功训练回执、完整四checkpoint、固定曝光及
既有实际应用审核leaf；分段completion额外核保留A与两旧失败元数据，失败或partial训练在真实row读取和runtime导入前拒绝。
load_control绑定固定preparation/原数值和原源码；ByteIndex仅构字节偏移，逐条解码延后。
package_prediction把新raw cache_key输出接入原anonymous_payload与evaluate_record，
生成绑定当前文件/行/checkpoint的新lineage，不复制旧H211预测或执行proof。
validate_primary_rows逐观测核同一parent/set/source-relative B2轴、eligibility及其证据，
固定242身份/1256分母；失败、超时和abstain均保留。运行仍调用原execute_record，
10=2+2+5+1秒、cap50000、cost/sigma/gate/dummy/target/reference均来自原冻结数值。
run在record第一次解码前启动原共享时钟，先durable原始执行，再调用原评价；末尾只写
原评价行与显式records.jsonl身份账本（空行记录仍保留），不校准、拟合、选型、bootstrap或加载模型。main需--execute及显式release，
默认仅报告关闭状态。合成检查由synthetic_checks子目录用假executor/元数据执行，
不调用真实评价/solver/forward。旧源、旧包与历史回执均不修改。
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict,replace
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
import time

MODELS=("211_A","211_B","193_A","193_B")
EVIDENCE=("training_success_receipt","training_complete","exposure_order_receipt")
PREPARATION_SHA="2bfc45664b7f951f06eb5bbc8a0c406b219e585a76993282c0a63e0cdc219126"
COHORT_SHA="92befbbaa295e8ed37a72fbbd0c16866ac6e8172e1ea2203ebd0831f1b0585a8"
ORIGINAL_PLAN_SHA="062e146a5ba5fdfe8e3016b07782932d398b51ad4a81a384dade34d77a90392c"
RUNNER_SHA="eae3552a3e98c22966b7e73880ec3d0a1bc5dd961b4a2fb965a098071f5a84d2"
ADAPTER_SHA="525f0332853e8ec92e16cb2bf90cc5be3611d29fc75b76a312a3540413dcafe3"
AXIS=dict(truth_basis="source_relative_current_serialization",nucleus="1H",
 task_semantics="derived_serialized_value_bin",target_level="parent",target_semantics="set",baseline="B2")

def need(ok,reason):
    if not ok:raise ValueError(reason)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1048576),b""):h.update(block)
    return h.hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def cache_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def checked_ref(ref):
    need(isinstance(ref,dict) and all(k in ref for k in ("path","sha256")),"path_sha_ref_required")
    path=Path(ref["path"]);need(sha(path)==ref["sha256"],"bound_file_changed:"+str(path))
    return path

def read_ref(ref):
    return json.loads(checked_ref(ref).read_text())

def leaf(obj,path):
    for key in path:obj=obj[key]
    return obj

def _validate_segmented_completion(actual, complete, jobs, read_json, verify_ref):
    """仅核分段完成的身份与保留失败元数据；不加载checkpoint或科学日志。"""
    fields=("completed_new_jobs","completion_provenance","prior_failed_attempts",
            "original_attempts_success","retained_segment_identity","retained_211_A_checkpoint","completion_plan")
    segmented=(actual.get("schema")=="bounded_H211_JJ_segmented_completion_execution_v1" or
               actual.get("status")=="SEGMENTED_COMPLETION_SUCCESS_PRIOR_FAILURES_RETAINED" or
               any(k in actual for k in fields) or any(k in complete for k in ("completed_new_jobs","completion_provenance")))
    if not segmented:return []
    need(actual.get("schema")=="bounded_H211_JJ_segmented_completion_execution_v1" and
         actual.get("status")=="SEGMENTED_COMPLETION_SUCCESS_PRIOR_FAILURES_RETAINED" and
         actual.get("original_attempts_success") is False,"segmented_completion_status")
    need([(j.get("seed"),j.get("variant")) for j in jobs]==[(211,"A"),(211,"B"),(193,"A"),(193,"B")] and
         actual.get("completed_new_jobs")==complete.get("completed_new_jobs")==jobs[1:],"segmented_new_three_jobs")
    provenance=actual.get("completion_provenance")
    need(isinstance(provenance,dict) and provenance==complete.get("completion_provenance"),"segmented_provenance_binding")
    checked=[]
    def bound(ref,label,decode=False):
        need(isinstance(ref,dict) and set(ref)=={"path","sha256"} and
             isinstance(ref["path"],str) and bool(ref["path"]) and
             isinstance(ref["sha256"],str) and len(ref["sha256"])==64 and
             all(c in "0123456789abcdef" for c in ref["sha256"]),"segmented_ref:"+label)
        verify_ref(ref);checked.append(dict(ref))
        return read_json(ref) if decode else ref
    identity_ref=provenance.get("completed_segment_identity")
    need(actual.get("retained_segment_identity")==identity_ref,"segmented_identity_ref")
    identity=bound(identity_ref,"identity",True)
    need(identity.get("schema")=="H211_completed_segment_identity_v1" and
         identity.get("completed_job")==jobs[0],"segmented_retained_job")
    retained=dict(path=jobs[0]["checkpoint"],sha256=jobs[0]["sha256"])
    need(identity.get("checkpoint")==actual.get("retained_211_A_checkpoint")==provenance.get("retained_A_source")==retained,
         "segmented_retained_checkpoint")
    bound(identity.get("history"),"history")
    accounting=actual.get("prior_failed_attempts")
    need(isinstance(accounting,dict) and type(accounting.get("remaining_wall_seconds")) is int and
         accounting["remaining_wall_seconds"]==14084 and accounting.get("diagnostics_accounted_separately") is True,
         "segmented_time_accounting")
    prior=accounting.get("prior_failed_receipts")
    names=("original_initialization","JJ_resource_stop")
    need(isinstance(prior,dict) and set(prior)==set(names),"segmented_prior_refs")
    need(provenance.get("prior_failed_receipts")==[prior[n] for n in names] and
         identity.get("source_execution_receipt")==prior["JJ_resource_stop"],"segmented_prior_identity")
    expected_shas=("d94721f057ba6e00fff24fa28539dff3759ce12b53943ca9b349354202ccb64b",
                   "4a43c91e968b468f160e0fdc4ad3733e45e7f6e7fea87a35f2821929b4bad0e8")
    for name,expected_sha,child in zip(names,expected_shas,(1,-15)):
        need(prior[name].get("sha256")==expected_sha,"segmented_prior_original_sha:"+name)
        old=bound(prior[name],name,True)
        need(old.get("success") is False and type(old.get("actual_child_exit")) is int and
             old["actual_child_exit"]==child and type(old.get("actual_outer_exit")) is int and
             old["actual_outer_exit"]==1,"segmented_prior_failed_actual:"+name)
        elapsed=old.get("elapsed_seconds")
        need(type(elapsed) in (int,float) and 0<elapsed<14400,"segmented_prior_elapsed:"+name)
        summary={k:old[k] for k in ("actual_child_exit","actual_outer_exit","success","elapsed_seconds")}
        if name=="JJ_resource_stop":
            need(old.get("stop_reason")=="resource_rss_limit","segmented_prior_rss_reason")
            summary["stop_reason"]=old["stop_reason"]
        need(accounting.get(name)==summary,"segmented_prior_summary:"+name)
    plan_ref=actual.get("completion_plan")
    bound(plan_ref,"completion_plan")
    need(plan_ref["sha256"]==provenance.get("completion_plan_sha256"),"segmented_plan_sha")
    bound(provenance.get("continuation_contract"),"continuation_contract")
    return checked

def training_gate(release,*,read=read_ref,verify=checked_ref,checked_refs=None):
    """共同metadata gate；在任何真实评价row或checkpoint消费者导入之前完成。"""
    need(release.get("schema")=="frozen_AB_evaluation_release_v1" and
         release.get("evaluation_release") is True and "execution_release" not in release,"evaluation_release_closed")
    refs=release["inputs"];receipt=read(refs["training_success_receipt"])
    need(receipt.get("success") is True and type(receipt.get("actual_child_exit")) is int and receipt["actual_child_exit"]==0 and
         type(receipt.get("actual_outer_exit")) is int and receipt["actual_outer_exit"]==0 and receipt.get("stop_reason","missing") is None,"actual_training_not_successful")
    complete=read(refs["training_complete"]);jobs=complete.get("results",[])
    need(complete.get("validation_calls")==0 and complete.get("test_calls")==0 and
         complete.get("checkpoint_selection")=="epoch10_only","training_complete_scope")
    need(receipt.get("completed_jobs")==jobs and len(jobs)==4,"four_actual_completed_jobs")
    table={}
    for row in jobs:
        key=str(row["seed"])+"_"+row["variant"]
        need(key in MODELS and key not in table and type(row["steps"]) is int and row["steps"]==770 and
             row["selection"]=="final_epoch_10_only" and re.fullmatch("[0-9a-f]{64}",row["actual_order_sha256"]),"final_epoch10_770_order")
        table[key]=row
    need(set(table)==set(MODELS),"all_four_jobs_required")
    for seed in (211,193):need(table[str(seed)+"_A"]["actual_order_sha256"]==table[str(seed)+"_B"]["actual_order_sha256"],"paired_actual_order_mismatch")
    segmented_refs=_validate_segmented_completion(receipt,complete,jobs,read,verify)
    if checked_refs is not None:checked_refs.extend(segmented_refs)
    exposure=read(refs["exposure_order_receipt"])
    need(exposure.get("schema")=="frozen_AB_training_exposure_order_v1" and
         exposure.get("actual_order_sha256_by_job")=={k:v["actual_order_sha256"] for k,v in table.items()},"exposure_order_binding")
    finals=release["final_checkpoints"];need(set(finals)==set(MODELS),"four_final_checkpoints")
    for key,ref in finals.items():
        row=table[key]
        need(ref["epoch"]==10 and ref["sha256"]==row["sha256"] and
             Path(ref["path"]).resolve()==Path(row["checkpoint"]).resolve(),"checkpoint_job_binding:"+key)
        verify(ref)
    review_ref=release["training_application_review"];review=read(review_ref)
    decision=leaf(review,review_ref["decision_path"])
    need(decision==review_ref["required_decision"] and isinstance(decision,str) and decision.startswith("PASS"),"actual_training_application_review")
    for key,ref in finals.items():
        need(leaf(review,review_ref["checkpoint_sha256_paths"][key])==ref["sha256"],"review_checkpoint_binding:"+key)
    for key in EVIDENCE:
        need(leaf(review,review_ref["evidence_sha256_paths"][key])==refs[key]["sha256"],"review_evidence_binding:"+key)
    need(release.get("no_refit") is True and release.get("seed_mean_selection") is False,"no_refit_or_model_selection")
    return table

class ByteIndex:
    """只索引opaque key字节偏移；不在队列准备时解码真实科学row。"""
    def __init__(self,path,key):
        self.path=Path(path);self.offsets={}
        pattern=re.compile(rb'"'+key.encode()+rb'"\s*:\s*("(?:[^"\\]|\\.)*")')
        with self.path.open("rb") as f:
            while True:
                offset=f.tell();line=f.readline()
                if not line:break
                if not line.strip():continue
                match=pattern.search(line);need(match is not None,"missing_index_key:"+key)
                value=json.loads(match.group(1));need(value not in self.offsets,"duplicate_index_key")
                self.offsets[value]=offset
        self.key=key
    def read(self,key):
        with self.path.open("rb") as f:f.seek(self.offsets[key]);raw=f.readline()
        row=json.loads(raw);need(row[self.key]==key,"index_identity_changed")
        return row,hashlib.sha256(raw).hexdigest()

def selected(row):
    return row["metric"]=="exact_observation" and all(dict(row["context"]).get(k)==v for k,v in AXIS.items())

def validate_primary_rows(rows,baseline,record):
    """仅核固定域与failure布尔，不重算指标。合成fixture可独立调用。"""
    def table(values):
        result={}
        for row in values:
            if selected(row):
                oid=row["observation_id"];need(oid not in result,"duplicate_primary_observation")
                result[oid]=row
        return result
    current=table(rows);original=table(baseline)
    need(set(current)==set(original),"fixed_observation_domain_changed")
    eligible=[]
    for oid,row in current.items():
        base=original[oid]
        need(all(type(row[k]) is bool for k in ("eligible","prediction_supported","success")),"explicit_binary_rows")
        need(not row["success"] or row["eligible"] and row["prediction_supported"],"unsupported_success")
        need(dict(row["context"])==dict(base["context"]),"fixed_context_changed")
        need(dict(row["context"])["connectivity_id"]==record["connectivity_sha256"],"fixed_connectivity_changed")
        for field in ("eligible","eligibility_reason_codes","eligibility_determinator"):
            need(digest(row.get(field))==digest(base.get(field)),"fixed_eligibility_evidence_changed:"+field)
        if row["eligible"]:eligible.append(oid)
    need(eligible==record["eligible_observation_ids"],"fixed_eligible_observation_order")
    return len(eligible)

def force_unavailable(bundle,raw,*,late=False):
    """仅把实际不可用或迟到结果保留为false，不改gold准入。"""
    if late or raw.get("status")!="completed" or raw.get("timed_out") is True:
        reason="pipeline:late_record_consumer_deadline" if late else "pipeline:unavailable_execution"
        bundle["rows"]=tuple(replace(r,prediction_supported=False,success=False,reason_codes=r.reason_codes+(reason,)) for r in bundle["rows"])
        if bundle.get("pipeline_status") is not None:
            bundle["pipeline_status"]=dict(bundle["pipeline_status"],certified=False,timed_out=bool(late or bundle["pipeline_status"].get("timed_out",False)),
              observation_determinate={k:False for k in bundle["pipeline_status"].get("observation_determinate",{})})
        if late:bundle.setdefault("metadata",{})["runner_consumer_deadline_passed"]=True
    return bundle

def execute_then_evaluate(executor,evaluator,payload,*,executor_kwargs,evaluator_kwargs,clock,deadline,durable_raw):
    """薄接线可注入假函数；生产只传原execute_record/evaluate_record。"""
    raw=executor(payload,**executor_kwargs)
    durable_raw(raw)
    remaining=deadline-clock()
    evaluation_raw=raw if remaining>0 else dict(status="total_deadline",result=None,timed_out=True)
    bundle=evaluator(evaluation_raw,remaining,**evaluator_kwargs)
    return raw,force_unavailable(bundle,evaluation_raw,late=clock()>=deadline)

def record_entry(iid,role,seed,arm,rows,raw,raw_ref,elapsed):
    """独立记录身份/执行元数据；空rows不伪造任何科学EvaluationRow。"""
    return dict(input_id=iid,role=role,experiment_seed=seed,experiment_arm=arm,
      rows_count=len(rows),actual_status=raw["status"],raw_execution=raw_ref,
      actual_execution_receipt_sha256=(raw.get("execution_receipt") or {}).get("sha256"),
      elapsed_seconds=elapsed)

def package_prediction(cache_input,cache_prediction,public,gold,*,typed,artifact):
    need(cache_input["status"]=="ok" and cache_input["cache_key"]==cache_prediction["cache_key"],"cache_join")
    need(cache_input["nucleus"]==cache_prediction["nucleus"]==public["nucleus"]=="1H","H_only_cache")
    need(cache_input["actual_conditions_sha256"]==cache_digest(public["actual_conditions"]) and
         cache_input["cache_key_semantics"]=="native_encoded_features_only","actual_conditions_binding")
    pred=typed(cache_prediction["predictions"]);serialized=asdict(pred)
    need(digest(serialized)==digest(cache_prediction["predictions"]),"typed_prediction_payload_changed")
    graph=cache_prediction["native_graph_snapshot"]
    need(cache_digest(graph)==cache_prediction["native_graph_snapshot_sha256"],"native_graph_sha")
    snapshot=dict(canonical_smiles=cache_prediction["canonical_smiles"],rdkit_version=cache_prediction["rdkit_version"],
                  atoms=graph["atoms"],bonds=graph["bonds"])
    need(snapshot==gold["baseline_structure_snapshot"] and snapshot["canonical_smiles"]==public["smiles"],"native_reference_graph_changed")
    stated=gold["baseline_structure_snapshot_sha256"]
    need(stated in (digest(snapshot),hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()),"reference_snapshot_sha")
    body=dict(input_id=public["input_id"],complete=True,baseline_structure_snapshot_sha256=stated,
       native_structure_snapshot_sha256=digest(snapshot),native_graph_snapshot_sha256=cache_prediction["native_graph_snapshot_sha256"],
       layout_sha256=digest(serialized["layout"]),attachment_sha256=digest(dict(blocks=serialized["attachment_blocks"],evidence_ids=serialized["attachment_evidence_ids"])),
       prediction_payload_sha256=digest(serialized),prediction_artifact_sha256=artifact["predictions_sha256"],
       cache_key=cache_input["cache_key"],source_artifact_bindings=artifact,
       evidence_ids=["cache-manifest:"+artifact["manifest_sha256"],"prediction-row:"+artifact["prediction_row_sha256"],"checkpoint:"+artifact["checkpoint_sha256"]])
    return pred,dict(input_id=public["input_id"],predictions=serialized,native_structure_snapshot=snapshot),dict(payload=body,sha256=digest(body))

def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def load_control(args):
    release=read_ref(dict(path=args.release,sha256=args.release_sha256))
    segmented_refs=[]
    training_gate(release,checked_refs=segmented_refs)
    need(release.get("score_adapter_sha256")==sha(__file__),"score_source_binding")
    need(release["inputs"]["score_plan"]==dict(path=args.plan,sha256=args.plan_sha256),"score_plan_binding")
    plan=read_ref(release["inputs"]["score_plan"])
    need(plan["schema"]=="H211_fixed_AB_score_plan_v1" and plan.get("allow_test") is False and plan.get("calibration_fit") is False,"score_plan_scope")
    key=plan["model_key"];need(key in MODELS,"fixed_model_key")
    need(release["inputs"]["preparation"]["sha256"]==PREPARATION_SHA,"frozen_preparation_sha")
    preparation=read_ref(release["inputs"]["preparation"])
    need(release["inputs"]["fixed_cohort"]["sha256"]==COHORT_SHA,"fixed_cohort_sha")
    fixed=read_ref(release["inputs"]["fixed_cohort"])
    cohort=preparation["fixed_cohort"];records=cohort["identity_and_saved_baseline_domain"]
    ids=[r["input_id"] for r in records]
    need(len(ids)==len(set(ids))==242 and fixed["ordered_input_ids"]==ids,"fixed242_order")
    need(Counter(r["role"] for r in records)==Counter(original_val=128,tune=114),"fixed_role_counts")
    need(Counter({role:sum(len(r["eligible_observation_ids"]) for r in records if r["role"]==role) for role in ("original_val","tune")})==Counter(original_val=663,tune=593),"fixed1256_domain")
    need(cohort["combined_exact_eligible"]==1256 and cohort["Htest_allowed"] is False,"fixed_domain_scope")
    refs=[release["inputs"][k] for k in EVIDENCE]+[release["inputs"]["preparation"],release["inputs"]["fixed_cohort"],release["inputs"]["score_plan"],release["training_application_review"]]+list(release["final_checkpoints"].values())
    refs.extend(segmented_refs)
    need(plan["original_scoring_plan"]["sha256"]==ORIGINAL_PLAN_SHA,"original_math_plan_sha")
    old=read_ref(plan["original_scoring_plan"])
    need(plan["source_cohort_sha256"]==old["source_cohort_sha256"],"original_source_cohort_binding")
    need(plan["frozen_runner"]["sha256"]==RUNNER_SHA and plan["evaluation_adapter"]["sha256"]==ADAPTER_SHA,"original_scoring_source_sha")
    refs.extend((plan["original_scoring_plan"],plan["frozen_runner"],plan["evaluation_adapter"]))
    repo=Path(plan["repo"]).resolve()
    for item in old["implementations"]:
        original=Path(item["path"])
        if original.parent.name=="nmr_assignment":
            ref=dict(path=str(repo/"nmr_assignment"/original.name),sha256=item["sha256"]);checked_ref(ref);refs.append(ref)
    for name in ("public","gold","ledger","admissions","numeric_config"):
        ref=plan["inputs"][name]
        need(ref["sha256"]==preparation["frozen_scoring_inputs"][name]["sha256"],"fixed_input_sha:"+name)
        checked_ref(ref);refs.append(ref)
    need(set(plan["baseline_evaluations"])==set(ids),"all242_baseline_refs")
    for record in records:
        ref=plan["baseline_evaluations"][record["input_id"]]
        need(ref["sha256"]==record["existing_B2_evaluation"]["sha256"],"fixed_baseline_sha")
        checked_ref(ref);refs.append(ref)
    cache_release=release["inputs"]["cache_release"];cache_control=read_ref(cache_release);refs.append(cache_release)
    need(cache_control.get("schema")=="frozen_AB_evaluation_release_v1" and cache_control.get("evaluation_release") is True and "execution_release" not in cache_control,"cache_release_not_approved")
    cache={name:read_ref(plan["cache"][name]) for name in ("manifest","receipt")}
    refs.extend(plan["cache"].values())
    for name in ("manifest","receipt"):
        need(cache[name]["model_key"]==key and cache[name]["final_checkpoint_sha256"]==release["final_checkpoints"][key]["sha256"] and
             cache[name]["evaluation_release_sha256"]==cache_release["sha256"],"cache_model_release_binding")
    need(cache["manifest"]["schema"]=="frozen_prediction_cache_manifest_v1","raw_cache_manifest")
    for name,filename in (("inputs","inputs.jsonl"),("predictions","predictions.jsonl"),("receipt","receipt.json")):
        need(cache["manifest"]["outputs"][filename]==plan["cache"][name]["sha256"],"cache_output_binding:"+name)
        checked_ref(plan["cache"][name])
    for ref in refs:checked_ref(ref)
    return release,plan,preparation,records,refs

def run(args):
    release,plan,preparation,records,refs=load_control(args)
    out=Path(args.out);need(not out.exists(),"unique_output_required")
    repo=Path(plan["repo"]).resolve();sys.path.insert(0,str(repo))
    os.environ["PYTHONPATH"]=str(repo)+(os.pathsep+os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    runner=load_module(checked_ref(plan["frozen_runner"]),"frozen_AB_original_runner")
    adapter=load_module(checked_ref(plan["evaluation_adapter"]),"frozen_AB_original_evaluator")
    from nmr_assignment.execution import execute_record,numeric_config_from_frozen,_predictions
    from nmr_assignment.diagnostics import DiagnosticBudget
    original_plan=read_ref(plan["original_scoring_plan"])
    for item in original_plan["implementations"]:
        original=Path(item["path"])
        if original.parent.name=="nmr_assignment":
            module_name="nmr_assignment" if original.name=="__init__.py" else "nmr_assignment."+original.stem
            module=sys.modules.get(module_name)
            if module is not None:
                need(Path(module.__file__).resolve()==repo/"nmr_assignment"/original.name and sha(module.__file__)==item["sha256"],"actual_imported_source_binding:"+module_name)
    numeric=numeric_config_from_frozen(read_ref(plan["inputs"]["numeric_config"]))
    budgets=numeric["budgets"]
    need([budgets[k] for k in ("per_record_wall_seconds","mapping_and_candidates_seconds","B1_solver_seconds","B2_solver_seconds","result_validation_reserve_seconds","max_candidates_per_global_problem")]==[10,2,2,5,1,50000],"original_10s_cap50000")
    data={k:ByteIndex(v["path"],"input_id") for k,v in plan["inputs"].items() if k in ("public","gold","ledger","admissions")}
    inputs=ByteIndex(plan["cache"]["inputs"]["path"],"input_id")
    predictions=ByteIndex(plan["cache"]["predictions"]["path"],"cache_key")
    ids=[r["input_id"] for r in records];need(set(inputs.offsets)==set(ids),"cache_all242_identity_domain")
    need(all(set(ids)<=set(x.offsets) for x in data.values()),"reference242_identity_missing")
    out.mkdir();(out/"raw").mkdir();(out/"evaluation").mkdir();(out/"lineage").mkdir()
    runner.durable(out/"initial_fixed_denominators.json",dict(input_ids=ids,eligible=1256,roles=dict(original_val=663,tune=593),policy="Every queued identity/eligible observation remains after any failure",references=refs))
    seed,arm=plan["model_key"].split("_");seed=int(seed);all_rows=[];events=[];used_keys=set();counts=Counter()
    for record in records:
        started=time.monotonic();deadline=started+10;pre_deadline=min(started+2,deadline-1);iid=record["input_id"]
        one={k:index.read(iid)[0] for k,index in data.items()}
        need(set(one["ledger"]["roles"])=={record["role"]} and one["ledger"]["connectivity_sha256"]==record["connectivity_sha256"],"frozen_record_role_connectivity")
        baseline=read_ref(plan["baseline_evaluations"][iid])["B2"]
        need(baseline["metadata"]["input_id"]==iid,"baseline_record_identity")
        def evaluate(pred,raw,payload=None,lineage=None,diagnostic=None):
            return adapter.evaluate_record(one["gold"],one["public"],pred,raw,method="B2",roles=one["ledger"]["roles"],
              source_cohort_sha256=plan["source_cohort_sha256"],connectivity_sha256=record["connectivity_sha256"],
              batch_admission_receipt=one["admissions"]["receipt"],prediction_lineage_receipt=lineage,
              execution_payload=payload,approved_numeric_config=numeric,diagnostic_budget=diagnostic)
        initial=evaluate(None,dict(status="not_started",result=None))
        validate_primary_rows([asdict(r) for r in initial["rows"]],baseline["rows"],record)
        runner.durable(out/"evaluation"/(iid+".not_started.json"),dict(B2=dict(rows=[asdict(r) for r in initial["rows"]],metadata=initial["metadata"])))
        cache_input,input_sha=inputs.read(iid);pred=None;payload=None;lineage=None;consumer_entered=False;raw=dict(status=cache_input["status"],result=None,timed_out=False)
        if cache_input["status"]=="ok":
            try:
                native,prediction_sha=predictions.read(cache_input["cache_key"]);used_keys.add(cache_input["cache_key"])
                artifact=dict(manifest_sha256=plan["cache"]["manifest"]["sha256"],predictions_sha256=plan["cache"]["predictions"]["sha256"],
                  prediction_row_sha256=prediction_sha,input_row_sha256=input_sha,checkpoint_sha256=release["final_checkpoints"][plan["model_key"]]["sha256"],
                  model_key=plan["model_key"],cache_release_sha256=release["inputs"]["cache_release"]["sha256"],score_release_sha256=args.release_sha256,score_source_sha256=sha(__file__))
                pred,wrapped,lineage=package_prediction(cache_input,native,one["public"],one["gold"],typed=_predictions,artifact=artifact)
                snapshot=runner.bound_snapshot(wrapped,lineage);payload,pred=runner.anonymous_payload(one["public"],wrapped["predictions"],snapshot,numeric)
                runner.durable(out/"lineage"/(iid+".json"),dict(input_id=iid,receipt=lineage))
                with (out/"raw"/(iid+".payload.json")).open("xb") as f:f.write(payload);f.flush();os.fsync(f.fileno())
                def consume(evaluation_raw,remaining):
                    return evaluate(pred,evaluation_raw,payload,lineage,DiagnosticBudget(max_checks=50000,time_limit_seconds=min(.25,max(.000001,remaining))))
                def durable_raw(value):
                    runner.durable(out/"raw"/(iid+".json"),dict(input_id=iid,raw_execution=value,payload_sha256=hashlib.sha256(payload).hexdigest(),record_started_at=started,record_deadline=deadline,preprocessing_deadline=pre_deadline))
                consumer_entered=True
                raw,bundle=execute_then_evaluate(execute_record,consume,payload,
                  executor_kwargs=dict(approved_numeric_config=numeric,input_id=iid,prediction_artifact_sha256=artifact["predictions_sha256"],record_started_at=started,record_deadline=deadline,preprocessing_deadline=pre_deadline),
                  evaluator_kwargs={},clock=time.monotonic,deadline=deadline,durable_raw=durable_raw)
            except Exception as exc:
                if consumer_entered:raise
                raw=dict(status="unsupported_cache_or_input",result=None,timed_out=False,detail=type(exc).__name__+":"+str(exc))
                pred=None;bundle=force_unavailable(evaluate(None,raw),raw,late=time.monotonic()>=deadline)
                runner.durable(out/"raw"/(iid+".json"),dict(input_id=iid,raw_execution=raw,record_deadline=deadline))
        else:
            need(cache_input["status"] in ("failed_retained","not_started_retained"),"explicit_cache_failure_status")
            bundle=force_unavailable(evaluate(None,raw),raw,late=time.monotonic()>=deadline)
            runner.durable(out/"raw"/(iid+".json"),dict(input_id=iid,raw_execution=raw,record_deadline=deadline))
        bundle=force_unavailable(bundle,raw,late=time.monotonic()>=deadline)
        rows=[asdict(r) for r in bundle["rows"]]
        counts[record["role"]]+=validate_primary_rows(rows,baseline["rows"],record)
        emitted=[dict(r,input_id=iid,role=record["role"],experiment_seed=seed,experiment_arm=arm) for r in rows]
        all_rows.extend(emitted)
        runner.durable(out/"evaluation"/(iid+".json"),dict(B2=dict(rows=rows,metadata=bundle["metadata"],pipeline_status=bundle["pipeline_status"])))
        raw_path=out/"raw"/(iid+".json")
        events.append(record_entry(iid,record["role"],seed,arm,emitted,raw,dict(path=str(raw_path.resolve()),sha256=sha(raw_path)),time.monotonic()-started))
        runner.durable(out/"record_completion_ledger.json",events)
    need(set(predictions.offsets)==used_keys,"unaccounted_native_cache_key")
    need(counts==Counter(original_val=663,tune=593) and len(events)==242,"final_fixed242_1256_domain")
    rows_path=out/"evaluation_rows.jsonl"
    with rows_path.open("x") as f:
        for row in all_rows:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+"\n")
        f.flush();os.fsync(f.fileno())
    ledger_path=out/"records.jsonl"
    with ledger_path.open("x") as f:
        for row in events:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+"\n")
        f.flush();os.fsync(f.fileno())
    for ref in refs:checked_ref(ref)
    need(sha(args.release)==args.release_sha256 and sha(__file__)==release["score_adapter_sha256"],"control_source_changed")
    cohort=preparation["fixed_cohort"]
    manifest=dict(schema="H211_fixed_AB_assignment_scores_v1",status="COMPLETED_FIXED_B2_EVALUATION",seed=seed,arm=arm,
      rows=dict(path=str(rows_path.resolve()),sha256=sha(rows_path)),preparation_sha256=PREPARATION_SHA,
      fixed_domain=dict(records=242,eligible_by_role=dict(original_val=663,tune=593),combined_exact_eligible=1256,ordered_ids_sha256=cohort["ordered_ids_sha256"],eligible_domain_sha256=cohort["eligible_domain_sha256"]),
      allow_test=False,calibration_fit_calls=0,model_forwards=0,record_ledger=dict(path=str(ledger_path.resolve()),sha256=sha(ledger_path)),source_sha256=sha(__file__),
      release_sha256=args.release_sha256,plan_sha256=args.plan_sha256,new_prediction_lineage=True,execution_receipt_policy="new execute_record receipts for actual completed producers; failure envelopes retained; no old proof copied",execution_receipt_count=sum(r["actual_execution_receipt_sha256"] is not None for r in events))
    runner.durable(out/"manifest.json",manifest)
    print(json.dumps(dict(manifest=str(out/"manifest.json"),sha256=sha(out/"manifest.json"))))

def main():
    p=argparse.ArgumentParser()
    for key in ("plan","plan-sha256","release","release-sha256","out"):p.add_argument("--"+key)
    p.add_argument("--execute",action="store_true");args=p.parse_args()
    if not args.execute:
        print(json.dumps(dict(status="ADAPTER_CLOSED_NO_ROWS_OR_RUNTIME_IMPORTS",evaluation_release=False,scoring_calls=0)));return
    need(all((args.plan,args.plan_sha256,args.release,args.release_sha256,args.out)),"explicit_control_refs_required")
    run(args)
if __name__=="__main__":main()
