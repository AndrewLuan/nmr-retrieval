# 功能概述：展示调用者提供的峰归属，返回带原子联动的独立 HTML；不计算归属、等价性或置信度。
# 主要职责：numbered_molecule 保留零基 AddHs 编号；render_report 校验引用、显式关系、分组和证据；
# _draw 绘制 RDKit 分子与原子命中区，_candidate/_confidence 生成安全文本，脚本只切换高亮。
# 代码库关系：依赖 RDKit 与标准库，由 tests/assignment/test_render.py 验证；不读取数据、权重或服务。
# 输入输出：接收 SMILES 与结果字典，返回字符串，无文件副作用；非法字段、关系、数值、索引报 ValueError。
# relation 描述峰的候选关系或候选内集合关系，缺省 unknown；不按集合大小推断。
# samegroup 只使用调用者完整结果提供的组标识着色；显示编号不证明 source 原子映射。
from collections.abc import Mapping
from colorsys import hls_to_rgb
from html import escape
from math import isfinite

from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

__all__ = ["numbered_molecule", "render_report"]

_RELATIONS = {
    "equivalent_group": ("≡", "等价组（调用者提供）"),
    "overlap": ("⊕", "重叠：多个环境同时对应此峰"),
    "alternatives": ("∨", "歧义：互斥备选"),
    "unknown": ("?", "未知关系"),
}
_PALETTE = ((.82, .90, .98), (.98, .87, .72), (.83, .93, .82),
            (.94, .83, .94), (.98, .92, .70), (.78, .93, .92))


def _group_color(index):
    return _PALETTE[index] if index < len(_PALETTE) else hls_to_rgb((index * .61803398875) % 1, .85, .65)


def _molecule(smiles):
    if not isinstance(smiles, str) or not smiles.strip():
        raise ValueError("SMILES must be nonempty")
    parser = Chem.SmilesParserParams()
    parser.removeHs = False
    mol = Chem.MolFromSmiles(smiles, parser)
    if mol is None or not mol.GetNumAtoms():
        raise ValueError("Invalid SMILES")
    mol = Chem.AddHs(mol)
    rdDepictor.Compute2DCoords(mol)
    return mol


def _draw(mol, atom_colors=None, *, interactive=False):
    drawer = rdMolDraw2D.MolDraw2DSVG(800, 420)
    drawer.drawOptions().addAtomIndices = True
    colors = atom_colors or {}
    drawer.DrawMolecule(mol, highlightAtoms=sorted(colors), highlightAtomColors=colors,
                        highlightBonds=[])
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    svg = svg[svg.index("<svg"):]
    if interactive:
        targets = []
        for index in range(mol.GetNumAtoms()):
            point = drawer.GetDrawCoords(index)
            targets.append(f'<circle id="assignment-atom-{index}" class="assignment-atom" '
                           f'data-atom-index="{index}" cx="{point.x:.3f}" cy="{point.y:.3f}" r="15"/>')
        svg = svg.replace("</svg>", "".join(targets) + "</svg>")
    return svg


def numbered_molecule(smiles: str) -> tuple[str, int]:
    """Return SVG and atom count; zero-based input order followed by added Hs."""
    mol = _molecule(smiles)
    return _draw(mol), mol.GetNumAtoms()


def _fields(value, allowed):
    if not isinstance(value, Mapping) or set(value) - set(allowed):
        raise ValueError("Unsupported fields or non-mapping input")


def _text(value):
    if not isinstance(value, str):
        raise ValueError("Display text must be a string")
    return escape(value, quote=True)


