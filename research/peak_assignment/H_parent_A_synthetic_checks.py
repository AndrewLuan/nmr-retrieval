# 功能概述：已审H父科学依赖与A公开入口的无私有数据导入/授权/metadata检查。
# main隔离导入公开H父链、resume、A producer；仅检验纯结构标签和空policy控制schema函数。
# 使用临时自足dummy授权绑定；falseauth CLI必须拒绝；不调用helper处理/模型/求解/评分/A。
import json,hashlib,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    bindings={}
    for name in ('H_resume_runtime_bindings.example.json','H_parent_A_runtime_bindings.example.json'):
        t=json.loads((ROOT/'templates'/name).read_text());assert t['execution_authorized'] is False
        bindings.update({k:(1 if 'count' in k else 'a'*64) for k in t['bindings']})
    with tempfile.TemporaryDirectory() as td:
        folder=Path(td);mp=folder/'dummy.json';config=dict(schema='portable_assignment_runtime_v1',execution_authorized=True,workspace=str(folder),bindings=bindings)
        mp.write_text(json.dumps(config));digest=hashlib.sha256(mp.read_bytes()).hexdigest()
        code="""import sys,importlib,json
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root));sys.argv=['synthetic','--runtime-manifest',sys.argv[2],'--runtime-manifest-sha256',sys.argv[3]]
names=('postprocessing_control_primitives','supervise_frozen_postprocessing','run_frozen_H_postprocessing_batch','frozen_reference_postprocessor','summarize_frozen_diagnostics','resume_frozen_H_postprocessing_batch','supervise_frozen_H_postprocessing_resume','TEST_STAGE_A_fixed_test_outer','TEST_STAGE_A_C_reference_rule_producer')
mods={n:importlib.import_module(n) for n in names}
assert all(Path(m.__file__).resolve().parent==root for m in mods.values())
assert mods['supervise_frozen_postprocessing'].bound is mods['postprocessing_control_primitives'].bound
assert mods['run_frozen_H_postprocessing_batch'].EXPECTED_BUDGET==mods['supervise_frozen_postprocessing'].EXPECTED_BUDGET
assert mods['supervise_frozen_postprocessing'].EXPECTED_BUDGET['total_wall_seconds']==900
outer=mods['TEST_STAGE_A_fixed_test_outer']
good=dict(status='unavailable',scope='C_nucleus_correct_established_conflicts_registry',exhaustive_audit_claim=False,H_corrections_imported=False,conflicts=[])
assert outer.validate_C_control_metadata(b'',good)['conflict_free_claim'] is False
for key in good:
 bad=dict(good);bad.pop(key)
 try:outer.validate_C_control_metadata(b'',bad)
 except ValueError:pass
 else:raise AssertionError('missing schema field admitted')
for key in ('exhaustive_audit_claim','H_corrections_imported'):
 bad=dict(good);bad[key]=0
 try:outer.validate_C_control_metadata(b'',bad)
 except ValueError:pass
 else:raise AssertionError('bool0 admitted')
print('PASS_PUBLIC_H_PARENT_RESUME_A_DIRECT_IMPORTS_AND_METADATA_SCHEMA')
"""
        run=subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT),str(mp),digest],cwd=folder,capture_output=True,text=True)
        assert run.returncode==0,(run.stdout,run.stderr)
        config['execution_authorized']=False;mp.write_text(json.dumps(config));digest=hashlib.sha256(mp.read_bytes()).hexdigest();denied=0
        for n in ('run_frozen_H_postprocessing_batch.py','supervise_frozen_postprocessing.py','summarize_frozen_diagnostics.py','TEST_STAGE_A_fixed_test_outer.py','TEST_STAGE_A_C_reference_rule_producer.py'):
            run=subprocess.run([sys.executable,'-I','-B','-c',"import sys,runpy;sys.path.insert(0,sys.argv[1]);p=sys.argv[2];sys.argv=sys.argv[2:];runpy.run_path(p,run_name='__main__')",str(ROOT),str(ROOT/n),'--runtime-manifest',str(mp),'--runtime-manifest-sha256',digest,'--help'],cwd=folder,capture_output=True,text=True)
            assert run.returncode!=0 and 'public execution defaults false' in run.stderr,(n,run.stderr)
            denied+=1
    delta=json.loads((ROOT/'H_parent_A_source_delta.json').read_text())
    for item in delta['files']:
        p=ROOT/Path(item['public_path']).name
        assert hashlib.sha256(p.read_bytes()).hexdigest()==item['public_sha256']
        compile(p.read_bytes(),str(p),'exec')
        assert all(x not in p.read_text() for x in ('/Users/','/home/user','/data/SpecGPT'))
    print(json.dumps(dict(status='PUBLIC_H_PARENT_A_IDENTITYFREE_PASS',source_files=6,direct_import_modules=9,default_deny_cli_attempts=denied,
        pure_metadata_schema_missing_and_bool_mutations_rejected=True,real_helper_calls=0,models=0,scores=0,A_executions=0,private_artifacts_read=0)))
if __name__=='__main__':main()
