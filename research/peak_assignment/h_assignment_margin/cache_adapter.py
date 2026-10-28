"""功能概述：冻结A/B末epoch10的匿名242条H预测缓存适配器，默认关闭。
关系：从原5f5 builder保留图、条件、计数、sigma、去重和输出契约；不调用评分或拟合。
validate_evaluation_release先核四checkpoint/曝光/固定身份/源码与资源引用；未放行不导入torch。
main只选择一个明确seed/arm，用原H211 args和同字节registry构造，安全加载裸state_dict。
非equivalence_head状态与原checkpoint逐项精确；输出原inputs/predictions/stages/receipt/manifest。
每模型独立新目录和缓存namespace；观测只用于身份账本，不进入模型特征。
资源总量由外部新plan明确提供，本文件不放行执行、不选择模型、不重校准、不读取test。
"""
import argparse,contextlib,gc,hashlib,json,math,os,resource,signal,sys,time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

NOM_SHA="07ada18e634cefff755ae46533370df3e2e3a3bb78679d6058dc62e7fa57ca85"
WIDTH_SHA="e0ff99480ff277fff57598b9e90f8b0428cb5e396d3c0f1bbccd221e35820f0f"
COUNT_SHA={"structures":"6c1f52c380637611ef90a3fbf0e32e6050255f3544c57caf0560818a829267b1","predictions":"320a94dd463e09b13b586fd2961eea14b85bb395d8952d9aca275ba77536539b"}
CONDITIONS={"solvent","frequency","pH","ph","temperature","NMR_solvent"}
DEADLINE=float("inf")
RSS_LIMIT=8589934592

def need(ok,reason):
    if not ok:raise ValueError(reason)

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def json_rows(path):
    with open(path) as f:
        for line in f:
            if line.strip():yield json.loads(line)

def public_record(row):
    need(isinstance(row,dict) and set(row)<= {"input_id","nucleus","smiles","actual_conditions","observations"},"public_whitelist")
    need(all(k in row for k in ("input_id","nucleus","smiles","actual_conditions")),"public_required_fields")
    need(isinstance(row["input_id"],str) and bool(row["input_id"]),"opaque_input_id_required")
    need(row["nucleus"] in ("1H","13C") and isinstance(row["smiles"],str),"public_structure_nucleus")
    c=row["actual_conditions"]
    need(isinstance(c,dict) and set(c)<=CONDITIONS,"actual_condition_whitelist")
    need(all(v is None or (isinstance(v,(str,int,float)) and not isinstance(v,bool)) for v in c.values()),"actual_condition_scalar")
    if "observations" in row:
        need(isinstance(row["observations"],list),"anonymous_observations_list")
        for obs in row["observations"]:
            need(isinstance(obs,dict) and set(obs)=={"bin_id","ppm_decimal"},"anonymous_bin_whitelist")
            need(isinstance(obs["bin_id"],str) and isinstance(obs["ppm_decimal"],str),"anonymous_bin_strings")
    # input_id只在输出join；public observations在此处即剥离。
    native=dict(smiles=row["smiles"],experimental_conditions={k:v for k,v in c.items() if k!="NMR_solvent"})
    if "NMR_solvent" in c:native["source_metadata"]={"NMR_solvent":c["NMR_solvent"]}
    return row["input_id"],row["nucleus"],native

def dedup_key(nucleus,canonical,cond,condition_vector):
    return digest(dict(nucleus=nucleus,canonical_smiles=canonical,native_cond=cond,
                       recovered_condition_vector=condition_vector))

def input_join_metadata(actual_conditions):
    # 完整实际条件只作输入身份账本；模型共享键仍只含原生编码特征。
    return dict(actual_conditions_sha256=digest(actual_conditions),
                cache_key_semantics="native_encoded_features_only")

