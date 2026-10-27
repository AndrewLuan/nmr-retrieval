"""功能概述：在同一冻结 unit/carrier 预测上调用 B0/B1/B2，不读取来源或 gold。
主要职责：run_baseline 校验显式科学参数、dummy 精确覆盖与预算；B0 独立近邻允许复用，
B1/B2 调 costs 后进入 solver。BaselineResult 保留原 SolveResult 与审计状态，不改写其
best/top-k/margins/attempts；外层 certified 标识整个调用是否仍在总 deadline 内。
LocalDecision 保留完整 minimum/cutoff 同分块及 rank bounds，不把固定 ID 排序解释为唯一；
全局逐峰 gap 使用 reduced objective 的显式 tie tolerance；无证书或无数值替代保守 abstain。
代码库关系：连接 costs/mapping/solver；所有 Candidate.environment_ids 是容量 unit IDs。
caller 另持 prediction manifest 与结构/条件，本模块不接 source、gold 或身份元数据。
输入输出与副作用：参数无科学默认值，finite time_limit 和绝对 monotonic total_deadline
必须显式给出。max_candidates 计 emitted 候选，examined_count 另报载体组合检查数，max_variables 限制候选加 dummy 的矩阵列数。
B2 显式选择 standardized/absolute 诊断 gates 与 raw/reduced convention；missing_costs 输入
解释为相对 kappa，由 b2_missing_costs 一致补偿 A_u；积分首轮禁用。总 deadline 覆盖生成与 solver 矩阵构造；若后端越界保留原始结果但外层 timeout/不认证。
GenerationLimit 返回可审计失败结果，不静默删样本；非法配置抛 ValueError。无文件/网络副作用。
"""
from dataclasses import dataclass
from collections.abc import Mapping
from math import isfinite
from time import monotonic
from .costs import (Observation, local_nearest, build_b1, build_b2, GenerationLimit,
                    _inputs, b2_missing_costs, unit_normalizers)
from .solver import solve_assignment


