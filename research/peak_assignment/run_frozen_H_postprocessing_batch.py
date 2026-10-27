# 功能概述：已审H父诊断/聚合或Stage A科学入口的公开迁移副本，非历史actual-run字节。
# 接口：显式runtime授权及独立冻结plan/source/review/release；路径/身份/SHA从external bindings取得。
# 关系：直接依赖同publictree或现有nmr_assignment；保留原数值算法、完整分母、预算及失败协议。
from portable_runtime import binding, workspace, artifact_path, repository, _config
"""功能概述：连接冻结 H 输入表与已审纯单记录后处理，保存固定队列和描述汇总。
按原 1408 身份顺序核对已审文件、五字段 policy、原匿名 bytes、source/cache 独审和
代码 SHA；EvidenceAnchor 只表示文件行完整性，不把哈希当作化学证明。joint_family
缺失时传 None，不枚举新状态。逐记录在全部读取、解码后、anchor 建立前创建一个
.25 秒/50000 checks budget，覆盖 anchor 建立及整个 helper；超限不重试，固定分母仍保留。
本层只汇总 helper 已返回的标量、混合误差和共同状态区间，按原角色分表；不运行
模型、映射、候选生成、求解、阈值拟合或测试。配对结果来自已审只读汇总的原字节。
关系：supervise_frozen_postprocessing 负责进程树资源和唯一启动；复杂科学规则归属
frozen_reference_postprocessor；原 H/C 评分与正式系统不变。check-only 不调用 helper。
"""
import argparse
from collections import Counter, defaultdict
import datetime
import hashlib
import importlib
import json
from math import ceil, fsum, isfinite
from pathlib import Path
import sys
import time
from supervise_frozen_postprocessing import EXPECTED_BUDGET, bound, need, read_bound, sha
POLICY_KEYS = ('source', 'nucleus', 'record_id', 'structure_id', 'row_sha256')
TABLES = ('public', 'gold', 'ledger', 'admissions', 'lineages', 'predictions', 'cache_input_ledger')

def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')

def emit(stream, value):
    stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
    stream.flush()

def indexed_rows(path, keys):
    result = {}
    with Path(path).open() as stream:
        for number, line in enumerate(stream, 1):
            need(line.strip(), 'blank_input_row')
            row = json.loads(line)
            key = tuple((row[k] for k in keys))
            need(key not in result, 'duplicate_input_key:' + str(path))
            result[key] = (row, number)
    return result

def quantiles(values):
    values = sorted(values)
    need(all((type(v) in (int, float) and isfinite(v) for v in values)), 'finite_summary_values')
    return dict(N=len(values), mean=fsum(values) / len(values) if values else None, p50=values[ceil(0.5 * len(values)) - 1] if values else None, p90=values[ceil(0.9 * len(values)) - 1] if values else None, p95=values[ceil(0.95 * len(values)) - 1] if values else None, maximum=max(values) if values else None)

