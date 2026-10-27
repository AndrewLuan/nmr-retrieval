# 功能概述：外层公开迁移副本；科学校验主体源自冻结producer，源码SHA与原运行SHA分开。
# 关系与接口：portable_runtime从显式--runtime-manifest读取路径/绑定/身份常量；缺项拒绝。
# 副作用：原函数及main保持原接口；执行仍要求原准入、预算、完整mapping与输入receipt。
from portable_runtime import repository, workspace, artifact_path, binding, render
'功能概述：从已冻结公共匿名cohort构建共享H211/C原生预测cache，非评价或训练入口。\npublic_record只接结构、实际条件、opaque input_id及匿名bin；bin完全不进入模型对象。\nrebuild_counts流式复用historical prepare的predicted-only/冲突删除，仅保留所需结构计数。\nrun顺序各加载一次H/C，安全weights_only+strict state；dedup_key仅结构与原生条件特征，\n不含input_id、observations或来源。每input输出引用共享raw/native_adapter载体，失败不替换。\nH assignment width按node_classes(batch)[owners]绑定原始九类float；C为显式2ppm fixed prior。\n原生values、ppm缩放、component_mass及assignment width证据分开，宽度不改原生中心。\ngraph_snapshot输出与source_transport同字段的native canonical图及RDKit版本供JJ比对。\nstage持久化started/completed/validated计数与partial receipt；complete需全输入成功及hash闭包。\n关系：通过PYTHONPATH指定冻结源码bundle，不改旧远端repo/探针；复用native_adapter/mapping。\n输入：cohort/asset/资源plan均须外部SHA冻结；execution_authorized形状不代替owner审批或\n准入审核。plan必须显式Python路径/CPU2/GPU0/RSS8GiB及wall/load/forward预算，不硬编码样本数。\n输出只新目录JSONL/manifest/receipt，无优化器、反传、拟合、指标、自动重试或外部API。\n'
import argparse, contextlib, gc, hashlib, json, math, os, resource, signal, sys, time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
NOM_SHA = binding('build_frozen_prediction_cache.sha_or_identity.1')
WIDTH_SHA = binding('build_frozen_prediction_cache.sha_or_identity.2')
COUNT_SHA = {'structures': binding('build_frozen_prediction_cache.sha_or_identity.3'), 'predictions': binding('build_frozen_prediction_cache.sha_or_identity.4')}
CONDITIONS = {'solvent', 'frequency', 'pH', 'ph', 'temperature', 'NMR_solvent'}
DEADLINE = float('inf')
RSS_LIMIT = 8589934592

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def json_rows(path):
    with open(path) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def public_record(row):
    need(isinstance(row, dict) and set(row) <= {'input_id', 'nucleus', 'smiles', 'actual_conditions', 'observations'}, 'public_whitelist')
    need(all((k in row for k in ('input_id', 'nucleus', 'smiles', 'actual_conditions'))), 'public_required_fields')
    need(isinstance(row['input_id'], str) and bool(row['input_id']), 'opaque_input_id_required')
    need(row['nucleus'] in ('1H', '13C') and isinstance(row['smiles'], str), 'public_structure_nucleus')
    c = row['actual_conditions']
    need(isinstance(c, dict) and set(c) <= CONDITIONS, 'actual_condition_whitelist')
    need(all((v is None or (isinstance(v, (str, int, float)) and (not isinstance(v, bool))) for v in c.values())), 'actual_condition_scalar')
    if 'observations' in row:
        need(isinstance(row['observations'], list), 'anonymous_observations_list')
        for obs in row['observations']:
            need(isinstance(obs, dict) and set(obs) == {'bin_id', 'ppm_decimal'}, 'anonymous_bin_whitelist')
            need(isinstance(obs['bin_id'], str) and isinstance(obs['ppm_decimal'], str), 'anonymous_bin_strings')
    native = dict(smiles=row['smiles'], experimental_conditions={k: v for k, v in c.items() if k != 'NMR_solvent'})
    if 'NMR_solvent' in c:
        native['source_metadata'] = {'NMR_solvent': c['NMR_solvent']}
    return (row['input_id'], row['nucleus'], native)

def dedup_key(nucleus, canonical, cond, condition_vector):
    return digest(dict(nucleus=nucleus, canonical_smiles=canonical, native_cond=cond, recovered_condition_vector=condition_vector))

