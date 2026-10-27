# 功能概述：公开H续行的identity-free导入/授权/状态机检查，不调用真实helper/model/score。
# main在隔离子进程中仅导入公共模块，验证同目录控制原语、精确资源错误与不重试语义。
# 临时dummy runtime明确授权且只含虚构绑定；false授权真实CLI连help也拒绝；不读D制品。
import json,hashlib,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    template=json.loads((ROOT/'templates/H_resume_runtime_bindings.example.json').read_text())
    assert template['execution_authorized'] is False
    with tempfile.TemporaryDirectory() as td:
        folder=Path(td);manifest=folder/'dummy.json'
        config=dict(template,execution_authorized=True,workspace=str(folder),bindings={
            k:(1 if 'count' in k else 'a'*64) for k in template['bindings']})
        manifest.write_text(json.dumps(config));digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
        code="""import sys,importlib,json
from pathlib import Path
root=Path(sys.argv[1]);manifest=sys.argv[2];digest=sys.argv[3]
sys.path.insert(0,str(root));sys.argv=['synthetic','--runtime-manifest',manifest,'--runtime-manifest-sha256',digest]
import resume_frozen_H_postprocessing_batch as driver
import supervise_frozen_H_postprocessing_resume as supervisor
import postprocessing_control_primitives as primitives
assert driver.need is primitives.need and supervisor.need is primitives.need
assert all(Path(m.__file__).resolve().parent==root.resolve() for m in (driver,supervisor,primitives))
assert supervisor.TOTAL==894 and supervisor.RESERVE==12
items=[dict(input_id='synthetic-'+str(i),roles=['synthetic-validation'],fixed_source_denominators={}) for i in range(3)]
prior=[dict(input_id=x['input_id'],status='not_started_unknown') for x in items];seen=[]
def invoke(x):
 seen.append(x['input_id'])
 if x['input_id']=='synthetic-1':raise ValueError('source_ledger_preflight_bound')
 return dict(input_id=x['input_id'],roles=x['roles'],status='complete'),None
rows=list(driver.run_tail(items,prior,invoke,lambda:None))
assert seen==[x['input_id'] for x in items]
assert [x[1]['status'] for x in rows]==['complete','resource_unknown','complete']
prior[0]['status']='unknown'
try:list(driver.run_tail(items,prior,invoke,lambda:None))
except ValueError:pass
else:raise AssertionError('historical unknown retry admitted')
assert not driver.exact_resource_error(ValueError('source_ledger_preflight_bound extra'))
print('PASS_PUBLIC_H_RESUME_IMPORT_AND_PURE_STATE_MACHINE')
"""
        run=subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT),str(manifest),digest],cwd=folder,capture_output=True,text=True)
        assert run.returncode==0,(run.stdout,run.stderr)
        config['execution_authorized']=False;manifest.write_text(json.dumps(config));digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
        denied=0
        for entry in ('resume_frozen_H_postprocessing_batch.py','supervise_frozen_H_postprocessing_resume.py'):
            for flag in ('--help','--execute'):
                run=subprocess.run([sys.executable,'-I','-B','-c',
                    "import runpy,sys;sys.path.insert(0,sys.argv[1]);p=sys.argv[2];sys.argv=sys.argv[2:];runpy.run_path(p,run_name='__main__')",
                    str(ROOT),str(ROOT/entry),'--runtime-manifest',str(manifest),'--runtime-manifest-sha256',digest,flag],cwd=folder,capture_output=True,text=True)
                assert run.returncode!=0 and 'public execution defaults false' in run.stderr,run.stderr
                denied+=1
    provenance=json.loads((ROOT/'H_resume_source_delta.json').read_text())
    for row in provenance['files']:
        path=ROOT/Path(row['public_path']).name
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['public_sha256']
        compile(path.read_bytes(),str(path),'exec')
        assert all(x not in path.read_text() for x in ('/Users/','/home/user','/data/SpecGPT'))
    print(json.dumps(dict(status='PUBLIC_H_RESUME_IDENTITYFREE_PASS',compiled_source_files=3,
        default_deny_attempts=denied,direct_import_no_D_fallback=True,pure_state_machine=True,
        real_helper_calls=0,model_calls=0,score_calls=0,actual_resume_executions=0)))
if __name__=='__main__':main()
