# 功能概述：已审conditional4公开副本，实际源SHA与portableSHA分别绑定。
# 关系：显式runtime授权/源码闭包；保留原终态、once、边界、预算与科学谓词。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding
authorize()
"""功能概述：条件性第二段只执行原固定队列可证明未开始后缀；不改变原score或其claim。
partition只看顺序完成身份和文件名证据，保守隔离最多一条边界，不读指标选路。
validate绑定原终态、全产物inventory、原计划与科学源码；失败/已开始记录永不重跑。
run复用5485原run函数全文，仅注入started hook和隔离计划视图；所有科学逐记录body保持原文。
入口默认check-only；--execute还须精确新plan/release和独审绑定，独立claim永久保留，无第三段。
本文件不加载模型，不改原输入/源码/配置；输出第二段与原非0退出分开，最终report由新merge分支处理。
"""
from pathlib import Path
import argparse,ast,copy,hashlib,importlib.util,json,os,sys,time
AUTH_SHA="7268574cf03549dc8aaf8c02adc3e0388946d8b12cbccf867838f963d2a1433e"
CALLER_SHA=binding("conditional_completion.public_caller_sha256")
SUPERVISOR_SHA=binding("conditional_completion.public_supervisor_sha256")
def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(item):
    need(sha(item["path"])==item["sha256"],"bound SHA");return json.loads(Path(item["path"]).read_text())
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("x") as f:json.dump(v,f,indent=2,allow_nan=False);f.write("\n");f.flush();os.fsync(f.fileno())
    directory_fd=os.open(str(p.parent),os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
    try:os.fsync(directory_fd)
    finally:os.close(directory_fd)
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def partition(queue,completed,touched,recovered=()):
    need(len(queue)==len(set(queue)),"duplicate queue")
    need(completed==queue[:len(completed)] and len(completed)<=len(queue),"nonprefix completions")
    need(set(touched)<=set(queue),"foreign started evidence")
    if len(completed)==len(queue):return dict(prefix=completed,boundary=[],suffix=[])
    if recovered:
        need(list(recovered)==[queue[len(completed)]],"only next complete persisted result recoverable")
        prefix=completed+list(recovered)
        need(set(touched)<=set(prefix),"started beyond recovered record")
        return dict(prefix=prefix,boundary=[],suffix=queue[len(prefix):])
    boundary=[queue[len(completed)]]
    need(set(touched)<=set(completed+boundary),"started outside conservative boundary")
    return dict(prefix=completed,boundary=boundary,suffix=queue[len(completed)+1:])
def touched_ids(root):
    ids=set()
    for directory in ("raw","evaluation"):
        for p in (Path(root)/directory).iterdir() if (Path(root)/directory).exists() else ():
            if not p.is_file():continue
            name=p.name
            if name.endswith(".json.tmp"):name=name[:-4]
            if not name.endswith(".json"):continue
            n=name[:-5]
            for ending in (".not_started",".payload"):
                if n.endswith(ending):n=n[:-len(ending)]
            ids.add(n)
    return ids
def recoverable_next(root,queue,completed):
    """只验证紧邻prefix的已保存完整记录形状/资格；绝不按成功或残差挑选。"""
    if len(completed)==len(queue):return []
    iid=queue[len(completed)];root=Path(root)
    paths=[root/"raw"/(iid+".json"),root/"evaluation"/(iid+".json"),root/"evaluation"/(iid+".not_started.json")]
    if not all(p.is_file() for p in paths):return []
    try:
        raw,final,initial=[json.loads(p.read_text()) for p in paths]
        need(raw["input_id"]==iid and set(final)==set(initial)=={"B0","B1","B2"},"recoverable complete identity/methods")
        for m,b in final.items():
            need(b["metadata"]["input_id"]==iid and b["metadata"]["roles"]==["native_test"],"recoverable metadata")
            def domain(rows):
                values={}
                for r in rows:
                    key=(r["metric"],r["observation_id"]);need(key not in values,"duplicate recoverable rows")
                    values[key]=[r[k] for k in ("context","eligible","eligibility_reason_codes","eligibility_determinator")]
                return values
            need(domain(b["rows"])==domain(initial[m]),"recoverable fixed eligibility")
        return [iid]
    except (ValueError,KeyError,TypeError):return []
def inventory(root):
    return {str(p.relative_to(root)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(Path(root).rglob("*")) if p.is_file()}
def same_item(a,b):return all(a.get(k)==b.get(k) for k in ("path","sha256"))
def validate_terminal(terminal):
    need(terminal.get("schema")=="TEST_STAGE_B_phase_actual_v1" and terminal.get("phase")=="score" and terminal.get("status")=="FAILED_OR_PARTIAL_RETAINED_NO_RETRY","original score receipt schema/phase/status")
    from datetime import datetime
    start=datetime.fromisoformat(terminal["started_UTC"]);finish=datetime.fromisoformat(terminal["finished_UTC"])
    need(start.tzinfo is not None and finish.tzinfo is not None and finish>=start,"finished original terminal timestamps")
    need(type(terminal.get("actual_worker_exit")) is int and (terminal.get("actual_inner_exit") is None or type(terminal["actual_inner_exit"]) is int),"observed worker/nullable inner EXIT")
    need(type(terminal.get("actual_outer_exit")) is int and terminal["actual_outer_exit"]!=0,"original observed nonzero outer EXIT required")
    need(terminal.get("termination_reason") in ("wall_limit","RSS_limit","leader_exit","supervisor_exception"),"actual terminal reason")
    need(terminal.get("leader_reaped") is True and terminal.get("owned_survivors")==[],"original tree closed")
    need(terminal.get("once_claim"),"original claim retained")
    # actual_inner_exit=None and missing final child inventory are legitimate
    # when guard kills phase_child_running worker; never invent a signal exit.
    return terminal
def validate(plan):
    need(plan["schema"]=="TEST_STAGE_B_conditional_completion_plan_v1","segment schema")
    need(plan["execution_authorized"] is True and plan["segment_index"]==2 and plan["third_segment_allowed"] is False,"only second segment")
    need(sha(plan["scope_authorization"]["path"])==plan["scope_authorization"]["sha256"]==AUTH_SHA,"owner original scope")
    need(plan["original_suite"]["sha256"]==binding('conditional_completion.original_suite_sha256') and plan["original_scoring_plan"]["sha256"]==binding('conditional_completion.original_scoring_plan_sha256'),"exact original run suite/plan")
    suite=load(plan["original_suite"]);original=load(plan["original_scoring_plan"])
    need(suite["implementations"]["locked_caller"]["sha256"]==CALLER_SHA,"caller5485")
    need(original["repo"]==suite["score_repo"],"original frozen repo")
    terminal=validate_terminal(load(plan["original_terminal_receipt"]))
    original_claim=load(plan["original_claim"])
    request=terminal["request_items"]
    need(same_item(request["suite"],plan["original_suite"]),"terminal exact suite request")
    need(request["release"]["sha256"]==binding('conditional_completion.original_owner_release_sha256') and request["phase"]["sha256"]==binding('conditional_completion.original_score_phase_sha256'),"terminal exact owner/score phase request")
    owner=load(request["release"]);phase=load(request["phase"]);config=load(phase["config"])
    need(owner["schema"]=="original_owner_test_stage_B_execution_release_v1" and owner["decision"]=="ALLOW_ONCE_C_FIXED_TEST_STAGE_B" and owner["suite_manifest_sha256"]==plan["original_suite"]["sha256"] and owner["once_claim_root"]==suite["once_claim_root"],"terminal owner suite binding")
    need(phase["schema"]=="TEST_STAGE_B_execution_phase_v1" and phase["phase"]=="score" and phase["suite_manifest_sha256"]==plan["original_suite"]["sha256"] and phase["budget"]==suite["budget"]["score"],"original score phase semantics")
    need(config["ordered_input_ids"]==original["input_ids"] and config["original_C_identity_count"]==3637 and config["output_directory"]==original["output_directory"] and same_item(config["delegate_plan"],plan["original_scoring_plan"]) and same_item(config["delegate_owner_release"],plan["original_delegate_release"]),"score phase config/plan binding")
    expected_phase_inputs={v["path"]:v["sha256"] for v in (request["suite"],request["release"],request["phase"],phase["config"])}
    expected_phase_inputs.update({v["path"]:v["sha256"] for v in suite["implementations"].values()})
    expected_phase_inputs.update({v["path"]:v["sha256"] for v in config.values() if isinstance(v,dict) and "path" in v and "sha256" in v})
    need(terminal["phase_input_sha256"]==expected_phase_inputs,"terminal exact phase input closure")
    key=hashlib.sha256((owner["release_id"]+"\0score\0execution").encode()).hexdigest()
    need(plan["original_claim"]["path"]==str(Path(suite["once_claim_root"])/(key+".json")),"original exact score claim path")
    need(same_item(plan["original_claim"],terminal["once_claim"]) and original_claim["schema"]=="TEST_STAGE_B_persistent_once_claim_v1" and original_claim["phase"]=="score" and original_claim["scope"]=="execution" and original_claim["suite_manifest_sha256"]==plan["original_suite"]["sha256"] and original_claim["owner_release_sha256"]==request["release"]["sha256"] and original_claim["release_id"]==owner["release_id"] and original_claim["claim_PID"]==terminal["child_PID"],"original exact score owner claim binding")
    root=Path(original["output_directory"])
    inv=load(plan["original_partial_inventory"])
    need(inventory(root)==inv["output_sha256"],"full original partial inventory closure")
    input_seal=load(plan["original_input_inventory"])
    expected_inputs={v["path"]:v["sha256"] for v in list(original["inputs"].values())+original["implementations"]}
    need(input_seal["input_sha256"]==expected_inputs,"full original input/source seal")
    need(all(sha(p)==h for p,h in expected_inputs.items()),"sealed input/source bytes")
    completed=json.loads((root/"record_completion_ledger.json").read_text()) if (root/"record_completion_ledger.json").exists() else []
    completed_ids=[r["input_id"] for r in completed]
    parts=partition(original["input_ids"],completed_ids,touched_ids(root),recoverable_next(root,original["input_ids"],completed_ids))
    need(parts["suffix"]==plan["ordered_suffix_ids"] and parts["boundary"]==plan["interrupted_unknown_ids"],"exact original suffix and boundary")
    need(parts["suffix"],"no unstarted suffix; no segment")
    for iid in parts["boundary"]:
        initial_path=root/"evaluation"/(iid+".not_started.json")
        need(initial_path.is_file(),"BLOCKED_MISSING_SAVED_BOUNDARY_DENOMINATOR")
        initial=json.loads(initial_path.read_text());need(set(initial)=={"B0","B1","B2"},"boundary saved full methods")
        need(all(v["prediction_supported"] is False and v["success"] is False for rows in initial.values() for v in rows),"boundary initial unsupported")
    need(int(os.environ["TEST_STAGE_B_COMPLETION_SUFFIX_N"])==len(parts["suffix"]),"outer fixed suffix N")
    need(plan["budget"]==dict(CPU_threads=1,GPU=0,RSS_bytes=8589934592,total_wall_seconds=15*len(parts["suffix"])+600,record_workers=1,cleanup_seconds=60),"fixed segment budget")
    need(not Path(plan["output_directory"]).exists(),"isolated new output")
    frozen_root=Path(suite["once_claim_root"]).parent
    need(plan["output_directory"]==str(frozen_root/"completion_segment_2"/"result") and plan["started_directory"]==str(frozen_root/"completion_segment_2"/"started"),"new fixed isolated completion output/journal")
    claimroot=Path(suite["once_claim_root"]);need(claimroot.resolve()==claimroot,"no claim root alias")
    claim=claimroot/"CONDITIONAL_COMPLETION_SEGMENT_2.json"
    need(plan["segment_claim_path"]==str(claim),"single persistent completion claim root")
    return suite,original,terminal,parts,claim

def transformed_run(source):
    tree=ast.parse(source);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="run")
    text=ast.get_source_segment(source,node)
    hook="        one = {name: {iid: data[name][iid]} if iid in data[name] else {} for name in ('public', 'gold', 'ledger', 'admissions', 'cache_input_ledger')}\n"
    need(text.count(hook)==1,"frozen materialization boundary")
    # Existing clock/start/deadlines stay BEFORE fsync; journal cost is inside10s.
    return text.replace(hook,'        completion_started(iid, record_started, record_deadline, preprocessing_deadline)\n'+hook,1)

def run(plan_item,release_item):
    plan=load(plan_item);release=load(release_item)
    need(release["schema"]=="TEST_STAGE_B_completion_once_release_v1" and release["plan_sha256"]==plan_item["sha256"] and release["entrypoint_sha256"]==sha(__file__) and release["execution_authorized"] is True,"exact completion release")
    review=load(release["independent_review"])
    for key,filename in (("completion","TEST_STAGE_B_completion.py"),("completion_supervisor","TEST_STAGE_B_completion_supervisor.py"),("completion_report","TEST_STAGE_B_completion_report.py")):
        need(review["source_sha256"][key]==sha(Path(__file__).with_name(filename)),"complete reviewed control closure")
    need(str(review["decision"]).startswith("PASS") and review["source_sha256"]["completion"]==sha(__file__),"completion source independent PASS")
    suite,original,terminal,parts,claim=validate(plan)
    write(claim,dict(schema="TEST_STAGE_B_completion_claim_v1",original_suite=plan["original_suite"],original_scoring_plan=plan["original_scoring_plan"],original_score_claim=plan["original_claim"],plan_sha256=plan_item["sha256"],release_sha256=release_item["sha256"],segment_index=2,no_retry=True,started_ns=time.time_ns()))
    # check_plan decodes all frozen tables. Declare each suffix input-read start
    # durably BEFORE that first decode; subsequent execution markers are distinct.
    journal=Path(plan["started_directory"]);need(not journal.exists(),"new started journal");journal.mkdir(parents=True)
    for iid in parts["suffix"]:write(journal/(iid+".read_started.json"),dict(input_id=iid,original_ordinal=original["input_ids"].index(iid),segment_plan_sha256=plan_item["sha256"],input_sha256={k:v["sha256"] for k,v in original["inputs"].items()},stage="input_binding_read_started",solver_started=False))
    caller_path=suite["implementations"]["locked_caller"]["path"];need(sha(caller_path)==CALLER_SHA,"frozen caller source")
    sys.path.insert(0,str(Path(caller_path).parent));caller=module(caller_path,"completion_frozen_caller")
    caller.OWNER_RELEASE=plan["original_delegate_release"]
    original_check=caller.check_plan
    def check(path,h):
        full,data,config,numeric,policy=original_check(path,h)
        namespace["REPO"]=caller.REPO
        need(full["input_ids"]==original["input_ids"],"full original queue bound")
        full=dict(full,input_ids=parts["suffix"],output_directory=plan["output_directory"])
        return full,data,config,numeric,policy
    def started(iid,start,deadline,preprocessing):write(journal/(iid+".execution_started.json"),dict(input_id=iid,original_ordinal=original["input_ids"].index(iid),segment_plan_sha256=plan_item["sha256"],input_sha256={k:v["sha256"] for k,v in original["inputs"].items()},stage="record_execution_started",record_started_at=start,record_deadline=deadline,preprocessing_deadline=preprocessing,started_ns=time.time_ns(),solver_started=False))
    namespace=dict(caller.__dict__,check_plan=check,completion_started=started)
    exec(compile(transformed_run(Path(caller_path).read_text()),caller_path,"exec"),namespace)
    namespace["run"](plan["original_scoring_plan"]["path"],plan["original_scoring_plan"]["sha256"])
    need(inventory(Path(original["output_directory"]))==load(plan["original_partial_inventory"])["output_sha256"],"postrun original partial unchanged")
    # Preserve segment receipt truth; never rewrite original manifest or exit.
    output=Path(plan["output_directory"])
    write(output/"completion_segment_receipt.json",dict(schema="TEST_STAGE_B_completion_segment_completed_v1",segment_index=2,original_terminal_receipt=plan["original_terminal_receipt"],original_outer_exit=terminal["actual_outer_exit"],suffix_count=len(parts["suffix"]),prefix_count=len(parts["prefix"]),boundary_unknown=parts["boundary"],original_C=3637,H_unavailable=1371,original_plan=plan["original_scoring_plan"],completion_plan=plan_item,source_run_transform="exact5485 run AST source + before-loop-body started call; isolated plan view only",raw_segment_manifest=dict(path=str(output/"manifest.json"),sha256=sha(output/"manifest.json")),segment_public_unavailable_field_is_local_count_not_global=True,no_retry=True))
def main():
    p=argparse.ArgumentParser();p.add_argument("--plan");p.add_argument("--plan-sha256");p.add_argument("--release");p.add_argument("--release-sha256");p.add_argument("--execute",action="store_true");a=p.parse_args()
    if not a.execute:print(json.dumps(dict(schema="TEST_STAGE_B_completion_interface_v1",actual_execution_authorized=False,terminal_and_suffix="pending",budget="15*N_suffix+600; per-record original10s/cap50000",retry=False)));return
    need(os.environ.get("TEST_STAGE_B_COMPLETION_OUTER_PID")==str(os.getppid()),"supervised completion only")
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
for _name in ('need', 'sha', 'load', 'write', 'module', 'partition', 'touched_ids', 'recoverable_next', 'inventory', 'same_item', 'validate_terminal', 'validate', 'transformed_run', 'run', 'main'):globals()[_name]=_public_guard(globals()[_name])
if __name__=="__main__":main()
