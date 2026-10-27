# 功能概述：构建受限的源相对参考提案，不认证原始实验归属或天然峰。
# 主要职责：build_source_reference 验证原文哈希、身份join、旧策略、序列化数组及外部联合映射；
# SourceReference 将匿名bins与hidden证据分离；coverage_ledger 汇总四层覆盖占位；
# ELEMENT_SYMBOLS/_atomic_number只校验完整周期表的符号与1..118整数编码，拒绝bool/padding。
# normalize_policy_rows 用显式核种scope和外部canonical结构函数生成独立binding旁表，原策略全文留hidden。
# CompiledReferenceContext/compile_reference_context 仅缓存immutable元数据索引，双SHA及全文绑定，无推理缓存。
# 代码库关系：复用derived_observation精确decimal分箱，不调用trusted admission或双射投影helper。
# 输入输出：纯函数，保留原JSON/targets/mask/token；异常数据返回reason，调用参数错误也不默认通过。
# transport的完整性只检查外部receipt形状，不执行化学算法；所有结果等待独审owner冻结，永不宣称admitted。
from dataclasses import dataclass, field
from collections.abc import Mapping
from decimal import Decimal
import hashlib
import json
import re
from functools import lru_cache
from types import MappingProxyType

from .derived_observation import build_serialized_value_bins


# 标准元素符号按原子序数1..118排列；仅验证编码，不推断价态或实验归属。
ELEMENT_SYMBOLS = tuple(("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca "
    "Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd "
    "In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os "
    "Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr "
    "Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og").split())
_ELEMENT_NUMBERS = {symbol: z for z, symbol in enumerate(ELEMENT_SYMBOLS, 1)}


def _atomic_number(token):
    if type(token) is int:
        return token if 1 <= token <= 118 else None
    if isinstance(token, str):
        return _ELEMENT_NUMBERS.get(token)
    return None