class SavedForwardSummary:
    """Only aggregate emitted fields; scalar, mixture and joint domains stay separate."""

    def __init__(self):
        self.groups = defaultdict(lambda: dict(records=0, statuses=Counter(), scalar=[], signed=[], scalar_record_means=[], mixture=[], bound_lower=[], bound_upper=[], subset_lower=[], subset_upper=[], widths=Counter(), target_statuses=Counter(), denominator_rows=[], fixed_denominators=[]))

    def add(self, record):
        forward = record.get('shared_forward') or {}
        rows = forward.get('rows', ())
        for role in record['roles']:
            group = self.groups[role]
            group['records'] += 1
            group['statuses'][record['status']] += 1
            group['denominator_rows'].append(record.get('reference_denominators'))
            group['fixed_denominators'].append(record['fixed_source_denominators'])
            scalar = [r for r in rows if r['status'] == 'scalar']
            mixture = [r for r in rows if r['status'] == 'mixture']
            group['target_statuses'].update((r['status'] for r in rows))
            group['scalar'].extend((r['absolute_error'] for r in scalar))
            group['signed'].extend((r['signed_error'] for r in scalar))
            if scalar:
                group['scalar_record_means'].append(fsum((r['absolute_error'] for r in scalar)) / len(scalar))
            group['mixture'].extend((r['mixture_expected_absolute_deviation'] for r in mixture))
            for row in scalar:
                if 'fixed_scale_3width_exceeded' in row:
                    need(type(row['fixed_scale_3width_exceeded']) is bool, 'exceedance_bool')
                    group['widths']['assessable'] += 1
                    group['widths']['exceeded'] += row['fixed_scale_3width_exceeded']
            bounds = forward.get('record_joint_bound')
            if bounds is not None:
                prefix = 'bound' if forward.get('domain_scope') == 'full_reference_targets' else 'subset'
                group[prefix + '_lower'].append(bounds['lower'])
                group[prefix + '_upper'].append(bounds['upper'])

    def result(self):
        output = {}
        for role, group in self.groups.items():
            environment_counts = [v.get('reference_environment_targets') if v is not None else None for v in group['denominator_rows']]
            need(all((v is None or (type(v) is int and v >= 0) for v in environment_counts)), 'source_environment_count_type')
            known_environment_counts = [v for v in environment_counts if v is not None]
            unknown_environment_records = sum((v is None for v in environment_counts))
            output[role] = dict(records=group['records'], statuses=dict(group['statuses']), scalar_absolute_error_ppm=quantiles(group['scalar']), scalar_signed_bias_ppm=fsum(group['signed']) / len(group['signed']) if group['signed'] else None, scalar_macro_mean_of_record_MAE_ppm=dict(N_records=len(group['scalar_record_means']), mean=fsum(group['scalar_record_means']) / len(group['scalar_record_means']) if group['scalar_record_means'] else None), mixture_expected_absolute_deviation_ppm=quantiles(group['mixture']), full_joint_record_mean_bound=dict(N=len(group['bound_lower']), lower=quantiles(group['bound_lower'])['mean'], upper=quantiles(group['bound_upper'])['mean']), invariant_subset_record_mean_bound=dict(N=len(group['subset_lower']), lower=quantiles(group['subset_lower'])['mean'], upper=quantiles(group['subset_upper'])['mean']), emitted_target_statuses=dict(group['target_statuses']), fixed_scale_3width_exceedance=dict(group['widths']), source_denominator_records_known=sum((v is not None for v in group['denominator_rows'])), source_denominator_records_unknown=sum((v is None for v in group['denominator_rows'])), source_denominator_record_count_basis='object_presence_only_environment_counts_separate', fixed_source_known_H_slots=sum((v['source_known_H_slots'] for v in group['fixed_denominators'])), fixed_serialized_observation_bins=sum((v['serialized_observation_bins'] for v in group['fixed_denominators'])), established_reference_environment_targets=sum(known_environment_counts), reference_environment_count_known_records=len(known_environment_counts), reference_environment_count_unknown_records=unknown_environment_records, unknown_reference_environment_target_count=None if unknown_environment_records else 0, fixed_source_known_H_slots_in_unknown_environment_records=sum((fixed['source_known_H_slots'] for count, fixed in zip(environment_counts, group['fixed_denominators']) if count is None)), established_environment_target_domain='records_with_nonnull_established_environment_counts_only')
        return output

