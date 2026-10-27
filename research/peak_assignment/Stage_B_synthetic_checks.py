# 功能概述：公开B六入口与支持源码的隔离导入、child配置传递、默认拒绝、compile/privacy检查。
# main只构临时dummy runtime及一份空子进程，不读真实test/模型/phase制品，不运行生产gate。
# canonical_argv仅测试参数接线；原科学gate回归源码保留断言，不在本检查启动监督器或求解。
import json,hashlib,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    bindings={}
    for p in [ROOT/'templates/runtime_manifest.example.json']+list((ROOT/'templates').glob('*runtime*bindings.example.json')):
        t=json.loads(p.read_text());assert t['execution_authorized'] is False
        bindings.update({k:(1 if 'count' in k else 'a'*64) for k in t['bindings']})
        for key,name in t.get('public_source_binding_targets',{}).items():
            bindings[key]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as td:
        folder=Path(td);mp=folder/'runtime.json';config=dict(schema='portable_assignment_runtime_v1',execution_authorized=True,workspace=str(folder),bindings=bindings)
        mp.write_text(json.dumps(config));digest=hashlib.sha256(mp.read_bytes()).hexdigest()
        code="""import sys,json,importlib,hashlib,subprocess,ast
from pathlib import Path
root=Path(sys.argv[1]).resolve();manifest=sys.argv[2];digest=sys.argv[3];sys.path.insert(0,str(root))
sys.argv=['synthetic','--runtime-manifest',manifest,'--runtime-manifest-sha256',digest]
def audit(event,args):
 if event=='import' and (str(args[0])=='torch' or str(args[0]).startswith(('torch.','nmr_transfer'))):raise RuntimeError('MODEL_IMPORT_FORBIDDEN')
sys.addaudithook(audit)
names=('TEST_STAGE_B_control','TEST_STAGE_B_execution_contract','TEST_STAGE_B_phase_supervisor','TEST_STAGE_B_package','TEST_STAGE_B_C_caller','TEST_STAGE_B_report','build_frozen_prediction_cache','prepare_C_scoring_artifacts','run_frozen_C_assignment_baselines','assignment_evaluation_adapter','frozen_report_estimators','TEST_STAGE_B_tests','TEST_STAGE_B_execution_tests','TEST_STAGE_B_EXECUTION_FOUR_GATES_regression','TEST_STAGE_B_CAL_RULE_IO_regression','TEST_STAGE_B_REPORT_P1_regression')
mods={n:importlib.import_module(n) for n in names}
assert all(Path(m.__file__).resolve().parent==root for m in mods.values())
import portable_stage_runtime as runtime
child=[sys.executable,'-I','-B','-c',"import sys,hashlib,json;from pathlib import Path;p=Path(sys.argv[sys.argv.index('--runtime-manifest')+1]);h=sys.argv[sys.argv.index('--runtime-manifest-sha256')+1];assert hashlib.sha256(p.read_bytes()).hexdigest()==h;assert json.loads(p.read_text())['execution_authorized'] is True;print('DUMMY_CHILD_SAME_RUNTIME')"]
child=runtime.with_runtime(child);run=subprocess.run(child,capture_output=True,text=True);assert run.returncode==0 and 'DUMMY_CHILD_SAME_RUNTIME' in run.stdout
assert runtime.with_runtime(child)==child
bad=child[:];bad[bad.index('--runtime-manifest-sha256')+1]='b'*64
try:runtime.with_runtime(bad)
except ValueError:pass
else:raise AssertionError('child runtime substitution admitted')
contract=mods['TEST_STAGE_B_execution_contract'];entry=root/'TEST_STAGE_B_package.py'
config=dict(python_executable=sys.executable,entrypoint=dict(path=str(entry),sha256=hashlib.sha256(entry.read_bytes()).hexdigest()),delegate_plan=dict(path='/synthetic/delegate.json',sha256='d'*64),delegate_owner_release=dict(path='/synthetic/release.json',sha256='e'*64))
argv=contract.canonical_argv('package',config,dict(path='/synthetic/config.json',sha256='f'*64));assert argv[-4:]==runtime.RUNTIME_ARGUMENTS and '--execute' in argv
source=ast.parse((root/'TEST_STAGE_B_phase_supervisor.py').read_text());calls=[n for n in ast.walk(source) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='subprocess' and n.func.attr=='Popen'];assert calls and all(isinstance(n.args[0],ast.Call) and isinstance(n.args[0].func,ast.Name) and n.args[0].func.id=='with_runtime' for n in calls)
assert not any(k=='torch' or k.startswith(('torch.','nmr_transfer')) for k in sys.modules)
print('PASS_PUBLIC_B_IMPORTS_CHILD_RUNTIME_NO_MODELS')
"""
        run=subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT),str(mp),digest],cwd=folder,capture_output=True,text=True,timeout=30)
        assert run.returncode==0,(run.stdout,run.stderr)
        # 外部workspace不复制builder；真实进程清除PYTHONPATH，10秒只覆盖启动/解析与退出。
        import os, ast
        environment=dict(os.environ);environment.pop("PYTHONPATH",None)
        builder=ROOT/"build_frozen_prediction_cache.py"
        prepared={"builder":{"path":str(builder),"sha256":hashlib.sha256(builder.read_bytes()).hexdigest()}}
        prepared_path=folder/"prepared_config.json";prepared_path.write_text(json.dumps(prepared))
        selected=json.loads(prepared_path.read_text())["builder"]
        assert Path(selected["path"]).parent==ROOT and not (folder/builder.name).exists()
        args=[sys.executable,"-B",selected["path"],"--runtime-manifest",str(mp),"--runtime-manifest-sha256",digest,"--help"]
        probe=subprocess.run(args,cwd=folder,env=environment,capture_output=True,text=True,timeout=10)
        assert probe.returncode==0 and "--assets-manifest" in probe.stdout,(probe.stdout,probe.stderr)
        probe=subprocess.run([sys.executable,"-B",str(ROOT/"TEST_STAGE_B_control.py"),"--runtime-manifest",str(mp),"--runtime-manifest-sha256",digest,"--check-only"],cwd=folder,env=environment,capture_output=True,text=True,timeout=10)
        assert probe.returncode==0 and "TEST_STAGE_B_interface_contract_v1" in probe.stdout,(probe.stdout,probe.stderr)
        source=ast.parse((ROOT/"TEST_STAGE_B_execution_contract.py").read_text())
        prepare=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=="prepare_prediction")
        assert "builder=item(builder)" in ast.unparse(prepare).replace(" ","")
        assert "copyfile(builder" not in ast.unparse(prepare).replace(" ","")
        config['execution_authorized']=False;mp.write_text(json.dumps(config));digest=hashlib.sha256(mp.read_bytes()).hexdigest();denied=0
        for n in ('build_frozen_prediction_cache','TEST_STAGE_B_control','TEST_STAGE_B_execution_contract','TEST_STAGE_B_phase_supervisor','TEST_STAGE_B_package','TEST_STAGE_B_C_caller','TEST_STAGE_B_report'):
            run=subprocess.run([sys.executable,'-I','-B','-c',"import sys,runpy;sys.path.insert(0,sys.argv[1]);p=sys.argv[2];sys.argv=sys.argv[2:];runpy.run_path(p,run_name='__main__')",str(ROOT),str(ROOT/(n+'.py')),'--runtime-manifest',str(mp),'--runtime-manifest-sha256',digest,'--help'],cwd=folder,capture_output=True,text=True,timeout=30)
            assert run.returncode!=0 and 'public execution defaults false' in run.stderr,(n,run.stderr)
            denied+=1
    delta=json.loads((ROOT/'Stage_B_source_delta.json').read_text())
    for row in delta['files']:
        p=ROOT/Path(row['public_path']).name
        assert hashlib.sha256(p.read_bytes()).hexdigest()==row['public_sha256']
        compile(p.read_bytes(),str(p),'exec')
        assert all(x not in p.read_text() for x in ('/Users/','/home/user','/data/SpecGPT'))
    print(json.dumps(dict(status='PUBLIC_B_IDENTITYFREE_PASS',isolated_direct_import_modules=16,source_and_regression_files_compiled=11,
        default_deny_CLI_attempts=denied,actual_dummy_child_runtime_binding=True,phase_worker_runtime_AST_check=True,
        real_phase_executions=0,real_test_values_read=0,model_loads=0,solver_calls=0,score_calls=0)))
if __name__=='__main__':main()
