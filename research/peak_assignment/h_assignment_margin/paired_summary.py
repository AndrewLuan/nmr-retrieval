"""功能概述：冻结A/B逐观测seed均值与配对connectivity汇总薄入口，不做模型或评分。
fixed_domain从原242身份和已存H211 B2行冻结每个观测的eligibility、轴、role、connectivity；
join_seed_rows要求四份211/193×A/B保存行完整同域及独立record ledger；零观测身份只留在ledger，失败/unknown保留，禁止int(0.5)。
summarize先用两个二元success的整数和表示两倍均值，再按固定分母汇总；各role/合并
共用一次connectivity抽样计划，2000次seed173，沿旧paired_gain比率及_quantile插值。
validate_training_gate要求完整成功四作业/曝光/四末权重SHA及原实际应用PASS，先于任何baseline或评分行读取。
新增_validate_segmented_completion仅核分段成功receipt、retained A身份/history、两原失败ref与plan/contract；旧非分段训练兼容。
CLI默认仅检查控制JSON且release关闭；--execute必须精确SHA绑定四份已完成评分manifest。
self-test仅运行人工tinyfixture的8次抽样和负例，不读真实结果、不执行正式2000统计。
主要副作用：仅独占写新JSON；不改旧文件，不fit/选阈值/选seed，无forward/solver/SSH。
"""
from pathlib import Path
from collections import defaultdict,Counter
from random import Random
from math import floor,ceil,isfinite
import argparse,json,hashlib,sys,datetime
SEEDS=(211,193)
ARMS=("A","B")
ROLES=("original_val","tune")
AXIS=dict(truth_basis="source_relative_current_serialization",nucleus="1H",task_semantics="derived_serialized_value_bin",target_level="parent",target_semantics="set",baseline="B2")
REPLICATES=2000
BOOTSTRAP_SEED=173
MISSING=object()
def need(ok,why):
    if not ok:raise ValueError(why)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def read_ref(ref):
    need(isinstance(ref,dict) and set(("path","sha256"))<=set(ref),"path+SHA required")
    need(sha(ref["path"])==ref["sha256"],"bound input SHA changed")
    return Path(ref["path"])
def reviewed_leaf(value,path):
    need(isinstance(path,list) and path and all(isinstance(k,str) and k for k in path),"review selector path")
    for name in path:
        need(isinstance(value,dict) and name in value,"review selector missing")
        value=value[name]
    return value
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

