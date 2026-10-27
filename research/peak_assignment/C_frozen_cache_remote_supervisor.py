# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：监督已由 root 许可的 C3740 冻结预测 cache；本脚本不作科学准入决定。\nstdin 接 deployment 或 {remote,files,execute_argv,resources}。从读取请求前开始总 10800s，\n包含全部预/后文件 SHA。逐部署文件校验后只启动一次子进程；SUPERVISOR_STARTED.json\n排他创建并 fsync，持久化 supervisor PID/UTC，child PID/PGID 独立事件也 durable。\n子进程 stdout/stderr 写新文件而不 PIPE，独占 new session PG；Linux affinity 最多2 CPU，\nGPU 不可见。wait(timeout) 事件同步期间采样 /proc 的组内 PID RSS/HWM，超 RSS/wall 即终止。\nfinally 始终只清理本次自建 PG（即使 leader 已退出），wait 有界 60s，禁止重试与扩预算。\n完整实际 receipt 保存 leader exit、终止原因、wall/cleanup/RSS、前后 SHA 和 partial cache\n已记录 valid/failed/not-started/unaccounted，不因失败丢记录，不假称 partial 为科学验证完成。\nload300s/forward9000s 由已冻结 builder 执行；supervisor 仅核对该预算未被改写。\n--self-test 只运行标准库合成监控/进程，不导入模型或读真实数据。常规入口仅 JSON 摘要 stdout。\n'
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
WALL = 10800
RSS = 8589934592
CLEANUP = 60

def utc():
    return datetime.now(timezone.utc).isoformat()

def require(value, message):
    if not value:
        raise ValueError(message)

