# 功能：定义已知结构 NMR 峰归属的纯数据边界，不实现科学阈值或匹配算法。
# 职责：strict 拒绝多余字段；decimal 保留十进制精度并拒绝非有限值；
# ObservedPeak/Conditions/Window 保留真实观测及未知状态；FrozenEnvironment
# 与 FrozenPredictions 是 legacy 标量兼容入口；新输入直接保留 FrozenCapacityPredictions
# 的 unit 容量与全部 carrier，不合成均值。pH/missing_mask 缺省保持 unknown。
# candidate_meaning/basis 显式记录集合含义及依据；validate_against 检查输入输出引用和覆盖，
# reuse_semantics 区分局部重复使用与全局排他；Alternative 的全局选项必须引用完整解 ID。
# InferenceInput.from_mapping 递归解析白名单输入；Assignment/Alternative/
# AssignmentOutput 表达集合结果、残差、可行性类别及证据，阻止含糊映射的唯一原子断言。
# 关系：依赖纯标准库 mapping；unique 声明须用外部 JointMapping 重算并绑定完整唯一 atom
# ProjectedAssignment，未知分区不支持。旧 legacy unique_atoms 标志不替代身份认证。
# 输入输出与副作用：接受映射或显式 dataclass 参数，返回不可变对象；非法输入抛 ValueError，
# 无文件、网络、缓存或持久化副作用。整数权重独立于实际积分，代价差不解释为概率。
# Hz 转换仅使用明确的 reference_offset 与实际正频率；计数和预测对象关系仍为待科学冻结的草案。
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from typing import Mapping, Optional, Tuple
from .mapping import (FrozenCapacityPredictions, CapacityLayout, CapacityUnit, FrozenCarrier,
                      JointMapping, ProjectedAssignment, project_assignment)


def strict(cls, value):
    if not isinstance(value, Mapping):
        raise ValueError(f"{cls.__name__} requires a mapping")
    unknown = set(value) - {f.name for f in fields(cls)}
    if unknown:
        raise ValueError(f"unknown {cls.__name__} keys: {sorted(unknown)}")
    return dict(value)


def decimal(value):
    if not isinstance(value, (str, Decimal)):
        raise ValueError("ppm and integral values require a decimal string or Decimal")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite():
        raise ValueError("decimal must be finite")
    return result


def ids(value):
    result = tuple(value)
    if any(type(x) is not int or x < 0 for x in result) or len(set(result)) != len(result):
        raise ValueError("atom candidates require distinct nonnegative integer atom indices")
    return result


@dataclass(frozen=True)
class Window:
    lower_ppm: Optional[Decimal]
    upper_ppm: Optional[Decimal]

    @classmethod
    def from_mapping(cls, value):
        data = strict(cls, value)
        return cls(**{k: None if v is None else decimal(v) for k, v in data.items()})

    def __post_init__(self):
        if (self.lower_ppm is None) != (self.upper_ppm is None):
            raise ValueError("window must be fully known or fully unknown")
        if self.lower_ppm is not None:
            if decimal(self.lower_ppm) >= decimal(self.upper_ppm):
                raise ValueError("window bounds must increase")


@dataclass(frozen=True)
class Conditions:
    solvent: Optional[str]
    temperature_kelvin: Optional[Decimal]
    frequency_mhz: Optional[Decimal]
    pH: Optional[Decimal] = None

    @classmethod
    def from_mapping(cls, value):
        data = strict(cls, value)
        for key in ("temperature_kelvin", "frequency_mhz", "pH"):
            if data.get(key) is not None:
                data[key] = decimal(data[key])
        return cls(**data)


    def __post_init__(self):
        if self.pH is not None:
            decimal(self.pH)
        if self.solvent is not None and not isinstance(self.solvent, str):
            raise ValueError("solvent must be a string or unknown")
        for value in (self.temperature_kelvin, self.frequency_mhz):
            if value is not None and decimal(value) <= 0:
                raise ValueError("known temperature and frequency must be positive")


