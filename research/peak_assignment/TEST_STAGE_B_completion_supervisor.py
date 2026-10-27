# 功能概述：已审conditional4公开副本，实际源SHA与portableSHA分别绑定。
# 关系：显式runtime授权/源码闭包；保留原终态、once、边界、预算与科学谓词。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding
authorize()
"""功能概述：条件completion/report独立监督，不修改活跃B监督或原7200s时钟。
main先以显式N选择15N+600或report600预算，然后才让受监督子进程读取plan；RSS8GiB/单CPU继承。
复用2e6b进程树监督和cleanup，保存独立inner/outer/全输出，不把原score非0变为0。
不重试，不创建第三段；--execute以外只输出接口。只由root未来实际terminal/review/plan绑定后启动。
"""
from pathlib import Path
import argparse,importlib.util,json,os,sys
import TEST_STAGE_B_completion as completion
def main():
    p=argparse.ArgumentParser();p.add_argument("--plan");p.add_argument("--plan-sha256");p.add_argument("--release");p.add_argument("--release-sha256");p.add_argument("--suffix-count",type=int);p.add_argument("--supervisor-dir");p.add_argument("--frozen-supervisor");p.add_argument("--report",action="store_true");p.add_argument("--execute",action="store_true");a=p.parse_args()
    if not a.execute:print(json.dumps(dict(schema="TEST_STAGE_B_completion_supervisor_interface_v1",execution_authorized=False,completion_wall="15*N+600",report_wall=600,RSS_bytes=8589934592,cleanup=60,no_retry=True)));return 0
    completion.need(a.suffix_count is not None and 0<a.suffix_count<=3636,"fixed positive suffix N")
    completion.need(completion.sha(a.frozen_supervisor)==completion.SUPERVISOR_SHA,"frozen process supervision source")
    frozen=completion.module(a.frozen_supervisor,"completion_frozen_supervision")
    budget=dict(CPU_threads=1,GPU=0,RSS_bytes=8589934592,total_wall_seconds=600 if a.report else 15*a.suffix_count+600,record_workers=1,cleanup_seconds=60)
    directory=Path(a.supervisor_dir);directory.mkdir(parents=True,exist_ok=False)
    os.environ["TEST_STAGE_B_COMPLETION_OUTER_PID"]=str(os.getpid())
    entry=Path(__file__).with_name("TEST_STAGE_B_completion_report.py" if a.report else "TEST_STAGE_B_completion.py")
    argv=[sys.executable,"-B",str(entry),"--plan",a.plan,"--plan-sha256",a.plan_sha256,"--release",a.release,"--release-sha256",a.release_sha256,"--execute"]
    # Explicit N is handed to child before it reads any plan; disagreement rejects.
    os.environ["TEST_STAGE_B_COMPLETION_SUFFIX_N"]=str(a.suffix_count)
    r=frozen.supervise_process(with_runtime(argv),directory=directory,prefix="TEST_STAGE_B_completion_report" if a.report else "TEST_STAGE_B_completion",budget=budget,cwd=entry.parent,phase="completion_report" if a.report else "completion",input_hashes={a.plan:a.plan_sha256,a.release:a.release_sha256})
    print(json.dumps(r));return r["actual_outer_exit"]

# 每个helper入口核相同显式runtime与公开四源闭包，防绕过main直接访问外部制品。
def _public_guard(function):
    import functools
    @functools.wraps(function)
    def call(*args,**kwargs):
        authorize()
        import hashlib
        sources=binding("conditional_completion.public_source_sha256")
        if set(sources)!={'TEST_STAGE_B_completion_tests.py', 'TEST_STAGE_B_completion_supervisor.py', 'TEST_STAGE_B_completion.py', 'TEST_STAGE_B_completion_report.py'}:raise ValueError("conditional complete four-source binding required")
        for name,want in sources.items():
            path=Path(__file__).with_name(name)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=want:raise ValueError("conditional public source binding mismatch:"+name)
        return function(*args,**kwargs)
    return call
for _name in ('main',):globals()[_name]=_public_guard(globals()[_name])
if __name__=="__main__":raise SystemExit(main())
