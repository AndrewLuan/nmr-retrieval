"""功能概述：用匿名 JSON 单记录 worker 执行共享预算的 B0/B1/B2，不加载模型或 gold。
主要职责：execute_record 在 decode 前限制输入字节，以 watchdog 的独占进程组覆盖启动、
导入、解析、结构 parent 诊断、候选生成、两个 solver 阶段和最终验证。numeric_config_from_frozen
只抽取冻结数值；worker 要求 payload 配置与调用方批准快照完全相等，不接受记录名等特征。
预处理也由独占 PID 子进程强制限定共享 2s（含 SciPy 导入和候选输出编码）。
_run_stage 的子预处理/solver 不创建 session，阶段超时只 kill 自建 PID 并 communicate 回收；外层
record 进程组仍包含该后代。B1/B2 各只构建一次候选、求解一次（含 Top3/margins），不重试。
代码库关系：复用 watchdog、mapping、costs、solver、baselines；不修改它们。结构 parent
诊断只保留 canonical parent mass 和完整 attachment blocks，不冒充 source atom 身份认证。
输入输出与副作用：严格字段重建 FrozenCapacityPredictions；10MiB 上限在无界 JSON decode
前执行。输入只含匿名观测、冻结结构预测、数值配置、结构 exchangeable IDs 和实际 window。
未知 window 不从观测范围猜测；κ 在普通/交换或全部 carrier 区间出窗之间按冻结规则选取。
输出保留各 BaselineResult 的 best/top-k/margins/attempts 和分开的 examined/emitted 计数。
所有子进程均有 finally 有界 kill/communicate/closepipes/reap 清理（.25s grace），避免后代持管无限等待；
正常输出附完整 candidate membership/costs/generation_complete，不为诊断重跑；失败保留记录状态，不认证超时结果。仅 POSIX，无训练、网络、
真实数据读写或持久缓存。python -m nmr_assignment.execution 是纯 JSON stdin/stdout 入口。
"""
import argparse
from dataclasses import asdict, fields
import json
import hashlib
from pathlib import Path
from math import fsum, isfinite
import os
import re
import subprocess
import sys
from time import monotonic

# 已批准的 serialized record 工程上限；实际冻结配置必须与此值一致。
MAX_INPUT_BYTES=10485760
BUDGET_KEYS=("per_record_wall_seconds","mapping_and_candidates_seconds","B1_solver_seconds",
             "B2_solver_seconds","result_validation_reserve_seconds","max_candidates_per_global_problem",
             "top_k","compute_margins","input_bytes_limit")
COST_KEYS=("B0_B1_reference_scale_ppm","B2_cost_convention","B2_gate_mode","B2_member_gate_multiplier",
           "B2_pair_span_error_scale_multiplier","B2_delta","B2_merge_cost","smin_ppm","integral_policy",
           "missing_kappa_ordinary","missing_kappa_reduced_reporting","B1_unexplained","B2_unexplained",
           "max_units_per_observation")


def _strict(data,keys):
    if not isinstance(data,dict) or set(data)!=set(keys):
        raise ValueError("JSON fields do not match anonymous contract")
    return data


def _pairs(items):
    result={}
    for key,value in items:
        if key in result: raise ValueError("duplicate JSON field")
        result[key]=value
    return result


def _reject(value):
    raise ValueError("nonfinite JSON literal")


def _decode(raw):
    if not isinstance(raw,bytes) or len(raw)>MAX_INPUT_BYTES:
        raise ValueError("unsupported_input_budget")
    return json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs,parse_constant=_reject)


def _positive(value):
    if type(value) not in (int,float) or not isfinite(value) or value<=0:
        raise ValueError("finite positive budget/scale required")
    return float(value)


def numeric_config_from_frozen(config):
    costs={k:config["machine_cost_contract"][k] for k in COST_KEYS}
    budgets={k:config["computation_budget"][k] for k in BUDGET_KEYS}
    result=dict(costs=costs,budgets=budgets,
                tie_relative_tolerance=config["machine_cost_contract"]["tie_relative_tolerance"])
    _validate_config(result)
    return result


def _validate_config(config):
    _strict(config,("costs","budgets","tie_relative_tolerance"))
    c,b=config["costs"],config["budgets"]
    _strict(c,COST_KEYS); _strict(b,BUDGET_KEYS)
    for key in ("B0_B1_reference_scale_ppm","smin_ppm"):
        _strict(c[key],("1H","13C"))
        for value in c[key].values(): _positive(value)
    for key in ("B2_member_gate_multiplier","B2_pair_span_error_scale_multiplier","B2_delta","B2_merge_cost"):
        _positive(c[key])
    for key in ("missing_kappa_ordinary","missing_kappa_reduced_reporting","B1_unexplained","B2_unexplained"):
        if type(c[key]) not in (int,float) or not isfinite(c[key]) or c[key]<0:
            raise ValueError("nonnegative explicit potential required")
    if (c["B2_cost_convention"]!="reduced_scale_normalizer" or c["B2_gate_mode"]!="standardized" or
            c["integral_policy"]!="disabled_both_nuclei_first_round" or c["max_units_per_observation"]!=2):
        raise ValueError("only approved reduced first-round cost convention supported")
    for key in BUDGET_KEYS[:5]: _positive(b[key])
    if b["input_bytes_limit"]!=MAX_INPUT_BYTES or type(b["max_candidates_per_global_problem"]) is not int or b["max_candidates_per_global_problem"]<0:
        raise ValueError("explicit input/candidate cap required")
    if type(b["top_k"]) is not int or not 1<=b["top_k"]<=3 or type(b["compute_margins"]) is not bool:
        raise ValueError("explicit raw Top3/margins policy required")
    _positive(config["tie_relative_tolerance"])


