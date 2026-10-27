# 功能概述：冻结H尾部续行的公开副本；原actual-run源码与公共源码SHA分开。
# 接口：显式runtime manifest授权及原plan/release/once门禁；身份、前缀、源证据绑定外置。
# 关系：复用六个纯控制原语；保留原budget/完整分母/未知与失败账本；无默认恢复授权。
from portable_runtime import binding, _config
"""功能概述：为H冻结后处理尾部续行提供独立once启动、资源监督和清理收据。
prepare只核精确plan/源码/父批元数据，默认不启动；execute要求新的独审PASS与owner
once release，不能复用父批LAUNCH。总计894秒包括本监督器元数据/hash、子进程及清理；
正常工作最多882秒，其余12秒留给只属于本次new-session的进程树清理和receipt。
cleanup_owned按本次PG及已记录PID出生时间杀进程，等待有界且不使用PIPE；
monitor用子进程wait事件，不固定sleep。真实内/外退出、原批加续批wall及未清理状态
均持久记录。最终查询已退出进程不构成错误，其余清理异常标unknown且仍写actual receipt。关系：只调用新resume driver；原supervisor/driver/helper与科学参数不改。
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import psutil
from postprocessing_control_primitives import need, sha, bound, read_bound, save_new, stamp
RUNTIME_ARGUMENTS = []
TOTAL = 894
RESERVE = 12

def cleanup_owned(child, owned, deadline):
    if child is None:
        return dict(cleanup_complete=True, cleanup_unknown=False, cleanup_errors=[], remaining_processes=[], group_kill_attempted=False)
    attempted = False
    errors = []

    def query_error(stage, exc):
        errors.append(stage + ':' + type(exc).__name__ + ':' + str(exc))
    try:
        os.killpg(child.pid, signal.SIGKILL)
        attempted = True
    except ProcessLookupError:
        pass
    except PermissionError as exc:
        attempted = True
        query_error('killpg', exc)
    for pid, born in owned.items():
        try:
            p = psutil.Process(pid)
            if p.create_time() == born:
                p.kill()
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
        except psutil.Error as exc:
            query_error('tracked_kill', exc)
    try:
        child.wait(timeout=max(0, min(4, deadline - time.monotonic())))
    except subprocess.TimeoutExpired:
        pass
    live = []
    for p in psutil.process_iter(['pid', 'create_time', 'status']):
        try:
            if p.info['status'] == psutil.STATUS_ZOMBIE:
                continue
            tracked = owned.get(p.pid) == p.info['create_time']
            samegroup = os.getpgid(p.pid) == child.pid and os.getsid(p.pid) == child.pid
            if tracked or samegroup:
                live.append(p)
        except (psutil.NoSuchProcess, psutil.ZombieProcess, ProcessLookupError):
            pass
        except (psutil.Error, PermissionError) as exc:
            query_error('group_liveness', exc)
    for p in live:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
        except psutil.Error as exc:
            query_error('group_kill', exc)
    _, alive = psutil.wait_procs(live, timeout=max(0, min(4, deadline - time.monotonic())))
    remaining = []
    for p in alive:
        try:
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                remaining.append(p.pid)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
        except Exception as exc:
            remaining.append(p.pid)
            query_error('final_liveness', exc)
    return dict(cleanup_complete=not errors and (not remaining) and (child.poll() is not None), cleanup_unknown=bool(errors), cleanup_errors=errors, remaining_processes=remaining, group_kill_attempted=attempted)

def prepare(path, digest):
    plan = read_bound(path, digest)
    need(plan['schema'] == 'frozen_H_postprocessing_tail_resume_v1' and plan['allow_test'] is False, 'resume_scope')
    need(plan['budget']['total_wall_seconds'] == TOTAL and plan['budget']['cleanup_and_receipt_reserve_seconds'] == RESERVE, 'tail_wall_cap')
    for item in plan['implementation'].values():
        bound(item)
    need(bound(plan['implementation']['supervisor']) == Path(__file__).resolve(), 'supervisor_binding')
    need(not Path(plan['output_directory']).exists(), 'fresh_tail_directory')
    need(Path(plan['supervisor_prefix']).name == 'H_frozen_postprocessing_resume', 'new_once_prefix')
    need(Path(plan['supervisor_prefix']).parent.is_dir(), 'supervisor_parent')
    return plan

def execute(path, digest, release_path, release_sha):
    started = time.monotonic()
    child = None
    owned = {}
    plan = None
    prefix = None
    receipt = dict(schema='frozen_H_postprocessing_tail_supervisor_actual_v1', started_utc=stamp(), plan_sha256=digest, release_sha256=release_sha, actual_inner_exit=None, new_outer_exit=1, peak_tree_RSS_bytes=0, termination_reason=None, new_model_calls=0, new_solver_calls=0, retries=0)

    def alarm(*_):
        raise TimeoutError('resume_total_work_deadline')
    previous = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, TOTAL - RESERVE)
    try:
        plan = prepare(path, digest)
        release = read_bound(release_path, release_sha)
        need(plan['execution_authorized'] is True, 'resume_not_authorized')
        need(release['decision'] == 'ALLOW_ONCE_FROZEN_H_POSTPROCESSING_TAIL_CONTINUATION', 'new_once_release')
        need(release['plan_sha256'] == digest and release['allow_test'] is False, 'release_binding')
        need(release['implementation_sha256'] == {k: v['sha256'] for k, v in plan['implementation'].items()}, 'release_sources')
        review = json.loads(bound(release['independent_implementation_review']).read_text())
        need(str(review.get('decision', review.get('status', ''))).startswith('PASS'), 'delta_review_PASS')
        actual = read_bound(plan['original_actual']['path'], plan['original_actual']['sha256'])
        need(actual['elapsed_seconds'] + TOTAL <= 900, 'combined_budget')
        prefix = Path(plan['supervisor_prefix'])
        save_new(str(prefix) + '_LAUNCH.json', receipt)
        argv = [sys.executable, '-B', str(bound(plan['implementation']['batch_driver'])), '--plan', str(Path(path).resolve()), '--plan-sha256', digest, '--execute']
        need(len(RUNTIME_ARGUMENTS) == 4, 'child explicit runtime binding required')
        argv += RUNTIME_ARGUMENTS
        receipt['argv'] = argv
        env = dict(os.environ, OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', CUDA_VISIBLE_DEVICES='')

        def affinity():
            if hasattr(os, 'sched_getaffinity'):
                os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
        with open(str(prefix) + '_stdout.log', 'x') as out, open(str(prefix) + '_stderr.log', 'x') as err, open(str(prefix) + '_resources.jsonl', 'x') as samples:
            child = subprocess.Popen(argv, cwd=plan['repo'], env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True, preexec_fn=affinity)
            root = psutil.Process(child.pid)
            receipt['child_pid'] = child.pid
            while True:
                try:
                    processes = [root] + root.children(recursive=True)
                except psutil.Error:
                    processes = []
                rss = 0
                for p in processes:
                    try:
                        owned[p.pid] = p.create_time()
                        rss += p.memory_info().rss
                    except psutil.Error:
                        pass
                elapsed = time.monotonic() - started
                receipt['peak_tree_RSS_bytes'] = max(rss, receipt['peak_tree_RSS_bytes'])
                samples.write(json.dumps(dict(elapsed_seconds=elapsed, tree_RSS_bytes=rss)) + '\n')
                samples.flush()
                if rss > 4294967296:
                    receipt['termination_reason'] = 'batch_RSS_limit'
                    break
                remaining = TOTAL - RESERVE - elapsed
                if remaining <= 0:
                    receipt['termination_reason'] = 'batch_work_wall_limit'
                    break
                try:
                    child.wait(timeout=min(1, remaining))
                    receipt['termination_reason'] = 'leader_exit'
                    break
                except subprocess.TimeoutExpired:
                    pass
    except BaseException as exc:
        receipt['error'] = type(exc).__name__ + ':' + str(exc)
        receipt['termination_reason'] = 'supervisor_exception'
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        cleanup_started = time.monotonic()
        try:
            receipt.update(cleanup_owned(child, owned, started + TOTAL - 2))
        except BaseException as exc:
            receipt.update(cleanup_complete=False, cleanup_unknown=True, cleanup_errors=['cleanup_exception:' + type(exc).__name__ + ':' + str(exc)], remaining_processes=None, group_kill_attempted=None)
        if child is not None:
            receipt['actual_inner_exit'] = child.returncode
        elapsed = time.monotonic() - started
        original_elapsed = None
        if plan:
            try:
                original_elapsed = read_bound(plan['original_actual']['path'], plan['original_actual']['sha256'])['elapsed_seconds']
            except Exception:
                pass
        ok = receipt['actual_inner_exit'] == 0 and receipt['termination_reason'] == 'leader_exit' and receipt['cleanup_complete'] and (elapsed < TOTAL) and (original_elapsed is not None) and (original_elapsed + elapsed <= 900)
        receipt.update(status='COMPLETED_PENDING_ARTIFACT_AUDIT' if ok else 'FAILED_OR_PARTIAL_NO_RETRY', new_outer_exit=0 if ok else 1, finished_utc=stamp(), elapsed_seconds=elapsed, cleanup_seconds=time.monotonic() - cleanup_started, original_plus_tail_wall_seconds=original_elapsed + elapsed if original_elapsed is not None else None)
        if prefix is not None:
            save_new(str(prefix) + '_actual_execution.json', receipt)
    print(json.dumps(receipt))
    return receipt['new_outer_exit']

def main():
    global RUNTIME_ARGUMENTS
    RUNTIME_ARGUMENTS = []
    for flag in ('--runtime-manifest','--runtime-manifest-sha256'):
        need(flag in sys.argv and sys.argv.index(flag)+1 < len(sys.argv), 'explicit runtime arguments required')
        RUNTIME_ARGUMENTS += [flag,sys.argv[sys.argv.index(flag)+1]]
    _config()
    p = argparse.ArgumentParser()
    p.add_argument('--plan', required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--release')
    p.add_argument('--release-sha256')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not a.execute:
        prepare(a.plan, a.plan_sha256)
        print(json.dumps(dict(status='CHECK_ONLY_NO_CHILD_STARTED')))
        return 0
    need(a.release and a.release_sha256, 'new_release_required')
    return execute(a.plan, a.plan_sha256, a.release, a.release_sha256)
if __name__ == '__main__':
    raise SystemExit(main())
