# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：C1–C8 producer纯合成fixture，独立于3745真实C行和全部模型/评分。\nfixture用RDKit构造声明结构与source_transport的真实纯结构内部接口，保持target完全不入匹配。\n测试完整/截断/timeout、C active元素、mask/null/finite/Decimal、空政策、冲突scope、\nJJ快照/版本、whole-map相关性与JSON证据重算。所有proof locator明确synthetic。\n只写测试内存；不执行真实batch、不调用forward、不修改core或源标签。\n'
import unittest, json, sys
from pathlib import Path
from copy import deepcopy
from decimal import Decimal
D = workspace()
REPO = repository()
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(D))
from rdkit import Chem, rdBase
from nmr_assignment import source_reference as core, source_transport as transport_core
import C_reference_rule_producer as producer

def fixture(smiles='CO', literals=None, mutate=None):
    full = Chem.AddHs(Chem.MolFromSmiles(smiles))
    n = full.GetNumAtoms()
    carbons = [a.GetIdx() for a in full.GetAtoms() if a.GetAtomicNum() == 6]
    literals = literals or ['20.10'] * len(carbons)
    row = dict(source_ref='synthetic-C-source', nucleus='13C', record_id='synthetic-row', smiles=smiles, atoms=[a.GetSymbol() for a in full.GetAtoms()], coordinates=[[0, 0, 0]] * n, atom_targets=[None] * n, atom_target_mask=[False] * n, atom_order=dict(basis='source_mol', source_to_canonical=list(range(n)), atomic_numbers=[a.GetAtomicNum() for a in full.GetAtoms()]), spectrum=[], experimental_conditions={'solvent': 'CDCl3', 'frequency': '100 MHz'})
    for i, (index, literal) in enumerate(zip(carbons, literals)):
        marker = '__DECIMAL_' + str(i) + '__'
        row['atom_targets'][index] = marker
        row['atom_target_mask'][index] = True
        row['spectrum'].append(dict(atom_index=index, shift=marker))
    if mutate:
        mutate(row)
    raw = json.dumps(row, ensure_ascii=False)
    for i, literal in enumerate(literals):
        raw = raw.replace(json.dumps('__DECIMAL_' + str(i) + '__'), literal)
    raw += '\n'
    binding = dict(source=row['source_ref'], nucleus=row['nucleus'], record_id=row['record_id'], structure_id=core.text_sha256(smiles), source_sha256='a' * 64, row_sha256=core.text_sha256(raw), policy_sha256=producer.EMPTY_POLICY_SHA)
    record = {k: binding[k] for k in ('source', 'nucleus', 'record_id', 'structure_id', 'row_sha256')}
    record['native_legacy_hash_partition'] = 'val'
    manifest = dict(source_sha256='a' * 64, policy_sha256=producer.EMPTY_POLICY_SHA, records=[record], native_partition='val', nucleus_scope='13C', reference_choice='raw', extraction_manifest_sha256='b' * 64, raw_subset_sha256='c' * 64, identity_ledger_sha256='d' * 64)
    text = json.dumps(manifest)
    binding['cohort_identity_manifest_sha256'] = core.text_sha256(text)
    payload = dict(smiles=smiles, atoms=row['atoms'], atom_order=row['atom_order'])
    transport = transport_core._transport_impl(payload, binding, None, None, 4096, rdBase.rdkitVersion, producer.file_sha(transport_core.__file__))
    lineage = transport['graph_lineage_evidence']
    native = dict(canonical_smiles=transport['canonical_smiles'], rdkit_version=rdBase.rdkitVersion, graph_snapshot=lineage['baseline_graph'], graph_snapshot_sha256=producer.digest(lineage['baseline_graph']))
    config = dict(rule_id=producer.RULE_ID, nucleus_scope='13C', scientific_rule_review_sha256=producer.RULE_REVIEW_SHA, source_sha256='a' * 64, source_reference_implementation_sha256=producer.file_sha(core.__file__), transport_implementation_sha256=producer.file_sha(transport_core.__file__), expected_rdkit_version=rdBase.rdkitVersion, extraction_manifest_sha256='b' * 64, raw_subset_sha256='c' * 64, identity_ledger_sha256='d' * 64, expected_cohort_identity_count=1, historical_C_quality_policy_status='unknown', policy_absence_action='direct_C_rule_preserve_unknown')
    config_text = json.dumps(config)
    return dict(raw_json_line=raw, source_sha256='a' * 64, empty_C_policy_jsonl='', empty_C_policy_sha256=producer.EMPTY_POLICY_SHA, cohort_manifest_json=text, cohort_identity_manifest_sha256=binding['cohort_identity_manifest_sha256'], transport=transport, native_graph_receipt=native, rule_config_json=config_text, rule_config_sha256=core.text_sha256(config_text), input_id='opaque-synthetic-C')