def _sequence(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("Display records must be lists or tuples")
    return value


def _atom_set(value, count):
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("Atom references must be sets or sequences")
    if any(type(i) is not int or not 0 <= i < count for i in value):
        raise ValueError("Atom index outside AddHs graph")
    return tuple(sorted(set(value)))


def _indices(value, count):
    return "{" + ", ".join(map(str, _atom_set(value, count))) + "}"


def _relation(value):
    if not isinstance(value, str) or value not in _RELATIONS:
        raise ValueError("Unsupported relation")
    mark, label = _RELATIONS[value]
    return f'<span class="relation" data-relation="{value}">{mark} {label}</span>'


def _references(atoms, parents):
    return (' data-atoms="' + ",".join(map(str, atoms)) + '" data-parents="' +
            ",".join(map(str, parents)) + '"')


def _candidate(candidate, count, groups):
    _fields(candidate, ("environment_id", "carrier_id", "atom_indices", "parent_indices",
                        "ambiguity_meaning", "ambiguity_basis", "relation", "samegroup"))
    atoms = _atom_set(candidate.get("atom_indices", ()), count)
    parents = _atom_set(candidate.get("parent_indices", ()), count)
    parts = [_relation(candidate.get("relation", "unknown")),
             "环境：" + _text(candidate.get("environment_id", "未提供")),
             "载体：" + _text(candidate.get("carrier_id", "未提供")),
             "原子：" + _indices(atoms, count), "父原子：" + _indices(parents, count)]
    if "samegroup" in candidate:
        group = candidate["samegroup"]
        if not isinstance(group, str) or not group.strip():
            raise ValueError("samegroup must be a nonempty caller-supplied identity")
        color = groups.setdefault(group, {"atoms": set(), "color": _group_color(len(groups))})
        color["atoms"].update(atoms)
        rgb = ",".join(str(int(x * 255)) for x in color["color"])
        parts.append(f'<span class="group" style="background:rgb({rgb})">组：{_text(group)}</span>')
    for key in ("ambiguity_meaning", "ambiguity_basis"):
        if key in candidate:
            parts.append(key + ": " + _text(candidate[key]))
    return ('<div class="candidate" tabindex="0" role="button" aria-label="高亮此候选的原子"' +
            _references(atoms, parents) + '>' + "<br>".join(parts) + "</div>", atoms, parents)


def _notes(values):
    return "<ul>" + "".join("<li>" + _text(v) + "</li>" for v in _sequence(values)) + "</ul>"


def _confidence(peak):
    parts = []
    if "assignment_margin" in peak:
        value = peak["assignment_margin"]
        if type(value) not in (int, float) or not isfinite(value):
            raise ValueError("assignment_margin must be a finite number")
        parts.append("未校准归属 margin（uncalibrated）：" + str(value))
    if "calibrated_confidence" in peak:
        supplied = peak["calibrated_confidence"]
        _fields(supplied, ("status", "truth_basis", "evidence"))
        if set(supplied) != {"status", "truth_basis", "evidence"}:
            raise ValueError("Calibrated confidence requires status, truth_basis and evidence")
        if not isinstance(supplied["status"], str) or supplied["status"] not in (
                "on_audit_passed", "off_insufficient_support", "off_audit_rejected", "unavailable"):
            raise ValueError("Unsupported calibrated confidence status")
        basis = supplied["truth_basis"]
        basis_labels = {"trusted_experimental": "实验真值口径",
                        "source_relative_current_serialization": "source 断言相对一致性；不表示实验正确概率",
                        "source_report_supported": "source 报告支持口径；不表示实验正确概率"}
        if not isinstance(basis, str) or basis not in basis_labels:
            raise ValueError("Unsupported truth_basis")
        if not _sequence(supplied["evidence"]):
            raise ValueError("Calibrated confidence requires caller-supplied evidence")
        parts.append("调用者提供的校准状态：" + _text(supplied["status"]) + "<br>truth_basis: " +
                     basis + "（" + basis_labels[basis] + "）" + _notes(supplied["evidence"]))
    return "<br>".join(parts)


_STYLE = """
body{font:15px system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#20262d}
h1{font-size:1.5rem}svg{max-width:100%;height:auto}table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid #d7dce1;padding:.7rem;text-align:left;vertical-align:top}
td{overflow-wrap:anywhere}.candidate{padding:.4rem;border-radius:5px;cursor:pointer}
.candidate:hover,.candidate:focus-visible,tr.selected{background:#edf3f8}.group{padding:1px 5px;border-radius:3px}
.relation{font-weight:600}.assignment-atom{fill:none;stroke:none;pointer-events:none}
.assignment-atom.active-parent{stroke:#6f4bb8;stroke-width:3;stroke-dasharray:4 3}
.assignment-atom.active-atom{fill:#ffbf4738;stroke:#9e6500;stroke-width:3;stroke-dasharray:none}
details{margin:1rem 0}summary{cursor:pointer}li{margin:.25rem 0}.table-scroll{overflow-x:auto}
"""
_SCRIPT = """
<script>
(() => {
  let pinned = null;
  const parse = value => (value || '').split(',').filter(Boolean);
  function show(target) {
    document.querySelectorAll('.assignment-atom').forEach(atom => {
      atom.classList.remove('active-atom', 'active-parent');
    });
    document.querySelectorAll('tr.selected').forEach(row => row.classList.remove('selected'));
    if (!target) return;
    const row = target.closest('tr');
    if (row) row.classList.add('selected');
    for (const [field, name] of [['parents', 'active-parent'], ['atoms', 'active-atom']]) {
      parse(target.dataset[field]).forEach(index => {
        const atom = document.getElementById('assignment-atom-' + index);
        if (atom) atom.classList.add(name);
      });
    }
  }
  document.querySelectorAll('[data-atoms]').forEach(target => {
    target.addEventListener('mouseenter', () => show(target));
    target.addEventListener('mouseleave', () => show(pinned));
    target.addEventListener('focus', () => show(target));
    target.addEventListener('blur', () => show(pinned));
    const toggle = event => {event.stopPropagation(); pinned = pinned === target ? null : target; show(pinned);};
    target.addEventListener('click', toggle);
    target.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); toggle(event);}
      if (event.key === 'Escape') {pinned = null; show(null);}
    });
  });
})();
</script>
"""


def render_report(smiles, peaks, *, title="峰归属", source_mapping_status="pending",
                  unreported_atom_indices=(), unreported_environments=(), unexplained_peaks=(),
                  evidence=(), assumptions=()):
    """Render caller-supplied assignments; no inference, calibration or certification.

    Legacy raw_peak/unit/candidates, prediction_text/residual_text and alternatives
    remain supported. relation is explicit on peaks/candidates: equivalent_group,
    overlap (simultaneous), alternatives (exclusive), or unknown (default).
    Candidate samegroup is a caller-supplied complete-result color identity, never
    derived from atom cardinality. Peak assignment_margin is uncalibrated; optional
    calibrated_confidence supplies status/truth_basis/evidence from upstream.
    All atom/parent references address the zero-based Chem.AddHs input-order graph.
    """
    if not isinstance(source_mapping_status, str) or source_mapping_status not in ("pending", "caller-supplied", "unavailable"):
        raise ValueError("Unsupported source mapping status")
    mol = _molecule(smiles)
    count, rows, groups = mol.GetNumAtoms(), [], {}
    for peak in _sequence(peaks):
        _fields(peak, ("raw_peak", "unit", "candidates", "prediction_text", "residual_text",
                       "alternatives", "relation", "assignment_margin", "calibrated_confidence"))
        if not {"raw_peak", "unit"} <= set(peak):
            raise ValueError("Peak requires raw_peak and unit")
        atoms, parents = set(), set()
        def candidates(items):
            rendered = []
            for item in _sequence(items):
                html, aa, pp = _candidate(item, count, groups)
                rendered.append(html)
                atoms.update(aa)
                parents.update(pp)
            return "<hr>".join(rendered)
        candidate_html = candidates(peak.get("candidates", ()))
        alternatives = []
        for alternative in _sequence(peak.get("alternatives", ())):
            _fields(alternative, ("scope", "candidates", "complete_solution_id"))
            if alternative.get("scope") not in ("local", "global"):
                raise ValueError("Alternative scope must be local or global")
            label = _relation("alternatives") + "; scope: " + alternative["scope"]
            if "complete_solution_id" in alternative:
                label += "; complete_solution_id: " + _text(alternative["complete_solution_id"])
            alternatives.append(label + candidates(alternative.get("candidates", ())))
        supplied = "<br>".join(key + ": " + _text(peak[key])
                              for key in ("prediction_text", "residual_text") if key in peak)
        if supplied:
            supplied += "<br>"
        supplied += _confidence(peak)
        cells = (_text(peak["raw_peak"]), _text(peak["unit"]), _relation(peak.get("relation", "unknown")),
                 candidate_html or "未提供归属", supplied, "<hr>".join(alternatives))
        rows.append('<tr tabindex="0"' + _references(sorted(atoms), sorted(parents)) + '>' +
                    "".join("<td>" + cell + "</td>" for cell in cells) + "</tr>")
    atom_colors = {}
    for group in groups.values():
        for index in group["atoms"]:
            if index in atom_colors and atom_colors[index] != group["color"]:
                raise ValueError("An atom cannot have conflicting samegroup color identities")
            atom_colors[index] = group["color"]
    svg = _draw(mol, atom_colors, interactive=True)
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>' + _text(title) +
            "</title><style>" + _STYLE + "</style></head><body><h1>" + _text(title) + "</h1>" + svg +
            "<p>悬停或点击峰行可高亮全部关联原子；点击候选可单独选择。实线圈为原子，虚线圈为父原子。"
            "相同组标识使用相同颜色，关系均由调用者提供。</p><div class=\"table-scroll\"><table><thead><tr>"
            "<th>原始峰位</th><th>单位</th><th>关系</th><th>原子集合 / 环境</th>"
            "<th>提供的结果与依据</th><th>互斥备选</th></tr></thead><tbody>" + "".join(rows) +
            "</tbody></table></div><p>未报告原子集合：" + _indices(unreported_atom_indices, count) +
            "</p><p>未报告环境（调用者提供）：</p>" + _notes(unreported_environments) +
            "<p>未解释峰（调用者提供）：</p>" + _notes(unexplained_peaks) +
            "<p>分区及其他假设：</p>" + _notes(assumptions) +
            "<details><summary>编号契约与来源依据</summary><p>Numbering contract: zero-based Chem.AddHs graph; "
            "supplied input atom order is preserved and added hydrogens follow. Graph atom count: " + str(count) +
            ". Source mapping status: " + source_mapping_status +
            ". Display atom indices are not proof of source atom mapping.</p><p>调用者提供的证据：</p>" +
            _notes(evidence) + "<p>界面只展示输入状态，不计算置信度或自动认证。</p></details>" + _SCRIPT + "</body></html>")
