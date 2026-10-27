# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
import argparse
from dataclasses import asdict, replace
import hashlib
import importlib.util
import json
import math
import os
import re
import resource
from pathlib import Path
import sys
import time
D = workspace()
REPO = repository()
METHODS = ('B0', 'B1', 'B2')
FROZEN_EXECUTION_SHA = binding('run_frozen_assignment_baselines.sha_or_identity.1')
FROZEN_EVALUATION_SHA = binding('run_frozen_assignment_baselines.sha_or_identity.2')
ALLOWED_ROLES = {'fixed_train8192', 'original_val', 'tune'}
VALIDATION_ROLES = {'original_val', 'tune'}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def digest(obj):
    from nmr_assignment.execution import canonical_digest
    return canonical_digest(obj)

def durable(path, obj):
    temp = Path(str(path) + '.tmp')
    with temp.open('w') as f:
        json.dump(obj, f, ensure_ascii=False, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)

def load_adapter(path):
    spec = importlib.util.spec_from_file_location('frozen_assignment_evaluation_adapter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class RawRowIndex:
    """Global byte offsets + opaque IDs only; per-record read/decode is deferred."""

    def __init__(self, path):
        self.path = Path(path)
        self.offsets = {}
        pattern = re.compile(b'"input_id"\\s*:\\s*("(?:[^"\\\\]|\\\\.)*")')
        with self.path.open('rb') as stream:
            while True:
                offset = stream.tell()
                literal = stream.readline()
                if not literal:
                    break
                if not literal.strip():
                    continue
                match = pattern.search(literal)
                if match is None:
                    raise ValueError('row missing opaque input_id')
                iid = json.loads(match.group(1))
                if iid in self.offsets:
                    raise ValueError('duplicate input join')
                self.offsets[iid] = offset

    def __iter__(self):
        return iter(self.offsets)

    def __len__(self):
        return len(self.offsets)

    def __contains__(self, key):
        return key in self.offsets

    def __getitem__(self, key):
        with self.path.open('rb') as stream:
            stream.seek(self.offsets[key])
            row = json.loads(stream.readline())
        if row['input_id'] != key:
            raise ValueError('top-level input identity differs from byte index')
        return row

    def get(self, key, default=None):
        return self[key] if key in self.offsets else default

def index(path, key='input_id'):
    if key != 'input_id':
        raise ValueError('only frozen opaque-ID byte indexes supported')
    return RawRowIndex(path)

def bound_snapshot(cache, lineage):
    if lineage.get('sha256') != digest(lineage['payload']):
        raise ValueError('prediction lineage receipt SHA mismatch')
    if 'predictions' in cache:
        prediction = cache['predictions']
        if digest(prediction) != lineage['payload'].get('prediction_payload_sha256') or digest(prediction['layout']) != lineage['payload'].get('layout_sha256') or digest(dict(blocks=prediction['attachment_blocks'], evidence_ids=prediction['attachment_evidence_ids'])) != lineage['payload'].get('attachment_sha256'):
            raise ValueError('cache layout/attachment lineage binding mismatch')
    snapshot = cache['native_structure_snapshot']
    stated = lineage['payload']['baseline_structure_snapshot_sha256']
    valid = (digest(snapshot), hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest())
    if stated not in valid:
        raise ValueError('native cache snapshot not bound to prediction lineage')
    return snapshot

def anonymous_payload(public, predictions, native_snapshot, numeric):
    from nmr_assignment.execution import _predictions
    pred = _predictions(predictions)
    atoms = {str(a['index']): a for a in native_snapshot['atoms']}
    if len(atoms) != len(native_snapshot['atoms']):
        raise ValueError('native graph duplicate atom IDs')
    exchange = []
    if pred.layout.nucleus == '1H':
        for unit in pred.layout.units:
            if sum((m for _, m in unit.parent_mass)) != unit.nucleus_mass:
                raise ValueError('partial unit parent mass')
            if all((parent in atoms and atoms[parent]['z'] in (7, 8, 16) and (type(mass) is int) and (mass > 0) for parent, mass in unit.parent_mass)):
                exchange.append(unit.unit_id)
    observations = []
    for b in public['observations']:
        if set(b) != {'bin_id', 'ppm_decimal'}:
            raise ValueError('anonymous observations may not contain hidden metadata')
        ppm = float(b['ppm_decimal'])
        if not math.isfinite(ppm):
            raise ValueError('nonfinite anonymous value')
        observations.append(dict(observation_id=b['bin_id'], ppm=ppm))
    if public['nucleus'] != pred.layout.nucleus:
        raise ValueError('public/prediction nucleus mismatch')
    payload = dict(observations=observations, predictions=asdict(pred), exchangeable_unit_ids=exchange, actual_window=None, numeric_config=numeric)
    return (json.dumps(payload, allow_nan=False, separators=(',', ':')).encode(), pred)

def check_plan(plan_path, expected_sha=None):
    path = Path(plan_path)
    if expected_sha and sha(path) != expected_sha:
        raise ValueError('plan SHA mismatch')
    plan = json.loads(path.read_text())
    if tuple(plan['methods']) != METHODS or plan['allow_test'] is not False:
        raise ValueError('fixed methods and explicit no-test scope required')
    global REPO
    REPO = repository()
    sys.path.insert(0, str(REPO))
    os.environ['PYTHONPATH'] = str(REPO) + (os.pathsep + os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else '')
    for name, item in plan['inputs'].items():
        if sha(item['path']) != item['sha256']:
            raise ValueError('input SHA mismatch:' + name)
    for item in plan['implementations']:
        if sha(item['path']) != item['sha256']:
            raise ValueError('implementation SHA mismatch')
    if not plan['reviews']:
        raise ValueError('exact-source independent review bindings required')
    covered = {}
    for item in plan['reviews']:
        if sha(item['path']) != item['sha256']:
            raise ValueError('review SHA mismatch')
        review = json.loads(Path(item['path']).read_text())
        if review.get('decision', review.get('status')) != item['exact_decision'] or not item['exact_decision'].startswith('PASS'):
            raise ValueError('review does not approve exact frozen version')
        for rel, expected in item['implementation_bindings'].items():
            actual = review.get('snapshot_after', review.get('reviewed_sha256', {})).get(rel)
            if actual is None:
                matches = [x for x in review.get('source_snapshots', ()) if x['path'].endswith('/' + rel.removeprefix('D/'))]
                if len(matches) == 1:
                    snap = matches[0]
                    if snap.get('sha256') != snap.get('after_sha256'):
                        raise ValueError('review source changed during audit')
                    actual = snap['sha256']
            if actual != expected:
                raise ValueError('review exact source binding mismatch:' + rel)
            source_path = artifact_path(rel[2:]) if rel.startswith('D/') else REPO / rel
            if sha(source_path) != expected:
                raise ValueError('review source drift:' + rel)
            covered[rel] = expected
    if 'nmr_assignment/execution.py' not in covered:
        raise ValueError('execution independent exact-source PASS missing')
    inputs = {name: item['path'] for name, item in plan['inputs'].items()}
    data = {name: index(inputs[name]) for name in ('public', 'gold', 'ledger', 'admissions', 'cache_input_ledger', 'predictions', 'lineages')}
    ids = tuple(plan['input_ids'])
    if any((not isinstance(i, str) or len(i) != 64 or any((c not in '0123456789abcdef' for c in i)) for i in ids)):
        raise ValueError('opaque SHA256 input IDs required')
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate frozen cohort input')
    for name in ('public', 'gold', 'ledger', 'admissions', 'cache_input_ledger'):
        if set(data[name]) != set(ids):
            raise ValueError('complete frozen input accounting required:' + name)
    if set(data['predictions']) - set(ids) or set(data['lineages']) - set(ids):
        raise ValueError('prediction input outside frozen cohort')
    for iid in ids:
        roles = set(data['ledger'][iid]['roles'])
        if not roles or not roles <= ALLOWED_ROLES:
            raise ValueError('test/unknown role forbidden')
        if roles & VALIDATION_ROLES and 'fixed_train8192' in roles:
            raise ValueError('train/validation connectivity role conflict')
        if data['cache_input_ledger'][iid]['status'] not in ('ready', 'cache_failed', 'not_started', 'unsupported', 'cache_missing', 'native_failed'):
            raise ValueError('explicit approved cache lifecycle status required')
        if data['cache_input_ledger'][iid]['roles'] != data['ledger'][iid]['roles']:
            raise ValueError('cache/cohort role mismatch')
    config = json.loads(Path(inputs['numeric_config']).read_text())
    from nmr_assignment.execution import numeric_config_from_frozen
    numeric = numeric_config_from_frozen(config)
    if numeric['budgets']['per_record_wall_seconds'] != 10:
        raise ValueError('original 10-second record budget required')
    from nmr_assignment.calibration import policy_from_frozen_config
    policy = policy_from_frozen_config(config)
    return (plan, data, config, numeric, policy)

def evaluate_one(adapter, iid, data, predictions, execution, *, plan, execution_payload=None, approved_numeric_config=None, diagnostic_budget=None):
    ledger = data['ledger'][iid]
    if diagnostic_budget is None and predictions is not None:
        from nmr_assignment.diagnostics import DiagnosticBudget
        diagnostic_budget = DiagnosticBudget(max_checks=50000, time_limit_seconds=0.25)
    return {method: adapter.evaluate_record(data['gold'][iid], data['public'][iid], predictions, execution, method=method, roles=ledger['roles'], source_cohort_sha256=plan['source_cohort_sha256'], connectivity_sha256=ledger['connectivity_sha256'], batch_admission_receipt=data['admissions'][iid]['receipt'], prediction_lineage_receipt=data['lineages'].get(iid, {}).get('receipt') if predictions is not None else None, execution_payload=execution_payload, approved_numeric_config=approved_numeric_config, diagnostic_budget=diagnostic_budget) for method in METHODS}

def strip_late_support(bundles):
    """Bookkeeping only: keep frozen gold eligibility, remove late prediction support."""
    for bundle in bundles.values():
        bundle['rows'] = tuple((replace(row, prediction_supported=False, success=False, reason_codes=row.reason_codes + ('pipeline:late_record_consumer_deadline',)) for row in bundle['rows']))
        status = bundle.get('pipeline_status')
        if status is not None:
            bundle['pipeline_status'] = dict(status, certified=False, timed_out=True, observation_determinate={k: False for k in status.get('observation_determinate', {})})
        bundle['metadata']['runner_consumer_deadline_passed'] = True

def run(plan_path, expected_sha):
    plan, data, config, numeric, policy = check_plan(plan_path, expected_sha)
    if not any((item['path'] == str(Path(__file__).resolve()) and item['sha256'] == sha(Path(__file__)) for item in plan['implementations'])):
        raise ValueError('frozen runner implementation SHA missing')
    if plan.get('execution_authorized') is not True or not expected_sha:
        raise ValueError('execution_authorized true and explicit frozen plan SHA required')
    if sha(REPO / 'nmr_assignment/execution.py') != FROZEN_EXECUTION_SHA or plan['inputs']['evaluation_adapter']['sha256'] != FROZEN_EVALUATION_SHA:
        raise ValueError('unified frozen producer/consumer source drift')
    adapter = load_adapter(plan['inputs']['evaluation_adapter']['path'])
    output = Path(plan['output_directory'])
    output.mkdir(exist_ok=False)
    (output / 'raw').mkdir()
    (output / 'evaluation').mkdir()
    from nmr_assignment.execution import execute_record
    from nmr_assignment.metrics import summarize
    from nmr_assignment.calibration import calibrate
    start = time.monotonic()
    queue = [dict(input_id=iid, methods={m: 'not_started' for m in METHODS}, gold_artifact_sha256=plan['inputs']['gold']['sha256'], admission_artifact_sha256=plan['inputs']['admissions']['sha256']) for iid in plan['input_ids']]
    durable(output / 'initial_not_started_fixed_denominators.json', dict(queue=queue, fixed_gold_denominator_artifacts={k: plan['inputs'][k] for k in ('gold', 'admissions', 'ledger')}, policy='All queued identities remain in denominator even if no worker completion file exists.'))
    rows_by_partition = {'train': [], 'validation': []}
    calibration_rows = []
    record_events = []
    from nmr_assignment.diagnostics import DiagnosticBudget
    for iid in plan['input_ids']:
        record_started = time.monotonic()
        record_deadline = record_started + numeric['budgets']['per_record_wall_seconds']
        preprocessing_deadline = min(record_started + numeric['budgets']['mapping_and_candidates_seconds'], record_deadline - numeric['budgets']['result_validation_reserve_seconds'])
        one = {name: {iid: data[name][iid]} if iid in data[name] else {} for name in ('public', 'gold', 'ledger', 'admissions', 'cache_input_ledger')}
        cache_state = one['cache_input_ledger'][iid]
        pred = None
        payload = None
        payload_sha = None
        raw = dict(status=cache_state.get('status', 'not_started'), result=None, timed_out=False)
        initial_bundles = evaluate_one(adapter, iid, one, None, dict(status='not_started', result=None), plan=plan, approved_numeric_config=numeric)
        durable(output / 'evaluation' / (iid + '.not_started.json'), {m: [asdict(row) for row in b['rows']] for m, b in initial_bundles.items()})
        if cache_state.get('status') == 'ready':
            try:
                one['predictions'] = {iid: data['predictions'][iid]}
                one['lineages'] = {iid: data['lineages'][iid]}
                cache = one['predictions'][iid]
                lineage = one['lineages'][iid]['receipt']
                if cache.get('input_id') != iid or lineage['payload']['input_id'] != iid:
                    raise ValueError('cache input identity mismatch')
                snapshot = bound_snapshot(cache, lineage)
                payload, pred = anonymous_payload(one['public'][iid], cache['predictions'], snapshot, numeric)
                payload_sha = hashlib.sha256(payload).hexdigest()
                payload_path = output / 'raw' / (iid + '.payload.json')
                with payload_path.open('xb') as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                raw = execute_record(payload, approved_numeric_config=numeric, input_id=iid, prediction_artifact_sha256=lineage['payload']['prediction_artifact_sha256'], record_started_at=record_started, record_deadline=record_deadline, preprocessing_deadline=preprocessing_deadline)
            except Exception as exc:
                raw = dict(status='unsupported_cache_or_input', result=None, timed_out=False, detail=type(exc).__name__ + ':' + str(exc))
                pred = None
        if 'lineages' not in one:
            one['lineages'] = {}
        durable(output / 'raw' / (iid + '.json'), dict(input_id=iid, raw_execution=raw, anonymous_payload_sha256=payload_sha, cache_input_state=cache_state, record_started_at=record_started, record_deadline=record_deadline, preprocessing_deadline=preprocessing_deadline, plan_sha256=expected_sha))
        remaining = record_deadline - time.monotonic()
        evaluation_execution = raw if remaining > 0 else dict(status='total_deadline', result=None, timed_out=True, reason='late_read_parse_or_durable_consumer')
        budget = DiagnosticBudget(max_checks=50000, time_limit_seconds=min(0.25, max(1e-06, remaining)))
        bundles = evaluate_one(adapter, iid, one, pred, evaluation_execution, plan=plan, execution_payload=payload, approved_numeric_config=numeric, diagnostic_budget=budget)
        if time.monotonic() >= record_deadline:
            strip_late_support(bundles)
        partition = 'validation' if set(one['ledger'][iid]['roles']) & VALIDATION_ROLES else 'train'
        evaluated = {}
        for method, bundle in bundles.items():
            rows_by_partition[partition].extend(bundle['rows'])
            evaluated[method] = dict(rows=[asdict(r) for r in bundle['rows']], metadata=bundle['metadata'], pipeline_status=bundle['pipeline_status'])
            if partition == 'validation' and bundle['pipeline_status'] is not None:
                for row in bundle['rows']:
                    if row.metric != 'compatible_observation':
                        continue
                    calibration_rows.append(adapter.calibration_record_from_evaluation(row, bundle, cohort_sha256=plan['validation_cohort_sha256'], source_sha256=plan['source_sha256'], label_sha256=plan['label_sha256'], rule_sha256=plan['rule_sha256'], relative_tolerance=numeric['tie_relative_tolerance']))
        durable(output / 'evaluation' / (iid + '.json'), evaluated)
        record_events.append(dict(input_id=iid, status=raw['status'], partition=partition, roles=one['ledger'][iid]['roles'], record_elapsed_seconds=time.monotonic() - record_started, record_deadline_overshoot_seconds=max(0.0, time.monotonic() - record_deadline)))
        durable(output / 'record_completion_ledger.json', record_events)
    durable(output / 'calibration_inputs.json', [asdict(r) for r in calibration_rows])
    artifacts = calibrate(calibration_rows, policy=policy) if calibration_rows else ()
    durable(output / 'calibration_artifacts.json', [asdict(a) for a in artifacts])
    summaries = {partition: summarize(rows) for partition, rows in rows_by_partition.items()}
    final = dict(status='FROZEN_ASSIGNMENT_EXECUTION_COMPLETED', input_records=len(plan['input_ids']), methods=METHODS, record_ledger=record_events, summaries=summaries, elapsed_seconds=time.monotonic() - start, plan_sha256=expected_sha, max_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024), calibration_validation_only=True, retry_count=0, actual_window_policy='unknown_None', model_forwards=0, test_inputs=0)
    durable(output / 'manifest.json', final)
    print(json.dumps(final))

