"""功能概述：将 mapping 冻结的单位容量和多中心分布转成 B0/B1/B2 成本。
主要职责：Observation 校验观测；local_nearest 按单位最小残差给局部 Top3，允许跨峰
复用；build_b1 使用显式固定尺度；build_b2 逐载体保留 sigma 和权重，以稳定 logsumexp
计算 Huber 混合成本。pair 消耗两个不同 unit，按逐组合成员残差及跨度门控，不重归一。
首轮 integral_policy 必须显式 disabled，两核均拒绝积分。unit_normalizers 与 b2_missing_costs
按预测分布计算 A_u；raw 与 reduced 的 matched/missing 同时补偿，保持完整解排序和 margin。
代码库关系：依赖 mapping 的质量与归一化验证，返回 solver.Candidate，environment_ids
始终是 unit IDs。全局排他、missing/unexplained dummy 由 solver 处理。
输入输出与副作用：显式科学参数，无默认阈值；max_candidates 只计 emitted 候选；examined_count 单独报告载体组合检查数（含门控拒绝），
检查循环受 deadline 限制，绝不以候选上限冒充检查数上限。
_unit_sets 按原 singleton/pair 次序惰性产出，并在每个组合前检查 deadline；不预分配 O(U²) pairs。
GenerationLimit 不返回截断图。无文件、网络、模型前向或缓存；非法输入抛 ValueError。
"""
from dataclasses import dataclass
from itertools import combinations, product
from math import isfinite, log, fsum, exp, hypot
from time import monotonic

from .solver import Candidate
from .mapping import FrozenCapacityPredictions


def _number(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, (bool, str, bytes)):
        raise ValueError(name + " must be finite numeric")
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(name + " must be finite numeric") from exc
    if not isfinite(value) or (positive and value <= 0) or (nonnegative and value < 0):
        raise ValueError(name + " outside allowed range")
    return value


def _identity(value):
    if not isinstance(value, str) or not value:
        raise ValueError("ID must be a nonempty string")


@dataclass(frozen=True)
class Observation:
    observation_id: str
    ppm: float

    def __post_init__(self):
        _identity(self.observation_id)
        object.__setattr__(self, "ppm", _number(self.ppm, "ppm"))


@dataclass(frozen=True)
class LocalResult:
    observation_id: str
    local_top3: tuple
    # Top3 includes the entire tie block crossing rank three.
    minimum_unit_ids: tuple
    rank_bounds: tuple
    tie_blocks: tuple


class GenerationLimit(RuntimeError):
    """Complete graph unavailable; counts retain examined and emitted audit facts."""
    def __init__(self, message, *, examined_count=0, emitted_count=0):
        super().__init__(message)
        self.examined_count = examined_count
        self.emitted_count = emitted_count


class GeneratedBatch(tuple):
    """Tuple-compatible complete result with separate examination/emission counts."""
    def __new__(cls, values, *, examined_count, emitted_count):
        obj = super().__new__(cls, values)
        obj.examined_count = examined_count
        obj.emitted_count = emitted_count
        return obj


class _Budget:
    def __init__(self, maximum, deadline):
        if type(maximum) is not int or maximum < 0:
            raise ValueError("max_candidates must be a nonnegative integer")
        self.maximum, self.count, self.emitted = maximum, 0, 0
        self.deadline = None if deadline is None else _number(deadline, "deadline")
        self.check()

    def fail(self, message):
        raise GenerationLimit(message,examined_count=self.count,emitted_count=self.emitted)

    def check(self):
        if self.deadline is not None and monotonic() >= self.deadline:
            self.fail("candidate deadline exhausted")

    def step(self):
        self.check()
        self.count += 1

    def emit(self):
        self.check()
        if self.emitted >= self.maximum:
            self.fail("emitted candidate budget exhausted")
        self.emitted += 1

    def finish(self, result):
        self.check()
        return GeneratedBatch(result,examined_count=self.count,emitted_count=self.emitted)


def _inputs(observations, predictions):
    obs = tuple(observations)
    if any(type(x) is not Observation for x in obs):
        raise ValueError("only strict Observation instances are accepted")
    if len({x.observation_id for x in obs}) != len(obs):
        raise ValueError("duplicate observation IDs")
    if type(predictions) is not FrozenCapacityPredictions:
        raise ValueError("predictions must be FrozenCapacityPredictions")
    predictions.layout.__post_init__()
    for carrier in predictions.carriers:
        carrier.__post_init__()
    predictions.__post_init__()
    grouped = {u.unit_id: [] for u in predictions.layout.units}
    for carrier in predictions.carriers:
        grouped[carrier.unit_id].append(carrier)
    return sorted(obs, key=lambda x: x.observation_id), tuple(
        (uid, tuple(grouped[uid])) for uid in sorted(grouped))


