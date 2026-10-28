"""功能：在显式训练放行后执行 H211 等价中心头的配对 A/B 训练。

数据运输复用 ReplaySpectra 和原 reviewed_objective；模型只接结构、条件与物理特征。
原始谱与稳定母节点标签只进入损失批次。完整酰胺甲基保留旧分组，部分标签不得补 H。
固定支持由 assignment_margin 提供；每步只替换 component:i 中心，不重建门控。
本模块不选择 checkpoint、不访问验证或测试；任何认证失败使整对训练停止。
真实权重载入由调用方在 validate_release 成功后提供；导入模块不载入模型。
本文件是 JJ 三作业completion待审核 staging，不覆盖原trainer或旧包。完成作业后释放局部持有者并显式回收环。main 在并行工作前固定原producer
的CPU线程2/interop2，独占写 trainer_runtime_claim.json；初始化使用原producer的
eval、全参数冻结和 inference_mode。batch8原损失与其余科学参数保持原样。
本delta仅取消batch teacher中心对singleton输出的跨上下文字面相等要求；singleton
初始化仍exact。同批teacher锚保持不变，teacher初始state/runtime按job持久绑定。

公开接口：dataset_from_records 返回有标签的 ReplaySpectra；feature_batch 返回白名单图。
prepare_run 核对 release、run-config、源码和逐条支持摘要，返回已绑定的数据与支持。
initialize_native_bindings 仅在放行后比较真实初始中心、父节点质量及注册布局。
train_step 执行一次 A/B 梯度；paired_train 固定顺序、轮数和最终保存，异常传播并记停机。
main 是唯一完整 CLI 接线：--run-config --release --out；缺少真实放行即拒绝载入权重。
"""
from __future__ import annotations
import copy
import gc
import datetime
import hashlib
import json
import math
import os
import random
import time
from pathlib import Path
import torch
from torch_geometric.data import Batch
from .h_replaytrain import ReplaySpectra, amide_groups
from .h_conditions import local_environment
from .h_labels import make_key
from .data import graph, quantiles

CHECKPOINT_SHA256 = '2d5c96533794c52a424ae5092f2e377a30c2ba85b5dd15d1c68bd92bea46f24f'
# Frozen nomination 07ada18e634cefff755ae46533370df3e2e3a3bb78679d6058dc62e7fa57ca85;
# only its metadata was read while implementing relocation, never the registry bytes.
REGISTRY_SHA256 = '9596526cb4c9433c562bf0953a77633d1febcf27dd1b38c95a3e021b51304329'
FEATURE_KEYS = frozenset(('x','edge_index','edge_attr','batch','ptr','structure_smiles','cond','physics','condition_vector','modality_is_theory','local_environment','acyl_environment'))
SEEDS = (211, 193)
MARGIN_ACCOUNTING_KEYS=('G_certified_count','A_certified_count','certified_pair_count','solver_calls','G_elapsed_seconds','A_elapsed_seconds','solver_elapsed_seconds','margin_record_elapsed_seconds')

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def validate_release(path, input_ids):
    r=json.loads(Path(path).read_text())
    if r.get('training_release') is not True: raise ValueError('training_release_closed')
    if r.get('checkpoint_sha256') != CHECKPOINT_SHA256: raise ValueError('checkpoint_binding')
    if r.get('admitted_input_ids') != list(input_ids) or len(set(input_ids))!=len(input_ids): raise ValueError('admitted_identity_order')
    for key in ('inputs','sources'):
        if not r.get(key): raise ValueError('release_missing_'+key)
        for ref in r[key].values():
            if sha256(ref['path'])!=ref['sha256']: raise ValueError('release_digest')
    if r.get('complete_G_feasibility_certified') is not True: raise ValueError('G_feasibility_pending')
    return r

def safe_grouping(g, experimental=True):
    g.group_targets=g.site_targets.clone();g.group_mask=g.site_mask.clone()
    g.group_expected=g.site_expected.clone();g.group_owner=torch.arange(len(g.x));g.group_site_weight=torch.ones(len(g.x))
    counts={'complete_merges':0,'blocked_partial':0}
    if experimental:
        for n,parents in amide_groups(g):
            if g.site_expected[n]>0: continue
            observed=[g.site_targets[p][g.site_mask[p]] for p in parents]
            if not any(len(v) for v in observed): continue
            if any(len(v)!=3 for v in observed): counts['blocked_partial']+=1;continue
            if any(float(v.max()-v.min())>.003 for v in observed): continue
            values=torch.cat([v.median().repeat(3) for v in observed])
            if len(values)>g.group_targets.shape[1]: raise ValueError('amide_capacity')
            g.group_targets[parents]=0;g.group_mask[parents]=False;g.group_expected[parents]=0
            g.group_targets[n]=0;g.group_mask[n]=False
            g.group_targets[n,:len(values)]=values;g.group_mask[n,:len(values)]=True
            g.group_expected[n]=6;g.group_owner[parents]=n;counts['complete_merges']+=1
    return counts

class MarginSpectra(ReplaySpectra):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,grouped=False,**kwargs)
    def __getitem__(self,i):
        g=super().__getitem__(i)
        g.local_environment=torch.tensor(local_environment(self.rows[i]['smiles']))
        counts=safe_grouping(g,self.rows[i]['domain']=='experimental')
        g.complete_merges=torch.tensor([counts['complete_merges']]);g.blocked_partial=torch.tensor([counts['blocked_partial']])
        return g