def text_sha256(text):
    """Hash exact UTF-8 text, including any line terminator."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _key(row):
    return (row.get("source", row.get("source_ref")), row.get("nucleus"),
            row.get("record_id"), row.get("structure_id"))


def _load(text):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("duplicate key")
            out[k] = v
        return out
    def constant(v):
        raise ValueError("nonfinite constant")
    return json.loads(text, parse_float=Decimal, parse_constant=constant, object_pairs_hook=pairs)


@dataclass(frozen=True)
class SourceReference:
    status: str
    classification: str
    reasons: tuple
    inference_bins: tuple = ()
    hidden: object = field(default_factory=dict, repr=False)
    truth_basis: str = "source_relative_current_serialization"
    reference_basis: str = "source_asserted_encoded_graph"
    trust_basis: str = "internal_source_consistency"
    proof_scope: str = "external_receipt_shape_only_owner_freeze_pending"

    def anonymous_payload(self):
        return tuple(dict(x) for x in self.inference_bins)


def build_source_reference(raw_json_line, *, source_sha256, policy_jsonl,
                           policy_sha256, cohort_manifest_json,
                           cohort_identity_manifest_sha256, transport,
                           quality_receipt=None, context=None):
    """Produce a hash-bound proposal; all label-bearing metadata stays hidden.

    Manifest: {source_sha256, policy_sha256, records:[identity plus row_sha256]}.
    Policy rows join on that exact four-field identity. transport carries the same
    binding plus joint_maps (full source slot -> baseline parent), complete,
    completeness_evidence_sha256, graph_lineage_evidence_sha256 and
    structure_only=true. These fields are declarations, not scientific verification.
    """
    reasons = []
    hidden = {"raw_json_line": raw_json_line, "trusted_experimental": False}
    bins = ()
    def fail(reason):
        reasons.append(reason)
    try:
        row = _load(raw_json_line)
        if not isinstance(row, Mapping):
            raise ValueError("row object required")
        sid = row.get("structure_id") or text_sha256(row["smiles"])
        identity = dict(source=row.get("source_ref"), nucleus=row.get("nucleus"),
                        record_id=row.get("record_id"), structure_id=sid)
        key = _key(identity)
        if any(not isinstance(x, str) or not x for x in key):
            fail("identity_missing")
        binding = dict(identity, source_sha256=source_sha256,
                       row_sha256=text_sha256(raw_json_line),
                       policy_sha256=policy_sha256,
                       cohort_identity_manifest_sha256=cohort_identity_manifest_sha256)
        hidden["binding"] = binding
        hidden["reference_original"] = row
        if not _sha(source_sha256):
            fail("source_sha_missing")
        trusted_context = compile_reference_context(policy_jsonl, policy_sha256,
            cohort_manifest_json, cohort_identity_manifest_sha256)
        if context is None:
            context = trusted_context
        if (context is not trusted_context or type(context) is not CompiledReferenceContext
                or context.policy_jsonl != policy_jsonl
                or context.cohort_manifest_json != cohort_manifest_json
                or context.policy_sha256 != policy_sha256
                or context.cohort_identity_manifest_sha256 != cohort_identity_manifest_sha256):
            fail("compiled_context_binding_mismatch")
            raise ValueError("context does not match frozen inputs")
        manifest = _load(context.manifest_header_json)
        if manifest.get("source_sha256") != source_sha256 or manifest.get("policy_sha256") != policy_sha256:
            fail("cohort_reference_binding_mismatch")
        matches = [_load(x) for x in context.cohort_index.get(key, ())]
        if len(matches) != 1:
            fail("cohort_duplicate_or_missing_join")
        elif matches[0].get("row_sha256") != binding["row_sha256"]:
            fail("cohort_row_hash_mismatch")
        matches = [_load(x) for x in context.policy_index.get(key, ())]
        if len(matches) > 1:
            fail("policy_duplicate_conflicting_join")
        policy = matches[0] if len(matches) == 1 else None
        hidden["policy"] = policy
        if policy is None:
            fail("policy_missing")
            # An external frozen equivalent audit may support construction, while
            # the missing historical-policy reason remains in the immutable result.
            q = quality_receipt if isinstance(quality_receipt, Mapping) else {}
            if not (all(q.get(k) == v for k, v in binding.items())
                    and q.get("decision") == "source_relative_keep"
                    and _sha(q.get("rules_sha256")) and _sha(q.get("evidence_sha256"))):
                fail("equivalent_quality_receipt_missing")
        else:
            if policy.get("row_sha256") != binding["row_sha256"]:
                fail("policy_row_hash_mismatch")
            normalization = policy.get("_normalization")
            if normalization is not None:
                expected_provenance = manifest.get("normalized_policy_provenance")
                fields = ("original_policy_sha256", "adapter_implementation_sha256", "nucleus_scope",
                          "reference_choice", "correction_overlay_sha256")
                if (not isinstance(expected_provenance, Mapping)
                        or any(normalization.get(k) != expected_provenance.get(k) for k in fields)
                        or not _sha(normalization.get("original_policy_sha256"))
                        or not _sha(normalization.get("adapter_implementation_sha256"))
                        or normalization.get("nucleus_scope") != row.get("nucleus")
                        or not _sha(normalization.get("canonical_structure_sha256"))
                        or text_sha256(normalization.get("original_policy_line", "")) != normalization.get("original_policy_line_sha256")):
                    fail("normalized_policy_provenance_mismatch")
                original_policy = _load(normalization.get("original_policy_line", "{}"))
                if any(policy.get(k) != v for k, v in original_policy.items()):
                    fail("normalized_policy_semantics_changed")
                if normalization.get("restriction"):
                    fail("policy_restricted")
                    fail("policy_restriction:" + str(normalization["restriction"]))
            disposition = policy.get("disposition", policy.get("quality", "unknown"))
            if (policy.get("keep_atom_parent_supervision") is not True
                    or disposition not in ("no_detected_local_conflict", "source_relative_keep", "reviewed_source_relative_keep")
                    or policy.get("weak_supervision") is True
                    or policy.get("shift_values_imputed") is True):
                fail("policy_restricted")
        n = len(row["atoms"])
        if any(len(row[k]) != n for k in ("coordinates", "atom_targets", "atom_target_mask")):
            fail("array_length_mismatch")
        # Zero/padding elements are never silently stripped or rebased.
        order = row["atom_order"]
        permutation = order["source_to_canonical"]
        numbers = order["atomic_numbers"]
        atom_numbers = [_atomic_number(a) for a in row["atoms"]]
        if (len(numbers) != n or numbers != atom_numbers
                or any(type(z) is not int or not 1 <= z <= 118 for z in numbers)
                or len(permutation) != n or any(type(i) is not int for i in permutation)
                or set(permutation) != set(range(n))):
            fail("atom_order_or_padding_invalid")
        nucleus_z = {"1H": 1, "13C": 6, "19F": 9, "31P": 15, "15N": 7,
                     "17O": 8, "11B": 5, "33S": 16}.get(row.get("nucleus"))
        if nucleus_z is None:
            fail("nucleus_unsupported")
        expected = []
        for i, (v, m) in enumerate(zip(row["atom_targets"], row["atom_target_mask"])):
            if type(m) not in (bool, int) or m not in (0, 1):
                fail("mask_invalid")
                continue
            if v is not None and (type(v) not in (int, Decimal) or not Decimal(v).is_finite()):
                fail("target_nonfinite_or_invalid")
            if not m and v is not None:
                fail("inactive_target_not_null")
            if m:
                if v is None:
                    fail("reported_target_missing")
                if i >= len(numbers) or numbers[i] != nucleus_z:
                    fail("nucleus_element_mismatch")
                expected.append((i, v))
        spectrum = row["spectrum"]
        actual = [(x["atom_index"], x["shift"]) for x in spectrum]
        if any(type(i) is not int for i, _ in actual) or sorted(actual) != expected:
            fail("spectrum_target_mismatch")
        derived = build_serialized_value_bins(raw_json_line)
        hidden["derived"] = derived
        if derived.reported_slot_count == 0:
            fail("no_known_labels")
        bins = derived.anonymous_payload()
        t = transport if isinstance(transport, Mapping) else {}
        if not all(t.get(k) == v for k, v in binding.items()):
            fail("transport_binding_mismatch")
        if (t.get("complete") is not True or not _sha(t.get("completeness_evidence_sha256"))
                or t.get("enumeration_truncated") is not False):
            fail("joint_mapping_completeness_unknown")
        if t.get("structure_only") is not True or not _sha(t.get("graph_lineage_evidence_sha256")):
            fail("graph_lineage_unsupported")
        maps = t.get("joint_maps", ())
        variants = set()
        if not isinstance(maps, (list, tuple)) or not maps:
            fail("joint_mapping_missing")
        else:
            for mapping in maps:
                if (not isinstance(mapping, Mapping) or any(type(i) is not int for i in mapping)
                        or set(mapping) != set(range(n))
                        or any(not isinstance(v, str) or not v for v in mapping.values())):
                    fail("joint_map_domain_invalid")
                    continue
                variants.add(tuple((b.bin_id, tuple(sorted({mapping[i] for i, _ in b.members})))
                                   for b in derived.hidden_provenance))
        hidden["joint_gold_variants"] = tuple(sorted(variants))
        hidden["transport"] = transport
        hidden["quality_receipt"] = quality_receipt
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, ArithmeticError) as exc:
        fail("invalid_reference:" + type(exc).__name__)
    blocking = [r for r in reasons if r != "policy_missing"]
    classification = "unknown"
    if "policy_restricted" in reasons:
        classification = "restricted"
    elif not blocking:
        classification = "parent_mapping_ambiguous" if len(hidden.get("joint_gold_variants", ())) > 1 else "unique_parent"
    hidden["gate_reasons"] = {
        "unknown": tuple(r for r in reasons if any(x in r for x in ("missing", "unknown"))),
        "unsupported": tuple(r for r in reasons if "unsupported" in r),
        "conflict": tuple(r for r in reasons if any(x in r for x in ("mismatch", "invalid", "duplicate", "restricted"))),
        "ambiguous": ("whole_joint_parent_alternatives",) if classification == "parent_mapping_ambiguous" else (),
    }
    hidden["coverage_support"] = {k: {"denominator": None, "covered": None, "status": "not_batch_counted"}
                                  for k in ("record", "structure", "unit", "atom")}
    return SourceReference("proposed_receipt", classification, tuple(dict.fromkeys(reasons)),
                           tuple(bins), hidden)


def coverage_ledger(references):
    """Return deterministic metadata rows; never treat these proposals as admitted."""
    return tuple({"status": r.status, "classification": r.classification,
                  "binding": dict(r.hidden.get("binding", {})), "reasons": r.reasons,
                  "coverage_support": r.hidden["coverage_support"]}
                 for r in references)


def normalize_policy_rows(raw_reference_lines, *, original_policy_jsonl,
                          original_policy_sha256, nucleus_scope,
                          canonicalize_structure, adapter_implementation_sha256,
                          reference_choice="raw", correction_record_ids=(),
                          correction_overlay_sha256=None):
    """Create a separate policy sidecar; never rewrite the original policy.

    canonicalize_structure is a frozen structure-only callable returning canonical
    isomeric identity text. nucleus_scope declares the original policy file scope,
    not a nucleus inferred from missing row fields. The caller retains all missing
    reference identities; this helper does not turn them into eligible policy rows.
    """
    if (text_sha256(original_policy_jsonl) != original_policy_sha256
            or not _sha(adapter_implementation_sha256)
            or not isinstance(nucleus_scope, str) or not nucleus_scope
            or reference_choice not in ("raw", "corrected")):
        raise ValueError("frozen policy/adapter/scope/reference binding required")
    corrections = set(correction_record_ids)
    if corrections and not _sha(correction_overlay_sha256):
        raise ValueError("correction identity list requires overlay SHA")
    policy_by_id = {}
    for literal in original_policy_jsonl.splitlines(keepends=True):
        if not literal.strip():
            continue
        parsed = _load(literal)
        # Preserve original semantic values and original literal separately.
        policy = json.loads(literal)
        key = (parsed.get("source", parsed.get("source_ref")), parsed.get("record_id"))
        if not all(isinstance(x, str) and x for x in key) or key in policy_by_id:
            raise ValueError("duplicate/conflicting original policy identity")
        if parsed.get("nucleus", nucleus_scope) != nucleus_scope:
            raise ValueError("original policy conflicts with declared nucleus scope")
        policy_by_id[key] = (policy, literal)
    provenance = dict(original_policy_sha256=original_policy_sha256,
                      adapter_implementation_sha256=adapter_implementation_sha256,
                      nucleus_scope=nucleus_scope, reference_choice=reference_choice,
                      correction_overlay_sha256=correction_overlay_sha256)
    normalized, missing, seen = [], [], set()
    for raw in raw_reference_lines:
        row = _load(raw)
        identity = dict(source=row.get("source_ref"), nucleus=row.get("nucleus"),
                        record_id=row.get("record_id"),
                        structure_id=row.get("structure_id") or text_sha256(row["smiles"]))
        key = _key(identity)
        if key in seen:
            raise ValueError("duplicate/conflicting reference identity")
        seen.add(key)
        original = policy_by_id.get((identity["source"], identity["record_id"]))
        if identity["nucleus"] != nucleus_scope or original is None:
            missing.append(identity)
            continue
        policy, literal = original
        canonical_source = canonicalize_structure(row["smiles"])
        canonical_policy = canonicalize_structure(policy.get("smiles"))
        if (not isinstance(canonical_source, str) or not canonical_source
                or canonical_source != canonical_policy):
            raise ValueError("policy/reference canonical structure mismatch")
        for k, value in identity.items():
            if k in policy and policy[k] != value:
                raise ValueError("policy/reference identity conflict")
        bound = dict(policy, **identity, row_sha256=text_sha256(raw))
        bound["_normalization"] = dict(provenance,
            original_policy_line=literal, original_policy_line_sha256=text_sha256(literal),
            canonical_structure_sha256=text_sha256(canonical_source))
        if reference_choice == "raw" and identity["record_id"] in corrections:
            bound["_normalization"]["restriction"] = "historical_correction_not_applied_to_raw_reference"
        normalized.append(bound)
    policy_jsonl = "".join(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n"
                           for p in normalized)
    return dict(policy_jsonl=policy_jsonl, policy_sha256=text_sha256(policy_jsonl),
                manifest_bindings=provenance, missing_policy_identities=tuple(missing))


@dataclass(frozen=True)
class CompiledReferenceContext:
    """Immutable metadata text/index cache; never caches inference or conditions."""
    policy_jsonl: str = field(repr=False)
    cohort_manifest_json: str = field(repr=False)
    policy_sha256: str
    cohort_identity_manifest_sha256: str
    manifest_header_json: str = field(repr=False)
    policy_index: object = field(repr=False)
    cohort_index: object = field(repr=False)


@lru_cache(maxsize=2)
def compile_reference_context(policy_jsonl, policy_sha256, cohort_manifest_json,
                              cohort_identity_manifest_sha256):
    """Parse frozen metadata once; indexes retain duplicates for fail-closed joins.

    Both original texts and both exact SHA values are cache keys. Cached values
    contain immutable strings/tuples/read-only mappings, never caller-mutable rows.
    """
    if (text_sha256(policy_jsonl) != policy_sha256
            or text_sha256(cohort_manifest_json) != cohort_identity_manifest_sha256
            or not _sha(policy_sha256) or not _sha(cohort_identity_manifest_sha256)):
        raise ValueError("compiled metadata hash mismatch")
    policy_index = {}
    for literal in policy_jsonl.splitlines():
        if literal.strip():
            row = _load(literal)
            policy_index.setdefault(_key(row), []).append(literal)
    manifest = _load(cohort_manifest_json)
    # Reparse with standard number representation only to serialize small metadata;
    # full original text and its hash remain the authoritative binding.
    standard = json.loads(cohort_manifest_json)
    cohort_index = {}
    for row in standard["records"]:
        cohort_index.setdefault(_key(row), []).append(json.dumps(row))
    header = {k: v for k, v in standard.items() if k != "records"}
    return CompiledReferenceContext(policy_jsonl, cohort_manifest_json, policy_sha256,
        cohort_identity_manifest_sha256, json.dumps(header),
        MappingProxyType({k: tuple(v) for k, v in policy_index.items()}),
        MappingProxyType({k: tuple(v) for k, v in cohort_index.items()}))
