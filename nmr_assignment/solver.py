"""功能概述：对调用方给定成本的 singleton/pair 候选求有限全局归属，不读取谱、标签或模型。
主要职责：Candidate 描述一个观测及其环境集合；Solution 保存完整解；Attempt 记录每次
SciPy MILP 的实际状态；Margin 保存禁止某峰当前完整赋值后重优化的差值；SolveResult
汇总最佳解、最多三个完整解、逐峰 margin 和认证范围。solve_assignment 是唯一求解入口。
代码库关系：独立于 contracts.py 的科学输入与映射语义，供归属适配层传入已冻结成本；
tests/assignment/test_solver.py 用独立穷举验证约束、排名及 margin。依赖 numpy/scipy。
输入输出与边界：环境恰好使用一次或缺测，观测恰好选择一个候选或未解释。成本可为负数，
必须有限；非法或重复输入抛 ValueError。按结构 ID 定义完整解，不做化学身份置换商空间。
总时间预算覆盖所有求解调用；非最优 incumbent 保留但不认证，未证明的 margin 为 None。
Top-k 的同成本解顺序由 HiGHS 决定，不扰动科学成本；最佳峰赋值相同时不会构成 margin
替代。认证指 HiGHS 浮点容差下的零相对 gap 最优性，不声称有理数精确证明。无文件写入、
网络、持久缓存或训练；时间预算不包含调用方的预处理，单次后端结束有少量调度开销。
"""

from dataclasses import dataclass
from math import fsum, isfinite
from time import monotonic
from typing import Mapping, Optional, Tuple

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csc_matrix, vstack


@dataclass(frozen=True)
class Candidate:
    observation_id: str
    environment_ids: Tuple[str, ...]
    cost: float


@dataclass(frozen=True)
class Solution:
    objective: float
    assignments: Mapping[str, Tuple[str, ...]]
    unobserved: Tuple[str, ...]
    unexplained: Tuple[str, ...]
    certified: bool


@dataclass(frozen=True)
class Attempt:
    purpose: str
    status: str
    raw_status: Optional[int]
    message: str
    optimal: bool
    timed_out: bool
    objective: Optional[float] = None
    mip_gap: Optional[float] = None
    dual_bound: Optional[float] = None


@dataclass(frozen=True)
class Margin:
    value: Optional[float]
    status: str
    certified: bool
    alternative_objective: Optional[float] = None


@dataclass(frozen=True)
class SolveResult:
    best: Optional[Solution]
    alternatives: Tuple[Solution, ...]
    status: str
    optimal: bool
    timed_out: bool
    top_k_certified: bool
    exhausted: bool
    margins: Mapping[str, Margin]
    attempts: Tuple[Attempt, ...]
    identification_quotient: str = "none"


def _ids(values, name):
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} require a sequence, not a single string")
    try:
        values = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{name} require a sequence") from exc
    if any(not isinstance(x, str) or not x for x in values):
        raise ValueError(f"{name} require nonempty string IDs")
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate {name}")
    return tuple(sorted(values))


def _cost(value):
    if isinstance(value, (bool, str, bytes)):
        raise ValueError("costs require finite real numbers")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("costs require finite real numbers") from exc
    if not isfinite(result):
        raise ValueError("costs require finite real numbers")
    return result


