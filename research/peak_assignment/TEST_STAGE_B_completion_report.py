# 功能概述：已审conditional4公开副本，实际源SHA与portableSHA分别绑定。
# 关系：显式runtime授权/源码闭包；保留原终态、once、边界、预算与科学谓词。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding
authorize()
"""功能概述：原非0评分+保守边界unknown+独立completion的显式新report分支。
只读取冻结保存的EvaluationRow；boundary必须已有not_started rows，否则BLOCKED不造分母、不重新evaluate。
collect_rows核完整队列、原inventory/第二段inventory、初始最终资格、source语义和身份；不调用solve/model。
重建阈值应用只读取保存语义轴、真实pipeline可用性及冻结OFF产物，不造reference/margin；cdf原P1校验原封调用。
9d估计器与cdf estimate_native_test原封调用，仅最终汇总一次；原score EXIT、raw、receipt、plan不变。
run使用原suite report持久claim防止另跑普通report，新增精确plan/release/源独审门禁；默认check-only。
"""
from pathlib import Path
from dataclasses import fields
from collections import Counter
import argparse,json,os,sys
import TEST_STAGE_B_completion as c
REPORT_SHA=binding("conditional_completion.public_report_sha256")
def boundary_rows(initial):
    c.need(set(initial)=={"B0","B1","B2"},"boundary saved initial methods")
    out={}
    for m,rows in initial.items():
        out[m]=[]
        for row in rows:
            c.need(row["prediction_supported"] is False and row["success"] is False,"boundary initial must already be unsupported failure")
            # Preserve every saved eligibility field/determinator and unknown label.
            out[m].append(dict(row,reason_codes=list(dict.fromkeys(list(row["reason_codes"])+["interrupted_unknown_boundary"]))))
    return out
def read_saved(root,inv,rel):
    item=inv["output_sha256"].get(rel);c.need(item is not None,"saved inventory missing:"+rel)
    p=Path(root)/rel;c.need(c.sha(p)==item["sha256"],"saved file SHA:"+rel);return json.loads(p.read_text())
def collect_rows(queue,parts,original_root,original_inventory,suffix_root,suffix_inventory,reporter,ledger,expected_plan_sha=None):
    c.need(parts["prefix"]+parts["boundary"]+parts["suffix"]==queue,"whole fixed queue partition")
    allbundles={};origins={}
    for iid in queue:
        boundary=iid in parts["boundary"]
        root,inv=(original_root,original_inventory) if iid in parts["prefix"] or boundary else (suffix_root,suffix_inventory)
        initial=read_saved(root,inv,"evaluation/"+iid+".not_started.json")
        if boundary:
            rows=boundary_rows(initial)
            bundles={m:dict(rows=v,metadata=dict(input_id=iid,roles=["native_test"]),pipeline_status=None) for m,v in rows.items()}
        else:
            bundles=read_saved(root,inv,"evaluation/"+iid+".json")
            raw=read_saved(root,inv,"raw/"+iid+".json")
            c.need(raw["input_id"]==iid and (expected_plan_sha is None or raw["plan_sha256"]==expected_plan_sha),"saved raw identity/plan")
        c.need(set(bundles)==set(initial)=={"B0","B1","B2"},"full saved method domain")
        for method,bundle in bundles.items():
            c.need(bundle["metadata"]["input_id"]==iid and bundle["metadata"]["roles"]==["native_test"],"saved test scope")
            c.need(reporter.inventory_domain(bundle["rows"])==reporter.inventory_domain(initial[method]),"fixed eligibility changed")
            for v in bundle["rows"]:
                context=dict(v["context"])
                want=dict(baseline=method,truth_basis="source_relative_current_serialization",nucleus="13C",task_semantics="derived_serialized_value_bin",target_level="parent",target_semantics="set")
                c.need(all(context[k]==val for k,val in want.items()),"frozen semantic axis")
                c.need(context["record_id"]==ledger[iid]["record_id"] and context["connectivity_id"]==ledger[iid]["connectivity_sha256"],"saved source identity")
        allbundles[iid]=bundles;origins[iid]="boundary_saved_initial_unknown" if boundary else "original_completed" if iid in parts["prefix"] else "completion_completed"
    return allbundles,origins