def _finite(value, name, *, positive=False):
    if isinstance(value, (bool, str, bytes)):
        raise ValueError(name + " requires a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(name + " requires a finite number") from exc
    if not isfinite(result) or (positive and result <= 0):
        raise ValueError(name + " outside allowed range")
    return result


@dataclass(frozen=True)
class LocalDecision:
    observation_id: str
    local_top3: tuple
    best_unique: bool
    third_boundary: str
    minimum_unit_ids: tuple = ()
    rank_bounds: tuple = ()
    tie_blocks: tuple = ()

    @property
    def minimum_tie_block(self):
        return self.minimum_unit_ids

    @property
    def minimum_tie_complete(self):
        return bool(self.tie_blocks) or not self.local_top3


@dataclass(frozen=True)
class BaselineResult:
    method: str
    status: str
    certified: bool
    timed_out: bool
    local: tuple
    solver_result: object
    candidate_count: int
    variable_count: int
    elapsed_seconds: float
    detail: str
    identification_quotient: str = "none"
    reuse_semantics: str = "global_exclusive"
    cost_convention: str = "not_applicable"
    per_observation_status: tuple = ()
    global_top3_boundary: str = "not_applicable"
    chemical_top3: str = "unsupported"
    examined_count: int = 0

    @property
    def observation_determinate(self):
        if self.method=="B0":
            return {row.observation_id:self.certified and row.best_unique for row in self.local}
        return {oid:state=="certified_separated_uncalibrated" for oid,state in self.per_observation_status}

    @property
    def observation_alternatives(self):
        return {row.observation_id:row.minimum_tie_block for row in self.local}



def run_baseline(method, observations, predictions, *, parameters, max_candidates,
                 max_variables, time_limit, total_deadline, top_k, compute_margins,
                 tie_relative_tolerance,
                 missing_costs=None, unexplained_costs=None):
    """Run one method with explicit costs and bounded work; no parameter tuning.

    B0/B1 require explicit scale; B0 dummy maps must be absent.
    B2 requires nucleus,delta,smin,lambda_merge,member_gate,pair_span and may take
    integral_penalties (first round rejects all contributions). B2 additionally
    requires gate_mode,normalizer_convention,integral_policy. Global dummy maps
    cover all IDs exactly; B2 missing_costs are relative kappa, converted consistently.
    Solver results retain their backend certification; outer certified is required
    as well before claiming the whole pipeline completed within total deadline.
    """
    started = monotonic()
    if method not in ("B0", "B1", "B2"):
        raise ValueError("method must be B0/B1/B2")
    limit = _finite(time_limit, "time_limit", positive=True)
    deadline = _finite(total_deadline, "total_deadline")
    tie_tolerance = _finite(tie_relative_tolerance,"tie_relative_tolerance")
    if tie_tolerance < 0:
        raise ValueError("tie_relative_tolerance must be nonnegative")
    if type(max_candidates) is not int or max_candidates < 0:
        raise ValueError("max_candidates must be a nonnegative integer")
    if type(max_variables) is not int or max_variables < 0:
        raise ValueError("max_variables must be a nonnegative integer")
    if type(top_k) is not int or not 1 <= top_k <= 3 or type(compute_margins) is not bool:
        raise ValueError("explicit top_k 1..3 and boolean compute_margins required")
    required = {"B0": {"scale"}, "B1": {"scale"}, "B2": {
        "nucleus", "delta", "smin", "lambda_merge", "member_gate", "pair_span",
        "gate_mode", "normalizer_convention", "integral_policy"}}[method]
    optional = {"integral_penalties"} if method == "B2" else set()
    if not isinstance(parameters, Mapping) or not required <= set(parameters) or set(parameters)-required-optional:
        raise ValueError("method parameters do not match whitelist")
    obs, grouped = _inputs(observations, predictions)
    obs_ids, unit_ids = tuple(o.observation_id for o in obs), tuple(uid for uid, _ in grouped)
    reuse = "independent_local" if method == "B0" else "global_exclusive"

    def result(status, *, raw=None, local=(), count=0, variables=0, timeout=False, certified=False, detail="", per_obs=(), examined=0):
        return BaselineResult(method, status, certified, timeout, local, raw, count, variables,
                              monotonic()-started, detail, "none", reuse,
                              parameters["normalizer_convention"] if method=="B2" else "fixed_distance",per_obs,
                              "space_exhausted" if raw is not None and raw.exhausted else
                              "cutoff_unverified" if raw is not None else "not_applicable",
                              "unsupported",examined)

    if method == "B0":
        if missing_costs is not None or unexplained_costs is not None:
            raise ValueError("B0 has no dummy costs")
    else:
        for values, ids, name in ((missing_costs,unit_ids,"missing_costs"),
                                  (unexplained_costs,obs_ids,"unexplained_costs")):
            if not isinstance(values,Mapping) or set(values) != set(ids):
                raise ValueError(name + " must cover exactly supplied IDs")
            for value in values.values():
                _finite(value,name)
    if monotonic() >= deadline:
        return result("total_deadline", timeout=True, detail="deadline exhausted before generation")
    # Generation has its own absolute deadline equal to the caller total deadline.
    try:
        if method == "B0":
            rows = local_nearest(obs,predictions,**parameters,tie_relative_tolerance=tie_tolerance,
                                 max_candidates=max_candidates,deadline=deadline)
            local = tuple(LocalDecision(row.observation_id,row.local_top3,
                len(row.minimum_unit_ids)==1,"complete_cutoff_tie_blocks",row.minimum_unit_ids,
                row.rank_bounds,row.tie_blocks) for row in rows)
            if monotonic() >= deadline:
                return result("total_deadline",local=local,timeout=True,count=rows.emitted_count,examined=rows.examined_count)
            return result("local_complete",local=local,certified=True,count=rows.emitted_count,examined=rows.examined_count,
                          detail="complete unit tie blocks; chemical identity projection remains external")
        build = build_b1 if method == "B1" else build_b2
        candidates = build(obs,predictions,**parameters,max_candidates=max_candidates,deadline=deadline)
    except GenerationLimit as exc:
        return result("total_deadline" if monotonic()>=deadline else "candidate_budget",
                      timeout=monotonic()>=deadline,detail=str(exc),count=exc.emitted_count,examined=exc.examined_count)
    count = len(candidates)
    variables = count+len(unit_ids)+len(obs_ids)
    if variables > max_variables:
        return result("matrix_budget",count=count,variables=variables,examined=candidates.examined_count,
                      detail="complete graph exceeds explicit variable budget; solver not called")
    remaining = deadline-monotonic()
    if remaining <= 0:
        return result("total_deadline",count=count,variables=variables,examined=candidates.examined_count,timeout=True)
    solver_missing = b2_missing_costs(predictions,missing_costs,smin=parameters["smin"],
        normalizer_convention=parameters["normalizer_convention"]) if method=="B2" else missing_costs
    remaining = deadline-monotonic()
    if remaining <= 0:
        return result("total_deadline",count=count,variables=variables,examined=candidates.examined_count,timeout=True)
    raw = solve_assignment(obs_ids,unit_ids,candidates,solver_missing,unexplained_costs,
        top_k=top_k,time_limit=min(limit,remaining),compute_margins=compute_margins)
    expired = monotonic() >= deadline
    constant = sum(unit_normalizers(predictions,smin=parameters["smin"]).values()) if (
        method=="B2" and parameters["normalizer_convention"]=="raw") else 0.
    decisions = []
    for oid in obs_ids:
        margin = raw.margins.get(oid)
        if expired or raw.best is None or not raw.optimal or margin is None or not margin.certified:
            state = "abstain_uncertified"
        elif margin.value is None or margin.alternative_objective is None:
            state = "abstain_no_numeric_alternative"
        else:
            tau = tie_tolerance*max(1.,abs(raw.best.objective-constant),abs(margin.alternative_objective-constant))
            state = "abstain_tie" if margin.value<=tau else "certified_separated_uncalibrated"
        decisions.append((oid,state))
    expired = expired or monotonic() >= deadline
    if expired:
        decisions = [(oid,"abstain_uncertified") for oid in obs_ids]
    return result("total_deadline" if expired else raw.status,raw=raw,count=count,variables=variables,examined=candidates.examined_count,
                  timeout=expired or raw.timed_out,certified=raw.optimal and not expired,per_obs=tuple(decisions),
                  detail="backend result retained; total deadline includes matrix construction" if expired else "")
