# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
import base64
import collections
import hashlib
import json
from pathlib import Path
import resource
import shlex
import subprocess
import time
D = workspace()
SOURCE_SHA = binding('prepare_H_reference_inputs.sha_or_identity.1')
POLICY_SHA = binding('prepare_H_reference_inputs.sha_or_identity.2')
REMOTE = render('\nimport sys,json,os,resource,time,hashlib,base64,re\nresource.setrlimit(resource.RLIMIT_CPU,(120,120))\nresource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))\ntry: os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])\nexcept AttributeError: pass\nfor name in ["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"]:os.environ[name]="2"\nfrom rdkit import Chem,rdBase\nstart=time.monotonic();plan=json.load(sys.stdin)\nsource="@@prepare_H_reference_inputs.embedded_path.4@@"\npolicy="@@prepare_H_reference_inputs.embedded_path.3@@"\nselected={(x["source"],x["nucleus"],x["record_id"]):x for x in plan["selected"]}\npairs={(k[0],k[2]) for k in selected}\ndef sha(p):\n h=hashlib.sha256()\n with open(p,"rb") as f:\n  for b in iter(lambda:f.read(1048576),b""):h.update(b)\n return h.hexdigest()\ndef emit(x): print(json.dumps(x),flush=True)\nsource_before=sha(source);policy_before=sha(policy)\nif source_before!=plan["source_sha256"] or policy_before!=plan["policy_sha256"]:raise ValueError("input hash mismatch")\npatterns={k:re.compile(rb\'"\'+k.encode()+rb\'"\\s*:\\s*("(?:[^"\\\\]|\\\\.)*")\') for k in ["source_ref","record_id","nucleus"]}\ncounts={}\nh=hashlib.sha256();raw_count=0\nfor lineno,line in enumerate(open(source,"rb"),1):\n h.update(line)\n ident={}\n for k,pat in patterns.items():\n  m=pat.search(line)\n  ident[k]=json.loads(m.group(1)) if m else None\n key=(ident["source_ref"],ident["nucleus"],ident["record_id"])\n if key not in selected:continue\n row=json.loads(line);expected=selected[key];reasons=[]\n mol=Chem.MolFromSmiles(row.get("smiles",""))\n exact=Chem.MolToSmiles(Chem.RemoveHs(mol),isomericSmiles=True) if mol is not None else None\n conn=Chem.MolToSmiles(Chem.RemoveHs(mol),isomericSmiles=False) if mol is not None else None\n group=hashlib.sha256(conn.encode()).hexdigest() if conn is not None else None\n if exact!=expected["exact_smiles"]:reasons.append("exact_structure_mismatch")\n if group!=expected["connectivity_sha256"]:reasons.append("connectivity_mismatch")\n if lineno!=expected["source_line"]:reasons.append("source_line_differs_or_duplicate")\n counts[key]=counts.get(key,0)+1;raw_count+=1\n emit(dict(kind="raw",key=list(key),line=lineno,raw_b64=base64.b64encode(line).decode(),\n  raw_line_sha256=hashlib.sha256(line).hexdigest(),exact_smiles=exact,connectivity_sha256=group,reasons=reasons))\npolicy_count=0;ph=hashlib.sha256()\nfor lineno,line in enumerate(open(policy,"rb"),1):\n ph.update(line);row=json.loads(line)\n if (row.get("source"),row.get("record_id")) not in pairs:continue\n policy_count+=1\n emit(dict(kind="policy",source=row["source"],record_id=row["record_id"],line=lineno,\n  raw_b64=base64.b64encode(line).decode(),line_sha256=hashlib.sha256(line).hexdigest()))\nsource_after=sha(source);policy_after=sha(policy)\nemit(dict(kind="receipt",source_before=source_before,source_stream=h.hexdigest(),source_after=source_after,\n policy_before=policy_before,policy_stream=ph.hexdigest(),policy_after=policy_after,\n raw_count=raw_count,policy_count=policy_count,\n duplicate_source_keys=[list(k) for k,n in counts.items() if n>1],\n missing_source_keys=[list(k) for k in selected if k not in counts],\n elapsed_seconds=time.monotonic()-start,max_RSS_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,\n cpu_seconds=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,\n rdkit_version=rdBase.rdkitVersion))\n')

def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()

