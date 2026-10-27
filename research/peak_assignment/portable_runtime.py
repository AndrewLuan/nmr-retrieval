# 功能概述：公开outer源码的外部绑定读取器，不授权科学运行、不生成证书。
# repository定位现有nmr_assignment/nmr_transfer；workspace/artifact_path区分制品和公开源码。
# binding缺字段立即失败；render只替换已命名路径槽；CLI参数在子脚本argparse前移除。
# 文件SHA由独立--runtime-manifest-sha256绑定；manifest字节不依赖私有D目录。
import sys,json,hashlib,re
from pathlib import Path
_ROOT=Path(__file__).resolve().parent
_CONFIG=None
def repository():
    root=_ROOT.parents[1]
    if not (root/'nmr_assignment').is_dir(): raise ValueError('repository core not found')
    if str(root) not in sys.path: sys.path.insert(0,str(root))
    return root
def _config():
    global _CONFIG
    if _CONFIG is None:
        def pop(flag):
            if flag not in sys.argv: raise ValueError('explicit '+flag+' required')
            i=sys.argv.index(flag);value=sys.argv[i+1];del sys.argv[i:i+2];return value
        path=Path(pop('--runtime-manifest'));want=pop('--runtime-manifest-sha256');raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=want:raise ValueError('runtime manifest digest mismatch')
        candidate=json.loads(raw)
        if candidate.get('schema')!='portable_assignment_runtime_v1':raise ValueError('runtime schema')
        # 模式互斥：原入口可能优先execute，任何只读flag均不能覆盖执行flag。
        modes = [x.split('=',1)[0] for x in sys.argv[1:] if x.split('=',1)[0] in
            ('--execute','--aggregate','--self-test','--checkonly','--check-only','--validate-only','--help')]
        if len(modes) > 1:
            raise ValueError('conflicting execution/read-only modes are forbidden')
        # parserless入口不会消费help/self-test；任何外部配置读取均须明确授权。
        if candidate.get('execution_authorized') is not True:
            raise ValueError('public execution defaults false; explicit externally reviewed authorization required')
        _CONFIG=candidate
    if _CONFIG.get('execution_authorized') is not True:
        raise ValueError('external artifact/config access requires execution_authorized=true')
    return _CONFIG
def workspace(): return Path(_config()['workspace'])
def artifact_path(name):
    _config()
    name=str(name)
    if name.endswith('.py') and (_ROOT/name).is_file():return _ROOT/name
    return Path(_config().get('artifacts',{}).get(name,workspace()/name))
def binding(key):
    values=_config()['bindings']
    if key not in values:raise ValueError('missing explicit external binding: '+key)
    return values[key]
def render(text):return re.sub(r'@@([^@]+)@@',lambda m:str(binding(m.group(1))),text)
repository()