def _predictions(data):
    from .mapping import CapacityUnit,CapacityLayout,FrozenCarrier,FrozenCapacityPredictions
    def checked(cls,value): return dict(_strict(value,tuple(f.name for f in fields(cls))))
    p=checked(FrozenCapacityPredictions,data)
    layout=checked(CapacityLayout,p["layout"])
    units=[]
    for value in layout["units"]:
        u=checked(CapacityUnit,value)
        u["parent_mass"]=tuple(tuple(v) for v in u["parent_mass"])
        u["evidence_ids"]=tuple(u["evidence_ids"])
        units.append(CapacityUnit(**u))
    layout["units"]=tuple(units)
    layout["parent_mass_totals"]=tuple(tuple(v) for v in layout["parent_mass_totals"])
    p["layout"]=CapacityLayout(**layout)
    carriers=[]
    for value in p["carriers"]:
        c=checked(FrozenCarrier,value)
        c["source_component_ids"]=tuple(c["source_component_ids"])
        carriers.append(FrozenCarrier(**c))
    p["carriers"]=tuple(carriers)
    p["attachment_blocks"]=tuple(tuple(v) for v in p["attachment_blocks"])
    p["attachment_evidence_ids"]=tuple(p["attachment_evidence_ids"])
    return FrozenCapacityPredictions(**p)


def _payload(raw,approved):
    from .costs import Observation
    value=_decode(raw)
    _strict(value,("observations","predictions","exchangeable_unit_ids","actual_window","numeric_config"))
    _validate_config(value["numeric_config"])
    if value["numeric_config"]!=approved:
        raise ValueError("payload numeric config differs from approved snapshot")
    obs=tuple(Observation(**_strict(o,("observation_id","ppm"))) for o in value["observations"])
    if len({o.observation_id for o in obs})!=len(obs): raise ValueError("duplicate observation ID")
    if any(re.fullmatch(r"(?:p|bin:|obs:)\d+",o.observation_id) is None for o in obs):
        raise ValueError("observation IDs must be anonymous pN/bin:N/obs:N")
    pred=_predictions(value["predictions"])
    exchange=value["exchangeable_unit_ids"]
    if not isinstance(exchange,list) or any(type(x) is not str for x in exchange) or len(set(exchange))!=len(exchange):
        raise ValueError("exchangeable IDs must be a distinct structural unit list")
    ids={u.unit_id for u in pred.layout.units}
    if set(exchange)-ids: raise ValueError("unknown exchangeable unit")
    window=value["actual_window"]
    if window is not None:
        _strict(window,("lower_ppm","upper_ppm"))
        if any(type(v) not in (float,int) or not isfinite(v) for v in window.values()) or window["lower_ppm"]>=window["upper_ppm"]:
            raise ValueError("actual window requires increasing finite ppm bounds")
    return obs,pred,set(exchange),window


def _as_text(value):
    return value.decode("utf-8",errors="replace") if isinstance(value,bytes) else (value or "")


def _bounded_cleanup(process):
    """Kill/reap only our Popen PID; inherited pipe holders cannot block cleanup."""
    if process.poll() is None:
        try: process.kill()
        except ProcessLookupError: pass
    out=err=""
    try:
        out,err=process.communicate(timeout=.25)
    except subprocess.TimeoutExpired as exc:
        out,err=_as_text(exc.output),_as_text(exc.stderr)
        for pipe in (process.stdin,process.stdout,process.stderr):
            if pipe is not None:
                try: pipe.close()
                except OSError: pass
        try: process.wait(timeout=.25)
        except subprocess.TimeoutExpired: pass
    return out,err,process.poll() is not None


def _run_stage(request,*,timeout_seconds,argv=None,raw_input=None):
    """Own exactly one child PID in the record group; bounded cleanup, no retry."""
    started=monotonic()
    process=None; cleaned=False
    try:
        if timeout_seconds<=0:
            return dict(status="stage_timeout",result=None,process_reaped=True,child_pid=None,stdout="",stderr="")
        text=raw_input.decode("utf-8") if raw_input is not None else json.dumps(request,allow_nan=False,separators=(",",":"))
        if len(text.encode())>MAX_INPUT_BYTES:
            return dict(status="unsupported_stage_input_budget",result=None,process_reaped=True,child_pid=None,stdout="",stderr="")
        process=subprocess.Popen(argv or [sys.executable,"-m","nmr_assignment.execution","--solver"],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=False)
        try:
            out,err=process.communicate(text,timeout=max(0.,timeout_seconds-(monotonic()-started)))
            cleaned=True
            expired=monotonic()-started>=timeout_seconds
            reaped=process.poll() is not None
        except subprocess.TimeoutExpired as exc:
            expired=True
            out,err,reaped=_bounded_cleanup(process)
            cleaned=True
            out=out or _as_text(exc.output); err=err or _as_text(exc.stderr)
        if expired:
            return dict(status="stage_timeout",result=None,process_reaped=reaped,child_pid=process.pid,stdout=out,stderr=err)
        if process.returncode!=0:
            return dict(status="solver_worker_error",result=None,process_reaped=reaped,child_pid=process.pid,stdout=out,stderr=err)
        decoded=json.loads(out)
        if monotonic()-started>=timeout_seconds:
            return dict(status="stage_timeout",result=None,process_reaped=reaped,child_pid=process.pid,stdout=out,stderr=err)
        return dict(status="completed",result=decoded,process_reaped=reaped,child_pid=process.pid,stdout="",stderr=err)
    finally:
        if process is not None and not cleaned:
            _bounded_cleanup(process)


