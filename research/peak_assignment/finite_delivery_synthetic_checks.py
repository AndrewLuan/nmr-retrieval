# 功能概述：finite公开入口的隔离合成控制元数据验证，非actual验收。
# 关系：临时runtime精确绑定源码/schema；复用23个identityfree真实字段形状反例；无数据/模型。
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    source=ROOT/"verify_source_relative_finite_delivery.py"
    bindings={"finite_verifier.public_source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"finite_verifier.schema_sha256":hashlib.sha256((ROOT/"source_relative_delivery_finite_schema.json").read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"runtime.json"
        config=dict(schema="portable_assignment_runtime_v1",execution_authorized=True,workspace=folder,bindings=bindings)
        env=dict(os.environ);env.pop("PYTHONPATH",None)
        def run(code):
            path.write_text(json.dumps(config));sha=hashlib.sha256(path.read_bytes()).hexdigest()
            return subprocess.run([sys.executable,"-I","-B","-c",code,str(ROOT),str(path),sha],cwd=folder,env=env,capture_output=True,text=True,timeout=30)
        setup='import sys;sys.path.insert(0,sys.argv[1]);sys.argv=["synthetic","--runtime-manifest",sys.argv[2],"--runtime-manifest-sha256",sys.argv[3]];'
        code=setup+"import unittest,verify_source_relative_finite_delivery as v,test_public_source_relative_finite as t;assert v.main()==2;r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(t));assert r.wasSuccessful();assert r.testsRun==23"
        r=run(code);assert r.returncode==0,(r.stdout,r.stderr)
        config["execution_authorized"]=False
        r=run(setup+"import verify_source_relative_finite_delivery as v;v.verify_test({})")
        assert r.returncode!=0 and "defaults false" in r.stderr,r.stderr
        config["execution_authorized"]=True;config["bindings"]["finite_verifier.public_source_sha256"]="0"*64
        r=run(setup+"import verify_source_relative_finite_delivery as v;v.verify_coverage({})")
        assert r.returncode!=0 and "binding mismatch" in r.stderr,r.stderr
        config["bindings"]=bindings.copy();config["bindings"]["finite_verifier.public_source_sha256"]=hashlib.sha256(source.read_bytes()).hexdigest()
        r=run(setup+'import verify_source_relative_finite_delivery as v,portable_runtime as runtime;runtime._CONFIG["execution_authorized"]=False;v.bound({})')
        assert r.returncode!=0 and "requires execution_authorized" in r.stderr,r.stderr
    print(json.dumps(dict(status="FINITE_PUBLIC_SYNTHETIC_ONLY_PASS",metadata_tests=23,isolated_temp_CWD=True,default_deny=True,helper_deny=True,source_binding_drift_rejected=True,actual_acceptance=False,models=0,actual_data_reads=0)))
if __name__=="__main__":main()