def synthetic_checks():
    """Two virtual validation records; only one invokes real prepare/solver once."""
    sys.path.insert(0, str(REPO))
    os.environ['PYTHONPATH'] = str(REPO) + (os.pathsep + os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else '')
    from nmr_assignment.mapping import build_capacity_layout, attach_prediction_carriers
    from nmr_assignment.execution import execute_record, numeric_config_from_frozen
    if sha(REPO / 'nmr_assignment/execution.py') != FROZEN_EXECUTION_SHA or sha(artifact_path('assignment_evaluation_adapter.py')) != FROZEN_EVALUATION_SHA:
        raise ValueError('synthetic requires exact frozen unified producer/consumer')
    adapter = load_adapter(artifact_path('assignment_evaluation_adapter.py'))
    config = json.loads(artifact_path('numerical_implementation_config.json').read_text())
    numeric = numeric_config_from_frozen(config)
    layout = build_capacity_layout(dict(nucleus='1H', parent_mass={'0': 1, '1': 1}, evidence_ids=['synthetic:structural'], isotope_count_verified=True, partition_hypothesis_id='synthetic'))
    pred = attach_prediction_carriers(layout, [dict(component_id='c0', owner_id='0', center_ppm=1.0, mass=1.0, sigma_ppm=0.1, sigma_source='synthetic'), dict(component_id='c1', owner_id='1', center_ppm=2.0, mass=1.0, sigma_ppm=0.1, sigma_source='synthetic')], dict(attachment_blocks=[['parent:0', 'parent:1']], attachment_evidence_ids=['synthetic:attachment']))
    snapshot = dict(canonical_smiles='CN', rdkit_version='synthetic', atoms=[dict(index=0, z=6), dict(index=1, z=7)], bonds=[])

    def fixture(number):
        raw = json.dumps(dict(source_ref='synthetic', nucleus='1H', record_id='synthetic' + str(number), smiles='CN', atom_targets=[1, 2], atom_target_mask=[1, 1]))
        iid = adapter.text_digest('opaque-synthetic-' + str(number))
        binding = dict(source='synthetic', nucleus='1H', record_id='synthetic' + str(number), structure_id=adapter.text_digest('CN'), source_sha256='1' * 64, row_sha256=adapter.text_digest(raw), policy_sha256='2' * 64, cohort_identity_manifest_sha256='3' * 64)
        lineage = dict(implementation_sha256='4' * 64, canonical_smiles='CN', baseline_graph={k: snapshot[k] for k in ('atoms', 'bonds')}, source_suppressed_H_by_parent={}, target_suppressed_H_by_parent={})
        proof = dict(graph_lineage_evidence_sha256=adapter._lineage_digest(lineage), enumeration_truncated=False, parent_projection_rows=[['0', '1']])
        transport = dict(binding, complete=True, enumeration_truncated=False, graph_lineage_evidence=lineage, graph_lineage_evidence_sha256=adapter._lineage_digest(lineage), completeness_evidence=proof, completeness_evidence_sha256=digest(proof), joint_maps=[{0: '0', 1: '1'}])
        gold = dict(input_id=iid, binding=binding, source_raw_line=raw, joint_gold_parent_sets=[[['bin:0', ['0']], ['bin:1', ['1']]]], transport=transport, scoreable=True, truth_basis='source_relative_current_serialization', reference_basis='source_asserted_encoded_graph', trust_basis='internal_source_consistency', trusted_experimental=False, baseline_structure_snapshot=snapshot, baseline_structure_snapshot_sha256=digest(snapshot))
        public = dict(input_id=iid, smiles='CN', nucleus='1H', actual_conditions={}, observations=[dict(bin_id='bin:0', ppm_decimal='1'), dict(bin_id='bin:1', ppm_decimal='2')])
        ap = dict(input_id=iid, binding=binding, reference_payload_sha256=digest(adapter._gold_payload(gold)), admitted=True, joint_nontrivial=True, transport_completeness_evidence_sha256=digest(proof), transport_implementation_sha256='4' * 64, implementation_sha256='6' * 64, rule_version='synthetic', evidence_ids=['synthetic:admitted'])
        pp = dict(input_id=iid, complete=True, baseline_structure_snapshot_sha256=digest(snapshot), layout_sha256=digest(asdict(pred.layout)), attachment_sha256=digest(dict(blocks=pred.attachment_blocks, evidence_ids=pred.attachment_evidence_ids)), prediction_artifact_sha256='5' * 64, prediction_payload_sha256=digest(asdict(pred)), evidence_ids=['synthetic:prediction'])
        return (gold, public, dict(payload=ap, sha256=digest(ap)), dict(payload=pp, sha256=digest(pp)))
    start = time.monotonic()
    gold1, public1, admission1, lineage1 = fixture(1)
    gold2, public2, admission2, lineage2 = fixture(2)
    record_started = time.monotonic()
    payload, decoded = anonymous_payload(public1, asdict(pred), bound_snapshot(dict(native_structure_snapshot=snapshot, predictions=asdict(pred)), lineage1), numeric)
    assert set(json.loads(payload)) == {'observations', 'predictions', 'exchangeable_unit_ids', 'actual_window', 'numeric_config'}
    assert json.loads(payload)['actual_window'] is None
    assert json.loads(payload)['exchangeable_unit_ids'] == ['parent:1']
    execution = execute_record(payload, approved_numeric_config=numeric, input_id=public1['input_id'], prediction_artifact_sha256=lineage1['payload']['prediction_artifact_sha256'], record_started_at=record_started, record_deadline=record_started + 10.0, preprocessing_deadline=record_started + 2.0)
    if execution.get('status') != 'completed' or execution.get('process_reaped') is not True:
        raise AssertionError('synthetic actual prepare/solver did not complete: ' + json.dumps(execution))
    import tempfile
    with tempfile.TemporaryDirectory(prefix='synthetic_assignment_durable_') as tmp:
        raw_path = Path(tmp) / 'raw_before_evaluation.json'
        exact_payload_path = Path(tmp) / 'execution.payload.json'
        exact_payload_path.write_bytes(payload)
        assert exact_payload_path.read_bytes() == payload
        durable(raw_path, execution)
        assert json.loads(raw_path.read_text()) == execution
    bundles = []
    for gold, public, admission, lineage, prediction, raw in ((gold1, public1, admission1, lineage1, decoded, execution), (gold2, public2, admission2, lineage2, None, dict(status='cache_failed', result=None, timed_out=False))):
        methods = {}
        from nmr_assignment.diagnostics import DiagnosticBudget
        shared_diagnostic_budget = DiagnosticBudget(max_checks=50000, time_limit_seconds=0.25)
        for method in METHODS:
            methods[method] = adapter.evaluate_record(gold, public, prediction, raw, method=method, roles=('original_val',), source_cohort_sha256='3' * 64, connectivity_sha256='7' * 64, batch_admission_receipt=admission, prediction_lineage_receipt=lineage, execution_payload=payload if prediction is not None else None, approved_numeric_config=numeric, diagnostic_budget=shared_diagnostic_budget)
        bundles.append(methods)
    for method in METHODS:
        exact = [r for r in bundles[1][method]['rows'] if r.metric == 'exact_observation']
        assert len(exact) == 2 and all((r.eligible and (not r.success) for r in exact))
    ambiguous_checks = []
    for method in ('B1', 'B2'):
        bundle = bundles[0][method]
        compatible = [r for r in bundle['rows'] if r.metric == 'compatible_observation']
        if not all((r.eligible and r.prediction_supported and r.success for r in compatible)):
            raise AssertionError('synthetic actual solver compatibility missing:' + method)
        for row in compatible:
            calibrated = adapter.calibration_record_from_evaluation(row, bundle, cohort_sha256='3' * 64, source_sha256='1' * 64, label_sha256='8' * 64, rule_sha256='9' * 64, relative_tolerance=numeric['tie_relative_tolerance'])
            assert calibrated.margin_certified is False
            ambiguous_checks.append(method + ':' + row.observation_id)
    expired_start = time.monotonic() - 3.0
    expired = execute_record(payload, approved_numeric_config=numeric, input_id=adapter.text_digest('expired-synthetic'), prediction_artifact_sha256=lineage1['payload']['prediction_artifact_sha256'], record_started_at=expired_start, record_deadline=expired_start + 10.0, preprocessing_deadline=expired_start + 2.0)
    assert expired['status'] == 'preprocessing_timeout' and 'execution_receipt' not in expired
    late_bundles = bundles[0]
    fixed_eligible = {m: [r.eligible for r in b['rows']] for m, b in late_bundles.items()}
    strip_late_support(late_bundles)
    assert all(([r.eligible for r in b['rows']] == fixed_eligible[m] and all((not r.success and (not r.prediction_supported) for r in b['rows'])) for m, b in late_bundles.items()))
    return dict(schema='frozen_assignment_runner_synthetic_v1', status='SYNTHETIC_2_RECORDS_PASS', synthetic_records=2, actual_solver_record_calls=1, expired_deadline_no_solver_probe=1, actual_methods=METHODS, frozen_execution_sha256=FROZEN_EXECUTION_SHA, frozen_evaluation_sha256=FROZEN_EVALUATION_SHA, checks=['anonymous strict schema', 'actual_window_unknown', 'native_graph_exchange_only', 'actual_prepare_solver_completed_process_reaped', 'raw_durable_before_evaluation', 'exact_submitted_bytes_retained', 'expired_inherited_predeadline_no_worker', 'late_consumer_strips_support_not_gold_eligibility', 'shared_three_baseline_diagnostic_budget', 'cache_failure_three_baselines_fixed_denominator', 'compatible_parent_ambiguity_not_high_confidence'], ambiguous_confidence_blocks=ambiguous_checks, execution_status=execution['status'], per_record_budget=numeric['budgets']['per_record_wall_seconds'], retry_count=0, elapsed_seconds=time.monotonic() - start, runner_sha256=sha(Path(__file__)), max_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024), real_gold_rows_read=0, real_scores_computed=0, model_forwards=0, test_inputs=0)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan')
    parser.add_argument('--plan-sha256')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--receipt')
    args = parser.parse_args()
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[name] = '1'
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    if args.self_test:
        result = synthetic_checks()
        if args.receipt:
            durable(Path(args.receipt), result)
        print(json.dumps(result))
    elif args.execute:
        run(args.plan, args.plan_sha256)
    else:
        if not args.plan:
            print(json.dumps(resource_plan()))
            return
        plan, data, config, numeric, policy = check_plan(args.plan, args.plan_sha256)
        print(json.dumps(dict(status='CHECK_ONLY_PASS_NO_EXECUTION', input_records=len(plan['input_ids']), resource_plan=resource_plan())))

