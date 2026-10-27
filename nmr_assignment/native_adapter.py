"""功能概述：把单图原生 owner/component/layout 数组接到结构容量与冻结载体核心。
adapt_native_predictions 接收上游已换算的 ppm 中心、逐成分质量及 sigma；返回
FrozenCapacityPredictions，其 layout 是唯一核容量，carrier 只表示同容量的中心分布。
_known_partition 从 equivalence_ids 的原始行列顺序核验 H 母节点并创建组容量；
_orbit_blocks 核验 preserved 轨道大小和匿名 ordinal，保留跨 parent 的整体 attachment 歧义。
代码库关系：仅依赖 nmr_assignment.mapping 的 build_capacity_layout 与
attach_prediction_carriers；不加载 torch/RDKit/checkpoint，不解析 gold/source 记录。
输入输出与副作用：所有输入为已规范化的 Python 序列和显式结构证据。证据定位符、
同位素核数认证和分区假设由调用方提交，本模块不默认生成 proof，也不认证其真实性。
known H 必须传完整 preserved 轨道；unknown H 保留 parent pool；C 每 owner 容量1。
sigma 按成分索引保留，不求均值；中心不重复换算单位。非法顺序、质量、证据或布局
抛 ValueError；无网络、文件、训练、缓存或全局状态修改。
"""
from collections import Counter, defaultdict
from .mapping import build_capacity_layout, attach_prediction_carriers