@dataclass(frozen=True)
class ObservedPeak:
    peak_id: str
    shift_literal: str
    unit: str
    hz_semantics: Optional[str]
    reference_hz: Optional[Decimal]
    reference_ppm: Optional[Decimal]
    observation_type: str
    integer_weight: Optional[int]
    actual_integral: Optional[Decimal]

    @property
    def ppm(self):
        return self.normalized_ppm()

    def normalized_ppm(self, conditions: Optional[Conditions] = None) -> Decimal:
        value = decimal(self.shift_literal)
        if self.unit == "ppm":
            return value
        if (conditions is None or conditions.frequency_mhz is None or
                self.hz_semantics != "reference_offset" or
                self.reference_hz is None or self.reference_ppm is None):
            raise ValueError("Hz conversion requires actual frequency and explicit reference_offset semantics")
        frequency = decimal(conditions.frequency_mhz)
        if frequency <= 0:
            raise ValueError("spectrometer frequency must be positive")
        return decimal(self.reference_ppm) + (value - decimal(self.reference_hz)) / frequency

    @classmethod
    def from_mapping(cls, value):
        data = strict(cls, value)
        for key in ("actual_integral", "reference_hz", "reference_ppm"):
            if data.get(key) is not None:
                data[key] = decimal(data[key])
        return cls(**data)

    def __post_init__(self):
        if not isinstance(self.shift_literal, str):
            raise ValueError("shift_literal must retain the original decimal string")
        decimal(self.shift_literal)
        if self.unit not in ("ppm", "Hz"):
            raise ValueError("unit must be ppm or Hz")
        if self.hz_semantics not in (None, "reference_offset"):
            raise ValueError("unsupported Hz semantics")
        for value in (self.reference_hz, self.reference_ppm):
            if value is not None:
                decimal(value)
        if self.unit == "ppm" and any(x is not None for x in
                (self.hz_semantics, self.reference_hz, self.reference_ppm)):
            raise ValueError("ppm observations must not carry Hz reference metadata")
        if any(not isinstance(x, str) or not x for x in (self.peak_id, self.observation_type)):
            raise ValueError("peak identity and observation type are required")
        if self.integer_weight is not None and (type(self.integer_weight) is not int or self.integer_weight < 0):
            raise ValueError("integer_weight must be an integer or unknown")
        if self.actual_integral is not None:
            if decimal(self.actual_integral) < 0:
                raise ValueError("actual_integral must be nonnegative")


def candidate_basis(meaning, basis):
    if meaning not in ("chemical_equivalence", "mapping_ambiguity", "possible_overlap", "unknown"):
        raise ValueError("candidate meaning must be explicit")
    if meaning == "unknown":
        if basis is not None:
            raise ValueError("unknown candidate basis must remain unknown")
    elif not isinstance(basis, str) or not basis.strip():
        raise ValueError("known candidate meaning requires a nonempty basis")


@dataclass(frozen=True)
class FrozenEnvironment:
    """Legacy scalar schema; cannot represent a multi-carrier unit distribution."""
    environment_id: str
    atom_candidates: Tuple[int, ...]
    parent_candidates: Tuple[int, ...]
    hydrogen_count: int
    predicted_ppm: Decimal
    mapping_ambiguous: bool
    candidate_meaning: str
    candidate_basis: Optional[str]

    @classmethod
    def from_mapping(cls, value):
        data = strict(cls, value)
        for key in ("atom_candidates", "parent_candidates"):
            data[key] = ids(data[key])
        data["predicted_ppm"] = decimal(data["predicted_ppm"])
        return cls(**data)

    def __post_init__(self):
        ids(self.atom_candidates)
        ids(self.parent_candidates)
        candidate_basis(self.candidate_meaning, self.candidate_basis)
        if self.candidate_meaning == "mapping_ambiguity" and not self.mapping_ambiguous:
            raise ValueError("mapping ambiguity meaning requires explicit ambiguous status")
        decimal(self.predicted_ppm)
        if type(self.hydrogen_count) is not int or self.hydrogen_count < 0:
            raise ValueError("hydrogen_count must be a nonnegative integer")
        if (type(self.mapping_ambiguous) is not bool or
                not isinstance(self.environment_id, str) or not self.environment_id):
            raise ValueError("environment identity and explicit ambiguity are required")


@dataclass(frozen=True)
class FrozenPredictions:
    """Legacy scalar input only; use FrozenCapacityPredictions for new inference."""
    mapping_capability: str
    structural_environment_count: int
    predicted_resonance_count: int
    environments: Tuple[FrozenEnvironment, ...]

    @classmethod
    def from_mapping(cls, value):
        data = strict(cls, value)
        data["environments"] = tuple(FrozenEnvironment.from_mapping(x) for x in data["environments"])
        return cls(**data)

    def __post_init__(self):
        if self.mapping_capability not in ("none", "candidate_sets", "unique_atoms"):
            raise ValueError("unsupported mapping capability")
        for count in (self.structural_environment_count, self.predicted_resonance_count):
            if type(count) is not int or count < 0:
                raise ValueError("counts must be explicit nonnegative integers")
        names = [x.environment_id for x in self.environments]
        if len(set(names)) != len(names):
            raise ValueError("duplicate environment identity")
        if self.mapping_capability == "unique_atoms":
            raise ValueError("legacy unique_atoms unsupported: use capacity predictions and bind output to a complete unique atom projection")