def _solver_worker(raw):
    value=_decode(raw)
    _strict(value,("observation_ids","unit_ids","candidates","missing_costs","unexplained_costs","top_k","compute_margins","time_limit"))
    from .solver import Candidate,solve_assignment
    candidates=tuple(Candidate(c["observation_id"],tuple(c["environment_ids"]),c["cost"])
        for c in (_strict(v,("observation_id","environment_ids","cost")) for v in value["candidates"]))
    result=solve_assignment(value["observation_ids"],value["unit_ids"],candidates,
        value["missing_costs"],value["unexplained_costs"],top_k=value["top_k"],
        compute_margins=value["compute_margins"],time_limit=value["time_limit"])
    result=asdict(result)
    result["execution_problem_sha256"]=canonical_digest(value)
    return result


def _raw_result(value):
    # Standardlib-only reconstruction: coordinator must not import SciPy outside
    # the preprocessing/solver child watchdogs. The original JSON stays unchanged.
    from types import SimpleNamespace
    def solution(data):
        if data is None: return None
        data=dict(_strict(data,("objective","assignments","unobserved","unexplained","certified")))
        data["assignments"]={k:tuple(v) for k,v in data["assignments"].items()}
        return SimpleNamespace(**data)
    data=dict(_strict(value,("best","alternatives","status","optimal","timed_out","top_k_certified",
        "exhausted","margins","attempts","identification_quotient")))
    data["best"]=solution(data["best"])
    data["alternatives"]=tuple(solution(v) for v in data["alternatives"])
    data["margins"]={k:SimpleNamespace(**_strict(v,("value","status","certified","alternative_objective")))
                     for k,v in data["margins"].items()}
    data["attempts"]=tuple(SimpleNamespace(**_strict(a,("purpose","status","raw_status","message",
        "optimal","timed_out","objective","mip_gap","dual_bound"))) for a in data["attempts"])
    return SimpleNamespace(**data)


def _validate_solutions(raw,request,tolerance):
    choices={(v["observation_id"],tuple(v["environment_ids"])):v["cost"] for v in request["candidates"]}
    units=set(request["unit_ids"]); obs=set(request["observation_ids"])
    for solution in (raw.best,)+raw.alternatives:
        if solution is None: continue
        if set(solution.assignments)!=obs: raise ValueError("worker solution observation coverage mismatch")
        used=[]; terms=[]
        for oid,members in solution.assignments.items():
            if members:
                if (oid,members) not in choices: raise ValueError("worker solution has unknown candidate")
                terms.append(choices[oid,members]); used.extend(members)
            else: terms.append(request["unexplained_costs"][oid])
        if len(used)!=len(set(used)) or set(solution.unobserved)!=units-set(used):
            raise ValueError("worker solution violates capacity exact cover")
        if set(solution.unexplained)!={oid for oid,members in solution.assignments.items() if not members}:
            raise ValueError("worker unexplained set mismatch")
        terms.extend(request["missing_costs"][uid] for uid in solution.unobserved)
        total=fsum(terms)
        if not isfinite(solution.objective) or abs(total-solution.objective)>tolerance*max(1.,abs(total),abs(solution.objective)):
            raise ValueError("worker objective mismatch")