def frozen_off_application(row,bundle,axes):
    """保存bundle没有reference/证书；仅重建冻结OFF元数据，不推断margin或target不变性。"""
    context=dict(row.context)
    semantic=dict(method=context["baseline"],nucleus=context["nucleus"],truth_basis=context["truth_basis"],task_semantics=context["task_semantics"],target_level=context["target_level"],target_semantics=context["target_semantics"],endpoint="per_peak_compatibility",sampling_unit="observation")
    off=dict(observation_id=row.observation_id,baseline=context["baseline"],publication_enabled=False,status="off_no_matching_reviewed_Cval_artifact",threshold=None,refit=False,reconstruction="saved_row_pipeline_availability_and_exact_frozen_off_artifact_only")
    matching=[a for a in axes if all(a.get("axis",{}).get(k)==v for k,v in semantic.items())]
    if bundle.get("pipeline_status") is None or len(matching)!=1:return off
    artifact=matching[0]
    c.need(artifact["status"].startswith("off_") and artifact.get("published_ids")==[],"reconstruction only exact frozen off")
    return dict(off,status=artifact["status"],stored_status=artifact["status"],stored_threshold=artifact.get("threshold"),frozen_threshold_available=False,frozen_threshold_axis=artifact["axis"],test_semantic_axis=semantic)

