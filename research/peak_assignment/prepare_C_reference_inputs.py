# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：先生成C身份提取计划；独立batch release后才冻结全部原native-val原行。\nREMOTE逐行hash原文件并只解析顶层身份标量；原80/10/10分区不变，val原行仅写hidden，\ntrain/test只输出身份与原行SHA，绝不输出其targets/mask/spectrum/条件或label值。\nC政策按nucleus隔离，H-only/缺政策记unknown，不推断自动准入。graph_snapshot复用\nsource_transport字段与AddHs(canonical)配方，记录JJ RDKit版本供跨环境比对，不作gold证明。\nmain默认--check-only/--plan只读小证据文件并打印计划，不SSH、不读真实源、不构造gold。\n--execute另需专门全val提取release；原16C probe release不扩大为整批运行授权。\n关系：遵循carbon_identity_reconstruction_astra原规则，核验historical/current data.py SHA。\n资源：远端CPU2、GPU0、RSS2GiB、wall120s；无模型/训练/assignment/test评价/自动重试/Git。\n输出：新目录identity_ledger.jsonl、policy_availability.jsonl、hidden/C_native_val_raw_rows.jsonl、\nval_graph_snapshots.jsonl及manifest/执行receipt。exact cache/training row membership始终unknown。\n'
import argparse, base64, hashlib, json, shlex, subprocess, time
from pathlib import Path
D = workspace()
RAW_SHA = binding('prepare_C_reference_inputs.sha_or_identity.1')
PROOF_SHA = binding('prepare_C_reference_inputs.sha_or_identity.2')
POLICY_SHA = binding('prepare_C_reference_inputs.sha_or_identity.3')
DATA_SHA = binding('prepare_C_reference_inputs.sha_or_identity.4')
REMOTE = render('\nimport os,time,signal,resource,sys,json,hashlib\nfrom pathlib import Path\nstarted=time.monotonic()\nos.environ.update(CUDA_VISIBLE_DEVICES="",OMP_NUM_THREADS="2",MKL_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2")\nresource.setrlimit(resource.RLIMIT_CPU,(115,115))\ntry:os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])\nexcept AttributeError:pass\ndef guard(*_):\n if time.monotonic()-started>120:raise TimeoutError("metadata_wall_limit")\n if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024>2147483648:raise MemoryError("metadata_RSS_limit")\nsignal.signal(signal.SIGALRM,guard);signal.setitimer(signal.ITIMER_REAL,.1,.1)\nfrom rdkit import Chem,rdBase,RDLogger\nRDLogger.DisableLog("rdApp.warning")\nrequest=json.load(sys.stdin)\ndef sha(path):\n h=hashlib.sha256()\n with open(path,"rb") as f:\n  for b in iter(lambda:f.read(1048576),b""):h.update(b)\n return h.hexdigest()\ndef emit(value):print(json.dumps(value,ensure_ascii=False),flush=True)\ndef end_value(text,start):\n depth=0;string=False;escape=False;i=start\n while i<len(text):\n  ch=text[i]\n  if string:\n   if escape:escape=False\n   elif ch=="\\\\":escape=True\n   elif ch==\'"\':string=False\n  else:\n   if ch==\'"\':string=True\n   elif ch in "[{":depth+=1\n   elif ch in "]}":\n    if depth==0:return i\n    depth-=1\n   elif ch=="," and depth==0:return i\n  i+=1\n return i\ndef metadata(line,keys):\n text=line.decode("utf-8");i=0;out={}\n while i<len(text) and text[i].isspace():i+=1\n if i>=len(text) or text[i]!="{":raise ValueError("top_level_JSON_object_required")\n i+=1;decoder=json.JSONDecoder()\n while i<len(text):\n  while i<len(text) and (text[i].isspace() or text[i]==","):i+=1\n  if i>=len(text) or text[i]=="}":break\n  key,j=decoder.raw_decode(text,i)\n  if not isinstance(key,str):raise ValueError("JSON_key_not_string")\n  i=j\n  while i<len(text) and text[i].isspace():i+=1\n  if text[i]!=":":raise ValueError("JSON_colon")\n  i+=1\n  while i<len(text) and text[i].isspace():i+=1\n  j=end_value(text,i)\n  if key in keys:\n   if key in out:raise ValueError("duplicate_metadata_key")\n   value=json.loads(text[i:j])\n   if value is not None and not isinstance(value,(str,int,float,bool)):raise ValueError("identity_metadata_scalar_required")\n   out[key]=value\n  i=j\n return out\ndef graph_snapshot(mol):\n return dict(atoms=[dict(index=a.GetIdx(),z=a.GetAtomicNum(),isotope=a.GetIsotope(),charge=a.GetFormalCharge(),radicals=a.GetNumRadicalElectrons(),aromatic=a.GetIsAromatic(),chiral_tag=str(a.GetChiralTag())) for a in mol.GetAtoms()],\n  bonds=[dict(a=b.GetBeginAtomIdx(),b=b.GetEndAtomIdx(),kind=str(b.GetBondType()),aromatic=b.GetIsAromatic(),stereo=str(b.GetStereo()),stereo_atoms=list(b.GetStereoAtoms())) for b in mol.GetBonds()])\nraw=Path("@@prepare_C_reference_inputs.embedded_path.8@@")\npolicy=Path("@@prepare_C_reference_inputs.embedded_path.7@@")\nhistory=Path("@@prepare_C_reference_inputs.embedded_path.6@@")\ncurrent=Path("@@prepare_C_reference_inputs.embedded_path.5@@")\nfor p in (history,current):\n if sha(p)!=request["data_sha256"]:raise ValueError("historical_current_identity_source_SHA")\nraw_before=sha(raw);policy_before=sha(policy)\nif raw_before!=request["raw_sha256"] or policy_before!=request["policy_sha256"]:raise ValueError("source_pre_SHA")\nexisting={(r["source"],r["record_id"]):r for r in request.get("existing_C_identities",[])}\ncounts={};seen=set();identity_rows=[];stream=hashlib.sha256();val_count=0;invalid=0\nfor lineno,line in enumerate(raw.open("rb"),1):\n stream.update(line)\n fields=metadata(line,{"source_ref","record_id","nucleus","smiles","structure_id","connectivity_sha256","native_legacy_hash_partition"})\n if fields.get("nucleus")!="13C":continue\n source=fields.get("source_ref");rid=fields.get("record_id");smi=fields.get("smiles")\n if not isinstance(source,str) or not isinstance(rid,str) or not isinstance(smi,str):raise ValueError("C_identity_required")\n key=(source,rid)\n if key in seen:raise ValueError("duplicate_C_identity_no_replacement")\n seen.add(key)\n item=dict(source=source,record_id=rid,nucleus="13C",source_line=lineno,raw_line_sha256=hashlib.sha256(line).hexdigest(),raw_smiles=smi,original_cache_row_membership="unknown")\n mol=Chem.MolFromSmiles(smi)\n if mol is None:\n  invalid+=1;item.update(status="invalid_identity_retained",historical_partition=None,reasons=["invalid_smiles"])\n  identity_rows.append(item);emit(dict(kind="identity",**item));continue\n mol=Chem.RemoveHs(mol);exact=Chem.MolToSmiles(mol,isomericSmiles=True);plain=Chem.MolToSmiles(mol,isomericSmiles=False)\n if "." in plain:\n  invalid+=1;item.update(status="invalid_identity_retained",historical_partition=None,reasons=["multicomponent_structure"])\n  identity_rows.append(item);emit(dict(kind="identity",**item));continue\n group=hashlib.sha256(plain.encode()).hexdigest();bucket=int(group[:8],16)%100\n partition="train" if bucket<80 else "val" if bucket<90 else "test"\n prior=existing.get(key,{})\n for present,want,label in ((fields.get("connectivity_sha256"),group,"stored_group"),(fields.get("native_legacy_hash_partition"),partition,"stored_partition"),(prior.get("connectivity_sha256"),group,"prior_group"),(prior.get("native_legacy_hash_partition"),partition,"prior_partition"),(prior.get("exact_smiles"),exact,"prior_exact")):\n  if present is not None and present!=want:raise ValueError(label+"_conflict")\n counts[partition]=counts.get(partition,0)+1\n item.update(status="identity_frozen",exact_smiles=exact,connectivity_sha256=group,historical_partition=partition,mod100_first8=bucket,role="original_native_C_"+partition+"_partition_candidate",exact_training_row_exposure="unknown",policy_admission="unknown")\n identity_rows.append(item);emit(dict(kind="identity",**item))\n if partition=="val":\n  # 原行不解析为label对象；只在已确定val后输出至hidden，不构造gold。\n  import base64\n  emit(dict(kind="val_raw",source=source,record_id=rid,line=lineno,raw_line_sha256=item["raw_line_sha256"],raw_b64=base64.b64encode(line).decode()))\n  full=Chem.AddHs(Chem.MolFromSmiles(exact));snapshot=graph_snapshot(full)\n  emit(dict(kind="val_graph",source=source,record_id=rid,exact_smiles=exact,rdkit_version=rdBase.rdkitVersion,recipe="AddHs(MolFromSmiles(canonical_isomeric_heavy_SMILES))",graph_snapshot=snapshot,graph_snapshot_sha256=hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()))\n  val_count+=1\npolicy_stream=hashlib.sha256();policy_nuclei={};explicit_C={}\nfor lineno,line in enumerate(policy.open("rb"),1):\n policy_stream.update(line)\n row=metadata(line,{"source","record_id","nucleus"})\n declared=row.get("nucleus") or "unspecified_not_C_evidence";policy_nuclei[declared]=policy_nuclei.get(declared,0)+1\n if declared=="13C":\n  explicit_C.setdefault((row.get("source"),row.get("record_id")),[]).append(dict(line=lineno,line_sha256=hashlib.sha256(line).hexdigest()))\nfor item in identity_rows:\n policy_refs=explicit_C.get((item["source"],item["record_id"]),[])\n emit(dict(kind="policy_availability",source=item["source"],record_id=item["record_id"],nucleus="13C",historical_partition=item["historical_partition"],policy_status="candidate_explicit_C_policy_requires_separate_audit" if policy_refs else "unknown_no_nucleus_valid_C_policy",policy_admitted=None,policy_evidence=policy_refs,available_policy_source=str(policy),available_policy_source_sha256=request["policy_sha256"],H_policy_not_reused=True))\nraw_after=sha(raw);policy_after=sha(policy)\nif not raw_before==stream.hexdigest()==raw_after==request["raw_sha256"]:raise ValueError("raw_full_pre_stream_post_SHA")\nif not policy_before==policy_stream.hexdigest()==policy_after==request["policy_sha256"]:raise ValueError("policy_full_pre_stream_post_SHA")\nguard();signal.setitimer(signal.ITIMER_REAL,0)\nemit(dict(kind="receipt",status="C_VAL_SOURCE_ROWS_FROZEN_NO_GOLD",raw_before=raw_before,raw_stream=stream.hexdigest(),raw_after=raw_after,policy_before=policy_before,policy_stream=policy_stream.hexdigest(),policy_after=policy_after,partition_counts=counts,invalid_identity_rows=invalid,val_raw_rows=val_count,identity_rows=len(seen),policy_declared_nucleus_counts=policy_nuclei,rdkit_version=rdBase.rdkitVersion,historical_RDKit_version="unknown",historical_identity_implementation_sha256=request["data_sha256"],elapsed_seconds=time.monotonic()-started,peak_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,CPU_threads=2,GPU_devices=0,model_loads=0,model_forwards=0,train_test_target_fields_decoded=False,train_test_values_emitted=False,new_split=False,gold_constructed=False))\n')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def plan():
    proof = artifact_path('reviews/carbon_identity_reconstruction_astra.json')
    probe = artifact_path('scientific_carbon_probe_release.json')
    if sha(proof) != PROOF_SHA:
        raise ValueError('C_identity_proof_SHA')
    release = json.loads(probe.read_text())
    if release['identity_proof_sha256'] != PROOF_SHA or release['new_split'] is not False:
        raise ValueError('probe_release_identity_binding')
    return dict(schema='C_reference_extraction_plan_v1', status='CHECK_ONLY_NOT_EXECUTED', raw_sha256=RAW_SHA, policy_sha256=POLICY_SHA, data_sha256=DATA_SHA, identity_proof_sha256=PROOF_SHA, pilot_release_sha256=sha(probe), extraction_scope='all original native-val C raw rows hidden; train/test identities only; original first8hex mod100 partition', policy_absence_action='unknown_no_autopass', CPU_threads=2, GPU_devices=0, RSS_limit_bytes=2147483648, wall_seconds=120, execution_requires='separate C_reference_extraction_release_v1; existing16C probe release is not batch authorization', remote_script_sha256=hashlib.sha256(REMOTE.encode()).hexdigest(), model_loads=0, model_forwards=0, gold_constructed=False)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--check-only', action='store_true')
    p.add_argument('--plan', action='store_true')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--batch-release')
    p.add_argument('--batch-release-sha256')
    p.add_argument('--out')
    p.add_argument('--identity-ledger')
    p.add_argument('--identity-ledger-sha256')
    a = p.parse_args()
    request = plan()
    if not a.execute:
        print(json.dumps(request, indent=2))
        return 0
    if a.check_only or a.plan:
        raise ValueError('check_only_cannot_execute')
    if not all((a.batch_release, a.batch_release_sha256, a.out)):
        raise ValueError('separate_batch_release_and_out_required')
    if sha(a.batch_release) != a.batch_release_sha256:
        raise ValueError('batch_release_SHA')
    release = json.loads(Path(a.batch_release).read_text())
    expected = dict(schema='C_reference_extraction_release_v1', execution_authorized=True, source_sha256=RAW_SHA, identity_proof_sha256=PROOF_SHA, val_raw_extract=True, test_identity_only=True, train_identity_only=True, new_split=False, policy_absence_action='unknown_no_autopass')
    if any((release.get(k) != v for k, v in expected.items())):
        raise ValueError('batch_release_scope')
    if a.identity_ledger:
        if not a.identity_ledger_sha256 or sha(a.identity_ledger) != a.identity_ledger_sha256:
            raise ValueError('identity_ledger_SHA')
        previous = json.loads(Path(a.identity_ledger).read_text())
        request['existing_C_identities'] = [r for r in previous['matched_source_identity_rows'] if r['nucleus'] == '13C']
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'hidden').mkdir()
    (out / 'plan.json').write_text(json.dumps(request, indent=2))
    argv = ['ssh', binding('prepare_C_reference_inputs.ssh_host.9'), shlex.join([binding('prepare_C_reference_inputs.path.10'), '-c', REMOTE])]
    started = time.monotonic()
    result = subprocess.run(argv, input=json.dumps(request), text=True, capture_output=True, timeout=125)
    execution = dict(actual_exit=result.returncode, seconds=time.monotonic() - started, remote_script_sha256=request['remote_script_sha256'], batch_release_sha256=a.batch_release_sha256, stderr=result.stderr, automatic_retry=False)
    (out / 'execution.json').write_text(json.dumps(execution, indent=2))
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    artifacts = {}
    for kind, name in (('identity', 'identity_ledger.jsonl'), ('policy_availability', 'policy_availability.jsonl'), ('val_graph', 'val_graph_snapshots.jsonl')):
        path = out / name
        rows = [m for m in messages if m['kind'] == kind]
        with path.open('x') as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
        artifacts[kind] = dict(path=str(path), sha256=sha(path), rows=len(rows))
    path = out / 'hidden/C_native_val_raw_rows.jsonl'
    raws = [m for m in messages if m['kind'] == 'val_raw']
    with path.open('xb') as f:
        for row in raws:
            line = base64.b64decode(row['raw_b64'])
            if hashlib.sha256(line).hexdigest() != row['raw_line_sha256']:
                raise ValueError('extracted_line_SHA')
            f.write(line)
    artifacts['val_raw'] = dict(path=str(path), sha256=sha(path), rows=len(raws))
    receipts = [m for m in messages if m['kind'] == 'receipt']
    ok = result.returncode == 0 and len(receipts) == 1
    if ok:
        receipt = receipts[0]
        ok = all((receipt[k] == RAW_SHA for k in ('raw_before', 'raw_stream', 'raw_after'))) and all((receipt[k] == POLICY_SHA for k in ('policy_before', 'policy_stream', 'policy_after'))) and (receipt['peak_RSS_bytes'] <= 2147483648) and (receipt['elapsed_seconds'] <= 120) and (receipt['val_raw_rows'] == len(raws))
    manifest = dict(schema='C_reference_extraction_manifest_v1', status='C_VAL_RAW_AND_IDENTITY_FROZEN_NO_GOLD' if ok else 'FAILED_PARTIAL_NO_RETRY', plan_sha256=sha(out / 'plan.json'), batch_release_sha256=a.batch_release_sha256, artifacts=artifacts, remote_receipt=receipts[0] if receipts else None, execution=execution)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest))
    return 0 if ok else 1
if __name__ == '__main__':
    raise SystemExit(main())