def dataset_from_records(features, supervision):
    if [r['input_id'] for r in features]!=[r['input_id'] for r in supervision]: raise ValueError('transport_identity_order')
    rows=[];graphs={};labels={};metadata={}
    for f,s in zip(features,supervision):
        if f['canonical_smiles']!=s['canonical_smiles']: raise ValueError('structure_binding')
        smi=f['canonical_smiles'];graphs.setdefault(smi,graph(smi))
        source=s['source_binding'];r=dict(smiles=smi,domain='experimental',source=source['source'],record_id=source['record_id'],q=quantiles(s['observed_source_values_ppm']),cond=f['cond'],physics=f['physics'],condition_vector=f['condition_vector'],review_spectral_weight=s['review_spectral_weight'])
        rows.append(r);labels[make_key(r)]={'groups':s['parent_values_ppm'],'full_atom_labels':s['full_atom_labels']}
        metadata[make_key(r)]={'vector':f['condition_vector']}
        if s['review_spectral_weight']==0 and s['parent_values_ppm']: raise ValueError('held_site_labels')
    return MarginSpectra(rows,graphs,'1H',metadata,annotations=labels)

def feature_batch(label_batch):
    out=Batch()
    for k in FEATURE_KEYS:
        if k in label_batch: out[k]=copy.deepcopy(label_batch[k])
    # Batch.num_graphs derives from ptr; no label field is copied.
    if set(out.keys())-FEATURE_KEYS: raise ValueError('label_leakage')
    return out

def configure_head(model):
    model.eval()
    selected=[]
    for name,p in model.named_parameters():
        p.requires_grad_(name.startswith('equivalence_head.'))
        if p.requires_grad:selected.append(p)
    if not selected: raise ValueError('missing_equivalence_head')
    return torch.optim.AdamW(selected,lr=3e-5,weight_decay=1e-4,eps=1e-8,betas=(.9,.999))

def frozen_state(model):
    allowed={k for k,_ in model.named_parameters() if k.startswith('equivalence_head.')}
    return {k:v.detach().clone() for k,v in model.state_dict().items() if k not in allowed}

def assert_state(model,expected):
    actual=model.state_dict()
    if any(not torch.equal(actual[k],v) for k,v in expected.items()): raise RuntimeError('noncenter_state_changed')

def epoch_order(n,seed):
    rng=random.Random(seed);out=[]
    for _ in range(10):
        ids=list(range(n));rng.shuffle(ids);out.append([ids[i:i+8] for i in range(0,n,8)])
    return out

def _finite_update_state(model,optimizer):
    for name,p in model.named_parameters():
        if p.requires_grad and not torch.isfinite(p.detach()).all():raise RuntimeError('nonfinite_head_parameter_after_step')
    def visit(value):
        if isinstance(value,torch.Tensor):
            if (value.is_floating_point() or value.is_complex()) and not torch.isfinite(value).all():raise RuntimeError('nonfinite_optimizer_state_after_step')
        elif isinstance(value,float):
            if not math.isfinite(value):raise RuntimeError('nonfinite_optimizer_state_after_step')
        elif isinstance(value,dict):
            for item in value.values():visit(item)
        elif isinstance(value,(tuple,list)):
            for item in value:visit(item)
    visit(optimizer.state)

def _margin_statistics(result):
    elapsed=[]
    for key in ('G','A_loss_augmented'):
        certificate=result[key]
        if certificate.get('status')!=0 or certificate.get('mip_gap')!=0:raise RuntimeError('uncertified_margin_return')
        seconds=float(certificate['elapsed_seconds'])
        if not math.isfinite(seconds) or seconds<0:raise RuntimeError('invalid_margin_elapsed')
        elapsed.append(seconds)
    record_seconds=float(result['elapsed_seconds'])
    if not math.isfinite(record_seconds) or record_seconds<0:raise RuntimeError('invalid_margin_elapsed')
    return dict(G_certified_count=1,A_certified_count=1,certified_pair_count=1,solver_calls=2,G_elapsed_seconds=elapsed[0],A_elapsed_seconds=elapsed[1],solver_elapsed_seconds=sum(elapsed),margin_record_elapsed_seconds=record_seconds)

def _check_teacher_state(teacher,expected):
    actual=teacher.state_dict()
    if set(actual)!=set(expected) or any(actual[k].shape!=v.shape or actual[k].dtype!=v.dtype or actual[k].device!=v.device or not torch.equal(actual[k],v) for k,v in expected.items()):raise RuntimeError('teacher_initial_state_changed')

