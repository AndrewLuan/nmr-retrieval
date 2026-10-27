# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
from collections import defaultdict
from dataclasses import replace
import hashlib
import json
from math import floor, ceil
from pathlib import Path
from random import Random
import sys
D = Path(__file__).resolve().parent
REPO = repository()
sys.path.insert(0, str(REPO))
from nmr_assignment.metrics import EvaluationRow, GROUP_FIELDS, summarize, paired_gain
CONTRACT_SHA256 = '9ed79581a211c2d5ed9f90a1472ca7135f5c04b5f7deb2f419f8ab554a0e7c27'
REPLICATES = 2000
SEED = 173
CONFIDENCE = 0.95
COMPARISONS = (('B1', 'B0'), ('B2', 'B0'), ('B2', 'B1'))

def _quantile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    lo, hi = (floor(position), ceil(position))
    return values[lo] + (values[hi] - values[lo]) * (position - lo)

def _group(row):
    c = dict(row.context)
    return tuple(((k, c[k]) for k in GROUP_FIELDS)) + (('metric', row.metric),)

def connectivity_estimates(rows):
    """Fixed eligible units, record rates, then equal record means per connectivity."""
    rows = tuple(rows)
    records = defaultdict(list)
    seen = set()
    for row in rows:
        if type(row) is not EvaluationRow:
            raise ValueError('typed EvaluationRow required')
        c = dict(row.context)
        key = (c['record_id'], row.observation_id)
        if key in seen:
            raise ValueError('duplicate estimation unit')
        seen.add(key)
        records[c['record_id']].append(row)
    clusters = defaultdict(list)
    no_eligible = 0
    for rid in sorted(records):
        rr = records[rid]
        connectivities = {dict(r.context)['connectivity_id'] for r in rr}
        if len(connectivities) != 1:
            raise ValueError('one record must bind one connectivity')
        eligible = tuple((r for r in rr if r.eligible))
        if not eligible:
            no_eligible += 1
            continue
        n, success = (len(eligible), sum((r.success for r in eligible)))
        supported = tuple((r for r in eligible if r.prediction_supported))
        clusters[next(iter(connectivities))].append(dict(record_id=rid, eligible=n, success=success, rate=success / n, supported=len(supported), supported_success=sum((r.success for r in supported))))
    stats = []
    for gid in sorted(clusters):
        rr = clusters[gid]
        stats.append(dict(connectivity_id=gid, records=rr, eligible=sum((r['eligible'] for r in rr)), success=sum((r['success'] for r in rr)), supported=sum((r['supported'] for r in rr)), supported_success=sum((r['supported_success'] for r in rr)), macro=sum((r['rate'] for r in rr)) / len(rr)))
    eligible_n = sum((s['eligible'] for s in stats))
    success_n = sum((s['success'] for s in stats))
    supported_n = sum((s['supported'] for s in stats))
    supported_connectivities = sum((s['supported'] > 0 for s in stats))
    conditional_success_n = sum((s['supported_success'] for s in stats))
    micro = success_n / eligible_n if eligible_n else None
    macro = sum((s['macro'] for s in stats)) / len(stats) if stats else None
    conditional = conditional_success_n / supported_n if supported_n else None
    micro_ci = macro_ci = conditional_ci = None
    conditional_defined = 0
    if len(stats) >= 2:
        rng = Random(SEED)
        micro_draws, macro_draws, conditional_draws = ([], [], [])
        for _ in range(REPLICATES):
            sample = [stats[rng.randrange(len(stats))] for _ in stats]
            n = sum((s['eligible'] for s in sample))
            micro_draws.append(sum((s['success'] for s in sample)) / n)
            macro_draws.append(sum((s['macro'] for s in sample)) / len(sample))
            n_supported = sum((s['supported'] for s in sample))
            if n_supported:
                conditional_draws.append(sum((s['supported_success'] for s in sample)) / n_supported)
        tail = (1 - CONFIDENCE) / 2
        micro_ci = (_quantile(micro_draws, tail), _quantile(micro_draws, 1 - tail))
        macro_ci = (_quantile(macro_draws, tail), _quantile(macro_draws, 1 - tail))
        conditional_defined = len(conditional_draws)
        if supported_connectivities >= 2 and conditional_defined == REPLICATES:
            conditional_ci = (_quantile(conditional_draws, tail), _quantile(conditional_draws, 1 - tail))
    conditional_reason = 'fewer_than_two_supported_connectivities' if supported_connectivities < 2 else 'bootstrap_zero_supported_denominator' if conditional_defined != REPLICATES else None
    return dict(determinate_assignment_success_rate=micro, determinate_assignment_success_rate_CI95=micro_ci, connectivity_equal_weight_macro_success_rate=macro, connectivity_equal_weight_macro_success_rate_CI95=macro_ci, conditional_accuracy_among_supported_outputs=conditional, conditional_accuracy_among_supported_outputs_CI95=conditional_ci, conditional_CI_support_status='on' if conditional_ci is not None else 'off', conditional_CI_reason=conditional_reason, supported_connectivities=supported_connectivities, eligible_units=eligible_n, successes=success_n, eligible_records=sum((len(s['records']) for s in stats)), eligible_connectivities=len(stats), total_records=len(records), zero_eligible_records=no_eligible, supported_eligible_units=supported_n, supported_successes=conditional_success_n, eligible_peaks=sum((r.eligible and r.observation_id is not None for r in rows)), bootstrap_replicates=REPLICATES, bootstrap_seed=SEED, confidence=CONFIDENCE, bootstrap_unit='connectivity', CI_support_status='on' if micro_ci is not None else 'off', conditional_defined_bootstrap_replicates=conditional_defined, macro_formula='mean_connectivity(mean_record(mean_eligible_unit(success)))')