def resource_plan():
    return dict(status='RUNNER_PREPARED_NO_REAL_EXECUTION', methods=METHODS, concurrent_records=1, threads=1, GPU_devices=0, max_record_workers_allowed=4, actual_record_workers=1, cpu_affinity_on_Linux=2, per_record_wall_seconds=10, preprocessing_seconds=2, memory_policy='Frozen metadata resident; peak RSS measured. Numeric source config defines no new RSS cap.', durable_storage='all-input initial denominator plus each raw result, metric rows, final ledger and calibration inputs', no_retry=True, no_forward=True, no_test=True, actual_window=None, worst_case_solver_wall_seconds='10 * frozen_input_count plus bounded watchdog cleanup and durable IO', execution_gate='--execute + frozen --plan-sha256 + execution_authorized + exact source/review bindings', required_inputs=['public', 'gold', 'ledger', 'admissions', 'cache_input_ledger', 'predictions', 'lineages', 'numeric_config', 'evaluation_adapter'], plan_fields=['repo', 'input_ids', 'inputs(path,sha256)', 'implementations(path,sha256)', 'reviews(path,sha256,exact_decision,implementation_bindings)', 'methods=B0/B1/B2', 'allow_test=false', 'execution_authorized', 'output_directory', 'source_cohort_sha256', 'validation_cohort_sha256', 'source_sha256', 'label_sha256', 'rule_sha256'])
if __name__ == '__main__':
    main()
