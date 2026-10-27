# 功能概述：冻结H尾部续行的公开副本；原actual-run源码与公共源码SHA分开。
# 接口：显式runtime manifest授权及原plan/release/once门禁；身份、前缀、源证据绑定外置。
# 关系：复用六个纯控制原语；保留原budget/完整分母/未知与失败账本；无默认恢复授权。
from portable_runtime import binding, _config
"""功能概述：为失败的冻结H后处理批次建立一次独立尾部续行，不覆盖父批产物。
verify_parent核对冻结设计、父plan/receipt/ledger、所有历史产物及前76行字节；
run_tail仅处理原序列index76起的not_started_unknown，前76不调用helper。
call_one与emit_record从context显式取得已核SHA的original_driver接口，保持anchor、单budget和输出接线；仅精确资源
ValueError可逐条unknown，其余错误停止尾部并保留1408身份。reaggregate只读取保存
标量，不重新计算映射/候选/分数；paired原字节复制。execute需独立once release由
新supervisor验证，并在新目录保存prefix引用、resource_unknown解释overlay和真实退出。
默认check-only只验证控制元数据和父产物；不调用真实helper、不运行模型/求解/校准。
关系：依赖原driver f1e434、helper26322及冻结恢复设计，原文件保持逐字节不变。
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from postprocessing_control_primitives import need, sha, bound, read_bound, save_new, stamp
DESIGN_SHA = binding('resume_frozen_H_postprocessing_batch.exact_source_or_evidence_sha256.1')
ORIGINAL_DRIVER_SHA = binding('resume_frozen_H_postprocessing_batch.exact_source_or_evidence_sha256.2')
PRODUCTS = ('reference_environment_denominators', 'shared_forward', 'candidate_membership', 'witness_objective')
PREFIX = binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.3')
TOTAL = binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.4')

def load_original(item):
    path = bound(item)
    need(item['sha256'] == ORIGINAL_DRIVER_SHA, 'original_driver_exact_SHA')
    spec = importlib.util.spec_from_file_location('resume_original_H_driver', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def exact_resource_error(exc):
    return type(exc) is ValueError and str(exc) == 'source_ledger_preflight_bound'

def unknown(item, status, reason):
    return dict(input_id=item['input_id'], roles=item['roles'], status=status, reason_codes=[reason], reference_denominators=None, shared_forward={}, methods={}, fixed_source_denominators=item['fixed_source_denominators'])

def verify_parent(plan):
    need(plan['schema'] == 'frozen_H_postprocessing_tail_resume_v1' and plan['allow_test'] is False, 'resume_scope')
    need(plan['budget'] == dict(CPU_threads=2, GPU=0, RSS_bytes=4294967296, total_wall_seconds=894, original_plus_tail_wall_seconds=900, per_record_checks=50000, per_record_seconds_after_load=0.25, record_workers=1, cleanup_and_receipt_reserve_seconds=12), 'fixed_resume_budget')
    design_path = bound(plan['design'])
    need(plan['design']['sha256'] == DESIGN_SHA, 'reviewed_recovery_design')
    design = json.loads(design_path.read_text())
    original = read_bound(plan['original_plan']['path'], plan['original_plan']['sha256'])
    root = Path(plan['original_directory'])
    for relative, digest in design['frozen_evidence_sha256'].items():
        if relative.startswith('H_frozen_postprocessing/'):
            need(sha(root / relative.split('/', 1)[1]) == digest, 'historical_artifact_SHA:' + relative)
    actual = read_bound(plan['original_actual']['path'], plan['original_actual']['sha256'])
    need(plan['original_actual']['sha256'] == design['frozen_evidence_sha256']['H_frozen_postprocessing_actual_execution.json'], 'parent_actual_binding')
    receipt = read_bound(root / 'receipt.json', design['original_actual']['receipt_sha256'])
    need(receipt['input_hashes_unchanged'] is True and receipt['status'] == 'FAILED_OR_PARTIAL_NO_RETRY', 'parent_status')
    need(actual['elapsed_seconds'] + 894 <= 900, 'combined_wall_cap')
    need(original == json.loads((root / 'plan.json').read_text()), 'parent_plan_exact')
    for name, digest in receipt['output_sha256'].items():
        need(sha(root / name) == digest, 'parent_product_SHA:' + name)
    ledger = json.loads((root / 'record_completion_ledger.json').read_text())
    need(len(ledger) == TOTAL and [r['input_id'] for r in ledger] == original['input_ids'], 'parent_identity_order')
    need(Counter((r['status'] for r in ledger[:PREFIX])) == Counter(complete=binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.5'), unknown=binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.6'), integrity_error=1), 'prefix_statuses')
    failed = design['failed_record']
    need(ledger[binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.7')]['input_id'] == failed['input_id'] and ledger[binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.8')]['reason_codes'] == [failed['stored_error']], 'exact_historical_error')
    need(all((r['status'] == 'not_started_unknown' for r in ledger[PREFIX:])), 'tail_not_started_only')
    need(plan['tail_input_ids'] == original['input_ids'][PREFIX:] and len(plan['tail_input_ids']) == binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.9'), 'exact_tail')
    prefixes = {}
    for name in PRODUCTS:
        data = (root / (name + '.jsonl')).read_bytes()
        lines = data.splitlines(keepends=True)
        need(len(lines) == TOTAL, 'parent_product_row_domain')
        need([json.loads(line)['input_id'] for line in lines] == original['input_ids'], 'product_identity_order')
        prefix = b''.join(lines[:PREFIX])
        binding = design['first76_original_byte_bindings'][name + '.jsonl']
        need(len(prefix) == binding['first76_bytes'] and hashlib.sha256(prefix).hexdigest() == binding['first76_sha256'], 'prefix_byte_SHA')
        prefixes[name] = prefix
    need(sha(root / 'paired_outcomes.json') == binding('resume_frozen_H_postprocessing_batch.exact_source_or_evidence_sha256.10'), 'paired_original_bytes')
    for item in plan['implementation'].values():
        bound(item)
    return (design, original, ledger, prefixes, actual)

def call_one(context, item, plan, calls):
    TABLES = context['original_driver'].TABLES
    POLICY_KEYS = context['original_driver'].POLICY_KEYS
    helper = context['helper']
    iid = item['input_id']
    values = {name: context['tables'][name][iid,][0] for name in TABLES}
    key = tuple((values['gold']['binding'][k] for k in POLICY_KEYS))
    policy, policy_line = context['policies'][key]
    payload_path = context['raw_paths'][iid, '.payload.json']
    raw_path = context['raw_paths'][iid, '.json']
    raw_payload = payload_path.read_bytes()
    raw_result = json.loads(raw_path.read_text())
    record_started = time.monotonic()
    budget = helper.DiagnosticBudget(max_checks=50000, time_limit_seconds=0.25)
    args = dict(public=values['public'], gold=values['gold'], policy=policy, admission_receipt=values['admissions']['receipt'], prediction_row=values['predictions'], lineage_receipt=values['lineages']['receipt'], raw_result=raw_result, numeric_config=context['numeric_config'], roles=item['roles'])
    evidence = tuple((str(context['sources'][name]) + ':' + str(context['tables'][name][iid,][1]) for name in TABLES)) + (str(context['sources']['policy']) + ':' + str(policy_line), str(raw_path), str(payload_path))
    anchor = helper.EvidenceAnchor(payload_sha256={name: context['canonical_digest'](args[name]) for name in helper.INPUT_NAMES}, raw_payload_sha256=hashlib.sha256(raw_payload).hexdigest(), source_application_review_sha256=plan['inputs']['source_application_review']['sha256'], cache_application_review_sha256=plan['inputs']['cache_application_review']['sha256'], source_cohort_sha256=plan['source_cohort_sha256'], evidence_ids=evidence, joint_family_sha256=None)
    calls[0] += 1
    result = helper.process_record(input_id=iid, raw_payload=raw_payload, evidence_anchor=anchor, joint_family=None, budget=budget, **args)
    return (result, record_started)

def emit_record(context, item, result, streams, plan_sha):
    emit = context['original_driver'].emit
    iid = item['input_id']
    prediction = context['tables']['predictions'][iid,][0]
    common = dict(input_id=iid, roles=item['roles'], connectivity_id=item['connectivity_id'], truth_basis='source_relative_current_serialization', nucleus='1H', assignment_task_semantics='derived_serialized_value_bin', reference_sha256=result.get('reference_sha256'), prediction_artifact_sha256=prediction['prediction_artifact_sha256'], numeric_config_sha256=context['canonical_digest'](context['numeric_config']), raw_execution_file_sha256=context['checked'][str(context['raw_paths'][iid, '.json'])], anonymous_payload_file_sha256=context['checked'][str(context['raw_paths'][iid, '.payload.json'])], plan_sha256=plan_sha, status=result['status'])
    emit(streams['reference_environment_denominators'], dict(common, source_binding=item['source_binding'], denominator=result.get('reference_denominators'), fixed_source_denominators=item['fixed_source_denominators'], targets=result.get('reference_targets'), gold_eligible_observations=result.get('gold_eligible_observations')))
    emit(streams['shared_forward'], dict(common, diagnostic=result.get('shared_forward')))
    emit(streams['candidate_membership'], dict(common, methods=result.get('methods', {})))
    emit(streams['witness_objective'], dict(common, methods=result.get('methods', {})))

def run_tail(items, prior, invoke, guard):
    """Synthetic-testable single attempt state machine; no prefix invocation."""
    need(len(items) == len(prior) and all((a['input_id'] == b['input_id'] for a, b in zip(items, prior))), 'tail_join')
    error = None
    for item, previous in zip(items, prior):
        need(previous['status'] == 'not_started_unknown', 'tail_retry_forbidden')
        started = None
        if error is None:
            try:
                guard()
            except TimeoutError:
                error = 'batch_wall_limit'
        if error:
            yield (item, unknown(item, 'not_started_unknown', error), started)
            continue
        try:
            result, started = invoke(item)
        except Exception as exc:
            if exact_resource_error(exc):
                result = unknown(item, 'resource_unknown', 'resource_unknown:ValueError:source_ledger_preflight_bound')
            else:
                error = 'integrity_error:' + type(exc).__name__ + ':' + str(exc)
                result = unknown(item, 'integrity_error', error)
        need(result['input_id'] == item['input_id'] and result['roles'] == item['roles'], 'helper_result_identity')
        result['fixed_source_denominators'] = item['fixed_source_denominators']
        yield (item, result, started)

def reaggregate(original, output, identities):
    summary, methods = (original.SavedForwardSummary(), original.SavedMethodSummary())
    files = {name: (output / (name + '.jsonl')).open() for name in PRODUCTS}
    try:
        for index, item in enumerate(identities):
            rows = {name: json.loads(next(stream)) for name, stream in files.items()}
            need(all((v['input_id'] == item['input_id'] for v in rows.values())), 'joined_order')
            den = rows['reference_environment_denominators']
            record = dict(input_id=item['input_id'], roles=item['roles'], status='resource_unknown' if index == binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.11') else den['status'], reference_denominators=den.get('denominator'), fixed_source_denominators=den['fixed_source_denominators'], shared_forward=rows['shared_forward'].get('diagnostic') or {}, methods=rows['candidate_membership'].get('methods', {}), gold_eligible_observations=den.get('gold_eligible_observations'))
            summary.add(record)
            methods.add(record)
        need(all((stream.readline() == '' for stream in files.values())), 'joined_extra_rows')
    finally:
        for stream in files.values():
            stream.close()
    return dict(schema='frozen_H_postprocessing_tail_saved_scalar_summary_v1', fixed_identities=TOTAL, per_role=summary.result(), per_role_method=methods.result(), source_only_overlay_index=binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.12'), threshold_refit=False, scientific_recomputation=False)

def execute(plan_path, plan_sha):
    started = time.monotonic()
    plan = read_bound(plan_path, plan_sha)
    need(plan['execution_authorized'] is True, 'resume_not_authorized')
    design, parent, prior, prefixes, actual = verify_parent(plan)
    original = load_original(plan['original_driver'])
    output = Path(plan['output_directory'])
    output.mkdir(parents=True, exist_ok=False)
    identities = original.frozen_source_identities(parent)
    save_new(output / 'plan.json', plan)
    save_new(output / 'fixed_identity_ledger.json', identities)
    save_new(output / 'prefix_resource_overlay.json', dict(index=binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.13'), input_id=prior[binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.14')]['input_id'], historical_status='integrity_error', historical_reason=prior[binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.15')]['reason_codes'], effective_status='resource_unknown', design_sha256=DESIGN_SHA, original_completion_ledger_sha256=sha(Path(plan['original_directory']) / 'record_completion_ledger.json')))
    records = list(prior[:PREFIX])
    provenance = [dict(input_id=r['input_id'], index=i, mode='reused', historical_status=r['status'], effective_status='resource_unknown' if i == binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.16') else r['status']) for i, r in enumerate(records)]
    calls = [0]
    error = None
    context = None
    streams = {}
    try:
        context = original.prepare(plan['original_plan']['path'], plan['original_plan']['sha256'], output_already_created=True)
        context['original_driver'] = original

        def guard():
            if time.monotonic() - started >= plan['budget']['total_wall_seconds'] - plan['budget']['cleanup_and_receipt_reserve_seconds']:
                raise TimeoutError('resume_work_deadline')
        for name in PRODUCTS:
            stream = (output / (name + '.jsonl')).open('x')
            stream.buffer.write(prefixes[name])
            stream.flush()
            streams[name] = stream
        invoke = lambda item: call_one(context, item, parent, calls)
        for index, (item, result, record_started) in enumerate(run_tail(identities[PREFIX:], prior[PREFIX:], invoke, guard), PREFIX):
            emit_record(context, item, result, streams, plan_sha)
            records.append(dict(input_id=item['input_id'], roles=item['roles'], status=result['status'], budget_checks=result.get('budget_checks'), reason_codes=result.get('reason_codes', []), elapsed_seconds_after_load=time.monotonic() - record_started if record_started is not None else None))
            provenance.append(dict(input_id=item['input_id'], index=index, mode='continued' if result['status'] != 'not_started_unknown' else 'not_started', effective_status=result['status']))
            if result['status'] in ('integrity_error', 'not_started_unknown'):
                error = result['reason_codes'][0]
    except Exception as exc:
        error = 'preflight_or_join_integrity_error:' + type(exc).__name__ + ':' + str(exc)
    finally:
        for stream in streams.values():
            stream.close()
    if len(records) < TOTAL:
        for index in range(len(records), TOTAL):
            item = identities[index]
            records.append(dict(input_id=item['input_id'], roles=item['roles'], status='not_started_unknown', reason_codes=[error]))
            provenance.append(dict(input_id=item['input_id'], index=index, mode='not_started', effective_status='not_started_unknown'))
            for name in PRODUCTS:
                path = output / (name + '.jsonl')
                if not path.exists():
                    path.write_bytes(prefixes[name])
                with path.open('a') as stream:
                    common = dict(input_id=item['input_id'], roles=item['roles'], status='not_started_unknown', reason_codes=[error])
                    if name == 'reference_environment_denominators':
                        common.update(denominator=None, fixed_source_denominators=item['fixed_source_denominators'])
                    elif name == 'shared_forward':
                        common['diagnostic'] = {}
                    else:
                        common['methods'] = {}
                    original.emit(stream, common)
    save_new(output / 'record_completion_ledger.json', records)
    save_new(output / 'record_provenance.json', provenance)
    (output / 'paired_outcomes.json').write_bytes((Path(plan['original_directory']) / 'paired_outcomes.json').read_bytes())
    save_new(output / 'summary.json', reaggregate(original, output, identities))
    prefix_ok = True
    for name, prefix in prefixes.items():
        with (output / (name + '.jsonl')).open('rb') as stream:
            prefix_ok &= stream.read(len(prefix)) == prefix
    unchanged = True
    if context:
        unchanged = all((sha(path) == digest for path, digest in context['checked'].items()))
    verify_parent(plan)
    elapsed = time.monotonic() - started
    if not unchanged or not prefix_ok:
        error = 'post_SHA_changed'
    if elapsed >= 894 or actual['elapsed_seconds'] + elapsed > 900:
        error = 'combined_wall_limit'
    counts = Counter((r['status'] for r in records))
    counts['integrity_error'] -= 1
    counts['resource_unknown'] += 1
    receipt = dict(schema='frozen_H_postprocessing_tail_actual_v1', kind='tail_continuation_of_failed_original_run', status='COMPLETED_PENDING_INDEPENDENT_AUDIT' if error is None else 'FAILED_OR_PARTIAL_NO_RETRY', original_plan_sha256=plan['original_plan']['sha256'], original_actual_execution_sha256=plan['original_actual']['sha256'], original_receipt_sha256=design['original_actual']['receipt_sha256'], original_completion_ledger_sha256=design['frozen_evidence_sha256']['H_frozen_postprocessing/record_completion_ledger.json'], prefix_record_count=binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.17'), prefix_product_byte_sha256={k: hashlib.sha256(v).hexdigest() for k, v in prefixes.items()}, tail_ids_sha256=hashlib.sha256(json.dumps(plan['tail_input_ids'], separators=(',', ':')).encode()).hexdigest(), tail_first_index=binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.18'), tail_identity_count=binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.19'), new_helper_calls=calls[0], resource_unknown_counts_and_reason_codes=dict(count=counts['resource_unknown'], exact_code='ValueError:source_ledger_preflight_bound'), new_inner_exit=0 if error is None else 1, new_outer_exit='see supervisor actual_execution receipt', original_plus_tail_wall_seconds=actual['elapsed_seconds'] + elapsed, elapsed_seconds=elapsed, input_hashes_unchanged=unchanged, prefix_hashes_unchanged=prefix_ok, fixed_denominator_accounting=dict(records=TOTAL, source_known_H_slots=sum((x['fixed_source_denominators']['source_known_H_slots'] for x in identities)), serialized_observation_bins=sum((x['fixed_source_denominators']['serialized_observation_bins'] for x in identities))), effective_statuses=dict(counts), error=error, output_sha256={p.name: sha(p) for p in output.iterdir() if p.is_file()}, cleanup_complete='see supervisor', new_model_calls=0, new_solver_calls=0, new_mapping_search=0, new_threshold_selection=0, retries=0, test_rows_read=0)
    save_new(output / 'receipt.json', receipt)
    print(json.dumps(dict(status=receipt['status'], new_helper_calls=calls[0], error=error)))
    return receipt['new_inner_exit']

def main():
    _config()
    p = argparse.ArgumentParser()
    p.add_argument('--plan', required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if a.execute:
        return execute(a.plan, a.plan_sha256)
    plan = read_bound(a.plan, a.plan_sha256)
    verify_parent(plan)
    print(json.dumps(dict(status='CHECK_ONLY_NO_HELPER', tail_count=binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.20'), prefix_reused=binding('resume_frozen_H_postprocessing_batch.frozen_identity_or_prefix_count.21'))))
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
