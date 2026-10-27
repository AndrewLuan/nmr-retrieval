# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：固定验证峰归属交付的真实完成条件，不运行模型或读取谱值。\n\nmain检查基准、三条基线、验证校准、一次固定测试、分层指标、展示、独审和\nGitHub主线证据。缺文件返回PENDING/EXIT2；已有文件不满足合同则拒绝完成。\n本文件不生成结果、不授予训练/前向权限，不以脚手架或声明代替真实结果。\n证据路径只接受可读取本地文件，全部hash必须一致；后续定义改变需原会话审阅。\n'
import hashlib
import json
from pathlib import Path
ROOT = workspace()

def main():
    required = ['completion.json', 'benchmark_manifest.json', 'frozen_definition.json', 'baseline_comparison.json', 'confidence_calibration.json', 'test_evaluation.json', 'stratified_metrics.json', 'code_publication.json', 'final_independent_review.json', 'report.md', 'demonstrations/index.html']
    missing = [name for name in required if not artifact_path(name).is_file()]
    if missing:
        print('PENDING:' + ','.join(missing))
        return 2
    read = lambda name: json.loads(artifact_path(name).read_text())
    done = read('completion.json')
    assert done['status'] == 'COMPLETE_VERIFIED_PEAK_ASSIGNMENT'
    assert done['training_updates'] == 0
    assert done['external_LLM_API_calls'] == 0
    assert done['SpatialShift_weights_or_pseudolabels_used'] is False
    assert done['test_used_for_parameter_selection'] is False
    assert done['historical_test_blind_claim'] is False
    bench = read('benchmark_manifest.json')
    assert bench['trusted_1H_reference_records'] > 0
    assert bench['original_labels_unchanged'] is True
    assert bench['ambiguous_atom_maps_excluded_from_unique_atom_accuracy'] is True
    assert bench['13C_support_audited'] is True
    freeze = read('frozen_definition.json')
    assert freeze['status'] == 'FROZEN_BY_ORIGINAL_SCIENTIFIC_OWNER'
    runs = read('baseline_comparison.json')['baseline_runs']
    assert {r['baseline'] for r in runs} == {'B0', 'B1', 'B2'} and len(runs) == 3
    assert len({r['shared_prediction_manifest_sha256'] for r in runs}) == 1
    for r in runs:
        assert r['status'] == 'COMPLETE' and r['inputs_unchanged'] is True
        assert r['training_updates'] == 0
        for key in ['actual_inner_exit', 'actual_external_exit']:
            assert type(r[key]) is int and r[key] == 0
    cal = read('confidence_calibration.json')
    assert cal['selection_split'] == 'validation'
    assert cal['denominators_and_confidence_intervals_reported'] is True
    if cal['high_confidence_enabled']:
        assert cal['high_confidence_precision'] >= 0.9
    test = read('test_evaluation.json')
    assert test['fixed_test_passes'] == 1
    assert test['historical_identity_counts'] == {'observed': 1000, 'frequency_crop': 200, 'peak_dropout': 171}
    assert test['unevaluable_retained_not_replaced'] is True
    assert test['freeze_before_evaluation_verified'] is True
    assert read('stratified_metrics.json')['required_metric_families_complete'] is True
    review = read('final_independent_review.json')
    assert review['status'] == 'PASS' and review['independent'] is True
    code = read('code_publication.json')
    assert code['repository'] == 'https://github.com/AndrewLuan/nmr-retrieval'
    assert code['head_sha'] == code['remote_main_sha'] == code['github_main_sha']
    assert code['tests_actual_exit'] == 0
    for path, expected in done['evidence_sha256'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, path
    print('PASS')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
