# 功能概述：已审H父诊断/聚合或Stage A科学入口的公开迁移副本，非历史actual-run字节。
# 接口：显式runtime授权及独立冻结plan/source/review/release；路径/身份/SHA从external bindings取得。
# 关系：直接依赖同publictree或现有nmr_assignment；保留原数值算法、完整分母、预算及失败协议。
from portable_runtime import binding, workspace, artifact_path, repository, _config
"""功能概述：独立固定测试 Stage A 的真实母源提取和来源准入外层，默认只检查清单。
validate_C_control_metadata严格核冻结C冲突unavailable/noHimport/空冲突列表与真正空policy bytes；
stage_A_metadata_preflight供check-only与execute在新out.mkdir前共用，仅读manifest及两份控制metadata；
validate_stage_A_manifest 在测试内容读取前核母源索引、身份、代码/规则/validation独审和资源；
extract_fixed_H_queries 从原冻结观测资产按原索引提取，不能重造变体或以源分箱替代；
verify_H_query_lineage/source_admission 调用已审索引producer与真实source_transport/core，缺证保留unknown。
extract_fixed_C_rows 按固定source_line/raw行SHA提取；produce_C_test_reference/verify_C_test_receipt
在Stage A内构native图、完整label-free transport及派生cohort，再实际调用独立native_test C1–C8。
validate_fixed_identity_projection 核原ledger完整顺序/身份；project_public_conditions仅投影测量白名单。
run_A 独占新目录，冻结有限batch/每记录预算；输出public/hidden/unknown/lineage/完整ledger及UTC/exit/
输入代码输出SHA。A前不要求新派生records SHA，A后产物交独审和B；无模型、预测、solver或评分。
check_B_release 仅验证独立B授权及实际A准入独审/相同配置阈值；本文件不实现或触发B推理。
默认DRAFT、未知历史H索引血缘、缺原variant峰表一律fail closed，绝不精确/近ppm反向join。
"""
import argparse
from collections import Counter
from dataclasses import asdict, is_dataclass
from decimal import Decimal
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import resource
import signal
import sys
import time
D = workspace()
SHA_RE = re.compile('[0-9a-f]{64}')
CONDITIONS = ('solvent', 'frequency', 'pH', 'ph', 'temperature', 'NMR_solvent')

def need(ok, message):
    if not ok:
        raise ValueError(message)

def is_sha(value):
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None

def json_value(value):
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, Decimal):
        need(value.is_finite(), 'nonfinite Decimal')
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value

