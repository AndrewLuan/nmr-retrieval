# 功能概述：conditional4公开副本隔离合成回归，不是实际分段完成验收。
# 关系：临时runtime与四源SHA闭包、原30测试、child配置与defaultdeny；不读真实制品。
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    bindings={}
    for path in [ROOT/"templates/runtime_manifest.example.json"]+list((ROOT/"templates").glob("*runtime*bindings.example.json")):
        value=json.loads(path.read_text());bindings.update({k:(1 if "count" in k else "a"*64) for k in value.get("bindings",{})})
        for key,name in value.get("public_source_binding_targets",{}).items():bindings[key]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    names=("TEST_STAGE_B_completion.py","TEST_STAGE_B_completion_supervisor.py","TEST_STAGE_B_completion_report.py","TEST_STAGE_B_completion_tests.py")
    bindings.update({"conditional_completion.public_source_sha256":{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},"conditional_completion.public_caller_sha256":hashlib.sha256((ROOT/"TEST_STAGE_B_C_caller.py").read_bytes()).hexdigest(),"conditional_completion.public_supervisor_sha256":hashlib.sha256((ROOT/"TEST_STAGE_B_phase_supervisor.py").read_bytes()).hexdigest(),"conditional_completion.public_report_sha256":hashlib.sha256((ROOT/"TEST_STAGE_B_report.py").read_bytes()).hexdigest()})
    bindings.update(json.loads((ROOT/"templates/conditional_completion_runtime_bindings.example.json").read_text())["bindings"])
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"runtime.json";config=dict(schema="portable_assignment_runtime_v1",execution_authorized=True,workspace=folder,bindings=bindings)
        environment=dict(os.environ);environment.pop("PYTHONPATH",None)
        def run(code):
            path.write_text(json.dumps(config));sha=hashlib.sha256(path.read_bytes()).hexdigest()
            return subprocess.run([sys.executable,"-I","-B","-c",code,str(ROOT),str(path),sha],cwd=folder,env=environment,capture_output=True,text=True,timeout=30)
        setup='import sys;sys.path.insert(0,sys.argv[1]);sys.argv=["synthetic","--runtime-manifest",sys.argv[2],"--runtime-manifest-sha256",sys.argv[3]];'
        probe=run(setup+"import unittest,TEST_STAGE_B_completion_tests as t;r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(t));assert r.wasSuccessful();assert r.testsRun==30")
        assert probe.returncode==0,(probe.stdout,probe.stderr)
        for name in names[:3]:
            probe=run(setup+"import importlib;m=importlib.import_module("+repr(name[:-3])+");m.main()")
            assert probe.returncode==0,(name,probe.stdout,probe.stderr)
        config["execution_authorized"]=False
        probe=run(setup+"import TEST_STAGE_B_completion as c;c.partition([],[],set())")
        assert probe.returncode!=0 and "defaults false" in probe.stderr,probe.stderr
        config["execution_authorized"]=True
        probe=run(setup+'import TEST_STAGE_B_completion as c,portable_runtime as r;r._CONFIG["execution_authorized"]=False;c.partition([],[],set())')
        assert probe.returncode!=0 and "requires execution_authorized" in probe.stderr,probe.stderr
        config["bindings"]["conditional_completion.public_source_sha256"]={}
        probe=run(setup+"import TEST_STAGE_B_completion as c;c.partition([],[],set())")
        assert probe.returncode!=0 and "four-source binding required" in probe.stderr,probe.stderr
    print(json.dumps(dict(status="CONDITIONAL_PUBLIC_SOURCE_ONLY_PASS",metadata_tests=30,isolated_import=True,default_deny=True,helper_deny=True,incomplete_source_closure_rejected=True,real_terminal_read=False,actual_segment=False,models=0,scientific_scores=0)))
if __name__=="__main__":main()