def _prepare_record(raw,approved,*,started,total_deadline,pre_deadline):
    if monotonic()>=pre_deadline: return dict(status="preprocessing_timeout",methods={})
    # Import and payload reconstruction belong to the preprocessing allowance.
    from .costs import local_nearest,build_b1,build_b2,parameters_from_frozen_config,GenerationLimit
    from .baselines import BaselineResult,LocalDecision
    obs,pred,exchange,window=_payload(raw,approved)
    c,b=approved["costs"],approved["budgets"]
    tau=approved["tie_relative_tolerance"]
    if monotonic()>=pre_deadline: return dict(status="preprocessing_timeout",methods={})
    nucleus=pred.layout.nucleus
    fakeconfig={"machine_cost_contract":c}
    params={method:parameters_from_frozen_config(fakeconfig,method=method,nucleus=nucleus,
              normalizer_convention="reduced") for method in ("B0","B1","B2")}
    # Structural parent/attachment diagnostic only. No source identity proof is invented.
    structural=dict(unit_parent_mass=[dict(unit_id=u.unit_id,parent_mass=u.parent_mass) for u in pred.layout.units],
                    attachment_blocks=pred.attachment_blocks,status="canonical_structure_only_source_identity_unverified")
    grouped={u.unit_id:[] for u in pred.layout.units}
    for carrier in pred.carriers: grouped[carrier.unit_id].append(carrier)
    kappa={}
    for uid,carriers in grouped.items():
        if monotonic()>=pre_deadline: return dict(status="preprocessing_timeout",methods={})
        outside=False
        if window is not None and all(r.sigma_ppm is not None for r in carriers):
            intervals=[(r.center_ppm-c["B2_member_gate_multiplier"]*max(r.sigma_ppm,c["smin_ppm"][nucleus]),
                        r.center_ppm+c["B2_member_gate_multiplier"]*max(r.sigma_ppm,c["smin_ppm"][nucleus])) for r in carriers]
            outside=all(upper<window["lower_ppm"] or lower>window["upper_ppm"] for lower,upper in intervals)
        kappa[uid]=c["missing_kappa_reduced_reporting"] if uid in exchange or outside else c["missing_kappa_ordinary"]
    methods={}; candidates={}
    def incomplete(status,**facts):
        for method in ("B0","B1","B2"):
            methods.setdefault(method,dict(method=method,status=status,certified=False,
                timed_out=status in ("preprocessing_timeout","total_deadline"),solver_result=None))
        return dict(status=status,methods=methods,**facts)
    try:
        local=local_nearest(obs,pred,**params["B0"],tie_relative_tolerance=tau,
            max_candidates=b["max_candidates_per_global_problem"],deadline=pre_deadline)
        decisions=tuple(LocalDecision(row.observation_id,row.local_top3,len(row.minimum_unit_ids)==1,
            "complete_cutoff_tie_blocks",row.minimum_unit_ids,row.rank_bounds,row.tie_blocks) for row in local)
        methods["B0"]=asdict(BaselineResult("B0","local_complete",True,False,decisions,None,
            local.emitted_count,0,monotonic()-started,"complete local tie blocks","none","independent_local",
            "fixed_distance",(),"not_applicable","unsupported",local.examined_count))
        for method,build in (("B1",build_b1),("B2",build_b2)):
            try:
                candidates[method]=build(obs,pred,**params[method],max_candidates=b["max_candidates_per_global_problem"],deadline=pre_deadline)
            except ValueError as exc:
                if method!="B2": raise
                methods[method]=dict(method=method,status="unsupported_prediction",certified=False,
                    timed_out=False,solver_result=None,detail=str(exc))
    except GenerationLimit as exc:
        return incomplete("preprocessing_timeout" if monotonic()>=pre_deadline else "candidate_budget",
                    examined_count=exc.examined_count,emitted_count=exc.emitted_count)
    if monotonic()>=pre_deadline: return incomplete("preprocessing_timeout")
    return dict(status="prepared",methods=methods,observation_ids=[o.observation_id for o in obs],
        unit_ids=list(grouped),relative_missing_costs=kappa,structural_parent_projection=structural,
        candidates={method:dict(values=[asdict(v) for v in values],examined_count=values.examined_count,
                    emitted_count=values.emitted_count) for method,values in candidates.items()})


def _candidate_diagnostics(candidates,methods,requests=None):
    result={method:dict(generation_complete=True,candidates=graph["values"],
        examined_count=graph["examined_count"],emitted_count=graph["emitted_count"])
        for method,graph in candidates.items()}
    for method,request in (requests or {}).items():
        result[method]["solver_request_parameters"]={k:v for k,v in request.items() if k!="candidates"}
        result[method]["solver_request_sha256"]=canonical_digest(request)
    for method in ("B1","B2"):
        result.setdefault(method,dict(generation_complete=False,reason=methods.get(method,{}).get("status","unavailable")))
    if result["B1"]["generation_complete"]:
        result["B0"]=dict(generation_complete=True,shared_candidate_graph="B1",
            reason="same explicit normalized singleton distances; no gate or dummy")
    return result