def check_time(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError('total_wall_10800_including_metadata_hashes')

def sha(path, deadline):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while True:
            check_time(deadline)
            block = stream.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()

def exclusive(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())

def atomic(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    exclusive(temporary, value)
    temporary.replace(path)

def request_fields(request):
    remote = Path(request.get('remote', request.get('remote_directory', '')))
    require(remote.is_absolute() and remote.is_dir(), 'existing absolute deployed directory required')
    files = request['files']
    argv = request['execute_argv']
    r = request['resources']
    require(isinstance(files, dict) and files, 'deployed file SHA manifest required')
    require(isinstance(argv, list) and argv and all((isinstance(x, str) and x for x in argv)), 'explicit argv required')
    expected = dict(CPU_threads=2, GPU_devices=0, RSS_limit_bytes=RSS, wall_seconds_total=WALL, load_seconds_per_model=300, forward_seconds_per_model=9000, max_forward_started=binding('C_frozen_cache_remote_supervisor.cohort_count.1'), input_count=binding('C_frozen_cache_remote_supervisor.cohort_count.2'), expected_H_model_loads=0, expected_C_model_loads=1, outer_cleanup_max_seconds=CLEANUP, retries=0)
    for key, value in expected.items():
        require(type(r.get(key)) is int and r[key] == value, 'C-only frozen resource mismatch: ' + key)
    normalized = {}
    for name, item in files.items():
        require(isinstance(name, str) and name and (not Path(name).is_absolute()) and ('..' not in Path(name).parts), 'relative deployed path required')
        path = (remote / name).resolve()
        require(path.is_relative_to(remote.resolve()), 'deployed path escapes directory')
        expected_sha = item['sha256'] if isinstance(item, dict) else item
        require(isinstance(expected_sha, str) and len(expected_sha) == 64 and all((c in '0123456789abcdef' for c in expected_sha)), 'exact SHA256 required')
        normalized[name] = dict(path=path, sha256=expected_sha, bytes=item.get('bytes') if isinstance(item, dict) else None)
    require(argv.count('--out') == 1 and argv.index('--out') + 1 < len(argv), 'builder output path required')
    output = Path(argv[argv.index('--out') + 1])
    output = output if output.is_absolute() else remote / output
    require(output.resolve().is_relative_to(remote.resolve()), 'cache output escapes deployed directory')
    return (remote, normalized, argv, r, output)

def read_status(text):
    result = {}
    for line in text.splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        if key in ('VmRSS', 'VmHWM'):
            words = value.split()
            if words and words[0].isdecimal():
                result[key + '_bytes'] = int(words[0]) * 1024
    return result

def proc_stat(pid):
    try:
        text = Path('/proc', str(pid), 'stat').read_text()
        values = text[text.rindex(')') + 2:].split()
        return dict(pid=int(pid), pgrp=int(values[2]), session=int(values[3]), start_ticks=int(values[19]))
    except (OSError, ValueError, IndexError):
        return None

def sample_group(pgid):
    rows = []
    for item in Path('/proc').iterdir():
        if not item.name.isdecimal():
            continue
        identity = proc_stat(item.name)
        if identity is None or identity['pgrp'] != pgid or identity['session'] != pgid:
            continue
        try:
            identity.update(read_status((item / 'status').read_text()))
        except OSError:
            continue
        rows.append(identity)
    return dict(utc=utc(), monotonic=time.monotonic(), members=rows, RSS_bytes=sum((r.get('VmRSS_bytes', 0) for r in rows)), HWM_sum_bytes=sum((r.get('VmHWM_bytes', 0) for r in rows)))

def monitor(process, *, deadline, rss_limit, sample_stream, sampler=sample_group):
    samples = 0
    peak = 0
    peak_hwm = 0
    reason = None
    while True:
        check = time.monotonic()
        if check >= deadline:
            reason = 'total_wall_budget'
            break
        sample = sampler(process.pid)
        samples += 1
        peak = max(peak, sample['RSS_bytes'])
        peak_hwm = max(peak_hwm, sample['HWM_sum_bytes'])
        sample_stream.write(json.dumps(sample, sort_keys=True) + '\n')
        sample_stream.flush()
        if sample['RSS_bytes'] > rss_limit:
            reason = 'RSS_budget'
            break
        if process.poll() is not None:
            break
        try:
            process.wait(timeout=min(0.5, max(0.0, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            continue
    if reason is not None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return dict(termination_reason=reason or ('leader_exit_zero' if process.returncode == 0 else 'leader_exit_nonzero'), leader_exit_before_cleanup=process.poll(), sample_count=samples, peak_sampled_RSS_bytes=peak, peak_sampled_HWM_sum_bytes=peak_hwm)

def cleanup_owned(process, *, leader_start_ticks, seconds=CLEANUP):
    started = time.monotonic()
    sent = False
    ownership_lost = False
    signal_error = None
    current = proc_stat(process.pid)
    if leader_start_ticks is not None and current is not None and (current['start_ticks'] != leader_start_ticks):
        ownership_lost = True
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            sent = True
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            signal_error = str(exc)
            if process.poll() is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
    try:
        process.wait(timeout=max(0.0, seconds - (time.monotonic() - started)))
    except subprocess.TimeoutExpired:
        pass
    return dict(cleanup_seconds=time.monotonic() - started, kill_owned_group_sent=sent, group_ownership_lost=ownership_lost, group_signal_error=signal_error, leader_reaped=process.poll() is not None, leader_exit_code=process.returncode)

def partial_cache(output):
    result = dict(expected_inputs=binding('C_frozen_cache_remote_supervisor.cohort_count.3'), valid_recorded=0, failed_recorded=0, not_started_recorded=0, unaccounted_inputs=binding('C_frozen_cache_remote_supervisor.cohort_count.4'), status='not_started_or_no_durable_input_ledger')
    for name in ('receipt.partial.json', 'manifest.json'):
        path = output / name
        if path.exists() and path.stat().st_size <= 1048576:
            try:
                result[name] = json.loads(path.read_text())
            except (OSError, ValueError):
                result[name] = dict(status='unreadable_partial_retained')
    ledger = output / 'inputs.jsonl'
    if ledger.exists():
        seen = {}
        malformed = 0
        try:
            with ledger.open() as stream:
                for literal in stream:
                    try:
                        row = json.loads(literal)
                        if row.get('input_id') in seen:
                            malformed += 1
                        else:
                            seen[row.get('input_id')] = row.get('status')
                    except ValueError:
                        malformed += 1
            counts = {kind: sum((v == kind for v in seen.values())) for kind in ('ok', 'failed_retained', 'not_started_retained')}
            result.update(valid_recorded=counts['ok'], failed_recorded=counts['failed_retained'], not_started_recorded=counts['not_started_retained'], unaccounted_inputs=max(0, binding('C_frozen_cache_remote_supervisor.cohort_count.5') - len(seen)), input_status_counts=counts, duplicate_or_malformed_rows=malformed, status='builder_recorded_partial_preserved_not_independently_validated')
        except OSError as exc:
            result['ledger_read_error'] = str(exc)
    return result

def supervise(request, *, started):
    deadline = started + WALL
    remote, files, argv, resources, output = request_fields(request)
    receipt = dict(schema='C_frozen_cache_remote_supervisor_actual_v1', supervisor_pid=os.getpid(), started_utc=utc(), resources=resources, remote=str(remote), execute_argv=argv, request_sha256=hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest(), pre_file_sha256={}, post_file_sha256={}, child_pid=None, child_pgid=None, leader_exit_code=None, termination_reason='not_started', models_started_by_supervisor=0, retries=0, cache_output=str(output))
    exclusive(remote / 'SUPERVISOR_STARTED.json', dict(supervisor_pid=os.getpid(), utc=receipt['started_utc'], request_sha256=receipt['request_sha256'], resources=resources, child_pid=None))
    process = None
    birth = None
    try:
        require(sys.platform.startswith('linux') and Path('/proc').is_dir(), 'Linux /proc supervisor required')
        allowed = sorted(os.sched_getaffinity(0))
        require(bool(allowed), 'CPU affinity unavailable')
        os.sched_setaffinity(0, allowed[:2])
        receipt['actual_CPU_affinity'] = sorted(os.sched_getaffinity(0))
        for name, item in files.items():
            check_time(deadline)
            actual = sha(item['path'], deadline)
            receipt['pre_file_sha256'][name] = actual
            require(actual == item['sha256'], 'deployed file SHA mismatch: ' + name)
            if item['bytes'] is not None:
                require(item['path'].stat().st_size == item['bytes'], 'deployed file size mismatch: ' + name)
        environment = dict(os.environ, OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2', NUMEXPR_NUM_THREADS='2', CUDA_VISIBLE_DEVICES='')
        check_time(deadline)
        with (remote / 'supervisor_child_stdout.log').open('x') as stdout, (remote / 'supervisor_child_stderr.log').open('x') as stderr, (remote / 'SUPERVISOR_SAMPLES.jsonl').open('x') as samples:
            process = subprocess.Popen(argv, cwd=remote, env=environment, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
            identity = proc_stat(process.pid)
            birth = None if identity is None else identity['start_ticks']
            receipt.update(child_pid=process.pid, child_pgid=process.pid, child_started_utc=utc())
            exclusive(remote / 'SUPERVISOR_CHILD_STARTED.json', dict(supervisor_pid=os.getpid(), child_pid=process.pid, child_pgid=process.pid, start_ticks=birth, utc=receipt['child_started_utc']))
            receipt.update(monitor(process, deadline=deadline, rss_limit=RSS, sample_stream=samples))
            receipt['leader_exit_code'] = process.poll()
        for name, item in files.items():
            check_time(deadline)
            receipt['post_file_sha256'][name] = sha(item['path'], deadline)
            require(receipt['post_file_sha256'][name] == receipt['pre_file_sha256'][name], 'post-run deployed input changed: ' + name)
        receipt['prepost_hash_complete'] = len(receipt['pre_file_sha256']) == len(receipt['post_file_sha256']) == len(files)
    except BaseException as exc:
        receipt['termination_reason'] = 'total_wall_budget' if isinstance(exc, TimeoutError) else 'supervisor_error'
        receipt['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        receipt['work_wall_seconds'] = time.monotonic() - started
        if process is not None:
            receipt.update(cleanup_owned(process, leader_start_ticks=birth, seconds=CLEANUP))
        else:
            receipt.update(cleanup_seconds=0, leader_reaped=True, child_never_started=True)
        receipt['partial_cache'] = partial_cache(output)
        receipt['builder_manifest_status'] = receipt['partial_cache'].get('manifest.json', {}).get('status')
        receipt['finished_utc'] = utc()
        receipt['actual_wall_with_cleanup_seconds'] = time.monotonic() - started
        receipt['status'] = 'builder_completed_hashes_closed_review_pending' if receipt.get('termination_reason') == 'leader_exit_zero' and receipt.get('prepost_hash_complete') is True and (receipt.get('leader_reaped') is True) and (receipt.get('builder_manifest_status') == 'complete') else 'failed_or_partial_retained_no_retry'
        atomic(remote / 'SUPERVISOR_ACTUAL_RECEIPT.json', receipt)
    return dict(status=receipt['status'], termination_reason=receipt['termination_reason'], child_pid=receipt['child_pid'], leader_exit_code=receipt['leader_exit_code'], leader_reaped=receipt['leader_reaped'], work_wall_seconds=receipt['work_wall_seconds'], cleanup_seconds=receipt['cleanup_seconds'], peak_sampled_RSS_bytes=receipt.get('peak_sampled_RSS_bytes'), partial_cache={k: receipt['partial_cache'][k] for k in ('status', 'expected_inputs', 'valid_recorded', 'failed_recorded', 'not_started_recorded', 'unaccounted_inputs')}, builder_manifest_status=receipt.get('builder_manifest_status'), receipt_path=str(remote / 'SUPERVISOR_ACTUAL_RECEIPT.json'))

def self_test():
    import io
    import tempfile
    require(read_status('VmRSS: 12 kB\nVmHWM: 20 kB\n') == {'VmRSS_bytes': 12288, 'VmHWM_bytes': 20480}, 'status parser')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'stdout'
        with path.open('w') as stream:
            child = subprocess.Popen([sys.executable, '-u', '-c', 'import threading;print("READY",flush=True);threading.Event().wait()'], stdout=stream, stderr=stream, start_new_session=True)
            try:

                def sampler(pid):
                    ready = 'READY' in path.read_text()
                    return dict(RSS_bytes=11 if ready else 0, HWM_sum_bytes=11 if ready else 0, members=[])
                result = monitor(child, deadline=time.monotonic() + 3, rss_limit=10, sample_stream=io.StringIO(), sampler=sampler)
                require(result['termination_reason'] == 'RSS_budget', 'READY RSS cancellation')
                require('READY' in path.read_text(), 'child must have entered controlled wait')
            finally:
                cleaned = cleanup_owned(child, leader_start_ticks=None, seconds=2)
            require(cleaned['leader_reaped'] and child.returncode == -signal.SIGKILL, 'owned child kill and reap')
        duplicate = Path(tmp) / 'SUPERVISOR_STARTED.json'
        exclusive(duplicate, {'pid': os.getpid()})
        try:
            exclusive(duplicate, {'duplicate': True})
        except FileExistsError:
            pass
        else:
            raise AssertionError('exclusive duplicate lock failed')
    return dict(status='SYNTHETIC_MONITOR_CHECKS_PASS_NO_MODEL', checks=4)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test()))
        return
    started = time.monotonic()

    def alarm(signum, frame):
        raise TimeoutError('total wall budget including request metadata and hashes')
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, WALL)
    try:
        raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
        require(len(raw) <= 4 * 1024 * 1024, 'deployment request too large')
        request = json.loads(raw)
        result = supervise(request, started=started)
    except BaseException as exc:
        signal.setitimer(signal.ITIMER_REAL, 0)
        result = dict(status='supervisor_not_started_or_request_rejected', error=type(exc).__name__ + ': ' + str(exc))
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
if __name__ == '__main__':
    main()
