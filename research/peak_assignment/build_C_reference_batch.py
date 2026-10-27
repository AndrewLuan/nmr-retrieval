# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：3745原native-val C源相对准入batch driver；默认只打印计划，不读raw值或执行batch。\nexecute先验证新source_bundle闭包、producer独审PASS、专用scope及输入SHA；冻结全部身份cohort\n和C直接规则config，然后逐row仅把结构白名单交source_transport(max4096/2s)及已审producer。\n完整ledger保留未知/失败/无public条目；raw/known-mask joint gold/transport/receipt/图仅在hidden。\npublic只含共享cache匿名schema，不能以None造payload。固定173盐分层审计不定义或缩小cohort。\n关系：仅新部署bundle的source_reference/source_transport/C_reference_rule_producer；不改生产repo\n或既有225-file bundle，不读原母源或test数值，不调用模型、评分、校准、训练或外部服务。\n资源：JJ native Python/RDKit2026.03.6，CPU2/GPU0/process-tree RSS2GiB/总10000s；每条map策略\n不变。此预算是准入metadata阶段，绝非独立modelcache10800s预算。失败不重试、不替换。\n输出：新C_reference_batch目录；真实执行另需root冻结config/审查和scope，本源码不自动授权。\n'
import argparse, ast, hashlib, json, os, resource, signal, sys, time
from collections import Counter
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
D = workspace()
SALT = 'source-relative-admission-audit-173-v1'
RAW_SHA = binding('build_C_reference_batch.sha_or_identity.1')
RULE_REVIEW_SHA = binding('build_C_reference_batch.sha_or_identity.2')
PRODUCER_SHA = binding('build_C_reference_batch.sha_or_identity.3')
CORE_SHA = binding('build_C_reference_batch.sha_or_identity.4')
TRANSPORT_SHA = binding('build_C_reference_batch.sha_or_identity.5')
EMPTY_SHA = hashlib.sha256(b'').hexdigest()
FIX_REVIEW_SHA = binding('build_C_reference_batch.sha_or_identity.6')
FIX_DECISION = 'PASS_C1_C8_PRODUCER_IMPLEMENTATION_FIXED_SNAPSHOT_APPLICATION_PENDING'
N = binding('build_C_reference_batch.cohort_count.7')
STARTED = 0.0
PEAK_TREE_RSS = 0

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for part in iter(lambda: f.read(1048576), b''):
            h.update(part)
    return h.hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

def text_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()

