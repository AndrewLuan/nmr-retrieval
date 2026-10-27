"""功能概述：定义 NMR 结构容量、冻结中心载体与联合身份映射的纯标准库核心。
CapacityUnit/CapacityLayout 分离整数核质量与物理分区假设；build_capacity_layout
检查 registry 的母节点质量守恒，未知 H 分区保留 unresolved_parent_pool。
FrozenCarrier/FrozenCapacityPredictions 与 attach_prediction_carriers 保留同一核容量
的多中心分布；小数成分质量仅归一化为混合权重，不增加可归属原子数。
JointMapping/make_joint_mapping 校验完整置换与身份引用；project_assignment 对整个
归属应用同一个合法映射，并报告各峰在全部映射下是否一致。截断枚举不能证明唯一。
MetricEligibility/metric_eligibility 将独立 gold 分母资格与预测能力分开，避免未知输出
缩小准确率分母。结构证据和映射完整性证明由上游提供，布尔声明不能替代独立审核。
源图缺立体标记不表示原样本无手性；source 原子顺序、同位素、立体及等价条件须有
原始证据或明确假设集合。AddHs 生成的 H 槽不自动继承真实源 H 身份。
关系：供 nmr_assignment 的适配器接入现有 solver；本文件不依赖 contracts、模型或
RDKit。tests/assignment/test_mapping.py 覆盖质量、联合置换、重编号与保守回退。
输入输出与副作用：接受显式字典/不可变 dataclass，返回不可变对象。非法质量、引用或
置换抛 ValueError；无文件、网络、训练、前向、全局缓存或持久化副作用。浮点容差仅用于
成分质量算术校验，不是化学位移 gate。中心选择与真实氢身份的证据保持分离。
"""
from dataclasses import dataclass
from math import fsum, isclose, isfinite
from itertools import permutations
from typing import Mapping, Optional, Tuple


MASS_REL_TOL = 1e-9
MASS_ABS_TOL = 1e-9
PARTITION_KINDS = ("registry_hypothesis", "unresolved_parent_pool", "atom_capacity")
MAPPING_BASES = ("provenance_lineage", "graph_mapping_ambiguity",
                 "latent_attachment_ambiguity", "certified_chemical_equivalence")


def _name(value):
    if not isinstance(value, str) or not value:
        raise ValueError("identity must be a nonempty string")
    return value


def _names(values, *, nonempty=True):
    if isinstance(values, str):
        raise ValueError("identities require a sequence, not one string")
    result = tuple(_name(x) for x in values)
    if len(set(result)) != len(result) or (nonempty and not result):
        raise ValueError("identities must be distinct and nonempty")
    return result


def _positive_int(value):
    if type(value) is not int or value <= 0:
        raise ValueError("nuclear capacity must be a positive integer")
    return value


def _number(value, *, positive=False):
    if isinstance(value, (bool, str)):
        raise ValueError("numeric fields require numbers")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid number") from exc
    if not isfinite(result) or (positive and result <= 0):
        raise ValueError("numeric field must be finite and satisfy its range")
    return result


def _mass(items):
    if not isinstance(items, Mapping) or not items:
        raise ValueError("parent mass requires a nonempty mapping")
    result = tuple(sorted((_name(k), _positive_int(v)) for k, v in items.items()))
    return result


def _equal_mass(actual, expected):
    return isclose(actual, expected, rel_tol=MASS_REL_TOL, abs_tol=MASS_ABS_TOL)


@dataclass(frozen=True)
class CapacityUnit:
    unit_id: str
    environment_id: str
    parent_mass: Tuple[Tuple[str, int], ...]
    nucleus_mass: int
    partition_status: str
    evidence_ids: Tuple[str, ...]

    def __post_init__(self):
        _name(self.unit_id)
        _name(self.environment_id)
        _positive_int(self.nucleus_mass)
        if self.partition_status not in PARTITION_KINDS:
            raise ValueError("unsupported partition status")
        if not self.parent_mass or len(dict(self.parent_mass)) != len(self.parent_mass):
            raise ValueError("parent claims must be distinct")
        for parent, mass in self.parent_mass:
            _name(parent)
            _positive_int(mass)
        if sum(mass for _, mass in self.parent_mass) != self.nucleus_mass:
            raise ValueError("unit nuclear mass differs from parent claims")
        _names(self.evidence_ids)


