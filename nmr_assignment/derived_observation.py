"""功能概述：从原 JSON 行构建单列 serialized-source-value-bin，独立于天然峰语义。
主要职责：build_serialized_value_bins 用 Decimal 精确数值相等合并已报告 targets，
不四舍五入、不用 epsilon、不推断天然 overlap。按观测数值排序编号，不泄露源原子顺序；
AnonymousBin 仅暴露匿名 ID 和规范化精确 ppm 文本（不受 Decimal context 精度影响）；
DerivedBins 将原 token/source index 留在 hidden provenance，original_precision 始终 unknown。
project_hidden_membership 接受外部完整双射备选，保留整份联合投影，不生成逐 bin 笛卡尔积。
代码库关系：独立纯标准库模块；不从标签生成结构容量、积分、条件或可信 gold。
输入输出与副作用：接受 caller 选好的单 nucleus 一维 ppm 数组和 mask 的原 JSON 行，
返回不可变对象；empty/partial 仅描述 mask 覆盖，不代表测量完整性。匿名 from_mapping
拒绝额外字段。隐藏成员可供独立 gold builder 使用，但本模块不认证来源或映射证据。
无真实数据读取、文件写入、模型、网络、缓存；非法字段、非有限数或不完整映射抛 ValueError。
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import json
from collections.abc import Mapping


@dataclass(frozen=True)
class _Number:
    token: str

    @property
    def decimal(self):
        return Decimal(self.token)


def _reject_constant(value):
    raise ValueError("nonfinite JSON number")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


@dataclass(frozen=True)
class AnonymousBin:
    bin_id: str
    ppm_decimal: str

    def __post_init__(self):
        if not isinstance(self.bin_id, str) or not self.bin_id:
            raise ValueError("bin_id must be nonempty")
        if not isinstance(self.ppm_decimal, str):
            raise ValueError("ppm_decimal requires exact decimal text")
        try:
            value = Decimal(self.ppm_decimal)
        except InvalidOperation as exc:
            raise ValueError("invalid ppm_decimal") from exc
        if not value.is_finite():
            raise ValueError("ppm_decimal must be finite")

    @classmethod
    def from_mapping(cls, value):
        if not isinstance(value, Mapping) or set(value) != {"bin_id", "ppm_decimal"}:
            raise ValueError("anonymous bins permit only bin_id and ppm_decimal")
        return cls(**value)

    def as_mapping(self):
        return {"bin_id": self.bin_id, "ppm_decimal": self.ppm_decimal}


@dataclass(frozen=True)
class HiddenBin:
    bin_id: str
    # Every raw number literal is preserved, even when numeric equality merges it.
    members: tuple


@dataclass(frozen=True)
class DerivedBins:
    inference_bins: tuple
    hidden_provenance: tuple = field(repr=False)
    source_slot_count: int
    reported_slot_count: int
    original_precision: str = field(default="unknown", init=False)
    observation_semantics: str = field(default="serialized-source-value-bin", init=False)
    gold_status: str = field(default="not_trusted_gold", init=False)

    @property
    def mask_coverage(self):
        if not self.reported_slot_count:
            return "empty"
        return "all_source_slots" if self.reported_slot_count == self.source_slot_count else "partial"

    def anonymous_payload(self):
        """Only these fields may cross the inference boundary."""
        return tuple(b.as_mapping() for b in self.inference_bins)


def _canonical_decimal(value):
    """Canonical exact text without Decimal context rounding or exponent expansion."""
    sign, digits, exponent = value.as_tuple()
    if not any(digits):
        return "0"
    digits = list(digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    coefficient = "".join(str(d) for d in digits)
    prefix = "-" if sign else ""
    return prefix + coefficient + ("e" + str(exponent) if exponent else "")


def build_serialized_value_bins(raw_json_line, *, target_field="atom_targets",
                                mask_field="atom_target_mask"):
    """Build from one caller-selected 1-D ppm column; never infer axes or units.

    Missing mask is an error. False/0 marks an unreported slot (which may be null).
    No bare verified flag admits a source: this function performs construction only.
    """
    if not isinstance(raw_json_line, str):
        raise ValueError("original JSON text required")
    try:
        source = json.loads(raw_json_line, parse_float=_Number, parse_int=_Number,
                            parse_constant=_reject_constant, object_pairs_hook=_object)
    except (json.JSONDecodeError, InvalidOperation) as exc:
        raise ValueError("invalid original JSON line") from exc
    if not isinstance(source, dict) or target_field not in source or mask_field not in source:
        raise ValueError("explicit target column and mask required")
    values, mask = source[target_field], source[mask_field]
    if not isinstance(values, list) or not isinstance(mask, list) or len(values) != len(mask):
        raise ValueError("targets and mask require equal one-dimensional arrays")
    groups = {}
    reported = 0
    for index, (value, active) in enumerate(zip(values, mask)):
        if type(active) is bool:
            pass
        elif type(active) is _Number and active.decimal in (Decimal(0), Decimal(1)):
            active = bool(active.decimal)
        else:
            raise ValueError("mask must contain booleans or numeric zero/one")
        if not active:
            continue
        if type(value) is not _Number or not value.decimal.is_finite():
            raise ValueError("reported target requires finite original JSON number")
        groups.setdefault(value.decimal, []).append((index, value.token))
        reported += 1
    public, hidden = [], []
    # Sort only observed numeric values, so IDs cannot reveal source atom ordering.
    for index, (value, members) in enumerate(sorted(groups.items())):
        bid = "bin:" + str(index)
        public.append(AnonymousBin(bid, _canonical_decimal(value)))
        hidden.append(HiddenBin(bid, tuple(members)))
    return DerivedBins(tuple(public), tuple(hidden), len(values), reported)


def project_hidden_membership(derived, external_joint_maps):
    """Project whole external bijections; result is diagnostic, never trusted gold.

    Each map must cover ALL original source slots, including masked slots; identities
    are distinct nonempty strings. Caller retains completeness and evidence externally.
    Each output variant is ((bin_id, (identity,...)),...) for one entire map.
    """
    if type(derived) is not DerivedBins:
        raise ValueError("DerivedBins required")
    maps = tuple(external_joint_maps)
    if not maps:
        raise ValueError("at least one complete external map required")
    domain = set(range(derived.source_slot_count))
    variants = set()
    for mapping in maps:
        if (not isinstance(mapping, Mapping) or any(type(k) is not int for k in mapping)
                or set(mapping) != domain):
            raise ValueError("external map must cover complete source domain")
        targets = tuple(mapping.values())
        if (any(not isinstance(t, str) or not t for t in targets) or
                len(set(targets)) != len(targets)):
            raise ValueError("external map must be a whole identity bijection")
        variants.add(tuple((b.bin_id, tuple(sorted(mapping[index] for index, _ in b.members)))
                           for b in derived.hidden_provenance))
    return tuple(sorted(variants))