def input_join_metadata(actual_conditions):
    return dict(actual_conditions_sha256=digest(actual_conditions), cache_key_semantics='native_encoded_features_only')

def rebuild_counts(structures_path, predictions_path, wanted, identity):
    structures = {}
    for row in json_rows(structures_path):
        try:
            smi = identity(row['source_smiles'])[0]
        except ValueError:
            continue
        if smi in wanted:
            structures[row['record_id']] = smi
        else:
            structures.pop(row['record_id'], None)
    registry = {}
    conflicts = set()
    for row in json_rows(predictions_path):
        if row['record_id'] not in structures:
            continue
        smi = structures[row['record_id']]
        counts = {n: v['count'] for n, v in row['nuclei'].items() if v.get('status') == 'predicted'}
        if smi in registry and registry[smi] != counts:
            conflicts.add(smi)
        registry[smi] = counts
    for smi in conflicts:
        registry.pop(smi, None)
    return (registry, conflicts)

def graph_snapshot(mol):
    return dict(atoms=[dict(index=a.GetIdx(), z=a.GetAtomicNum(), isotope=a.GetIsotope(), charge=a.GetFormalCharge(), radicals=a.GetNumRadicalElectrons(), aromatic=a.GetIsAromatic(), chiral_tag=str(a.GetChiralTag())) for a in mol.GetAtoms()], bonds=[dict(a=b.GetBeginAtomIdx(), b=b.GetEndAtomIdx(), kind=str(b.GetBondType()), aromatic=b.GetIsAromatic(), stereo=str(b.GetStereo()), stereo_atoms=list(b.GetStereoAtoms())) for b in mol.GetBonds()])

def peak_rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)

def monitor(*_):
    need(time.monotonic() < DEADLINE, 'wall_budget')
    need(peak_rss() <= RSS_LIMIT, 'RSS_budget')

