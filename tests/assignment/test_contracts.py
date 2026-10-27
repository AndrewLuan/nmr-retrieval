# 功能：用合成映射验证归属输入边界，不使用真实数据、模型或科学参数。
# 职责：sample 构建独立输入；ContractTests 检查泄漏、精度、计数、映射和非法值。
# 关系与输入输出：只依赖标准库及 nmr_assignment.contracts；unittest 同步执行，
# 断言失败由测试框架报告，无网络、文件写入或持久化副作用。
from dataclasses import replace
import copy
import unittest
from decimal import Decimal

from nmr_assignment.contracts import Alternative, Assignment, AssignmentOutput, InferenceInput
from nmr_assignment.native_adapter import adapt_native_predictions
from nmr_assignment.mapping import make_joint_mapping, project_assignment


def sample():
    return dict(structure="CO", nucleus="1H", observed_peaks=[dict(
        peak_id="p0", shift_literal="3.1400", unit="ppm", hz_semantics=None,
        reference_hz=None, reference_ppm=None, observation_type="reported_peak",
        integer_weight=3, actual_integral=None)], window=dict(lower_ppm=None, upper_ppm=None),
        actual_conditions=dict(solvent=None, temperature_kelvin=None, frequency_mhz=None),
        frozen_predictions=dict(mapping_capability="candidate_sets", structural_environment_count=2,
            predicted_resonance_count=3, environments=[dict(environment_id="e0",
                atom_candidates=[0, 1], parent_candidates=[0], hydrogen_count=3,
                predicted_ppm="3.1", mapping_ambiguous=True,
                candidate_meaning="mapping_ambiguity", candidate_basis="synthetic candidate map")]))


