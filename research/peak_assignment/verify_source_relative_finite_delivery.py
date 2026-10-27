"""功能概述：独立核验有限源相对交付，不替代原强目标谓词。
validate绑定d280/7889与原强谓词SHA，保留overall/trusted实验/H固定test完成False。
verify_test区分H1371不可评/0次固定test模型评分，与C3637一次实际预测/包装/评分/报告；
phase核receipt、persistent once claim、真实输出inventory/hash和应用独审。预测真实1/1/1
不得洗白，实际H/C加载及3636/3635/1/0计数取SHA与inventory绑定builder receipt；expected声明不作证据，score/report另核0。verify_coverage逐域保留未完成目标；默认缺件PENDING。
只读控制JSON/交付文件，不读谱值或JSONL、不训练/运行模型/评价/阈值/Git、不写完成状态。分段报告显式核实际plan/release输入map、suffix inventory、输出目录和原input seal引用闭包。
verify_segmented调用verify_original_terminal/verify_partition核原终态与保守分区；source_gate与sealed_inventory/sealed_primary核源码独审、实际封存输出及应用审计；N0无已审native报告路径时阻断，不发明段。邻接schema说明封装字段，合成tests验证假Hpass/换身份/假指标/退出洗白/缺实际输出等。
"""
import hashlib
import json
from pathlib import Path
from portable_runtime import workspace, binding
ROOT=workspace()
STATUS="SOURCE_RELATIVE_DELIVERY_COMPLETE_TRUSTED_GOLD_UNAVAILABLE"
AUTH_SHA="7889f813ced7fbe525ed7c3bd1a787a62c31d34008b53813492ddc1cae5253bb"
DECISION_SHA="d28039f0d6ad7eb7c284587821ddcf2b30b9ad67f091ceebe642ead1d04c18a4"
STRONG_SHA="726c9b52145085fdca441f32043a575444d8503b8e5a106cd82e1ce72e85c62d"
PREDICTION_RECEIPT_SHA="f848167644298829bfa021ef02beba83900d3bf28bf764b630ba88cebab7b0d0"
IDENTITY_SHA="43f1dfc71029d987be1e5b85d49aaacb7daa0056cad8d8269f27cffe0117e3af"
REQUIRED=("source_relative_completion.json","source_relative_benchmark_manifest.json","frozen_definition.json","baseline_comparison.json","confidence_calibration.json","test_evaluation.json","stratified_metrics.json","code_publication.json","source_relative_final_independent_review.json","report.md","demonstrations/index.html")
STATES={"supported","off","unknown","unsupported","unavailable"}
UNFINISHED={"chemical_quotient_top3","natural_overlap","strict_full_spectrum","systematic_stress"}
SUPPORTED={"per_peak_exact","whole_reported_input","micro","macro","conditional","paired","stratified"}
def need(ok,message):
    if not ok:raise ValueError(message)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def load(path):
    need(Path(path).suffix.lower()!=".jsonl","control_JSON_only_no_JSONL_values")
    return json.loads(Path(path).read_text())
def bound(item):
    p=Path(item["path"]);need(p.is_file() and digest(p)==item["sha256"],"evidence_SHA:"+str(p));return p
def value_at(obj,path):
    need(isinstance(path,list),"selector_path")
    for key in path:obj=obj[key]
    return obj
def exact_int(v,n,message):need(type(v) is int and v==n,message)
def review(item,subject):
    doc=load(bound(item["artifact"]));decision=doc.get("decision",doc.get("status",""))
    need(isinstance(decision,str) and decision.startswith("PASS"),"application_review_PASS")
    need(value_at(doc,item["subject_sha256_path"])==subject,"application_review_subject")
    return doc
def phase(item,name,exits,suite,release):
    ri=item["actual_receipt"];r=load(bound(ri));need(r["phase"]==name,"actual_phase")
    for k,n in zip(("actual_inner_exit","actual_worker_exit","actual_outer_exit"),exits):exact_int(r[k],n,"actual_exit:"+name+":"+k)
    need(r["input_hashes_unchanged"] is True and r["leader_reaped"] is True and r["owned_survivors"]==[],"phase_integrity_cleanup")
    # Frozen expected_* fields may be None; they are declarations, never actual proof.
    inv=load(bound(r["child_output_inventory"]))
    exact_int(inv["child_exit"],exits[0],"inventory_child_exit");exact_int(inv["outer_exit"],exits[2],"inventory_outer_exit")
    need(inv["once_claim"]==r["once_claim"],"inventory_once_binding")
    ci=r["once_claim"];claim=load(bound(ci))
    need(claim["schema"]=="TEST_STAGE_B_persistent_once_claim_v1" and claim["phase"]==name and claim["scope"]=="execution" and claim["retained_on_all_failures"] is True,"persistent_once_claim")
    need(claim["suite_manifest_sha256"]==suite["sha256"] and claim["owner_release_sha256"]==release["sha256"],"once_suite_release")
    oi=item["primary_output"];op=bound(oi);entry=inv["output_sha256"][item["primary_output_inventory_key"]]
    need((entry["sha256"] if isinstance(entry,dict) else entry)==oi["sha256"],"actual_output_inventory_binding")
    if name=="prediction":
        builder_item=item["prediction_receipt"]
        builder=load(bound(builder_item))
        need(builder_item["sha256"]==PREDICTION_RECEIPT_SHA,"actual_prediction_receipt_SHA")
        recorded=inv["output_sha256"][item["prediction_receipt_inventory_key"]]
        need((recorded["sha256"] if isinstance(recorded,dict) else recorded)==builder_item["sha256"],"prediction_receipt_inventory_binding")
        loads=builder["model_loads"]
        need(isinstance(loads,dict) and set(loads)<={"1H","13C"},"actual_model_loads_domain")
        exact_int(loads.get("1H",0),0,"actual_fixed_H_model_loads")
        exact_int(loads["13C"],1,"actual_fixed_C_model_loads")
        for key,expected in (("input_count",3636),("input_success",3635),("input_failed",1),("input_not_started",0)):
            exact_int(builder[key],expected,"actual_prediction_count:"+key)
    review(item["application_review"],ri["sha256"])
    return load(op),ci["sha256"]