def run(plan_item,release_item):
    plan=c.load(plan_item);release=c.load(release_item)
    c.need(plan["schema"]=="TEST_STAGE_B_completion_final_report_plan_v1" and release["schema"]=="TEST_STAGE_B_completion_report_once_release_v1","completion report explicit schemas")
    c.need(release["execution_authorized"] is True and release["plan_sha256"]==plan_item["sha256"] and release["entrypoint_sha256"]==c.sha(__file__),"exact report release")
    review=c.load(release["independent_review"])
    for key,filename in (("completion","TEST_STAGE_B_completion.py"),("completion_supervisor","TEST_STAGE_B_completion_supervisor.py"),("completion_report","TEST_STAGE_B_completion_report.py")):
        c.need(review["source_sha256"][key]==c.sha(Path(__file__).with_name(filename)),"complete reviewed control closure")
    c.need(str(review["decision"]).startswith("PASS") and review["source_sha256"]["completion_report"]==c.sha(__file__),"report source PASS")
    segment=c.load(plan["completion_plan"]);original=c.load(segment["original_scoring_plan"]);suite=c.load(segment["original_suite"])
    original_terminal=c.load(segment["original_terminal_receipt"]);actual=c.load(plan["completion_actual_receipt"])
    c.need(original_terminal.get("actual_outer_exit")!=0 and original_terminal.get("leader_reaped") is True and original_terminal.get("owned_survivors")==[],"original nonzero closed retained")
    c.need(actual.get("actual_inner_exit")==actual.get("actual_outer_exit")==0 and actual.get("leader_reaped") is True and actual.get("owned_survivors")==[],"completion actual closed0")
    c.need(actual.get("input_sha256",{}).get(plan["completion_plan"]["path"])==plan["completion_plan"]["sha256"],"actual completion plan binding")
    c.need(int(os.environ["TEST_STAGE_B_COMPLETION_SUFFIX_N"])==len(segment["ordered_suffix_ids"]),"report fixed suffix N")
    original_inv=c.load(segment["original_partial_inventory"]);suffix_inv=c.load(plan["completion_output_inventory"])
    input_seal=c.load(segment["original_input_inventory"])
    c.need(all(c.sha(p)==h for p,h in input_seal["input_sha256"].items()),"sealed original input/source bytes still frozen")
    root=Path(original["output_directory"]);suffix=Path(segment["output_directory"])
    c.need(c.inventory(root)==original_inv["output_sha256"] and c.inventory(suffix)==suffix_inv["output_sha256"],"both source inventories exact")
    events=json.loads((root/"record_completion_ledger.json").read_text()) if (root/"record_completion_ledger.json").exists() else []
    completed_ids=[v["input_id"] for v in events]
    parts=c.partition(original["input_ids"],completed_ids,c.touched_ids(root),c.recoverable_next(root,original["input_ids"],completed_ids))
    c.need(parts["suffix"]==segment["ordered_suffix_ids"] and parts["boundary"]==segment["interrupted_unknown_ids"],"sealed suffix unchanged")
    receipt=read_saved(suffix,suffix_inv,"completion_segment_receipt.json")
    c.need(all(receipt["completion_plan"][k]==plan["completion_plan"][k] for k in ("path","sha256")),"segment output exact plan")
    sm=read_saved(suffix,suffix_inv,"manifest.json")
    c.need(sm["status"]=="FROZEN_ASSIGNMENT_EXECUTION_COMPLETED" and [v["input_id"] for v in sm["record_ledger"]]==parts["suffix"],"completion full suffix only")
    reporter_path=suite["implementations"]["report_adaptor"]["path"];c.need(c.sha(reporter_path)==REPORT_SHA,"cdf frozen report/P1 source")
    sys.path.insert(0,str(Path(reporter_path).parent));sys.path.insert(0,original["repo"])
    reporter=c.module(reporter_path,"completion_frozen_report");contract=reporter.contract
    # Reuses original report phase key: ordinary and segmented report cannot both run.
    bound_suite,a=contract.bind_suite(segment["original_suite"],plan["original_owner_suite_release"])
    c.need(bound_suite==suite and a["queue"]==original["input_ids"],"original actual A queue/suite")
    claim=contract.claim_phase(segment["original_suite"],plan["original_owner_suite_release"],"report")
    ledger=contract.component.unique(list(contract.component.rows(contract.bound(original["inputs"]["ledger"]))))
    bundles,origins=collect_rows(a["queue"],parts,root,original_inv,suffix,suffix_inv,reporter,ledger,segment["original_scoring_plan"]["sha256"])
    from nmr_assignment.metrics import EvaluationRow
    caller_path=suite["implementations"]["locked_caller"]["path"];c.need(c.sha(caller_path)==c.CALLER_SHA,"5485 frozen apply")
    caller=c.module(caller_path,"completion_report_frozen_caller")
    frozen=contract.load(suite["Cval_frozen_calibration"]);axes=frozen if isinstance(frozen,list) else frozen["axes"]
    caller.bind_Cval_rule_contract(original,axes,a)
    rows=[];applied=[];expected={};schema={f.name for f in fields(EvaluationRow)}
    for iid in a["queue"]:
        for method,bundle in bundles[iid].items():
            for value in bundle["rows"]:
                c.need(set(value)==schema,"saved EvaluationRow schema")
                row=EvaluationRow(**{k:reporter.freeze(v) for k,v in value.items()});rows.append(row)
                if row.metric=="compatible_observation":
                    context=dict(row.context);semantic=dict(method=method,nucleus=context["nucleus"],truth_basis=context["truth_basis"],task_semantics=context["task_semantics"],target_level=context["target_level"],target_semantics=context["target_semantics"],endpoint="per_peak_compatibility",sampling_unit="observation")
                    key=(iid,method,row.observation_id);c.need(key not in expected,"duplicate compatible domain")
                    expected[key]=dict(semantic_axis=semantic,pipeline_available=bundle.get("pipeline_status") is not None)
                    if iid not in parts["suffix"]:applied.append(dict(input_id=iid,**frozen_off_application(row,bundle,axes)))
    # Suffix application bytes are an existing output: reuse without reapply.
    suffix_applied=read_saved(suffix,suffix_inv,"frozen_Cval_threshold_application.json")
    c.need(all(v["input_id"] in parts["suffix"] for v in suffix_applied),"suffix application domain")
    applied.extend(suffix_applied)
    validation=reporter.validate_threshold_applications(applied,expected,frozen)
    metrics=reporter.estimate_native_test(rows,reporter.estimator(suite["implementations"]["estimators"]))
    out=Path(plan["output_directory"]);c.need(not out.exists(),"new final report output");out.mkdir(parents=True)
    result=dict(schema="TEST_STAGE_B_segmented_native_test_report_v1",status="FROZEN_SEGMENTED_TEST_REPORT_PENDING_ACTUAL_APPLICATION_AUDIT",source_relative_only=True,native_test=metrics,original_execution=dict(receipt=segment["original_terminal_receipt"],outer_exit=original_terminal["actual_outer_exit"],unchanged=True),completion_execution=dict(receipt=plan["completion_actual_receipt"],outer_exit=actual["actual_outer_exit"],segment_index=2),coverage=dict(original_C_identity_denominator=3637,H_original_identity_denominator=1371,H_assignment_status="unavailable_no_model_no_assignment_metrics",public_scoring_queue=len(a["queue"]),public_unavailable_unknown=3637-len(a["queue"]),partition=parts,origin_counts=dict(Counter(origins.values()))),highconfidence=dict(published=0,application_validation=validation,stored_statuses_preserved=True,Cval_artifact_sha256=suite["Cval_frozen_calibration"]["sha256"],reconstructed_fixed_off_metadata_from_saved_rows=True,reconstructed_margins=False,reconstructed_target_invariance=False,test_fit_calls=0),original_score_rewritten=False,new_models=0,new_solves=0,new_gold_evaluations=0,new_mapping_search=0,no_retry=True,report_claim=claim)
    c.need(c.inventory(root)==original_inv["output_sha256"] and c.inventory(suffix)==suffix_inv["output_sha256"],"postread saved source hashes")
    c.write(out/"frozen_Cval_threshold_application.json",applied);c.write(out/"report.json",result)
    c.write(out/"report_receipt.json",dict(schema="TEST_STAGE_B_completion_final_report_receipt_v1",report_sha256=c.sha(out/"report.json"),plan=plan_item,original_terminal=segment["original_terminal_receipt"],completion_actual=plan["completion_actual_receipt"],both_original_and_completion_inventories_preserved=True,source_suite_sha256=segment["original_suite"]["sha256"]))
