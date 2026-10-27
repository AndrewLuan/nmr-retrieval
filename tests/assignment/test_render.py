# 功能概述：用合成输入验证峰归属展示，不使用实验数据、模型或评分器。
# 主要职责：检查 AddHs 编号、SVG 命中区、显式关系、组颜色、集合联动引用、转义与置信口径。
# 代码库关系：仅调用 nmr_assignment.render 的公开 API；pytest 提供断言和参数化。
# 输入输出：无持久化产物；失败直接报告契约偏差。
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
import pytest
from rdkit import Chem
from nmr_assignment.render import numbered_molecule, render_report


def test_ethanol_full_graph_numbering():
    svg, count = numbered_molecule("CCO")
    assert count == 9
    assert svg.startswith("<svg")
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    assert [a.GetSymbol() for a in mol.GetAtoms()] == ["C", "C", "O"] + ["H"] * 6
    result = render_report("CCO", [{"raw_peak": "1.20", "unit": "ppm",
        "candidates": [{"atom_indices": set(range(3, 9)), "parent_indices": {0, 1, 2},
                        "carrier_id": "h-set", "environment_id": "env",
                        "ambiguity_meaning": "unresolved carrier",
                        "ambiguity_basis": "supplied equivalence"}]}])
    assert "{3, 4, 5, 6, 7, 8}" in result
    assert 'data-relation="unknown"' in result
    assert "ambiguous (set-valued)" not in result
    assert 'data-relation="equivalent_group"' not in result
    assert "1.20" in result and "ppm" in result
    assert result.count("<svg") == 1
    assert "Source mapping status: pending" in result
    assert "not proof of source atom mapping" in result


def test_isotope_charge_stereo_retained():
    # RDKit SVG class references retain the isotope-bearing atom identity.
    svg, count = numbered_molecule("[2H][C@H](F)[NH3+]")
    assert count == 8
    assert "atom-0" in svg
    assert "atom-1" in svg
    assert "bond-" in svg
    # Compare normal isotope case: isotope contributes extra glyph geometry.
    plain, _ = numbered_molecule("[H][C@H](F)[NH3+]")
    assert svg != plain


def test_escape_and_supplied_alternatives():
    attack = '<script>alert("x")</script>'
    result = render_report("CCO", [{"raw_peak": attack, "unit": attack,
        "candidates": [{"environment_id": attack, "atom_indices": {3, 4}}],
        "prediction_text": attack, "residual_text": "0.2 ppm",
        "alternatives": [{"scope": "global", "complete_solution_id": attack,
                          "candidates": [{"atom_indices": {5}}]}]}],
        title=attack, evidence=[attack], assumptions=[attack],
        unexplained_peaks=[attack], unreported_atom_indices={6, 7, 8})
    # One fixed interaction script is expected; supplied script tags stay text.
    assert result.count("<script>") == 1
    assert '<script>alert("x")</script>' not in result
    assert "&lt;script&gt;" in result
    assert "scope: global" in result and "complete_solution_id:" in result
    assert "0.2 ppm" in result and "{6, 7, 8}" in result


@pytest.mark.parametrize("smiles", ["", "not smiles", "C("])
def test_invalid_smiles(smiles):
    with pytest.raises(ValueError):
        numbered_molecule(smiles)


@pytest.mark.parametrize("indices", [{9}, {-1}, {True}, ["3"]])
def test_invalid_atom_references(indices):
    with pytest.raises(ValueError):
        render_report("CCO", [{"raw_peak": "1", "unit": "ppm",
                              "candidates": [{"atom_indices": indices}]}])


def test_unsupported_claims():
    with pytest.raises(ValueError):
        render_report("CCO", [{"raw_peak": "1", "unit": "ppm", "confidence": .9}])
    with pytest.raises(ValueError):
        render_report("CCO", [], source_mapping_status="verified")


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def _peak(**kwargs):
    return {"raw_peak": "synthetic mechanism", "unit": "ppm", **kwargs}


def test_sets_and_multiple_candidates_do_not_infer_relation():
    result = render_report("CCO", [_peak(candidates=[
        {"atom_indices": {3, 4, 5}, "parent_indices": {0, 1}},
        {"atom_indices": {6, 7}}])])
    assert result.count('data-relation="unknown"') == 3
    assert "ambiguous" not in result
    assert 'data-relation="equivalent_group"' not in result
    assert 'data-relation="overlap"' not in result


def test_three_explicit_relations_remain_distinct():
    results = {relation: render_report("CCO", [_peak(relation=relation,
        candidates=[{"atom_indices": {3, 4, 5}, "relation": relation}])])
        for relation in ("equivalent_group", "overlap", "alternatives")}
    assert "≡ 等价组" in results["equivalent_group"]
    assert "⊕ 重叠：多个环境同时对应此峰" in results["overlap"]
    assert "∨ 歧义：互斥备选" in results["alternatives"]
    for relation, result in results.items():
        assert result.count('data-relation="' + relation + '"') == 2