def verify_test_once(t):
    need(t["schema"]=="source_relative_fixed_test_H_unavailable_C_complete_v1","finite_test_schema")
    need(t["scope_acceptance_sha256"]==AUTH_SHA,"scope_acceptance_SHA")
    need("fixed_test_passes" not in t,"generic_H_test_pass_forbidden")
    original=load(bound(t["fixed_identity_manifest"]))["identities"]
    need(t["fixed_identity_manifest"]["sha256"]==IDENTITY_SHA,"original_fixed_identity_SHA")
    h=[r for r in original if r["nucleus"]=="1H"];c=[r for r in original if r["nucleus"]=="13C"]
    need(len(h)==1371 and len(c)==3637,"original_identity_counts")
    H=t["H_fixed_test"];C=t["C_native_test"]
    need(H["identity_order_sha256"]==canonical(h) and C["identity_order_sha256"]==canonical(c),"original_identity_order_SHA")
    need(H["retained_ids"]==[r["query_id"] for r in h],"H_retained_original_order")
    need(C["retained_ids"]==[r["input_id"] for r in c],"C_retained_original_order")
    need(H["historical_identity_counts"]==dict(observed=1000,frequency_crop=200,peak_dropout=171),"H_variants")
    exact_int(H["original_identity_count"],1371,"H_denominator")
    exact_int(H["H_fixed_test_scoring_runs"],0,"no_H_fixed_test_score");exact_int(H["H_fixed_test_model_calls"],0,"no_H_fixed_test_models")
    need(H["H_fixed_test_assignment_complete"] is False and H["assignment_metrics"] is None and H["status"]=="unavailable" and H["replacement_observations"] is False,"H_unavailable_not_pass")
    a=load(bound(H["A_actual"]))
    need(a["H_asset_mode"]=="unavailable" and a["original_H_fixed_test_completion"] is False and a["H_fixed_test_assignment_metrics"]=="unavailable","A_actual_H_unavailable")
    for k in ("models","scores"):exact_int(a[k],0,"A_only_no_model_score:"+k)
    review(H["A_application_review"],H["A_actual"]["sha256"])
    need(H["unevaluable_retained_not_replaced"] is True,"H_unknown_retention")
    for k,n in (("original_identity_count",3637),("scorequeue",3636),("source_unknown",1),("prediction_available",3635),("prediction_failed_retained",1)):exact_int(C[k],n,"C_domain:"+k)
    need(C["unevaluable_retained_not_replaced"] is True and C["cache_failed_eligible_retained"] is True,"C_failure_denominators")
    for k in ("actual_prediction_runs","actual_package_runs","actual_scoring_runs","actual_report_runs"):exact_int(C[k],1,"once_C:"+k)
    si=C["suite_manifest"];suite=load(bound(si));ri=C["owner_release"];release=load(bound(ri))
    need(suite["execution_authorized"] is True and release["decision"]=="ALLOW_ONCE_C_FIXED_TEST_STAGE_B" and release["suite_manifest_sha256"]==si["sha256"] and release["no_retry"] is True,"actual_suite_once_release")
    need(C["freeze_before_evaluation_verified"] is True,"freeze_before_evaluation")
    phases=C["phases"];need(set(phases)=={"prediction","package","score","report"},"four_actual_C_phases")
    outputs={};claims=[]
    for n,exits in (("prediction",(1,1,1)),("package",(0,0,0)),("score",(0,0,0)),("report",(0,0,0))):
        outputs[n],claim=phase(phases[n],n,exits,si,ri);claims.append(claim)
    need(len(set(claims))==4,"distinct_once_claims")
    p=outputs["package"]
    need(p["original_identity_denominator"]==3637 and p["scorequeue"]==3636 and p["public_unavailable"]==1 and p["inputs"]["predictions"]["rows"]==3635,"package_actual_counts")
    queue=C["scorequeue_ids"];need(len(queue)==len(set(queue))==3636 and set(queue)<set(C["retained_ids"]),"C_queue_identity_subset")
    need(queue==[iid for iid in C["retained_ids"] if iid in set(queue)],"C_queue_original_order")
    s=outputs["score"];need(s["status"]=="FROZEN_ASSIGNMENT_EXECUTION_COMPLETED" and s["input_records"]==3636 and s["original_identity_denominator"]==3637,"actual_scoring_manifest_complete")
    need([r["input_id"] for r in s["record_ledger"]]==queue,"actual_score_order")
    report=outputs["report"];v=report["coverage"]
    need(report["source_relative_only"] is True and report["schema"]=="TEST_STAGE_B_native_test_report_v1","actual_native_test_report")
    need(v["original_C_identity_denominator"]==3637 and v["public_scoring_queue"]==3636 and v["public_unavailable_unknown"]==1 and v["H_original_identity_denominator"]==1371 and v["H_assignment_status"]=="unavailable_no_model_no_assignment_metrics","actual_report_fixed_coverage")
    exact_int(report["highconfidence"]["published"],0,"frozen_publication_off");exact_int(report["highconfidence"]["test_fit_calls"],0,"no_test_refit")
    need(report["no_test_threshold_reselection"] is True,"frozen_thresholds")
    return outputs
