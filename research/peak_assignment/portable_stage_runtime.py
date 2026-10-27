# 功能概述：B公开控制链的显式runtime参数传递；不改变已审portable_runtime。
# 模块首次导入在任何workspace绑定前保存CLI两参数；authorize仍由冻结runtime核SHA/显式授权。
# with_runtime为outer/worker/phase子进程附相同path/SHA；已有参数必须相同，不复制生产数据。
import sys
from portable_runtime import _config

def capture(argv):
    result=[]
    for flag in ('--runtime-manifest','--runtime-manifest-sha256'):
        if argv.count(flag)!=1:return []
        i=argv.index(flag)
        if i+1>=len(argv):return []
        result += [flag,argv[i+1]]
    return result
RUNTIME_ARGUMENTS=capture(sys.argv)
def authorize():
    _config()
    if len(RUNTIME_ARGUMENTS)!=4:raise ValueError('explicit runtime CLI path/SHA required for public phase chain')
    return RUNTIME_ARGUMENTS[:]
def with_runtime(argv):
    args=authorize();out=list(argv)
    present=[x for x in out if x in ('--runtime-manifest','--runtime-manifest-sha256')]
    if present:
        if capture(out)!=args:raise ValueError('child runtime path/SHA mismatch')
        return out
    return out+args