def json_value(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError('unsupported_hidden_value:' + type(value).__name__)

def dump(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as f:
        json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2, default=json_value, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)

def append(path, value):
    with path.open('a') as f:
        f.write(json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_value, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())

def rows(path):
    with open(path) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def tree_rss():
    root = os.getpid()
    queue = [root]
    seen = set()
    total = 0
    while queue:
        pid = queue.pop()
        if pid in seen:
            continue
        seen.add(pid)
        try:
            for line in Path('/proc/' + str(pid) + '/status').read_text().splitlines():
                if line.startswith('VmRSS:'):
                    total += int(line.split()[1]) * 1024
            queue.extend((int(x) for x in Path('/proc/' + str(pid) + '/task/' + str(pid) + '/children').read_text().split()))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return total

def monitor(*_):
    global PEAK_TREE_RSS
    current = tree_rss()
    PEAK_TREE_RSS = max(PEAK_TREE_RSS, current)
    need(current <= 2147483648, 'admission_metadata_RSS_2GiB')
    need(time.monotonic() - STARTED <= 10000, 'admission_metadata_wall_10000s')

def metadata(text, keys):
    """Decode only named top-level identity scalars; skip all label values by scanning."""
    decoder = json.JSONDecoder()
    i = 0
    out = {}
    while i < len(text) and text[i].isspace():
        i += 1
    need(i < len(text) and text[i] == '{', 'source_JSON_object')
    i += 1
    while i < len(text):
        while i < len(text) and (text[i].isspace() or text[i] == ','):
            i += 1
        if i >= len(text) or text[i] == '}':
            break
        key, end = decoder.raw_decode(text, i)
        need(isinstance(key, str), 'source_JSON_key')
        i = end
        while i < len(text) and text[i].isspace():
            i += 1
        need(text[i] == ':', 'source_JSON_colon')
        i += 1
        while i < len(text) and text[i].isspace():
            i += 1
        start = i
        depth = 0
        string = False
        escape = False
        while i < len(text):
            ch = text[i]
            if string:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    string = False
            elif ch == '"':
                string = True
            elif ch in '[{':
                depth += 1
            elif ch in ']}':
                if depth == 0:
                    break
                depth -= 1
            elif ch == ',' and depth == 0:
                break
            i += 1
        if key in keys:
            need(key not in out, 'duplicate_identity_key')
            out[key] = json.loads(text[start:i])
    return out

def draft_plan():
    manifest = artifact_path('C_reference_inputs/manifest.json')
    known = json.loads(manifest.read_text()) if manifest.exists() else None
    return dict(schema='C_reference_batch_driver_plan_v1', status='CHECK_ONLY_SOURCE_PLAN_NO_BATCH', driver_sha256=sha(__file__), execution_authorized=False, input_identity_count=N, input_manifest_sha256=sha(manifest) if known else None, candidate_scope='all3745 frozen original native-val C identities; no identity selected by success', producer_sha256=PRODUCER_SHA, source_reference_sha256=CORE_SHA, source_transport_sha256=TRANSPORT_SHA, expected_rdkit_version='2026.03.6', python_executable=binding('build_C_reference_batch.path.8'), CPU_threads=2, GPU_devices=0, RSS_limit_bytes=2147483648, total_seconds=10000, mapping_max_maps=4096, mapping_seconds_per_record=2, model_calls=0, test_value_access=False, mother_source_rescan=False, sample_salt=SALT, sample_per_stratum=1, sample_defines_cohort=False, required_execute_flags=['--config', '--config-sha256', '--out'], pending_root_freeze=['newsourcebundle and closure manifest SHA', 'producer fixreview PASS artifact/exactSHA/decision', 'C batch scope release and SHA', 'copied input artifact paths with immutable SHA', 'actual empty C policy and unavailable-C-conflict artifact SHA', 'rule config and derived cohort SHA frozen before per-row transport'], true_run_in_this_invocation=False)

def execute(config, config_sha, out):
    global STARTED
    STARTED = time.monotonic()
    need(config['schema'] == 'C_reference_batch_driver_config_v1', 'config_schema')
    need(config['execution_authorized'] is True, 'execution_not_released')
    need(config['python_executable'] == binding('build_C_reference_batch.path.9'), 'native_python_plan')
    need(Path(sys.executable).resolve() == Path(config['python_executable']).resolve(), 'must_run_JJ_native_python')
    need(config['CPU_threads'] == 2 and config['GPU_devices'] == 0 and (config['RSS_limit_bytes'] == 2147483648) and (config['total_seconds'] == 10000) and (config['mapping_max_maps'] == 4096) and (config['mapping_seconds_per_record'] == 2), 'fixed_metadata_budget')
    bundle = Path(config['bundle_root']).resolve()
    need('/outputs/' in str(bundle) and bundle.name == 'source_bundle', 'new_output_bundle_only')
    tracked = {}

    def verify(path, expected):
        path = Path(path).resolve()
        need(sha(path) == expected, 'input_SHA:' + str(path))
        tracked[str(path)] = expected
        return path
    closure_path = verify(config['source_manifest']['path'], config['source_manifest']['sha256'])
    closure = json.loads(closure_path.read_text())
    actual = {str(p.relative_to(bundle)): p for p in bundle.rglob('*.py')}
    need(set(actual) == set(closure['source_files']), 'source_bundle_closure_set')
    for rel, path in actual.items():
        verify(path, closure['source_files'][rel])
    verify(__file__, config['driver_sha256'])
    need(closure['source_files']['C_reference_rule_producer.py'] == PRODUCER_SHA, 'reviewed_producer_SHA')
    need(closure['source_files']['nmr_assignment/source_reference.py'] == CORE_SHA, 'reviewed_core_SHA')
    need(closure['source_files']['nmr_assignment/source_transport.py'] == TRANSPORT_SHA, 'reviewed_transport_SHA')
    review_path = verify(config['producer_review']['path'], config['producer_review']['sha256'])
    review = json.loads(review_path.read_text())
    decision = review.get('decision')
    need(config['producer_review']['sha256'] == FIX_REVIEW_SHA, 'producer_review_fixed_SHA')
    need(review.get('schema') == 'C_producer_fix_independent_implementation_review_astra_v1' and decision == FIX_DECISION == config['producer_review']['expected_decision'] and (review.get('producer_sha256') == PRODUCER_SHA) and (review.get('source_reference_sha256') == CORE_SHA) and (review.get('source_transport_sha256') == TRANSPORT_SHA) and (review.get('scientific_rule_review_sha256') == RULE_REVIEW_SHA) and (review.get('producer_implementation_approved_for_previously_authorized_frozen_C_val_admission') is True) and (review.get('real_C3745_application_reviewed') is False), 'producer_review_not_fixed_PASS')
    release_path = verify(config['scope_release']['path'], config['scope_release']['sha256'])
    release = json.loads(release_path.read_text())
    expected = dict(schema='C_reference_batch_release_v1', execution_authorized=True, nucleus_scope='13C', native_partition='val', identity_count=N, source_sha256=RAW_SHA, producer_sha256=PRODUCER_SHA, producer_review_sha256=config['producer_review']['sha256'], driver_sha256=config['driver_sha256'], test_values_allowed=False, model_calls_allowed=False)
    need(all((release.get(k) == v for k, v in expected.items())), 'C_batch_scope_not_released')
    assets = {name: verify(item['path'], item['sha256']) for name, item in config['inputs'].items()}
    need(set(assets) == {'extraction_manifest', 'identity', 'val_raw', 'val_graph', 'empty_policy', 'known_conflict_availability'}, 'input_asset_whitelist')
    extraction = json.loads(assets['extraction_manifest'].read_text())
    need(extraction['status'] == 'C_VAL_RAW_AND_IDENTITY_FROZEN_NO_GOLD' and extraction['remote_receipt']['val_raw_rows'] == N, 'frozen_extraction_scope')
    need(all((extraction['remote_receipt'][k] == RAW_SHA for k in ('raw_before', 'raw_stream', 'raw_after'))), 'mother_source_SHA_receipt')
    for name in ('identity', 'val_raw', 'val_graph'):
        need(sha(assets[name]) == extraction['artifacts'][name]['sha256'], 'extraction_artifact_binding:' + name)
    need(sha(assets['empty_policy']) == EMPTY_SHA and assets['empty_policy'].read_bytes() == b'', 'genuine_empty_C_policy')
    availability = json.loads(assets['known_conflict_availability'].read_text())
    need(availability['schema'] == 'C_known_conflict_availability_v1' and availability['nucleus_scope'] == '13C' and (availability['status'] == 'unavailable') and (availability['exhaustive_historical_audit'] is False), 'C_conflict_availability_scope')
    os.environ.update(CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    resource.setrlimit(resource.RLIMIT_CPU, (10000, 10000))
    signal.signal(signal.SIGALRM, monitor)
    signal.setitimer(signal.ITIMER_REAL, 0.2, 0.2)
    sys.path.insert(0, str(bundle))
    import C_reference_rule_producer as producer
    from nmr_assignment import source_reference as core, source_transport
    from rdkit import rdBase
    need(rdBase.rdkitVersion == '2026.03.6', 'JJ_RDKit_version')
    for name, module in tuple(sys.modules.items()):
        if name == 'C_reference_rule_producer' or name == 'nmr_assignment' or name.startswith('nmr_assignment.'):
            path = getattr(module, '__file__', None)
            if path:
                need(str(Path(path).resolve()) in tracked, 'module_outside_frozen_bundle')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    hidden = out / 'hidden'
    hidden.mkdir()
    receipt = dict(status='partial', identity_count=N, processed=0, public_count=0, public_unavailable=0, transport_started=0, transport_completed=0, model_loads=0, model_forwards=0)
    ledger = []
    candidates = {}
    identities = []
    graphs = {}
    raw_offsets = {}

    def stage(name, **extra):
        monitor()
        receipt.update(last_stage=name, elapsed_seconds=time.monotonic() - STARTED, peak_tree_RSS_bytes=PEAK_TREE_RSS)
        append(hidden / 'stages.jsonl', dict(receipt, **extra))
        dump(out / 'receipt.partial.json', receipt)
    try:
        for row in rows(assets['identity']):
            if row.get('nucleus') == '13C' and row.get('historical_partition') == 'val':
                identities.append(row)
        need(len(identities) == N, 'all3745_native_val_identities')
        by_key = {(r['source'], r['record_id']): r for r in identities}
        need(len(by_key) == N, 'duplicate_native_val_identity')
        for row in rows(assets['val_graph']):
            key = (row['source'], row['record_id'])
            need(key in by_key and key not in graphs, 'native_graph_identity_join')
            graphs[key] = dict(canonical_smiles=row['exact_smiles'], rdkit_version=row['rdkit_version'], graph_snapshot=row['graph_snapshot'], graph_snapshot_sha256=row['graph_snapshot_sha256'])
        need(len(graphs) == N, 'native_graph_full_domain')
        with assets['val_raw'].open('rb') as f:
            while True:
                offset = f.tell()
                line = f.readline()
                if not line:
                    break
                fields = metadata(line.decode(), {'source_ref', 'nucleus', 'record_id', 'structure_id', 'smiles'})
                key = (fields.get('source_ref'), fields.get('record_id'))
                need(fields.get('nucleus') == '13C' and key in by_key and (key not in raw_offsets), 'raw_identity_join')
                meta = by_key[key]
                need(hashlib.sha256(line).hexdigest() == meta['raw_line_sha256'] and fields['smiles'] == meta['raw_smiles'], 'exact_raw_line_binding')
                raw_offsets[key] = (offset, fields.get('structure_id') or text_sha(fields['smiles']))
        need(len(raw_offsets) == N, 'raw_full_identity_domain')
        records = []
        for meta in identities:
            key = (meta['source'], meta['record_id'])
            records.append(dict(source=meta['source'], nucleus='13C', record_id=meta['record_id'], structure_id=raw_offsets[key][1], row_sha256=meta['raw_line_sha256'], native_legacy_hash_partition='val'))
        cohort = dict(source_sha256=RAW_SHA, policy_sha256=EMPTY_SHA, records=records, nucleus_scope='13C', native_partition='val', reference_choice='raw', extraction_manifest_sha256=sha(assets['extraction_manifest']), raw_subset_sha256=sha(assets['val_raw']), identity_ledger_sha256=sha(assets['identity']))
        cohort_text = canonical(cohort)
        (hidden / 'cohort_manifest.json').write_text(cohort_text)
        cohort_sha = text_sha(cohort_text)
        rule = dict(rule_id=producer.RULE_ID, nucleus_scope='13C', scientific_rule_review_sha256=RULE_REVIEW_SHA, source_sha256=RAW_SHA, source_reference_implementation_sha256=CORE_SHA, transport_implementation_sha256=TRANSPORT_SHA, expected_rdkit_version='2026.03.6', extraction_manifest_sha256=cohort['extraction_manifest_sha256'], raw_subset_sha256=cohort['raw_subset_sha256'], identity_ledger_sha256=cohort['identity_ledger_sha256'], expected_cohort_identity_count=N, historical_C_quality_policy_status='unknown', policy_absence_action='direct_C_rule_preserve_unknown', known_conflict_availability_sha256=sha(assets['known_conflict_availability']))
        rule_text = canonical(rule)
        (hidden / 'rule_config.json').write_text(rule_text)
        rule_sha = text_sha(rule_text)
        stage('all_identity_and_rule_frozen', cohort_sha256=cohort_sha, rule_config_sha256=rule_sha)
        with assets['val_raw'].open('rb') as raw:
            for meta, record in zip(identities, records):
                key = (meta['source'], meta['record_id'])
                input_id = 'C-' + text_sha('|'.join((record['source'], '13C', record['record_id'], record['structure_id'], record['row_sha256'])))
                binding = {k: record[k] for k in ('source', 'nucleus', 'record_id', 'structure_id', 'row_sha256')}
                binding.update(source_sha256=RAW_SHA, policy_sha256=EMPTY_SHA, cohort_identity_manifest_sha256=cohort_sha)
                raw.seek(raw_offsets[key][0])
                line = raw.readline()
                text = line.decode()
                row_result = None
                transport = {}
                known = None
                total_slots = None
                try:
                    row = core._load(text)
                    structure = {k: row[k] for k in ('smiles', 'atoms', 'atom_order', 'source_ref', 'nucleus', 'record_id')}
                    if 'structure_id' in row:
                        structure['structure_id'] = row['structure_id']
                    receipt['transport_started'] += 1
                    stage('transport_started', input_id=input_id)
                    transport = source_transport.build_source_transport(structure, binding=binding, baseline_smiles=meta['exact_smiles'], max_maps=4096, time_limit_seconds=2.0, expected_rdkit_version='2026.03.6')
                    receipt['transport_completed'] += 1
                    row_result = producer.produce_C_reference(text, source_sha256=RAW_SHA, empty_C_policy_jsonl='', empty_C_policy_sha256=EMPTY_SHA, cohort_manifest_json=cohort_text, cohort_identity_manifest_sha256=cohort_sha, transport=transport, native_graph_receipt=graphs[key], rule_config_json=rule_text, rule_config_sha256=rule_sha, input_id=input_id)
                    reference = row_result['reference']
                    derived = reference.hidden.get('derived') if reference else None
                    known = derived.reported_slot_count if derived else 0
                    total_slots = sum((core._atomic_number(z) == 6 for z in row.get('atom_order', {}).get('atomic_numbers', [])))
                    classification = row_result['ledger']['proposed_reference_class']
                    public = row_result['public_payload']
                    entry = dict(row_result['ledger'], ledger_class=classification, scoreable_proposal=public is not None, producer_implementation_sha256=PRODUCER_SHA, connectivity_sha256=meta['connectivity_sha256'], known_conflict_availability_sha256=sha(assets['known_conflict_availability']))
                    append(hidden / 'quality_receipts.jsonl', dict(input_id=input_id, quality_receipt=row_result['quality_receipt']))
                    append(hidden / 'producer_evidence.jsonl', dict(input_id=input_id, evidence=row_result['evidence_bundle']))
                    append(hidden / 'reference_gold.jsonl', dict(input_id=input_id, raw_json_line=text, reference_hidden=reference.hidden if reference else None, native_graph_snapshot=graphs[key], known_mask_joint_gold=reference.hidden.get('joint_gold_variants', ()) if reference else ()))
                    if public is not None:
                        need(set(public) == {'input_id', 'nucleus', 'smiles', 'actual_conditions', 'observations'}, 'public_schema')
                        append(out / 'public.jsonl', public)
                        receipt['public_count'] += 1
                    else:
                        receipt['public_unavailable'] += 1
                        append(out / 'public_unavailable.jsonl', dict(input_id=input_id, status='public_unavailable_retained', reasons=entry['reasons']))
                except Exception as exc:
                    classification = 'unknown_driver_failure'
                    receipt['public_unavailable'] += 1
                    entry = dict(binding, input_id=input_id, ledger_class=classification, scoreable_proposal=False, reasons=[type(exc).__name__ + ':' + str(exc)], policy_missing=True, historical_C_quality_policy_status='unknown', connectivity_sha256=meta['connectivity_sha256'])
                    append(out / 'public_unavailable.jsonl', dict(input_id=input_id, status='public_unavailable_retained', reasons=entry['reasons']))
                    append(hidden / 'reference_gold.jsonl', dict(input_id=input_id, raw_json_line=text, native_graph_snapshot=graphs[key]))
                append(hidden / 'transport.jsonl', dict(input_id=input_id, transport=transport))
                scope = 'representative_scope_unknown' if total_slots is None else 'partial_known_nucleus_mask_semantics_unknown' if known < total_slots else 'all_nucleus_slots_mask_semantics_unknown'
                entry.update(representative_label_scope=scope, representative_expansion=False, native_role='native_val')
                ledger.append(entry)
                append(hidden / 'ledger.jsonl', entry)
                receipt['processed'] += 1
                stratum = '|'.join(('13C', meta['source'], 'native_val', classification, scope))
                immutable = '|'.join((meta['source'], '13C', meta['record_id'], record['structure_id'], record['row_sha256']))
                audit_hash = text_sha(SALT + '\n' + immutable)
                if stratum not in candidates or audit_hash < candidates[stratum]['audit_hash']:
                    candidates[stratum] = dict(stratum=stratum, audit_hash=audit_hash, input_id=input_id)
                stage('record_retained', input_id=input_id)
        need(receipt['processed'] == N and receipt['public_count'] + receipt['public_unavailable'] == N, 'all_identity_accounting')
        dump(hidden / 'application_audit_selection.json', dict(salt=SALT, per_stratum=1, defines_cohort=False, entries=sorted(candidates.values(), key=lambda x: x['stratum'])))
        receipt['status'] = 'C_REFERENCE_BATCH_COMPLETE_APPLICATION_REVIEW_PENDING'
    except BaseException as exc:
        receipt.update(status='FAILED_PARTIAL_NO_RETRY', error=type(exc).__name__ + ':' + str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        processed = {(r.get('source'), r.get('record_id')) for r in ledger}
        for record in identities:
            if (record['source'], record['record_id']) not in processed:
                append(hidden / 'ledger.jsonl', dict(source=record['source'], record_id=record['record_id'], nucleus='13C', ledger_class='not_started_retained', reasons=['batch_aborted_no_retry'], native_role='native_val', policy_missing=True, historical_C_quality_policy_status='unknown'))
        for path, before in tracked.items():
            try:
                need(sha(path) == before, 'post_SHA_mismatch')
            except Exception as exc:
                receipt.update(status='FAILED_PARTIAL_NO_RETRY', hash_closure_error=path, hash_closure_reason=type(exc).__name__ + ':' + str(exc))
        receipt.update(elapsed_seconds=time.monotonic() - STARTED, peak_tree_RSS_bytes=PEAK_TREE_RSS, config_sha256=config_sha, source_hashes=tracked)
        if receipt['elapsed_seconds'] > 10000 or PEAK_TREE_RSS > 2147483648:
            receipt['status'] = 'FAILED_PARTIAL_RESOURCE_LIMIT'
        dump(out / 'receipt.json', receipt)
        artifacts = {str(p.relative_to(out)): dict(sha256=sha(p), bytes=p.stat().st_size) for p in out.rglob('*') if p.is_file() and p.name != 'manifest.json'}
        dump(out / 'manifest.json', dict(schema='C_reference_batch_manifest_v1', status=receipt['status'], all_identity_denominator=N, public_count=receipt['public_count'], public_unavailable=receipt['public_unavailable'], source_sha256=RAW_SHA, empty_C_policy_sha256=EMPTY_SHA, producer_sha256=PRODUCER_SHA, model_loads=0, model_forwards=0, application_audit_pending=True, test_values_accessed=False, artifacts=artifacts, receipt=receipt))
    return 0 if receipt['status'] == 'C_REFERENCE_BATCH_COMPLETE_APPLICATION_REVIEW_PENDING' else 1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--config')
    parser.add_argument('--config-sha256')
    parser.add_argument('--out')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(draft_plan(), indent=2))
        return 0
    need(not args.check_only and (not args.plan), 'plan_cannot_execute')
    need(args.config and args.config_sha256 and args.out, 'frozen_config_and_new_out_required')
    need(sha(args.config) == args.config_sha256, 'driver_config_SHA')
    return execute(json.loads(Path(args.config).read_text()), args.config_sha256, args.out)
if __name__ == '__main__':
    raise SystemExit(main())