@dataclass(frozen=True)
class CapacityLayout:
    nucleus: str
    units: Tuple[CapacityUnit, ...]
    parent_mass_totals: Tuple[Tuple[str, int], ...]
    structural_environment_count: Optional[int]
    partition_hypothesis_id: str

    def __post_init__(self):
        if self.nucleus not in ("1H", "13C"):
            raise ValueError("only 1H and 13C capacities are supported")
        _name(self.partition_hypothesis_id)
        _names([u.unit_id for u in self.units])
        _names([u.environment_id for u in self.units])
        expected = dict(self.parent_mass_totals)
        if not expected or len(expected) != len(self.parent_mass_totals):
            raise ValueError("parent totals require distinct identities")
        for parent, mass in expected.items():
            _name(parent)
            _positive_int(mass)
        actual = {parent: 0 for parent in expected}
        for unit in self.units:
            for parent, mass in unit.parent_mass:
                if parent not in actual:
                    raise ValueError("unit references an unknown parent")
                actual[parent] += mass
        if actual != expected:
            raise ValueError("partition does not conserve parent nuclear mass")
        kinds = {unit.partition_status for unit in self.units}
        if len(kinds) != 1:
            raise ValueError("one problem must use one partition hypothesis")
        if self.structural_environment_count is not None:
            if (type(self.structural_environment_count) is not int or
                    self.structural_environment_count != len(self.units) or
                    kinds != {"registry_hypothesis"}):
                raise ValueError("physical environment count needs a complete registry partition")
        elif kinds == {"registry_hypothesis"}:
            raise ValueError("complete registry partition requires its environment count")
        if self.nucleus == "13C" and any(v != 1 for v in expected.values()):
            raise ValueError("each carbon graph node contributes exactly one C nucleus")


def build_capacity_layout(structure_evidence, registry_entry=None):
    """Build capacity from verified eligible-nucleus counts, never from centers or gold.

    structure_evidence: nucleus, parent_mass {str:int}, evidence_ids,
    isotope_count_verified=True, partition_hypothesis_id; registry use also needs
    partition_evidence_ids. registry_entry has groups [{unit_id, parents, mass}].
    Parent IDs must already be canonical graph addresses converted to strings.
    """
    if structure_evidence.get("isotope_count_verified") is not True:
        raise ValueError("eligible isotope-specific nuclear count is not verified")
    nucleus = structure_evidence["nucleus"]
    expected = _mass(structure_evidence["parent_mass"])
    evidence = _names(structure_evidence["evidence_ids"])
    hypothesis = _name(structure_evidence["partition_hypothesis_id"])
    groups = None if registry_entry is None else registry_entry.get("groups")
    units = []
    if groups:
        partition_evidence = _names(structure_evidence.get("partition_evidence_ids", ()))
        for i, group in enumerate(groups):
            uid = _name(group.get("unit_id", "group:" + str(i)))
            claims = _mass(group["parents"])
            mass = _positive_int(group["mass"])
            units.append(CapacityUnit(uid, uid, claims, mass,
                                      "registry_hypothesis", evidence + partition_evidence))
        count = len(units)
        reported_count = registry_entry.get("counts", {}).get(nucleus)
        if reported_count is not None and (type(reported_count) is not int or reported_count != count):
            raise ValueError("registry count differs from its groups")
    else:
        kind = "atom_capacity" if nucleus == "13C" else "unresolved_parent_pool"
        for parent, mass in expected:
            uid = "parent:" + parent
            units.append(CapacityUnit(uid, uid, ((parent, mass),), mass, kind, evidence))
        count = None
    return CapacityLayout(nucleus, tuple(units), expected, count, hypothesis)


@dataclass(frozen=True)
class FrozenCarrier:
    carrier_id: str
    unit_id: str
    center_ppm: float
    mixture_weight: float
    sigma_ppm: Optional[float]
    sigma_source: str
    source_component_ids: Tuple[str, ...]

    def __post_init__(self):
        _name(self.carrier_id)
        _name(self.unit_id)
        _number(self.center_ppm)
        weight = _number(self.mixture_weight, positive=True)
        if weight > 1 + MASS_ABS_TOL:
            raise ValueError("carrier probability exceeds one")
        if self.sigma_ppm is not None:
            _number(self.sigma_ppm, positive=True)
            if self.sigma_source == "unknown":
                raise ValueError("a known sigma requires a source")
        elif self.sigma_source != "unknown":
            raise ValueError("absent sigma must retain unknown source")
        _name(self.sigma_source)
        _names(self.source_component_ids)