def _worker_record(raw,approved,*,started,total_deadline,pre_deadline):
    if monotonic()>=pre_deadline: return dict(status="preprocessing_timeout",methods={})
    # Hard stage cap includes Python/SciPy imports and all candidate serialization.
    prep_argv=[sys.executable,"-m","nmr_assignment.execution","--prepare","--started",str(started),
        "--total-deadline",str(total_deadline),"--pre-deadline",str(pre_deadline),
        "--approved-config",json.dumps(approved,allow_nan=False,separators=(",",":"))]
    prep_stage=_run_stage(None,timeout_seconds=max(0.,pre_deadline-monotonic()),argv=prep_argv,raw_input=raw)
    if prep_stage["status"]!="completed":
        return dict(status="preprocessing_timeout" if prep_stage["status"]=="stage_timeout" else prep_stage["status"],
            methods={method:dict(method=method,status="preprocessing_unavailable",certified=False,
                      timed_out=prep_stage["status"]=="stage_timeout",solver_result=None) for method in ("B0","B1","B2")},
            preprocessing_audit={k:v for k,v in prep_stage.items() if k!="result"})
    prepared=prep_stage["result"]
    if prepared["status"]!="prepared":
        for method in ("B0","B1","B2"):
            prepared.setdefault("methods",{}).setdefault(method,dict(method=method,status=prepared["status"],
                certified=False,timed_out=prepared["status"]=="preprocessing_timeout",solver_result=None))
        return prepared
    methods=prepared["methods"]; candidates=prepared["candidates"]
    obs_ids,unit_ids=prepared["observation_ids"],prepared["unit_ids"]
    kappa=prepared["relative_missing_costs"]; structural=prepared["structural_parent_projection"]
    c,b=approved["costs"],approved["budgets"]; tau=approved["tie_relative_tolerance"]
    stage_audit={}; requests={}
    for method in ("B1","B2"):
        if method not in candidates: continue
        count=len(candidates[method]["values"]); variables=count+len(obs_ids)+len(unit_ids)
        if variables>b["max_candidates_per_global_problem"]+len(obs_ids)+len(unit_ids):
            return dict(status="matrix_budget",methods=methods)
        stage_started=monotonic()
        stage_deadline=min(stage_started+b[method+"_solver_seconds"],total_deadline-b["result_validation_reserve_seconds"])
        remaining=stage_deadline-stage_started
        if remaining<=0:
            methods[method]=dict(method=method,status="total_deadline",certified=False,timed_out=True)
            continue
        request=dict(observation_ids=obs_ids,unit_ids=unit_ids,
            candidates=candidates[method]["values"],missing_costs=kappa,
            unexplained_costs={oid:c[method+"_unexplained"] for oid in obs_ids},
            top_k=b["top_k"],compute_margins=b["compute_margins"],time_limit=remaining)
        requests[method]=request
        stage=_run_stage(request,timeout_seconds=max(0.,stage_deadline-monotonic()))
        stage_audit[method]={k:v for k,v in stage.items() if k!="result"}
        if stage["status"]!="completed":
            methods[method]=dict(method=method,status=stage["status"],certified=False,
                timed_out=stage["status"]=="stage_timeout",candidate_count=count,
                examined_count=candidates[method]["examined_count"],solver_result=None)
            continue
        backend=dict(stage["result"])
        if backend.pop("execution_problem_sha256",None)!=canonical_digest(request):
            methods[method]=dict(method=method,status="backend_problem_binding_missing",certified=False,
                timed_out=False,solver_result=None)
            continue
        raw_result=_raw_result(backend)
        _validate_solutions(raw_result,request,tau)
        expired=monotonic()>=total_deadline
        determinate=[]
        for oid in request["observation_ids"]:
            margin=raw_result.margins.get(oid)
            if expired or not raw_result.optimal or raw_result.best is None or margin is None or not margin.certified:
                state="abstain_uncertified"
            elif margin.value is None or margin.alternative_objective is None:
                state="abstain_no_numeric_alternative"
            else:
                bound=tau*max(1.,abs(raw_result.best.objective),abs(margin.alternative_objective))
                state="abstain_tie" if margin.value<=bound else "certified_separated_uncalibrated"
            determinate.append((oid,state))
        methods[method]=dict(method=method,status="total_deadline" if expired else raw_result.status,
            certified=raw_result.optimal and not expired,timed_out=expired or raw_result.timed_out,
            local=[],solver_result=backend,backend_problem_sha256=canonical_digest(request),candidate_count=count,variable_count=variables,
            elapsed_seconds=monotonic()-started,detail="shared record allowance; raw Top3 diagnostic",
            identification_quotient="none",reuse_semantics="global_exclusive",
            cost_convention="reduced" if method=="B2" else "fixed_distance",
            per_observation_status=determinate,
            global_top3_boundary="space_exhausted" if raw_result.exhausted else "cutoff_unverified",
            chemical_top3="unsupported",examined_count=candidates[method]["examined_count"])
    expired=monotonic()>=total_deadline
    if expired:
        for method in methods.values():
            method["certified"]=False; method["timed_out"]=True
    return dict(status="total_deadline" if expired else "completed",methods=methods,
                structural_parent_projection=structural,relative_missing_costs=kappa,stage_audit=stage_audit,
                preprocessing_audit={k:v for k,v in prep_stage.items() if k!="result"},
                candidate_diagnostics=_candidate_diagnostics(candidates,methods,requests),
                elapsed_seconds=monotonic()-started)


def canonical_digest(value):
    """Execution JSON digest: sorted keys, compact UTF-8, finite numbers only.

    Use JSON-native objects with string keys (asdict tuples serialize as arrays).
    Do not coerce floats to ints or stringify integer keys after hashing. Exact
    input byte SHA is additionally bound; retain the submitted bytes unchanged.
    """
    """Common plain-JSON digest, matching the evaluation adapter contract."""
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _implementation_hashes():
    root=Path(__file__).resolve().parent
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest()
            for name in ("execution.py","solver.py","costs.py","mapping.py","diagnostics.py")}


def _input_binding(raw,approved,input_id,prediction_artifact_sha256):
    value=_decode(raw)
    if value["numeric_config"]!=approved: raise ValueError("approved numeric snapshot mismatch")
    return dict(input_id=input_id,prediction_artifact_sha256=prediction_artifact_sha256,
        raw_input_sha256=hashlib.sha256(raw).hexdigest(),input_payload_sha256=canonical_digest(value),
        observations_sha256=canonical_digest(value["observations"]),
        predictions_sha256=canonical_digest(value["predictions"]),numeric_config_sha256=canonical_digest(approved))


