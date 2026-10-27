# 功能概述：已审H父诊断/聚合或Stage A科学入口的公开迁移副本，非历史actual-run字节。
# 接口：显式runtime授权及独立冻结plan/source/review/release；路径/身份/SHA从external bindings取得。
# 关系：直接依赖同publictree或现有nmr_assignment；保留原数值算法、完整分母、预算及失败协议。
from portable_runtime import binding, workspace, artifact_path, repository, _config
from postprocessing_control_primitives import need, sha, bound, read_bound, save_new, stamp
'功能概述：监督一次冻结 H 制品后处理，记录进程树资源、真实退出及清理。\n本文件只负责批次运行，不建立参考、不解释分数、不调用模型或求解器。批次计划和\n独立审核后的 release 必须分别绑定精确 SHA；默认 check-only 不启动子进程。\n运行层限制固定为一个 worker、两个线程、GPU 0、4 GiB 和 900 秒。唯一 launch\n文件采用排他创建，任何失败都不自动重试。文件读取和逐记录 .25 秒/50000 checks\n由已审批次入口和纯单记录 helper 执行；这里不扩大或重置其预算。\n关系：由 root 批次编排调用；不修改原 H/C 评分、校准、测试或正式检索系统。\n'
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import psutil
RUNTIME_ARGUMENTS = []
EXPECTED_BUDGET = dict(CPU_threads=2, GPU=0, RSS_bytes=4294967296, total_wall_seconds=900, per_record_checks=50000, per_record_seconds_after_load=0.25, record_workers=1)

def cleanup_owned(child, owned):
    """The new session also owns descendants born between RSS samples."""
    if child is None:
        return dict(cleanup_complete=True, remaining_processes=[], group_kill_attempted=False)
    group_kill_attempted = False
    try:
        os.killpg(child.pid, signal.SIGKILL)
        group_kill_attempted = True
    except ProcessLookupError:
        pass
    except PermissionError:
        group_kill_attempted = True
    for pid, born in reversed(tuple(owned.items())):
        try:
            process = psutil.Process(pid)
            if process.create_time() == born and process.status() != psutil.STATUS_ZOMBIE:
                process.kill()
        except psutil.Error:
            pass
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    deadline = time.monotonic() + 5
    remaining = []
    while True:
        remaining = []
        for process in psutil.process_iter(['pid', 'create_time', 'status']):
            try:
                if process.info['status'] == psutil.STATUS_ZOMBIE:
                    continue
                tracked = process.pid in owned and owned[process.pid] == process.info['create_time']
                in_group = os.getpgid(process.pid) == child.pid and os.getsid(process.pid) == child.pid
                if tracked or in_group:
                    remaining.append(process.pid)
            except (psutil.Error, ProcessLookupError, PermissionError):
                pass
        if not remaining or time.monotonic() >= deadline:
            break
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    return dict(cleanup_complete=not remaining, remaining_processes=remaining, group_kill_attempted=group_kill_attempted)

def prepare(plan_path, plan_sha):
    plan = read_bound(plan_path, plan_sha)
    need(plan['schema'] == 'frozen_H_postprocessing_batch_plan_v1', 'plan_schema')
    need(plan['allow_test'] is False, 'test_forbidden')
    need(plan['budget'] == EXPECTED_BUDGET, 'fixed_budget_required')
    need(len(plan['input_ids']) == binding('supervise_frozen_postprocessing.identity_count.1') and len(set(plan['input_ids'])) == binding('supervise_frozen_postprocessing.identity_count.2'), 'fixed_1408_identity_domain')
    for item in plan['implementation'].values():
        bound(item)
    need(bound(plan['implementation']['supervisor']) == Path(__file__).resolve(), 'supervisor_binding')
    driver = bound(plan['implementation']['batch_driver'])
    directory = Path(plan['supervisor_artifacts']).resolve()
    need(directory.is_dir(), 'existing_supervisor_parent_required')
    output = Path(plan['output_directory']).resolve()
    need(not output.exists(), 'output_must_not_exist')
    argv = [sys.executable, '-B', str(driver), '--plan', str(Path(plan_path).resolve()), '--plan-sha256', plan_sha, '--execute']
    need(len(RUNTIME_ARGUMENTS) == 4, 'child explicit runtime binding required')
    argv += RUNTIME_ARGUMENTS
    return (plan, directory, argv)