def main():
    p = argparse.ArgumentParser()
    for name in ('cohort', 'cohort-sha256', 'assets-manifest', 'assets-sha256', 'plan', 'plan-sha256', 'out'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    tracked = {}
    reported = set()
    rows = []
    actual_condition_joins = {}
    receipt = dict(status='partial', forward_started=0, forward_completed=0, forward_validated=0, input_count=0, input_success=0, input_failed=0, input_not_started=0, dedup_hits=0, model_loads={}, updates=0, CPU_threads=2, GPU_devices=0)

    def write_json(name, value):
        tmp = out / (name + '.tmp')
        with tmp.open('w') as f:
            json.dump(value, f, allow_nan=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(out / name)

    def emit(name, value):
        if name == 'inputs.jsonl':
            value = dict(value, **actual_condition_joins[value['input_id']])
        with (out / name).open('a') as f:
            f.write(json.dumps(value, allow_nan=False) + '\n')
            f.flush()
            os.fsync(f.fileno())

    def stage(name, **extra):
        receipt.update(seconds=time.monotonic() - started, peakRSS_bytes=peak_rss(), last_stage=name)
        emit('stages.jsonl', dict(stage=name, **receipt, **extra))
        write_json('receipt.partial.json', receipt)

    def freeze(path, expected):
        path = str(Path(path).resolve())
        actual = sha(path)
        need(actual == expected, 'pre_hash:' + path)
        tracked[path] = actual
        return path
    try:
        plan = json.loads(Path(freeze(a.plan, a.plan_sha256)).read_text())
        need(plan['schema'] == 'frozen_prediction_cache_plan_v1' and plan['execution_authorized'] is True, 'execution_not_released')
        need(plan['CPU_threads'] == 2 and plan['GPU_devices'] == 0 and (plan['RSS_limit_bytes'] == 8589934592), 'resource_plan')
        need(str(Path(sys.executable).resolve()) == str(Path(plan['python_executable']).resolve()), 'python_runtime')
        for key in ('wall_seconds_total', 'load_seconds_per_model', 'forward_seconds_per_model', 'max_forward_started'):
            need(type(plan[key]) in (int, float) and plan[key] > 0, 'positive_explicit_budget:' + key)
        need(type(plan['max_forward_started']) is int and type(plan['input_count']) is int and (plan['input_count'] >= 0), 'integer_cohort_forward_budgets')
        global DEADLINE, RSS_LIMIT
        RSS_LIMIT = plan['RSS_limit_bytes']
        total_deadline = started + plan['wall_seconds_total']
        DEADLINE = total_deadline
        signal.signal(signal.SIGALRM, monitor)
        signal.setitimer(signal.ITIMER_REAL, 0.1, 0.1)
        os.environ.update(CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
        cohort = freeze(a.cohort, a.cohort_sha256)
        assets = json.loads(Path(freeze(a.assets_manifest, a.assets_sha256)).read_text())
        need(assets['schema'] == 'frozen_prediction_assets_v1', 'assets_schema')
        required_assets = {'nomination', 'H_width', 'numeric_config', 'numerical_release', 'structures', 'predictions', 'scope_release'}
        need(set(assets['files']) == required_assets, 'asset_file_whitelist')
        files = {k: freeze(v['path'], v['sha256']) for k, v in assets['files'].items()}
        need(sha(files['nomination']) == NOM_SHA and sha(files['H_width']) == WIDTH_SHA, 'approved_model_width_asset')
        for key, want in COUNT_SHA.items():
            need(sha(files[key]) == want, 'historical_count_asset:' + key)
        bundle = Path(assets['bundle_root']).resolve()
        actual_sources = {str(x.relative_to(bundle)): x for pkg in ('nmr_transfer', 'nmr_assignment') for x in (bundle / pkg).rglob('*.py')}
        need(set(actual_sources) == set(assets['source_files']), 'source_closure_file_set')
        for rel, path in actual_sources.items():
            freeze(path, assets['source_files'][rel])
        freeze(__file__, assets['runner_sha256'])
        sys.path.insert(0, str(bundle))
        import torch
        torch.set_num_threads(2)
        torch.set_num_interop_threads(2)
        from rdkit import Chem, rdBase
        receipt['rdkit_version'] = rdBase.rdkitVersion
        from torch_geometric.data import Batch
        from nmr_transfer.data import identity, graph, condition, physical_features
        from nmr_transfer.h_conditions import local_environment
        from nmr_transfer.h_acyl import acyl_environment
        from nmr_transfer.h_metadata import raw_conditions
        from nmr_transfer.h_uncertainty import node_classes, CLASSES
        from nmr_transfer.emission_model import make_model
        from nmr_assignment.native_adapter import adapt_native_predictions
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and str(Path(path).resolve()).startswith(str(bundle) + os.sep) and str(path).endswith('.py'):
                need(str(Path(path).resolve()) in tracked, 'imported_source_outside_closure')
        nom = json.loads(Path(files['nomination']).read_text())
        width = json.loads(Path(files['H_width']).read_text())
        numeric = json.loads(Path(files['numeric_config']).read_text())
        need(width['classes'] == list(CLASSES) and len(width['selected_ppm']) == 9, 'H_class_order')
        info = numeric['source_frozen_information']
        need(info['H_width_sha256'] == WIDTH_SHA and [info['H_widths_ppm'][x] for x in CLASSES] == width['selected_ppm'], 'H_exact_width_binding')
        need(info['C_width_ppm'] == 2 and info['C_width_source'] == 'fixed_error_scale_prior_no_qualified_C_residual_fit', 'C_fixed_assignment_prior')
        scope = json.loads(Path(files['scope_release']).read_text())
        need(scope['schema'] == 'prediction_cache_scope_release_v1' and scope['production_cache_authorized'] is True and (scope['cohort_sha256'] == a.cohort_sha256), 'cohort_scope_not_released')
        need(scope['checkpoint_sha256'] == {n: nom[k]['sha256'] for n, k in (('1H', 'H'), ('13C', 'C'))}, 'scope_model_binding')
        rows = []
        ids = set()
        wanted = set()
        for row in json_rows(cohort):
            input_id, nucleus, native = public_record(row)
            need(input_id not in ids, 'duplicate_input_id')
            ids.add(input_id)
            actual_condition_joins[input_id] = input_join_metadata(row['actual_conditions'])
            try:
                mol = Chem.MolFromSmiles(native['smiles'])
                need(mol is not None, 'invalid_structure')
                need(not any((atom.GetIsotope() for atom in mol.GetAtoms())), 'isotope_scope_not_supported')
                canonical = identity(native['smiles'])[0]
                wanted.add(canonical)
                rows.append((input_id, nucleus, native, canonical, None))
            except Exception as exc:
                rows.append((input_id, nucleus, native, None, type(exc).__name__ + ':' + str(exc)))
        receipt['input_count'] = len(rows)
        need(len(rows) == plan['input_count'], 'frozen_cohort_count')
        registry, conflicts = rebuild_counts(files['structures'], files['predictions'], wanted, identity)
        stage('metadata_ready', RDKit_version=rdBase.rdkitVersion, unique_structures=len(wanted), structural_count_conflicts=len(conflicts))
        cache = {}
        failed_keys = set()
        model = None
        real_load = torch.load
        for nucleus, key in (('1H', 'H'), ('13C', 'C')):
            subset = [row for row in rows if row[1] == nucleus]
            if not subset:
                continue
            spec = nom[key]
            checkpoint = freeze(spec['checkpoint'], spec['sha256'])
            freeze(spec['training_config'], spec['training_config_sha256'])
            if key == 'H':
                freeze(nom['H']['registry']['path'], nom['H']['registry']['sha256'])
            DEADLINE = min(total_deadline, time.monotonic() + plan['load_seconds_per_model'])

            @contextlib.contextmanager
            def safe_load():
                allowed = {str(Path(checkpoint).resolve())}
                if key == 'H':
                    allowed.add(str(Path(nom['H']['registry']['path']).resolve()))

                def load(path, *args, **kwargs):
                    resolved = str(Path(path).resolve())
                    need(resolved in allowed and (not args), 'unapproved_load')
                    kwargs.update(weights_only=True, map_location='cpu')
                    stage('before_safe_load', nucleus=nucleus, path=resolved)
                    result = real_load(path, **kwargs)
                    stage('after_safe_load', nucleus=nucleus, path=resolved)
                    return result
                torch.load = load
                try:
                    yield
                finally:
                    torch.load = real_load
            with safe_load():
                payload = torch.load(checkpoint, weights_only=True, map_location='cpu')
                cfg = payload['args']
                expected = dict(nucleus=nucleus, model=spec['model'], width=256, layers=3)
                if key == 'H':
                    for name in ('condition_mode', 'response_mode', 'message_mode', 'context_depth', 'equivalence_mode', 'count_decode', 'use_frozen_embedding', 'joint_reporting', 'amide_gap_scale'):
                        expected[name] = spec['lineage'][name]
                    expected.update(equivalence_registry_path=nom['H']['registry']['path'], equivalence_registry_sha256=nom['H']['registry']['sha256'])
                else:
                    expected['mode'] = 'domain'
                    if 'seed' in cfg:
                        expected['seed'] = 21
                    need(not cfg.get('count_decode', False), 'C_count_decode')
                for name, value in expected.items():
                    need(cfg.get(name) == value, 'config:' + name)
                need(not any(('sigma' in name for name in payload['state_dict'])), 'unexpected_native_sigma_head')
                stage('before_model_construction', nucleus=nucleus)
                model = make_model(cfg)
                stage('after_model_construction', nucleus=nucleus)
                need(type(model).__module__ + '.' + type(model).__name__ == spec['model_class'], 'class_mismatch')
                model.load_state_dict(payload['state_dict'], strict=True)
                stage('after_strict_load', nucleus=nucleus)
            for module_name, module in tuple(sys.modules.items()):
                if module_name == 'nmr_transfer' or module_name.startswith(('nmr_transfer.', 'nmr_assignment.')):
                    path = getattr(module, '__file__', None)
                    if path:
                        need(str(Path(path).resolve()) in tracked, 'imported_native_source_outside_bundle')
            del payload
            gc.collect()
            model.eval()
            for param in model.parameters():
                param.requires_grad_(False)
            receipt['model_loads'][nucleus] = 1
            DEADLINE = min(total_deadline, time.monotonic() + plan['forward_seconds_per_model'])
            for input_id, _, native, canonical, pre_error in subset:
                ck = None
                try:
                    if pre_error:
                        raise ValueError(pre_error)
                    cond = condition(native)
                    cond[0] = 0.0
                    recovered = raw_conditions(native)[0] if key == 'H' else None
                    cond_tensor = torch.tensor(cond, dtype=torch.float32).reshape(1, 4)
                    vector = torch.tensor(recovered['vector']).reshape(1, -1) if recovered else None
                    ck = dedup_key(nucleus, canonical, cond_tensor.tolist(), vector.tolist() if vector is not None else None)
                    if ck in failed_keys:
                        raise ValueError('same_native_key_previously_failed_no_retry')
                    if ck in cache:
                        receipt['dedup_hits'] += 1
                        receipt['input_success'] += 1
                        emit('inputs.jsonl', dict(input_id=input_id, nucleus=nucleus, status='ok', cache_key=ck, deduplicated=True))
                        reported.add(input_id)
                        stage('input_deduplicated', input_id=input_id)
                        continue
                    g = graph(canonical)
                    g.structure_smiles = canonical
                    g.cond = cond_tensor
                    g.physics = torch.tensor(physical_features(canonical, registry.get(canonical))).reshape(1, 8)
                    g.modality_is_theory = torch.tensor([False])
                    if key == 'H':
                        g.local_environment = torch.tensor(local_environment(canonical))
                        g.acyl_environment = torch.tensor(acyl_environment(canonical).copy())
                        g.condition_vector = vector
                    b = Batch.from_data_list([g])
                    monitor()
                    need(receipt['forward_started'] < plan['max_forward_started'], 'forward_count_budget')
                    receipt['forward_started'] += 1
                    stage('forward_started', input_id=input_id, cache_key=ck)
                    with torch.inference_mode():
                        d = model(b, details=True)
                    receipt['forward_completed'] += 1
                    stage('forward_completed', input_id=input_id, cache_key=ck)
                    values, mass, owners, groups = [d[k].detach().cpu() for k in ('values', 'weights', 'owners', 'groups')]
                    need(len(values) == len(mass) == len(owners) == len(groups) and len(values) > 0, 'component_shapes')
                    need(bool(torch.isfinite(values).all() and torch.isfinite(mass).all() and (mass > 0).all() and (groups == 0).all()), 'component_numeric')
                    mol = Chem.AddHs(Chem.MolFromSmiles(canonical))
                    parents = {}
                    for atom in mol.GetAtoms():
                        count = sum((n.GetAtomicNum() == 1 for n in atom.GetNeighbors())) if key == 'H' and atom.GetAtomicNum() != 1 else int(key == 'C' and atom.GetAtomicNum() == 6)
                        if key == 'H' and atom.GetAtomicNum() == 1 and (not any((n.GetAtomicNum() != 1 for n in atom.GetNeighbors()))):
                            count = 1
                        if count:
                            parents[str(atom.GetIdx())] = count
                    need(set(owners.tolist()) == {int(p) for p in parents}, 'owner_coverage')
                    for parent, count in parents.items():
                        need(abs(float(mass[owners == int(parent)].sum()) - count) < 1e-05, 'parent_mass')
                    known = bool(b.equivalence_known[0]) if key == 'H' else False
                    layout = {name: getattr(b, name).detach().cpu().tolist() for name in ('equivalence_ids', 'equivalence_known', 'preserved_group_orbits', 'preserved_group_ordinal', 'preserved_group_sizes') if hasattr(b, name)}
                    tags = node_classes(b)[d['owners']].detach().cpu().tolist() if key == 'H' else [None] * len(values)
                    sigmas = [width['selected_ppm'][tag] for tag in tags] if key == 'H' else [2.0] * len(values)
                    sigma_source = 'historical_H211_train_parent_class_width:' + WIDTH_SHA if key == 'H' else 'fixed_error_scale_prior_no_qualified_C_residual_fit:' + sha(files['numeric_config'])
                    centers = [float(x) * (10 if key == 'H' else 200) for x in values]
                    evidence = dict(nucleus=nucleus, parent_mass=parents, isotope_count_verified=True, evidence_ids=['native_graph:' + ck + ':' + rdBase.rdkitVersion], partition_hypothesis_id='H_registry:' + nom['H']['registry']['sha256'] if known else 'unresolved_parent_pool' if key == 'H' else 'carbon_atom_capacity')
                    if known:
                        evidence['partition_evidence_ids'] = ['H_registry:' + nom['H']['registry']['sha256']]
                    pred = adapt_native_predictions(evidence, centers_ppm=centers, masses=mass.tolist(), owners=owners.tolist(), graph_indices=groups.tolist(), sigma_ppm=sigmas, sigma_sources=[sigma_source] * len(values), known_h_layout=known, layout_evidence_ids=['native_layout:' + ck] if known else [], attachment_evidence_ids=['native_preserved_orbits:' + ck] if known else [], equivalence_ids=layout.get('equivalence_ids') if key == 'H' else None, preserved_group_orbits=layout['preserved_group_orbits'][0] if known else None, preserved_group_ordinal=layout['preserved_group_ordinal'][0] if known else None, preserved_group_sizes=layout['preserved_group_sizes'][0] if known else None)
                    raw = dict(cache_key=ck, nucleus=nucleus, canonical_smiles=canonical, rdkit_version=rdBase.rdkitVersion, native_graph_recipe='AddHs(MolFromSmiles(canonical_isomeric_heavy_SMILES))', native_graph_snapshot=graph_snapshot(mol), native_graph_snapshot_sha256=digest(graph_snapshot(mol)), native_values=values.tolist(), center_scale=10 if key == 'H' else 200, centers_ppm=centers, component_mass=mass.tolist(), owners=owners.tolist(), groups=groups.tolist(), native_sigma_ppm=None, native_sigma_source='no_trained_native_sigma_head', layout=layout, native_cond=cond_tensor.tolist(), recovered_condition_vector=vector.tolist() if vector is not None else None, assignment_width_ppm=sigmas, assignment_width_class=tags, assignment_width_source=sigma_source, predictions=asdict(pred))
                    emit('predictions.jsonl', raw)
                    cache[ck] = True
                    receipt['forward_validated'] += 1
                    receipt['input_success'] += 1
                    emit('inputs.jsonl', dict(input_id=input_id, nucleus=nucleus, status='ok', cache_key=ck, deduplicated=False))
                    reported.add(input_id)
                    stage('forward_validated', input_id=input_id, cache_key=ck)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as exc:
                    if ck:
                        failed_keys.add(ck)
                    receipt['input_failed'] += 1
                    emit('inputs.jsonl', dict(input_id=input_id, nucleus=nucleus, status='failed_retained', cache_key=ck, error=type(exc).__name__ + ':' + str(exc)))
                    reported.add(input_id)
                    stage('input_failed_retained', input_id=input_id)
                    monitor()
                    if str(exc).startswith(('forward_count_budget', 'wall_budget', 'RSS_budget', 'unapproved_load')):
                        raise
            del model
            model = None
            gc.collect()
        DEADLINE = total_deadline
        need(receipt['input_success'] + receipt['input_failed'] == receipt['input_count'], 'input_accounting')
        receipt['status'] = 'complete' if receipt['input_failed'] == 0 else 'partial_with_retained_failures'
    except BaseException as exc:
        receipt.update(status='failed_partial', error=type(exc).__name__ + ':' + str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for input_id, nucleus, _, _, _ in rows:
            if input_id not in reported:
                emit('inputs.jsonl', dict(input_id=input_id, nucleus=nucleus, status='not_started_retained', error='batch_aborted_no_retry'))
                receipt['input_not_started'] += 1
        post = {}
        for path, before in tracked.items():
            try:
                post[path] = sha(path)
                if post[path] != before:
                    receipt.update(status='failed_partial', hash_closure_error=path)
            except Exception as exc:
                receipt.update(status='failed_partial', hash_closure_error=str(exc))
        receipt.update(seconds=time.monotonic() - started, peakRSS_bytes=peak_rss(), pre_hashes=tracked, post_hashes=post)
        if 'total_deadline' in locals() and time.monotonic() > total_deadline:
            receipt.update(status='failed_partial', resource_error='total_wall_budget_including_hash_closure')
        if receipt['peakRSS_bytes'] > RSS_LIMIT:
            receipt.update(status='failed_partial', resource_error='RSS_budget')
        write_json('receipt.json', receipt)
        outputs = {name: sha(out / name) for name in ('inputs.jsonl', 'predictions.jsonl', 'stages.jsonl') if (out / name).exists()}
        write_json('manifest.json', dict(schema='frozen_prediction_cache_manifest_v1', status=receipt['status'], cohort_sha256=a.cohort_sha256, assets_sha256=a.assets_sha256, plan_sha256=a.plan_sha256, outputs=outputs, center_contract='same frozen centers for B0/B1/B2; mass is component_mass, not observed integral', assignment_width_contract='separate from native sigma; H original classfloat/C2ppm fixed prior', forwards=dict(started=receipt['forward_started'], completed=receipt['forward_completed'], validated=receipt['forward_validated'])))
        print(json.dumps(receipt, allow_nan=False), flush=True)
    return 0 if receipt['status'] == 'complete' else 1
if __name__ == '__main__':
    sys.exit(main())