@dataclass(frozen=True)
class FrozenCapacityPredictions:
    layout: CapacityLayout
    carriers: Tuple[FrozenCarrier, ...]
    attachment_blocks: Tuple[Tuple[str, ...], ...]
    attachment_evidence_ids: Tuple[str, ...]
    branch_semantics: str = "owner_marginal"

    def __post_init__(self):
        _names([r.carrier_id for r in self.carriers])
        units = {u.unit_id: u for u in self.layout.units}
        weights = {uid: [] for uid in units}
        components = []
        for carrier in self.carriers:
            if carrier.unit_id not in units:
                raise ValueError("carrier references an unknown unit")
            weights[carrier.unit_id].append(carrier.mixture_weight)
            components.extend(carrier.source_component_ids)
        _names(components)
        if any(not _equal_mass(fsum(ws), 1.) for ws in weights.values()):
            raise ValueError("each capacity needs normalized carrier weights")
        seen = set()
        for block in self.attachment_blocks:
            _names(block)
            if len(block) < 2 or any(uid not in units for uid in block) or seen.intersection(block):
                raise ValueError("attachment blocks must be disjoint known nonsingleton units")
            if len({units[uid].nucleus_mass for uid in block}) != 1:
                raise ValueError("attachment permutation must preserve nuclear mass")
            seen.update(block)
        _names(self.attachment_evidence_ids, nonempty=bool(self.attachment_blocks))
        if self.branch_semantics != "owner_marginal":
            raise ValueError("joint branch correlations require a separate model contract")


def attach_prediction_carriers(layout, frozen_components, model_layout=None):
    """Attach frozen component mass to proven units; coalesce only exactly equal values.

    Each component has component_id, owner_id, center_ppm, mass and optionally
    sigma_ppm/sigma_source. model_layout supplies component_unit_ids when parent
    claims are split, plus optional attachment_blocks/attachment_evidence_ids.
    Unit binding uses component indices, never center order or proximity.
    """
    model_layout = {} if model_layout is None else model_layout
    bindings = model_layout.get("component_unit_ids", {})
    units = {u.unit_id: u for u in layout.units}
    components = tuple(frozen_components)
    component_ids = _names([c["component_id"] for c in components])
    if set(bindings) - set(component_ids):
        raise ValueError("binding references an unknown component")
    by_unit = {uid: [] for uid in units}
    owner_mass = {parent: [] for parent, _ in layout.parent_mass_totals}
    unit_parent_mass = {uid: {p: [] for p, _ in u.parent_mass} for uid, u in units.items()}
    for component in components:
        cid = component["component_id"]
        owner = _name(component["owner_id"])
        if owner not in owner_mass:
            raise ValueError("component references an unknown parent")
        mass = _number(component["mass"], positive=True)
        center = _number(component["center_ppm"])
        sigma = component.get("sigma_ppm")
        sigma = None if sigma is None else _number(sigma, positive=True)
        source = component.get("sigma_source", "unknown")
        _name(source)
        if (sigma is None) != (source == "unknown"):
            raise ValueError("sigma presence and source disagree")
        uid = bindings.get(cid)
        if uid is None:
            choices = [u.unit_id for u in layout.units if owner in dict(u.parent_mass)]
            if len(choices) != 1:
                raise ValueError("split parent requires explicit model-layout component binding")
            uid = choices[0]
        if uid not in units or owner not in unit_parent_mass[uid]:
            raise ValueError("component binding violates unit parent claims")
        owner_mass[owner].append(mass)
        unit_parent_mass[uid][owner].append(mass)
        by_unit[uid].append((cid, center, mass, sigma, source))
    for parent, expected in layout.parent_mass_totals:
        if not _equal_mass(fsum(owner_mass[parent]), expected):
            raise ValueError("component mass does not conserve parent nuclear mass")
    result = []
    for uid, unit in units.items():
        for parent, expected in unit.parent_mass:
            if not _equal_mass(fsum(unit_parent_mass[uid][parent]), expected):
                raise ValueError("component binding does not conserve unit parent mass")
        equal = {}
        for cid, center, mass, sigma, source in sorted(by_unit[uid]):
            equal.setdefault((center, sigma, source), []).append((cid, mass))
        for index, ((center, sigma, source), rows) in enumerate(equal.items()):
            result.append(FrozenCarrier(uid + ":carrier:" + str(index), uid, center,
                fsum(mass for _, mass in rows) / unit.nucleus_mass, sigma, source,
                tuple(cid for cid, _ in rows)))
    blocks = tuple(tuple(block) for block in model_layout.get("attachment_blocks", ()))
    proof = tuple(model_layout.get("attachment_evidence_ids", ()))
    return FrozenCapacityPredictions(layout, tuple(result), blocks, proof)