def execute(plan_path, plan_sha, release_path, release_sha):
    plan, directory, argv = prepare(plan_path, plan_sha)
    release = read_bound(release_path, release_sha)
    need(plan.get('execution_authorized') is True, 'plan_not_authorized')
    need(release.get('decision') == 'ALLOW_ONCE_FROZEN_H_POSTPROCESSING', 'explicit_once_release_required')
    need(release.get('plan_sha256') == plan_sha and release.get('allow_test') is False, 'release_plan_or_scope_binding')
    review = json.loads(bound(release['independent_implementation_review']).read_text())
    need(str(review.get('decision', review.get('status', ''))).startswith('PASS'), 'independent_implementation_review_required')
    need(release.get('implementation_sha256') == {key: value['sha256'] for key, value in plan['implementation'].items()}, 'release_implementation_binding')
    prefix = directory / 'H_frozen_postprocessing'
    started = time.monotonic()
    receipt = dict(schema='frozen_H_postprocessing_supervisor_actual_v1', started_utc=stamp(), argv=argv, plan_sha256=plan_sha, release_sha256=release_sha, budget=EXPECTED_BUDGET, actual_inner_exit=None, peak_tree_RSS_bytes=0, new_model_calls=0, new_solver_calls=0, new_mapping_search=0, test_rows_read=0, retries=0, termination_reason=None)
    save_new(str(prefix) + '_LAUNCH.json', receipt)
    child = None
    owned = {}
    environment = dict(os.environ, OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2', CUDA_VISIBLE_DEVICES='')
    try:
        with open(str(prefix) + '_stdout.log', 'x') as out, open(str(prefix) + '_stderr.log', 'x') as err, open(str(prefix) + '_resources.jsonl', 'x') as samples:
            child = subprocess.Popen(argv, cwd=plan['repo'], env=environment, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            root = psutil.Process(child.pid)
            receipt['child_pid'] = child.pid
            while True:
                try:
                    processes = [root] + root.children(recursive=True)
                except psutil.NoSuchProcess:
                    processes = []
                rss = 0
                for process in processes:
                    try:
                        owned[process.pid] = process.create_time()
                        rss += process.memory_info().rss
                    except psutil.Error:
                        pass
                elapsed = time.monotonic() - started
                receipt['peak_tree_RSS_bytes'] = max(receipt['peak_tree_RSS_bytes'], rss)
                samples.write(json.dumps(dict(elapsed_seconds=elapsed, tree_RSS_bytes=rss, processes=len(processes))) + '\n')
                samples.flush()
                if rss > EXPECTED_BUDGET['RSS_bytes']:
                    receipt['termination_reason'] = 'batch_RSS_limit'
                    break
                if elapsed >= EXPECTED_BUDGET['total_wall_seconds']:
                    receipt['termination_reason'] = 'batch_wall_limit'
                    break
                try:
                    child.wait(timeout=min(1.0, EXPECTED_BUDGET['total_wall_seconds'] - elapsed))
                    receipt['termination_reason'] = 'leader_exit'
                    break
                except subprocess.TimeoutExpired:
                    pass
    except BaseException as exc:
        receipt['termination_reason'] = 'supervisor_exception'
        receipt['error'] = type(exc).__name__ + ':' + str(exc)
    finally:
        cleanup = time.monotonic()
        receipt.update(cleanup_owned(child, owned))
        if child is not None:
            if child.poll() is None:
                receipt['leader_not_reaped'] = True
            receipt['actual_inner_exit'] = child.returncode
        receipt.update(finished_utc=stamp(), elapsed_seconds=time.monotonic() - started, cleanup_seconds=time.monotonic() - cleanup)
        receipt['status'] = 'COMPLETED_PENDING_ARTIFACT_AUDIT' if receipt['actual_inner_exit'] == 0 and receipt['termination_reason'] == 'leader_exit' and receipt['cleanup_complete'] else 'FAILED_OR_PARTIAL_NO_RETRY'
        save_new(str(prefix) + '_actual_execution.json', receipt)
    print(json.dumps(receipt))
    return 0 if receipt['status'] == 'COMPLETED_PENDING_ARTIFACT_AUDIT' else 1

def main():
    global RUNTIME_ARGUMENTS
    RUNTIME_ARGUMENTS = []
    for flag in ('--runtime-manifest','--runtime-manifest-sha256'):
        need(flag in sys.argv and sys.argv.index(flag)+1 < len(sys.argv), 'explicit runtime arguments required')
        RUNTIME_ARGUMENTS += [flag,sys.argv[sys.argv.index(flag)+1]]
    _config()
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--release')
    parser.add_argument('--release-sha256')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        prepare(args.plan, args.plan_sha256)
        print(json.dumps(dict(status='CHECK_ONLY_NO_CHILD_STARTED', execution_authorized=False)))
        return 0
    need(args.release and args.release_sha256, 'release_path_and_SHA_required')
    return execute(args.plan, args.plan_sha256, args.release, args.release_sha256)
if __name__ == '__main__':
    raise SystemExit(main())