def validate_training_gate(release):
    """先核真实训练终态和应用审核，仅读取其控制证据；不读取任何评分或baseline行。"""
    need(release.get("schema")=="frozen_AB_evaluation_release_v1","evaluation release schema")
    need("execution_release" not in release,"obsolete execution_release forbidden")
    need(release.get("evaluation_release") is True,"evaluation release closed")
    refs=release["inputs"];evidence_names=("training_success_receipt","training_complete","exposure_order_receipt")
    evidence={};used=[]
    for name in evidence_names:
        path=read_ref(refs[name]);used.append(dict(path=str(path),sha256=sha(path)));evidence[name]=json.loads(path.read_text())
        if name=="training_success_receipt":
            receipt=evidence[name]
            need(receipt.get("success") is True and type(receipt.get("actual_child_exit")) is int and receipt["actual_child_exit"]==0 and type(receipt.get("actual_outer_exit")) is int and receipt["actual_outer_exit"]==0 and receipt.get("stop_reason",MISSING) is None,"successful paired training terminal required")
    complete=evidence["training_complete"];receipt=evidence["training_success_receipt"];exposure=evidence["exposure_order_receipt"]
    need(complete.get("validation_calls")==0 and complete.get("test_calls")==0 and complete.get("checkpoint_selection")=="epoch10_only","training completion scope")
    jobs=complete["results"];keys={str(s)+"_"+a for s in SEEDS for a in ARMS}
    need(isinstance(jobs,list) and len(jobs)==4,"four completed training jobs required")
    need({str(j.get("seed"))+"_"+str(j.get("variant")) for j in jobs}==keys,"four fixed training jobs required")
    need(receipt.get("completed_jobs")==jobs,"actual receipt/complete job binding")
    finals=release["final_checkpoints"];need(set(finals)==keys,"all four final checkpoints required")
    orders={}
    for job in jobs:
        name=str(job["seed"])+"_"+job["variant"];ref=finals[name]
        need(job.get("steps")==770 and job.get("selection")=="final_epoch_10_only" and ref.get("epoch")==10,"fixed final epoch and updates")
        need(job.get("checkpoint")==ref["path"] and job.get("sha256")==ref["sha256"],"final checkpoint identity/SHA binding")
        path=read_ref(ref);used.append(dict(path=str(path),sha256=sha(path)))
        order=job.get("actual_order_sha256")
        need(isinstance(order,str) and len(order)==64 and all(c in "0123456789abcdef" for c in order),"actual exposure order SHA required")
        orders[name]=order
    for seed in SEEDS:need(orders[str(seed)+"_A"]==orders[str(seed)+"_B"],"same-seed paired exposure mismatch")
    need(exposure.get("schema")=="frozen_AB_training_exposure_order_v1" and exposure.get("actual_order_sha256_by_job")==orders,"exposure receipt does not bind all four actual orders")
    used.extend(_validate_segmented_completion(receipt,complete,jobs,lambda ref:json.loads(read_ref(ref).read_text()),read_ref))
    binding=release["training_application_review"];review_path=read_ref(binding);used.append(dict(path=str(review_path),sha256=sha(review_path)));review=json.loads(review_path.read_text())
    decision=binding["required_decision"]
    need(isinstance(decision,str) and decision.startswith("PASS") and reviewed_leaf(review,binding["decision_path"])==decision,"exact actual training application PASS required")
    need(set(binding["checkpoint_sha256_paths"])==keys and set(binding["evidence_sha256_paths"])==set(evidence_names),"review bindings complete")
    for name in keys:need(reviewed_leaf(review,binding["checkpoint_sha256_paths"][name])==finals[name]["sha256"],"review final checkpoint SHA mismatch")
    for name in evidence_names:need(reviewed_leaf(review,binding["evidence_sha256_paths"][name])==refs[name]["sha256"],"review training evidence SHA mismatch")
    return dict(training_application_review_sha256=sha(review_path),required_decision=decision,actual_order_sha256_by_job=orders,checked_refs=used)
def quantile(values,q):
    values=sorted(values);position=(len(values)-1)*q;lo,hi=floor(position),ceil(position)
    return values[lo]+(values[hi]-values[lo])*(position-lo)
def selected(row):
    c=dict(row["context"])
    return row["metric"]=="exact_observation" and all(c.get(k)==v for k,v in AXIS.items())
def key(row):return (row["input_id"],row["observation_id"])
def fixed_domain(preparation):
    records=preparation["fixed_cohort"]["identity_and_saved_baseline_domain"]
    need(len(records)==242 and len({r["input_id"] for r in records})==242,"fixed242 identity domain")
    domain={};identity={};baselines=[];refs=[]
    for record in records:
        iid=record["input_id"];role=record["role"];conn=record["connectivity_sha256"]
        need(role in ROLES,"validation role only")
        identity[iid]=dict(role=role,connectivity_id=conn)
        p=read_ref(record["existing_B2_evaluation"]);refs.append(dict(path=str(p),sha256=sha(p)))
        bundle=json.loads(p.read_text())["B2"];need(bundle["metadata"]["input_id"]==iid,"baseline input binding")
        eligible=[]
        for original in bundle["rows"]:
            if not selected(original):continue
            row=dict(original,input_id=iid,role=role);k=key(row);need(k not in domain,"duplicate baseline observation")
            need(type(row["eligible"]) is bool and type(row["success"]) is bool,"frozen baseline booleans")
            need(dict(row["context"])["connectivity_id"]==conn,"baseline connectivity")
            domain[k]=row;baselines.append(row)
            if row["eligible"]:eligible.append(row["observation_id"])
        need(eligible==record["eligible_observation_ids"],"frozen eligibility order/domain")
    need(Counter(v["role"] for v in identity.values())==Counter(original_val=128,tune=114),"frozen role counts")
    need(Counter(r["role"] for r in domain.values() if r["eligible"])==Counter(original_val=663,tune=593),"fixed eligible663/593")
    return domain,identity,baselines,refs
