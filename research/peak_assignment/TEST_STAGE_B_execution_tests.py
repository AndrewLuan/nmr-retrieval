# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：仅合成验证新增Stage B执行层的进程、预算、门禁与saved-row报告接口。
P1报告fixture更新为完整compatible应用域与冻结三method off metadata；空队列unit fixture明确mock claim，真实claim由独立four-gates覆盖。
不读取真实test/A结果，不调用模型、求解或真实评分；不重跑已锁组件测试。
所有子进程有监督deadline及finally清理；READY文件由子进程写出，避免固定sleep同步。
"""
import json, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
import TEST_STAGE_B_execution_contract as c
import TEST_STAGE_B_phase_supervisor as s
import TEST_STAGE_B_report as r

class ExecutionTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def budget(self, wall=3):
        return dict(CPU_threads=1, GPU=0, RSS_bytes=8589934592, total_wall_seconds=wall, record_workers=1, cleanup_seconds=2)

    def run_child(self, code, prefix='child', wall=3, **kw):
        return s.supervise_process([sys.executable, '-c', code], directory=self.root, prefix=prefix, budget=self.budget(wall), cwd=self.root, phase='synthetic', **kw)

    def test_success_actual_exits(self):
        v = self.run_child('raise SystemExit(0)')
        self.assertEqual((v['actual_inner_exit'], v['actual_outer_exit']), (0, 0))
        self.assertFalse(v['owned_survivors'])

    def test_nonzero_retained_no_retry(self):
        v = self.run_child('raise SystemExit(7)')
        self.assertEqual((v['actual_inner_exit'], v['actual_outer_exit'], v['retries']), (7, 1, 0))

    def test_exclusive_launch(self):
        self.run_child('pass')
        with self.assertRaises(FileExistsError):
            self.run_child('pass')

    def test_timeout_ready_and_reaped(self):
        ready = self.root / 'READY'
        code = 'from pathlib import Path; import threading; Path(' + repr(str(ready)) + ").write_text('READY'); threading.Event().wait(20)"
        v = self.run_child(code, wall=2)
        self.assertTrue(ready.exists())
        self.assertEqual(v['termination_reason'], 'wall_limit')
        self.assertEqual(v['actual_outer_exit'], 1)
        self.assertTrue(v['leader_reaped'])
        self.assertFalse(v['owned_survivors'])

    def test_descendant_after_leader_exit(self):
        ready = self.root / 'descendant_READY'
        child = 'from pathlib import Path; import threading; Path(' + repr(str(ready)) + ").write_text('READY'); threading.Event().wait(20)"
        code = "import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c'," + repr(child) + ']); end=time.monotonic()+5\nwhile not Path(' + repr(str(ready)) + ').exists():\n if time.monotonic()>end: raise SystemExit(9)\n time.sleep(.001)'
        v = self.run_child(code, wall=8)
        self.assertTrue(ready.exists())
        self.assertEqual(v['actual_inner_exit'], 0)
        self.assertFalse(v['owned_survivors'])
        self.assertTrue(v['leader_reaped'])

    def test_preflight_consumes_wall_before_spawn(self):
        v = self.run_child('raise SystemExit(0)', started_monotonic=time.monotonic() - 4)
        self.assertIsNone(v['actual_inner_exit'])
        self.assertEqual(v['actual_outer_exit'], 1)
        self.assertIn('preflight_wall_budget_exhausted', v['error'])

    def test_budget_and_no_future_cache_binding(self):
        self.assertEqual([c.BUDGETS[x]['total_wall_seconds'] for x in ('prediction', 'package', 'score', 'report')], [900, 300, 7200, 600])
        self.assertEqual(c.BUDGETS['score']['record_workers'], 1)
        self.assertFalse(c.contract()['actual_execution_authorized'])
        self.assertNotIn('predictions_sha256', c.contract())
        c.verify_locked()

    def test_dynamic_domain_rejected_before_phase_launch(self):
        cfg = dict(ordered_input_ids=['wrong'], original_C_identity_count=binding('TEST_STAGE_B_execution_tests.frozen_identity_count.1'))
        c.write(self.root / 'config.json', cfg)
        phase = dict(schema='TEST_STAGE_B_execution_phase_v1', execution_authorized=True, phase='score', suite_manifest_sha256='suite', budget=c.BUDGETS['score'], config=c.item(self.root / 'config.json'))
        c.write(self.root / 'phase.json', phase)
        with patch.object(c, 'bind_suite', return_value=({}, {'queue': ['synthetic']})):
            with self.assertRaisesRegex(ValueError, 'dynamic_A_queue_original3637'):
                c.validate_phase({'sha256': 'suite'}, {}, c.item(self.root / 'phase.json'))

    def test_phase_not_released(self):
        c.write(self.root / 'phase.json', dict(schema='TEST_STAGE_B_execution_phase_v1', execution_authorized=False))
        with patch.object(c, 'bind_suite', return_value=({}, {'queue': []})):
            with self.assertRaisesRegex(ValueError, 'phase_manifest'):
                c.validate_phase({}, {}, c.item(self.root / 'phase.json'))

    def test_native_test_frozen_estimator_and_unsupported_denominator(self):
        helper = r.estimator(c.item(c.D / 'frozen_report_estimators.py'))
        rows = []
        for method in ('B0', 'B1', 'B2'):
            ctx = dict(truth_basis='source_relative_current_serialization', nucleus='13C', task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', baseline=method, record_id='synthetic', connectivity_id='synthetic_group')
            rows.append(helper.EvaluationRow(tuple(ctx.items()), 'exact_observation', 'obs', True, False, False, (), (), (), ()))
        result = r.estimate_native_test(rows, helper)
        self.assertEqual(result['role'], 'native_test')
        self.assertEqual(len(result['summaries']), 3)
        for v in result['summaries']:
            self.assertEqual(v['eligible_units'], 1)
            self.assertEqual(v['successes'], 0)
            self.assertEqual(v['determinate_assignment_success_rate'], 0)
            self.assertEqual(v['stratum']['role'], 'native_test')
            self.assertEqual(v['chemical_quotient_top3_status'], 'unsupported')
        self.assertEqual(r.estimate_native_test([], helper)['summaries'], [])

    def test_inventory_gold_gate_immutable(self):
        base = dict(metric='exact_observation', observation_id='p', context=[], eligible=True, eligibility_reason_codes=[], eligibility_determinator=[])
        changed = dict(base, eligible=False)
        self.assertNotEqual(r.inventory_domain([base]), r.inventory_domain([changed]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            r.inventory_domain([base, base])

    def test_saved_report_full_api_failed_cache_row(self):
        from dataclasses import asdict
        helper = r.estimator(c.item(c.D / 'frozen_report_estimators.py'))
        repo = c.D.parents[1] / 'nmr-retrieval'
        queue = ['synthetic_C']
        root = self.root / 'score'
        root.mkdir()
        (root / 'raw').mkdir()
        (root / 'evaluation').mkdir()

        def save(path, v):
            c.write(path, v)
            return c.item(path)
        ledger = self.root / 'ledger.jsonl'
        ledger.write_text(json.dumps(dict(input_id=queue[0], record_id='synthetic', connectivity_sha256='synthetic_group')) + '\n')
        cache = self.root / 'cache.jsonl'
        cache.write_text(json.dumps(dict(input_id=queue[0], status='failed_retained')) + '\n')
        package = save(self.root / 'pack.json', dict(original_identity_denominator=binding('TEST_STAGE_B_execution_tests.frozen_identity_count.2'), scorequeue=1))
        plan = save(self.root / 'plan.json', dict(input_ids=queue, repo=str(repo), packaging_manifest=package, inputs=dict(ledger=c.item(ledger), cache_input_ledger=c.item(cache))))
        save(root / 'raw' / (queue[0] + '.json'), dict(input_id=queue[0], plan_sha256=plan['sha256'], raw_execution=dict(status='failed_retained')))
        bundles = {}
        initial = {}
        for method in ('B0', 'B1', 'B2'):
            ctx = dict(truth_basis='source_relative_current_serialization', nucleus='13C', task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', baseline=method, record_id='synthetic', connectivity_id='synthetic_group')
            row = asdict(helper.EvaluationRow(tuple(ctx.items()), 'exact_observation', 'obs', True, False, False, (), (), (), ()))
            row2 = dict(row, metric='compatible_observation')
            bundles[method] = dict(rows=[row, row2], metadata=dict(input_id=queue[0], roles=['native_test']), pipeline_status=None)
            initial[method] = [row, row2]
        save(root / 'evaluation' / (queue[0] + '.json'), bundles)
        save(root / 'evaluation' / (queue[0] + '.not_started.json'), initial)
        save(root / 'frozen_Cval_threshold_application.json', [dict(input_id=queue[0], baseline=m, observation_id='obs', publication_enabled=False, refit=False, status='off_no_matching_reviewed_Cval_artifact', threshold=None) for m in ('B0', 'B1', 'B2')])
        completed = save(root / 'manifest.json', dict(status='FROZEN_ASSIGNMENT_EXECUTION_COMPLETED', input_records=1, original_identity_denominator=binding('TEST_STAGE_B_execution_tests.frozen_identity_count.3'), plan_sha256=plan['sha256'], record_ledger=[dict(input_id=queue[0])]))
        inventory = save(self.root / 'inventory.json', dict(child_exit=0, outer_exit=0, output_sha256={str(p.relative_to(root)): dict(sha256=c.sha(p)) for p in root.rglob('*') if p.is_file()}))
        config = save(self.root / 'report_config.json', dict(suite_manifest_sha256='synthetic_suite', scoring_plan=plan, completed_scoring_manifest=completed, scoring_output_inventory=inventory, estimators=c.item(c.D / 'frozen_report_estimators.py'), output_directory=str(self.root / 'report')))
        frozen = [dict(axis=dict(method=m, nucleus='13C', truth_basis='source_relative_current_serialization', task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', endpoint='per_peak_compatibility', sampling_unit='observation', cohort_sha256='a' * 64, source_sha256='b' * 64, label_sha256='c' * 64, rule_sha256='d' * 64), status='off_audit_rejected', threshold=5, published_ids=[]) for m in ('B0', 'B1', 'B2')]
        suite = dict(Cval_frozen_calibration=save(self.root / 'frozen.json', frozen), Cval_actual_application_review=dict(sha256='synthetic_review'))
        with patch.object(c, 'bind_suite', return_value=(suite, dict(queue=queue, full_C=[]))):
            result = r.report(config, dict(sha256='synthetic_suite'), {})
        self.assertEqual(result['coverage']['original_C_identity_denominator'], binding('TEST_STAGE_B_execution_tests.frozen_identity_count.4'))
        self.assertEqual(result['coverage']['H_original_identity_denominator'], binding('TEST_STAGE_B_execution_tests.frozen_identity_count.5'))
        self.assertEqual(result['highconfidence']['published'], 0)
        self.assertEqual(result['coverage']['cache_lifecycle_counts'], {'failed_retained': 1})
        self.assertTrue(all((v['eligible_units'] == 1 and v['successes'] == 0 for v in result['native_test']['summaries'])))

    def test_empty_queue_no_model_outputs_require_actual_audit(self):
        suite = dict(stage_A_binding=dict(stage_A_output_manifest=dict(sha256='synthetic_A')))
        a = dict(full_C=[], queue=[], data=dict(ledger=[]))
        with patch.object(c, 'bind_suite', return_value=(suite, a)), patch.object(c, 'claim_phase', return_value={'path': 'synthetic_claim', 'sha256': 'f' * 64}):
            v = c.prepare_prediction(dict(sha256='synthetic_suite'), {}, self.root / 'empty')
        self.assertTrue(v['actual_cache_application_review_still_required'])
        self.assertEqual(Path(v['cache_predictions']['path']).read_bytes(), b'')
        receipt = json.loads(Path(v['receipt']['path']).read_text())
        self.assertEqual((receipt['C_model_loads'], receipt['H_model_loads'], receipt['forward_started']), (0, 0, 0))
        self.assertIsNone(receipt['actual_inner_exit'])
        self.assertFalse(receipt['child_started'])
if __name__ == '__main__':
    unittest.main(verbosity=2)
