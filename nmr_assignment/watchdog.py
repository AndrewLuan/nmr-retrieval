"""功能概述：用独占子进程组执行单记录任务，外层时限包含启动、输入与后端初始化。

run_isolated接显式argv、输入文本、总秒数及环境覆盖，返回退出/超时和原始输出。
计时从参数验证前开始；剩余预算耗尽时不启动进程。communicate受同一截止约束，
超时后仅杀本函数创建的新session进程组，等待回收并收齐stdout/stderr，不自动重试。
关系：baseline数据driver用此函数包住mapping、候选、solver setup/Top3/margins；
solver内部计时不能替代此边界。调用方保留timeout记录与固定gold分母。
输入输出与副作用：仅POSIX本地主机/JJ；不使用shell，不接收gold或推断语义，不访问
其他任务PID。正常失败与deadline分别记录。清理发生于所有异常路径，防止迟到输出。
"""
from dataclasses import dataclass
from math import isfinite
import os
import signal
import subprocess
from time import monotonic


@dataclass(frozen=True)
class WatchdogResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    elapsed_seconds: float
    child_pid: int | None
    process_reaped: bool


def _kill_owned(process):
    """Kill the self-created session even if its leader has already exited.

    Descendants can retain the group's pipes after leader exit. process.pid is the
    PGID established by this invocation's start_new_session=True; no external PID
    or caller-provided process group is accepted.
    """
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _partial_text(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    return value or ''


def _finish_owned(process):
    """Bound cleanup too; an escaped pipe holder cannot hang the whole driver."""
    try:
        return process.communicate(timeout=.25)
    except subprocess.TimeoutExpired as exc:
        out, err = _partial_text(exc.output), _partial_text(exc.stderr)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        try:
            process.wait(timeout=.25)
        except subprocess.TimeoutExpired:
            # Only this Popen's leader is targeted, never another job's PID.
            process.kill()
            try:
                process.wait(timeout=.25)
            except subprocess.TimeoutExpired:
                pass
        return out, err


def run_isolated(argv, input_text, *, timeout_seconds, env_overrides=None, cwd=None):
    started = monotonic()
    if os.name != 'posix':
        raise ValueError('this worker driver requires POSIX process groups')
    if (isinstance(timeout_seconds, (bool, str)) or not isinstance(timeout_seconds, (int, float))
            or not isfinite(timeout_seconds) or timeout_seconds <= 0):
        raise ValueError('finite positive total timeout required')
    if (not isinstance(argv, (tuple, list)) or not argv
            or any(not isinstance(x, str) or not x for x in argv)):
        raise ValueError('explicit nonempty argv sequence required')
    if not isinstance(input_text, str):
        raise ValueError('worker input must already be a validated text payload')
    environment = dict(os.environ)
    for key, value in (env_overrides or {}).items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError('environment overrides must be text')
        environment[key] = value
    deadline = started + float(timeout_seconds)
    if monotonic() >= deadline:
        return WatchdogResult(None, '', '', True, monotonic()-started, None, True)
    process = None
    communication_completed = False
    try:
        process = subprocess.Popen(list(argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, cwd=cwd, env=environment, start_new_session=True)
        try:
            remaining = max(0., deadline-monotonic())
            out, err = process.communicate(input_text, timeout=remaining)
            communication_completed = True
            # A returned result just beyond the boundary remains a timeout even if
            # the worker claims optimality. Its raw output is kept for diagnosis.
            timed_out = monotonic() >= deadline
        except subprocess.TimeoutExpired:
            timed_out = True
    finally:
        # A successful leader can leave a descendant whose pipes were detached
        # or closed by a stage supervisor. Always close this invocation's owned
        # group, including normal/nonzero exit and exceptions; preserve the
        # leader's original return code and computation-timeout facts.
        if process is not None:
            _kill_owned(process)
            drained_out, drained_err = _finish_owned(process)
            if not communication_completed:
                out, err = drained_out, drained_err
    return WatchdogResult(process.returncode, out, err, timed_out,
                          monotonic()-started, process.pid, process.poll() is not None)
