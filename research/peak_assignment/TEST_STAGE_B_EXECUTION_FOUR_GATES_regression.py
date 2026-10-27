# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：执行层四finding独立回归，真实入口+完整合成A五表及原固定asset metadata。
所有5008身份均为临时虚构，真实Cval只读冻结控制metadata；不读真实test或执行模型/求解。
fixture不伪称真实审批；所有synthetic PASS/release仅在TemporaryDirectory内用于schema门禁验证。
监督用真实子进程/PG/RSS/wall；READY状态和有限条件等待覆盖预检/最终hash阻塞及finally清理。
"""
import copy, json, os, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch
import TEST_STAGE_B_control as ctl
import TEST_STAGE_B_execution_contract as c
import TEST_STAGE_B_phase_supervisor as s
D = workspace()
REPO = repository()

def save(p, v):
    c.write(p, v)
    return c.item(p)

def jsonl(p, rows):
    with p.open('x') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')
    return c.item(p)

class Fixture:

    def __init__(self, root, public_count=0):
        self.root = root
        self.queue = ['synthetic_C0'] if public_count else []
        bridge = c.load(c.item(artifact_path('reviews/stage_A_metadata_recovery_closure_bridge_astra.json')))
        codepaths = dict(outer=artifact_path('TEST_STAGE_A_fixed_test_outer.py'), C_test_producer=artifact_path('TEST_STAGE_A_C_reference_rule_producer.py'), source_reference=REPO / 'nmr_assignment/source_reference.py', source_transport=REPO / 'nmr_assignment/source_transport.py')
        codes = {k: c.item(v) for k, v in codepaths.items()}
        assert {k: v['sha256'] for k, v in codes.items()} == bridge['reviewed_stage_A_closure']['code_sha256']
        numeric = c.item(artifact_path('numerical_implementation_config.json'))
        cal = c.item(artifact_path('C_val_assignment_results/calibration_artifacts.json'))
        validation_result = dict(path='SYNTHETIC_METADATA_ONLY_NO_OPEN', sha256=bridge['reviewed_stage_A_closure']['validation_result_sha256']['C'])
        extraction = save(root / 'extraction.json', dict(codes=codes, numeric_config=numeric, validation=dict(C=dict(threshold_artifact=cal, validation_result=validation_result))))
        ledger = []
        for nucleus, count in (('1H', binding('TEST_STAGE_B_EXECUTION_FOUR_GATES_regression.frozen_identity_count.1')), ('13C', binding('TEST_STAGE_B_EXECUTION_FOUR_GATES_regression.frozen_identity_count.2'))):
            for i in range(count):
                iid = ('synthetic_H' if nucleus == '1H' else 'synthetic_C') + str(i)
                ledger.append(dict(input_id=iid, identity_ordinal=len(ledger), nucleus=nucleus, public_available=iid in self.queue, reference_admitted=iid in self.queue, variant='synthetic', non_evaluable_reason=None if iid in self.queue else 'synthetic_unavailable'))
        public = [dict(input_id=iid, nucleus='13C', smiles='CC', actual_conditions={}, observations=[dict(observation_id='synthetic_obs', ppm_decimal='1')]) for iid in self.queue]
        tables = dict(ledger=ledger, public=public, unknown=[dict(input_id=r['input_id'], reason='synthetic_unavailable') for r in ledger if not r['reference_admitted']], lineage=[dict(input_id=r['input_id'], evidence={}) for r in ledger], hidden=[dict(input_id=r['input_id'], identity={}, evidence={}) for r in ledger])
        artifacts = {}
        for name, rows in tables.items():
            artifacts[name] = dict(**jsonl(root / (name + '.jsonl'), rows), rows=len(rows))
        receipt = save(root / 'A_receipt.json', dict(status='complete', exit_code=0, stage_B_authorized=False, models=0, solves=0, scores=0, manifest_sha256=extraction['sha256'], artifacts=artifacts, inputs={}, codes=codes))
        review = save(root / 'SYNTHETIC_A_REVIEW.json', dict(decision='PASS_SYNTHETIC_SCHEMA_FIXTURE_NOT_ACTUAL_APPROVAL', stage_A_output_manifest_sha256=receipt['sha256']))
        A = dict(stage_A_output_manifest=receipt, stage_A_actual_admission_review=review, stage_A_extraction_manifest=extraction, stage_A_outer=codes['outer'], stage_A_protocol_bridge=c.item(artifact_path('reviews/stage_A_metadata_recovery_closure_bridge_astra.json')))
        names = dict(execution_contract='TEST_STAGE_B_execution_contract.py', phase_supervisor='TEST_STAGE_B_phase_supervisor.py', report_adaptor='TEST_STAGE_B_report.py', locked_control='TEST_STAGE_B_control.py', locked_package='TEST_STAGE_B_package.py', locked_caller='TEST_STAGE_B_C_caller.py', builder='build_frozen_prediction_cache.py', estimators='frozen_report_estimators.py', base_caller='run_frozen_C_assignment_baselines.py', base_packager='prepare_C_scoring_artifacts.py')
        impl = {k: c.item(artifact_path(n)) for k, n in names.items()}
        sourcemap = {k: v['sha256'] for k, v in impl.items()}
        code_review = save(root / 'SYNTHETIC_SOURCE_REVIEW.json', dict(decision='PASS_SYNTHETIC_SCHEMA_FIXTURE_NOT_ACTUAL_APPROVAL', source_sha256=sourcemap))
        cal_review = save(root / 'SYNTHETIC_CAL_REVIEW.json', dict(decision='PASS_SYNTHETIC_SCHEMA_FIXTURE_NOT_ACTUAL_APPROVAL', calibration_artifacts_sha256=cal['sha256'], validation_result_sha256=validation_result['sha256']))
        template = c.item(artifact_path('frozen_C_cache_deploy_bundle_released/assets.json'))
        native = c.load(template)['source_files']
        self.suite = dict(schema='TEST_STAGE_B_execution_suite_v1', execution_authorized=True, authorized_phases=list(c.BUDGETS), budget=c.BUDGETS, implementations=impl, stage_A_binding=A, execution_contract_independent_review=code_review, execution_review_fields=dict(decision=['decision'], source_sha256=['source_sha256']), numeric_config=numeric, Cval_frozen_calibration=cal, Cval_actual_application_review=cal_review, Cval_review_fields=dict(decision=['decision'], calibration_artifacts_sha256=['calibration_artifacts_sha256'], validation_result_sha256=['validation_result_sha256']), Cval_scoring_rule_contract=c.item(artifact_path('C_val_scoring_rule_contract.json')), once_claim_root=str(root / 'claims'), phase_python={n: sys.executable for n in c.BUDGETS}, prediction_python=sys.executable, working_directory=str(root), prediction_asset_template=template, prediction_source_files=native, builder=impl['builder'])
        self.si = save(root / 'suite.json', self.suite)
        self.release = dict(schema='original_owner_test_stage_B_execution_release_v1', decision='ALLOW_ONCE_C_FIXED_TEST_STAGE_B', suite_manifest_sha256=self.si['sha256'], C_fixed_identity_count=binding('TEST_STAGE_B_EXECUTION_FOUR_GATES_regression.frozen_identity_count.3'), H_fixed_identity_count=binding('TEST_STAGE_B_EXECUTION_FOUR_GATES_regression.frozen_identity_count.4'), no_retry=True, owner_authorization_evidence_sha256='f' * 64, release_id='SYNTHETIC_NOT_ACTUAL_RELEASE', once_claim_root=self.suite['once_claim_root'], implementation_sha256=sourcemap)
        self.ri = save(root / 'release.json', self.release)

    def phase(self, name, cfg, stem):
        ci = save(self.root / (stem + '_config.json'), cfg)
        return save(self.root / (stem + '_phase.json'), dict(schema='TEST_STAGE_B_execution_phase_v1', execution_authorized=True, phase=name, suite_manifest_sha256=self.si['sha256'], budget=c.BUDGETS[name], config=ci))

    def base_config(self, out):
        return dict(python_executable=sys.executable, ordered_input_ids=self.queue, original_C_identity_count=binding('TEST_STAGE_B_EXECUTION_FOUR_GATES_regression.frozen_identity_count.5'), stage_A_receipt_sha256=self.suite['stage_A_binding']['stage_A_output_manifest']['sha256'], output_directory=str(out))

    def prediction_phase(self):
        assert self.queue
        a = ctl.bind_stage_A(self.suite['stage_A_binding'])
        cohort = jsonl(self.root / 'prediction_public.jsonl', [ctl.cache_public(a['public'][iid]) for iid in self.queue])
        template = c.load(self.suite['prediction_asset_template'])
        assets = dict(template, files=dict(template['files']))
        nom = c.item(artifact_path('frozen_C_cache_deploy_bundle_released/frozen_assets/predictor_nomination_astra.json'))
        nomv = c.load(nom)
        scope = save(self.root / 'prediction_scope.json', dict(schema='prediction_cache_scope_release_v1', production_cache_authorized=True, cohort_sha256=cohort['sha256'], checkpoint_sha256={'1H': nomv['H']['sha256'], '13C': c.C_CKPT}))
        assets['files'].update(nomination=nom, numeric_config=self.suite['numeric_config'], scope_release=scope)
        bp = save(self.root / 'builder_plan.json', dict(schema='frozen_prediction_cache_plan_v1', execution_authorized=True, wall_seconds_total=900, CPU_threads=2, GPU_devices=0, RSS_limit_bytes=8589934592, input_count=1, max_forward_started=1, load_seconds_per_model=300, forward_seconds_per_model=600, python_executable=sys.executable))
        cfg = dict(self.base_config(self.root / 'prediction_result'), expected_H_model_loads=0, expected_C_model_loads=1, builder=self.suite['builder'], cohort=cohort, assets=save(self.root / 'prediction_assets.json', assets), builder_plan=bp)
        return (self.phase('prediction', cfg, 'prediction'), cfg)

    def report_phase(self, stem='report', bad_count=False):
        score = self.root / (stem + '_saved')
        score.mkdir()
        applied = save(score / 'frozen_Cval_threshold_application.json', [])
        ledger = jsonl(self.root / (stem + '_packledger.jsonl'), [])
        cache = jsonl(self.root / (stem + '_cacheledger.jsonl'), [])
        package = save(self.root / (stem + '_pack.json'), dict(original_identity_denominator=binding('TEST_STAGE_B_EXECUTION_FOUR_GATES_regression.frozen_identity_count.6'), scorequeue=0))
        plan = save(self.root / (stem + '_scoreplan.json'), dict(input_ids=[], repo=str(REPO), packaging_manifest=package, inputs=dict(ledger=ledger, cache_input_ledger=cache)))
        completed = save(score / 'manifest.json', dict(status='FROZEN_ASSIGNMENT_EXECUTION_COMPLETED', input_records=0, original_identity_denominator=binding('TEST_STAGE_B_EXECUTION_FOUR_GATES_regression.frozen_identity_count.7'), plan_sha256=plan['sha256'], record_ledger=[]))
        inventory = save(self.root / (stem + '_saved_inventory.json'), dict(child_exit=0, outer_exit=0, output_sha256={p.name: dict(sha256=c.sha(p)) for p in score.iterdir()}))
        actual = save(self.root / (stem + '_score_actual.json'), dict(actual_inner_exit=0, actual_worker_exit=0, actual_outer_exit=0, last_worker_stage='inventory_completed', child_output_inventory=inventory))
        cfg = dict(self.base_config(self.root / (stem + '_result')), scoring_actual_supervisor_receipt=actual, entrypoint=self.suite['implementations']['report_adaptor'], suite_manifest=self.si, owner_suite_release=self.ri, suite_manifest_sha256=self.si['sha256'], scoring_plan=plan, completed_scoring_manifest=completed, scoring_output_inventory=inventory, estimators=self.suite['implementations']['estimators'])
        if bad_count:
            cfg['original_C_identity_count'] = 0
        return (self.phase('report', cfg, stem), cfg)

class FourGates(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def directory(self, name):
        p = self.root / name
        p.mkdir()
        return p

    def test_real_bind_suite_recovery_bridge_and_Cval_rule(self):
        f = Fixture(self.root)
        suite, a = c.bind_suite(f.si, f.ri)
        self.assertEqual(len(a['full_C']), binding('TEST_STAGE_B_EXECUTION_FOUR_GATES_regression.frozen_identity_count.8'))
        self.assertEqual(a['queue'], [])
        self.assertEqual(ctl.A_OUTER_SHA, c.sha(artifact_path('TEST_STAGE_A_fixed_test_outer.py')))
        self.assertEqual(suite['Cval_scoring_rule_contract']['sha256'], binding('TEST_STAGE_B_EXECUTION_FOUR_GATES_regression.exact_SHA_or_identity.9'))

    def test_real_prediction_request_fixed_asset_schema_no_forward(self):
        f = Fixture(self.root, 1)
        phase, cfg = f.prediction_phase()
        _, a, p, config, argv = c.validate_phase(f.si, f.ri, phase)
        self.assertEqual(a['queue'], ['synthetic_C0'])
        self.assertIn('--assets-manifest', argv)
        self.assertEqual(config['expected_H_model_loads'], 0)
        self.assertEqual(c.sha(argv[2]), c.BUILDER_SHA)

    def test_real_prediction_request_rejects_runner_drift(self):
        f = Fixture(self.root, 1)
        _, cfg = f.prediction_phase()
        assets = c.load(cfg['assets'])
        assets['runner_sha256'] = '0' * 64
        cfg['assets'] = save(self.root / 'wrongassets.json', assets)
        phase = f.phase('prediction', cfg, 'badprediction')
        with self.assertRaisesRegex(ValueError, 'cache_builder_asset_SHA'):
            c.validate_phase(f.si, f.ri, phase)

    def test_real_A_bridge_required_exact(self):
        f = Fixture(self.root)
        A = copy.deepcopy(f.suite['stage_A_binding'])
        A['stage_A_protocol_bridge']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'A_exact_metadata_recovery_bridge'):
            ctl.bind_stage_A(A)

    def test_once_scope_alternate_supervisor_and_output_real_entrypoint(self):
        f = Fixture(self.root)
        phase, cfg = f.report_phase()
        first = s.execute(f.si, f.ri, phase, self.directory('supervisor1'), phase_name='report')
        self.assertEqual((first['actual_inner_exit'], first['actual_outer_exit']), (0, 0), first)
        self.assertEqual(first['last_worker_stage'], 'inventory_completed')
        self.assertTrue(Path(first['child_output_inventory']['path']).exists())
        final_inventory = c.load(first['child_output_inventory'])
        self.assertEqual(final_inventory['outer_exit'], 0)
        self.assertIsNone(c.load(final_inventory['worker_inventory'])['outer_exit'])
        self.assertTrue(first['phase_input_postcheck_passed'])
        phase2, cfg2 = f.report_phase('report2')
        second = s.execute(f.si, f.ri, phase2, self.directory('supervisor2'), phase_name='report')
        self.assertEqual(second['actual_outer_exit'], 1)
        self.assertIsNone(second['actual_inner_exit'])
        self.assertIn('FileExistsError', second['worker_error'])
        self.assertFalse(Path(cfg2['output_directory']).exists())

    def test_failed_preflight_claim_retained(self):
        f = Fixture(self.root)
        phase, _ = f.report_phase(bad_count=True)
        bad = s.execute(f.si, f.ri, phase, self.directory('bad'), phase_name='report')
        self.assertEqual(bad['actual_outer_exit'], 1)
        self.assertIn('dynamic_A_queue', bad['worker_error'])
        phase2, _ = f.report_phase('afterfailure')
        again = s.execute(f.si, f.ri, phase2, self.directory('again'), phase_name='report')
        self.assertIn('FileExistsError', again['worker_error'])
        self.assertEqual(len(list((self.root / 'claims').glob('*.json'))), 1)

    def test_empty_prediction_claims_both_scopes_no_model(self):
        f = Fixture(self.root)
        v = c.prepare_prediction(f.si, f.ri, self.root / 'prepared_empty')
        receipt = c.load(v['receipt'])
        self.assertEqual(receipt['forward_started'], 0)
        self.assertIsNone(receipt['actual_inner_exit'])
        claims = [json.loads(p.read_text()) for p in (self.root / 'claims').glob('*.json')]
        self.assertEqual({(v['phase'], v['scope']) for v in claims}, {('prediction', 'execution'), ('prediction', 'preparation')})
        with self.assertRaises(FileExistsError):
            c.prepare_prediction(f.si, f.ri, self.root / 'prepared_again')

    def test_preparation_failure_retains_claim(self):
        f = Fixture(self.root)
        out = self.directory('exists')
        with self.assertRaisesRegex(ValueError, 'new_prediction_preparation'):
            c.prepare_prediction(f.si, f.ri, out)
        with self.assertRaises(FileExistsError):
            c.prepare_prediction(f.si, f.ri, self.root / 'different')

    def run_synthetic_worker(self, kind):
        f = Fixture(self.root)
        worker = self.directory('worker')
        ready = self.root / 'READY'
        out = self.root / 'synthetic_output'
        phase = f.si
        setup = 'import sys;sys.path.insert(0,' + repr(str(D)) + ');import TEST_STAGE_B_phase_supervisor as s;import TEST_STAGE_B_execution_contract as c;from pathlib import Path;import threading,json'
        if kind == 'preflight':
            validator = 'def validate(*args):\n Path(' + repr(str(ready)) + ").write_text('READY')\n threading.Event().wait(20)\n"
            patching = 'c.validate_phase=validate\n'
        else:
            validator = "def validate(*args):\n return ({'implementations':{},'working_directory':" + repr(str(self.root)) + "},{},{'phase':'report','config':" + repr(f.si) + "},{'output_directory':" + repr(str(out)) + "},[sys.executable,'-c'," + repr('from pathlib import Path;p=Path(' + repr(str(out)) + ");p.mkdir();(p/'data').write_text('synthetic')") + '])\n'
            patching = 'c.validate_phase=validate\noldsha=c.sha\ndef sha(path):\n if Path(path)==Path(' + repr(str(out / 'data')) + '):\n  Path(' + repr(str(ready)) + ").write_text('READY')\n  threading.Event().wait(20)\n return oldsha(path)\nc.sha=sha\n"
        script = setup + '\n' + validator + patching + 'raise SystemExit(s.phase_worker(' + repr(f.si) + ',' + repr(f.ri) + ',' + repr(phase) + ",'report'," + repr(str(worker)) + '))'
        result = s.supervise_process([sys.executable, '-c', script], directory=worker, prefix='outer', budget=dict(CPU_threads=1, GPU=0, RSS_bytes=8589934592, total_wall_seconds=2, record_workers=1, cleanup_seconds=2), cwd=self.root, phase='synthetic', inner_state_path=worker / 'TEST_STAGE_B_report_worker_state.json')
        self.assertTrue(ready.exists(), result)
        self.assertEqual(result['termination_reason'], 'wall_limit')
        self.assertEqual(result['actual_outer_exit'], 1)
        self.assertFalse(result['owned_survivors'])
        return (result, worker)

    def test_active_preflight_deadline_receipt_no_phase_child(self):
        result, worker = self.run_synthetic_worker('preflight')
        self.assertIsNone(result['actual_inner_exit'])
        self.assertEqual(result['last_worker_stage'], 'before_validate_phase')
        self.assertTrue((worker / 'outer_actual.json').exists())

    def test_inventory_deadline_never_early_outer_success(self):
        result, worker = self.run_synthetic_worker('inventory')
        self.assertEqual(result['actual_inner_exit'], 0)
        self.assertEqual(result['last_worker_stage'], 'before_output_inventory')
        self.assertFalse((worker / 'TEST_STAGE_B_report_child_output_inventory.json').exists())

    def test_default_real_entrypoint_is_checkonly(self):
        p = subprocess.run([sys.executable, '-B', str(artifact_path('TEST_STAGE_B_phase_supervisor.py'))], capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 0)
        self.assertFalse(json.loads(p.stdout)['actual_execution_authorized'])

    def test_claim_root_must_match_exact_owner_release(self):
        f = Fixture(self.root)
        wrong = dict(f.release, once_claim_root=str(self.root / 'other_claims'))
        ri = save(self.root / 'wrong_release.json', wrong)
        with self.assertRaisesRegex(ValueError, 'owner_suite_once_root_binding'):
            c.claim_phase(f.si, ri, 'prediction')
        self.assertFalse((self.root / 'other_claims').exists())

    def test_active_RSS_limit_before_phase_child(self):
        f = Fixture(self.root)
        worker = self.directory('RSS_worker')
        ready = self.root / 'RSS_READY'
        script = 'import sys;sys.path.insert(0,' + repr(str(D)) + ');import TEST_STAGE_B_phase_supervisor as s;import TEST_STAGE_B_execution_contract as c;from pathlib import Path;import threading\ndef validate(*args):\n Path(' + repr(str(ready)) + ").write_text('READY')\n memory=bytearray(128*1024*1024)\n threading.Event().wait(20)\nc.validate_phase=validate\nraise SystemExit(s.phase_worker(" + repr(f.si) + ',' + repr(f.ri) + ',' + repr(f.si) + ",'report'," + repr(str(worker)) + '))'
        v = s.supervise_process([sys.executable, '-c', script], directory=worker, prefix='RSS', budget=dict(CPU_threads=1, GPU=0, RSS_bytes=64 * 1024 * 1024, total_wall_seconds=5, record_workers=1, cleanup_seconds=2), cwd=self.root, phase='synthetic', inner_state_path=worker / 'TEST_STAGE_B_report_worker_state.json')
        self.assertTrue(ready.exists())
        self.assertEqual(v['termination_reason'], 'RSS_limit')
        self.assertEqual(v['actual_outer_exit'], 1)
        self.assertIsNone(v['actual_inner_exit'])
        self.assertFalse(v['owned_survivors'])

    def test_report_requires_final_score_outer_exit_zero(self):
        f = Fixture(self.root)
        _, cfg = f.report_phase()
        actual = c.load(cfg['scoring_actual_supervisor_receipt'])
        actual['actual_outer_exit'] = 1
        cfg['scoring_actual_supervisor_receipt'] = save(self.root / 'failed_score_actual.json', actual)
        phase = f.phase('report', cfg, 'failedscore')
        with self.assertRaisesRegex(ValueError, 'report_actual_final_score_exit_inventory'):
            c.validate_phase(f.si, f.ri, phase)
if __name__ == '__main__':
    unittest.main(verbosity=2)