def verify_coverage(m):
    need("required_metric_families_complete" not in m,"blanket_all_metrics_complete_forbidden")
    domains=m["metric_domain_coverage"]
    need(isinstance(domains,dict) and SUPPORTED|UNFINISHED|{"high_confidence","H_fixed_test_assignment"}<=set(domains),"metric_domain_inventory")
    for name,item in domains.items():
        need(item["status"] in STATES and item["evidence"] and item["scope"],"metric_domain_status:"+name)
        for e in item["evidence"]:bound(e)
        if name in SUPPORTED:need(item["status"]=="supported","supported_metric_missing:"+name)
    need(domains["high_confidence"]["status"]=="off" and domains["H_fixed_test_assignment"]["status"]=="unavailable","unavailable_off_domains")
    for name in UNFINISHED:need(domains[name]["status"] in {"unsupported","unknown","unavailable"},"uncompleted_metric_misrepresented:"+name)
    need(set(m["original_goal_unfinished_domains"])>=UNFINISHED|{"trusted_experimental","H_fixed_test_assignment"},"original_unfinished_scope")

SEGMENTED_SCHEMA="source_relative_segmented_H_unavailable_C_complete_v1"
SEGMENT_AUTH_SHA="7268574cf03549dc8aaf8c02adc3e0388946d8b12cbccf867838f963d2a1433e"
ORIGINAL_BINDINGS={"suite":"aed363b9438186765745f4f568f71ba183904dc4b3f2c60ccef8c7831f79baf7","phase":"7e12a1fc4ced86c6749b8937eb2903b2cb09aa6ef318576a15eab210068d96b7","owner":"7c1cf21c46fb852b7e3cb430bab6f52b4e6babe211372ac223cb14b573150d82","scoring_plan":"f5270fc73c400d9a112273c02ef6ae5c1f209d8614886c700a0388681f69f74e"}
SEGMENT_SOURCE_SHAS={"completion":"fe3a0a6c350016cce0ad3d5cbb74287caf42563c0b718b1e1f6a1a9269777c88","completion_supervisor":"f8c84850c4f250c319d5bdc948012da1f81aa4796c040c15c90b357b8a989a13","completion_report":"542c2808791410d6ecbeaa0507ff3507125fb98ee83be883fdc968a684dc69d1","tests":"0df4d1779335e98ff61fb97afa93577fcbebd32c93e410ba37f8e57e57d449e1"}
FROZEN_REPORT_SHAS={"estimators":"9d002586d9b47db528ef50ae8a82e4eeb44e2721ef9f5ee7cb76e2661b561084","report_P1":"cdf69f2238bcb9bb5ba3b367afb4d8b2a5d5ec87129d14851134c5fc61b6cd47"}

def same_ref(a,b):
    return a["path"]==b["path"] and a["sha256"]==b["sha256"]

def sealed_inventory(item,root):
    """Hash complete saved directory bytes without decoding scientific rows."""
    root=Path(root);doc=load(bound(item));need(root.is_dir(),"sealed_directory_missing")
    actual={str(p.relative_to(root)):digest(p) for p in root.rglob("*") if p.is_file()}
    declared={p:(e["sha256"] if isinstance(e,dict) else e) for p,e in doc["output_sha256"].items()}
    need(actual==declared,"sealed_complete_file_inventory")
    return declared

def sealed_primary(item):
    receipt=load(bound(item["actual_receipt"]))
    need(receipt["schema"]=="TEST_STAGE_B_phase_actual_v1" and receipt["status"]=="CHILD_COMPLETED_PENDING_ARTIFACT_AUDIT"
         and receipt["phase"]==item["phase"],"segment_execution_phase")
    from math import isfinite
    wall=receipt["elapsed_seconds"];rss=receipt["peak_tree_RSS_bytes"];budget=receipt["budget"]
    need(type(wall) in (int,float) and isfinite(wall) and 0<=wall<=budget["total_wall_seconds"]+budget["cleanup_seconds"]
         and type(rss) is int and 0<=rss<=budget["RSS_bytes"],"actual_segment_resource_bounds")
    for k in ("actual_inner_exit","actual_outer_exit"):exact_int(receipt[k],0,"segment_actual_exit:"+k)
    if "actual_worker_exit" in receipt:exact_int(receipt["actual_worker_exit"],0,"segment_worker_exit")
    need(receipt["leader_reaped"] is True and receipt["owned_survivors"]==[]
         and receipt["input_hashes_unchanged"] is True,"segment_cleanup_input_integrity")
    inv=sealed_inventory(item["output_inventory"],item["output_root"])
    output=item["primary_output"];bound(output)
    need(inv[item["primary_output_inventory_key"]]==output["sha256"],"segmented_actual_output_inventory")
    audit=review(item["application_review"],item["actual_receipt"]["sha256"])
    need(value_at(audit,item["application_review"]["output_inventory_sha256_path"])==item["output_inventory"]["sha256"]
         and value_at(audit,item["application_review"]["primary_output_sha256_path"])==output["sha256"],"actual_application_inventory_output_binding")
    return receipt,load(bound(output))

def source_gate(item):
    need(set(item["sources"])==set(SEGMENT_SOURCE_SHAS),"segment_source_domain")
    for k,d in SEGMENT_SOURCE_SHAS.items():
        bound(item["sources"][k]);need(item["sources"][k]["sha256"]==d,"frozen_segment_source:"+k)
    audit=load(bound(item["independent_source_review"]))
    need(str(audit["decision"]).startswith("PASS") and audit["source_sha256"]==SEGMENT_SOURCE_SHAS,"segment_source_independent_PASS")