def _capacity_prediction(pred):
    # Typed upstream mapping objects are the only capacity metadata entry point.
    objects = [(pred,FrozenCapacityPredictions),(pred.layout,CapacityLayout)]
    objects += [(u,CapacityUnit) for u in pred.layout.units]
    objects += [(c,FrozenCarrier) for c in pred.carriers]
    for obj, cls in objects:
        if type(obj) is not cls or set(vars(obj)) != {f.name for f in fields(cls)}:
            raise ValueError("capacity metadata must use strict upstream mapping objects")
        obj.__post_init__()


@dataclass(frozen=True)
class InferenceInput:
    structure: str
    nucleus: str
    observed_peaks: Tuple[ObservedPeak, ...]
    window: Window
    actual_conditions: Conditions
    frozen_predictions: object
    missing_mask: object = None

    @property
    def observed_peak_count(self):
        return len(self.observed_peaks)

    @classmethod
    def from_mapping(cls, value):
        data = strict(cls, value)
        data["observed_peaks"] = tuple(ObservedPeak.from_mapping(x) for x in data["observed_peaks"])
        for key, parser in (("window", Window), ("actual_conditions", Conditions)):
            data[key] = parser.from_mapping(data[key])
        if type(data["frozen_predictions"]) is not FrozenCapacityPredictions:
            data["frozen_predictions"] = FrozenPredictions.from_mapping(data["frozen_predictions"])
        return cls(**data)

    def __post_init__(self):
        if self.nucleus not in ("1H", "13C") or not isinstance(self.structure, str) or not self.structure:
            raise ValueError("structure and supported nucleus are required")
        if self.missing_mask is not None:
            raise ValueError("non-None missing_mask unsupported until measurement axis/provenance is defined")
        if type(self.actual_conditions) is not Conditions or type(self.window) is not Window:
            raise ValueError("typed conditions and window required")
        if any(type(x) is not ObservedPeak for x in self.observed_peaks):
            raise ValueError("typed observed peaks required")
        if type(self.frozen_predictions) is FrozenCapacityPredictions:
            _capacity_prediction(self.frozen_predictions)
            if self.frozen_predictions.layout.nucleus != self.nucleus:
                raise ValueError("capacity nucleus differs from inference nucleus")
        elif type(self.frozen_predictions) is not FrozenPredictions:
            raise ValueError("frozen_predictions must be legacy or typed capacity predictions")
        names = [x.peak_id for x in self.observed_peaks]
        if len(set(names)) != len(names):
            raise ValueError("duplicate observed peak identity")


@dataclass(frozen=True)
class Alternative:
    environment_ids: Tuple[str, ...]
    feasibility: str
    complete_solution_id: Optional[str] = None

    def __post_init__(self):
        if self.feasibility not in ("global_feasible", "local_unconstrained"):
            raise ValueError("alternative feasibility must be explicit")
        if self.feasibility == "global_feasible":
            if not isinstance(self.complete_solution_id, str) or not self.complete_solution_id.strip():
                raise ValueError("global alternative requires a complete solution ID")
        elif self.complete_solution_id is not None:
            raise ValueError("local alternative cannot claim a complete solution ID")


@dataclass(frozen=True)
class Assignment:
    peak_id: str
    environment_ids: Tuple[str, ...]
    atom_candidates: Tuple[int, ...]
    mapping_ambiguous: bool
    unique_atom_claim: bool
    residual_ppm: Optional[Decimal]
    alternatives: Tuple[Alternative, ...]
    candidate_meaning: str = "unknown"
    candidate_basis: Optional[str] = None

    def __post_init__(self):
        ids(self.atom_candidates)
        candidate_basis(self.candidate_meaning, self.candidate_basis)
        if self.candidate_meaning == "mapping_ambiguity" and not self.mapping_ambiguous:
            raise ValueError("mapping ambiguity meaning requires ambiguous status")
        if type(self.mapping_ambiguous) is not bool or type(self.unique_atom_claim) is not bool:
            raise ValueError("mapping flags must be real booleans")
        if self.unique_atom_claim and (self.mapping_ambiguous or len(self.atom_candidates) != 1):
            raise ValueError("unique atom claim requires an unambiguous singleton")
        if self.residual_ppm is not None:
            decimal(self.residual_ppm)