def digest(value):
    return hashlib.sha256(json.dumps(json_value(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()

def sha(path, guard=lambda: None):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            guard()
            h.update(block)
    return h.hexdigest()

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def write_json(path, value):
    with Path(path).open('x') as f:
        json.dump(json_value(value), f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())

def read_jsonl(path, guard=lambda: None):
    with Path(path).open('rb') as f:
        while True:
            guard()
            line = f.readline(10485761)
            if not line:
                break
            need(len(line) <= 10485760 and line.endswith(b'\n'), 'bounded complete JSONL line required')
            need(bool(line.strip()), 'blank frozen asset row')
            yield json.loads(line)

def load_code(item, name):
    need(is_sha(item.get('sha256')) and sha(item['path']) == item['sha256'], 'exact producer code SHA required')
    spec = importlib.util.spec_from_file_location(name, item['path'])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def project_public_conditions(source, claimed=None):
    """Only bound measurement source fields are copied; unknown public keys cannot pass."""
    projected = {}
    bindings = {}
    nested = source.get('experimental_conditions') or source.get('conditions') or {}
    need(isinstance(nested, dict), 'condition source must be object/unknown')
    container = 'experimental_conditions' if source.get('experimental_conditions') else 'conditions'
    for key in ('solvent', 'frequency', 'pH', 'ph', 'temperature'):
        if key in nested:
            projected[key] = nested[key]
            bindings[key] = container + '.' + key
    for key in ('solvent', 'frequency'):
        if key in source:
            projected[key] = source[key]
            bindings[key] = key
    metadata = source.get('source_metadata') or {}
    need(isinstance(metadata, dict), 'actual source metadata object')
    if 'NMR_solvent' in metadata:
        projected['NMR_solvent'] = metadata['NMR_solvent']
        bindings['NMR_solvent'] = 'source_metadata.NMR_solvent'
    for key, value in list(projected.items()):
        need(value is None or type(value) in (str, int, float, Decimal), 'nested/bool condition is not measurement scalar')
        if isinstance(value, (float, Decimal)):
            need(math.isfinite(float(value)), 'nonfinite actual condition')
        projected[key] = format(value, 'f') if isinstance(value, Decimal) else value
    if claimed is not None:
        need(isinstance(claimed, dict) and set(claimed) <= set(CONDITIONS), 'unknown public condition field')
        need(claimed == projected, 'public conditions must equal exact measurement projection')
    return (projected, bindings)

def leak_free_public(row):
    need(set(row) == {'input_id', 'nucleus', 'observations', 'smiles', 'actual_conditions'}, 'public leakage/schema')
    need(row['nucleus'] in ('1H', '13C') and isinstance(row['smiles'], str), 'public structure/nucleus')
    need(isinstance(row['actual_conditions'], dict) and set(row['actual_conditions']) <= set(CONDITIONS), 'public condition whitelist')
    for value in row['actual_conditions'].values():
        need(value is None or type(value) in (str, int, float), 'public condition must be scalar')
        if type(value) is float:
            need(math.isfinite(value), 'nonfinite public condition')
    ids = []
    for obs in row['observations']:
        need(set(obs) == {'observation_id', 'ppm_decimal'}, 'public observation leakage')
        need(isinstance(obs['observation_id'], str) and obs['observation_id'], 'original observation ID required')
        need(isinstance(obs['ppm_decimal'], str) and math.isfinite(float(obs['ppm_decimal'])), 'finite original ppm text')
        ids.append(obs['observation_id'])
    need(len(ids) == len(set(ids)), 'duplicate original observation IDs')

def identity_id(identity):
    return identity['query_id'] if identity['nucleus'] == '1H' else identity['input_id']

def validate_fixed_identity_projection(fixed, H_ledger, C_ledger):
    expected = []
    hkeys = ('query_id', 'cohort', 'ordinal', 'ledger_ordinal', 'identity_file_ordinal', 'source', 'record_id', 'nucleus', 'original_smiles', 'exact_smiles', 'connectivity_sha256')
    for row in H_ledger['rows']:
        if row['cohort'].startswith('test_'):
            expected.append({k: row[k] for k in hkeys})
    ckeys = ('source', 'record_id', 'nucleus', 'source_line', 'raw_line_sha256', 'raw_smiles', 'exact_smiles', 'connectivity_sha256', 'historical_partition')
    for ordinal, row in enumerate((r for r in C_ledger if r.get('historical_partition') == 'test')):
        expected.append(dict(input_id='C-test:' + row['record_id'], fixed_test_ordinal=ordinal, **{k: row[k] for k in ckeys}))
    need(fixed['identities'] == expected, 'fixed identity projection/order differs from original ledgers')
    identities = fixed['identities']
    keys = [(r['nucleus'], identity_id(r)) for r in identities]
    records = [(r['nucleus'], r['source'], r['record_id'], r.get('cohort')) for r in identities]
    need(len(keys) == len(set(keys)) and len(records) == len(set(records)), 'duplicate fixed identity')
    need(Counter((r['cohort'] for r in identities if r['nucleus'] == '1H')) == Counter(test_observed=binding('TEST_STAGE_A_fixed_test_outer.identity_count.1'), test_frequency_crop=binding('TEST_STAGE_A_fixed_test_outer.identity_count.2'), test_peak_dropout=binding('TEST_STAGE_A_fixed_test_outer.identity_count.3')), 'original H variant denominator')
    need(sum((r['nucleus'] == '13C' for r in identities)) == binding('TEST_STAGE_A_fixed_test_outer.identity_count.4'), 'original C3637 denominator')
    return identities

def verify_review(item):
    need(is_sha(item.get('sha256')) and sha(item['path']) == item['sha256'], 'independent review exact bytes required')
    review = json.loads(Path(item['path']).read_text())
    need(item.get('decision') and item['decision'].startswith('PASS') and (review.get('decision') == item['decision']), 'review exact PASS required')
    for assertion in item.get('assertions', []):
        value = review
        for key in assertion['path']:
            value = value[key]
        need(value == assertion['equals'], 'independent review content binding mismatch')
    return review

def validate_H_asset_mode(m):
    """Unavailable is a reviewed absence-of-established-asset mode, never an empty replacement table."""
    mode = m.get('H_asset_mode')
    need(isinstance(mode, dict) and mode.get('mode') in ('unavailable', 'reviewed-original-table'), 'explicit mutually exclusive H asset mode')
    if mode['mode'] == 'unavailable':
        need(mode.get('observation_asset') is None and mode.get('schema') is None and (mode.get('index_producer') is None), 'unavailable H locator/schema/index producer must be null')
        need(m.get('H_original_schema') is None and m.get('H_index_producer') is None, 'unavailable H top-level schema/index producer must be null')
        need(not set(m['assets']) & {'H_original_observations', 'H_source_index', 'H_policy'}, 'unavailable H cannot supply dummy observation/source/policy assets')
        review_item = mode['metadata_review']
        expected = binding('TEST_STAGE_A_fixed_test_outer.exact_SHA_or_identity.5')
        need(review_item.get('sha256') == expected and sha(review_item['path']) == expected, 'unavailable H exact independent metadata review required')
        review = json.loads(Path(review_item['path']).read_text())
        need(review.get('decision') == 'LOCATORS_AND_PRODUCER_BINDINGS_VERIFIED_LINEAGE_RECOVERY_UNPROVEN' and review.get('fixed_denominator') == dict(observed=binding('TEST_STAGE_A_fixed_test_outer.identity_count.6'), frequency_crop=binding('TEST_STAGE_A_fixed_test_outer.identity_count.7'), peak_dropout=binding('TEST_STAGE_A_fixed_test_outer.identity_count.8'), total=binding('TEST_STAGE_A_fixed_test_outer.identity_count.9')), 'unavailable H review decision/1371 denominator binding')
        need(is_sha(mode.get('fixed_identity_manifest_sha256')) and mode['fixed_identity_manifest_sha256'] == m['assets']['fixed_identities']['sha256'], 'unavailable H frozen identity manifest binding')
    else:
        need(isinstance(mode.get('observation_asset'), dict) and mode['observation_asset'] == m['assets'].get('H_original_observations'), 'reviewed H original asset binding required')
        need(isinstance(mode.get('schema'), dict) and mode['schema'] == m.get('H_original_schema') and isinstance(mode.get('index_producer'), dict) and (mode['index_producer'] == m.get('H_index_producer')), 'reviewed H original schema/producer mode binding required')
    return mode['mode']

def validate_stage_A_manifest(manifest_path, release_path, release_sha):
    release = release_gate(release_path, release_sha, manifest_path, 'A')
    m = json.loads(Path(manifest_path).read_text())
    need(m['schema'] == 'fixed_test_stage_A_extraction_manifest_v2' and m['implementation_status'] == 'COMPLETE_INDEPENDENTLY_REVIEWED', 'Stage A draft not released')
    need(m.get('stage') == 'A' and m.get('allow_stage_B') is False, 'A cannot authorize B')
    H_mode = validate_H_asset_mode(m)
    required_assets = {'fixed_identities', 'H_identity_ledger', 'C_identity_ledger', 'atom_source', 'C_empty_policy', 'C_known_conflict_availability'}
    if H_mode == 'reviewed-original-table':
        required_assets |= {'H_original_observations', 'H_source_index', 'H_policy'}
    need(set(m['assets']) == required_assets, 'mother source whitelist; no precomputed admission records')
    for name, item in m['assets'].items():
        need(item.get('path') and is_sha(item.get('sha256')) and Path(item['path']).is_file(), 'nonnull existing frozen mother source required:' + name)
    need(m['codes'] and all((item.get('path') and is_sha(item.get('sha256')) for item in m['codes'].values())), 'nonnull implementation SHA required')
    for item in m['codes'].values():
        need(sha(item['path']) == item['sha256'], 'frozen source changed')
    need(m['codes']['outer']['sha256'] == sha(__file__), 'outer exact code binding')
    need(set(m['reviews']) == {'outer', 'C_test_scope', 'H_validation', 'C_validation', 'frozen_rules'}, 'all pre-A independent reviews required')
    for item in m['reviews'].values():
        verify_review(item)
    for kind in ('H', 'C'):
        for role in ('validation_result', 'threshold_artifact'):
            item = m['validation'][kind][role]
            need(item.get('path') and is_sha(item.get('sha256')) and (sha(item['path']) == item['sha256']), 'frozen per-nucleus validation evidence')
    closure = m['review_closure']
    for name, code in m['codes'].items():
        need(closure['code_sha256'].get(name) == code['sha256'], 'code review closure missing:' + name)
    need(closure['mother_source_sha256'] == {k: v['sha256'] for k, v in m['assets'].items()}, 'all mother source exact review closure')
    need(closure['validation_result_sha256'] == {k: m['validation'][k]['validation_result']['sha256'] for k in ('H', 'C')}, 'validation result review closure')
    need(closure['numeric_config_sha256'] == m['numeric_config']['sha256'] and sha(m['numeric_config']['path']) == m['numeric_config']['sha256'], 'same frozen numeric config')
    for kind in ('H', 'C'):
        need(closure['threshold_sha256'][kind] == m['validation'][kind]['threshold_artifact']['sha256'], 'reviewed threshold closure')
    frozen = verify_review(m['reviews']['frozen_rules'])
    value = frozen
    for key in m['review_closure_path']:
        value = value[key]
    need(value == closure, 'review closure self declaration rejected')
    resources = m['resources']
    need(resources['CPU_threads'] == 2 and resources['GPU_devices'] == 0 and (resources['RSS_limit_bytes'] == 2147483648), 'fixed extraction resource envelope')
    need(resources['mapping_max_maps'] == 4096 and resources['mapping_seconds_per_record'] == 2, 'same reviewed finite per-record transport')
    need(type(resources['total_seconds']) in (int, float) and math.isfinite(resources['total_seconds']) and (resources['total_seconds'] > 0), 'separately frozen finite batch budget')
    need(resources['assembly_seconds'] == 120, 'assembly budget must not masquerade as extraction budget')
    if H_mode == 'reviewed-original-table':
        need(m['H_original_schema']['variant_policy'] == 'preserve_only_no_regeneration', 'no variant reconstruction')
        lineage = m['H_index_producer']
        if lineage['status'] == 'unavailable':
            need(lineage.get('code') is None and lineage['action'] == 'non_evaluable_retained', 'missing H producer cannot self certify')
        else:
            need(lineage['status'] == 'reviewed' and lineage['code'] == m['codes']['H_index_producer'], 'H index producer code must be exact reviewed source')
    for name in ('fixed_identities', 'H_identity_ledger', 'C_identity_ledger'):
        item = m['assets'][name]
        need(sha(item['path']) == item['sha256'], 'identity-only artifact SHA:' + name)
    validate_fixed_identity_projection(json.loads(Path(m['assets']['fixed_identities']['path']).read_text()), json.loads(Path(m['assets']['H_identity_ledger']['path']).read_text()), list(read_jsonl(m['assets']['C_identity_ledger']['path'])))
    return (m, release)

def _scalar_metadata(raw, keys):
    """Skip nonidentity JSON values without decoding targets/spectrum for unselected mother rows."""
    text = raw.decode()
    decoder = json.JSONDecoder()
    i = 0
    out = {}
    while i < len(text) and text[i].isspace():
        i += 1
    need(i < len(text) and text[i] == '{', 'mother JSON object')
    i += 1
    while True:
        while i < len(text) and (text[i].isspace() or text[i] == ','):
            i += 1
        if i >= len(text) or text[i] == '}':
            return out
        key, i = decoder.raw_decode(text, i)
        while text[i].isspace():
            i += 1
        need(text[i] == ':', 'mother JSON colon')
        i += 1
        while text[i].isspace():
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
            need(key not in out, 'duplicate mother identity key')
            value = json.loads(text[start:i])
            need(value is None or type(value) in (str, int, float, bool), 'scalar identity metadata')
            out[key] = value

def extract_fixed_C_rows(source_item, identities, guard):
    wanted = {i['source_line']: i for i in identities if i['nucleus'] == '13C'}
    need(len(wanted) == len([i for i in identities if i['nucleus'] == '13C']), 'duplicate C source line')
    found = {}
    h = hashlib.sha256()
    with Path(source_item['path']).open('rb') as f:
        for line_number, raw in enumerate(f, 1):
            guard()
            h.update(raw)
            if line_number not in wanted:
                continue
            i = wanted[line_number]
            need(hashlib.sha256(raw).hexdigest() == i['raw_line_sha256'], 'C original raw line SHA mismatch')
            row = json.loads(raw)
            need((row['source_ref'], row['record_id'], row['nucleus'], row['smiles']) == (i['source'], i['record_id'], '13C', i['raw_smiles']), 'C exact native identity mismatch')
            found[identity_id(i)] = raw.decode()
    need(h.hexdigest() == source_item['sha256'], 'mother source SHA mismatch')
    need(len(found) == len(wanted), 'C missing original rows; no substitution')
    return found

def extract_H_source_rows(source_item, identities, source_index, guard):
    wanted = {(i['source'], i['record_id']): i for i in identities if i['nucleus'] == '1H'}
    source_index = [r for r in source_index if r.get('nucleus') == '1H']
    idx = {(r['source'], r['record_id']): r for r in source_index}
    need(len(idx) == len(source_index), 'duplicate H source index identity')
    lines = {r['source_line']: key for key, r in idx.items() if key in wanted}
    need(len(lines) == len([key for key in idx if key in wanted]), 'duplicate H source line')
    result = {}
    h = hashlib.sha256()
    with Path(source_item['path']).open('rb') as f:
        for number, raw in enumerate(f, 1):
            guard()
            h.update(raw)
            if number not in lines:
                continue
            key = lines[number]
            record = idx[key]
            if record.get('raw_line_sha256') is not None:
                need(hashlib.sha256(raw).hexdigest() == record['raw_line_sha256'], 'H existing exact raw source SHA')
            row = json.loads(raw)
            need((row['source_ref'], row['record_id'], row['nucleus']) == (*key, '1H'), 'H source record identity')
            result[key] = raw.decode()
    need(h.hexdigest() == source_item['sha256'], 'H mother source SHA')
    return result

def extract_fixed_H_queries(source_item, identities, schema, guard):
    """Extract an existing original-observation table, never a table of derived admissions."""
    wanted = {i['query_id']: i for i in identities if i['nucleus'] == '1H'}
    found = {}
    h = hashlib.sha256()
    need(schema['format'] == 'original_observation_jsonl_v1', 'reviewed original table reader required; bank/features cannot masquerade as peak table')
    with Path(source_item['path']).open('rb') as f:
        for ordinal, raw in enumerate(f):
            guard()
            h.update(raw)
            need(len(raw) <= 10485760, 'original observation row cap')
            meta = _scalar_metadata(raw, {'query_id'})
            iid = meta.get('query_id')
            if iid not in wanted:
                continue
            row = json.loads(raw, parse_float=Decimal)
            need(not set(row) & {'admission', 'reference_admitted', 'gate_outcomes', 'joint_gold_variants', 'complete'}, 'preprocessed admission is not original observation source')
            need(iid not in found, 'duplicate original H query')
            identity = wanted[iid]
            need(all((row[k] == identity[k] for k in ('cohort', 'source', 'record_id'))), 'original H exact identity/variant')
            need(row['identity_file_ordinal'] == identity['identity_file_ordinal'], 'original identity-file row binding')
            if 'original_smiles' in identity:
                need(row['smiles'] == identity['original_smiles'], 'original H query structure identity')
            need(isinstance(row['observations'], list), 'original observation table required')
            conditions, _ = project_public_conditions(row)
            public = dict(input_id=iid, nucleus='1H', smiles=row['smiles'], observations=row['observations'], actual_conditions=conditions)
            leak_free_public(public)
            found[iid] = dict(identity=identity, public=public, original_query=row, original_row_sha256=hashlib.sha256(raw).hexdigest(), original_asset_ordinal=ordinal, original_source_asset_sha256=source_item['sha256'], original_raw_line=raw.decode())
    need(h.hexdigest() == source_item['sha256'], 'original observation asset SHA mismatch')
    return {iid: found.get(iid, dict(identity=identity, public=None, reason='original_observation_row_unavailable')) for iid, identity in wanted.items()}

class _VerifiedHLineage(dict):
    """Only actual index-producer verification creates this in-memory admission prerequisite."""

def verify_H_query_lineage(record, source_raw, producer, producer_sha, parent=None):
    try:
        need(record['public'] is not None and source_raw is not None, 'original query/source unavailable')
        need(producer is not None and is_sha(producer_sha), 'audited actual index producer unavailable')
        raw = json.loads(source_raw)
        q = record['original_query']
        projection = producer.project_original_observation_indices(source_raw, record['original_raw_line'])
        need(projection['source_row_sha256'] == text_sha(source_raw) and projection['original_query_row_sha256'] == record['original_row_sha256'], 'producer mother/query byte binding')
        links = projection['observation_index_projection']
        ids = [o['observation_id'] for o in record['public']['observations']]
        need([r['observation_id'] for r in links] == ids, 'complete original observation order projection')
        source_slots = len(raw['atoms'])
        upstream = projection['upstream_observations']
        need(isinstance(upstream, list) and upstream, 'actual upstream observation domain required')
        seen = []
        for link in links:
            j = link['upstream_observation_index']
            members = link['source_atom_members']
            need(type(j) is int and 0 <= j < len(upstream), 'upstream observation index out of bounds')
            need(isinstance(members, list) and members and (len(members) == len(set(members))) and all((type(i) is int and 0 <= i < source_slots for i in members)), 'source atom index out of bounds/duplicate')
            need(members == upstream[j]['source_atom_members'], 'complete merged source membership differs')
            need(record['public']['observations'][len(seen)]['ppm_decimal'] == upstream[j]['ppm_decimal'], 'original observation value integrity')
            seen.append(link)
        if record['identity']['cohort'] == 'test_observed':
            active = {i for i, m in enumerate(raw['atom_target_mask']) if m}
            members = [i for link in links for i in link['source_atom_members']]
            need(len(members) == len(set(members)) and set(members) == active, 'observed normalization must cover active source index partition')
        else:
            need(type(parent) is _VerifiedHLineage and parent['verified'], 'variant observed-parent trace must already be proven')
            need(parent['source_row_sha256'] == text_sha(source_raw), 'variant parent raw source differs')
            need(projection['parent_query_id'] == parent['query_id'], 'variant parent ID mismatch')
            keep = projection['retained_parent_indices']
            parent_links = parent['links']
            parent_obs = parent['observations']
            need(isinstance(keep, list) and keep == sorted(set(keep)) and all((type(i) is int and 0 <= i < len(parent_links) for i in keep)), 'variant retained index bounds/order')
            need([parent_links[i] for i in keep] == links, 'child membership/upstream index must equal retained parent links')
            need([parent_obs[i] for i in keep] == record['public']['observations'], 'variant original observation subset differs')
        return (_VerifiedHLineage(verified=True, query_id=record['identity']['query_id'], links=links, observations=record['public']['observations'], source_row_sha256=text_sha(source_raw), producer_sha256=producer_sha, projection=projection), None)
    except (KeyError, ValueError, TypeError, IndexError, AttributeError) as exc:
        return (dict(verified=False), 'H_lineage_unproven:' + str(exc))

def structural_native_and_transport(raw_text, binding, context, guard):
    """Only declared molecular structure reaches matching; labels do not select a map."""
    from rdkit import Chem, rdBase
    from nmr_assignment import source_transport
    guard()
    row = json.loads(raw_text)
    need(rdBase.rdkitVersion == context['expected_rdkit_version'], 'reviewed RDKit version mismatch')
    canonical = Chem.MolToSmiles(Chem.RemoveHs(Chem.MolFromSmiles(row['smiles'])), isomericSmiles=True)
    mol = Chem.AddHs(Chem.MolFromSmiles(canonical))
    graph = source_transport._graph_snapshot(mol)
    native = dict(canonical_smiles=canonical, rdkit_version=rdBase.rdkitVersion, graph_snapshot=graph, graph_snapshot_sha256=digest(graph))
    structure = {k: row[k] for k in ('smiles', 'atoms', 'atom_order', 'source_ref', 'nucleus', 'record_id')}
    if 'structure_id' in row:
        structure['structure_id'] = row['structure_id']
    transport = source_transport.build_source_transport(structure, binding=binding, baseline_smiles=canonical, max_maps=context['mapping_max_maps'], time_limit_seconds=context['mapping_seconds_per_record'], expected_rdkit_version=rdBase.rdkitVersion)
    guard()
    return (native, transport)

def raw_binding(raw_text, source_sha, policy_sha, cohort_sha):
    row = json.loads(raw_text)
    return dict(source=row['source_ref'], nucleus=row['nucleus'], record_id=row['record_id'], structure_id=row.get('structure_id') or text_sha(row['smiles']), source_sha256=source_sha, row_sha256=text_sha(raw_text), policy_sha256=policy_sha, cohort_identity_manifest_sha256=cohort_sha)

def verify_full_transport(raw_text, binding, native, transport):
    from nmr_assignment import source_transport
    t = source_transport.restore_joint_map_keys(transport)
    need(all((t.get(k) == v for k, v in binding.items())), 'computed transport binding mismatch')
    need(t.get('complete') is True and t.get('enumeration_truncated') is False and (t.get('structure_only') is True), 'computed transport incomplete')
    lineage = t['graph_lineage_evidence']
    proof = t['completeness_evidence']
    restored = dict(lineage)
    for name in ('source_suppressed_H_by_parent', 'target_suppressed_H_by_parent'):
        if name in restored:
            restored[name] = {int(k): v for k, v in restored[name].items()}
    raw = json.loads(raw_text)
    order = raw['atom_order']
    payload = dict(smiles=raw['smiles'], atoms=raw['atoms'], atom_order={k: order[k] for k in ('basis', 'source_to_canonical', 'atomic_numbers')})
    need(lineage['source_structure_payload'] == payload, 'transport source graph differs from actual raw source')
    from nmr_assignment.source_transport import _digest
    need(_digest(restored) == t['graph_lineage_evidence_sha256'] and digest(proof) == t['completeness_evidence_sha256'] and (proof['graph_lineage_evidence_sha256'] == t['graph_lineage_evidence_sha256']) and (proof.get('enumeration_truncated') is False), 'transport proof digest mismatch')
    need(lineage['baseline_graph'] == native['graph_snapshot'] and lineage['canonical_smiles'] == native['canonical_smiles'] and (lineage['rdkit_version'] == native['rdkit_version']), 'independent native structure mismatch')
    domain = set(range(len(raw['atoms'])))
    parents = {str(a['index']) for a in native['graph_snapshot']['atoms'] if a['z'] != 1}
    family = []
    for mapping in t['joint_maps']:
        need(set(mapping) == domain and all((str(v) in parents for v in mapping.values())), 'whole joint source/native domain invalid')
        family.append(tuple((mapping[i] for i in range(len(raw['atoms'])))))
    need(family and sorted(set(family)) == sorted(set((tuple(v) for v in proof['parent_projection_rows']))), 'whole joint family differs from complete proof')
    return t

def make_C_context(raw_rows, identities, source_sha, extraction_input_sha, identity_sha, empty_policy, context):
    from nmr_assignment import source_reference as core
    records = []
    texts = []
    for identity in identities:
        if identity['nucleus'] != '13C':
            continue
        text = raw_rows[identity_id(identity)]
        row = json.loads(text)
        texts.append(text)
        record = {k: v for k, v in raw_binding(text, source_sha, text_sha(empty_policy), '0' * 64).items() if k in ('source', 'nucleus', 'record_id', 'structure_id', 'row_sha256')}
        record.update(native_legacy_hash_partition='test', native_role='native_test')
        records.append(record)
    cohort = dict(source_sha256=source_sha, policy_sha256=text_sha(empty_policy), records=records, native_partition='test', native_role='native_test', nucleus_scope='13C', reference_choice='raw', extraction_manifest_sha256=extraction_input_sha, raw_subset_sha256=text_sha(''.join(texts)), identity_ledger_sha256=identity_sha)
    cohort_text = json.dumps(cohort, ensure_ascii=False, allow_nan=False)
    producer = context['C_producer']
    config = dict(rule_id=producer.RULE_ID, nucleus_scope='13C', scientific_rule_review_sha256=producer.RULE_REVIEW_SHA, source_sha256=source_sha, source_reference_implementation_sha256=context['core_sha256'], transport_implementation_sha256=context['transport_sha256'], expected_rdkit_version=context['expected_rdkit_version'], extraction_manifest_sha256=extraction_input_sha, raw_subset_sha256=cohort['raw_subset_sha256'], identity_ledger_sha256=identity_sha, expected_cohort_identity_count=binding('TEST_STAGE_A_fixed_test_outer.identity_count.10'), historical_C_quality_policy_status='unknown', policy_absence_action='direct_C_rule_preserve_unknown')
    config_text = json.dumps(config, ensure_ascii=False, allow_nan=False)
    return dict(cohort_text=cohort_text, cohort_sha256=text_sha(cohort_text), config_text=config_text, config_sha256=text_sha(config_text), empty_policy=empty_policy, policy_sha256=text_sha(empty_policy), source_sha256=source_sha)

def produce_C_test_reference(raw_text, identity, C_context, context, guard):
    """Compute, rather than accept, C1–C8 and whole transport from actual original source."""
    need(identity['historical_partition'] == 'test', 'C original historical partition changed')
    need(text_sha(raw_text) == identity['raw_line_sha256'], 'C raw row byte binding')
    binding = raw_binding(raw_text, C_context['source_sha256'], C_context['policy_sha256'], C_context['cohort_sha256'])
    native, transport = structural_native_and_transport(raw_text, binding, context, guard)
    kwargs = dict(raw_json_line=raw_text, source_sha256=C_context['source_sha256'], empty_C_policy_jsonl=C_context['empty_policy'], empty_C_policy_sha256=C_context['policy_sha256'], cohort_manifest_json=C_context['cohort_text'], cohort_identity_manifest_sha256=C_context['cohort_sha256'], transport=transport, native_graph_receipt=native, rule_config_json=C_context['config_text'], rule_config_sha256=C_context['config_sha256'], input_id=identity_id(identity), known_conflicts_json=None, known_conflicts_sha256=None)
    computed = context['C_producer'].produce_C_reference(**kwargs)
    return verify_C_test_receipt(raw_text, identity, computed, kwargs, context, guard)

def verify_C_test_receipt(raw_text, identity, claimed, producer_kwargs, context, guard):
    """Recompute actual producer output; forged gate/joint booleans never authorize a row."""
    guard()
    need(producer_kwargs['input_id'] == identity_id(identity) and producer_kwargs['raw_json_line'] == raw_text and (text_sha(raw_text) == identity['raw_line_sha256']), 'C verifier exact original identity/raw binding')
    recomputed = context['C_producer'].produce_C_reference(**producer_kwargs)
    need(json_value(claimed) == json_value(recomputed), 'C claimed receipt/public/joint differs from actual producer computation')
    transport = producer_kwargs['transport']
    native = producer_kwargs['native_graph_receipt']
    admitted = recomputed['quality_receipt'] is not None and recomputed['public_payload'] is not None
    if admitted:
        binding = raw_binding(raw_text, producer_kwargs['source_sha256'], producer_kwargs['empty_C_policy_sha256'], producer_kwargs['cohort_identity_manifest_sha256'])
        verify_full_transport(raw_text, binding, native, transport)
        quality = recomputed['quality_receipt']
        need(quality['evidence_sha256'] == context['C_producer'].digest(recomputed['evidence_bundle']), 'C fresh quality evidence binding')
        conditions, condition_binding = project_public_conditions(context['C_producer'].core._load(raw_text), recomputed['public_payload']['actual_conditions'])
        bins = recomputed['public_payload']['observations']
        public = dict(input_id=identity_id(identity), nucleus='13C', smiles=recomputed['public_payload']['smiles'], observations=[dict(observation_id=b['bin_id'], ppm_decimal=b['ppm_decimal']) for b in bins], actual_conditions=conditions)
        leak_free_public(public)
    else:
        public = None
        condition_binding = {}
    return dict(public=public, reference_admitted=admitted, reason=None if admitted else 'C1_C8_reference_unknown_or_restricted', hidden=dict(raw_json_line=raw_text, computed_reference=json_value(recomputed['reference']), quality_receipt=recomputed['quality_receipt'], evidence_bundle=recomputed['evidence_bundle'], native_graph_snapshot=native, transport=transport, condition_source_fields=condition_binding), lineage=dict(actual_producer_sha256=context['C_producer_sha256'], source_row_sha256=text_sha(raw_text), whole_transport_sha256=digest(transport), computed_not_claimed=True))

def verify_H_source_admission(record, source_raw, lineage, H_context, context, guard):
    from nmr_assignment import source_reference as core
    if type(lineage) is not _VerifiedHLineage or not lineage['verified']:
        return dict(reference_admitted=False, reason='H_lineage_unproven', hidden=None)
    binding = raw_binding(source_raw, H_context['source_sha256'], H_context['policy_sha256'], H_context['cohort_sha256'])
    native, transport = structural_native_and_transport(source_raw, binding, context, guard)
    need(native['canonical_smiles'] == record['identity']['exact_smiles'], 'H source/query exact canonical structure differs')
    try:
        verified_transport = verify_full_transport(source_raw, binding, native, transport)
    except (ValueError, KeyError, TypeError) as exc:
        return dict(reference_admitted=False, reason='H_transport_unknown:' + str(exc), hidden=transport)
    reference = core.build_source_reference(source_raw, source_sha256=H_context['source_sha256'], policy_jsonl=H_context['policy'], policy_sha256=H_context['policy_sha256'], cohort_manifest_json=H_context['cohort_text'], cohort_identity_manifest_sha256=H_context['cohort_sha256'], transport=transport)
    admitted = reference.classification in ('unique_parent', 'parent_mapping_ambiguous')
    variants = set()
    if admitted:
        for mapping in verified_transport['joint_maps']:
            variants.add(tuple(((link['observation_id'], tuple(sorted({mapping[i] for i in link['source_atom_members']}))) for link in lineage['links'])))
    need(not admitted or bool(variants), 'H empty whole query projection')
    return dict(reference_admitted=admitted, reason=None if admitted else 'H_source_rule_not_admitted', hidden=dict(raw_json_line=source_raw, source_reference=json_value(reference), original_query_joint_gold_variants=sorted(variants), native_graph_snapshot=native, transport=transport, verified_index_projection=lineage), lineage=dict(source_row_sha256=text_sha(source_raw), producer_sha256=lineage['producer_sha256'], computed_not_claimed=True))

def make_H_context(raw_rows, source_sha, policy):
    records = [{k: v for k, v in raw_binding(text, source_sha, text_sha(policy), '0' * 64).items() if k in ('source', 'nucleus', 'record_id', 'structure_id', 'row_sha256')} for text in raw_rows.values()]
    cohort_text = json.dumps(dict(source_sha256=source_sha, policy_sha256=text_sha(policy), records=records), ensure_ascii=False)
    return dict(source_sha256=source_sha, policy=policy, policy_sha256=text_sha(policy), cohort_text=cohort_text, cohort_sha256=text_sha(cohort_text))

def release_gate(path, expected_sha, manifest_path, stage):
    need(path and is_sha(expected_sha) and (sha(path) == expected_sha), 'owner exact release JSON+SHA required')
    r = json.loads(Path(path).read_text())
    need(r.get('schema') == 'original_owner_test_stage_' + stage + '_release_v1' and r.get('stage') == stage and (r.get('execution_authorized') is True), 'independent owner stage release')
    need(r.get('manifest_sha256') == sha(manifest_path) and r.get('entrypoint_sha256') == sha(__file__), 'exact manifest/code release binding')
    need(r.get('H_fixed_identity_count') == binding('TEST_STAGE_A_fixed_test_outer.identity_count.11') and r.get('C_fixed_identity_count') == binding('TEST_STAGE_A_fixed_test_outer.identity_count.12'), 'original denominator unchanged')
    need(isinstance(r.get('release_id'), str) and bool(r['release_id']) and is_sha(r.get('owner_authorization_evidence_sha256')), 'owner release identity/evidence required')
    if stage == 'A':
        need(r.get('one_fixed_test_extraction') is True and r.get('prediction_blind_admission') is True, 'A scope')
        need(all((r.get(k) is False for k in ('model_forward_allowed', 'solve_allowed', 'score_allowed', 'stage_B_authorized'))), 'A cannot authorize B')
    return r

def calibration_axis_publication_gate(requested_axis, artifacts):
    """Stored validation evidence transfers only across the exact advertised semantic axis; never refit."""
    fields = ('method', 'nucleus', 'truth_basis', 'task_semantics', 'target_level', 'target_semantics', 'endpoint', 'sampling_unit')
    need(all((isinstance(requested_axis.get(k), str) and requested_axis[k] for k in fields)), 'explicit test calibration semantic axis')
    matching = [a for a in artifacts if all((a.get('axis', {}).get(k) == requested_axis[k] for k in fields))]
    if len(matching) != 1:
        return dict(publication_enabled=False, status='off_no_matching_semantic_axis', threshold=None)
    artifact = matching[0]
    threshold = artifact.get('threshold')
    status = artifact.get('status')
    enabled = status == 'on_audit_passed' and type(threshold) in (int, float) and math.isfinite(threshold) and (threshold > 0)
    return dict(publication_enabled=enabled, status=status if not enabled else 'on_exact_reviewed_semantic_axis', threshold=threshold if enabled else None, stored_threshold=threshold, refit=False)

def check_B_release(path, expected_sha, manifest_path):
    release = release_gate(path, expected_sha, manifest_path, 'B')
    m = json.loads(Path(manifest_path).read_text())
    for key in ('stage_A_output_manifest', 'stage_A_actual_admission_review', 'stage_A_numeric_config', 'stage_B_numeric_config', 'stage_A_threshold_artifact', 'stage_B_threshold_artifact'):
        item = m[key]
        need(item.get('path') and is_sha(item.get('sha256')) and (sha(item['path']) == item['sha256']), 'B actual evidence:' + key)
    actual = json.loads(Path(m['stage_A_output_manifest']['path']).read_text())
    need(actual.get('status') == 'complete' and actual.get('exit_code') == 0 and (actual.get('stage_B_authorized') is False), 'B requires completed A, never failed/partial receipt')
    need(actual.get('artifacts', {}).get('ledger', {}).get('rows') == binding('TEST_STAGE_A_fixed_test_outer.identity_count.13'), 'B original full identity denominator')
    review = json.loads(Path(m['stage_A_actual_admission_review']['path']).read_text())
    need(review['decision'].startswith('PASS') and review['stage_A_output_manifest_sha256'] == m['stage_A_output_manifest']['sha256'], 'B actual admission review exact binding')
    for key in ('numeric_config', 'threshold_artifact'):
        need(m['stage_A_' + key]['sha256'] == m['stage_B_' + key]['sha256'], 'B cannot refit parameter/threshold')
    need(isinstance(m.get('requested_calibration_axes'), list), 'B must state semantic axes or explicitly publish no confidence')
    stored = json.loads(Path(m['stage_A_threshold_artifact']['path']).read_text())
    artifacts = stored if isinstance(stored, list) else stored['axes']
    gates = [dict(axis=axis, gate=calibration_axis_publication_gate(axis, artifacts)) for axis in m['requested_calibration_axes']]
    return dict(release, calibration_publication_gates=gates, threshold_fit_calls=0)

def write_stage_A_outputs(out, identities, H_results, C_results, guard):
    rows = {k: [] for k in ('public', 'hidden', 'unknown', 'lineage', 'ledger')}
    for ordinal, identity in enumerate(identities):
        guard()
        iid = identity_id(identity)
        result = (H_results if identity['nucleus'] == '1H' else C_results)[iid]
        public = result.get('public')
        if public is not None:
            leak_free_public(public)
            rows['public'].append(public)
        admitted = result.get('reference_admitted') is True
        rows['hidden'].append(dict(input_id=iid, identity=identity, evidence=result.get('hidden')))
        rows['lineage'].append(dict(input_id=iid, evidence=result.get('lineage')))
        rows['ledger'].append(dict(input_id=iid, identity_ordinal=ordinal, nucleus=identity['nucleus'], variant=identity.get('cohort'), public_available=public is not None, reference_admitted=admitted, non_evaluable_reason=result.get('reason'), historical_nonblind=identity['nucleus'] == '13C', trusted_experimental=False, task_semantics='original_fixed_query_observations' if identity['nucleus'] == '1H' else 'derived_serialized_value_bin', calibration_default='off_unless_exact_reviewed_semantic_axis'))
        if not admitted:
            rows['unknown'].append(dict(input_id=iid, reason=result.get('reason')))
    artifacts = {}
    for name, values in rows.items():
        path = out / (name + '.jsonl')
        with path.open('x') as f:
            for value in values:
                guard()
                f.write(json.dumps(json_value(value), ensure_ascii=False, allow_nan=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        artifacts[name] = dict(path=str(path), sha256=sha(path, guard), rows=len(values))
    return artifacts

def process_H_stage_A(m, identities, context, out, guard):
    """Unavailable mode performs no H observation/source/policy/transport work and retains every identity."""
    if m['H_asset_mode']['mode'] == 'unavailable':
        return {i['query_id']: dict(public=None, reference_admitted=False, reason='original_observation_artifact_unavailable', hidden=dict(availability='not_established_by_reviewed_metadata', metadata_review=m['H_asset_mode']['metadata_review']), lineage=dict(status='unavailable', metadata_review_sha256=m['H_asset_mode']['metadata_review']['sha256'])) for i in identities if i['nucleus'] == '1H'}
    H_queries = extract_fixed_H_queries(m['assets']['H_original_observations'], identities, m['H_original_schema'], guard)
    source_index = json.loads(Path(m['assets']['H_source_index']['path']).read_text())['matched_source_identity_rows']
    H_raw = extract_H_source_rows(m['assets']['atom_source'], identities, source_index, guard)
    write_json(out / 'H_extraction_receipt.json', dict(mother_source_sha256=m['assets']['atom_source']['sha256'], identity_index_sha256=m['assets']['H_source_index']['sha256'], rows=[dict(source=key[0], record_id=key[1], raw_line_sha256=text_sha(text)) for key, text in H_raw.items()]))
    H_policy = Path(m['assets']['H_policy']['path']).read_text()
    H_context = make_H_context(H_raw, m['assets']['atom_source']['sha256'], H_policy)
    index_spec = m['H_index_producer']
    H_producer = load_code(index_spec['code'], 'stage_A_H_index_producer') if index_spec['status'] == 'reviewed' else None
    H_producer_sha = index_spec['code']['sha256'] if H_producer is not None else None
    H_results = {}
    verified = {}
    observed_parents = {}
    H_order = [i for i in identities if i['nucleus'] == '1H' and i['cohort'] == 'test_observed'] + [i for i in identities if i['nucleus'] == '1H' and i['cohort'] != 'test_observed']
    for identity in H_order:
        guard()
        iid = identity['query_id']
        record = H_queries[iid]
        raw = H_raw.get((identity['source'], identity['record_id']))
        original = record.get('original_query', {})
        parent_key = (identity['source'], identity['record_id'], identity['connectivity_sha256'])
        parent = observed_parents.get(parent_key)
        trace, reason = verify_H_query_lineage(record, raw, H_producer, H_producer_sha, parent)
        verified[iid] = trace
        if identity['cohort'] == 'test_observed':
            need(parent_key not in observed_parents, 'duplicate frozen observed parent identity')
            observed_parents[parent_key] = trace
        result = dict(public=record.get('public'), reference_admitted=False, reason=reason, hidden=dict(original_query=original, original_query_raw_line=record.get('original_raw_line')), lineage=trace)
        if trace['verified']:
            try:
                result.update(verify_H_source_admission(record, raw, trace, H_context, context, guard))
            except (ValueError, KeyError, TypeError, RuntimeError) as exc:
                result.update(reference_admitted=False, reason='H_actual_source_reference_unknown:' + str(exc))
        H_results[iid] = result
    return H_results

def validate_C_control_metadata(empty_policy_bytes, conflict):
    """Validate unavailable evidence only; empty registry never asserts conflict-free source."""
    need(type(empty_policy_bytes) is bytes and empty_policy_bytes == b'', 'actual C policy must remain genuinely empty bytes')
    need(type(conflict) is dict, 'C conflict metadata object required')
    need(conflict.get('status') == 'unavailable' and conflict.get('scope') == 'C_nucleus_correct_established_conflicts_registry' and (conflict.get('exhaustive_audit_claim') is False) and (conflict.get('H_corrections_imported') is False) and (type(conflict.get('conflicts')) is list) and (conflict['conflicts'] == []), 'C known-conflict unavailable exact metadata schema')
    return dict(empty_policy='', known_conflict_status='unavailable', exhaustive_audit_claim=False, H_corrections_imported=False, conflict_free_claim=False)

def stage_A_metadata_preflight(manifest_path):
    """Read only the manifest, exact empty-policy bytes and conflict control metadata.

    No source/identity/observation files are opened and no output directory is created.
    This is engineering schema readiness, not release/admission approval.
    """
    manifest = json.loads(Path(manifest_path).read_text())
    assets = manifest['assets']
    policy = assets['C_empty_policy']
    conflict = assets['C_known_conflict_availability']
    need(is_sha(policy.get('sha256')) and sha(policy['path']) == policy['sha256'], 'C empty-policy exact control SHA')
    need(is_sha(conflict.get('sha256')) and sha(conflict['path']) == conflict['sha256'], 'C conflict-metadata exact control SHA')
    checked = validate_C_control_metadata(Path(policy['path']).read_bytes(), json.loads(Path(conflict['path']).read_text()))
    return dict(checked, control_sha256=dict(C_empty_policy=policy['sha256'], C_known_conflict_availability=conflict['sha256']), source_values_read=False)

def run_A(manifest_path, release_path, release_sha):
    control_metadata = stage_A_metadata_preflight(manifest_path)
    m, release = validate_stage_A_manifest(manifest_path, release_path, release_sha)
    out = Path(m['output_directory'])
    out.mkdir(exist_ok=False)
    started = time.monotonic()
    deadline = started + m['resources']['total_seconds']
    receipt = dict(status='failed', exit_code=1, started_UTC=utc(), PID=os.getpid(), release_sha256=release_sha, manifest_sha256=sha(manifest_path), models=0, solves=0, scores=0, retries=0)
    write_json(out / 'STARTED.json', receipt)

    def guard():
        need(time.monotonic() < deadline, 'Stage A finite batch deadline')
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
        need(rss <= m['resources']['RSS_limit_bytes'], 'Stage A RSS budget')

    def timeout(*_):
        raise TimeoutError('Stage A finite batch deadline')
    previous = signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, m['resources']['total_seconds'])
    try:
        os.environ.update(CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
        if hasattr(os, 'sched_getaffinity'):
            os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
        fixed = json.loads(Path(m['assets']['fixed_identities']['path']).read_text())
        identities = validate_fixed_identity_projection(fixed, json.loads(Path(m['assets']['H_identity_ledger']['path']).read_text()), list(read_jsonl(m['assets']['C_identity_ledger']['path'], guard)))
        write_json(out / 'initial_identity_denominator.json', dict(total=binding('TEST_STAGE_A_fixed_test_outer.identity_count.14'), H=binding('TEST_STAGE_A_fixed_test_outer.identity_count.15'), C=binding('TEST_STAGE_A_fixed_test_outer.identity_count.16'), rows=[dict(input_id=identity_id(i), identity_ordinal=n, nucleus=i['nucleus'], status='not_started') for n, i in enumerate(identities)], policy='Every original identity remains retained on interruption; no complete admission is asserted for unstarted rows.'))
        for name, item in m['assets'].items():
            need(sha(item['path'], guard) == item['sha256'], 'mother source pre-SHA:' + name)
        sys.path.insert(0, m['repo'])
        producer = load_code(m['codes']['C_test_producer'], 'stage_A_C_test_producer')
        from nmr_assignment import source_reference, source_transport
        need(sha(source_reference.__file__) == m['codes']['source_reference']['sha256'] and sha(source_transport.__file__) == m['codes']['source_transport']['sha256'], 'imported core exact source')
        context = dict(C_producer=producer, C_producer_sha256=m['codes']['C_test_producer']['sha256'], core_sha256=m['codes']['source_reference']['sha256'], transport_sha256=m['codes']['source_transport']['sha256'], expected_rdkit_version=m['expected_rdkit_version'], mapping_max_maps=m['resources']['mapping_max_maps'], mapping_seconds_per_record=m['resources']['mapping_seconds_per_record'])
        empty = control_metadata['empty_policy']
        C_raw = extract_fixed_C_rows(m['assets']['atom_source'], identities, guard)
        extraction_receipt = dict(mother_source_sha256=m['assets']['atom_source']['sha256'], fixed_identity_manifest_sha256=m['assets']['fixed_identities']['sha256'], raw_rows=[dict(input_id=identity_id(i), raw_line_sha256=text_sha(C_raw[identity_id(i)])) for i in identities if i['nucleus'] == '13C'])
        write_json(out / 'C_extraction_receipt.json', extraction_receipt)
        C_context = make_C_context(C_raw, identities, m['assets']['atom_source']['sha256'], sha(out / 'C_extraction_receipt.json'), m['assets']['C_identity_ledger']['sha256'], empty, context)
        write_json(out / 'C_derived_cohort_and_rule.json', C_context)
        C_results = {}
        for identity in identities:
            if identity['nucleus'] != '13C':
                continue
            guard()
            iid = identity_id(identity)
            try:
                C_results[iid] = produce_C_test_reference(C_raw[iid], identity, C_context, context, guard)
            except (ValueError, KeyError, TypeError, RuntimeError) as exc:
                C_results[iid] = dict(public=None, reference_admitted=False, reason='C_actual_producer_unknown:' + str(exc), hidden=dict(raw_json_line=C_raw[iid]))
        H_results = process_H_stage_A(m, identities, context, out, guard)
        assembly_started = time.monotonic()

        def assembly_guard():
            guard()
            need(time.monotonic() - assembly_started < 120, 'assembly-only120s deadline')
        artifacts = write_stage_A_outputs(out, identities, H_results, C_results, assembly_guard)
        for name, item in m['assets'].items():
            need(sha(item['path'], guard) == item['sha256'], 'mother source post-SHA:' + name)
        receipt.update(status='complete', exit_code=0, artifacts=artifacts, inputs=m['assets'], codes=m['codes'], H_asset_mode=m['H_asset_mode']['mode'], H_fixed_test_assignment_metrics='unavailable' if m['H_asset_mode']['mode'] == 'unavailable' else 'requires_actual_admission_review', original_H_fixed_test_completion=False, source_admission_method='actual original-row extraction + reviewed C producer/full structural transport; H original index producer or unknown')
    except BaseException as exc:
        receipt['error'] = type(exc).__name__ + ':' + str(exc)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        receipt.update(finished_UTC=utc(), elapsed_seconds=time.monotonic() - started, stage_B_authorized=False)
        write_json(out / 'receipt.json', receipt)

def main():
    _config()
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, default=D / 'TEST_STAGE_A_EXTRACTION_MANIFEST.json')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--owner-release')
    p.add_argument('--owner-release-sha256')
    p.add_argument('--check-B-release', action='store_true')
    args = p.parse_args()
    if args.check_B_release:
        check_B_release(args.owner_release, args.owner_release_sha256, args.manifest)
    elif args.execute:
        run_A(args.manifest, args.owner_release, args.owner_release_sha256)
    else:
        metadata = stage_A_metadata_preflight(args.manifest)
        m = json.loads(args.manifest.read_text())
        print(json.dumps(dict(status='CHECK_ONLY_TEST_SEALED', C_control_metadata_preflight=metadata, manifest_sha256=sha(args.manifest), implementation_status=m['implementation_status'], source_implementation_sha256=sha(__file__), test_values_read=False, models=0, solves=0, scores=0)))
if __name__ == '__main__':
    main()