def estimate_report(rows, *, role):
    """One pre-frozen role at a time; baseline/metric/track/nucleus never pool."""
    if role not in ('fixed_train8192', 'original_val', 'tune', 'validation'):
        raise ValueError('explicit existing train/validation role required; test forbidden')
    rows = tuple(sorted(rows, key=lambda r: (_group(r), dict(r.context)['record_id'], '' if r.observation_id is None else r.observation_id)))
    grouped = defaultdict(list)
    for row in rows:
        grouped[_group(row)].append(row)
    summary = []
    for legacy in summarize(rows):
        stratum = legacy['stratum']
        key = tuple(((k, stratum[k]) for k in GROUP_FIELDS)) + (('metric', stratum['metric']),)
        estimates = connectivity_estimates(grouped[key])
        if estimates['determinate_assignment_success_rate'] != legacy['precision']:
            raise ValueError('core fixed denominator disagrees')
        clean = {k: v for k, v in legacy.items() if k != 'precision'}
        clean['stratum'] = dict(stratum, role=role)
        clean.update(estimates)
        clean['chemical_quotient_top3'] = None
        clean['chemical_quotient_top3_status'] = 'unsupported'
        clean['truth_scope'] = 'source assertion consistency, not trusted experimental accuracy' if stratum['truth_basis'] == 'source_relative_current_serialization' else stratum['truth_basis']
        summary.append(clean)
    gains = []
    for higher, lower in COMPARISONS:
        for item in paired_gain(rows, lower, higher, replicates=REPLICATES, seed=SEED, confidence=CONFIDENCE):
            gains.append(dict(item, comparison=higher + '-' + lower, stratum=dict(item['stratum'], role=role)))
    return dict(schema='frozen_assignment_report_estimators_v1', role=role, contract_sha256=CONTRACT_SHA256, summaries=summary, paired_gains=gains, comparison_estimand='paired fixed-eligible micro gain; connectivity cluster bootstrap', whole_input_and_strict_full_separate=True, chemical_quotient_top3=None, real_experiment_truth_promoted=False)

