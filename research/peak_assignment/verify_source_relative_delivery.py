# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：仅核验源相对交付，不替代原verify_assignment_complete强目标。\n职责：检查真实执行、固定test、统计/展示/出版/独审与完整SHA链，以及可信实验gold缺证声明。\n关系：原强谓词字节不改；此入口成功也强制overall_user_goal_fully_met=False。\n输入输出：只读本轮JSON与交付文件；缺件PENDING/EXIT2，证据不符失败，绝不生成科学结果。\n'
import hashlib
import json
from pathlib import Path
ROOT = workspace()
STATUS = 'SOURCE_RELATIVE_DELIVERY_COMPLETE_TRUSTED_GOLD_UNAVAILABLE'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    names = ['source_relative_completion.json', 'source_relative_benchmark_manifest.json', 'frozen_definition.json', 'baseline_comparison.json', 'confidence_calibration.json', 'test_evaluation.json', 'stratified_metrics.json', 'code_publication.json', 'source_relative_final_independent_review.json', 'report.md', 'demonstrations/index.html']
    missing = [name for name in names if not artifact_path(name).is_file()]
    if missing:
        print('PENDING_SOURCE_RELATIVE:' + ','.join(missing))
        return 2
    read = lambda name: json.loads(artifact_path(name).read_text())
    done = read('source_relative_completion.json')
    assert done['status'] == STATUS
    assert done['overall_user_goal_fully_met'] is False
    assert done['trusted_experimental_benchmark_complete'] is False
    assert done['missing_original_annotation_evidence']
    assert done['training_updates'] == done['external_LLM_API_calls'] == 0
    assert done['SpatialShift_weights_or_pseudolabels_used'] is False
    assert done['test_used_for_parameter_selection'] is False
    assert done['historical_test_blind_claim'] is False
    decision = read('SOURCE_RELATIVE_COMPLETION_SCOPE_DECISION.json')
    assert digest(Path(decision['original_strong_predicate']['path'])) == decision['original_strong_predicate']['sha256']
    bench = read('source_relative_benchmark_manifest.json')
    assert bench['truth_basis'] == 'source_relative_current_serialization'
    assert bench['reference_basis'] == 'source_asserted_encoded_graph'
    assert bench['trust_basis'] == 'internal_source_consistency'
    assert bench['trusted_experimental'] is False
    assert bench['source_relative_1H_records'] > 0
    assert bench['trusted_experimental_records'] == 0
    assert bench['original_labels_unchanged'] is True
    assert bench['13C_support_audited'] is True
    assert bench['unevaluable_identities_retained'] is True
    assert read('frozen_definition.json')['status'] == 'FROZEN_BY_ORIGINAL_SCIENTIFIC_OWNER'
    runs = read('baseline_comparison.json')['baseline_runs']
    assert len(runs) == 3 and {r['baseline'] for r in runs} == {'B0', 'B1', 'B2'}
    assert len({r['shared_prediction_manifest_sha256'] for r in runs}) == 1
    for run in runs:
        assert run['status'] == 'COMPLETE'
        assert run['inputs_unchanged'] is True and run['training_updates'] == 0
        assert run['actual_inner_exit'] == run['actual_external_exit'] == 0
        assert run['all_frozen_input_ids_accounted_for'] is True
    calibration = read('confidence_calibration.json')
    assert calibration['selection_split'] == 'validation'
    assert calibration['denominators_and_confidence_intervals_reported'] is True
    assert calibration['truth_bases_not_pooled'] is True
    test = read('test_evaluation.json')
    assert test['fixed_test_passes'] == 1
    assert test['historical_identity_counts'] == {'observed': 1000, 'frequency_crop': 200, 'peak_dropout': 171}
    assert test['unevaluable_retained_not_replaced'] is True
    assert test['freeze_before_evaluation_verified'] is True
    assert read('stratified_metrics.json')['required_metric_families_complete'] is True
    review = read('source_relative_final_independent_review.json')
    assert review['status'] == 'PASS_SOURCE_RELATIVE_DELIVERY' and review['independent'] is True
    assert review['trusted_experimental_benchmark_complete'] is False
    code = read('code_publication.json')
    assert code['repository'] == 'https://github.com/AndrewLuan/nmr-retrieval'
    assert code['head_sha'] == code['remote_main_sha'] == code['github_main_sha']
    assert code['tests_actual_exit'] == 0 and code['actual_execution_scripts_published'] is True
    for path, expected in done['evidence_sha256'].items():
        assert digest(Path(path)) == expected, path
    print('PASS_' + STATUS + ';overall_user_goal_fully_met=false')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
