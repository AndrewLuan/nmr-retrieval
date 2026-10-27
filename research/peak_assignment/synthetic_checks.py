# 功能概述：无私有D依赖的公开源码接口验证；不运行真实模型/求解/数据。
# main编译allowlist，核源码SHA/脱敏，执行两个pure模块合成接口，并测试默认拒绝授权。
# 输入仅公开源码/模板；输出stdout小JSON，失败抛异常；不写科学receipt或修改原数据。
import importlib.util,json,hashlib,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def relocation_checks():
    """仅测模式门禁和外部制品路径；临时合成文件不含真实科学数据。"""
    import portable_runtime as runtime
    template=json.loads((ROOT/'templates/runtime_manifest.example.json').read_text())
    old=sys.argv[:]
    denied=[]
    with tempfile.TemporaryDirectory() as td:
        outside=Path(td)/'external-artifacts';outside.mkdir()
        template['workspace']=str(outside)
        p=Path(td)/'runtime.json';p.write_text(json.dumps(template))
        prefix=['synthetic','--runtime-manifest',str(p),'--runtime-manifest-sha256',hashlib.sha256(p.read_bytes()).hexdigest()]
        try:
            for flags in (['--execute'],['--execute','--checkonly'],['--execute','--check-only'],
                          ['--execute','--self-test'],['--execute','--help'],['--aggregate','--validate-only'],
                          ['--help'],['--self-test'],['--checkonly'],['--check-only'],['--validate-only']):
                sys.argv=prefix+flags;runtime._CONFIG=None
                try:runtime._config()
                except ValueError:denied.append(flags)
                else:raise AssertionError('mixed/default execution admitted: '+str(flags))
            import subprocess
            for entry in ('prepare_H_reference_inputs.py','verify_C_frozen_cache_artifacts.py'):
                for flag in ('--help','--self-test'):
                    attempt=subprocess.run([sys.executable,'-B',str(ROOT/entry)]+prefix[1:]+[flag],capture_output=True,text=True)
                    assert attempt.returncode!=0 and 'public execution defaults false' in attempt.stderr
            # 与生产无关的临时dummy manifest显式授权，仅含临时路径；纯合成不借flag绕授权。
            template['execution_authorized']=True
            p.write_text(json.dumps(template))
            prefix=['synthetic','--runtime-manifest',str(p),'--runtime-manifest-sha256',hashlib.sha256(p.read_bytes()).hexdigest()]
            # 两个verifier只检查缺件PENDING与外部根，不制造完整交付PASS。
            for name in ('verify_assignment_complete','verify_source_relative_delivery'):
                runtime._CONFIG=None;sys.argv=prefix+['--check-only']
                module=load(name)
                assert module.ROOT==outside and module.ROOT!=ROOT
                probe=outside/'synthetic_probe.json';probe.write_text('{"synthetic":true}')
                assert runtime.artifact_path('synthetic_probe.json').read_text()=='{"synthetic":true}'
                assert not (ROOT/'synthetic_probe.json').exists()
                assert module.main()==2  # 缺独立交付证据仍PENDING，不制造PASS。
        finally:sys.argv=old;runtime._CONFIG=None
    return dict(status='RELOCATION_DELTA_SYNTHETIC_PASS',denied_modes=denied,external_verifier_roots=2,
        external_artifact_probe_read=True,missing_evidence_pending_preserved=True,parserless_flag_attempts_rejected=4,
        real_data_reads=0,scientific_entrypoints_executed=0)

def main():
    if '--relocation-only' in sys.argv:
        print(json.dumps(relocation_checks()));return
    inventory=json.loads((ROOT/'source_manifest.json').read_text())
    for row in inventory['files']:
        p=ROOT/Path(row['public_path']).name;raw=p.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==row['public_sha256']
        compile(raw,str(p),'exec')
        assert all(x not in raw.decode() for x in ('/Users/','/home/user','/data/SpecGPT'))
    adapter=load('assignment_evaluation_adapter').synthetic_checks()
    estimator=load('frozen_report_estimators').synthetic_checks()
    import portable_runtime as runtime
    template=json.loads((ROOT/'templates/runtime_manifest.example.json').read_text())
    assert template['execution_authorized'] is False
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'runtime.json';p.write_text(json.dumps(template));old=sys.argv[:]
        sys.argv=['synthetic','--runtime-manifest',str(p),'--runtime-manifest-sha256',hashlib.sha256(p.read_bytes()).hexdigest(),'--execute']
        try:
            try:runtime._config()
            except ValueError:pass
            else:raise AssertionError('default authorization admitted')
        finally:sys.argv=old;runtime._CONFIG=None
    import subprocess
    additive=[]
    for name in ('H_resume_synthetic_checks.py','H_parent_A_synthetic_checks.py','Stage_B_synthetic_checks.py','finite_delivery_synthetic_checks.py','conditional_completion_synthetic_checks.py'):
        run=subprocess.run([sys.executable,'-B',str(ROOT/name)],capture_output=True,text=True)
        assert run.returncode==0,(name,run.stdout,run.stderr)
        additive.append(dict(script=name,actual_exit=run.returncode,stdout=run.stdout))
    print(json.dumps(dict(status='PUBLIC_SYNTHETIC_INTERFACE_PASS',source_files=len(inventory['files']),additive=additive,adapter=adapter,estimator=estimator,real_rows_read=0,model_loads=0,real_batch_solves=0)))
if __name__=='__main__':main()