def validate_record_ledger(identity,rows,ledger,seed,arm):
    """独立身份账本保留零观测记录；科学行不承担完整record覆盖证明。"""
    need(isinstance(ledger,list) and [r.get("input_id") for r in ledger]==list(identity),"complete ordered record ledger required")
    counts=Counter(row.get("input_id") for row in rows)
    need(set(counts)<=set(identity),"row input outside record ledger")
    required={"input_id","role","experiment_seed","experiment_arm","rows_count","actual_status","raw_execution","actual_execution_receipt_sha256","elapsed_seconds"}
    for record in ledger:
        need(required<=set(record),"record ledger fields missing")
        iid=record["input_id"]
        need(record["role"]==identity[iid]["role"] and record["experiment_seed"]==seed and record["experiment_arm"]==arm,"record ledger role/seed/arm mismatch")
        need(type(record["rows_count"]) is int and record["rows_count"]>=0 and record["rows_count"]==counts[iid],"record ledger rows_count mismatch")
        need(isinstance(record["actual_status"],str) and bool(record["actual_status"]),"record ledger actual status")
        raw=record["raw_execution"]
        need(isinstance(raw,dict) and isinstance(raw.get("path"),str) and bool(raw["path"]) and isinstance(raw.get("sha256"),str) and len(raw["sha256"])==64,"record raw execution ref")
        value=record["actual_execution_receipt_sha256"]
        need(value is None or isinstance(value,str) and len(value)==64,"record execution receipt SHA")
        elapsed=record["elapsed_seconds"]
        need(type(elapsed) in (int,float) and isfinite(elapsed) and elapsed>=0,"record elapsed seconds")
    return dict(records=len(ledger),zero_row_records=sum(r["rows_count"]==0 for r in ledger),scientific_rows=len(rows))
def join_seed_rows(domain,identity,runs,record_ledgers):
    need(set(runs)=={(s,a) for s in SEEDS for a in ARMS},"four fixed seed/arm runs")
    need(set(record_ledgers)==set(runs),"four record ledgers required")
    joined={}
    for seed,arm in sorted(runs):
        rows=runs[(seed,arm)];table={}
        validate_record_ledger(identity,rows,record_ledgers[(seed,arm)],seed,arm)
        for row in rows:
            need(row.get("experiment_seed")==seed and row.get("experiment_arm")==arm,"row seed/arm mismatch")
            iid=row.get("input_id");need(iid in identity,"foreign input")
            need(row.get("role")==identity[iid]["role"],"row role mismatch")
            need(row.get("metric")!="record_identity_only","metadata marker is not a scientific row")
            if not selected(row):continue
            k=key(row);need(k in domain and k not in table,"foreign/duplicate observation")
            base=domain[k]
            need(type(row["eligible"]) is bool and type(row["success"]) is bool and type(row["prediction_supported"]) is bool,"binary saved EvaluationRow required")
            need(row["eligible"]==base["eligible"],"frozen gold eligibility changed")
            need(not row["success"] or row["eligible"] and row["prediction_supported"],"unsupported/ineligible cannot succeed")
            need(dict(row["context"])==dict(base["context"]),"semantic/reference/connectivity context changed")
            for field in ("eligibility_determinator","eligibility_reason_codes"):
                need(row.get(field)==base.get(field),"gold eligibility evidence changed")
            table[k]=row
        need(set(table)==set(domain),"all frozen observations including failures required")
        joined[(seed,arm)]=table
    output=[]
    for k,base in domain.items():
        a=sum(joined[(s,"A")][k]["success"] for s in SEEDS)
        b=sum(joined[(s,"B")][k]["success"] for s in SEEDS)
        # Integers are two-times means, not int(mean); half successes remain exact.
        output.append(dict(input_id=k[0],observation_id=k[1],role=base["role"],connectivity_id=identity[k[0]]["connectivity_id"],eligible=base["eligible"],A_twice_seed_mean=a,B_twice_seed_mean=b,original_H211_success=int(base["success"])))
    return output
