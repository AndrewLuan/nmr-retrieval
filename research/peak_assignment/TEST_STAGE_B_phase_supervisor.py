# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：Stage B各phase一次性监督，动态C队列≤3637；不使用旧硬3740监督脚本。
实际入口先核execution suite/A实际source PASS/owner once及phase产物门禁；默认不启动进程。
phase_worker把claim/validate_phase/实际子进程/输入posthash/最终inventory放进单个受监督进程，固定同一clock/RSS；无自动retry。
execute要求显式phase-name先选冻结预算，外层不先读取或验证manifest；仅worker完成inventory后才可报outer0。
监督原argv/UTC/PID/inner与outer exit/RSS/输入输出SHA，worker exit与实际phase child exit分别保留。
start_new_session建立进程组所有权，finally先清理所属PG，再清理birth-time已见后代，
有限回收并核owned survivors；清理失败或资源超限不能报成功。合成测试只直接调用进程原语。
"""
from pathlib import Path
import argparse, datetime, json, os, signal, subprocess, time, sys
import psutil
import TEST_STAGE_B_execution_contract as contract
D = workspace()

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def group_members(pgid):
    found = []
    for proc in psutil.process_iter(['pid', 'create_time', 'status']):
        try:
            if os.getpgid(proc.pid) == pgid and proc.info['status'] != psutil.STATUS_ZOMBIE:
                found.append((proc.pid, proc.info['create_time']))
        except (OSError, psutil.Error):
            pass
    return found

def cleanup(child, owned, seconds):
    start = time.monotonic()
    pgid = child.pid if child else None
    if pgid:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for pid, born in reversed(tuple(owned.items())):
        try:
            p = psutil.Process(pid)
            if p.create_time() == born and p.status() != psutil.STATUS_ZOMBIE:
                p.kill()
        except psutil.Error:
            pass
    reaped = True
    if child:
        try:
            child.wait(timeout=max(0.01, seconds - (time.monotonic() - start)))
        except subprocess.TimeoutExpired:
            reaped = False
    survivors = []
    deadline = start + seconds
    while True:
        survivors = []
        for pid, born in owned.items():
            try:
                p = psutil.Process(pid)
                if p.create_time() == born and p.is_running() and (p.status() != psutil.STATUS_ZOMBIE):
                    survivors.append(pid)
            except psutil.Error:
                pass
        if pgid:
            survivors.extend((pid for pid, _ in group_members(pgid)))
        survivors = sorted(set(survivors))
        if not survivors or time.monotonic() >= deadline:
            break
        pending = []
        for pid in survivors:
            try:
                pending.append(psutil.Process(pid))
            except psutil.Error:
                pass
        psutil.wait_procs(pending, timeout=min(0.05, max(0.0, deadline - time.monotonic())))
    return dict(leader_reaped=reaped, owned_survivors=survivors, cleanup_seconds=time.monotonic() - start)

def supervise_process(argv, *, directory, prefix, budget, cwd, phase, input_hashes=None, expected_H_loads=None, expected_C_loads=None, started_monotonic=None, started_UTC=None, inner_state_path=None):
    directory = Path(directory)
    contract.need(directory.is_dir(), 'supervisor_parent_required')
    base = directory / prefix
    receipt = dict(schema='TEST_STAGE_B_phase_actual_v1', phase=phase, started_UTC=started_UTC or utc(), supervisor_PID=os.getpid(), argv=argv, budget=budget, actual_inner_exit=None, actual_outer_exit=None, peak_tree_RSS_bytes=0, termination_reason=None, retries=0, input_sha256=input_hashes or {}, expected_H_model_loads=expected_H_loads, expected_C_model_loads=expected_C_loads)
    contract.write(str(base) + '_LAUNCH.json', receipt)
    child = None
    owned = {}
    start = time.monotonic() if started_monotonic is None else started_monotonic
    env = dict(os.environ, TEST_STAGE_B_PHASE_OUTER_PID=str(os.getpid()), CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS=str(budget['CPU_threads']), OPENBLAS_NUM_THREADS=str(budget['CPU_threads']), MKL_NUM_THREADS=str(budget['CPU_threads']))
    try:
        with open(str(base) + '_stdout.log', 'x') as stdout, open(str(base) + '_stderr.log', 'x') as stderr, open(str(base) + '_resources.jsonl', 'x') as samples:
            contract.need(time.monotonic() - start < budget['total_wall_seconds'], 'preflight_wall_budget_exhausted')
            child = subprocess.Popen(with_runtime(argv), cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
            receipt['child_PID'] = child.pid
            try:
                root = psutil.Process(child.pid)
                if hasattr(root, 'cpu_affinity'):
                    available = root.cpu_affinity()
                    root.cpu_affinity(available[:budget['CPU_threads']])
                    receipt['CPU_affinity'] = root.cpu_affinity()
            except psutil.NoSuchProcess:
                root = None
            while True:
                try:
                    procs = [root] + root.children(recursive=True) if root else []
                except psutil.NoSuchProcess:
                    procs = []
                rss = 0
                for p in procs:
                    try:
                        owned[p.pid] = p.create_time()
                        rss += p.memory_info().rss
                    except psutil.Error:
                        pass
                elapsed = time.monotonic() - start
                receipt['peak_tree_RSS_bytes'] = max(receipt['peak_tree_RSS_bytes'], rss)
                samples.write(json.dumps(dict(elapsed_seconds=elapsed, tree_RSS_bytes=rss, processes=len(procs))) + '\n')
                samples.flush()
                if rss > budget['RSS_bytes']:
                    receipt['termination_reason'] = 'RSS_limit'
                    break
                if elapsed >= budget['total_wall_seconds']:
                    receipt['termination_reason'] = 'wall_limit'
                    break
                try:
                    child.wait(timeout=min(0.05, budget['total_wall_seconds'] - elapsed))
                    receipt['termination_reason'] = 'leader_exit'
                    break
                except subprocess.TimeoutExpired:
                    pass
    except BaseException as exc:
        receipt['termination_reason'] = 'supervisor_exception'
        receipt['error'] = type(exc).__name__ + ':' + str(exc)
    finally:
        closed = cleanup(child, owned, budget['cleanup_seconds'])
        receipt.update(closed)
        receipt['actual_inner_exit'] = child.returncode if child else None
        if inner_state_path is not None:
            receipt['actual_worker_exit'] = receipt['actual_inner_exit']
            receipt['actual_inner_exit'] = None
            try:
                state = json.loads(Path(inner_state_path).read_text())
                receipt['actual_inner_exit'] = state.get('actual_inner_exit')
                receipt['last_worker_stage'] = state.get('stage')
                receipt['worker_error'] = state.get('error')
                receipt['once_claim'] = state.get('once_claim')
                receipt['child_output_inventory'] = state.get('child_output_inventory')
                receipt['phase_input_sha256'] = state.get('input_sha256', {})
                receipt['phase_input_postcheck_passed'] = state.get('input_postcheck_passed', False)
                receipt['request_items'] = state.get('request_items', {})
            except (OSError, ValueError):
                receipt['last_worker_stage'] = 'state_unavailable'
        changed = []
        for p, h in (input_hashes or {}).items():
            try:
                if contract.sha(p) != h:
                    changed.append(p)
            except OSError:
                changed.append(p)
        ok = receipt.get('actual_worker_exit', receipt['actual_inner_exit']) == 0 and receipt['actual_inner_exit'] == 0 and (inner_state_path is None or receipt.get('last_worker_stage') == 'inventory_completed') and (receipt['termination_reason'] == 'leader_exit') and closed['leader_reaped'] and (not closed['owned_survivors']) and (not changed)
        receipt.update(status='CHILD_COMPLETED_PENDING_ARTIFACT_AUDIT' if ok else 'FAILED_OR_PARTIAL_RETAINED_NO_RETRY', actual_outer_exit=0 if ok else 1, finished_UTC=utc(), elapsed_seconds=time.monotonic() - start, input_hashes_unchanged=not changed, changed_inputs=changed)
        if inner_state_path is not None and receipt.get('child_output_inventory'):
            try:
                worker_inventory = contract.bound(receipt['child_output_inventory'])
                contract.need(worker_inventory.stat().st_size <= 67108864, 'inventory_metadata_size_limit')
                inventory = json.loads(worker_inventory.read_text())
                inventory.update(outer_exit=receipt['actual_outer_exit'], final_outer_UTC=utc(), worker_inventory=receipt['child_output_inventory'], cleanup=closed)
                final_path = directory / (prefix + '_child_output_inventory.json')
                contract.write(final_path, inventory)
                receipt['child_output_inventory'] = contract.item(final_path)
            except BaseException as exc:
                receipt.update(actual_outer_exit=1, status='FAILED_OR_PARTIAL_RETAINED_NO_RETRY', inventory_finalization_error=type(exc).__name__ + ':' + str(exc))
        outputs = {}
        for p in directory.glob(prefix + '_*'):
            if p.is_file() and p.name != prefix + '_actual.json':
                outputs[p.name] = dict(sha256=contract.sha(p), bytes=p.stat().st_size)
        receipt['supervisor_output_sha256'] = outputs
        contract.write(str(base) + '_actual.json', receipt)
    return receipt

def write_state(path, value):
    """只覆盖本次worker中间receipt；最终outer receipt由父监督在cleanup后写出。"""
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)

def phase_worker(suite_item, release_item, phase_item, name, worker_dir):
    """预检、phase子进程和最终inventory均在同一受监督worker/PG/RSS/wall内。"""
    state_path = Path(worker_dir) / ('TEST_STAGE_B_' + name + '_worker_state.json')
    state = dict(stage='before_claim', phase=name, actual_inner_exit=None, child_started=False, started_UTC=utc(), request_items=dict(suite=suite_item, release=release_item, phase=phase_item))
    write_state(state_path, state)
    try:
        state['once_claim'] = contract.claim_phase(suite_item, release_item, name)
        state['stage'] = 'before_validate_phase'
        write_state(state_path, state)
        suite, a, phase, config, argv = contract.validate_phase(suite_item, release_item, phase_item)
        contract.need(phase['phase'] == name, 'explicit_phase_budget_binding')
        inputs = {v['path']: v['sha256'] for v in (suite_item, release_item, phase_item, phase['config'])}
        for v in suite['implementations'].values():
            inputs[v['path']] = v['sha256']
        for value in config.values():
            if isinstance(value, dict) and 'path' in value and ('sha256' in value):
                contract.bound(value)
                inputs[value['path']] = value['sha256']
        state.update(stage='before_phase_child', argv=argv, input_sha256=inputs)
        write_state(state_path, state)
        prefix = Path(worker_dir) / ('TEST_STAGE_B_' + name + '_phase_child')
        with open(str(prefix) + '_stdout.log', 'x') as stdout, open(str(prefix) + '_stderr.log', 'x') as stderr:
            child = subprocess.Popen(with_runtime(argv), cwd=suite['working_directory'], stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
            state.update(stage='phase_child_running', child_started=True, child_PID=child.pid)
            write_state(state_path, state)
            inner = child.wait()
        state.update(stage='before_output_inventory', actual_inner_exit=inner)
        write_state(state_path, state)
        changed = [p for p, h in inputs.items() if not Path(p).is_file() or contract.sha(p) != h]
        contract.need(not changed, 'phase_input_hash_changed:' + repr(changed))
        state['input_postcheck_passed'] = True
        out = Path(config['output_directory'])
        closed = {}
        if out.exists():
            for path in out.rglob('*'):
                if path.is_file():
                    closed[str(path.relative_to(out))] = dict(sha256=contract.sha(path), bytes=path.stat().st_size)
        inventory_path = Path(worker_dir) / ('TEST_STAGE_B_' + name + '_worker_output_inventory.json')
        contract.write(inventory_path, dict(child_exit=inner, outer_exit=None, output_sha256=closed, requires_phase_application_audit=True, no_retry=True, inventory_completed_UTC=utc(), once_claim=state['once_claim']))
        state.update(stage='inventory_completed', child_output_inventory=contract.item(inventory_path), finished_UTC=utc())
        write_state(state_path, state)
        return 0 if inner == 0 else 1
    except BaseException as exc:
        state.update(stage='worker_failed', error=type(exc).__name__ + ':' + str(exc), finished_UTC=utc())
        write_state(state_path, state)
        return 1

def execute(suite_item, release_item, phase_item, supervisor_dir, *, phase_name):
    contract.need(phase_name in contract.BUDGETS, 'explicit_phase_name_required')
    directory = Path(supervisor_dir)
    contract.need(directory.is_dir(), 'supervisor_parent_required')
    argv = [sys.executable, '-B', str(Path(__file__).resolve()), '--_worker', '--phase-name', phase_name, '--suite', suite_item['path'], '--suite-sha256', suite_item['sha256'], '--owner-release', release_item['path'], '--owner-release-sha256', release_item['sha256'], '--phase', phase_item['path'], '--phase-sha256', phase_item['sha256'], '--supervisor-dir', str(directory)]
    return supervise_process(argv, directory=directory, prefix='TEST_STAGE_B_' + phase_name, budget=contract.BUDGETS[phase_name], cwd=D, phase=phase_name, inner_state_path=directory / ('TEST_STAGE_B_' + phase_name + '_worker_state.json'))

def main():
    authorize()
    p = argparse.ArgumentParser()
    p.add_argument('--suite')
    p.add_argument('--suite-sha256')
    p.add_argument('--owner-release')
    p.add_argument('--owner-release-sha256')
    p.add_argument('--phase')
    p.add_argument('--phase-sha256')
    p.add_argument('--phase-name', choices=tuple(contract.BUDGETS))
    p.add_argument('--supervisor-dir')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--_worker', action='store_true', help=argparse.SUPPRESS)
    a = p.parse_args()
    if not a.execute and (not a._worker):
        print(json.dumps(contract.contract(), indent=2))
        return 0
    si = dict(path=a.suite, sha256=a.suite_sha256)
    ri = dict(path=a.owner_release, sha256=a.owner_release_sha256)
    pi = dict(path=a.phase, sha256=a.phase_sha256)
    if a._worker:
        contract.need(os.environ.get('TEST_STAGE_B_PHASE_OUTER_PID') == str(os.getppid()), 'internal_worker_requires_live_outer_parent')
        return phase_worker(si, ri, pi, a.phase_name, a.supervisor_dir)
    receipt = execute(si, ri, pi, a.supervisor_dir, phase_name=a.phase_name)
    print(json.dumps(receipt, indent=2))
    return receipt['actual_outer_exit']
if __name__ == '__main__':
    raise SystemExit(main())