def rebuild_counts(structures_path,predictions_path,wanted,identity):
    # 最后一个有效source_smiles覆盖同record_id；无关结构删除旧selected映射。
    structures={}
    for row in json_rows(structures_path):
        try:smi=identity(row["source_smiles"])[0]
        except ValueError:continue
        if smi in wanted:structures[row["record_id"]]=smi
        else:structures.pop(row["record_id"],None)
    registry={};conflicts=set()
    for row in json_rows(predictions_path):
        if row["record_id"] not in structures:continue
        smi=structures[row["record_id"]]
        counts={n:v["count"] for n,v in row["nuclei"].items() if v.get("status")=="predicted"}
        if smi in registry and registry[smi]!=counts:conflicts.add(smi)
        registry[smi]=counts
    for smi in conflicts:registry.pop(smi,None)
    return registry,conflicts

def graph_snapshot(mol):
    # 字段与source_transport._graph_snapshot一致；仅图结构，不是源实验身份认证。
    return dict(atoms=[dict(index=a.GetIdx(),z=a.GetAtomicNum(),isotope=a.GetIsotope(),charge=a.GetFormalCharge(),radicals=a.GetNumRadicalElectrons(),aromatic=a.GetIsAromatic(),chiral_tag=str(a.GetChiralTag())) for a in mol.GetAtoms()],
                bonds=[dict(a=b.GetBeginAtomIdx(),b=b.GetEndAtomIdx(),kind=str(b.GetBondType()),aromatic=b.GetIsAromatic(),stereo=str(b.GetStereo()),stereo_atoms=list(b.GetStereoAtoms())) for b in mol.GetBonds()])

def peak_rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=="darwin" else 1024)

def monitor(*_):
    need(time.monotonic()<DEADLINE,"wall_budget")
    need(peak_rss()<=RSS_LIMIT,"RSS_budget")


ORIGINAL_H_SHA="2d5c96533794c52a424ae5092f2e377a30c2ba85b5dd15d1c68bd92bea46f24f"
COHORT_SHA="92befbbaa295e8ed37a72fbbd0c16866ac6e8172e1ea2203ebd0831f1b0585a8"

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

def validate_training_success(release):
    """核实际四作业成功与配对顺序；任何部分训练在数据行读取前拒绝。"""
    models=release["final_checkpoints"]
    keys={"211_A","211_B","193_A","193_B"}
    need(set(models)==keys,"four_final_models")
    evidence={}
    for key in ("training_success_receipt","training_complete","exposure_order_receipt"):
        ref=release["inputs"][key]
        need(sha(ref["path"])==ref["sha256"],"training_evidence_sha:"+key)
        evidence[key]=json.loads(Path(ref["path"]).read_text())
    actual=evidence["training_success_receipt"];complete=evidence["training_complete"]
    need(actual.get("success") is True and type(actual.get("actual_child_exit")) is int and actual["actual_child_exit"]==0 and type(actual.get("actual_outer_exit")) is int and actual["actual_outer_exit"]==0 and actual.get("stop_reason","missing") is None,"training_actual_not_success")
    jobs=complete["results"]
    need(isinstance(jobs,list) and len(jobs)==4 and actual.get("completed_jobs")==jobs,"training_four_actual_jobs")
    need(complete.get("validation_calls")==0 and complete.get("test_calls")==0 and complete.get("checkpoint_selection")=="epoch10_only","training_completion_contract")
    orders={}
    for row in jobs:
        key=str(row["seed"])+"_"+row["variant"]
        need(key in keys and key not in orders,"training_duplicate_or_unknown_job")
        need(type(row["steps"]) is int and row["steps"]==770 and row["selection"]=="final_epoch_10_only","training_update_budget")
        ref=models[key]
        need(type(ref["epoch"]) is int and ref["epoch"]==10 and row["sha256"]==ref["sha256"] and Path(row["checkpoint"]).resolve()==Path(ref["path"]).resolve(),"training_final_model_binding")
        value=row["actual_order_sha256"]
        need(isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value),"training_order_digest")
        orders[key]=value
    need(set(orders)==keys and all(orders[str(seed)+"_A"]==orders[str(seed)+"_B"] for seed in (211,193)),"training_paired_order")
    exposure=evidence["exposure_order_receipt"]
    need(exposure.get("schema")=="frozen_AB_training_exposure_order_v1" and exposure.get("actual_order_sha256_by_job")==orders,"training_exposure_order_binding")
    evidence["segmented_checked_refs"]=_validate_segmented_completion(actual,complete,jobs,lambda ref:json.loads(Path(ref["path"]).read_text()),lambda ref:need(sha(ref["path"])==ref["sha256"],"segmented_metadata_digest"))
    return evidence