def main():
    started = time.monotonic()
    identity_path = artifact_path('raw_frozen_identity_join.json')
    release_path = artifact_path('scientific_reference_release.json')
    identity = json.loads(identity_path.read_text())
    release = json.loads(release_path.read_text())
    assert release['admission_execution_allowed'] is True and release['reference_choice'] == 'raw'
    assert sha_bytes(identity_path.read_bytes()) == release['cohort_identity_source']['sha256']
    rows = identity['matched_source_identity_rows']
    blocked = {r['connectivity_sha256'] for r in rows if any((m.get('connectivity') for c, m in r['frozen_1H_cohort_membership'].items() if c.startswith('test') or c.startswith('historical_verify')))}
    ledger, selected = ([], [])
    for row in rows:
        if row['nucleus'] != '1H':
            continue
        membership = row['frozen_1H_cohort_membership']
        roles = []
        if membership.get('fixed_train8192', {}).get('connectivity') and row['native_legacy_hash_partition'] == 'train':
            roles.append('fixed_train8192')
        if row['native_legacy_hash_partition'] == 'val':
            for role in ('original_val', 'tune'):
                m = membership.get(role, {})
                if m.get('record') and m.get('exact_stereo'):
                    roles.append(role)
        if not roles:
            continue
        reasons = ['excluded_test_or_historical_verify_connectivity'] if row['connectivity_sha256'] in blocked else []
        item = dict(row, reference_roles=roles, selection_reasons=reasons)
        ledger.append(item)
        if not reasons:
            selected.append(item)
    keycounts = collections.Counter(((r['source'], r['nucleus'], r['record_id']) for r in selected))
    assert all((n == 1 for n in keycounts.values())), 'identity plan duplicate; no replacement'
    plan = dict(schema='H_reference_batch_identity_manifest_v1', status='IDENTITY_PLAN_FROZEN', source_sha256=SOURCE_SHA, policy_sha256=POLICY_SHA, input_identity_sha256=sha_bytes(identity_path.read_bytes()), scientific_release_sha256=sha_bytes(release_path.read_bytes()), selection_rule='H: fixed_train8192 connectivity AND native train; val original/tune record AND exact stereo AND native val; exclude all test/historical verify connectivity', selected=selected, selection_ledger=ledger, selected_count=len(selected), role_counts=dict(collections.Counter((role for r in selected for role in r['reference_roles']))), reference_choice='raw', trusted_experimental=False, gold_constructed=False)
    manifest = artifact_path('H_reference_batch_identity_manifest.json')
    if manifest.exists():
        raise FileExistsError('manifest already exists; no automatic overwrite/retry')
    manifest.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    plan_payload = json.dumps(plan).encode()
    frozen_plan_sha = sha_bytes(manifest.read_bytes())
    cmd = ['ssh', binding('prepare_H_reference_inputs.ssh_host.5'), shlex.join([binding('prepare_H_reference_inputs.path.6'), '-c', REMOTE])]
    proc = subprocess.run(cmd, input=plan_payload, capture_output=True, timeout=120)
    plan['execution'] = dict(exit=proc.returncode, elapsed_seconds=time.monotonic() - started, frozen_identity_plan_sha256=frozen_plan_sha, remote_script_sha256=sha_bytes(REMOTE.encode()), argv=cmd, stderr=proc.stderr.decode(errors='replace'))
    if proc.returncode:
        plan['status'] = 'EXTRACTION_FAILED_NO_RETRY'
        manifest.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
        raise SystemExit(proc.returncode)
    messages = [json.loads(x) for x in proc.stdout.splitlines()]
    receipt = [x for x in messages if x['kind'] == 'receipt']
    assert len(receipt) == 1
    plan['remote_receipt'] = receipt[0]
    assert all((receipt[0][k] == SOURCE_SHA for k in ('source_before', 'source_stream', 'source_after')))
    assert all((receipt[0][k] == POLICY_SHA for k in ('policy_before', 'policy_stream', 'policy_after')))
    hidden = artifact_path('hidden')
    hidden.mkdir(exist_ok=True)
    artifacts = {}
    for kind, name in [('raw', 'H_reference_raw_rows.jsonl'), ('policy', 'H_reference_policy_subset.jsonl')]:
        path = hidden / name
        records = [x for x in messages if x['kind'] == kind]
        with path.open('xb') as out:
            for record in records:
                out.write(base64.b64decode(record['raw_b64']))
        artifacts[kind] = dict(path=str(path), sha256=sha_bytes(path.read_bytes()), bytes=path.stat().st_size, rows=len(records))
    plan['hidden_artifacts'] = artifacts
    plan['verified_policy_subset'] = dict(subset_sha256=artifacts['policy']['sha256'], original_full_artifact_sha256=POLICY_SHA, full_artifact_stream_verified=True, subset_is_complete_artifact=False, normalized_adapter_requirement='bind originalfullSHA + subsetSHA + extraction receipt; do not hash subset as full artifact')
    plan['extraction_ledger'] = [{k: v for k, v in x.items() if k != 'raw_b64'} for x in messages if x['kind'] != 'receipt']
    plan['status'] = 'H_TRAINVAL_METADATA_EXTRACTED_GOLD_NOT_CONSTRUCTED'
    plan['execution']['elapsed_seconds'] = time.monotonic() - started
    manifest.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(status=plan['status'], selected=len(selected), roles=plan['role_counts'], raw_rows=artifacts['raw']['rows'], policy_rows=artifacts['policy']['rows'], exit=proc.returncode, elapsed=plan['execution']['elapsed_seconds'], remote_resources=receipt[0])))
if __name__ == '__main__':
    main()
