# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：Stage B接口的纯合成协议测试，不读取真实test、Cval结果或阈值。
用A实际receipt/五表shape构固定5008账本，验证C3637原序、动态队列、门禁及阈值apply-off。
不调用模型、transport、求解器、真实评价或校准拟合；临时文件全部finally删除。
"""
from pathlib import Path
from types import SimpleNamespace
import json, tempfile, unittest, copy, ast
import TEST_STAGE_B_control as ctl
import TEST_STAGE_B_package as package
import TEST_STAGE_B_C_caller as caller

class StageBTests(unittest.TestCase):

    def artifact(self, root, name, values):
        p = root / (name + '.jsonl')
        p.write_text(''.join((json.dumps(v) + '\n' for v in values)))
        return dict(path=str(p), sha256=ctl.sha(p), rows=len(values))

    def boundjson(self, root, name, value):
        p = root / (name + '.json')
        p.write_text(json.dumps(value) + '\n')
        return dict(path=str(p), sha256=ctl.sha(p))

    def fixture(self, root, public_count=2):
        ledger = []
        public = []
        unknown = []
        lineage = []
        for i in range(binding('TEST_STAGE_B_tests.frozen_identity_count.1')):
            C = i >= binding('TEST_STAGE_B_tests.frozen_identity_count.2')
            iid = ('C-test:' if C else 'H-') + str(i)
            available = C and i < binding('TEST_STAGE_B_tests.frozen_identity_count.3') + public_count
            ledger.append(dict(input_id=iid, identity_ordinal=i, nucleus='13C' if C else '1H', public_available=available, reference_admitted=available))
            lineage.append(dict(input_id=iid, evidence=None))
            if available:
                public.append(dict(input_id=iid, nucleus='13C', smiles='CC', actual_conditions={}, observations=[dict(observation_id='bin:0', ppm_decimal='1.00')]))
            else:
                unknown.append(dict(input_id=iid, reason='synthetic unavailable'))
        codes = {k: dict(sha256=ctl.A_OUTER_SHA if k == 'outer' else 'a' * 64) for k in ('outer', 'C_test_producer', 'source_reference', 'source_transport')}
        extraction = self.boundjson(root, 'extraction', dict(codes=codes))
        arts = {n: self.artifact(root, n, v) for n, v in dict(ledger=ledger, public=public, unknown=unknown, lineage=lineage).items()}
        receipt = self.boundjson(root, 'receipt', dict(status='complete', exit_code=0, stage_B_authorized=False, models=0, solves=0, scores=0, manifest_sha256=extraction['sha256'], codes=codes, artifacts=arts))
        review = self.boundjson(root, 'review', dict(decision='PASS_SYNTHETIC_SOURCE_ONLY', stage_A_output_manifest_sha256=receipt['sha256']))
        return (dict(stage_A_output_manifest=receipt, stage_A_actual_admission_review=review, stage_A_extraction_manifest=extraction, stage_A_outer=dict(path=str(ctl.D / 'TEST_STAGE_A_fixed_test_outer.py'), sha256=ctl.A_OUTER_SHA)), ledger)

    def test_actual_A_schema_order_and_dynamic_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, ledger = self.fixture(Path(tmp))
            a = ctl.bind_stage_A(plan)
            self.assertEqual(len(a['ordered_C_ids']), binding('TEST_STAGE_B_tests.frozen_identity_count.4'))
            self.assertEqual(a['queue'], [ledger[i]['input_id'] for i in (binding('TEST_STAGE_B_tests.frozen_identity_count.5'), 1372)])
            req = ctl.prediction_request(plan, a)
            self.assertIsNone(req['future_prediction_sha256'])
            self.assertIsNone(req['cache_application_review'])
            self.assertEqual(req['max_forward_started'], 2)
            self.assertEqual(req['expected_H_model_loads'], 0)

    def test_all_unknown_has_no_C_or_H_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, _ = self.fixture(Path(tmp), 0)
            a = ctl.bind_stage_A(plan)
            self.assertEqual(len(a['ordered_C_ids']), binding('TEST_STAGE_B_tests.frozen_identity_count.6'))
            self.assertEqual(a['queue'], [])
            self.assertEqual(ctl.prediction_request(plan, a)['expected_C_model_loads'], 0)

    def test_failed_partial_A_does_not_authorize_B(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, _ = self.fixture(Path(tmp))
            p = Path(plan['stage_A_output_manifest']['path'])
            r = json.loads(p.read_text())
            r['status'] = 'failed'
            p.write_text(json.dumps(r))
            plan['stage_A_output_manifest']['sha256'] = ctl.sha(p)
            with self.assertRaisesRegex(ValueError, 'A_actual_complete_only'):
                ctl.bind_stage_A(plan)

    def test_public_identifier_rename_preserves_values_and_hidden_rejected(self):
        p = dict(input_id='synthetic', nucleus='13C', smiles='CC', actual_conditions={'temperature': '298.1500'}, observations=[dict(observation_id='p', ppm_decimal='1.000')])
        v = ctl.cache_public(p)
        self.assertEqual(v['observations'], [dict(bin_id='p', ppm_decimal='1.000')])
        self.assertEqual(v['actual_conditions'], p['actual_conditions'])
        bad = copy.deepcopy(p)
        bad['observations'][0]['members'] = [0]
        with self.assertRaises(ValueError):
            ctl.cache_public(bad)
        bad = copy.deepcopy(p)
        bad['actual_conditions']['source'] = 'secret'
        with self.assertRaises(ValueError):
            ctl.cache_public(bad)

    def test_stage_A_release_not_B_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = self.boundjson(Path(tmp), 'release', dict(stage='A', execution_authorized=True))
            with self.assertRaisesRegex(ValueError, 'B_separate_owner_release'):
                ctl.stage_B_release(item, 'a' * 64, 'prediction_once', 'b' * 64)

    def test_exact_complete_semantic_axes_and_off(self):
        axis = dict(method='B2', nucleus='13C', truth_basis='source_relative_current_serialization', task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', endpoint='per_peak_compatibility', sampling_unit='observation')
        artifact = dict(axis=axis, status='on_audit_passed', threshold=2.0)
        self.assertTrue(ctl.frozen_axis_gate(axis, [artifact])['publication_enabled'])
        for key in ctl.SEMANTIC_AXES:
            changed = dict(axis, **{key: 'different'})
            self.assertFalse(ctl.frozen_axis_gate(changed, [artifact])['publication_enabled'])
        self.assertFalse(ctl.frozen_axis_gate(axis, [dict(artifact, status='off_insufficient_support')])['publication_enabled'])
        with self.assertRaises(ValueError):
            ctl.frozen_axis_gate({'method': 'B2'}, [])

    def test_cache_review_only_after_artifacts_and_failed_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pred = self.artifact(root, 'pred', [])
            ci = self.artifact(root, 'ci', [dict(input_id='i', status='failed_retained', error='unsupported_feature:79/54')])
            review = self.boundjson(root, 'cacheReview', dict(decision='PASS_SYNTHETIC', pred=pred['sha256'], inp=ci['sha256'], N=1))
            plan = dict(cache_predictions=pred, cache_inputs=ci, cache_application_review=review, cache_review_fields=dict(decision=['decision'], predictions_sha256=['pred'], inputs_sha256=['inp'], input_count=['N']))
            inputs, preds = ctl.bind_cache_review(plan, ['i'])
            self.assertEqual(inputs['i']['status'], 'failed_retained')
            self.assertEqual(preds, {})
            bad = copy.deepcopy(plan)
            bad['cache_predictions'] = None
            with self.assertRaises(ValueError):
                ctl.bind_cache_review(bad, ['i'])

    def test_prediction_preparation_release_is_external_no_hash_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, _ = self.fixture(root)
            numeric = self.boundjson(root, 'numeric', {'synthetic': True})
            ex = Path(plan['stage_A_extraction_manifest']['path'])
            v = json.loads(ex.read_text())
            v['numeric_config'] = numeric
            ex.write_text(json.dumps(v))
            plan['stage_A_extraction_manifest']['sha256'] = ctl.sha(ex)
            rp = Path(plan['stage_A_output_manifest']['path'])
            a = json.loads(rp.read_text())
            a['manifest_sha256'] = ctl.sha(ex)
            rp.write_text(json.dumps(a))
            plan['stage_A_output_manifest']['sha256'] = ctl.sha(rp)
            rev = Path(plan['stage_A_actual_admission_review']['path'])
            r = json.loads(rev.read_text())
            r['stage_A_output_manifest_sha256'] = ctl.sha(rp)
            rev.write_text(json.dumps(r))
            plan['stage_A_actual_admission_review']['sha256'] = ctl.sha(rev)
            plan.update(execution_authorized=True, stage_B_numeric_config=numeric, prediction_resources={'synthetic_resource_plan': True}, prediction_preparation_directory=str(root / 'prediction-inputs'))
            original = self.boundjson(root, 'Bplan', plan)
            implreview = self.boundjson(root, 'implementation-review', dict(decision='PASS_SYNTHETIC_ONLY', entrypoint_sha256=ctl.sha(ctl.__file__)))
            release = self.boundjson(root, 'Brelease', dict(independent_implementation_review=implreview, implementation_review_fields=dict(decision=['decision'], entrypoint_sha256=['entrypoint_sha256']), schema='original_owner_test_stage_B_release_v1', stage='B', execution_authorized=True, manifest_sha256=original['sha256'], entrypoint_sha256=ctl.sha(ctl.__file__), C_fixed_identity_count=binding('TEST_STAGE_B_tests.frozen_identity_count.7'), H_fixed_identity_count=binding('TEST_STAGE_B_tests.frozen_identity_count.8'), authorized_phases=['prediction_once'], no_retry=True, owner_authorization_evidence_sha256='a' * 64, release_id='synthetic'))
            result = ctl.materialize_prediction_inputs(plan, original['sha256'], release)
            self.assertFalse(result['execution_authorized'])
            self.assertEqual(result['public']['rows'], 2)
            self.assertIsNone(result['future_prediction_sha256'])
            self.assertNotIn('owner_release', json.loads(Path(original['path']).read_text()))
            saved = json.loads((root / 'prediction-inputs/fixed_C_identity_coverage.json').read_text())
            self.assertEqual(len(saved['rows']), binding('TEST_STAGE_B_tests.frozen_identity_count.9'))

    def test_positive_threshold_audit_rejected_never_publishes_even_high_margin(self):
        from dataclasses import make_dataclass
        for method in ('B1', 'B2'):
            axis = dict(method=method, nucleus='13C', truth_basis='source_relative_current_serialization', task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', endpoint='per_peak_compatibility', sampling_unit='observation', cohort_sha256='a' * 64, source_sha256='b' * 64, label_sha256='c' * 64, rule_sha256='d' * 64)
            artifact = dict(axis=axis, status='off_audit_rejected', threshold=0.01)
            Axis = make_dataclass('SyntheticFrozenAxis', [(k, str) for k in axis])
            record = SimpleNamespace(axis=Axis(**axis), gold_eligible=True, prediction_supported=True, margin_certified=True, margin=999.0)
            adapter = SimpleNamespace(calibration_record_from_evaluation=lambda *a, **kw: record)
            context = dict(baseline=method, nucleus='13C', truth_basis=axis['truth_basis'], task_semantics=axis['task_semantics'], target_level='parent', target_semantics='set')
            row = SimpleNamespace(observation_id='p', context=tuple(context.items()), metric='compatible_observation')
            result = caller.apply_frozen_threshold(adapter, row, {'pipeline_status': {}}, {'_frozen_calibration': [artifact]}, {'tie_relative_tolerance': 1e-07})
            self.assertFalse(result['publication_enabled'])
            self.assertIsNone(result['threshold'])
            self.assertEqual(result['status'], 'off_audit_rejected')
            self.assertEqual(result['stored_threshold'], 0.01)

    def test_caller_has_no_fit_and_preserves_deadline_source(self):
        tree = ast.parse((ctl.D / 'TEST_STAGE_B_C_caller.py').read_text())
        names = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertNotIn('calibrate', names)
        self.assertNotIn('cluster_bootstrap', names)
        self.assertEqual(caller.anonymous_payload, caller.BASE.anonymous_payload)
        self.assertEqual(caller.evaluate_one, caller.BASE.evaluate_one)
        self.assertEqual(caller.bound_snapshot, caller.BASE.bound_snapshot)
        self.assertEqual(caller.strip_late_support, caller.BASE.strip_late_support)
        off = caller.apply_frozen_threshold(None, SimpleNamespace(observation_id='p', context=(('baseline', 'B2'),), metric='compatible_observation'), {}, {'_frozen_calibration': []}, {})
        self.assertFalse(off['publication_enabled'])
if __name__ == '__main__':
    unittest.main()