def _execution_trace(body,method,value):
    """Rebuild the exact emitted problem without regenerating any candidate."""
    source="B1" if method=="B0" else method
    graph=body.get("candidate_diagnostics",{}).get(source,{})
    if graph.get("generation_complete") is not True: raise ValueError("candidate generation incomplete")
    candidates=graph["candidates"]
    if graph["emitted_count"]!=len(candidates): raise ValueError("candidate count mismatch")
    obs=[o["observation_id"] for o in value["observations"]]
    units=[u["unit_id"] for u in value["predictions"]["layout"]["units"]]
    missing={} if method=="B0" else body["relative_missing_costs"]
    unexplained={} if method=="B0" else {o:value["numeric_config"]["costs"][method+"_unexplained"] for o in obs}
    controls={}
    request_sha=None
    if method!="B0":
        params=graph["solver_request_parameters"]
        request=dict(params,candidates=candidates)
        request_sha=canonical_digest(request)
        if graph["solver_request_sha256"]!=request_sha: raise ValueError("solver request SHA mismatch")
        if (params["observation_ids"]!=obs or params["unit_ids"]!=units
                or params["missing_costs"]!=missing or params["unexplained_costs"]!=unexplained):
            raise ValueError("solver request input/domain/dummy mismatch")
        controls={k:params[k] for k in ("top_k","compute_margins","time_limit")}
        budgets=value["numeric_config"]["budgets"]
        if (controls["top_k"]!=budgets["top_k"] or controls["compute_margins"]!=budgets["compute_margins"]
                or not 0<_positive(controls["time_limit"])<=budgets[method+"_solver_seconds"]):
            raise ValueError("solver controls differ from frozen config")
        if body["methods"][method].get("backend_problem_sha256")!=request_sha:
            raise ValueError("backend problem receipt missing or mismatched")
    return dict(method=method,observation_ids=obs,unit_ids=units,candidates=candidates,
        missing_costs=missing,unexplained_costs=unexplained,
        cost_convention="reduced" if method=="B2" else "fixed_distance",
        solver_controls=controls,solver_request_sha256=request_sha)


def _make_execution_receipt(raw,approved,envelope,*,input_id,prediction_artifact_sha256):
    """Actual execute_record producer only; integrity receipt, not a new MILP proof."""
    value=_decode(raw); body=envelope["result"]
    proofs={}
    for method, result in body.get("methods",{}).items():
        if result.get("certified") is not True or result.get("timed_out") is not False: continue
        try: trace=_execution_trace(body,method,value)
        except (KeyError,ValueError,TypeError): continue
        proofs[method]=dict(candidate_trace_sha256=canonical_digest(trace),
            method_result_sha256=canonical_digest(result))
    payload=dict(schema="actual_assignment_execution_receipt_v1",
        producer="nmr_assignment.execution.execute_record",proof_scope="observed_backend_status_not_independent_MILP_proof",
        input_binding=_input_binding(raw,approved,input_id,prediction_artifact_sha256),
        implementation_sha256=_implementation_hashes(),methods=proofs,
        result_body_sha256=canonical_digest(body),
        outer_state={k:envelope.get(k) for k in ("status","timed_out","process_reaped","exit_code")})
    return dict(payload=payload,sha256=canonical_digest(payload))


def _baseline_object(value):
    from types import SimpleNamespace
    result=SimpleNamespace(**value)
    result.solver_result=_raw_result(value["solver_result"])
    return result