def verify_original_terminal(C):
    original=C["original_score"];r=load(bound(original["actual_receipt"]))
    need(r["schema"]=="TEST_STAGE_B_phase_actual_v1" and r["phase"]=="score" and r["status"]=="FAILED_OR_PARTIAL_RETAINED_NO_RETRY","original_failed_score_terminal")
    from datetime import datetime
    start=datetime.fromisoformat(r["started_UTC"]);finish=datetime.fromisoformat(r["finished_UTC"])
    need(start.tzinfo is not None and finish.tzinfo is not None and finish>=start,"original_terminal_finished")
    need(r["actual_inner_exit"] is None or type(r["actual_inner_exit"]) is int,"original_nullable_inner_exit")
    need(type(r["actual_worker_exit"]) is int and type(r["actual_outer_exit"]) is int and r["actual_outer_exit"]!=0,"original_actual_nonzero_outer")
    need(r["termination_reason"] in {"wall_limit","RSS_limit","leader_exit","supervisor_exception"}
         and r["leader_reaped"] is True and r["owned_survivors"]==[],"original_terminal_cleanup")
    request=r["request_items"]
    for k in ("suite","phase","owner"):
        key="release" if k=="owner" else k
        bound(request[key]);need(request[key]["sha256"]==ORIGINAL_BINDINGS[k],"original_exact_request:"+k)
    need(same_ref(request["suite"],C["suite_manifest"]) and same_ref(request["release"],C["owner_release"]),"original_C_suite_owner")
    suite=load(bound(C["suite_manifest"]));owner=load(bound(C["owner_release"]));phase_doc=load(bound(request["phase"]))
    config=load(bound(phase_doc["config"]));plan_item=original["scoring_plan"];plan=load(bound(plan_item))
    need(r["budget"]==phase_doc["budget"] and phase_doc["budget"]["total_wall_seconds"]==7200,"original_fixed7200_budget")
    need(plan_item["sha256"]==ORIGINAL_BINDINGS["scoring_plan"],"original_exact_scoring_plan")
    need(phase_doc["phase"]=="score" and phase_doc["schema"]=="TEST_STAGE_B_execution_phase_v1"
         and phase_doc["suite_manifest_sha256"]==C["suite_manifest"]["sha256"]
         and phase_doc["budget"]==suite["budget"]["score"],"original_phase_semantics")
    need(config["ordered_input_ids"]==C["scorequeue_ids"]==plan["input_ids"]
         and config["original_C_identity_count"]==3637
         and config["output_directory"]==plan["output_directory"]
         and same_ref(config["delegate_plan"],plan_item),"original_phase_config_plan")
    expected={x["path"]:x["sha256"] for x in (request["suite"],request["release"],request["phase"],phase_doc["config"])}
    expected.update({x["path"]:x["sha256"] for x in suite["implementations"].values()})
    expected.update({x["path"]:x["sha256"] for x in config.values() if isinstance(x,dict) and "path" in x and "sha256" in x})
    need(r["phase_input_sha256"]==expected,"original_phase_input_closure")
    for p,h in expected.items():need(digest(p)==h,"original_phase_input_SHA")
    ci=original["claim"];claim=load(bound(ci))
    key=hashlib.sha256((owner["release_id"]+"\0score\0execution").encode()).hexdigest()
    need(ci["path"]==str(Path(suite["once_claim_root"])/(key+".json")) and same_ref(ci,r["once_claim"]),"original_canonical_claim")
    need(claim["schema"]=="TEST_STAGE_B_persistent_once_claim_v1" and claim["phase"]=="score" and claim["scope"]=="execution"
         and claim["suite_manifest_sha256"]==C["suite_manifest"]["sha256"]
         and claim["owner_release_sha256"]==C["owner_release"]["sha256"]
         and claim["release_id"]==owner["release_id"] and claim["claim_PID"]==r["child_PID"],"original_claim_owner_phase")
    inputs=load(bound(original["input_inventory"]))["input_sha256"]
    declared={x["path"]:x["sha256"] for x in list(plan["inputs"].values())+plan["implementations"]}
    need(inputs==declared,"original_full_input_seal")
    for p,h in inputs.items():need(digest(p)==h,"original_input_SHA")
    inv=sealed_inventory(original["partial_inventory"],original["output_root"])
    need(plan["output_directory"]==original["output_root"],"original_sealed_root")
    audit=review(original["application_review"],original["actual_receipt"]["sha256"])
    need(value_at(audit,original["application_review"]["partial_inventory_sha256_path"])==original["partial_inventory"]["sha256"]
         and value_at(audit,original["application_review"]["input_inventory_sha256_path"])==original["input_inventory"]["sha256"],"original_application_seals_binding")
    return r,plan,inv,suite,owner

def verify_partition(C,plan,inv):
    original=C["original_score"];p_item=C["partition"];parts=load(bound(p_item));root=Path(original["output_root"])
    queue=C["scorequeue_ids"]
    completed=load(root/"record_completion_ledger.json") if "record_completion_ledger.json" in inv else []
    completed=[r["input_id"] for r in completed]
    need(completed==queue[:len(completed)],"original_completed_prefix")
    recovered=parts["recovered_complete_ids"]
    need(not recovered or recovered==queue[len(completed):len(completed)+1],"only_immediate_recovery")
    prefix=completed+recovered
    boundary=[] if recovered or len(prefix)==len(queue) else queue[len(prefix):len(prefix)+1]
    suffix=queue[len(prefix)+len(boundary):]
    need(parts["prefix"]==prefix and parts["boundary"]==boundary and parts["suffix"]==suffix,"conservative_exact_partition")
    need(parts["original_queue_sha256"]==canonical(queue),"partition_queue_SHA")
    touched=set()
    for rel in inv:
        path=Path(rel)
        if path.parts[0] not in {"raw","evaluation"}:continue
        name=path.name
        if name.endswith(".tmp"):name=name[:-4]
        for ending in (".not_started.json",".payload.json",".json"):
            if name.endswith(ending):
                touched.add(name[:-len(ending)]);break
    need(touched<=set(prefix+boundary),"started_or_tmp_outside_boundary")
    need(set(parts["touched_ids"])==touched,"partition_touched_evidence")
    for iid in prefix:
        for rel in ("raw/"+iid+".json","evaluation/"+iid+".json","evaluation/"+iid+".not_started.json"):
            need(rel in inv,"prefix_complete_persisted_files")
    for iid in boundary:need("evaluation/"+iid+".not_started.json" in inv,"boundary_saved_denominator_required")
    # An independent actual audit must establish saved initial/final eligibility; no reevaluation here.
    audit=review(C["partition_application_review"],p_item["sha256"])
    need(audit["saved_eligibility_domains_unchanged"] is True and audit["no_started_record_retried"] is True
         and value_at(audit,C["partition_application_review"]["partial_inventory_sha256_path"])==original["partial_inventory"]["sha256"],"partition_actual_eligibility_audit")
    return parts