class ContractTests(unittest.TestCase):
    def capacity_input(self, nucleus="13C"):
        value=sample()
        value["nucleus"]=nucleus
        mass=1 if nucleus=="13C" else 2
        pred=adapt_native_predictions(dict(nucleus=nucleus,parent_mass={"0":mass},
            isotope_count_verified=True,evidence_ids=["synthetic-graph"],partition_hypothesis_id="synthetic"),
            centers_ppm=[1,3],masses=[mass/2,mass/2],owners=[0,0],graph_indices=[0,0],
            sigma_ppm=[1,2],sigma_sources=["synthetic","synthetic"],known_h_layout=False,
            layout_evidence_ids=[],attachment_evidence_ids=[])
        value["frozen_predictions"]=pred
        return value,pred

    def test_capacity_h_and_carbon_keep_all_carriers_unknown_conditions(self):
        for nucleus in ("1H","13C"):
            value,pred=self.capacity_input(nucleus)
            parsed=InferenceInput.from_mapping(value)
            self.assertIs(parsed.frozen_predictions,pred)
            self.assertEqual(len(pred.layout.units),1)
            self.assertEqual([c.center_ppm for c in pred.carriers],[1,3])
            self.assertEqual([c.sigma_ppm for c in pred.carriers],[1,2])
            self.assertIsNone(parsed.actual_conditions.pH)
            self.assertIsNone(parsed.missing_mask)
            self.assertEqual(pred.layout.units[0].nucleus_mass,1 if nucleus=="13C" else 2)
        value,_=self.capacity_input()
        value["actual_conditions"]["pH"]="7.1"
        self.assertEqual(InferenceInput.from_mapping(value).actual_conditions.pH,Decimal("7.1"))
        value["missing_mask"]=False
        with self.assertRaisesRegex(ValueError,"measurement axis"):
            InferenceInput.from_mapping(value)

    def test_capacity_dict_and_nested_leakage_not_an_entry_point(self):
        value,pred=self.capacity_input()
        from dataclasses import asdict
        value["frozen_predictions"]=asdict(pred)
        value["frozen_predictions"]["layout"]["gold"]="leak"
        with self.assertRaises(ValueError): InferenceInput.from_mapping(value)
        value,_=self.capacity_input()
        value["actual_conditions"]["pH"]={"source":"leak"}
        with self.assertRaises(ValueError): InferenceInput.from_mapping(value)

    def test_unique_output_requires_bound_complete_atom_projection(self):
        value,pred=self.capacity_input()
        original=InferenceInput.from_mapping(value)
        uid=pred.layout.units[0].unit_id
        a=Assignment("p0",(uid,),(0,),False,True,None,())
        output=AssignmentOutput((a,),(),(),(),(),"global_exclusive")
        with self.assertRaisesRegex(ValueError,"projection"):
            output.validate_against(original)
        joint=make_joint_mapping(pred.layout,{uid:["0"]},[(uid,)],level="atom",complete=True,
            basis="provenance_lineage",evidence_ids=["synthetic-proof"],target_universe=["0"],
            completeness_evidence_id="synthetic-complete",max_joint_maps=10)
        projection=project_assignment({"p0":(uid,)},joint)
        output.validate_against(original,joint_mapping=joint,projection=projection)
        with self.assertRaises(ValueError):
            replace(output,assignments=(replace(a,atom_candidates=(1,)),)).validate_against(
                original,joint_mapping=joint,projection=projection)
        incomplete=replace(joint,complete=False,completeness_evidence_id=None)
        with self.assertRaises(ValueError):
            output.validate_against(original,joint_mapping=incomplete,
                projection=project_assignment({"p0":(uid,)},incomplete))

    def test_precision_unknowns_and_distinct_counts(self):
        result = InferenceInput.from_mapping(sample())
        peak = result.observed_peaks[0]
        self.assertEqual(peak.shift_literal, "3.1400")
        self.assertEqual(peak.ppm.as_tuple().exponent, -4)
        self.assertEqual(peak.ppm, Decimal("3.14"))
        self.assertIsNone(result.window.lower_ppm)
        self.assertIsNone(result.window.upper_ppm)
        self.assertEqual(peak.integer_weight, 3)
        self.assertIsNone(peak.actual_integral)
        self.assertEqual((result.frozen_predictions.structural_environment_count,
                          result.frozen_predictions.predicted_resonance_count,
                          result.observed_peak_count), (2, 3, 1))

    def test_leakage_and_unknown_keys_rejected_at_every_boundary(self):
        base = sample()
        paths = [(), ("observed_peaks", 0), ("window",), ("actual_conditions",),
                 ("frozen_predictions",), ("frozen_predictions", "environments", 0)]
        for path in paths:
            for forbidden in ("source", "record_id", "gold", "labels", "truth", "unexpected"):
                with self.subTest(path=path, key=forbidden):
                    value = copy.deepcopy(base)
                    target = value
                    for key in path:
                        target = target[key]
                    target[forbidden] = "leak"
                    with self.assertRaises(ValueError):
                        InferenceInput.from_mapping(value)

    def test_nested_mapping_cannot_hide_in_scalar_condition(self):
        value = sample()
        value["actual_conditions"]["solvent"] = {"source": "leak"}
        with self.assertRaises(ValueError):
            InferenceInput.from_mapping(value)

    def test_invalid_nucleus_and_nonfinite_values(self):
        value = sample()
        value["nucleus"] = "19F"
        with self.assertRaises(ValueError):
            InferenceInput.from_mapping(value)
        for literal in ("NaN", "Infinity", "-Infinity", "invalid"):
            for prediction in (False, True):
                value = sample()
                target = value["frozen_predictions"]["environments"][0] if prediction else value["observed_peaks"][0]
                target["predicted_ppm" if prediction else "shift_literal"] = literal
                with self.assertRaises(ValueError):
                    InferenceInput.from_mapping(value)

    def test_hz_conversion_requires_actual_frequency_and_explicit_reference(self):
        value = sample()
        peak = value["observed_peaks"][0]
        peak.update(shift_literal="850.00", unit="Hz", hz_semantics="reference_offset",
                    reference_hz="50", reference_ppm="1.5")
        value["actual_conditions"]["frequency_mhz"] = "400"
        parsed = InferenceInput.from_mapping(value)
        self.assertEqual(parsed.observed_peaks[0].normalized_ppm(parsed.actual_conditions), Decimal("3.5"))
        self.assertEqual(parsed.observed_peaks[0].shift_literal, "850.00")
        for missing in ("hz_semantics", "reference_hz", "reference_ppm", "frequency_mhz"):
            invalid = copy.deepcopy(value)
            target = invalid["actual_conditions"] if missing == "frequency_mhz" else invalid["observed_peaks"][0]
            target[missing] = None
            parsed = InferenceInput.from_mapping(invalid)
            with self.assertRaises(ValueError):
                parsed.observed_peaks[0].normalized_ppm(parsed.actual_conditions)
        with self.assertRaises(ValueError):
            parsed.observed_peaks[0].ppm

    def test_negative_values_and_invalid_types(self):
        cases = [("integer_weight", -1), ("integer_weight", True),
                 ("actual_integral", "-0.1"), ("actual_integral", 1.5), ("unit", "kHz")]
        for key, bad in cases:
            value = sample()
            value["observed_peaks"][0][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                InferenceInput.from_mapping(value)
        for key in ("frequency_mhz", "temperature_kelvin"):
            for bad in ("0", "-1", True, "NaN"):
                value = sample()
                value["actual_conditions"][key] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    InferenceInput.from_mapping(value)
        for flags in (("false", False), (False, "true"), (1, False)):
            with self.assertRaises(ValueError):
                Assignment("p0", ("e0",), (0,), *flags, None, ())
        value = sample()
        value["frozen_predictions"]["environments"][0]["mapping_ambiguous"] = "false"
        with self.assertRaises(ValueError):
            InferenceInput.from_mapping(value)

    def test_ambiguous_mapping_cannot_claim_unique_atom(self):
        with self.assertRaises(ValueError):
            Assignment("p0", ("e0",), (0,), True, True, None, ())
        result = Assignment("p0", ("e0",), (0, 1), True, False, Decimal("0.04"), ())
        self.assertEqual(result.atom_candidates, (0, 1))
        value = sample()
        value["frozen_predictions"]["mapping_capability"] = "unique_atoms"
        with self.assertRaises(ValueError):
            InferenceInput.from_mapping(value)

    def test_candidate_meaning_and_basis(self):
        for meaning, basis in (("invalid", "x"), ("chemical_equivalence", None), ("unknown", "x")):
            value = sample()
            value["frozen_predictions"]["environments"][0].update(candidate_meaning=meaning, candidate_basis=basis)
            with self.assertRaises(ValueError):
                InferenceInput.from_mapping(value)
        value = sample()
        value["frozen_predictions"]["environments"][0].update(candidate_meaning="unknown", candidate_basis=None)
        self.assertEqual(InferenceInput.from_mapping(value).frozen_predictions.environments[0].candidate_meaning, "unknown")

    def test_global_alternative_requires_complete_solution_reference(self):
        for solution_id in (None, "", " "):
            with self.assertRaises(ValueError):
                Alternative(("e0",), "global_feasible", solution_id)
        self.assertEqual(Alternative(("e0",), "global_feasible", "solution-2").complete_solution_id, "solution-2")
        with self.assertRaises(ValueError):
            Alternative(("e0",), "local_unconstrained", "solution-2")

    def test_unique_capability_rejected_even_with_claimed_unambiguous_singleton(self):
        value = sample()
        value["frozen_predictions"].update(mapping_capability="unique_atoms")
        value["frozen_predictions"]["environments"][0].update(atom_candidates=[0], mapping_ambiguous=False,
            candidate_meaning="unknown", candidate_basis=None)
        with self.assertRaises(ValueError):
            InferenceInput.from_mapping(value)

    def test_output_references_coverage_and_subset_validation(self):
        original = InferenceInput.from_mapping(sample())
        assignment = Assignment("p0", ("e0",), (0, 1), True, False, None,
            (Alternative(("e0",), "global_feasible", "solution-2"),),
            "mapping_ambiguity", "synthetic map")
        output = AssignmentOutput((assignment,), (), (), (), (), "global_exclusive")
        output.validate_against(original)
        bad_outputs = [replace(output, assignments=()), replace(output, unexplained_peak_ids=("p0",)),
            replace(output, unreported_environment_ids=("e0",)),
            replace(output, assignments=(replace(assignment, peak_id="missing"),)),
            replace(output, assignments=(replace(assignment, environment_ids=("missing",)),)),
            replace(output, assignments=(replace(assignment, atom_candidates=(99,)),)),
            replace(output, assignments=(replace(assignment, mapping_ambiguous=False,
                candidate_meaning="unknown", candidate_basis=None),)),
            replace(output, assignments=(replace(assignment, alternatives=(Alternative(("missing",), "local_unconstrained"),)),))]
        for bad in bad_outputs:
            with self.assertRaises(ValueError):
                bad.validate_against(original)

    def test_local_reuse_is_explicitly_allowed_global_reuse_rejected(self):
        value = sample()
        value["observed_peaks"].append(dict(value["observed_peaks"][0], peak_id="p1"))
        original = InferenceInput.from_mapping(value)
        first = Assignment("p0", ("e0",), (0, 1), True, False, None,
            (Alternative(("e0",), "local_unconstrained"),))
        output = AssignmentOutput((first, replace(first, peak_id="p1")), (), (), (), (), "local_unconstrained")
        output.validate_against(original)
        with self.assertRaises(ValueError):
            replace(output, reuse_semantics="global_exclusive").validate_against(original)
        global_option = replace(first, alternatives=(Alternative(("e0",), "global_feasible", "whole-2"),))
        with self.assertRaises(ValueError):
            replace(output, assignments=(global_option, replace(first, peak_id="p1"))).validate_against(original)


if __name__ == "__main__":
    unittest.main()