def _bind_frozen_teacher(teacher,features):
    runtime=(torch.get_num_threads(),torch.get_num_interop_threads(),str(torch.get_default_dtype()),torch.get_float32_matmul_precision(),torch.are_deterministic_algorithms_enabled(),tuple(sorted(os.sched_getaffinity(0))) if hasattr(os,'sched_getaffinity') else None,tuple((k,os.environ.get(k)) for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','CUDA_VISIBLE_DEVICES','PYTHONHASHSEED')),tuple((k,str(features[k].dtype),str(features[k].device),features[k].requires_grad) for k in sorted(FEATURE_KEYS) if k in features and isinstance(features[k],torch.Tensor)))
    if not hasattr(teacher,'_assignment_initial_state'):
        teacher._assignment_initial_state={k:v.detach().clone() for k,v in teacher.state_dict().items()}
        teacher._assignment_runtime_signature=runtime
    if runtime!=teacher._assignment_runtime_signature:raise RuntimeError('teacher_runtime_changed')
    if any(p.requires_grad for p in teacher.parameters()):raise RuntimeError('teacher_not_frozen')
    _check_teacher_state(teacher,teacher._assignment_initial_state)
    return teacher._assignment_initial_state

def _check_feature_inputs(expected,*copies):
    for key in FEATURE_KEYS:
        for actual in copies:
            if (key in expected)!=(key in actual):raise RuntimeError('feature_input_missing_'+key)
            if key not in expected:continue
            x,y=expected[key],actual[key]
            if isinstance(x,torch.Tensor):
                if not isinstance(y,torch.Tensor) or x.shape!=y.shape or x.dtype!=y.dtype or x.device!=y.device or x.requires_grad!=y.requires_grad or not torch.equal(x,y):raise RuntimeError('feature_input_changed_'+key)
            elif x!=y:raise RuntimeError('feature_input_changed_'+key)

def train_step(model,teacher,label_batch,optimizer,*,variant,margin_records,margin_fn=None,old_objective=None,details_transform=None):
    if variant not in ('A','B'): raise ValueError('variant')
    from .h_reviewed_supervision import reviewed_objective
    from .h_condmodel import training_details
    model.eval();teacher.eval();features=feature_batch(label_batch)
    fixed=frozen_state(model);teacher_fixed=_bind_frozen_teacher(teacher,features)
    optimizer.zero_grad(set_to_none=True)
    student_features=features.clone();teacher_features=features.clone()
    for obj,b in ((model,student_features),(teacher,teacher_features)):
        for method in ('attach_layout','attach_orbits'):
            if hasattr(obj,method):getattr(obj,method)(b)
    signature_keys=('equivalence_ids','equivalence_offsets','equivalence_duplicates','equivalence_known','preserved_group_orbits','preserved_group_ordinal','preserved_group_sizes')
    for k in signature_keys:
        if (k in student_features)!=(k in teacher_features):raise RuntimeError('layout_signature_missing')
        if k in student_features and not torch.equal(student_features[k],teacher_features[k]):raise RuntimeError('layout_signature_'+k)
    _check_feature_inputs(features,student_features,teacher_features)
    details=model(student_features,details=True)
    with torch.no_grad(): initial=teacher(teacher_features,details=True)
    _check_feature_inputs(features,student_features,teacher_features)
    if not torch.isfinite(initial['values']).all() or not torch.isfinite(initial['quantiles']).all():raise RuntimeError('nonfinite_teacher_output')
    if initial['quantiles'].shape!=details['quantiles'].shape or initial['quantiles'].dtype!=details['quantiles'].dtype or initial['quantiles'].device!=details['quantiles'].device:raise RuntimeError('teacher_quantile_signature')
    for key in ('weights','owners','groups','exchangeable'):
        if key in initial and not torch.equal(details[key],initial[key]): raise RuntimeError('native_signature_'+key)
    for i,r in enumerate(margin_records):
        if initial['values'][initial['groups']==i].numel()!=len(r['support'].component_ids):raise ValueError('teacher_component_domain')
        if 'initial_component_signature' in r:
            mask=initial['groups']==i
            for key,expected in r['initial_component_signature'].items():
                current=initial[key][mask].detach().cpu()
                if key=='owners':current=current-int(features.ptr[i])
                if key=='groups':current=current-i
                if not torch.equal(current,expected):raise RuntimeError('initial_component_signature_'+key)
        if 'initial_layout_signature' not in r:continue
        lo=int(features.ptr[i]);hi=int(features.ptr[i+1])
        for key,value in r['initial_layout_signature'].items():
            current=student_features[key][lo:hi] if key=='equivalence_ids' else student_features[key][i:i+1]
            if not torch.equal(current.detach().cpu(),value):raise RuntimeError('initial_layout_changed_'+key)
    objective=old_objective or reviewed_objective;transform=details_transform or training_details
    old=objective(transform(details,label_batch),label_batch)['loss']
    anchor=(details['quantiles']-initial['quantiles'].detach()).abs().mean()
    total=old+.5*anchor; margins=[]
    accounting=dict(G_certified_count=0,A_certified_count=0,certified_pair_count=0,solver_calls=0,G_elapsed_seconds=0.,A_elapsed_seconds=0.,solver_elapsed_seconds=0.,margin_record_elapsed_seconds=0.)
    if variant=='B':
        if margin_fn is None:
            from nmr_assignment.assignment_margin import loss as margin_fn
        if len(margin_records)!=label_batch.num_graphs: raise ValueError('margin_record_count')
        for i,r in enumerate(margin_records):
            # Frozen producer converts each fp32 scalar to Python float before ppm scaling.
            centers=details['values'][details['groups']==i].double()*10
            if centers.numel()!=len(r['support'].component_ids): raise ValueError('component_domain')
            result=margin_fn(centers,r['support'],r['allowed_joint_parent_sets'],r['invariant_parent_sets'],r['model_unit_parent_sets'],r['solver_config'])
            for key,value in _margin_statistics(result).items():accounting[key]+=value
            margins.append(result['loss'])
        total=total+.005*torch.stack(margins).mean()
    if not torch.isfinite(total): raise RuntimeError('nonfinite_loss')
    constant_loss=not total.requires_grad
    if constant_loss:
        # No structural head path: retain the scheduled AdamW step (including decay),
        # without pretending the frozen emitted centers have a trainable gradient.
        total=total+sum(p.sum()*0 for p in model.parameters() if p.requires_grad)
    total.backward()
    head=[]
    for name,p in model.named_parameters():
        if name.startswith('equivalence_head.'):
            if p.grad is not None:
                if not torch.isfinite(p.grad).all():raise RuntimeError('nonfinite_head_gradient')
                head.append(p)
        elif p.grad is not None:raise RuntimeError('nonhead_gradient')
    if not head:raise RuntimeError('missing_head_gradient_path')
    if any(p.grad is not None for p in teacher.parameters()):raise RuntimeError('teacher_gradient')
    head_grad_norm=torch.nn.utils.clip_grad_norm_(head,2,error_if_nonfinite=True)
    assert_state(model,fixed)
    _check_teacher_state(teacher,teacher_fixed)
    step_returned=False
    try:
        optimizer.step();step_returned=True
        _finite_update_state(model,optimizer);assert_state(model,fixed)
        _check_teacher_state(teacher,teacher_fixed)
    except Exception as exc:
        exc.optimizer_step_entered=True;exc.optimizer_step_returned=step_returned
        exc.completed_step_margin_statistics=dict(accounting)
        raise
    return {'loss':float(total.detach()),'old_loss':float(old.detach()),'teacher_anchor':float(anchor.detach()),'margin_records':len(margins),'constant_loss_zero_head_gradient':constant_loss,'head_grad_norm':float(head_grad_norm),**accounting}

def identity_order_sha256(input_ids):
    return hashlib.sha256(json.dumps(input_ids,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()

def atomic_json(path,value):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n');os.replace(temporary,path)

def prepare_completion(plan_path,plan_sha,config_path,release_path,input_ids,output_directory):
    """绑定一次completion计划和保留A历史；只核checkpoint字节，不反序列化。"""
    release=validate_release(release_path,input_ids)
    ref=release.get('completion_plan')
    if not ref or Path(ref['path']).resolve()!=Path(plan_path).resolve() or ref['sha256']!=plan_sha or sha256(plan_path)!=plan_sha:raise ValueError('completion_plan_binding')
    plan=json.loads(Path(plan_path).read_text())
    required={'schema','run_config','trainer','continuation_contract','completed_segment_identity','prior_failed_attempts','remaining_jobs','retained_job','resources','output_directory'}
    if set(plan)!=required or plan['schema']!='H211_fixed_AB_completion_plan_v1':raise ValueError('completion_plan_schema')
    def checked(ref):
        if set(ref)!={'path','sha256'} or sha256(ref['path'])!=ref['sha256']:raise ValueError('completion_metadata_digest')
        return ref
    for key in ('run_config','trainer','continuation_contract','completed_segment_identity'):checked(plan[key])
    if Path(plan['run_config']['path']).resolve()!=Path(config_path).resolve() or plan['trainer']!=release['sources']['trainer']:raise ValueError('completion_executed_binding')
    if Path(plan['trainer']['path']).resolve()!=Path(__file__).resolve():raise ValueError('completion_trainer_path')
    if Path(output_directory).resolve()!=Path(plan['output_directory']).resolve()/'models':raise ValueError('completion_output_binding')
    contract=json.loads(Path(plan['continuation_contract']['path']).read_text())
    identity=json.loads(Path(plan['completed_segment_identity']['path']).read_text())
    schedule=[{'seed':211,'variant':'B','steps':770},{'seed':193,'variant':'A','steps':770},{'seed':193,'variant':'B','steps':770}]
    resources={'cpu_threads':2,'gpu_count':0,'max_wall_seconds':14084,'max_process_tree_rss_bytes':4294967296}
    if contract.get('schema')!='H211_completion_continuation_contract_v1' or contract.get('preparation_authorized') is not True:raise ValueError('completion_contract')
    for obj in (plan,contract):
        if obj['remaining_jobs']!=schedule or obj['retained_job']!='211_A' or obj['resources']!=resources or obj['output_directory']!=plan['output_directory']:raise ValueError('completion_fixed_schedule_resources')
    if contract['completed_segment_identity']!=plan['completed_segment_identity'] or contract['prior_failed_attempts']!=plan['prior_failed_attempts']:raise ValueError('completion_contract_refs')
    if set(plan['prior_failed_attempts'])!={'original_initialization','JJ_resource_stop'}:raise ValueError('completion_prior_attempts')
    for ref in plan['prior_failed_attempts'].values():checked(ref)
    if identity.get('schema')!='H211_completed_segment_identity_v1' or identity['original_H211_checkpoint_sha256']!=CHECKPOINT_SHA256 or contract['original_H211_checkpoint_sha256']!=CHECKPOINT_SHA256:raise ValueError('completion_original_start')
    if identity['ordered_training_records']!=len(input_ids) or len(input_ids)!=615 or identity['ordered_training_input_ids_sha256']!=identity_order_sha256(input_ids):raise ValueError('completion_training_order')
    for key in ('checkpoint','history','source_run_config','source_execution_receipt','source_execution_budget'):checked(identity[key])
    if identity['source_execution_receipt']!=plan['prior_failed_attempts']['JJ_resource_stop']:raise ValueError('completion_failed_receipt_binding')
    prior=json.loads(Path(identity['source_execution_receipt']['path']).read_text())
    if prior.get('success') is not False or prior.get('actual_child_exit')!=-15 or prior.get('actual_outer_exit')!=1:raise ValueError('completion_prior_terminal')
    original=json.loads(Path(plan['prior_failed_attempts']['original_initialization']['path']).read_text())
    if original.get('success') is not False or original.get('actual_child_exit')!=1 or original.get('actual_outer_exit')!=1:raise ValueError('completion_original_terminal')
    prior_config=json.loads(Path(identity['source_run_config']['path']).read_text())
    if prior_config['input_ids']!=list(input_ids):raise ValueError('completion_prior_identity')
    current_config=json.loads(Path(config_path).read_text())
    if set(prior_config['inputs'])!=set(current_config['inputs']) or any(prior_config['inputs'][k]['sha256']!=v['sha256'] for k,v in current_config['inputs'].items() if k!='support_manifest'):raise ValueError('completion_original_inputs')
    old_support=checked(prior_config['inputs']['support_manifest']);new_support=checked(current_config['inputs']['support_manifest'])
    def manifest_rows(ref):
        with Path(ref['path']).open() as stream:return [json.loads(line) for line in stream if line.strip()]
    old_rows=manifest_rows(old_support);new_rows=manifest_rows(new_support)
    if len(old_rows)!=len(new_rows):raise ValueError('completion_support_manifest_count')
    for before,after in zip(old_rows,new_rows):
        left=copy.deepcopy(before);right=copy.deepcopy(after)
        source=left['support_artifact'].pop('path');target=right['support_artifact'].pop('path')
        relative=Path(source).relative_to(Path(old_support['path']).parent)
        if '..' in relative.parts or str(Path(new_support['path']).parent/relative)!=target or left!=right:raise ValueError('completion_support_relocation')
        if sha256(target)!=after['support_artifact']['sha256']:raise ValueError('completion_support_payload_digest')
    job=dict(identity['completed_job']);checkpoint=identity['checkpoint']
    if (job['seed'],job['variant'],job['steps'],job['selection'])!=(211,'A',770,'final_epoch_10_only') or job['checkpoint']!=checkpoint['path'] or job['sha256']!=checkpoint['sha256']:raise ValueError('completion_retained_job')
    with Path(identity['history']['path']).open() as stream:history=[json.loads(line) for line in stream if line.strip()]
    expected=[];step=0
    for epoch,batches in enumerate(epoch_order(len(input_ids),211),1):
        for indices in batches:
            step+=1;batch_ids=[input_ids[i] for i in indices];expected.append(batch_ids)
            if len(history)<step:raise ValueError('completion_history_short')
            row=history[step-1]
            if (row['seed'],row['arm'],row['epoch'],row['step'])!=(211,'A',epoch,step) or row['cumulative_steps']!=step or row['batch_input_id_order_sha256']!=identity_order_sha256(batch_ids):raise ValueError('completion_history_order')
    order=identity_order_sha256(expected)
    if step!=770 or len(history)!=770 or order!=identity['actual_order_sha256'] or order!=job['actual_order_sha256']:raise ValueError('completion_order_digest')
    for seed in SEEDS:
        sequence=[[input_ids[i] for i in indices] for batches in epoch_order(len(input_ids),seed) for indices in batches]
        if identity_order_sha256(sequence)!=identity['expected_order_sha256_by_seed'][str(seed)]:raise ValueError('completion_expected_seed_order')
    provenance={'completion_plan_sha256':plan_sha,'continuation_contract':plan['continuation_contract'],'completed_segment_identity':plan['completed_segment_identity'],'retained_A_source':checkpoint,'prior_failed_receipts':[plan['prior_failed_attempts'][key] for key in ('original_initialization','JJ_resource_stop')]}
    return {'reused_result':job,'order_sha256':order,'provenance':provenance}

def paired_train(model_factory,dataset,margin_records,release_path,input_ids,output_directory,*,device='cpu',completion=None):
    """运行剩余三个固定作业；history逐步记录梯度/曝光，status原子记录阶段；失败终止整对。"""
    validate_release(release_path,input_ids)
    if completion is None:raise ValueError('completion_metadata_required')
    if len(dataset)!=len(input_ids) or len(margin_records)!=len(input_ids):raise ValueError('training_domain')
    out=Path(output_directory)
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True);results=[dict(completion['reused_result'])] if completion else [];cumulative_steps=0;orders={211:completion['order_sha256']} if completion else {};started=time.monotonic()
    def status(stage,**values):
        atomic_json(out/'status.json',dict(stage=stage,cumulative_steps=cumulative_steps,elapsed_seconds=time.monotonic()-started,job_solver_statistics=dict(job_accounting),**values))
    for seed in SEEDS:
        for variant in ('A','B'):
            if completion and seed==211 and variant=='A':continue
            random.seed(seed);torch.manual_seed(seed)
            steps=0;actual_order=[];epoch=0;job_started=time.monotonic();job_accounting={k:0 for k in MARGIN_ACCOUNTING_KEYS}
            model=teacher=optimizer=batch=metrics=p=None
            try:
                status('initializing',seed=seed,arm=variant,job_steps=steps)
                model=model_factory().to(device);teacher=copy.deepcopy(model).eval()
                for p in teacher.parameters():p.requires_grad_(False)
                optimizer=configure_head(model)
                for epoch,batches in enumerate(epoch_order(len(dataset),seed),1):
                    for indices in batches:
                        status('training_step',seed=seed,arm=variant,epoch=epoch,job_steps=steps)
                        batch=Batch.from_data_list([dataset[i] for i in indices]).to(device)
                        metrics=train_step(model,teacher,batch,optimizer,variant=variant,margin_records=[margin_records[i] for i in indices])
                        steps+=1;cumulative_steps+=1
                        for key in MARGIN_ACCOUNTING_KEYS:job_accounting[key]+=metrics[key]
                        batch_ids=[input_ids[i] for i in indices];actual_order.append(batch_ids)
                        history=dict(seed=seed,arm=variant,epoch=epoch,step=steps,cumulative_steps=cumulative_steps,elapsed_seconds=time.monotonic()-started,job_elapsed_seconds=time.monotonic()-job_started,batch_input_id_order_sha256=identity_order_sha256(batch_ids),**metrics,**{'job_cumulative_'+key:value for key,value in job_accounting.items()})
                        with (out/'history.jsonl').open('a') as stream:stream.write(json.dumps(history,allow_nan=False)+'\n')
                        status('step_complete',seed=seed,arm=variant,epoch=epoch,job_steps=steps)
                order_sha=identity_order_sha256(actual_order)
                if variant=='A':orders[seed]=order_sha
                elif orders.get(seed)!=order_sha:raise RuntimeError('paired_actual_order_mismatch')
                status('saving_final_epoch',seed=seed,arm=variant,epoch=epoch,job_steps=steps,actual_order_sha256=order_sha)
                path=out/f'{seed}_{variant}_epoch10.pt';torch.save(model.state_dict(),path)
                checkpoint_sha=sha256(path)
                results.append({'seed':seed,'variant':variant,'steps':steps,'actual_order_sha256':order_sha,'checkpoint':str(path),'sha256':checkpoint_sha,'selection':'final_epoch_10_only','job_elapsed_seconds':time.monotonic()-job_started,**job_accounting})
                status('job_complete',seed=seed,arm=variant,epoch=epoch,job_steps=steps,actual_order_sha256=order_sha)
            except Exception as exc:
                failed_statistics=getattr(exc,'completed_step_margin_statistics',None)
                atomic_json(out/'paired_stop.json',{'seed':seed,'variant':variant,'steps':steps,'cumulative_steps':cumulative_steps,'error':repr(exc),'retry':False,'failed_step_optimizer_entered':getattr(exc,'optimizer_step_entered',False),'failed_step_optimizer_returned':getattr(exc,'optimizer_step_returned',False),'rollback_performed':False,'job_solver_statistics_successful_steps':job_accounting,'failed_step_solver_statistics':failed_statistics,'failed_step_solver_calls_unknown':variant=='B' and failed_statistics is None})
                status('paired_stop',seed=seed,arm=variant,epoch=epoch,job_steps=steps,error=repr(exc))
                raise
            finally:
                model=teacher=optimizer=batch=metrics=p=None
                gc.collect()
    status('four_jobs_complete',paired_actual_orders_match=True)
    return results

def load_support(value):
    from nmr_assignment.assignment_margin import FixedSupport,CarrierSupport,EdgeSupport
    from nmr_assignment.costs import Observation
    d=dict(value)
    d['observations']=tuple(Observation(**x) for x in d['observations'])
    d['carriers']=tuple(CarrierSupport(**dict(x,source_component_ids=tuple(x['source_component_ids']),source_component_indices=tuple(x['source_component_indices']))) for x in d['carriers'])
    d['edges']=tuple(EdgeSupport(**dict(x,unit_ids=tuple(x['unit_ids']),carrier_combinations=tuple(tuple(y) for y in x['carrier_combinations']))) for x in d['edges'])
    for k in ('unit_ids','component_ids','missing_costs','unexplained_costs'):
        d[k]=tuple(tuple(x) if isinstance(x,list) else x for x in d[k])
    return FixedSupport(**d)

def _jsonl(ref):
    if sha256(ref['path'])!=ref['sha256']:raise ValueError('input_digest')
    rows=[json.loads(x) for x in Path(ref['path']).read_text().splitlines()]
    if len({r['input_id'] for r in rows})!=len(rows):raise ValueError('duplicate_input')
    return rows

def prepare_run(config_path,release_path):
    """在权重载入前封闭所有输入、源码和逐条支持引用。"""
    c=json.loads(Path(config_path).read_text());ids=c['input_ids']
    if set(c)-{'input_ids','inputs','device','constant_loss_policy'} or not ids:raise ValueError('run_config_schema')
    release=validate_release(release_path,ids)
    if c.get('constant_loss_policy')!='zero_head_gradient_preserve_steps' or release.get('constant_loss_policy')!=c['constant_loss_policy']:raise ValueError('owner_constant_loss_policy_required')
    if release.get('run_config_sha256')!=sha256(config_path):raise ValueError('run_config_binding')
    required=('features','supervision','admission','support_manifest','solver_config','checkpoint','equivalence_registry','scope_decision','scientific_protocol','numeric_config','feasibility_gate')
    if set(c['inputs'])!=set(required):raise ValueError('required_input_keys')
    if c['inputs']!=release['inputs']:raise ValueError('executed_input_binding')
    required_sources={'trainer','assignment_margin','reviewed_objective','replay','conditions','training_details','model_factory','model','data'}
    if set(release['sources'])!=required_sources:raise ValueError('required_source_keys')
    import importlib
    modules={'trainer':__name__,'assignment_margin':'nmr_assignment.assignment_margin','reviewed_objective':'nmr_transfer.h_reviewed_supervision','replay':'nmr_transfer.h_replaytrain','conditions':'nmr_transfer.h_conditions','training_details':'nmr_transfer.h_condmodel','model_factory':'nmr_transfer.emission_model','model':'nmr_transfer.h_preserved_group_model','data':'nmr_transfer.data'}
    for key,module in modules.items():
        actual=Path(importlib.import_module(module).__file__).resolve()
        ref=release['sources'][key]
        if Path(ref['path']).resolve()!=actual or ref['sha256']!=sha256(actual):raise ValueError('executed_source_binding_'+key)
    if sha256(c['inputs']['checkpoint']['path'])!=CHECKPOINT_SHA256:raise ValueError('checkpoint_bytes')
    if c['inputs']['equivalence_registry']['sha256']!=REGISTRY_SHA256:raise ValueError('nomination_registry_binding')
    gate=json.loads(Path(c['inputs']['feasibility_gate']['path']).read_text())
    if gate.get('complete') is not True or gate.get('training_admitted_input_ids')!=ids:raise ValueError('final_G_domain_binding')
    data={k:_jsonl(c['inputs'][k]) for k in ('features','supervision','admission','support_manifest')}
    selected={}
    for k,rs in data.items():
        lookup={r['input_id']:r for r in rs}
        selected[k]=[lookup[x] for x in ids]
    records=[]
    solver_ref=c['inputs']['solver_config'];solver=json.loads(Path(solver_ref['path']).read_text())
    for a,s,f,supervision in zip(selected['admission'],selected['support_manifest'],selected['features'],selected['supervision']):
        if not a['source_family_complete'] or not a['model_family_complete'] or a['supervised_observation_count']<=0:raise ValueError('admission_not_ready')
        if a['status']!='internal_mapping_ready_pending_batch_review' or not supervision['assignment_training_ready'] or supervision['review_spectral_weight']<=0:raise ValueError('restricted_training_record')
        ref=s['support_artifact']
        if sha256(ref['path'])!=ref['sha256']:raise ValueError('support_digest')
        raw=json.loads(Path(ref['path']).read_text())
        if raw['input_id']!=a['input_id'] or raw['schema']!='initial_margin_fixed_support_v1':raise ValueError('support_identity')
        native=raw['native_signature']
        units=native['predictions']['layout']['units']
        if not units or any(u['partition_status']!='registry_hypothesis' for u in units):raise ValueError('known_equivalence_layout_required')
        if native['native_structure_snapshot_sha256']!=f['native_structure_snapshot_sha256']:raise ValueError('support_feature_graph_binding')
        if native['predictions']['layout']!=a['known_layout']:raise ValueError('support_admission_layout_binding')
        support=load_support(raw['support'])
        records.append(dict(input_id=a['input_id'],support=support,native_signature=raw['native_signature'],allowed_joint_parent_sets=a['allowed_joint_parent_sets'],invariant_parent_sets=a['invariant_parent_sets'],model_unit_parent_sets=a['model_unit_parent_sets'],solver_config=solver))
    return c,selected,records

def initialize_native_bindings(model,dataset,records,device):
    """未来放行后的真实初始复现：不生成候选、不求解，也不更改支持。"""
    model.eval()
    for parameter in model.parameters():parameter.requires_grad_(False)
    initial_state={k:v.detach().clone() for k,v in model.state_dict().items()}
    for i,r in enumerate(records):
        b=feature_batch(Batch.from_data_list([dataset[i]])).to(device)
        # The original producer lets forward attach its registry fields, after
        # the unconditioned native forward; do not pre-attach them here.
        with torch.inference_mode():d=model(b,details=True)
        assert_state(model,initial_state)
        if 'equivalence_known' not in b or not bool(b.equivalence_known.all()):raise RuntimeError('model_known_layout_required')
        centers=d['values'].detach().cpu().double()*10
        support=r['support']
        if len(centers)!=len(support.component_ids):raise RuntimeError('initial_component_domain')
        for carrier in support.carriers:
            for j in carrier.source_component_indices:
                if float(centers[j])!=carrier.initial_center_ppm:raise RuntimeError('saved_initial_center_not_reproduced')
        # Capacity layout is bound to the original prediction; parent nuclear mass must
        # equal actual emitted mass, without replacing fractional mass by capacity count.
        prediction=r['native_signature']['predictions'];layout=prediction['layout']
        expected={}
        for unit in layout['units']:
            for parent,mass in unit['parent_mass']:expected[int(parent.split(':')[-1])]=expected.get(int(parent.split(':')[-1]),0)+mass
        actual={}
        for owner,weight in zip(d['owners'].detach().cpu().tolist(),d['weights'].detach().cpu().tolist()):actual[owner]=actual.get(owner,0)+weight
        if actual!=expected:raise RuntimeError('saved_parent_mass_not_reproduced')
        units={u['unit_id']:u for u in layout['units']}
        for carrier in prediction['carriers']:
            indices=[int(x.split(':')[1]) for x in carrier['source_component_ids']]
            parents={int(x.split(':')[-1]) for x,_ in units[carrier['unit_id']]['parent_mass']}
            if any(int(d['owners'][j]) not in parents for j in indices):raise RuntimeError('saved_component_owner')
            mass=float(d['weights'][indices].sum())
            target=carrier['mixture_weight']*units[carrier['unit_id']]['nucleus_mass']
            if abs(mass-target)>1e-9*max(1,abs(target)):raise RuntimeError('saved_carrier_mass')
        r['initial_component_centers_ppm']=centers
        r['initial_component_signature']={k:d[k].detach().cpu().clone() for k in ('weights','owners','groups','exchangeable')}
        r['initial_layout_signature']={k:b[k].detach().cpu().clone() for k in ('equivalence_ids','equivalence_offsets','equivalence_duplicates','equivalence_known','preserved_group_orbits','preserved_group_ordinal','preserved_group_sizes') if k in b}

def relocate_registry_config(cfg,ref):
    """只重定位已冻结同字节 registry；不变更任何其它 checkpoint 参数。"""
    if cfg.get('equivalence_registry_sha256')!=REGISTRY_SHA256 or ref.get('sha256')!=REGISTRY_SHA256:raise ValueError('checkpoint_registry_digest_binding')
    if sha256(ref['path'])!=REGISTRY_SHA256:raise ValueError('registry_bytes')
    relocated=dict(cfg);relocated['equivalence_registry_path']=ref['path']
    if {k:v for k,v in relocated.items() if k!='equivalence_registry_path'}!={k:v for k,v in cfg.items() if k!='equivalence_registry_path'}:raise RuntimeError('model_argument_changed')
    return relocated

def main(argv=None):
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--run-config',required=True);p.add_argument('--release',required=True);p.add_argument('--out',required=True);p.add_argument('--completion-plan',required=True);p.add_argument('--completion-plan-sha256',required=True)
    args=p.parse_args(argv)
    torch.set_num_threads(2);torch.set_num_interop_threads(2)
    c,selected,records=prepare_run(args.run_config,args.release)
    completion=prepare_completion(args.completion_plan,args.completion_plan_sha256,args.run_config,args.release,c['input_ids'],args.out)
    if c.get('device','cpu')!='cpu':raise ValueError('JJ_recovery_requires_CPU')
    runtime_claim=Path(args.out).parent/'trainer_runtime_claim.json'
    with runtime_claim.open('x') as stream:
        json.dump(dict(schema='JJ_recovery_trainer_runtime_claim_v1',pid=os.getpid(),created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),device='cpu',torch_num_threads=torch.get_num_threads(),torch_num_interop_threads=torch.get_num_interop_threads(),thread_environment={k:os.environ.get(k) for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','CUDA_VISIBLE_DEVICES')},checkpoint_sha256=CHECKPOINT_SHA256,registry_sha256=REGISTRY_SHA256,initialization_mode_requested='producer_eval_all_parameters_frozen_inference_mode',training_success=False),stream,indent=2)
        stream.write('\n')
    from .emission_model import make_model
    from .h_preserved_group_model import PreservedGroupSpecGNN
    # Only the exact approved self-produced checkpoint may use its saved args schema.
    checkpoint=torch.load(c['inputs']['checkpoint']['path'],map_location='cpu',weights_only=True)
    cfg=relocate_registry_config(checkpoint['args'],c['inputs']['equivalence_registry'])
    if cfg.get('model')!='preserved_group_atom' or cfg.get('nucleus')!='1H':raise ValueError('checkpoint_architecture')
    def factory():
        # 原producer的限定安全加载：只准两份已校验制品，任何路径均强制CPU/True。
        real_load=torch.load
        allowed={str(Path(c['inputs'][key]['path']).resolve()) for key in ('checkpoint','equivalence_registry')}
        def safe_load(path,*args,**kwargs):
            if args or str(Path(path).resolve()) not in allowed:raise ValueError('unapproved_model_load')
            kwargs.update(weights_only=True,map_location='cpu')
            return real_load(path,**kwargs)
        torch.load=safe_load
        try:
            m=make_model(cfg)
            if type(m) is not PreservedGroupSpecGNN:raise ValueError('model_type')
            m.load_state_dict(checkpoint['state_dict'],strict=True)
            return m
        finally:torch.load=real_load
    ds=dataset_from_records(selected['features'],selected['supervision'])
    initial=None
    try:
        initial=factory().to(c.get('device','cpu'));initialize_native_bindings(initial,ds,records,c.get('device','cpu'))
    finally:
        initial=None
        gc.collect()
    result=paired_train(factory,ds,records,args.release,c['input_ids'],args.out,device=c.get('device','cpu'),completion=completion)
    (Path(args.out)/'complete.json').write_text(json.dumps({'results':result,'completed_new_jobs':result[1:],'completion_provenance':completion['provenance'],'validation_calls':0,'test_calls':0,'checkpoint_selection':'epoch10_only'},indent=2))

if __name__=='__main__':main()