def validate_evaluation_release(a):
    """仅标准库准入；成功训练和独审先于数据行读取及任何tensor加载。"""
    need(sha(a.release)==a.release_sha256,"release_sha")
    release=json.loads(Path(a.release).read_text())
    need(release.get("schema")=="frozen_AB_evaluation_release_v1" and release.get("evaluation_release") is True and "execution_release" not in release,"evaluation_execution_closed")
    training_evidence=validate_training_success(release)
    need(release["adapter_sha256"]==sha(__file__),"adapter_binding")
    need(release["original_checkpoint_sha256"]==ORIGINAL_H_SHA,"original_checkpoint_binding")
    models=release["final_checkpoints"]
    for key,ref in models.items():need(sha(ref["path"])==ref["sha256"],"final_checkpoint:"+key)
    for key,path,expected in (("cohort",a.cohort,a.cohort_sha256),("assets",a.assets_manifest,a.assets_sha256),("plan",a.plan,a.plan_sha256)):
        ref=release["inputs"][key];need(Path(ref["path"]).resolve()==Path(path).resolve() and ref["sha256"]==expected and sha(path)==expected,"release_input:"+key)
    need(release.get("no_refit") is True and release.get("seed_mean_selection") is False,"no_refit_or_selection")
    review=release["training_application_review"];need(sha(review["path"])==review["sha256"],"training_review_sha")
    payload=json.loads(Path(review["path"]).read_text())
    node=payload
    for key in review["decision_path"]:node=node[key]
    need(node==review["required_decision"] and isinstance(node,str) and node.startswith("PASS"),"training_review_decision")
    for key,ref in models.items():
        node=payload
        for part in review["checkpoint_sha256_paths"][key]:node=node[part]
        need(node==ref["sha256"],"training_review_model_binding:"+key)
    for key in ("training_success_receipt","training_complete","exposure_order_receipt"):
        node=payload
        for part in review["evidence_sha256_paths"][key]:node=node[part]
        need(node==release["inputs"][key]["sha256"],"training_review_evidence_binding:"+key)
    ref=release["inputs"]["fixed_cohort"]
    need(sha(ref["path"])==ref["sha256"]==COHORT_SHA,"fixed_cohort_sha")
    fixed=json.loads(Path(ref["path"]).read_text())
    ids=fixed["ordered_input_ids"];rows=list(json_rows(a.cohort))
    need(len(ids)==242 and len(set(ids))==242 and [r["input_id"] for r in rows]==ids,"anonymous242_order")
    need(all(r["nucleus"]=="1H" for r in rows),"H_only")
    for r in rows:public_record(r)
    for ref in training_evidence["segmented_checked_refs"]:need(sha(ref["path"])==ref["sha256"],"segmented_metadata_changed")
    return release,models[a.model_key]