@dataclass(frozen=True)
class AssignmentOutput:
    assignments: Tuple[Assignment, ...]
    unexplained_peak_ids: Tuple[str, ...]
    unreported_environment_ids: Tuple[str, ...]
    evidence: Tuple[str, ...]
    assumptions: Tuple[str, ...]

    reuse_semantics: str

    def validate_against(self, original: InferenceInput, *, joint_mapping=None, projection=None) -> None:
        """Bind identity claims conservatively to a whole-assignment unique atom map.

        This API does not certify isolated peaks while other peaks remain ambiguous.
        Integer atom candidates use exact integer-string source IDs in the map.
        """
        if self.reuse_semantics not in ("local_unconstrained", "global_exclusive"):
            raise ValueError("explicit reuse semantics required")
        peak_ids = {p.peak_id for p in original.observed_peaks}
        capacity = type(original.frozen_predictions) is FrozenCapacityPredictions
        envs = ({u.unit_id:u for u in original.frozen_predictions.layout.units} if capacity else
                {e.environment_id:e for e in original.frozen_predictions.environments})
        bound_projection = None
        if joint_mapping is not None or projection is not None:
            if not capacity or type(joint_mapping) is not JointMapping or type(projection) is not ProjectedAssignment:
                raise ValueError("projection binding requires capacity predictions, JointMapping and ProjectedAssignment")
            expected = {u.unit_id:u.nucleus_mass for u in original.frozen_predictions.layout.units}
            if dict(zip(joint_mapping.unit_ids,joint_mapping.unit_masses)) != expected:
                raise ValueError("joint mapping capacity differs from inference layout")
            if joint_mapping.partition_statuses != tuple(next(u.partition_status for u in original.frozen_predictions.layout.units
                    if u.unit_id==uid) for uid in joint_mapping.unit_ids):
                raise ValueError("joint mapping partition status differs from inference layout")
            variants = set(joint_mapping.unit_permutations)
            targets = dict(joint_mapping.target_by_unit)
            for block in original.frozen_predictions.attachment_blocks:
                positions = [joint_mapping.unit_ids.index(uid) for uid in block]
                for permutation in variants:
                    for left,right in zip(positions,positions[1:]):
                        swapped = list(permutation)
                        swapped[left],swapped[right] = swapped[right],swapped[left]
                        if (tuple(sorted(targets[permutation[left]])) != tuple(sorted(targets[permutation[right]]))
                                and tuple(swapped) not in variants):
                            raise ValueError("joint mapping omits latent attachment ambiguity")
            whole = {a.peak_id:a.environment_ids for a in self.assignments}
            whole.update({pid:() for pid in self.unexplained_peak_ids})
            computed = project_assignment(whole,joint_mapping,missing_unit_ids=self.unreported_environment_ids,
                reuse_semantics="independent_local" if self.reuse_semantics=="local_unconstrained" else "global_exclusive")
            if computed != projection:
                raise ValueError("projection must bind the entire current assignment")
            bound_projection = computed
        reported = [a.peak_id for a in self.assignments] + list(self.unexplained_peak_ids)
        if len(reported) != len(set(reported)) or set(reported) != peak_ids:
            raise ValueError("every observed peak must occur exactly once")
        used = []
        for assignment in self.assignments:
            names = assignment.environment_ids
            if not names or len(names) != len(set(names)) or not set(names) <= envs.keys():
                raise ValueError("assigned environment IDs must be distinct supplied IDs")
            if capacity:
                if len(names)>2:
                    raise ValueError("capacity assignment supports at most two units")
                if assignment.atom_candidates or assignment.unique_atom_claim:
                    if (bound_projection is None or bound_projection.level!="atom" or
                            not bound_projection.mapping_complete or not bound_projection.joint_exact or
                            bound_projection.unresolved_unit_ids):
                        raise ValueError("atom identity unsupported without complete unique atom projection and resolved units")
                    targets = dict(bound_projection.variants[0])[assignment.peak_id]
                    if tuple(sorted(str(i) for i in assignment.atom_candidates)) != tuple(sorted(targets)):
                        raise ValueError("atom candidates must equal the bound atom projection (integer-string source IDs)")
            else:
                allowed = {atom for name in names for atom in envs[name].atom_candidates}
                if not set(assignment.atom_candidates) <= allowed:
                    raise ValueError("assigned atoms must be supplied candidates")
                if any(envs[name].mapping_ambiguous for name in names):
                    if not assignment.mapping_ambiguous or assignment.unique_atom_claim:
                        raise ValueError("output must preserve supplied mapping ambiguity")
                if assignment.unique_atom_claim and original.frozen_predictions.mapping_capability != "unique_atoms":
                    raise ValueError("unique atom claim exceeds supplied capability")
            for alternative in assignment.alternatives:
                if (len(alternative.environment_ids) != len(set(alternative.environment_ids)) or
                        not set(alternative.environment_ids) <= envs.keys()):
                    raise ValueError("alternative references unknown or duplicate environment IDs")
                if self.reuse_semantics == "local_unconstrained" and alternative.feasibility != "local_unconstrained":
                    raise ValueError("local baseline cannot advertise global alternatives")
            used.extend(names)
        if self.reuse_semantics == "global_exclusive" and len(used) != len(set(used)):
            raise ValueError("global assignments cannot reuse environments")
        unreported = self.unreported_environment_ids
        if len(unreported) != len(set(unreported)) or set(unreported) != envs.keys() - set(used):
            raise ValueError("unreported environments must exactly cover unused supplied IDs")