@dataclass(frozen=True)
class JointMapping:
    unit_ids: Tuple[str, ...]
    target_by_unit: Tuple[Tuple[str, Tuple[str, ...]], ...]
    unit_permutations: Tuple[Tuple[str, ...], ...]
    level: str
    complete: bool
    basis: str
    evidence_ids: Tuple[str, ...]
    completeness_evidence_id: Optional[str]
    target_universe: Tuple[str, ...]
    unit_masses: Tuple[int, ...]
    partition_statuses: Tuple[str, ...]

    def __post_init__(self):
        ids = _names(self.unit_ids)
        universe = _names(self.target_universe)
        _names(self.evidence_ids)
        if self.level not in ("atom", "parent", "group") or self.basis not in MAPPING_BASES:
            raise ValueError("unsupported identity level or mapping basis")
        if type(self.complete) is not bool:
            raise ValueError("mapping completeness must be explicit")
        if self.complete:
            _name(self.completeness_evidence_id)
        elif self.completeness_evidence_id is not None:
            raise ValueError("incomplete mapping cannot carry a completeness proof")
        if len(self.unit_masses) != len(ids):
            raise ValueError("unit masses must cover the mapping domain")
        if (len(self.partition_statuses) != len(ids) or
                any(s not in PARTITION_KINDS for s in self.partition_statuses)):
            raise ValueError("mapping must retain capacity partition status")
        mass = dict(zip(ids, (_positive_int(x) for x in self.unit_masses)))
        target = dict(self.target_by_unit)
        if len(self.target_by_unit) != len(ids) or set(target) != set(ids):
            raise ValueError("targets must cover exactly the unit domain")
        all_targets = []
        for uid in ids:
            if isinstance(target[uid], str) or len(target[uid]) != mass[uid]:
                raise ValueError("target count differs from nuclear capacity")
            if any(_name(x) not in universe for x in target[uid]):
                raise ValueError("target is outside the declared universe")
            all_targets.extend(target[uid])
        if self.level == "atom" and len(set(all_targets)) != len(all_targets):
            raise ValueError("two capacities cannot claim the same source atom")
        if (not self.unit_permutations or
                len(set(self.unit_permutations)) != len(self.unit_permutations)):
            raise ValueError("joint maps must be nonempty and distinct")
        for permutation in self.unit_permutations:
            if len(permutation) != len(ids) or set(permutation) != set(ids):
                raise ValueError("each joint map must be a whole-unit bijection")
            if any(mass[a] != mass[b] for a, b in zip(ids, permutation)):
                raise ValueError("joint maps must preserve unit nuclear mass")


def _attachment_maps(ids, blocks):
    """Lazily enumerate disjoint block bijections so the caller can bound work."""
    def visit(index, current):
        if index == len(blocks):
            yield tuple(current[uid] for uid in ids)
            return
        block = blocks[index]
        for order in permutations(block):
            changed = dict(current)
            changed.update(zip(block, order))
            yield from visit(index + 1, changed)
    yield from visit(0, dict(zip(ids, ids)))