def run(kw):
    return producer.produce_C_reference(**kw)

class CRuleTests(unittest.TestCase):

    def test_complete_C1_C8_keep_is_only_source_relative_unknown_historical_quality(self):
        out = run(fixture())
        self.assertIsNotNone(out['quality_receipt'])
        self.assertTrue(all((x['passed'] for x in out['ledger']['gate_outcomes'].values())))
        self.assertEqual(out['reference'].classification, 'unique_parent')
        self.assertIn('policy_missing', out['reference'].reasons)
        self.assertEqual(out['ledger']['historical_C_quality_policy_status'], 'unknown')
        self.assertIn('historical_C_quality_unknown', out['ledger']['reasons'])
        self.assertFalse(out['ledger']['trusted_experimental'])
        self.assertEqual(out['quality_receipt']['known_conflict_input_status'], 'unavailable_no_C_specific_registry')

    def test_public_schema_no_hidden_binding_members_or_receipts(self):
        out = run(fixture())
        public = out['public_payload']
        self.assertEqual(set(public), {'input_id', 'nucleus', 'smiles', 'actual_conditions', 'observations'})
        self.assertEqual(set(public['observations'][0]), {'bin_id', 'ppm_decimal'})
        self.assertNotIn('source', public)
        self.assertNotIn('atom_target_mask', public)
        self.assertEqual(out['quality_receipt']['evidence_sha256'], producer.digest(out['evidence_bundle']))
        persisted = json.loads(json.dumps(out['evidence_bundle']))
        self.assertEqual(out['quality_receipt']['evidence_sha256'], producer.digest(persisted))

    def test_wrong_active_noncarbon_target_C2(self):

        def change(r):
            r['atom_targets'][0] = None
            r['atom_target_mask'][0] = False
            r['atom_targets'][1] = '__DECIMAL_0__'
            r['atom_target_mask'][1] = True
            r['spectrum'] = [dict(atom_index=1, shift='__DECIMAL_0__')]
        out = run(fixture(mutate=change))
        self.assertIsNone(out['quality_receipt'])
        self.assertFalse(out['ledger']['gate_outcomes']['C2']['passed'])

    def test_mask_invalid_inactive_nonnull_and_spectrum_mismatch_C3(self):
        mutations = [lambda r: r['atom_target_mask'].__setitem__(0, 2), lambda r: r['atom_target_mask'].__setitem__(0, False), lambda r: r['spectrum'][0].__setitem__('shift', 21.5)]
        for mutate in mutations:
            out = run(fixture(mutate=mutate))
            self.assertIsNone(out['quality_receipt'])
            self.assertFalse(out['ledger']['gate_outcomes']['C3']['passed'])

    def test_nonfinite_invalid_target_and_empty_coverage_retained(self):
        for literal in ('NaN', 'Infinity'):
            out = run(fixture(literals=[literal]))
            self.assertIsNone(out['public_payload'])
            self.assertEqual(set(out['ledger']['gate_outcomes']), {'C' + str(i) for i in range(1, 9)})

        def empty(r):
            r['atom_targets'] = [None] * len(r['atoms'])
            r['atom_target_mask'] = [False] * len(r['atoms'])
            r['spectrum'] = []
        out = run(fixture(mutate=empty))
        self.assertFalse(out['ledger']['gate_outcomes']['C5']['passed'])

    def test_exact_Decimal_bins_no_epsilon_and_whole_joint_ambiguity(self):
        out = run(fixture('CC', ['20.100000000000000000001', '20.100000000000000000002']))
        self.assertIsNotNone(out['quality_receipt'])
        self.assertEqual(len(out['public_payload']['observations']), 2)
        variants = out['reference'].hidden['joint_gold_variants']
        self.assertEqual(len(variants), 2)
        self.assertTrue(all((len({tuple(v) for _, v in variant}) == 2 for variant in variants)))
        self.assertEqual(out['reference'].classification, 'parent_mapping_ambiguous')

    def test_masked_siblings_not_expanded(self):

        def mask_second(r):
            r['atom_targets'][1] = None
            r['atom_target_mask'][1] = False
            r['spectrum'] = [s for s in r['spectrum'] if s['atom_index'] == 0]
        out = run(fixture('CC', ['20.1', '20.2'], mask_second))
        self.assertEqual(len(out['public_payload']['observations']), 1)
        self.assertEqual(out['reference'].hidden['derived'].reported_slot_count, 1)

    def test_C4_truncated_timeout_and_RDKit_or_graph_mismatch(self):
        for mode in ('truncated', 'timeout', 'rdkit', 'graph'):
            kw = fixture()
            if mode == 'truncated':
                kw['transport'].update(complete=False, enumeration_truncated=True)
            if mode == 'timeout':
                kw['transport'].update(complete=False, joint_maps=(), reason_codes=('transport_time_limit',))
            if mode == 'rdkit':
                kw['native_graph_receipt']['rdkit_version'] = 'different-version'
            if mode == 'graph':
                kw['native_graph_receipt']['graph_snapshot']['atoms'][0]['charge'] = 9
            out = run(kw)
            self.assertIsNone(out['quality_receipt'])
            self.assertFalse(out['ledger']['gate_outcomes']['C4']['passed'])

    def test_duplicate_or_wrong_partition_cohort_C1(self):
        for change in ('duplicate', 'partition'):
            kw = fixture()
            manifest = json.loads(kw['cohort_manifest_json'])
            if change == 'duplicate':
                manifest['records'].append(deepcopy(manifest['records'][0]))
            else:
                manifest['records'][0]['native_legacy_hash_partition'] = 'test'
            kw['cohort_manifest_json'] = json.dumps(manifest)
            kw['cohort_identity_manifest_sha256'] = core.text_sha256(kw['cohort_manifest_json'])
            out = run(kw)
            self.assertIsNone(out['quality_receipt'])
            self.assertFalse(out['ledger']['gate_outcomes']['C1']['passed'])

    def test_H_keep_cannot_replace_empty_C_policy(self):
        kw = fixture()
        kw['empty_C_policy_jsonl'] = json.dumps(dict(nucleus='1H', keep_atom_parent_supervision=True)) + '\n'
        kw['empty_C_policy_sha256'] = core.text_sha256(kw['empty_C_policy_jsonl'])
        out = run(kw)
        self.assertIsNone(out['quality_receipt'])
        self.assertFalse(out['ledger']['gate_outcomes']['C6']['passed'])

    def test_known_C_conflict_or_raw_correction_restriction_preserved(self):
        for restriction in ('known_source_conflict', 'raw_correction_not_applied'):
            kw = fixture()
            entry = {k: v for k, v in kw['transport'].items() if k in ('source', 'nucleus', 'record_id', 'structure_id')}
            entry['restriction'] = restriction
            document = dict(schema='C_known_source_conflicts_v1', nucleus_scope='13C', records=[entry])
            kw['known_conflicts_json'] = json.dumps(document)
            kw['known_conflicts_sha256'] = core.text_sha256(kw['known_conflicts_json'])
            out = run(kw)
            self.assertIsNone(out['quality_receipt'])
            self.assertFalse(out['ledger']['gate_outcomes']['C7']['passed'])

    def test_H_conflict_with_same_record_id_is_not_C_conflict(self):
        kw = fixture()
        entry = {k: v for k, v in kw['transport'].items() if k in ('source', 'nucleus', 'record_id', 'structure_id')}
        entry.update(nucleus='1H', restriction='H_only_conflict')
        kw['known_conflicts_json'] = json.dumps(dict(schema='C_known_source_conflicts_v1', nucleus_scope='13C', records=[entry]))
        kw['known_conflicts_sha256'] = core.text_sha256(kw['known_conflicts_json'])
        out = run(kw)
        self.assertIsNone(out['quality_receipt'])
        self.assertIn('known_conflict_registry_scope_invalid', out['ledger']['reasons'])
        self.assertNotIn('known_C_source_restriction', out['ledger']['reasons'])

    def test_coordinate_length_and_masked_target_null_domains(self):
        out = run(fixture(mutate=lambda r: r['coordinates'].pop()))
        self.assertIsNone(out['quality_receipt'])
        self.assertFalse(out['ledger']['gate_outcomes']['C2']['passed'])
        out = run(fixture(mutate=lambda r: r['atom_targets'].__setitem__(0, None)))
        self.assertIsNone(out['quality_receipt'])
        self.assertFalse(out['ledger']['gate_outcomes']['C3']['passed'])

    def test_no_hard_ppm_plausibility_gate_or_epsilon(self):
        out = run(fixture(literals=['99999.000000000000000000001']))
        self.assertIsNotNone(out['quality_receipt'])
        self.assertEqual(Decimal(out['public_payload']['observations'][0]['ppm_decimal']), Decimal('99999.000000000000000000001'))

    def test_review_regression_actual_whole_family_must_match_verified_proof(self):
        for mutation in ('drop_variant', 'invent_parent'):
            kw = fixture('CC', ['20.1', '20.2'])
            if mutation == 'drop_variant':
                kw['transport']['joint_maps'] = kw['transport']['joint_maps'][:1]
            else:
                kw['transport']['joint_maps'] = tuple(({i: '999999' for i in mapping} for mapping in kw['transport']['joint_maps']))
            out = run(kw)
            self.assertIsNone(out['quality_receipt'])
            self.assertIsNone(out['public_payload'])
            self.assertFalse(out['ledger']['gate_outcomes']['C4']['passed'])

    def test_review_regression_missing_structure_id_conflict_is_not_silently_ignored(self):
        kw = fixture()
        entry = {k: v for k, v in kw['transport'].items() if k in ('source', 'nucleus', 'record_id')}
        entry['restriction'] = 'known_C_conflict_without_structure_binding'
        kw['known_conflicts_json'] = json.dumps(dict(schema='C_known_source_conflicts_v1', nucleus_scope='13C', records=[entry]))
        kw['known_conflicts_sha256'] = core.text_sha256(kw['known_conflicts_json'])
        out = run(kw)
        self.assertIsNone(out['quality_receipt'])
        self.assertFalse(out['ledger']['gate_outcomes']['C7']['passed'])
        self.assertIn('known_conflict_registry_scope_invalid', out['ledger']['reasons'])

    def test_review_regression_decimal_conditions_and_keep_public_consistency(self):

        def finite_conditions(row):
            row['experimental_conditions'].update(temperature=298.15, pH=7.4)
            row['experimental_conditions']['frequency'] = None
        out = run(fixture(mutate=finite_conditions))
        self.assertIsNotNone(out['quality_receipt'])
        self.assertIsNotNone(out['public_payload'])
        conditions = out['public_payload']['actual_conditions']
        self.assertEqual(Decimal(conditions['temperature']), Decimal('298.15'))
        self.assertEqual(Decimal(conditions['pH']), Decimal('7.4'))
        self.assertIsNone(conditions['frequency'])
        bad = run(fixture(mutate=lambda r: r['experimental_conditions'].update(temperature=True)))
        self.assertIsNone(bad['quality_receipt'])
        self.assertIsNone(bad['public_payload'])
        self.assertFalse(bad['ledger']['gate_outcomes']['C8']['passed'])

    def test_rule_or_implementation_hash_mismatch_no_keep(self):
        kw = fixture()
        config = json.loads(kw['rule_config_json'])
        config['source_reference_implementation_sha256'] = 'f' * 64
        kw['rule_config_json'] = json.dumps(config)
        kw['rule_config_sha256'] = core.text_sha256(kw['rule_config_json'])
        self.assertIsNone(run(kw)['quality_receipt'])

    def test_transport_lineage_and_quality_evidence_survive_JSON_roundtrip(self):
        kw = fixture('CCCCCCCCCCCC')
        kw['transport'] = json.loads(json.dumps(kw['transport']))
        kw['transport'] = transport_core.restore_joint_map_keys(kw['transport'])
        out = run(kw)
        self.assertIsNotNone(out['quality_receipt'])
        self.assertEqual(out['quality_receipt']['evidence_sha256'], producer.digest(json.loads(json.dumps(out['evidence_bundle']))))
if __name__ == '__main__':
    unittest.main()