class SavedMethodSummary:
    """Count only emitted nonexclusive diagnostics, with fixed unknown rows retained."""

    def __init__(self):
        self.groups = defaultdict(lambda: dict(records=0, eligible_known=0, eligible_denominator_unknown_records=0, membership_rows=0, status=Counter(), reasons=Counter(), witness=Counter(), objective=Counter(), cardinality_proof_rows=0, fields={key: Counter() for key in ('reference_candidate_present', 'pre_gate_representable', 'numerical_gate_excluded')}))

    def add(self, record):
        eligible = record.get('gold_eligible_observations')
        need(eligible is None or (type(eligible) is int and eligible >= 0), 'saved_eligible_count')
        for role in record['roles']:
            for method in ('B1', 'B2'):
                group = self.groups[role, method]
                obj = record.get('methods', {}).get(method, {})
                group['records'] += 1
                group['status'][obj.get('status', 'unknown')] += 1
                group['reasons'].update(obj.get('reason_codes', []))
                rows = obj.get('candidate_membership', [])
                need(len({v['observation_id'] for v in rows}) == len(rows), 'duplicate_membership_observation')
                if eligible is None:
                    group['eligible_denominator_unknown_records'] += 1
                    need(not rows, 'membership_without_known_eligible_domain')
                else:
                    need(len(rows) <= eligible, 'membership_exceeds_fixed_eligible_domain')
                    group['eligible_known'] += eligible
                    for counter in group['fields'].values():
                        counter['unknown'] += eligible - len(rows)
                group['membership_rows'] += len(rows)
                for row in rows:
                    need(row.get('gold_eligible') is True, 'saved_membership_eligibility')
                    for key, counter in group['fields'].items():
                        value = row.get(key, 'unknown')
                        need(type(value) is bool or value == 'unknown', 'saved_diagnostic_three_state')
                        counter['true' if value is True else 'false' if value is False else 'unknown'] += 1
                    group['cardinality_proof_rows'] += bool(row.get('method_cardinality_limit'))
                group['witness']['true' if obj.get('witness_found') is True else 'unknown'] += 1
                objective = obj.get('objective_diagnostic', {})
                value = objective.get('certified_incompatible_choice_with_reference_witness')
                label = 'true' if value is True else 'false' if value is False else 'unknown'
                group['objective'][label] += 1

    def result(self):
        return [dict(role=role, method=method, fixed_records=group['records'], known_eligible_observations=group['eligible_known'], eligible_semantics='source_reference_observation_admission_not_exact_uniqueness', eligible_denominator_unknown_records=group['eligible_denominator_unknown_records'], emitted_membership_rows=group['membership_rows'], observation_diagnostics={key: dict(value) for key, value in group['fields'].items()}, emitted_complete_cardinality_proof_rows=group['cardinality_proof_rows'], witness_found=dict(group['witness']), certified_incompatible_choice_with_reference_witness=dict(group['objective']), method_status=dict(group['status']), saved_reason_codes=dict(group['reasons']), interpretation='nonexclusive_saved_operational_flags_no_causal_partition') for (role, method), group in sorted(self.groups.items())]

def frozen_source_identities(plan):
    """Read the owner-reviewed source-only ledger from the SHA-bound plan."""
    ids = plan['input_ids']
    need(len(ids) == len(set(ids)) == binding('run_frozen_H_postprocessing_batch.identity_count.1'), 'fixed_identity_domain')
    rows = json.loads(json.dumps(plan['fixed_source_ledger']))
    need([r['input_id'] for r in rows] == ids, 'frozen_source_ledger_order')
    for row in rows:
        need(row['status'] == 'not_started', 'frozen_source_ledger_initial_status')
        roles = row['roles']
        need(roles and len(roles) == len(set(roles)) and (set(roles) <= {'fixed_train8192', 'tune', 'original_val'}), 'frozen_source_ledger_roles')
        fixed = row['fixed_source_denominators']
        need(all((type(fixed[k]) is int and fixed[k] >= 0 for k in ('source_known_H_slots', 'serialized_observation_bins'))), 'frozen_source_counts')
        need(type(fixed['source_reference_admitted']) is bool, 'frozen_source_admission_bool')
        need(all((row['source_binding'].get(k) for k in POLICY_KEYS)), 'frozen_source_binding')
    return rows