def verify_execution_method(envelope,raw_payload,*,approved_numeric_config,input_id,
                            prediction_artifact_sha256,method,binding,budget=None):
    """Common postprocessing bridge for metrics and diagnostics; never solve.

    The actual driver produced the JSON receipt. Requiring that receipt avoids
    upgrading free-standing certified flags; hashes defend accidental cross-wiring,
    not a malicious actor who fabricates an entire run history.
    """
    from dataclasses import replace
    from .diagnostics import (DiagnosticBudget,DiagnosticLimit,CandidateTrace,TraceCandidate,
        PayloadReceipt,SolverResultCertificate,payload_digest,result_snapshot_digest,verify_solver_result)
    b=DiagnosticBudget() if budget is None else budget
    try:
        b.step()
        if method not in ("B0","B1","B2"): raise ValueError("unknown method")
        if not isinstance(raw_payload,bytes): raise ValueError("exact execution raw bytes required")
        receipt=envelope.get("execution_receipt") or {}
        proof=receipt.get("payload")
        if not isinstance(proof,dict) or receipt.get("sha256")!=canonical_digest(proof):
            raise ValueError("execution receipt missing or mismatched")
        if (proof.get("schema")!="actual_assignment_execution_receipt_v1"
                or proof.get("producer")!="nmr_assignment.execution.execute_record"
                or proof.get("implementation_sha256")!=_implementation_hashes()):
            raise ValueError("unapproved execution producer implementation")
        expected=_input_binding(raw_payload,approved_numeric_config,input_id,prediction_artifact_sha256)
        if proof.get("input_binding")!=expected: raise ValueError("execution input binding mismatch")
        if envelope.get("input_id")!=input_id or envelope.get("prediction_artifact_sha256")!=prediction_artifact_sha256:
            raise ValueError("execution envelope identity mismatch")
        outer={k:envelope.get(k) for k in ("status","timed_out","process_reaped","exit_code")}
        if (proof.get("outer_state")!=outer or outer!={"status":"completed","timed_out":False,"process_reaped":True,"exit_code":0}):
            raise ValueError("execution outer completion not certified")
        body=envelope["result"]
        if body.get("status")!="completed" or proof.get("result_body_sha256")!=canonical_digest(body):
            raise ValueError("execution result body mismatch")
        value=_decode(raw_payload)
        trace_data=_execution_trace(body,method,value)
        method_result=body["methods"][method]
        expected_method=dict(candidate_trace_sha256=canonical_digest(trace_data),method_result_sha256=canonical_digest(method_result))
        if proof["methods"].get(method)!=expected_method: raise ValueError("execution method trace/result mismatch")
        if envelope.get("candidate_trace_sha256",expected_method["candidate_trace_sha256"])!=expected_method["candidate_trace_sha256"]:
            raise ValueError("foreign envelope candidate trace")
        # DiagnosticBinding config/prediction hashes identify the SAME execution inputs.
        if (binding.prediction_sha256!=prediction_artifact_sha256 or
                binding.config_sha256!=expected["numeric_config_sha256"]):
            raise ValueError("diagnostic binding differs from execution input")
        b.step(len(trace_data["candidates"]))
        if method=="B0":
            # B0 shares complete B1 singleton distances. Recompute the local tie
            # partition from the emitted graph, not from self-reported best_unique.
            costs={}
            for c in trace_data["candidates"]:
                members=tuple(c["environment_ids"])
                if len(members)!=1 or c["observation_id"] not in trace_data["observation_ids"] or members[0] not in trace_data["unit_ids"]:
                    raise ValueError("invalid B0 singleton graph")
                key=(c["observation_id"],members[0])
                if key in costs or not isfinite(c["cost"]): raise ValueError("duplicate/nonfinite B0 candidate")
                costs[key]=c["cost"]
            if len(costs)!=len(trace_data["observation_ids"])*len(trace_data["unit_ids"]):
                raise ValueError("B0 singleton graph incomplete")
            assignment={}; blocks={}; determinate={}
            locals_by_id={r["observation_id"]:r for r in method_result.get("local",())}
            if len(locals_by_id)!=len(method_result.get("local",())) or set(locals_by_id)!=set(trace_data["observation_ids"]):
                raise ValueError("B0 local domain mismatch")
            tolerance=approved_numeric_config["tie_relative_tolerance"]
            for oid in trace_data["observation_ids"]:
                ranked=sorted(((u,costs[oid,u]) for u in trace_data["unit_ids"]),key=lambda x:(x[1],x[0]))
                partitions=[]
                for item in ranked:
                    if not partitions or item[1]-partitions[-1][0][1]>tolerance*max(1.,abs(item[1]),abs(partitions[-1][0][1])):
                        partitions.append([])
                    partitions[-1].append(item)
                block=tuple(u for u,_ in partitions[0]) if partitions else ()
                local=locals_by_id[oid]
                if (tuple(local.get("minimum_unit_ids",()))!=block or
                    tuple(tuple(p) for p in local.get("tie_blocks",()))!=tuple(tuple(u for u,_ in p) for p in partitions)
                    or local.get("best_unique")!=(len(block)==1)):
                    raise ValueError("B0 reported tie block inconsistent with graph")
                assignment[oid]=(block[0],) if block else ()
                blocks[oid]=block; determinate[oid]=len(block)==1
            b.step()
            return dict(status="complete",certified=True,assignments=assignment,
                observation_determinate=determinate,observation_alternatives=blocks,
                observation_alternatives_complete={o:True for o in assignment},margin_scores={},
                method_result=method_result,execution_receipt_sha256=receipt["sha256"],
                source_candidate_trace_sha256=expected_method["candidate_trace_sha256"],
                tie_relative_tolerance=approved_numeric_config["tie_relative_tolerance"])
        trace=CandidateTrace(method,tuple(trace_data["observation_ids"]),tuple(trace_data["unit_ids"]),
            tuple(TraceCandidate(c["observation_id"],tuple(c["environment_ids"]),c["cost"]) for c in trace_data["candidates"]),
            tuple(sorted(trace_data["missing_costs"].items())),tuple(sorted(trace_data["unexplained_costs"].items())),trace_data["cost_convention"])
        # This bridge binds reference metadata only AFTER the actual label-free
        # execution receipt was checked. It cannot issue a free-standing run proof.
        trace=replace(trace,receipt=PayloadReceipt(True,payload_digest(trace.payload(binding)),("execution:"+receipt["sha256"],)))
        obj=_baseline_object(method_result)
        certificate=SolverResultCertificate(trace.receipt.payload_sha256,result_snapshot_digest(obj,budget=b),
            approved_numeric_config["tie_relative_tolerance"],0.,proof["implementation_sha256"]["solver.py"],receipt["sha256"])
        certificate=replace(certificate,receipt=PayloadReceipt(True,payload_digest(certificate.payload(binding)),
            ("actual-execution:"+receipt["sha256"],"candidate-trace:"+expected_method["candidate_trace_sha256"])))
        verified=verify_solver_result(obj,trace,certificate,binding=binding,budget=b)
        if verified["status"]!="complete": return verified
        verified.update(method_result=method_result,trace=trace,result_certificate=certificate,result_object=obj,
            source_candidate_trace_sha256=expected_method["candidate_trace_sha256"],
            tie_relative_tolerance=approved_numeric_config["tie_relative_tolerance"])
        return verified
    except (ValueError,KeyError,TypeError,AttributeError,DiagnosticLimit) as exc:
        return dict(status="unknown",certified=False,reason_codes=("execution_verification:"+str(exc),))