def solve_assignment(observation_ids, environment_ids, candidates,
                     missing_costs, unexplained_costs, *, top_k=3,
                     time_limit=None, compute_margins=True):
    """Return up to top_k ID-distinct complete solutions and exact-cost margins.

    alternatives excludes best. top_k_certified means all requested ranks are
    proven or the space was exhausted; optimal refers only to best. status is
    the best-solve status; attempts expose later limits/errors. timed_out covers
    any phase. No-alternative margins have value=None, status='no_alternative',
    certified=True; they are not probabilities or numerical infinite margins.
    """
    obs = _ids(observation_ids, "observation IDs")
    env = _ids(environment_ids, "environment IDs")
    if type(top_k) is not int or not 1 <= top_k <= 3:
        raise ValueError("top_k must be an integer from 1 to 3")
    if type(compute_margins) is not bool:
        raise ValueError("compute_margins must be boolean")
    if time_limit is not None:
        time_limit = _cost(time_limit)
        if time_limit <= 0:
            raise ValueError("time_limit must be positive")
    if not isinstance(missing_costs, Mapping) or set(missing_costs) != set(env):
        raise ValueError("missing_costs must cover exactly the environment IDs")
    if not isinstance(unexplained_costs, Mapping) or set(unexplained_costs) != set(obs):
        raise ValueError("unexplained_costs must cover exactly the observation IDs")
    normalized, seen = [], set()
    for candidate in candidates:
        if not isinstance(candidate, Candidate):
            raise ValueError("candidates must be Candidate instances")
        members = _ids(candidate.environment_ids, "candidate environment IDs")
        if not 1 <= len(members) <= 2:
            raise ValueError("candidates require one or two distinct environments")
        if candidate.observation_id not in obs or not set(members) <= set(env):
            raise ValueError("candidate references an unknown ID")
        key = candidate.observation_id, members
        if key in seen:
            raise ValueError("duplicate candidate assignment")
        seen.add(key)
        normalized.append(Candidate(candidate.observation_id, members, _cost(candidate.cost)))
    normalized.sort(key=lambda x: (x.observation_id, x.environment_ids))
    # Variable identities are unique physical choices; there are no dummy copies.
    choices = [(x.observation_id, x.environment_ids) for x in normalized]
    costs = [x.cost for x in normalized]
    choices += [(None, (i,)) for i in env]
    costs += [_cost(missing_costs[i]) for i in env]
    choices += [(j, ()) for j in obs]
    costs += [_cost(unexplained_costs[j]) for j in obs]
    try:
        magnitude = fsum(abs(x) for x in costs)
    except OverflowError as exc:
        raise ValueError("total cost magnitude exceeds floating point range") from exc
    if not isfinite(magnitude):
        raise ValueError("total cost magnitude exceeds floating point range")
    n = len(choices)
    obs_rows = {j: k for k, j in enumerate(obs)}
    env_rows = {i: len(obs) + k for k, i in enumerate(env)}
    rows, cols = [], []
    for k, (j, members) in enumerate(choices):
        if j is not None:
            rows.append(obs_rows[j]); cols.append(k)
        for i in members:
            rows.append(env_rows[i]); cols.append(k)
    matrix = csc_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(obs) + len(env), n))
    costs = np.asarray(costs, dtype=float)
    started = monotonic()
    attempts = []

    def run(purpose, excluded=(), forbidden=None):
        remaining = None if time_limit is None else time_limit - (monotonic() - started)
        if remaining is not None and remaining <= 0:
            attempts.append(Attempt(purpose, "time_limit", None, "total time budget exhausted", False, True))
            return None, None
        if n == 0:
            solution = Solution(0., {}, (), (), True)
            attempts.append(Attempt(purpose, "optimal", 0, "empty assignment", True, False, 0., 0., 0.))
            return solution, ()
        extra = []
        for selected in excluded:
            # A selected set covers every equality row. No distinct feasible
            # complete solution can contain it, so this cut excludes only it.
            extra.append(csc_matrix((np.ones(len(selected)), ([0] * len(selected), selected)), shape=(1, n)))
        constraint_matrix = vstack([matrix] + extra, format="csc") if extra else matrix
        lower = np.concatenate([np.ones(matrix.shape[0]), np.full(len(extra), -np.inf)])
        upper = np.concatenate([np.ones(matrix.shape[0]), [len(x) - 1 for x in excluded]])
        bounds_upper = np.ones(n)
        if forbidden is not None:
            bounds_upper[forbidden] = 0.
        options = {"mip_rel_gap": 0.}
        if remaining is not None:
            options["time_limit"] = remaining
        result = milp(costs, integrality=np.ones(n), bounds=Bounds(np.zeros(n), bounds_upper),
                      constraints=LinearConstraint(constraint_matrix, lower, upper), options=options)
        raw = int(result.status)
        status = {0: "optimal", 1: "limit", 2: "infeasible", 3: "unbounded", 4: "error"}.get(raw, "error")
        message = str(result.message)
        timed_out = raw == 1 and "time" in message.lower()
        certified = raw == 0
        selected, solution = None, None
        if getattr(result, "x", None) is not None:
            vector = np.asarray(result.x, dtype=float)
            valid = vector.shape == (n,) and np.isfinite(vector).all()
            rounded = np.rint(vector) if valid else np.zeros(n)
            valid = (valid and np.max(np.abs(vector - rounded)) <= 1e-6
                     and np.all((rounded >= 0) & (rounded <= bounds_upper))
                     and np.all(constraint_matrix @ rounded >= lower - 1e-7)
                     and np.all(constraint_matrix @ rounded <= upper + 1e-7))
            if valid:
                selected = tuple(int(k) for k in np.flatnonzero(rounded))
                assignments, unobserved = {}, []
                for k in selected:
                    j, members = choices[k]
                    if j is None:
                        unobserved.extend(members)
                    else:
                        assignments[j] = members
                assignments = {j: assignments[j] for j in obs}
                solution = Solution(fsum(float(costs[k]) for k in selected), assignments,
                                    tuple(sorted(unobserved)), tuple(j for j in obs if not assignments[j]), certified)
            else:
                status, certified = "error", False
                message += "; rejected nonintegral or infeasible incumbent"
        if certified and solution is None:
            status, certified = "error", False
            message += "; optimal status without feasible incumbent"
        gap = getattr(result, "mip_gap", None)
        dual = getattr(result, "mip_dual_bound", None)
        attempts.append(Attempt(purpose, status, raw, message, certified, timed_out,
                                None if solution is None else solution.objective,
                                None if gap is None else float(gap), None if dual is None else float(dual)))
        return solution, selected

    best, best_selected = run("best")
    best_attempt = attempts[-1]
    alternatives = []
    exhausted = n == 0 and best_attempt.optimal
    top_certified = best_attempt.optimal and (top_k == 1 or exhausted)
    if best_attempt.optimal and not exhausted:
        exclusions = [best_selected]
        for rank in range(2, top_k + 1):
            alternative, selected = run(f"top_{rank}", excluded=exclusions)
            attempt = attempts[-1]
            if attempt.status == "infeasible":
                exhausted, top_certified = True, True
                break
            if alternative is not None:
                alternatives.append(alternative)
            if not attempt.optimal:
                break
            exclusions.append(selected)
            if rank == top_k:
                top_certified = True
    margins = {}
    for j in obs:
        if not compute_margins:
            margins[j] = Margin(None, "not_requested", False)
        elif not best_attempt.optimal:
            margins[j] = Margin(None, "best_not_optimal", False)
        else:
            chosen = next(k for k in best_selected if choices[k][0] == j)
            alternative, _ = run(f"margin:{j}", forbidden=chosen)
            attempt = attempts[-1]
            if attempt.status == "infeasible":
                margins[j] = Margin(None, "no_alternative", True)
            elif attempt.optimal:
                delta = alternative.objective - best.objective
                # Preserve evidence of numerical contradictions rather than
                # reporting a negative margin as a proof of confidence.
                if delta < -1e-7 * max(1., abs(best.objective)):
                    margins[j] = Margin(None, "numerical_inconsistency", False, alternative.objective)
                else:
                    margins[j] = Margin(max(0., delta), "optimal", True, alternative.objective)
            else:
                margins[j] = Margin(None, attempt.status, False,
                                    None if alternative is None else alternative.objective)
    return SolveResult(best, tuple(alternatives), best_attempt.status, best_attempt.optimal,
                       any(a.timed_out for a in attempts), top_certified, exhausted,
                       margins, tuple(attempts))
