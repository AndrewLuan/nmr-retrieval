# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：REPORT-P1独立合成回归，只核保存compatible应用域及冻结off证据。
fixture使用真实字段形状的虚构身份/axis，不读取真实test；不调用模型、求解或重拟合。
直接guard反例与完整saved-file report接口共同验证；保留原dadbb review/probe历史字节。
既有execution_tests不修改、不重跑；其旧exact-only报告fixture不是本P1完整compatible域。
"""
import copy, json, tempfile, unittest
from pathlib import Path
from dataclasses import asdict
from unittest.mock import patch
import TEST_STAGE_B_report as r
import TEST_STAGE_B_execution_contract as c

def fixture(pipeline=True):
    frozen = []
    expected = {}
    applied = []
    for method in ('B0', 'B1', 'B2'):
        axis = dict(method=method, nucleus='13C', truth_basis='source_relative_current_serialization', task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', endpoint='per_peak_compatibility', sampling_unit='observation', cohort_sha256='a' * 64, source_sha256='b' * 64, label_sha256='c' * 64, rule_sha256='d' * 64)
        status = 'off_insufficient_support' if method == 'B0' else 'off_audit_rejected'
        threshold = None if method == 'B0' else 5
        frozen.append(dict(axis=axis, status=status, threshold=threshold, published_ids=[]))
        semantic = {k: axis[k] for k in c.component.SEMANTIC_AXES}
        expected['synthetic_C', method, 'obs'] = dict(semantic_axis=semantic, pipeline_available=pipeline)
        v = dict(input_id='synthetic_C', baseline=method, observation_id='obs', publication_enabled=False, refit=False, status='off_no_matching_reviewed_Cval_artifact', threshold=None)
        if pipeline:
            v.update(status=status, stored_status=status, stored_threshold=threshold, frozen_threshold_available=False, frozen_threshold_axis=copy.deepcopy(axis), test_semantic_axis=copy.deepcopy(semantic), margin=None, margin_certified=False)
        applied.append(v)
    return (applied, expected, frozen)

class ReportP1(unittest.TestCase):

    def reject(self, mutation):
        a, e, f = fixture()
        mutation(a, e, f)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            r.validate_threshold_applications(a, e, f)

    def test_empty_applications_rejected(self):
        self.reject(lambda a, e, f: a.clear())

    def test_missing_B2_rejected(self):
        self.reject(lambda a, e, f: a.pop())

    def test_duplicate_rejected(self):
        self.reject(lambda a, e, f: a.append(copy.deepcopy(a[0])))

    def test_foreign_input_rejected(self):
        self.reject(lambda a, e, f: a[0].update(input_id='foreign'))

    def test_fake_on_with_false_publication_rejected(self):

        def mutation(a, e, f):
            for v in a:
                v.update(status='on_exact_reviewed_semantic_axis', stored_status='on_audit_passed', stored_threshold=999, frozen_threshold_available=True)
        self.reject(mutation)

    def test_axis_provenance_rejected(self):
        self.reject(lambda a, e, f: a[1]['frozen_threshold_axis'].update(rule_sha256='e' * 64))

    def test_wrong_threshold_rejected(self):
        self.reject(lambda a, e, f: a[1].update(stored_threshold=999))

    def test_missing_semantic_axis_rejected(self):
        self.reject(lambda a, e, f: a[1]['test_semantic_axis'].pop('endpoint'))

    def test_missing_frozen_method_rejected(self):
        self.reject(lambda a, e, f: f.pop())

    def test_nonnull_off_preserved(self):
        a, e, f = fixture()
        v = r.validate_threshold_applications(a, e, f)
        self.assertEqual(v['validated_applications'], 3)
        self.assertEqual(a[1]['stored_threshold'], 5)
        self.assertFalse(a[1]['publication_enabled'])

    def test_pipeline_unavailable_fallback(self):
        a, e, f = fixture(False)
        self.assertTrue(r.validate_threshold_applications(a, e, f)['stored_statuses_preserved'])

    def test_no_matching_semantic_fallback(self):
        a, e, f = fixture(False)
        for v in e.values():
            v['pipeline_available'] = True
        for v in f:
            v['axis']['target_level'] = 'atom'
        self.assertEqual(r.validate_threshold_applications(a, e, f)['validated_applications'], 3)

    def test_fallback_cannot_assert_stored_on(self):
        a, e, f = fixture(False)
        a[0]['stored_status'] = 'on_audit_passed'
        with self.assertRaisesRegex(ValueError, 'fallback_must_not_assert'):
            r.validate_threshold_applications(a, e, f)

    def test_empty_queue_valid(self):
        _, _, f = fixture()
        self.assertEqual(r.validate_threshold_applications([], {}, f)['validated_applications'], 0)

    def test_saved_report_complete_failed_cache_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            root = folder / 'score'
            root.mkdir()
            (root / 'raw').mkdir()
            (root / 'evaluation').mkdir()

            def save(p, v):
                c.write(p, v)
                return c.item(p)
            iid = 'synthetic_C'
            queue = [iid]
            ledger = folder / 'ledger.jsonl'
            ledger.write_text(json.dumps(dict(input_id=iid, record_id='synthetic', connectivity_sha256='synthetic_group')) + '\n')
            cache = folder / 'cache.jsonl'
            cache.write_text(json.dumps(dict(input_id=iid, status='failed_retained')) + '\n')
            package = save(folder / 'pack.json', dict(original_identity_denominator=binding('TEST_STAGE_B_REPORT_P1_regression.frozen_identity_count.1'), scorequeue=1))
            plan = save(folder / 'plan.json', dict(input_ids=queue, repo=str(c.D.parents[1] / 'nmr-retrieval'), packaging_manifest=package, inputs=dict(ledger=c.item(ledger), cache_input_ledger=c.item(cache))))
            helper = r.estimator(c.item(c.D / 'frozen_report_estimators.py'))
            bundles = {}
            initial = {}
            applied, expected, frozen = fixture(False)
            for method in ('B0', 'B1', 'B2'):
                ctx = dict(truth_basis='source_relative_current_serialization', nucleus='13C', task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', baseline=method, record_id='synthetic', connectivity_id='synthetic_group')
                rows = [asdict(helper.EvaluationRow(tuple(ctx.items()), m, 'obs', True, False, False, (), (), (), ())) for m in ('exact_observation', 'compatible_observation')]
                bundles[method] = dict(rows=rows, metadata=dict(input_id=iid, roles=['native_test']), pipeline_status=None)
                initial[method] = copy.deepcopy(rows)
            save(root / 'raw' / (iid + '.json'), dict(input_id=iid, plan_sha256=plan['sha256'], raw_execution=dict(status='failed_retained')))
            save(root / 'evaluation' / (iid + '.json'), bundles)
            save(root / 'evaluation' / (iid + '.not_started.json'), initial)
            save(root / 'frozen_Cval_threshold_application.json', applied)
            completed = save(root / 'manifest.json', dict(status='FROZEN_ASSIGNMENT_EXECUTION_COMPLETED', input_records=1, original_identity_denominator=binding('TEST_STAGE_B_REPORT_P1_regression.frozen_identity_count.2'), plan_sha256=plan['sha256'], record_ledger=[dict(input_id=iid)]))
            inv = save(folder / 'inventory.json', dict(child_exit=0, outer_exit=0, output_sha256={str(p.relative_to(root)): dict(sha256=c.sha(p)) for p in root.rglob('*') if p.is_file()}))
            cfg = save(folder / 'cfg.json', dict(suite_manifest_sha256='synthetic_suite', scoring_plan=plan, completed_scoring_manifest=completed, scoring_output_inventory=inv, estimators=c.item(c.D / 'frozen_report_estimators.py'), output_directory=str(folder / 'report')))
            suite = dict(Cval_frozen_calibration=save(folder / 'frozen.json', frozen), Cval_actual_application_review=dict(sha256='e' * 64))
            with patch.object(c, 'bind_suite', return_value=(suite, dict(queue=queue, full_C=[]))):
                result = r.report(cfg, dict(sha256='synthetic_suite'), {})
            self.assertEqual(result['highconfidence']['application_validation']['validated_applications'], 3)
            self.assertEqual(len(result['native_test']['summaries']), 6)
            self.assertTrue(all((v['eligible_units'] == 1 and v['successes'] == 0 for v in result['native_test']['summaries'])))
if __name__ == '__main__':
    unittest.main(verbosity=2)
