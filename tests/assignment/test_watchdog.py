"""功能概述：用真实独占子进程验证记录级超时、回收与原始输出保留，不运行模型。
关系：只测watchdog公开函数；child用READY事件确认已进入受控等待，避免把未启动当取消。
输入输出：子进程标准输入/输出；无固定sleep、自动重试或共享进程终止，无文件副作用。
"""
import os
import json
import signal
import socket
import sys
import tempfile
import unittest
from nmr_assignment.watchdog import run_isolated


@unittest.skipUnless(os.name == 'posix', 'POSIX worker contract')
class WatchdogTests(unittest.TestCase):
    def test_normal_exit_preserves_output_and_failure_code(self):
        result = run_isolated([sys.executable, '-c',
            'import sys;print(sys.stdin.read());sys.stderr.write("diagnostic");sys.exit(7)'],
            'anonymous payload', timeout_seconds=5)
        self.assertEqual(result.exit_code, 7)
        self.assertIn('anonymous payload', result.stdout)
        self.assertEqual(result.stderr, 'diagnostic')
        self.assertFalse(result.timed_out)
        self.assertTrue(result.process_reaped)

    def test_started_worker_timeout_is_killed_and_reaped(self):
        result = run_isolated([sys.executable, '-u', '-c',
            'import threading;print("READY",flush=True);threading.Event().wait()'],
            '', timeout_seconds=1)
        self.assertIn('READY', result.stdout)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.exit_code, -9)
        self.assertTrue(result.process_reaped)
        with self.assertRaises(ProcessLookupError):
            os.kill(result.child_pid, 0)

    def test_invalid_deadline_does_not_start_worker(self):
        for limit in (None, 0, -1, float('inf'), float('nan'), True, '10'):
            with self.assertRaises(ValueError):
                run_isolated([sys.executable, '-c', 'raise RuntimeError("must not start")'],
                             '', timeout_seconds=limit)

    def test_exited_leader_pipe_holding_descendant_is_cleaned(self):
        # The fixture has its own bounded end so a regression fails rather than
        # hanging the suite forever. READY proves the descendant actually started.
        descendant = 'import threading;print("DESCENDANT_READY",flush=True);threading.Event().wait(4)'
        leader = ('import subprocess,sys;subprocess.Popen([sys.executable,"-u","-c",'
                  + repr(descendant) + ']);print("LEADER_EXIT",flush=True)')
        result = run_isolated([sys.executable, '-u', '-c', leader], '', timeout_seconds=1)
        self.assertIn('LEADER_EXIT', result.stdout)
        self.assertIn('DESCENDANT_READY', result.stdout)
        self.assertTrue(result.timed_out)
        self.assertTrue(result.process_reaped)
        self.assertEqual(result.exit_code, 0)  # Leader exited before timeout.
        self.assertLess(result.elapsed_seconds, 2)

    def test_normal_leader_exit_cleans_detached_pipe_descendant(self):
        # The socket's EOF certifies descendant termination without PID polling.
        # A control pipe proves READY before the leader exits normally. The
        # guardian bounds a failed test too; it is not a synchronization sleep.
        with tempfile.TemporaryDirectory(prefix='watchdog-') as folder:
            path = os.path.join(folder, 'ready.sock')
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(path)
                server.listen(1)
                server.settimeout(2)
                descendant = (
                    'import os,socket,sys,threading;'
                    's=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);'
                    's.connect(sys.argv[1]);s.sendall(b"READY");'
                    'os.write(int(sys.argv[2]),b"READY");os.close(int(sys.argv[2]));'
                    'threading.Event().wait(4)')
                leader = (
                    'import os,subprocess,sys,json;readfd,writefd=os.pipe();'
                    'p=subprocess.Popen([sys.executable,"-c",'+repr(descendant)+',sys.argv[1],str(writefd)],'
                    'pass_fds=(writefd,),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);'
                    'os.close(writefd);assert os.read(readfd,5)==b"READY";os.close(readfd);'
                    'print(json.dumps({"descendant_pid":p.pid}),flush=True)')
                result = None
                descendant_closed = False
                try:
                    result = run_isolated([sys.executable, '-c', leader, path], '', timeout_seconds=2)
                    self.assertEqual(result.exit_code, 0)
                    self.assertFalse(result.timed_out)
                    self.assertTrue(result.process_reaped)
                    self.assertGreater(json.loads(result.stdout)['descendant_pid'], 0)
                    with server.accept()[0] as connection:
                        connection.settimeout(1)
                        self.assertEqual(connection.recv(5), b'READY')
                        self.assertEqual(connection.recv(1), b'')
                        descendant_closed = True
                finally:
                    if result is not None and not descendant_closed:
                        try:
                            os.killpg(result.child_pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass


if __name__ == '__main__':
    unittest.main()