def prepare(plan_path, plan_sha, *, output_already_created=False):
    plan = read_bound(plan_path, plan_sha)
    need(plan['schema'] == 'frozen_H_postprocessing_batch_plan_v1' and plan['allow_test'] is False, 'plan_scope')
    need(plan['budget'] == EXPECTED_BUDGET, 'fixed_budget')
    need('paired_summary' in plan['inputs'], 'reviewed_paired_summary_required_before_execution')
    ids = plan['input_ids']
    need(len(ids) == len(set(ids)) == binding('run_frozen_H_postprocessing_batch.identity_count.2'), 'fixed_identity_domain')
    frozen_identities = frozen_source_identities(plan)
    checked = {}

    def record(item):
        path = bound(item)
        checked[str(path)] = item['sha256']
        return path
    implementations = {name: record(item) for name, item in plan['implementation'].items()}
    need(implementations['batch_driver'] == Path(__file__).resolve(), 'batch_driver_binding')
    for item in plan['required_implementations'].values():
        record(item)
    repo = Path(plan['repo']).resolve()
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(implementations['single_record_helper'].parent))
    helper = importlib.import_module('frozen_reference_postprocessor')
    need(Path(helper.__file__).resolve() == implementations['single_record_helper'], 'helper_import_path')
    need(set(helper.REQUIRED_IMPLEMENTATIONS) == set(plan['required_implementations']), 'required_implementation_domain')
    for key, digest in helper.REQUIRED_IMPLEMENTATIONS.items():
        need(plan['required_implementations'][key]['sha256'] == digest, 'helper_required_SHA:' + key)
    from nmr_assignment.execution import canonical_digest, numeric_config_from_frozen
    sources = {name: record(item) for name, item in plan['inputs'].items()}
    need(json.loads(sources['frozen_source_ledger'].read_text())['records'] == frozen_identities, 'frozen_source_ledger_file_binding')
    original_plan = json.loads(sources['scoring_plan'].read_text())
    need(original_plan['input_ids'] == ids and original_plan['allow_test'] is False, 'original_order_scope')
    completed = json.loads(sources['completed_manifest'].read_text())
    need(completed['status'] == 'FROZEN_ASSIGNMENT_EXECUTION_COMPLETED', 'completed_execution_required')
    need([v['input_id'] for v in completed['record_ledger']] == ids, 'completed_order_domain')
    handoff = json.loads(sources['report_handoff'].read_text())
    need(handoff['completed_manifest_sha256'] == plan['inputs']['completed_manifest']['sha256'], 'handoff_manifest')
    for name in ('source_application_review', 'cache_application_review', 'lineage_application_review'):
        review = json.loads(sources[name].read_text())
        need(str(review.get('decision', review.get('status', ''))).startswith('PASS'), 'existing_application_review:' + name)
    tables = {name: indexed_rows(sources[name], ('input_id',)) for name in TABLES}
    for name, table in tables.items():
        need(set(table) == {(iid,) for iid in ids}, 'table_identity_domain:' + name)
    policies = indexed_rows(sources['policy'], POLICY_KEYS)
    need(len(policies) == len(ids), 'policy_domain_count')
    numeric_config = numeric_config_from_frozen(json.loads(sources['numeric_config'].read_text()))
    root = sources['completed_manifest'].parent
    closure = handoff['observed_output_sha256']
    raw_paths = {}
    identity_ledger = []
    for iid in ids:
        ledger = tables['ledger'][iid,][0]
        gold = tables['gold'][iid,][0]
        key = tuple((gold['binding'][k] for k in POLICY_KEYS))
        need(key == tuple((ledger[k] for k in POLICY_KEYS)) and key in policies, 'five_field_policy_join')
        roles = ledger['roles']
        need(roles and len(set(roles)) == len(roles) and (set(roles) <= {'fixed_train8192', 'tune', 'original_val'}), 'role_scope')
        for suffix in ('.json', '.payload.json'):
            path = (root / 'raw' / (iid + suffix)).resolve()
            need(str(path) in closure, 'raw_closure_missing')
            record(dict(path=str(path), sha256=closure[str(path)]))
            raw_paths[iid, suffix] = path
        identity_ledger.append(dict(input_id=iid, roles=roles, connectivity_id=ledger['connectivity_sha256'], source_binding=gold['binding'], status='not_started', fixed_source_denominators=dict(source_known_H_slots=ledger['known_label_atoms'], serialized_observation_bins=ledger['bins'], source_reference_admitted=ledger['scoreable'])))
    need(identity_ledger == frozen_identities, 'source_only_ledger_actual_binding')
    if not output_already_created:
        need(not Path(plan['output_directory']).exists(), 'output_exists')
    return dict(plan=plan, helper=helper, tables=tables, policies=policies, checked=checked, numeric_config=numeric_config, raw_paths=raw_paths, identities=identity_ledger, canonical_digest=canonical_digest, sources=sources)