def _cost(value):
    return _number(value, "generated cost", nonnegative=True)


def local_nearest(observations, predictions, *, scale, tie_relative_tolerance, max_candidates, deadline=None):
    """Independent B0; no gates or dummies; emitted budget counts peak/unit choices."""
    scale = _number(scale, "scale", positive=True)
    tolerance = _number(tie_relative_tolerance,"tie_relative_tolerance",nonnegative=True)
    budget = _Budget(max_candidates, deadline)
    obs, pred = _inputs(observations, predictions)
    result = []
    for peak in obs:
        ranked = []
        for uid, carriers in pred:
            residuals = []
            for carrier in carriers:
                budget.step()
                residuals.append(abs(peak.ppm - carrier.center_ppm))
            budget.emit()
            ranked.append((uid, _cost(min(residuals)/scale)))
        ranked.sort(key=lambda x: (x[1], x[0]))
        blocks = []
        for entry in ranked:
            if not blocks or entry[1]-blocks[-1][0][1] > tolerance*max(1.,abs(entry[1]),abs(blocks[-1][0][1])):
                blocks.append([])
            blocks[-1].append(entry)
        bounds, selected = [], []
        rank = 1
        for block in blocks:
            end = rank+len(block)-1
            bounds.extend((uid,rank,end) for uid,_ in block)
            if rank <= 3:
                selected.extend(block)
            rank=end+1
        minimum = tuple(uid for uid,_ in blocks[0]) if blocks else ()
        result.append(LocalResult(peak.observation_id,tuple(selected),minimum,tuple(bounds),
                                  tuple(tuple(uid for uid,_ in block) for block in blocks)))
    return budget.finish(result)


def build_b1(observations, predictions, *, scale, max_candidates, deadline=None):
    """Fixed per-nucleus caller scale; no width or exclusivity used here."""
    scale = _number(scale, "scale", positive=True)
    budget = _Budget(max_candidates, deadline)
    obs, pred = _inputs(observations, predictions)
    result = []
    for peak in obs:
        for uid, carriers in pred:
            residuals = []
            for carrier in carriers:
                budget.step()
                residuals.append(abs(peak.ppm - carrier.center_ppm))
            budget.emit()
            result.append(Candidate(peak.observation_id, (uid,),
                                    _cost(min(residuals) / scale)))
    return budget.finish(result)


def build_b2(observations, predictions, *, nucleus, delta, smin,
             lambda_merge, member_gate, pair_span, gate_mode, normalizer_convention,
             integral_policy, max_candidates, deadline=None, integral_penalties=None):
    """Normalized carrier mixtures; budget caps emitted candidates only.

    First-round integral_policy must be disabled for both nuclei.
    standardized gates use |residual|/s and |center difference|/hypot(s1,s2).
    raw adds A per consumed unit; reduced uses qtilde and compensated missing costs.
    Gates remove probability mass, never renormalize the surviving combinations.
    """
    if nucleus not in ("1H", "13C"):
        raise ValueError("nucleus must be 1H or 13C")
    if gate_mode not in ("standardized", "absolute_ppm"):
        raise ValueError("explicit gate_mode must be standardized or absolute_ppm")
    if normalizer_convention not in ("raw", "reduced"):
        raise ValueError("normalizer_convention must be raw or reduced")
    if integral_policy != "disabled" or integral_penalties is not None:
        raise ValueError("first-round integral policy is disabled for both nuclei")
    delta = _number(delta, "delta", positive=True)
    smin = _number(smin, "smin", positive=True)
    merge = _number(lambda_merge, "lambda_merge", positive=True)
    gate = _number(member_gate, "member_gate", nonnegative=True)
    span = _number(pair_span, "pair_span", nonnegative=True)
    budget = _Budget(max_candidates, deadline)
    obs, pred = _inputs(observations, predictions)
    if predictions.layout.nucleus != nucleus:
        raise ValueError("nucleus differs from capacity layout")
    budget.check()
    scales, normalizers, log_qtilde = _normalizer_parts(pred, smin, budget)
    budget.check()
    unresolved = {u.unit_id for u in predictions.layout.units
                  if u.partition_status == "unresolved_parent_pool"}
    budget.check()
    result = []
    for peak in obs:
        for members in _unit_sets(pred, unresolved, budget):
            logs = []
            ids = tuple(uid for uid, _ in members)
            for carriers in product(*(cs for _, cs in members)):
                budget.step()
                residuals = [abs(peak.ppm - c.center_ppm) for c in carriers]
                if any((r/scales[c.carrier_id] if gate_mode=="standardized" else r)>gate
                       for c,r in zip(carriers,residuals)):
                    continue
                if len(carriers) == 2:
                    difference = abs(carriers[0].center_ppm-carriers[1].center_ppm)
                    if gate_mode=="standardized":
                        difference /= hypot(*(scales[c.carrier_id] for c in carriers))
                    if difference > span:
                        continue
                terms = []
                for c, residual in zip(carriers, residuals):
                    z = residual / scales[c.carrier_id]
                    rho = z*z/2 if z <= delta else delta*(z-delta/2)
                    terms.append(log_qtilde[c.carrier_id] - rho)
                logs.append(fsum(terms))
            if not logs:
                continue
            maximum = max(logs)
            if not isfinite(maximum):
                raise ValueError("mixture cost overflow")
            cost = -maximum-log(fsum(exp(v-maximum) for v in logs))
            # Normalization tolerance in mapping can yield tiny negative roundoff.
            cost = max(0., cost) + merge*(len(members)-1)
            if normalizer_convention == "raw":
                cost += fsum(normalizers[uid] for uid in ids)
            budget.emit()
            result.append(Candidate(peak.observation_id, ids, _cost(cost)))
    return budget.finish(result)