def test_svg_and_row_references_cover_exact_addhs_indices():
    result = render_report("CCO", [_peak(relation="overlap", candidates=[
        {"atom_indices": {3, 4, 5}, "parent_indices": {0}, "samegroup": "CH3", "relation": "equivalent_group"},
        {"atom_indices": {6, 7}, "parent_indices": {1}, "samegroup": "CH2", "relation": "equivalent_group"}])])
    root = ET.fromstring(result[result.index("<svg"):result.index("</svg>") + 6])
    circles = [node.attrib for node in root.iter() if node.attrib.get("class") == "assignment-atom"]
    assert {node["id"] for node in circles} == {f"assignment-atom-{i}" for i in range(9)}
    assert {int(node["data-atom-index"]) for node in circles} == set(range(9))
    tags = Tags(result).tags
    row = next(attrs for tag, attrs in tags if tag == "tr" and "data-atoms" in attrs)
    assert row["data-atoms"] == "3,4,5,6,7" and row["data-parents"] == "0,1"
    for _, attrs in tags:
        for key in ("data-atoms", "data-parents"):
            if key in attrs:
                assert all(f"assignment-atom-{i}" in {n["id"] for n in circles}
                           for i in attrs[key].split(",") if i)
    assert "mouseenter" in result and "click" in result and "keydown" in result


def test_samegroup_has_matching_table_and_rdkit_color():
    result = render_report("CCO", [_peak(candidates=[
        {"atom_indices": {3}, "samegroup": "caller-group"},
        {"atom_indices": {4, 5}, "samegroup": "caller-group"}])])
    badges = [attrs["style"] for tag, attrs in Tags(result).tags if attrs.get("class") == "group"]
    assert len(badges) == 2 and badges[0] == badges[1]
    assert badges[0] == "background:rgb(209,229,249)"
    assert "#D1E5F9" in result  # RDKit rounds the supplied pale-blue group color.
    assert 'data-relation="equivalent_group"' not in result  # Color never infers equivalence.


def test_more_than_six_groups_do_not_reuse_first_color():
    result = render_report("CCCCCCC", [_peak(candidates=[
        {"atom_indices": [i], "samegroup": f"caller-group-{i}"} for i in range(7)])])
    badges = [attrs["style"] for _, attrs in Tags(result).tags if attrs.get("class") == "group"]
    assert len(set(badges)) == 7


def test_conflicting_samegroup_identity_is_rejected_without_silent_color_choice():
    with pytest.raises(ValueError, match="conflicting samegroup"):
        render_report("CCO", [_peak(candidates=[
            {"atom_indices": [3], "samegroup": "A"}, {"atom_indices": [3], "samegroup": "B"}])])


def test_supplied_margin_and_confidence_are_not_computed_or_probability():
    result = render_report("CCO", [_peak(assignment_margin=.25,
        calibrated_confidence={"status": "on_audit_passed",
            "truth_basis": "source_relative_current_serialization", "evidence": ["synthetic audit fixture"]})])
    assert "uncalibrated" in result and "0.25" in result
    assert "on_audit_passed" in result and "source_relative_current_serialization" in result
    assert "不表示实验正确概率" in result and "synthetic audit fixture" in result
    assert "界面只展示输入状态" in result


def test_all_new_text_is_escaped():
    attack = '\"/><img src=x onerror=alert(1)>'
    result = render_report("CCO", [_peak(candidates=[{"samegroup": attack, "atom_indices": {3},
        "ambiguity_basis": attack}], calibrated_confidence={"status": "unavailable",
        "truth_basis": "trusted_experimental", "evidence": [attack]})])
    assert "<img" not in result and "&lt;img" in result
    assert all(tag != "img" for tag, _ in Tags(result).tags)


@pytest.mark.parametrize("kwargs", [
    {"relation": "ambiguous"}, {"relation": []},
    {"candidates": [{"relation": "equivalent"}]},
    {"candidates": [{"samegroup": ""}]}, {"candidates": [{"samegroup": 1}]},
    {"candidates": [{"parent_indices": {99}}]},
    {"candidates": "not records"}, {"alternatives": "not records"},
    {"assignment_margin": True}, {"assignment_margin": float("nan")},
    {"assignment_margin": float("inf")}, {"assignment_margin": "0.2"},
    {"calibrated_confidence": {"status": "on_audit_passed"}},
    {"calibrated_confidence": {"status": "verified", "truth_basis": "trusted_experimental", "evidence": ["x"]}},
    {"calibrated_confidence": {"status": "unavailable", "truth_basis": "probability", "evidence": ["x"]}},
    {"calibrated_confidence": {"status": "unavailable", "truth_basis": "trusted_experimental", "evidence": []}},
    {"calibrated_confidence": {"status": "unavailable", "truth_basis": "trusted_experimental", "evidence": "x"}},
    {"calibrated_confidence": {"status": "unavailable", "truth_basis": "trusted_experimental", "evidence": [1]}},
])
def test_strict_new_field_validation(kwargs):
    with pytest.raises(ValueError):
        render_report("CCO", [_peak(**kwargs)])


def test_unknown_unexplained_unreported_and_partition_assumptions_retained():
    result = render_report("CCO", [_peak()], unreported_atom_indices={8},
        unreported_environments=["exchangeable OH"], unexplained_peaks=["unresolved synthetic peak"],
        assumptions=["synthetic partition assumption"])
    assert "未知关系" in result and "未提供归属" in result
    assert "{8}" in result and "unresolved synthetic peak" in result
    assert "synthetic partition assumption" in result
    assert "exchangeable OH" in result