def verify_segmented(t):
    need(t["scope_acceptance_sha256"]==AUTH_SHA and "fixed_test_passes" not in t,"segmented_scope")
    auth=t["conditional_scope_authorization"];bound(auth);need(auth["sha256"]==SEGMENT_AUTH_SHA,"conditional_scope_bytes")
    original=load(bound(t["fixed_identity_manifest"]))["identities"]
    need(t["fixed_identity_manifest"]["sha256"]==IDENTITY_SHA,"original_fixed_identity_SHA")
    h=[r for r in original if r["nucleus"]=="1H"];c=[r for r in original if r["nucleus"]=="13C"]
    H=t["H_fixed_test"];C=t["C_native_test"]
    need(len(h)==1371 and len(c)==3637 and H["retained_ids"]==[r["query_id"] for r in h] and C["retained_ids"]==[r["input_id"] for r in c],"segmented_original_identity_order")
    need(H["identity_order_sha256"]==canonical(h) and C["identity_order_sha256"]==canonical(c),"segmented_identity_SHA")
    need(H["historical_identity_counts"]==dict(observed=1000,frequency_crop=200,peak_dropout=171) and H["original_identity_count"]==1371,"segmented_H_variants")
    for k in ("H_fixed_test_scoring_runs","H_fixed_test_model_calls"):exact_int(H[k],0,"segmented_H_no_execution")
    need(H["H_fixed_test_assignment_complete"] is False and H["assignment_metrics"] is None and H["replacement_observations"] is False
         and H["status"]=="unavailable" and H["unevaluable_retained_not_replaced"] is True,"segmented_H_unavailable")
    a=load(bound(H["A_actual"]));review(H["A_application_review"],H["A_actual"]["sha256"])
    need(a["H_asset_mode"]=="unavailable" and a["original_H_fixed_test_completion"] is False and a["H_fixed_test_assignment_metrics"]=="unavailable","A_actual_H_unavailable")
    for k in ("models","scores"):exact_int(a[k],0,"A_only_no_models_scores")
    for k,n in (("original_identity_count",3637),("scorequeue",3636),("source_unknown",1),("prediction_available",3635),("prediction_failed_retained",1)):exact_int(C[k],n,"segmented_C_domain")
    queue=C["scorequeue_ids"];need(len(queue)==len(set(queue))==3636 and set(queue)<set(C["retained_ids"])
        and queue==[i for i in C["retained_ids"] if i in set(queue)],"segmented_fixed_queue_order")
    need(C["unevaluable_retained_not_replaced"] is True and C["cache_failed_eligible_retained"] is True,"segmented_denominator_retention")
    need(C["execution_protocol"]=="original_partial_plus_one_completion_segment" and C["original_single7200_complete"] is False
         and C["freeze_before_evaluation_verified"] is True,"amended_protocol_honesty")
    suite_item=C["suite_manifest"];owner_item=C["owner_release"]
    suite=load(bound(suite_item));owner=load(bound(owner_item))
    need(suite["execution_authorized"] is True and owner["schema"]=="original_owner_test_stage_B_execution_release_v1"
         and owner["decision"]=="ALLOW_ONCE_C_FIXED_TEST_STAGE_B" and owner["no_retry"] is True
         and owner["suite_manifest_sha256"]==suite_item["sha256"] and owner["once_claim_root"]==suite["once_claim_root"],"segmented_original_release")
    need(set(C["phases"])=={"prediction","package"},"segmented_original_phase_domain")
    for name,exits in (("prediction",(1,1,1)),("package",(0,0,0))):phase(C["phases"][name],name,exits,suite_item,owner_item)
    terminal,plan,inv,suite,owner=verify_original_terminal(C)
    parts=verify_partition(C,plan,inv);N=len(parts["suffix"])
    if N==0:
        need(C.get("completion_segment") is None,"empty_suffix_no_invented_segment")
        raise ValueError("empty_suffix_no_approved_current_native_report_path")
    for key in ("actual_prediction_runs","actual_package_runs","actual_scoring_runs","actual_report_runs","actual_completion_segments"):exact_int(C[key],1,"segmented_once_count:"+key)
    source_gate(C["completion_sources"])
    seg=C["completion_segment"];segment_plan_item=seg["plan"];sp=load(bound(segment_plan_item))
    need(sp["schema"]=="TEST_STAGE_B_conditional_completion_plan_v1" and sp["segment_index"]==2 and sp["third_segment_allowed"] is False,"segment2_only")
    need(sp["ordered_suffix_ids"]==parts["suffix"] and sp["interrupted_unknown_ids"]==parts["boundary"]
        and same_ref(sp["original_terminal_receipt"],C["original_score"]["actual_receipt"])
        and same_ref(sp["original_partial_inventory"],C["original_score"]["partial_inventory"])
        and same_ref(sp["original_scoring_plan"],C["original_score"]["scoring_plan"])
        and same_ref(sp["original_suite"],suite_item) and same_ref(sp["original_claim"],C["original_score"]["claim"]),"segment_plan_original_partition")
    need(same_ref(sp["original_input_inventory"],C["original_score"]["input_inventory"]),"segment_original_input_inventory_join")
    bound(sp["original_input_inventory"])
    need(sp["budget"]==dict(CPU_threads=1,GPU=0,RSS_bytes=8589934592,total_wall_seconds=15*N+600,record_workers=1,cleanup_seconds=60),"fixed_segment2_budget")
    frozen_root=Path(suite["once_claim_root"]).parent
    need(sp["output_directory"]==str(frozen_root/"completion_segment_2"/"result") and sp["started_directory"]==str(frozen_root/"completion_segment_2"/"started"),"canonical_segment2_directories")
    need({p.name for p in Path(suite["once_claim_root"]).glob("CONDITIONAL_COMPLETION_SEGMENT_*.json")}=={"CONDITIONAL_COMPLETION_SEGMENT_2.json"},"no_third_segment_claim")
    ci=seg["claim"];claim=load(bound(ci))
    need(ci["path"]==str(Path(suite["once_claim_root"])/"CONDITIONAL_COMPLETION_SEGMENT_2.json") and sp["segment_claim_path"]==ci["path"],"canonical_segment2_once")
    need(claim["schema"]=="TEST_STAGE_B_completion_claim_v1" and claim["segment_index"]==2 and claim["no_retry"] is True
         and claim["plan_sha256"]==segment_plan_item["sha256"] and same_ref(claim["original_score_claim"],C["original_score"]["claim"]),"actual_segment2_claim")
    release=load(bound(seg["release"]))
    need(release["schema"]=="TEST_STAGE_B_completion_once_release_v1" and release["plan_sha256"]==segment_plan_item["sha256"]
         and release["entrypoint_sha256"]==SEGMENT_SOURCE_SHAS["completion"] and release["execution_authorized"] is True
         and claim["release_sha256"]==seg["release"]["sha256"],"segment2_release")
    need(same_ref(release["independent_review"],C["completion_sources"]["independent_source_review"]),"segment2_review_release")
    started=sealed_inventory(seg["started_inventory"],sp["started_directory"])
    names={i+suffix for i in parts["suffix"] for suffix in (".read_started.json",".execution_started.json")}
    need(set(started)==names,"exact_suffix_started_journal")
    for iid in parts["suffix"]:
        for ending,stage in ((".read_started.json","input_binding_read_started"),(".execution_started.json","record_execution_started")):
            j=load(Path(sp["started_directory"])/(iid+ending))
            need(j["input_id"]==iid and j["original_ordinal"]==queue.index(iid)
                 and j["segment_plan_sha256"]==segment_plan_item["sha256"]
                 and j["input_sha256"]=={k:x["sha256"] for k,x in plan["inputs"].items()} and j["stage"]==stage,"durable_started_identity")
            if ending==".execution_started.json":
                need(j["record_deadline"]==j["record_started_at"]+10
                     and j["preprocessing_deadline"]==j["record_started_at"]+2,"same_original_record_clock")
    segment_audit=load(bound(seg["execution"]["application_review"]["artifact"]))
    need(value_at(segment_audit,seg["execution"]["application_review"]["started_inventory_sha256_path"])==seg["started_inventory"]["sha256"],"actual_started_journal_audit_binding")
    receipt,result=sealed_primary(seg["execution"])
    need(seg["execution"]["phase"]=="completion" and receipt["budget"]==sp["budget"]
         and seg["execution"]["output_root"]==sp["output_directory"]
         and receipt["input_sha256"]=={segment_plan_item["path"]:segment_plan_item["sha256"],seg["release"]["path"]:seg["release"]["sha256"]},"actual_segment_phase_budget")
    need(result["schema"]=="TEST_STAGE_B_completion_segment_completed_v1" and result["segment_index"]==2
         and result["suffix_count"]==N and result["prefix_count"]==len(parts["prefix"]) and result["boundary_unknown"]==parts["boundary"]
         and result["original_C"]==3637 and result["H_unavailable"]==1371
         and same_ref(result["completion_plan"],segment_plan_item) and same_ref(result["original_terminal_receipt"],C["original_score"]["actual_receipt"])
         and result["original_outer_exit"]==terminal["actual_outer_exit"],"actual_completed_segment_accounting")
    manifest_item=result["raw_segment_manifest"]
    segment_files=sealed_inventory(seg["execution"]["output_inventory"],seg["execution"]["output_root"])
    need(manifest_item["path"]==str(Path(seg["execution"]["output_root"])/"manifest.json")
         and segment_files["manifest.json"]==manifest_item["sha256"],"actual_segment_manifest_inventory")
    manifest=load(bound(manifest_item))
    need(manifest["status"]=="FROZEN_ASSIGNMENT_EXECUTION_COMPLETED" and manifest["input_records"]==N
         and [r["input_id"] for r in manifest["record_ledger"]]==parts["suffix"],"complete_suffix_not_partial")
    report_item=C["segmented_report"]
    report_plan_item=report_item["plan"];rp=load(bound(report_plan_item));report_release=load(bound(report_item["release"]))
    need(rp["schema"]=="TEST_STAGE_B_completion_final_report_plan_v1" and same_ref(rp["completion_plan"],segment_plan_item)
         and same_ref(rp["completion_actual_receipt"],seg["execution"]["actual_receipt"])
         and same_ref(rp["original_owner_suite_release"],owner_item),"segmented_report_plan")
    need(report_release["schema"]=="TEST_STAGE_B_completion_report_once_release_v1" and report_release["execution_authorized"] is True
         and report_release["plan_sha256"]==report_plan_item["sha256"]
         and report_release["entrypoint_sha256"]==SEGMENT_SOURCE_SHAS["completion_report"]
         and same_ref(report_release["independent_review"],C["completion_sources"]["independent_source_review"]),"segmented_report_release")
    need(same_ref(rp["completion_output_inventory"],seg["execution"]["output_inventory"]),"report_completion_output_inventory_join")
    bound(rp["completion_output_inventory"])
    need(rp["output_directory"]==report_item["execution"]["output_root"],"report_actual_output_directory_join")
    rr,report=sealed_primary(report_item["execution"])
    need(rr.get("input_sha256")=={report_plan_item["path"]:report_plan_item["sha256"],
         report_item["release"]["path"]:report_item["release"]["sha256"]},"report_actual_plan_release_input_map")
    need(report_item["execution"]["phase"]=="completion_report" and rr["budget"]==dict(CPU_threads=1,GPU=0,RSS_bytes=8589934592,total_wall_seconds=600,record_workers=1,cleanup_seconds=60),"actual_segmented_report_budget")
    for k,hsh in FROZEN_REPORT_SHAS.items():bound(report_item["frozen_implementations"][k]);need(report_item["frozen_implementations"][k]["sha256"]==hsh,"frozen_report_axes_source")
    rc=load(bound(report["report_claim"]));key=hashlib.sha256((owner["release_id"]+"\0report\0execution").encode()).hexdigest()
    need(report["report_claim"]["path"]==str(Path(suite["once_claim_root"])/(key+".json")) and rc["phase"]=="report" and rc["scope"]=="execution"
         and rc["suite_manifest_sha256"]==suite_item["sha256"] and rc["owner_release_sha256"]==owner_item["sha256"],"single_original_report_claim")
    need(report["schema"]=="TEST_STAGE_B_segmented_native_test_report_v1" and report["source_relative_only"] is True and report["original_score_rewritten"] is False,"segmented_report_honesty")
    coverage=report["coverage"]
    need(coverage["original_C_identity_denominator"]==3637 and coverage["H_original_identity_denominator"]==1371
         and coverage["H_assignment_status"]=="unavailable_no_model_no_assignment_metrics"
         and coverage["public_scoring_queue"]==3636 and coverage["public_unavailable_unknown"]==1
         and coverage["partition"]=={k:parts[k] for k in ("prefix","boundary","suffix")}
         and coverage["origin_counts"]=={k:n for k,n in (("original_completed",len(parts["prefix"])),("boundary_saved_initial_unknown",len(parts["boundary"])),("completion_completed",len(parts["suffix"]))) if n}
         and sum(coverage["origin_counts"].values())==3636,"combined_fixed_coverage")
    need(same_ref(report["original_execution"]["receipt"],C["original_score"]["actual_receipt"])
         and report["original_execution"]["outer_exit"]==terminal["actual_outer_exit"]
         and same_ref(report["completion_execution"]["receipt"],seg["execution"]["actual_receipt"])
         and report["completion_execution"]["outer_exit"]==0,"true_original_and_segment_exits")
    metrics=report["native_test"]
    need(metrics["role"]=="native_test" and metrics["estimator_source_sha256"]==FROZEN_REPORT_SHAS["estimators"]
         and metrics["whole_input_and_strict_full_separate"] is True and metrics["chemical_quotient_top3"] is None
         and metrics["real_experiment_truth_promoted"] is False,"frozen_9d_native_axes")
    exact_int(metrics["test_threshold_fit_calls"],0,"no_test_metric_refit")
    hc=report["highconfidence"]
    need(hc["published"]==0 and hc["test_fit_calls"]==0 and hc["stored_statuses_preserved"] is True
         and hc["Cval_artifact_sha256"]==suite["Cval_frozen_calibration"]["sha256"]
         and hc["reconstructed_fixed_off_metadata_from_saved_rows"] is True
         and hc["reconstructed_margins"] is False and hc["reconstructed_target_invariance"] is False,"frozen_off_no_scientific_reconstruction")
    need(hc["application_validation"]["expected_applications"]==hc["application_validation"]["validated_applications"]
         and hc["application_validation"]["frozen_method_artifacts"]==3,"cdf_P1_full_application_domain")
    for k in ("new_models","new_solves","new_gold_evaluations","new_mapping_search"):exact_int(report[k],0,"no_new_report_science")
    return {"original_terminal":terminal,"partition":parts,"completion":result,"report":report}