def make_joint_mapping(layout, target_by_unit, unit_permutations, *, level,
                       complete, basis, evidence_ids, target_universe,
                       completeness_evidence_id=None, attachment_blocks=(),
                       attachment_evidence_ids=(), max_joint_maps=4096):
    """Validate whole-unit bijections, not independent peak-level option sets.

    target_by_unit values contain one target per nucleus. Repeated parent/group
    targets encode resource mass, not measured integration. Atom targets are unique.
    A complete=True declaration requires an upstream completeness proof locator.
    """
    ids = tuple(u.unit_id for u in layout.units)
    universe = _names(target_universe)
    if set(target_by_unit) != set(ids):
        raise ValueError("target mapping must cover exactly all units")
    if level not in ("atom", "parent", "group") or basis not in MAPPING_BASES:
        raise ValueError("unsupported identity level or mapping basis")
    if type(complete) is not bool:
        raise ValueError("mapping completeness must be explicit")
    proof = _names(evidence_ids)
    if complete:
        _name(completeness_evidence_id)
    elif completeness_evidence_id is not None:
        raise ValueError("incomplete enumeration cannot carry a completeness proof")
    targets = []
    all_atoms = []
    masses = {u.unit_id: u.nucleus_mass for u in layout.units}
    for uid in ids:
        if isinstance(target_by_unit[uid], str):
            raise ValueError("target entries require a sequence")
        values = tuple(_name(t) for t in target_by_unit[uid])
        if len(values) != masses[uid] or set(values) - set(universe):
            raise ValueError("target mapping violates nuclear count or target universe")
        targets.append((uid, values))
        all_atoms.extend(values)
    if level == "atom" and len(set(all_atoms)) != len(all_atoms):
        raise ValueError("two capacities cannot claim the same source atom")
    permutations = tuple(tuple(p) for p in unit_permutations)
    if not permutations or len(set(permutations)) != len(permutations):
        raise ValueError("joint maps must be nonempty and distinct")
    for permutation in permutations:
        if len(permutation) != len(ids) or set(permutation) != set(ids):
            raise ValueError("each joint map must be a whole-unit bijection")
        if any(masses[src] != masses[dst] for src, dst in zip(ids, permutation)):
            raise ValueError("joint map must preserve unit nuclear mass")
    # The model's latent attachment permutations must be composed with source maps.
    _positive_int(max_joint_maps)
    blocks = tuple(_names(block) for block in attachment_blocks)
    seen = set()
    for block in blocks:
        if len(block) < 2 or set(block) - set(ids) or seen.intersection(block):
            raise ValueError("attachment blocks must be disjoint known nonsingleton units")
        if len({masses[uid] for uid in block}) != 1:
            raise ValueError("attachment permutations must preserve nuclear mass")
        seen.update(block)
    attach_proof = _names(attachment_evidence_ids, nonempty=bool(blocks))
    proof = tuple(dict.fromkeys(proof + attach_proof))
    # A block whose targets coincide under EVERY source map is provably invisible
    # at this projection level. This avoids factorial methyl-H expansion for parents.
    active = []
    for block in blocks:
        if any(len({tuple(sorted(target_by_unit[dict(zip(ids, base))[uid]]))
                    for uid in block}) > 1 for base in permutations):
            active.append(block)
    expanded = set()
    truncated = False
    attempts = 0
    for attach in _attachment_maps(ids, active):
        for base in permutations:
            attempts += 1
            if attempts > max_joint_maps:
                truncated = True
                break
            source = dict(zip(ids, base))
            combined = tuple(source[uid] for uid in attach)
            expanded.add(combined)
            if len(expanded) > max_joint_maps:
                expanded.remove(combined)
                truncated = True
                break
        if truncated:
            break
    if truncated:
        complete = False
        completeness_evidence_id = None
    return JointMapping(ids, tuple(targets), tuple(sorted(expanded)), level, complete,
                        basis, proof, completeness_evidence_id, universe,
                        tuple(masses[uid] for uid in ids),
                        tuple(u.partition_status for u in layout.units))


@dataclass(frozen=True)
class ProjectedAssignment:
    level: str
    variants: Tuple[Tuple[Tuple[str, Tuple[str, ...]], ...], ...]
    per_observation_exact: Tuple[Tuple[str, bool], ...]
    mapping_complete: bool
    joint_exact: bool
    missing_unit_ids: Tuple[str, ...]
    reuse_semantics: str
    unresolved_unit_ids: Tuple[str, ...]