def preflight_failed(plan, output, plan_sha, identities, exc, started, utc):
    """No helper invocation; retain the already approved source ledger for every identity."""
    reason = 'preflight_integrity_error:' + type(exc).__name__ + ':' + str(exc)
    forward, methods = (SavedForwardSummary(), SavedMethodSummary())
    records = []
    names = ('reference_environment_denominators', 'shared_forward', 'candidate_membership', 'witness_objective')
    streams = {name: (output / (name + '.jsonl')).open('x') for name in names}
    try:
        for row in identities:
            record = dict(input_id=row['input_id'], roles=row['roles'], status='not_started_unknown', reason_codes=[reason], reference_denominators=None, fixed_source_denominators=row['fixed_source_denominators'], shared_forward={}, methods={})
            forward.add(record)
            methods.add(record)
            records.append(dict(input_id=row['input_id'], roles=row['roles'], status='not_started_unknown', reason_codes=[reason], budget_checks=0, elapsed_seconds_after_load=None))
            common = dict(input_id=row['input_id'], roles=row['roles'], status='not_started_unknown', reason_codes=[reason], plan_sha256=plan_sha)
            emit(streams['reference_environment_denominators'], dict(common, denominator=None, fixed_source_denominators=row['fixed_source_denominators'], source_binding=row['source_binding']))
            for name in names[1:]:
                emit(streams[name], dict(common, diagnostic='unknown'))
    finally:
        for stream in streams.values():
            stream.close()
    write_json(output / 'record_completion_ledger.json', records)
    write_json(output / 'input_sha256_manifest.json', dict(status='PREFLIGHT_FAILED_NOT_ALL_INPUTS_VERIFIED', declared_inputs=plan['inputs'], plan_sha256=plan_sha))
    write_json(output / 'summary.json', dict(schema='frozen_H_postprocessing_summary_v1', status='FAILED_PREFLIGHT_NO_HELPER_CALLS', fixed_identities=len(identities), per_role=forward.result(), per_role_method=methods.result(), source_denominator_origin='owner_reviewed_inline_source_ledger_not_new_environment_inference'))
    write_json(output / 'paired_outcomes.json', dict(status='not_started_unknown', reason_codes=[reason]))
    files = {path.name: sha(path) for path in output.iterdir() if path.is_file()}
    write_json(output / 'receipt.json', dict(schema='frozen_H_postprocessing_actual_v1', status='FAILED_OR_PARTIAL_NO_RETRY', started_utc=utc, finished_utc=stamp(), elapsed_seconds=time.monotonic() - started, plan_sha256=plan_sha, output_sha256=files, fixed_identities=len(identities), error=reason, actual_helper_calls=0, new_model_calls=0, new_solver_calls=0, new_mapping_search=0, new_threshold_selection=0, test_rows_read=0, retries=0))
    print(json.dumps(dict(status='FAILED_PREFLIGHT_NO_HELPER_CALLS', fixed_identities=len(identities), error=reason)))
    return 1