def main():
    p=argparse.ArgumentParser();p.add_argument("--plan");p.add_argument("--plan-sha256");p.add_argument("--release");p.add_argument("--release-sha256");p.add_argument("--execute",action="store_true");a=p.parse_args()
    if not a.execute:print(json.dumps(dict(schema="TEST_STAGE_B_segmented_report_interface_v1",execution_authorized=False,boundary_missing_initial="BLOCKED",estimators="same9d once",P1="exact cdf guard reused")));return
    c.need(os.environ.get("TEST_STAGE_B_COMPLETION_OUTER_PID")==str(os.getppid()),"supervised report only")
    run(dict(path=a.plan,sha256=a.plan_sha256),dict(path=a.release,sha256=a.release_sha256))

# 每个helper入口核相同显式runtime与公开四源闭包，防绕过main直接访问外部制品。
def _public_guard(function):
    import functools
    @functools.wraps(function)
    def call(*args,**kwargs):
        authorize()
        import hashlib
        sources=binding("conditional_completion.public_source_sha256")
        if set(sources)!={'TEST_STAGE_B_completion_tests.py', 'TEST_STAGE_B_completion_supervisor.py', 'TEST_STAGE_B_completion.py', 'TEST_STAGE_B_completion_report.py'}:raise ValueError("conditional complete four-source binding required")
        for name,want in sources.items():
            path=Path(__file__).with_name(name)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=want:raise ValueError("conditional public source binding mismatch:"+name)
        return function(*args,**kwargs)
    return call
for _name in ('boundary_rows', 'read_saved', 'collect_rows', 'frozen_off_application', 'run', 'main'):globals()[_name]=_public_guard(globals()[_name])
if __name__=="__main__":main()