def project_assignment(assignment, joint_mapping, *, missing_unit_ids=None,
                       reuse_semantics="global_exclusive"):
    """Apply each legal whole map to all observations; never form Cartesian options."""
    if reuse_semantics not in ("global_exclusive", "independent_local"):
        raise ValueError("reuse semantics must be explicit")
    ids = joint_mapping.unit_ids
    # Validate caller-created dataclass instances too; no unchecked mapping shortcut.
    if (not ids or len(set(ids)) != len(ids) or not joint_mapping.unit_permutations or
            set(dict(joint_mapping.target_by_unit)) != set(ids) or
            any(len(p) != len(ids) or set(p) != set(ids) for p in joint_mapping.unit_permutations)):
        raise ValueError("invalid joint mapping")
    if joint_mapping.complete and not joint_mapping.completeness_evidence_id:
        raise ValueError("complete mapping requires a proof locator")
    if not isinstance(assignment, Mapping):
        raise ValueError("assignment must map observation IDs to unit sequences")
    chosen = []
    normalized = []
    for observation, units in sorted(assignment.items()):
        _name(observation)
        units = _names(units, nonempty=False)
        if len(units) > 2 or set(units) - set(ids):
            raise ValueError("assignment requires at most two known distinct units")
        chosen.extend(units)
        normalized.append((observation, units))
    if reuse_semantics == "global_exclusive" and len(chosen) != len(set(chosen)):
        raise ValueError("a capacity cannot be assigned to two observations")
    missing = tuple(sorted(set(ids) - set(chosen)))
    if missing_unit_ids is not None and set(_names(missing_unit_ids, nonempty=False)) != set(missing):
        raise ValueError("missing units must complement assigned units")
    targets = dict(joint_mapping.target_by_unit)
    variants = set()
    for permutation in joint_mapping.unit_permutations:
        mapping = dict(zip(ids, permutation))
        variants.add(tuple((obs, tuple(sorted(t for uid in units for t in targets[mapping[uid]])))
                           for obs, units in normalized))
    variants = tuple(sorted(variants))
    exact = tuple((obs, joint_mapping.complete and
                   len({dict(variant)[obs] for variant in variants}) == 1)
                  for obs, _ in normalized)
    return ProjectedAssignment(joint_mapping.level, variants, exact,
                               joint_mapping.complete,
                               joint_mapping.complete and len(variants) == 1,
                               missing, reuse_semantics,
                               tuple(uid for uid, status in zip(ids, joint_mapping.partition_statuses)
                                     if status == "unresolved_parent_pool"))


@dataclass(frozen=True)
class MetricEligibility:
    metric: str
    gold_eligible: bool
    prediction_supported: bool
    reason_codes: Tuple[str, ...]


def metric_eligibility(evidence, projection, *, metric):
    """Separate pre-frozen gold denominator from prediction failures/abstentions.

    This does not calculate accuracy or certify source evidence. Independent gold
    admission supplies explicit booleans and evidence locators. Unknown output
    remains inside any previously admitted denominator.
    """
    if metric not in ("exact_atom", "exact_parent", "exact_group", "compatibility", "whole_molecule"):
        raise ValueError("unknown metric")
    reasons = []
    required = ["spectrum_authentic", "observation_semantics_verified", "independent_gold_verified",
                "assignment_provenance_verified", "stereo_scope_verified", "isotope_scope_verified"]
    if metric == "exact_atom":
        required += ["atom_assignment_verified"]
    elif metric == "exact_parent":
        required += ["parent_assignment_verified"]
    elif metric == "exact_group":
        required += ["chemical_group_assignment_verified"]
    elif metric == "compatibility":
        required += ["joint_allowed_set_verified", "joint_allowed_set_nontrivial"]
    else:
        required += ["full_assignment_gold", "measurement_completeness_verified",
                     "window_and_conditions_verified"]
    for key in required:
        if evidence.get(key) is not True:
            reasons.append("gold:" + key)
    try:
        _names(evidence.get("gold_evidence_ids", ()))
    except ValueError:
        reasons.append("gold:missing_evidence_locators")
    eligible = not reasons
    expected_level = {"exact_atom": "atom", "exact_parent": "parent", "exact_group": "group"}.get(metric)
    supported = projection.mapping_complete
    if expected_level:
        supported = supported and projection.level == expected_level and projection.joint_exact
    if metric == "whole_molecule":
        supported = supported and projection.joint_exact and projection.reuse_semantics == "global_exclusive"
    if metric in ("exact_atom", "exact_group", "whole_molecule") and projection.unresolved_unit_ids:
        supported = False
        reasons.append("prediction:unresolved_parent_capacity")
    if not supported:
        reasons.append("prediction:unresolved_or_incomplete_identity")
    return MetricEligibility(metric, eligible, supported, tuple(reasons))