def execute(plan_path, plan_sha):
    started, utc = (time.monotonic(), stamp())
    plan = read_bound(plan_path, plan_sha)
    need(plan['schema'] == 'frozen_H_postprocessing_batch_plan_v1' and plan['allow_test'] is False, 'plan_scope')
    need(plan['budget'] == EXPECTED_BUDGET, 'fixed_budget')
    need(plan.get('execution_authorized') is True, 'plan_not_authorized')
    identities = frozen_source_identities(plan)
    output = Path(plan['output_directory'])
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'plan.json', plan)
    write_json(output / 'fixed_identity_ledger.json', identities)
    try:
        context = prepare(plan_path, plan_sha, output_already_created=True)
    except Exception as exc:
        return preflight_failed(plan, output, plan_sha, identities, exc, started, utc)
    helper = context['helper']
    write_json(output / 'input_sha256_manifest.json', context['checked'])
    summary, method_summary, statuses = (SavedForwardSummary(), SavedMethodSummary(), Counter())
    records, error = ([], None)
    names = ('reference_environment_denominators', 'shared_forward', 'candidate_membership', 'witness_objective')
    streams = {name: (output / (name + '.jsonl')).open('x') for name in names}
    try:
        for item in context['identities']:
            iid = item['input_id']
            record_started = None
            if time.monotonic() - started >= EXPECTED_BUDGET['total_wall_seconds']:
                error = 'batch_wall_limit'
            if error:
                result = dict(input_id=iid, roles=item['roles'], status='not_started_unknown', reason_codes=[error], reference_denominators=None, shared_forward={}, methods={})
            else:
                try:
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
                    result = helper.process_record(input_id=iid, raw_payload=raw_payload, evidence_anchor=anchor, joint_family=None, budget=budget, **args)
                except Exception as exc:
                    error = 'integrity_error:' + type(exc).__name__ + ':' + str(exc)
                    result = dict(input_id=iid, roles=item['roles'], status='integrity_error', reason_codes=[error], reference_denominators=None, shared_forward={}, methods={})
            item['status'] = result['status']
            result['fixed_source_denominators'] = item['fixed_source_denominators']
            statuses[result['status']] += 1
            summary.add(result)
            method_summary.add(result)
            records.append(dict(input_id=iid, roles=item['roles'], status=result['status'], budget_checks=result.get('budget_checks'), reason_codes=result.get('reason_codes', []), elapsed_seconds_after_load=time.monotonic() - record_started if record_started is not None else None))
            prediction = context['tables']['predictions'][iid,][0]
            common = dict(input_id=iid, roles=item['roles'], connectivity_id=item['connectivity_id'], truth_basis='source_relative_current_serialization', nucleus='1H', assignment_task_semantics='derived_serialized_value_bin', reference_sha256=result.get('reference_sha256'), prediction_artifact_sha256=prediction['prediction_artifact_sha256'], numeric_config_sha256=context['canonical_digest'](context['numeric_config']), raw_execution_file_sha256=context['checked'][str(context['raw_paths'][iid, '.json'])], anonymous_payload_file_sha256=context['checked'][str(context['raw_paths'][iid, '.payload.json'])], plan_sha256=plan_sha, status=result['status'])
            emit(streams['reference_environment_denominators'], dict(common, source_binding=item['source_binding'], denominator=result.get('reference_denominators'), fixed_source_denominators=item['fixed_source_denominators'], targets=result.get('reference_targets'), gold_eligible_observations=result.get('gold_eligible_observations')))
            emit(streams['shared_forward'], dict(common, diagnostic=result.get('shared_forward')))
            emit(streams['candidate_membership'], dict(common, methods=result.get('methods', {})))
            emit(streams['witness_objective'], dict(common, methods=result.get('methods', {})))
    finally:
        for stream in streams.values():
            stream.close()
    write_json(output / 'record_completion_ledger.json', records)
    write_json(output / 'summary.json', dict(schema='frozen_H_postprocessing_summary_v1', per_role=summary.result(), per_role_method=method_summary.result(), fixed_identities=len(context['identities']), statuses=dict(statuses), quantile_rule='nearest_rank_x_ceil_pN_minus_1', scalar_weight='one_source_environment', mixture_metric='sum_q_absolute_carrier_error', threshold_refit=False))
    paired = context['sources']['paired_summary']
    with (output / 'paired_outcomes.json').open('xb') as target:
        target.write(paired.read_bytes())
    changed = [path for path, digest in context['checked'].items() if sha(path) != digest]
    if changed:
        error = 'post_input_SHA_changed'
    files = {path.name: sha(path) for path in output.iterdir() if path.is_file()}
    receipt = dict(schema='frozen_H_postprocessing_actual_v1', status='COMPLETED_PENDING_INDEPENDENT_AUDIT' if error is None else 'FAILED_OR_PARTIAL_NO_RETRY', started_utc=utc, finished_utc=stamp(), elapsed_seconds=time.monotonic() - started, plan_sha256=plan_sha, output_sha256=files, fixed_identities=binding('run_frozen_H_postprocessing_batch.identity_count.3'), statuses=dict(statuses), input_hashes_unchanged=not changed, changed_input_paths=changed, error=error, new_model_calls=0, new_solver_calls=0, new_mapping_search=0, new_threshold_selection=0, test_rows_read=0, retries=0)
    write_json(output / 'receipt.json', receipt)
    print(json.dumps(dict(status=receipt['status'], records=len(records), error=error)))
    return 0 if error is None else 1

def main():
    _config()
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        return execute(args.plan, args.plan_sha256)
    context = prepare(args.plan, args.plan_sha256)
    print(json.dumps(dict(status='CHECK_ONLY_NO_POSTPROCESSING', identities=len(context['identities']))))
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
