"""功能概述：独立核验有限源相对交付，不替代原强目标谓词。
validate绑定d280/7889与原强谓词SHA，保留overall/trusted实验/H固定test完成False。
verify_test区分H1371不可评/0次固定test模型评分，与C3637一次实际预测/包装/评分/报告；
phase核receipt、persistent once claim、真实输出inventory/hash和应用独审。预测真实1/1/1
不得洗白，实际H/C加载及3636/3635/1/0计数取SHA与inventory绑定builder receipt；expected声明不作证据，score/report另核0。verify_coverage逐域保留未完成目标；默认缺件PENDING。
只读控制JSON/交付文件，不读谱值或JSONL、不训练/运行模型/评价/阈值/Git、不写完成状态。
邻接schema说明封装字段，合成tests验证假Hpass/换身份/假指标/退出洗白/缺实际输出等。
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
def verify_test(t):
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
    runs=read("baseline_comparison.json")["baseline_runs"]
    need(len(runs)==3 and {r["baseline"] for r in runs}=={"B0","B1","B2"},"three_baselines")
    need(len({r["shared_prediction_manifest_sha256"] for r in runs})==1,"shared_frozen_predictions")
    for r in runs:
        need(r["status"]=="COMPLETE" and r["inputs_unchanged"] is True and r["training_updates"]==0 and r["all_frozen_input_ids_accounted_for"] is True,"baseline_batch_accounting")
        for k in ("actual_inner_exit","actual_external_exit"):exact_int(r[k],0,"baseline_exit")
    cal=read("confidence_calibration.json")
    need(cal["selection_split"]=="validation" and cal["denominators_and_confidence_intervals_reported"] is True and cal["truth_bases_not_pooled"] is True,"validation_calibration")
    verify_test(read("test_evaluation.json"));verify_coverage(read("stratified_metrics.json"))
    final=read("source_relative_final_independent_review.json")
    need(final["status"]=="PASS_SOURCE_RELATIVE_DELIVERY" and final["independent"] is True and final["trusted_experimental_benchmark_complete"] is False and final["scope_acceptance_sha256"]==AUTH_SHA,"final_independent_scope")
    code=read("code_publication.json")
    need(code["repository"]=="https://github.com/AndrewLuan/nmr-retrieval" and code["head_sha"]==code["remote_main_sha"]==code["github_main_sha"] and code["tests_actual_exit"]==0 and code["actual_execution_scripts_published"] is True,"published_actual_source")
    closure=done["evidence_sha256"];need(isinstance(closure,dict) and closure,"evidence_closure_required")
    subjects={str((root/n).resolve()) for n in REQUIRED if n not in {"source_relative_completion.json","source_relative_final_independent_review.json"}}
    subjects|={str((root/n).resolve()) for n in ("SOURCE_RELATIVE_FINITE_H_UNAVAILABLE_SCOPE_AUTHORIZATION.txt","SOURCE_RELATIVE_COMPLETION_SCOPE_DECISION.json")}
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
for _name in ("need","digest","canonical","load","bound","value_at","exact_int","review","phase","verify_test","verify_coverage","validate","main"):
    globals()[_name]=_guarded(globals()[_name])

if __name__=="__main__":raise SystemExit(main())