def verify_test(t):
    if t.get("schema")==SEGMENTED_SCHEMA:return verify_segmented(t)
    return verify_test_once(t)

def validate(root=None):
    if root is None:root=ROOT
    root=Path(root);read=lambda n:load(root/n)
    need(digest(root/"SOURCE_RELATIVE_FINITE_H_UNAVAILABLE_SCOPE_AUTHORIZATION.txt")==AUTH_SHA,"scope_authorization_bytes")
    need(digest(root/"SOURCE_RELATIVE_COMPLETION_SCOPE_DECISION.json")==DECISION_SHA,"original_scope_bytes")
    d=read("SOURCE_RELATIVE_COMPLETION_SCOPE_DECISION.json")
    need(digest(d["original_strong_predicate"]["path"])==STRONG_SHA and d["original_strong_predicate"]["sha256"]==STRONG_SHA,"strong_predicate_unchanged")
    done=read("source_relative_completion.json");need(done["status"]==STATUS and done["scope_acceptance_sha256"]==AUTH_SHA,"finite_status_scope")
    for k in ("overall_user_goal_fully_met","trusted_experimental_benchmark_complete","H_fixed_test_assignment_complete"):need(done[k] is False,"strong_goal_not_met:"+k)
    need(done["missing_original_annotation_evidence"],"trusted_gold_evidence_gap")
    need(done["training_updates"]==done["external_LLM_API_calls"]==0,"no_new_training_API")
    for k in ("SpatialShift_weights_or_pseudolabels_used","test_used_for_parameter_selection","historical_test_blind_claim"):need(done[k] is False,"scope_boundary:"+k)
    b=read("source_relative_benchmark_manifest.json")
    for k,e in {"truth_basis":"source_relative_current_serialization","reference_basis":"source_asserted_encoded_graph","trust_basis":"internal_source_consistency","trusted_experimental":False,"trusted_experimental_records":0,"original_labels_unchanged":True,"13C_support_audited":True,"unevaluable_identities_retained":True}.items():need(type(b[k]) is type(e) and b[k]==e,"benchmark_scope:"+k)
    need(b["source_relative_1H_records"]>0,"H_source_reference_records")
    need(read("frozen_definition.json")["status"]=="FROZEN_BY_ORIGINAL_SCIENTIFIC_OWNER","owner_frozen_definition")
    test_payload=read("test_evaluation.json");segmented=test_payload.get("schema")==SEGMENTED_SCHEMA
    execution_evidence=verify_test(test_payload)
    if segmented:
        need(done["execution_protocol"]=="original_partial_plus_one_completion_segment" and done["batch_execution_protocol_amended"] is True and done["original_single7200_complete"] is False,"explicit_done_segmented_scope")
    runs=read("baseline_comparison.json")["baseline_runs"]
    need(len(runs)==3 and {r["baseline"] for r in runs}=={"B0","B1","B2"},"three_baselines")
    need(len({r["shared_prediction_manifest_sha256"] for r in runs})==1,"shared_frozen_predictions")
    for r in runs:
        need(r["inputs_unchanged"] is True and r["training_updates"]==0 and r["all_frozen_input_ids_accounted_for"] is True,"baseline_batch_accounting")
        if segmented:
            need(r["status"]=="COMPLETE_ACCOUNTING_SEGMENTED" and r["execution_protocol"]=="original_partial_plus_one_completion_segment","segmented_baseline_accounting")
            terminal=execution_evidence["original_terminal"]
            need(r["original_actual_inner_exit"]==terminal["actual_inner_exit"] and r["original_actual_external_exit"]==terminal["actual_outer_exit"],"baseline_original_exit_preserved")
            for k in ("completion_actual_inner_exit","completion_actual_external_exit"):exact_int(r[k],0,"baseline_completion_exit")
        else:
            need(r["status"]=="COMPLETE","baseline_batch_accounting")
            for k in ("actual_inner_exit","actual_external_exit"):exact_int(r[k],0,"baseline_exit")
    cal=read("confidence_calibration.json")
    need(cal["selection_split"]=="validation" and cal["denominators_and_confidence_intervals_reported"] is True and cal["truth_bases_not_pooled"] is True,"validation_calibration")
    verify_coverage(read("stratified_metrics.json"))
    final=read("source_relative_final_independent_review.json")
    need(final["status"]=="PASS_SOURCE_RELATIVE_DELIVERY" and final["independent"] is True and final["trusted_experimental_benchmark_complete"] is False and final["scope_acceptance_sha256"]==AUTH_SHA,"final_independent_scope")
    code=read("code_publication.json")
    need(code["repository"]=="https://github.com/AndrewLuan/nmr-retrieval" and code["head_sha"]==code["remote_main_sha"]==code["github_main_sha"] and code["tests_actual_exit"]==0 and code["actual_execution_scripts_published"] is True,"published_actual_source")
    closure=done["evidence_sha256"];need(isinstance(closure,dict) and closure,"evidence_closure_required")
    subjects={str((root/n).resolve()) for n in REQUIRED if n not in {"source_relative_completion.json","source_relative_final_independent_review.json"}}
    subjects|={str((root/n).resolve()) for n in ("SOURCE_RELATIVE_FINITE_H_UNAVAILABLE_SCOPE_AUTHORIZATION.txt","SOURCE_RELATIVE_COMPLETION_SCOPE_DECISION.json")}
    if segmented:subjects.add(str(bound(test_payload["conditional_scope_authorization"]).resolve()))
    need(subjects<=set(closure),"root_evidence_closure_complete")
    for p,expected in closure.items():need(digest(p)==expected,"final_evidence_SHA:"+p)
    need(final["reviewed_evidence_sha256"]==closure,"final_review_exact_closure")
    return True