def _integer(value, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("native indices must be integers in range")
    return value


def _evidence(values, *, needed):
    if isinstance(values, str):
        raise ValueError("evidence locators require a sequence")
    result = tuple(values)
    if (any(not isinstance(x, str) or not x.strip() for x in result) or
            len(result) != len(set(result)) or (needed and not result)):
        raise ValueError("explicit evidence locators are required")
    return result


def _vector(values, size, name):
    if isinstance(values, (str, bytes)):
        raise ValueError(name + " requires a normalized sequence")
    result = tuple(values)
    if len(result) != size:
        raise ValueError(name + " length differs from component count")
    return result


def _known_partition(owners, masses, equivalence_ids):
    if equivalence_ids is None:
        raise ValueError("known H requires equivalence_ids")
    parents, gids = [], []
    for parent, row in enumerate(equivalence_ids):
        if len(row) != 6:
            raise ValueError("native equivalence layout must have six slots per node")
        for gid in row:
            _integer(gid, minimum=-1)
            if gid >= 0:
                parents.append(parent)
                gids.append(gid)
    if tuple(parents) != owners:
        raise ValueError("known H component order differs from layout parents")
    if any(isinstance(m, (bool, str)) or m != 1 for m in masses):
        raise ValueError("known preserved H components must have mass one")
    claims = defaultdict(Counter)
    for owner, gid in zip(parents, gids):
        claims[gid][str(owner)] += 1
    groups = [dict(unit_id="group:" + str(gid), parents=dict(claims[gid]),
                   mass=sum(claims[gid].values())) for gid in sorted(claims)]
    return groups, tuple(gids)


def _orbit_blocks(gids, orbits, ordinal, sizes):
    if any(v is None for v in (orbits, ordinal, sizes)):
        raise ValueError("known preserved H requires full orbit metadata")
    arrays = tuple(tuple(a) for a in (orbits, ordinal, sizes))
    if len({len(a) for a in arrays}) != 1:
        raise ValueError("preserved orbit arrays differ in length")
    by_orbit = defaultdict(list)
    for gid in sorted(set(gids)):
        if gid >= len(arrays[0]):
            raise ValueError("group outside preserved orbit arrays")
        orbit, order, size = (a[gid] for a in arrays)
        _integer(orbit); _integer(order); _integer(size, minimum=1)
        by_orbit[orbit].append((gid, order, size))
    blocks = []
    for rows in by_orbit.values():
        if (any(size != len(rows) for _, _, size in rows) or
                sorted(order for _, order, _ in rows) != list(range(len(rows)))):
            raise ValueError("orbit size or ordinal is inconsistent")
        if len(rows) > 1:
            blocks.append(tuple("group:" + str(gid) for gid, _, _ in rows))
    return tuple(blocks)


def adapt_native_predictions(structure_evidence, *, centers_ppm, masses, owners,
                             graph_indices, sigma_ppm, sigma_sources,
                             known_h_layout, layout_evidence_ids,
                             attachment_evidence_ids, equivalence_ids=None,
                             preserved_group_orbits=None,
                             preserved_group_ordinal=None,
                             preserved_group_sizes=None):
    """Normalize one graph; return immutable capacity/carriers without atom identity.

    owners are zero-based canonical graph-node indices; every graph index is zero.
    structure_evidence must carry verified parent_mass and actual evidence locators.
    Caller supplies sigma per component, including explicit None/"unknown".
    """
    if type(known_h_layout) is not bool:
        raise ValueError("known_h_layout must be explicit boolean")
    centers = tuple(centers_ppm)
    if not centers:
        raise ValueError("native component list must be nonempty")
    size = len(centers)
    owner = _vector(owners, size, "owners")
    for node in owner:
        _integer(node)
    mass = _vector(masses, size, "masses")
    graphs = _vector(graph_indices, size, "graph_indices")
    if any(type(g) is not int or g != 0 for g in graphs):
        raise ValueError("adapter accepts exactly one graph with index zero")
    sigmas = _vector(sigma_ppm, size, "sigma_ppm")
    sources = _vector(sigma_sources, size, "sigma_sources")
    layout_proof = _evidence(layout_evidence_ids, needed=known_h_layout)
    attachment_proof = _evidence(attachment_evidence_ids, needed=False)
    evidence = dict(structure_evidence)
    nucleus = evidence.get("nucleus")
    if nucleus not in ("1H", "13C"):
        raise ValueError("unsupported nucleus")
    for parent in evidence.get("parent_mass", {}):
        if not isinstance(parent, str) or not parent.isdecimal() or str(int(parent)) != parent:
            raise ValueError("parent evidence requires canonical graph-node string IDs")
    registry = None
    bindings = {}
    blocks = ()
    if known_h_layout:
        if nucleus != "1H":
            raise ValueError("known H layout cannot describe C")
        groups, gids = _known_partition(owner, mass, equivalence_ids)
        registry = {"groups": groups}
        blocks = _orbit_blocks(gids, preserved_group_orbits,
                               preserved_group_ordinal, preserved_group_sizes)
        if blocks and not attachment_proof:
            raise ValueError("latent attachment blocks require explicit evidence")
        prior = _evidence(evidence.get("partition_evidence_ids", ()), needed=True)
        evidence["partition_evidence_ids"] = tuple(dict.fromkeys(prior + layout_proof))
        bindings = {"component:" + str(i): "group:" + str(gid)
                    for i, gid in enumerate(gids)}
    elif any(x is not None for x in (preserved_group_orbits,
                                      preserved_group_ordinal, preserved_group_sizes)):
        raise ValueError("unknown layout cannot carry a preserved-group identity claim")
    elif equivalence_ids is not None:
        if any(gid != -1 for row in equivalence_ids for gid in row):
            raise ValueError("unknown layout cannot contain active equivalence groups")
    layout = build_capacity_layout(evidence, registry)
    components = []
    for i, (center, weight, node, sigma, source) in enumerate(
            zip(centers, mass, owner, sigmas, sources)):
        # 数值、质量守恒及sigma来源一致性由mapping核心统一检查；不重新缩放或平均。
        components.append(dict(component_id="component:" + str(i),
                               owner_id=str(node), center_ppm=center, mass=weight,
                               sigma_ppm=sigma, sigma_source=source))
    return attach_prediction_carriers(layout, components, {
        "component_unit_ids": bindings,
        "attachment_blocks": blocks,
        "attachment_evidence_ids": attachment_proof,
    })