def main():
    started=time.monotonic()
    p=argparse.ArgumentParser()
    for name in ("cohort","cohort-sha256","assets-manifest","assets-sha256","plan","plan-sha256","out"):p.add_argument("--"+name,required=True)
    p.add_argument("--release",required=True);p.add_argument("--release-sha256",required=True);p.add_argument("--model-key",choices=("211_A","211_B","193_A","193_B"),required=True);p.add_argument("--check-only",action="store_true")
    a=p.parse_args();evaluation_release,selected=validate_evaluation_release(a)
    if a.check_only:print(json.dumps({"status":"metadata_checked_no_execution","model_key":a.model_key}));return 0
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    tracked={};reported=set();rows=[];actual_condition_joins={};receipt=dict(status="partial",forward_started=0,forward_completed=0,forward_validated=0,input_count=0,input_success=0,input_failed=0,input_not_started=0,dedup_hits=0,model_loads={},updates=0,CPU_threads=2,GPU_devices=0)
    def write_json(name,value):
        tmp=out/(name+".tmp")
        with tmp.open("w") as f:json.dump(value,f,allow_nan=False,indent=2);f.flush();os.fsync(f.fileno())
        tmp.replace(out/name)
    def emit(name,value):
        if name=="inputs.jsonl":value=dict(value,**actual_condition_joins[value["input_id"]])
        with (out/name).open("a") as f:f.write(json.dumps(value,allow_nan=False)+"\n");f.flush();os.fsync(f.fileno())
    def stage(name,**extra):
        receipt.update(seconds=time.monotonic()-started,peakRSS_bytes=peak_rss(),last_stage=name)
        emit("stages.jsonl",dict(stage=name,**receipt,**extra));write_json("receipt.partial.json",receipt)
    def freeze(path,expected):
        path=str(Path(path).resolve());actual=sha(path);need(actual==expected,"pre_hash:"+path);tracked[path]=actual;return path
    try:
        plan=json.loads(Path(freeze(a.plan,a.plan_sha256)).read_text())
        need(plan["schema"]=="frozen_prediction_cache_plan_v1" and plan["execution_authorized"] is True,"execution_not_released")
        need(plan["CPU_threads"]==2 and plan["GPU_devices"]==0 and type(plan["RSS_limit_bytes"]) is int and plan["RSS_limit_bytes"]>0,"resource_plan")
        need(str(Path(sys.executable).resolve())==str(Path(plan["python_executable"]).resolve()),"python_runtime")
        for key in ("wall_seconds_total","load_seconds_per_model","forward_seconds_per_model","max_forward_started"):
            need(type(plan[key]) in (int,float) and plan[key]>0,"positive_explicit_budget:"+key)
        need(type(plan["max_forward_started"]) is int and type(plan["input_count"]) is int and plan["input_count"]>=0,"integer_cohort_forward_budgets")
        global DEADLINE,RSS_LIMIT
        RSS_LIMIT=plan["RSS_limit_bytes"];total_deadline=started+plan["wall_seconds_total"];DEADLINE=total_deadline
        signal.signal(signal.SIGALRM,monitor);signal.setitimer(signal.ITIMER_REAL,.1,.1)
        os.environ.update(CUDA_VISIBLE_DEVICES="",OMP_NUM_THREADS="2",MKL_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2")
        cohort=freeze(a.cohort,a.cohort_sha256);assets=json.loads(Path(freeze(a.assets_manifest,a.assets_sha256)).read_text())
        need(assets["schema"]=="frozen_prediction_assets_v1","assets_schema")
        required_assets={"nomination","H_width","numeric_config","numerical_release","structures","predictions"}
        need(set(assets["files"])==required_assets,"asset_file_whitelist")
        files={k:freeze(v["path"],v["sha256"]) for k,v in assets["files"].items()}
        need(sha(files["nomination"])==NOM_SHA and sha(files["H_width"])==WIDTH_SHA,"approved_model_width_asset")
        for key,want in COUNT_SHA.items():need(sha(files[key])==want,"historical_count_asset:"+key)
        bundle=Path(assets["bundle_root"]).resolve()
        actual_sources={str(x.relative_to(bundle)):x for pkg in ("nmr_transfer","nmr_assignment") for x in (bundle/pkg).rglob("*.py")}
        need(set(actual_sources)==set(assets["source_files"]),"source_closure_file_set")
        for rel,path in actual_sources.items():freeze(path,assets["source_files"][rel])
        freeze(__file__,assets["runner_sha256"])
        sys.path.insert(0,str(bundle))
        import torch
        torch.set_num_threads(2);torch.set_num_interop_threads(2)
        from rdkit import Chem,rdBase
        receipt["rdkit_version"]=rdBase.rdkitVersion
        from torch_geometric.data import Batch
        from nmr_transfer.data import identity,graph,condition,physical_features
        from nmr_transfer.h_conditions import local_environment
        from nmr_transfer.h_acyl import acyl_environment
        from nmr_transfer.h_metadata import raw_conditions
        from nmr_transfer.h_uncertainty import node_classes,CLASSES
        from nmr_transfer.emission_model import make_model
        from nmr_assignment.native_adapter import adapt_native_predictions
        for module in tuple(sys.modules.values()):
            path=getattr(module,"__file__",None)
            if path and str(Path(path).resolve()).startswith(str(bundle)+os.sep) and str(path).endswith(".py"):
                need(str(Path(path).resolve()) in tracked,"imported_source_outside_closure")
        nom=json.loads(Path(files["nomination"]).read_text());width=json.loads(Path(files["H_width"]).read_text());numeric=json.loads(Path(files["numeric_config"]).read_text())
        need(width["classes"]==list(CLASSES) and len(width["selected_ppm"])==9,"H_class_order")
        info=numeric["source_frozen_information"]
        need(info["H_width_sha256"]==WIDTH_SHA and [info["H_widths_ppm"][x] for x in CLASSES]==width["selected_ppm"],"H_exact_width_binding")
        need(info["C_width_ppm"]==2 and info["C_width_source"]=="fixed_error_scale_prior_no_qualified_C_residual_fit","C_fixed_assignment_prior")
        baseline_ref=evaluation_release["inputs"]["original_native_predictions"]
        baseline_path=freeze(baseline_ref["path"],baseline_ref["sha256"])
        baseline_raw={}
        for raw in json_rows(baseline_path):
            need(raw["cache_key"] not in baseline_raw,"duplicate_original_native_key")
            baseline_raw[raw["cache_key"]]=raw
        rows=[];ids=set();wanted=set()
        for row in json_rows(cohort):
            input_id,nucleus,native=public_record(row);need(input_id not in ids,"duplicate_input_id");ids.add(input_id)
            actual_condition_joins[input_id]=input_join_metadata(row["actual_conditions"])
            try:
                mol=Chem.MolFromSmiles(native["smiles"]);need(mol is not None,"invalid_structure")
                need(not any(atom.GetIsotope() for atom in mol.GetAtoms()),"isotope_scope_not_supported")
                canonical=identity(native["smiles"])[0];wanted.add(canonical)
                rows.append((input_id,nucleus,native,canonical,None))
            except Exception as exc:rows.append((input_id,nucleus,native,None,type(exc).__name__+":"+str(exc)))
        receipt["input_count"]=len(rows);need(len(rows)==plan["input_count"],"frozen_cohort_count")
        registry,conflicts=rebuild_counts(files["structures"],files["predictions"],wanted,identity)
        stage("metadata_ready",RDKit_version=rdBase.rdkitVersion,unique_structures=len(wanted),structural_count_conflicts=len(conflicts))
        cache={};failed_keys=set();model=None
        real_load=torch.load
        for nucleus,key in (("1H","H"),):
            subset=[row for row in rows if row[1]==nucleus]
            if not subset:continue
            spec=nom[key];checkpoint=freeze(evaluation_release["inputs"]["original_checkpoint"]["path"],ORIGINAL_H_SHA);freeze(spec["training_config"],spec["training_config_sha256"])
            final_checkpoint=freeze(selected["path"],selected["sha256"])
            if key=="H":
                registry_ref=evaluation_release["inputs"]["equivalence_registry"]
                need(registry_ref["sha256"]==nom["H"]["registry"]["sha256"],"registry_same_bytes")
                freeze(registry_ref["path"],registry_ref["sha256"])
            DEADLINE=min(total_deadline,time.monotonic()+plan["load_seconds_per_model"])
            @contextlib.contextmanager
            def safe_load():
                allowed={str(Path(checkpoint).resolve()),str(Path(final_checkpoint).resolve())}
                if key=="H":allowed.add(str(Path(registry_ref["path"]).resolve()))
                def load(path,*args,**kwargs):
                    resolved=str(Path(path).resolve());need(resolved in allowed and not args,"unapproved_load")
                    kwargs.update(weights_only=True,map_location="cpu");stage("before_safe_load",nucleus=nucleus,path=resolved)
                    result=real_load(path,**kwargs);stage("after_safe_load",nucleus=nucleus,path=resolved);return result
                torch.load=load
                try:yield
                finally:torch.load=real_load
            with safe_load():
                payload=torch.load(checkpoint,weights_only=True,map_location="cpu");cfg=dict(payload["args"])
                need(payload["args"].get("equivalence_registry_sha256")==registry_ref["sha256"],"checkpoint_registry_binding")
                cfg["equivalence_registry_path"]=registry_ref["path"]
                final_state=torch.load(final_checkpoint,weights_only=True,map_location="cpu")
                need(set(final_state)==set(payload["state_dict"]),"final_state_keys")
                for name,value in payload["state_dict"].items():
                    actual=final_state[name]
                    need(actual.shape==value.shape and actual.dtype==value.dtype and bool(torch.isfinite(actual).all()),"final_state_signature:"+name)
                    if not name.startswith("equivalence_head."):need(torch.equal(actual,value),"non_head_changed:"+name)
                expected=dict(nucleus=nucleus,model=spec["model"],width=256,layers=3)
                if key=="H":
                    for name in ("condition_mode","response_mode","message_mode","context_depth","equivalence_mode","count_decode","use_frozen_embedding","joint_reporting","amide_gap_scale"):expected[name]=spec["lineage"][name]
                    expected.update(equivalence_registry_path=registry_ref["path"],equivalence_registry_sha256=nom["H"]["registry"]["sha256"])
                else:
                    expected["mode"]="domain"
                    if "seed" in cfg:expected["seed"]=21
                    need(not cfg.get("count_decode",False),"C_count_decode")
                for name,value in expected.items():need(cfg.get(name)==value,"config:"+name)
                need(not any("sigma" in name for name in payload["state_dict"]),"unexpected_native_sigma_head")
                stage("before_model_construction",nucleus=nucleus);model=make_model(cfg);stage("after_model_construction",nucleus=nucleus)
                need(type(model).__module__+"."+type(model).__name__==spec["model_class"],"class_mismatch")
                model.load_state_dict(final_state,strict=True);stage("after_strict_load",nucleus=nucleus)
            for module_name,module in tuple(sys.modules.items()):
                if module_name=="nmr_transfer" or module_name.startswith(("nmr_transfer.","nmr_assignment.")):
                    path=getattr(module,"__file__",None)
                    if path:need(str(Path(path).resolve()) in tracked,"imported_native_source_outside_bundle")
            del payload,final_state;gc.collect();model.eval()
            for param in model.parameters():param.requires_grad_(False)
            receipt["model_loads"][nucleus]=1
            receipt.update(model_key=a.model_key,final_checkpoint_sha256=selected["sha256"],evaluation_release_sha256=a.release_sha256)
            DEADLINE=min(total_deadline,time.monotonic()+plan["forward_seconds_per_model"])
            for input_id,_,native,canonical,pre_error in subset:
                ck=None
                try:
                    if pre_error:raise ValueError(pre_error)
                    cond=condition(native);cond[0]=0.
                    recovered=raw_conditions(native)[0] if key=="H" else None
                    cond_tensor=torch.tensor(cond,dtype=torch.float32).reshape(1,4)
                    vector=torch.tensor(recovered["vector"]).reshape(1,-1) if recovered else None
                    ck=dedup_key(nucleus,canonical,cond_tensor.tolist(),vector.tolist() if vector is not None else None)
                    if ck in failed_keys:raise ValueError("same_native_key_previously_failed_no_retry")
                    if ck in cache:
                        receipt["dedup_hits"]+=1;receipt["input_success"]+=1
                        emit("inputs.jsonl",dict(input_id=input_id,nucleus=nucleus,status="ok",cache_key=ck,deduplicated=True));reported.add(input_id);stage("input_deduplicated",input_id=input_id);continue
                    g=graph(canonical);g.structure_smiles=canonical;g.cond=cond_tensor
                    g.physics=torch.tensor(physical_features(canonical,registry.get(canonical))).reshape(1,8);g.modality_is_theory=torch.tensor([False])
                    if key=="H":
                        g.local_environment=torch.tensor(local_environment(canonical));g.acyl_environment=torch.tensor(acyl_environment(canonical).copy());g.condition_vector=vector
                    b=Batch.from_data_list([g]);monitor()
                    need(receipt["forward_started"]<plan["max_forward_started"],"forward_count_budget")
                    receipt["forward_started"]+=1;stage("forward_started",input_id=input_id,cache_key=ck)
                    with torch.inference_mode():d=model(b,details=True)
                    receipt["forward_completed"]+=1;stage("forward_completed",input_id=input_id,cache_key=ck)
                    values,mass,owners,groups=[d[k].detach().cpu() for k in ("values","weights","owners","groups")]
                    need(len(values)==len(mass)==len(owners)==len(groups) and len(values)>0,"component_shapes")
                    need(bool(torch.isfinite(values).all() and torch.isfinite(mass).all() and (mass>0).all() and (groups==0).all()),"component_numeric")
                    mol=Chem.AddHs(Chem.MolFromSmiles(canonical));parents={}
                    for atom in mol.GetAtoms():
                        count=(sum(n.GetAtomicNum()==1 for n in atom.GetNeighbors()) if key=="H" and atom.GetAtomicNum()!=1 else int(key=="C" and atom.GetAtomicNum()==6))
                        if key=="H" and atom.GetAtomicNum()==1 and not any(n.GetAtomicNum()!=1 for n in atom.GetNeighbors()):count=1
                        if count:parents[str(atom.GetIdx())]=count
                    need(set(owners.tolist())=={int(p) for p in parents},"owner_coverage")
                    for parent,count in parents.items():need(abs(float(mass[owners==int(parent)].sum())-count)<1e-5,"parent_mass")
                    known=bool(b.equivalence_known[0]) if key=="H" else False
                    layout={name:getattr(b,name).detach().cpu().tolist() for name in ("equivalence_ids","equivalence_known","preserved_group_orbits","preserved_group_ordinal","preserved_group_sizes") if hasattr(b,name)}
                    tags=node_classes(b)[d["owners"]].detach().cpu().tolist() if key=="H" else [None]*len(values)
                    sigmas=[width["selected_ppm"][tag] for tag in tags] if key=="H" else [2.]*len(values)
                    sigma_source="historical_H211_train_parent_class_width:"+WIDTH_SHA if key=="H" else "fixed_error_scale_prior_no_qualified_C_residual_fit:"+sha(files["numeric_config"])
                    centers=[float(x)*(10 if key=="H" else 200) for x in values]
                    evidence=dict(nucleus=nucleus,parent_mass=parents,isotope_count_verified=True,
                                  evidence_ids=["native_graph:"+ck+":"+rdBase.rdkitVersion],
                                  partition_hypothesis_id=("H_registry:"+nom["H"]["registry"]["sha256"] if known else "unresolved_parent_pool" if key=="H" else "carbon_atom_capacity"))
                    if known:evidence["partition_evidence_ids"]=["H_registry:"+nom["H"]["registry"]["sha256"]]
                    pred=adapt_native_predictions(evidence,centers_ppm=centers,masses=mass.tolist(),owners=owners.tolist(),graph_indices=groups.tolist(),sigma_ppm=sigmas,sigma_sources=[sigma_source]*len(values),known_h_layout=known,
                        layout_evidence_ids=["native_layout:"+ck] if known else [],
                        attachment_evidence_ids=["native_preserved_orbits:"+ck] if known else [],
                        equivalence_ids=layout.get("equivalence_ids") if key=="H" else None,
                        preserved_group_orbits=layout["preserved_group_orbits"][0] if known else None,
                        preserved_group_ordinal=layout["preserved_group_ordinal"][0] if known else None,
                        preserved_group_sizes=layout["preserved_group_sizes"][0] if known else None)
                    raw=dict(cache_key=ck,nucleus=nucleus,canonical_smiles=canonical,rdkit_version=rdBase.rdkitVersion,native_graph_recipe="AddHs(MolFromSmiles(canonical_isomeric_heavy_SMILES))",native_graph_snapshot=graph_snapshot(mol),native_graph_snapshot_sha256=digest(graph_snapshot(mol)),native_values=values.tolist(),center_scale=10 if key=="H" else 200,centers_ppm=centers,component_mass=mass.tolist(),owners=owners.tolist(),groups=groups.tolist(),native_sigma_ppm=None,native_sigma_source="no_trained_native_sigma_head",layout=layout,native_cond=cond_tensor.tolist(),recovered_condition_vector=vector.tolist() if vector is not None else None,assignment_width_ppm=sigmas,assignment_width_class=tags,assignment_width_source=sigma_source,predictions=asdict(pred))
                    need(ck in baseline_raw,"initial_native_signature_unavailable")
                    initial=baseline_raw[ck]
                    for field in ("canonical_smiles","rdkit_version","native_graph_snapshot","native_graph_snapshot_sha256","component_mass","owners","groups","layout","native_cond","recovered_condition_vector","assignment_width_ppm","assignment_width_class","assignment_width_source"):
                        need(raw[field]==initial[field],"initial_native_signature:"+field)
                    emit("predictions.jsonl",raw);cache[ck]=True;receipt["forward_validated"]+=1;receipt["input_success"]+=1
                    emit("inputs.jsonl",dict(input_id=input_id,nucleus=nucleus,status="ok",cache_key=ck,deduplicated=False));reported.add(input_id);stage("forward_validated",input_id=input_id,cache_key=ck)
                except (KeyboardInterrupt,SystemExit):raise
                except Exception as exc:
                    if ck:failed_keys.add(ck)
                    receipt["input_failed"]+=1
                    emit("inputs.jsonl",dict(input_id=input_id,nucleus=nucleus,status="failed_retained",cache_key=ck,error=type(exc).__name__+":"+str(exc)));reported.add(input_id)
                    stage("input_failed_retained",input_id=input_id)
                    monitor()
                    if str(exc).startswith(("forward_count_budget","wall_budget","RSS_budget","unapproved_load")):raise
            del model;model=None;gc.collect()
        DEADLINE=total_deadline
        need(receipt["input_success"]+receipt["input_failed"]==receipt["input_count"],"input_accounting")
        receipt["status"]="complete" if receipt["input_failed"]==0 else "partial_with_retained_failures"
    except BaseException as exc:receipt.update(status="failed_partial",error=type(exc).__name__+":"+str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        for input_id,nucleus,_,_,_ in rows:
            if input_id not in reported:
                emit("inputs.jsonl",dict(input_id=input_id,nucleus=nucleus,status="not_started_retained",error="batch_aborted_no_retry"))
                receipt["input_not_started"]+=1
        post={}
        for path,before in tracked.items():
            try:
                post[path]=sha(path)
                if post[path]!=before:receipt.update(status="failed_partial",hash_closure_error=path)
            except Exception as exc:receipt.update(status="failed_partial",hash_closure_error=str(exc))
        receipt.update(seconds=time.monotonic()-started,peakRSS_bytes=peak_rss(),pre_hashes=tracked,post_hashes=post)
        if "total_deadline" in locals() and time.monotonic()>total_deadline:receipt.update(status="failed_partial",resource_error="total_wall_budget_including_hash_closure")
        if receipt["peakRSS_bytes"]>RSS_LIMIT:receipt.update(status="failed_partial",resource_error="RSS_budget")
        write_json("receipt.json",receipt)
        outputs={name:sha(out/name) for name in ("inputs.jsonl","predictions.jsonl","stages.jsonl","receipt.json") if (out/name).exists()}
        write_json("manifest.json",dict(schema="frozen_prediction_cache_manifest_v1",model_key=a.model_key,final_checkpoint_sha256=selected["sha256"],evaluation_release_sha256=a.release_sha256,status=receipt["status"],cohort_sha256=a.cohort_sha256,assets_sha256=a.assets_sha256,plan_sha256=a.plan_sha256,outputs=outputs,center_contract="same frozen centers for B0/B1/B2; mass is component_mass, not observed integral",assignment_width_contract="separate from native sigma; H original classfloat/C2ppm fixed prior",forwards=dict(started=receipt["forward_started"],completed=receipt["forward_completed"],validated=receipt["forward_validated"])))
        print(json.dumps(receipt,allow_nan=False),flush=True)
    return 0 if receipt["status"]=="complete" else 1

if __name__=="__main__":sys.exit(main())