def main():
    missing=[n for n in REQUIRED if not (ROOT/n).is_file()]
    if missing:print("PENDING_SOURCE_RELATIVE:"+",".join(missing));return 2
    validate(ROOT)
    print("PASS_"+STATUS+";overall_user_goal_fully_met=false;trusted_experimental_benchmark_complete=false;H_fixed_test_assignment_complete=false");return 0
# 功能概述：每个公开helper访问均重复核授权和公开源码/schema精确SHA；不生成完成证书。
def _public_guard():
    workspace()
    for key,path in (("finite_verifier.public_source_sha256",Path(__file__)),
                     ("finite_verifier.schema_sha256",Path(__file__).with_name("source_relative_delivery_finite_schema.json"))):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=binding(key):
            raise ValueError("finite public source/schema binding mismatch:"+key)
def _guarded(function):
    import functools
    @functools.wraps(function)
    def call(*args,**kwargs):
        _public_guard()
        return function(*args,**kwargs)
    return call
for _name in ('need', 'digest', 'canonical', 'load', 'bound', 'value_at', 'exact_int', 'review', 'phase', 'verify_test_once', 'verify_coverage', 'same_ref', 'sealed_inventory', 'sealed_primary', 'source_gate', 'verify_original_terminal', 'verify_partition', 'verify_segmented', 'verify_test', 'validate', 'main'):
    globals()[_name]=_guarded(globals()[_name])


if __name__=="__main__":raise SystemExit(main())