def execute_record(raw_payload,*,approved_numeric_config,input_id=None,prediction_artifact_sha256=None,
                   record_started_at=None,record_deadline=None,preprocessing_deadline=None):
    """Use caller-started record timing; inherited deadlines may only tighten budgets."""
    entered=monotonic()
    started=entered if record_started_at is None else float(record_started_at)
    if not isfinite(started) or started>entered:
        raise ValueError("record start cannot be future or nonfinite")
    _validate_config(approved_numeric_config)
    if not isinstance(raw_payload,bytes) or len(raw_payload)>MAX_INPUT_BYTES:
        return dict(status="unsupported_input_budget",result=None,process_reaped=True)
    b=approved_numeric_config["budgets"]
    maximum_total=started+b["per_record_wall_seconds"]
    total_deadline=maximum_total if record_deadline is None else float(record_deadline)
    if not isfinite(total_deadline) or total_deadline>maximum_total:
        raise ValueError("record deadline cannot relax frozen budget")
    maximum_pre=min(started+b["mapping_and_candidates_seconds"],total_deadline-b["result_validation_reserve_seconds"])
    pre_deadline=maximum_pre if preprocessing_deadline is None else float(preprocessing_deadline)
    if not isfinite(pre_deadline) or pre_deadline>maximum_pre:
        raise ValueError("preprocessing deadline cannot relax frozen budget")
    if monotonic()>=pre_deadline:
        return dict(status="preprocessing_timeout",result=None,process_reaped=True,timed_out=True)
    from .watchdog import run_isolated
    remaining=total_deadline-monotonic()
    if remaining<=0: return dict(status="total_deadline",result=None,process_reaped=True)
    argv=[sys.executable,"-m","nmr_assignment.execution","--record", "--started",str(started),
          "--total-deadline",str(total_deadline),"--pre-deadline",str(pre_deadline),
          "--approved-config",json.dumps(approved_numeric_config,allow_nan=False,separators=(",",":"))]
    watchdog=run_isolated(argv,raw_payload.decode("utf-8"),timeout_seconds=remaining)
    result=None
    if watchdog.stdout:
        try: result=json.loads(watchdog.stdout)
        except json.JSONDecodeError: pass
    expired=watchdog.timed_out or monotonic()>=total_deadline
    if expired and isinstance(result,dict):
        result["status"]="total_deadline"
        for method in result.get("methods",{}).values():
            method["certified"]=False; method["timed_out"]=True
    envelope=dict(status="total_deadline" if expired else "worker_error" if watchdog.exit_code else
                result.get("status","worker_error") if isinstance(result,dict) else "worker_error",
                result=result,process_reaped=watchdog.process_reaped,child_pid=watchdog.child_pid,
                exit_code=watchdog.exit_code,timed_out=expired,elapsed_seconds=monotonic()-started,
                stderr=watchdog.stderr,input_id=input_id,prediction_artifact_sha256=prediction_artifact_sha256)
    if envelope["status"]=="completed" and envelope["process_reaped"] is True:
        envelope["execution_receipt"]=_make_execution_receipt(raw_payload,approved_numeric_config,envelope,
            input_id=input_id,prediction_artifact_sha256=prediction_artifact_sha256)
    # Receipt construction / parent JSON parsing may finish late; never certify it.
    if monotonic()>=total_deadline:
        envelope["status"]="total_deadline"; envelope["timed_out"]=True
        envelope.pop("execution_receipt",None)
        for method in (result or {}).get("methods",{}).values():
            method["certified"]=False; method["timed_out"]=True
    envelope["elapsed_seconds"]=monotonic()-started
    return envelope


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--record",action="store_true"); parser.add_argument("--solver",action="store_true")
    parser.add_argument("--prepare",action="store_true")
    parser.add_argument("--started",type=float); parser.add_argument("--total-deadline",type=float)
    parser.add_argument("--pre-deadline",type=float); parser.add_argument("--approved-config")
    args=parser.parse_args()
    try:
        raw=sys.stdin.buffer.read(MAX_INPUT_BYTES+1)
        if len(raw)>MAX_INPUT_BYTES: raise ValueError("unsupported_input_budget")
        if sum((args.solver,args.record,args.prepare))!=1: raise ValueError("exactly one worker mode required")
        if args.solver:
            result=_solver_worker(raw)
        elif args.record or args.prepare:
            approved=json.loads(args.approved_config); _validate_config(approved)
            worker=_worker_record if args.record else _prepare_record
            result=worker(raw,approved,started=args.started,total_deadline=args.total_deadline,pre_deadline=args.pre_deadline)
        else: raise ValueError("exactly one worker mode required")
        print(json.dumps(result,allow_nan=False,separators=(",",":")))
    except Exception as exc:
        print(json.dumps(dict(status="worker_error",error=type(exc).__name__+": "+str(exc))))
        sys.exit(2)


if __name__=="__main__": main()