def _unit_sets(pred, unresolved, budget):
    """Original deterministic singleton-then-pair order, with no eager pair graph."""
    budget.check()
    for size in (1, 2):
        budget.check()
        for members in combinations(pred, size):
            budget.check()
            if size==2 and any(uid in unresolved for uid,_ in members):
                continue
            yield members


def _logsumexp(values):
    maximum = max(values)
    if not isfinite(maximum):
        raise ValueError("normalizer overflow")
    return maximum+log(fsum(exp(v-maximum) for v in values))


def _normalizer_parts(grouped, smin, budget=None):
    scales, normalizers, log_qtilde = {}, {}, {}
    for uid, carriers in grouped:
        logs = []
        for c in carriers:
            if budget is not None:
                budget.check()
            if c.sigma_ppm is None:
                raise ValueError("B2 requires carrier-specific frozen sigma provenance")
            scale = max(_number(c.sigma_ppm,"sigma",positive=True),smin)
            scales[c.carrier_id] = scale
            logs.append(log(c.mixture_weight)+log(smin)-log(scale))
        logz = _logsumexp(logs)
        normalizers[uid] = max(0.,-logz)
        for c, value in zip(carriers, logs):
            log_qtilde[c.carrier_id] = value-logz
    return scales, normalizers, log_qtilde


def unit_normalizers(predictions, *, smin):
    """A_u from frozen q/s only; no observed values, labels or measured integrals."""
    smin = _number(smin,"smin",positive=True)
    _, grouped = _inputs((),predictions)
    return _normalizer_parts(grouped,smin)[1]


def b2_missing_costs(predictions, relative_missing_costs, *, smin, normalizer_convention):
    """Map explicit kappa to raw A+kappa or reduced kappa; exact-cover gauge only."""
    from collections.abc import Mapping
    if normalizer_convention not in ("raw","reduced"):
        raise ValueError("normalizer_convention must be raw or reduced")
    constants = unit_normalizers(predictions,smin=smin)
    if not isinstance(relative_missing_costs,Mapping) or set(relative_missing_costs)!=set(constants):
        raise ValueError("relative missing costs must cover every unit exactly")
    return {uid:_number(relative_missing_costs[uid],"relative missing cost",nonnegative=True)+
            (constant if normalizer_convention=="raw" else 0.) for uid,constant in constants.items()}


def parameters_from_frozen_config(config, *, method, nucleus, normalizer_convention):
    """Extract caller-approved configuration values; never load or approve a config.

    This function does not infer exchange/window priors or create dummy maps. Those
    depend on separately supplied frozen structure/acquisition evidence.
    """
    if nucleus not in ("1H","13C") or method not in ("B0","B1","B2"):
        raise ValueError("unsupported method/nucleus")
    if normalizer_convention not in ("raw","reduced"):
        raise ValueError("normalizer_convention must be raw or reduced")
    p = config["machine_cost_contract"]
    if method in ("B0","B1"):
        return {"scale":p["B0_B1_reference_scale_ppm"][nucleus]}
    if (p["integral_policy"] != "disabled_both_nuclei_first_round" or
            p["B2_gate_mode"] != "standardized" or p["max_units_per_observation"] != 2):
        raise ValueError("unsupported frozen first-round machine cost policy")
    return dict(nucleus=nucleus,delta=p["B2_delta"],smin=p["smin_ppm"][nucleus],
        lambda_merge=p["B2_merge_cost"],member_gate=p["B2_member_gate_multiplier"],
        pair_span=p["B2_pair_span_error_scale_multiplier"],gate_mode=p["B2_gate_mode"],
        normalizer_convention=normalizer_convention,integral_policy="disabled")