def synthetic_checks():

    def row(method, record, group, observation, eligible, supported, success, metric='exact_observation'):
        context = dict(truth_basis='source_relative_current_serialization', nucleus='1H', task_semantics='derived_serialized_value_bin', target_level='parent', target_semantics='set', baseline=method, record_id=record, connectivity_id=group)
        return EvaluationRow(tuple(context.items()), metric, observation, eligible, supported, success, (), (), (), ())
    rows = []
    for method in ('B0', 'B1', 'B2'):
        rows.append(row(method, 'r1', 'A', 'p0', True, True, True))
        for i in range(3):
            success = method == 'B2' or (method == 'B1' and i == 0)
            supported = success or i == 0
            rows.append(row(method, 'r2', 'A', 'p' + str(i), True, supported, success))
        for i in range(2):
            rows.append(row(method, 'r3', 'B', 'p' + str(i), True, True, True))
        rows.append(row(method, 'empty', 'C', 'p0', False, False, False))
    report = estimate_report(rows, role='original_val')
    summaries = {x['stratum']['baseline']: x for x in report['summaries']}
    b0 = summaries['B0']
    assert b0['determinate_assignment_success_rate'] == 0.5
    assert b0['connectivity_equal_weight_macro_success_rate'] == 0.75
    assert b0['connectivity_equal_weight_macro_success_rate'] != 0.625
    assert b0['conditional_accuracy_among_supported_outputs'] == 0.75
    assert (b0['eligible_units'], b0['eligible_records'], b0['eligible_connectivities'], b0['supported_eligible_units'], b0['zero_eligible_records']) == (6, 3, 2, 4, 1)
    assert 'precision' not in b0 and b0['CI_support_status'] == 'on'
    gains = {x['comparison']: x['gain'] for x in report['paired_gains']}
    assert abs(gains['B1-B0'] - 1 / 6) < 1e-12
    assert gains['B2-B0'] == 0.5 and abs(gains['B2-B1'] - 1 / 3) < 1e-12
    empty = [row(m, 'e', 'E', 'p0', False, False, False) for m in ('B0', 'B1', 'B2')]
    no = estimate_report(empty, role='tune')
    assert all((x['determinate_assignment_success_rate'] is None and x['connectivity_equal_weight_macro_success_rate'] is None and (x['conditional_accuracy_among_supported_outputs'] is None) for x in no['summaries']))
    assert all((x['gain'] is None and x['CI'] is None for x in no['paired_gains']))
    mismatch = list(rows)
    mismatch[7] = replace(mismatch[7], eligible=False, prediction_supported=False, success=False)
    try:
        estimate_report(mismatch, role='original_val')
    except ValueError:
        pass
    else:
        raise AssertionError('paired denominator mismatch must fail closed')
    omitted = [r for r in rows if not (dict(r.context)['baseline'] == 'B2' and dict(r.context)['record_id'] == 'r1')]
    try:
        estimate_report(omitted, role='original_val')
    except ValueError:
        pass
    else:
        raise AssertionError('paired cohort mismatch must fail closed')
    whole = []
    for method in ('B0', 'B1', 'B2'):
        whole.append(row(method, 'r1', 'A', None, True, True, True, 'all_input_reported_peaks_exact'))
        whole.append(row(method, 'r1', 'A', None, False, False, False, 'strict_full_spectrum'))
    wh = estimate_report(whole, role='original_val')
    assert {x['stratum']['metric'] for x in wh['summaries']} == {'all_input_reported_peaks_exact', 'strict_full_spectrum'}
    assert all((x['determinate_assignment_success_rate'] is None for x in wh['summaries'] if x['stratum']['metric'] == 'strict_full_spectrum'))
    assert estimate_report(tuple(reversed(rows)), role='original_val') == report
    return ['unequal_record_and_connectivity_macro_hierarchy', 'fixed_micro_not_supported_conditional', 'real_N_and_zero_eligible_counts', 'paired_gain_sign_and_2000_seed173_CI', 'paired_eligibility_mismatch_rejected', 'paired_cohort_mismatch_rejected', 'no_eligible_NA', 'whole_input_strict_full_separate', 'unsupported_chemical_top3_NA', 'deterministic_input_order_invariance']

def main():
    import argparse
    import time
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--receipt')
    args = parser.parse_args()
    if not args.self_test:
        raise SystemExit('Pure helper only; --self-test does not read real results.')
    start = time.monotonic()
    checks = synthetic_checks()
    result = dict(schema='frozen_report_estimators_synthetic_receipt_v1', status='SYNTHETIC_CHECKS_PASS', checks=checks, exit=0, elapsed_seconds=time.monotonic() - start, implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), contract_sha256=CONTRACT_SHA256, replicates=REPLICATES, seed=SEED, confidence=CONFIDENCE, real_gold_rows_read=0, real_result_rows_read=0, test_rows_read=0, model_loads=0)
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result))
if __name__ == '__main__':
    main()