def summary_point(rows):
    rr=[r for r in rows if r["eligible"]];n=len(rr)
    a=sum(r["A_twice_seed_mean"] for r in rr);b=sum(r["B_twice_seed_mean"] for r in rr);old=sum(r["original_H211_success"] for r in rr)
    return dict(eligible=n,A_seedmean_successes=a/2,B_seedmean_successes=b/2,A_rate=a/(2*n) if n else None,B_rate=b/(2*n) if n else None,gain_B_minus_A=(b-a)/(2*n) if n else None,gain_twice_success_count=b-a,original_H211_successes=old,original_H211_rate=old/n if n else None,B_point_below_original_H211=(b<2*old) if n else None)
def summarize(rows,*,replicates=REPLICATES,trace=False):
    groups=defaultdict(list)
    for row in rows:
        if row["eligible"]:groups[row["connectivity_id"]].append(row)
    cluster_ids=sorted(groups)
    roles=("combined",)+ROLES
    points={role:summary_point(rows if role=="combined" else [r for r in rows if r["role"]==role]) for role in roles}
    draws={role:[] for role in roles};undefined=Counter();trace_rows=[]
    if len(cluster_ids)>=2:
        rng=Random(BOOTSTRAP_SEED)
        for _ in range(replicates):
            # One global paired draw; all records/roles/peaks and both seed means remain together.
            chosen=[cluster_ids[rng.randrange(len(cluster_ids))] for _ in cluster_ids]
            sampled=[r for cid in chosen for r in groups[cid]]
            counts={}
            for role in roles:
                point=summary_point(sampled if role=="combined" else [r for r in sampled if r["role"]==role])
                counts[role]=point["eligible"]
                if point["eligible"]:draws[role].append(point["gain_B_minus_A"])
                else:undefined[role]+=1
            if trace:trace_rows.append(dict(cluster_ids=chosen,eligible=counts))
    for role in roles:
        valid=len(draws[role])==replicates and len(cluster_ids)>=2
        points[role].update(CI95=[quantile(draws[role],(1-.95)/2),quantile(draws[role],1-(1-.95)/2)] if valid else None,CI_support_status="on" if valid else "off",undefined_replicates=undefined[role],bootstrap_replicates=replicates,bootstrap_seed=BOOTSTRAP_SEED)
    combined=points["combined"];n=combined["eligible"]
    effect=n>0 and combined["gain_twice_success_count"]*10>=n
    positive_CI=combined["CI95"] is not None and combined["CI95"][0]>0
    nonnegative_roles=all(points[r]["eligible"]>0 and points[r]["gain_twice_success_count"]>=0 for r in ROLES)
    result=dict(points=points,bootstrap_unit="eligible-observation connectivity; all roles/records/seed means held in same cluster",eligible_connectivities=len(cluster_ids),replicates=replicates,seed=BOOTSTRAP_SEED,confidence=.95,interval="percentile with frozen linear quantile interpolation",pass_checks=dict(combined_gain_at_least_five_pp=effect,combined_CI_lower_positive=positive_CI,both_role_point_gains_nonnegative=nonnegative_roles,pre_registered_criterion_pass=effect and positive_CI and nonnegative_roles),baseline_interpretation="Original saved H211 B2 same domain, no new baseline forward; B below it cannot be described as deployment-baseline improvement.",new_baseline_forwards=0)
    if trace:result["synthetic_draw_trace"]=trace_rows
    return result
def synthetic_checks():
    # Three records, two clusters, unequal role sizes; one cluster spans both roles.
    layout=[("r1","o1","original_val","c1"),("r1","o2","original_val","c1"),("r2","o3","tune","c1"),("r3","o4","original_val","c2")]
    domain={};identity={}
    for iid,oid,role,conn in layout:
        identity[iid]=dict(role=role,connectivity_id=conn)
        domain[(iid,oid)]=dict(input_id=iid,observation_id=oid,role=role,context=list(dict(AXIS,record_id="source:"+iid,connectivity_id=conn).items()),metric="exact_observation",eligible=True,success=False,prediction_supported=False,eligibility_determinator="synthetic-fixed",eligibility_reason_codes=[])
    identity["r4"]=dict(role="tune",connectivity_id="c2")  # no observations, ledger only
    values={(211,"A"):[0,0,0,0],(193,"A"):[1,0,0,0],(211,"B"):[1,1,0,0],(193,"B"):[1,0,1,0]}
    runs={}
    for pair,success in values.items():
        runs[pair]=[dict(r,success=bool(v),prediction_supported=True,experiment_seed=pair[0],experiment_arm=pair[1]) for r,v in zip(domain.values(),success)]
    ledgers={pair:[dict(input_id=iid,role=meta["role"],experiment_seed=pair[0],experiment_arm=pair[1],rows_count=sum(row["input_id"]==iid for row in rows),actual_status="no_observations" if iid=="r4" else "synthetic_completed",raw_execution=dict(path="synthetic_not_read/"+iid,sha256="0"*64),actual_execution_receipt_sha256=None,elapsed_seconds=0.) for iid,meta in identity.items()] for pair,rows in runs.items()}
    need(all(validate_record_ledger(identity,runs[pair],ledger,*pair)["zero_row_records"]==1 for pair,ledger in ledgers.items()),"empty record not retained")
    joined=join_seed_rows(domain,identity,runs,ledgers);answer=summarize(joined,replicates=8,trace=True)
    need(joined[0]["A_twice_seed_mean"]==1,"half success was lost")
    need(answer["points"]["combined"]["A_rate"]==.125 and answer["points"]["combined"]["B_rate"]==.5 and answer["points"]["combined"]["gain_B_minus_A"]==.375,"seed mean/weighted ratio")
    need(answer["points"]["combined"]["gain_B_minus_A"]!=(answer["points"]["original_val"]["gain_B_minus_A"]+answer["points"]["tune"]["gain_B_minus_A"])/2,"incorrect equal-role mean")
    for draw in answer["synthetic_draw_trace"]:
        need(draw["eligible"]["combined"]==draw["eligible"]["original_val"]+draw["eligible"]["tune"],"roles independently sampled")
        need(draw["eligible"]["tune"]==draw["cluster_ids"].count("c1"),"cross-role cluster broken")
    import copy
    bad=copy.deepcopy(runs);bad[(211,"A")][0]["eligible"]=False
    try:join_seed_rows(domain,identity,bad,ledgers)
    except ValueError:pass
    else:raise AssertionError("changed denominator accepted")
    bad=copy.deepcopy(runs);bad[(211,"A")].append(bad[(211,"A")][0])
    try:join_seed_rows(domain,identity,bad,ledgers)
    except ValueError:pass
    else:raise AssertionError("duplicate accepted")
    for mutation in ("rows_count","missing_record","role"):
        bad=copy.deepcopy(ledgers)
        if mutation=="rows_count":bad[(211,"A")][-1]["rows_count"]=1
        elif mutation=="missing_record":bad[(211,"A")].pop()
        else:bad[(211,"A")][-1]["role"]="original_val"
        try:join_seed_rows(domain,identity,runs,bad)
        except ValueError:pass
        else:raise AssertionError("bad ledger accepted:"+mutation)
    return dict(status="SYNTHETIC_PASS",synthetic_replicates=8,formal_2000_bootstrap_executed=False,checks=["seed half preserved","count-weighted combined ratio","one shared cross-role cluster draw","eligibility mutation rejected","duplicate observation rejected","zero-observation ledger retains fourth record without changing four-obs denominator","bad ledger count/missing record/role rejected"],identity_records=4,zero_observation_records=1,points=answer["points"])
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--preparation");parser.add_argument("--preparation-sha256");parser.add_argument("--runs");parser.add_argument("--runs-sha256");parser.add_argument("--release");parser.add_argument("--release-sha256");parser.add_argument("--out");parser.add_argument("--execute",action="store_true");parser.add_argument("--self-test",action="store_true");a=parser.parse_args()
    if a.self_test:
        need(not a.execute,"self-test cannot execute evaluation");print(json.dumps(synthetic_checks()));return
    need(all((a.preparation,a.preparation_sha256,a.runs,a.runs_sha256,a.release,a.release_sha256)),"control refs required")
    paths=dict(preparation=read_ref(dict(path=a.preparation,sha256=a.preparation_sha256)),runs=read_ref(dict(path=a.runs,sha256=a.runs_sha256)),release=read_ref(dict(path=a.release,sha256=a.release_sha256)))
    release=json.loads(paths["release"].read_text())
    if not a.execute:
        print(json.dumps(dict(status="CONTROL_CHECK_ONLY_NO_RESULTS_READ",evaluation_release_open=release.get("evaluation_release") is True,formal_bootstrap_executed=False)));return
    training_gate=validate_training_gate(release)
    need(release.get("paired_summary_source_sha256")==sha(__file__) and release.get("preparation_sha256")==a.preparation_sha256 and release.get("runs_sha256")==a.runs_sha256,"release exact input/source binding")
    need(a.out and not Path(a.out).exists(),"unique new output required")
    before={k:sha(p) for k,p in paths.items()}
    preparation=json.loads(paths["preparation"].read_text());control=json.loads(paths["runs"].read_text());need(control["schema"]=="H211_AB_four_saved_score_manifests_v1","runs schema")
    need(control.get("preparation_sha256")==a.preparation_sha256,"runs fixed cohort binding")
    domain,identity,baseline,baseline_refs=fixed_domain(preparation)
    runs={};record_ledgers={};all_refs=list(baseline_refs)+training_gate["checked_refs"]
    for item in control["runs"]:
        pair=(item["experiment_seed"],item["experiment_arm"]);need(pair not in runs,"duplicate seed/arm")
        manifest_path=read_ref(item["manifest"]);manifest=json.loads(manifest_path.read_text())
        need(manifest["schema"]=="H211_fixed_AB_assignment_scores_v1" and manifest["status"]=="COMPLETED_FIXED_B2_EVALUATION" and manifest["seed"]==pair[0] and manifest["arm"]==pair[1],"completed score manifest")
        frozen=preparation["fixed_cohort"];declared=manifest["fixed_domain"]
        need(declared["records"]==242 and declared["eligible_by_role"]=={"original_val":663,"tune":593} and declared["combined_exact_eligible"]==1256,"manifest fixed domain counts")
        need(declared["ordered_ids_sha256"]==frozen["ordered_ids_sha256"] and declared["eligible_domain_sha256"]==frozen["eligible_domain_sha256"],"manifest fixed domain identity")
        need(manifest["preparation_sha256"]==a.preparation_sha256 and manifest["allow_test"] is False and manifest["calibration_fit_calls"]==0,"score fixed scope")
        rows_path=read_ref(manifest["rows"]);runs[pair]=[json.loads(line) for line in rows_path.open()]
        ledger_path=read_ref(manifest["record_ledger"]);record_ledgers[pair]=[json.loads(line) for line in ledger_path.open()]
        all_refs.append(dict(path=str(ledger_path),sha256=sha(ledger_path)))
        all_refs.extend((dict(path=str(manifest_path),sha256=sha(manifest_path)),dict(path=str(rows_path),sha256=sha(rows_path))))
    joined=join_seed_rows(domain,identity,runs,record_ledgers);result=summarize(joined)
    result["record_ledger_validation"]={str(seed)+"_"+arm:validate_record_ledger(identity,runs[(seed,arm)],ledger,seed,arm) for (seed,arm),ledger in record_ledgers.items()}
    result["bootstrap_cluster_order"]="sorted connectivity IDs; deterministic combined-seedmean order, not bit-identical old role API draws"
    need({k:sha(p) for k,p in paths.items()}==before,"control changed")
    for ref in all_refs:read_ref(ref)
    result.update(schema="H211_AB_seedmean_paired_summary_v1",status="COMPLETED_SAVED_ROWS_SUMMARY_NOT_DEPLOYMENT_PROMOTION",reference_axis=dict(AXIS,metric="exact_observation"),input_records=242,fixed_eligible=1256,roles=dict(original_val=dict(records=128,eligible=663),tune=dict(records=114,eligible=593)),source_sha256=sha(__file__),control_sha256=before,training_gate=training_gate,bound_inputs=all_refs,seed_mean_rows_sha256=digest(joined),actual_argv=sys.argv,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),training_or_model_calls=0,formal_bootstrap_executed=True)
    with Path(a.out).open("x") as f:json.dump(result,f,indent=2,allow_nan=False);f.write("\n")
    print(json.dumps(dict(output=a.out,sha256=sha(a.out),pre_registered_criterion_pass=result["pass_checks"]["pre_registered_criterion_pass"])))
if __name__=="__main__":main()
