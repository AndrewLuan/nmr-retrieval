"""功能概述：来源含噪探索性A/B的固定完整候选图与中心可微成本接口。
freeze_support沿用costs的完整singleton/pair、carrier门控和reduced权重，保存通过的组合；
local_cost_tensors只随中心重算Huber/logsumexp，绝不重新门控、删组合、重归一或平均carrier。
本模块不读取来源/文件/模型、不修改旧loss/参数；jointfamily及invariant parent SET由准入模块提供。
仅供root后续训练入口接线，所有候选、sigma/q/merge及dummy参数必须从原冻结配置显式传入。
loss使用完整gold/model共同selector的G及完整A-d两个认证MILP；仅对已选原成本反传。
固定5s每argmin/10s共享、100000变量与节点；所有limit/不可行/数值错误抛MarginFailure，不能跳样或扩预算。
后端版本、稳定变量顺序、单线程/seed0须由run_config冻结；同cost多解不声明化学唯一。
"""
from dataclasses import dataclass
from math import fsum,hypot,isfinite
from .costs import Observation,_inputs,_normalizer_parts,_unit_sets,_Budget,_number


@dataclass(frozen=True)
class CarrierSupport:
    carrier_id: str
    unit_id: str
    initial_center_ppm: float
    sigma_ppm: float
    log_weight: float
    source_component_ids: tuple
    source_component_indices: tuple


@dataclass(frozen=True)
class EdgeSupport:
    observation_id: str
    unit_ids: tuple
    # Every tuple is one original surviving carrier product; retain all mass.
    carrier_combinations: tuple


@dataclass(frozen=True)
class FixedSupport:
    observations: tuple
    unit_ids: tuple
    carriers: tuple
    edges: tuple
    delta: float
    merge_cost: float
    examined_count: int
    emitted_count: int
    component_ids: tuple = ()
    missing_costs: tuple = ()
    unexplained_costs: tuple = ()
    normalizer_convention: str = "reduced"


def _freeze_support(observations,predictions,*,nucleus,delta,smin,lambda_merge,
                   member_gate,pair_span,gate_mode,normalizer_convention,
                   integral_policy,max_candidates,deadline=None):
    """Complete initial graph independent of labels; any budget failure raises, never truncates."""
    if nucleus not in ("1H","13C") or predictions.layout.nucleus!=nucleus:
        raise ValueError("support nucleus differs from capacity layout")
    if gate_mode!="standardized" or normalizer_convention!="reduced" or integral_policy!="disabled":
        raise ValueError("assignment margin requires frozen reduced standardized nonintegral B2")
    delta=_number(delta,"delta",positive=True);smin=_number(smin,"smin",positive=True)
    merge=_number(lambda_merge,"lambda_merge",positive=True)
    gate=_number(member_gate,"member_gate",nonnegative=True);span=_number(pair_span,"pair_span",nonnegative=True)
    budget=_Budget(max_candidates,deadline);obs,pred=_inputs(observations,predictions)
    scales,_,weights=_normalizer_parts(pred,smin,budget)
    unresolved={u.unit_id for u in predictions.layout.units if u.partition_status=="unresolved_parent_pool"}
    carriers=tuple(CarrierSupport(c.carrier_id,uid,c.center_ppm,scales[c.carrier_id],weights[c.carrier_id],tuple(c.source_component_ids),tuple(_component_index(name) for name in c.source_component_ids)) for uid,cs in pred for c in cs)
    from itertools import product
    edges=[]
    for peak in obs:
        for members in _unit_sets(pred,unresolved,budget):
            combinations=[]
            for cs in product(*(carriers for _,carriers in members)):
                budget.step()
                if any(abs(peak.ppm-c.center_ppm)/scales[c.carrier_id]>gate for c in cs):continue
                if len(cs)==2 and abs(cs[0].center_ppm-cs[1].center_ppm)/hypot(*(scales[c.carrier_id] for c in cs))>span:continue
                combinations.append(tuple(c.carrier_id for c in cs))
            if combinations:
                budget.emit();edges.append(EdgeSupport(peak.observation_id,tuple(uid for uid,_ in members),tuple(combinations)))
    complete=budget.finish(edges)
    return FixedSupport(tuple(obs),tuple(uid for uid,_ in pred),carriers,tuple(complete),delta,merge,complete.examined_count,complete.emitted_count)


def local_cost_tensors(support,centers_ppm):
    """原component:i一维中心输入；每carrier取其全sourcecomponents的同一中心，绝不均值。

    carrier ID与component ID是独立命名空间。同carrier源components固定属于同一
    unit，必须当前逐项精确同中心；否则状态漂移失败。原owners/groups/layout不变
    还由root trainer对当前modeldetails和初始签名逐项检查，不能仅凭中心推断身份。
    """
    import torch
    if type(support) is not FixedSupport:raise ValueError("fixed complete support required")
    if not torch.is_tensor(centers_ppm) or centers_ppm.ndim!=1 or not torch.is_floating_point(centers_ppm):
        raise ValueError("centers must be original model-component 1D floating tensor")
    if len(centers_ppm)!=len(support.component_ids):raise ValueError("original component domain changed")
    if not bool(torch.isfinite(centers_ppm.detach()).all()):raise MarginFailure("nonfinite component center")
    by_id={c.carrier_id:c for c in support.carriers};carrier_centers={};seen={}
    for c in support.carriers:
        if not c.source_component_indices:raise MarginFailure("carrier has no bound original components")
        for index in c.source_component_indices:
            if index in seen:raise MarginFailure("source component reused across carriers/units")
            seen[index]=(c.unit_id,c.carrier_id)
        values=centers_ppm[list(c.source_component_indices)]
        if not torch.equal(values.detach(),values[0].detach().expand_as(values)):
            raise MarginFailure("same-carrier source components no longer share a center")
        carrier_centers[c.carrier_id]=values[0]
    if set(seen)!=set(range(len(support.component_ids))):raise MarginFailure("component membership/domain drift")
    centers_ppm=carrier_centers
    observed={o.observation_id:o.ppm for o in support.observations};result={}
    for edge in support.edges:
        logs=[]
        for combination in edge.carrier_combinations:
            terms=[]
            for cid in combination:
                c=by_id[cid];z=(centers_ppm[cid]-observed[edge.observation_id]).abs()/c.sigma_ppm
                rho=torch.where(z<=support.delta,z.square()/2,support.delta*(z-support.delta/2))
                terms.append(c.log_weight-rho)
            logs.append(torch.stack(terms).sum())
        # Same nonnegative roundoff clamp as frozen costs.build_b2.
        value=(-torch.logsumexp(torch.stack(logs),dim=0)).clamp_min(0)+support.merge_cost*(len(edge.unit_ids)-1)
        result[(edge.observation_id,edge.unit_ids)]=value
    return result


class MarginFailure(RuntimeError):
    """Paired training step must stop; structured status supports bounded preflight accounting only."""
    def __init__(self,message,*,stage=None,backend_status=None,certificate=None):
        super().__init__(message)
        self.stage=stage;self.backend_status=backend_status;self.certificate=certificate


def _need(value,reason):
    if not value:raise MarginFailure(reason)


def _component_index(name):
    _need(isinstance(name,str) and name.startswith("component:"),"source_component_ids must bind original component:i")
    suffix=name[len("component:"):]
    _need(suffix.isdecimal() and str(int(suffix))==suffix,"canonical component index required")
    return int(suffix)


def freeze_support(inference_input,cost_config):
    """Freeze full initial B2 support; explicit original dummy costs never inferred from labels.

    cost_config contains numeric_config (full frozen schema), missing_costs and
    unexplained_costs (complete maps already justified by original window/structure
    policy), and optional candidate_deadline. No inference or optimizer call here.
    """
    from dataclasses import replace
    from .contracts import InferenceInput
    from .costs import parameters_from_frozen_config
    from .mapping import FrozenCapacityPredictions
    _need(type(inference_input) is InferenceInput,"typed InferenceInput required")
    inference_input.__post_init__()
    _need(inference_input.nucleus=="1H" and type(inference_input.frozen_predictions) is FrozenCapacityPredictions,"H211 capacity predictions only")
    numeric=cost_config["numeric_config"]
    params=parameters_from_frozen_config(numeric,method="B2",nucleus="1H",normalizer_convention="reduced")
    maximum=numeric["computation_budget"]["max_candidates_per_global_problem"]
    _need(type(maximum) is int and 0<maximum<=100000,"fixed candidate cap")
    observations=tuple(Observation(p.peak_id,float(p.normalized_ppm(inference_input.actual_conditions))) for p in inference_input.observed_peaks)
    pred=inference_input.frozen_predictions
    support=_freeze_support(observations,pred,**params,max_candidates=maximum,deadline=cost_config.get("candidate_deadline"))
    all_components=tuple(name for c in pred.carriers for name in c.source_component_ids)
    _need(len(all_components)==len(set(all_components)),"original component occurs in more than one carrier/unit")
    component_ids=tuple("component:"+str(i) for i in range(len(all_components)))
    _need(set(all_components)==set(component_ids),"complete original component domain required; carrier IDs remain independent")
    missing=cost_config["missing_costs"];unexplained=cost_config["unexplained_costs"]
    _need(set(missing)==set(support.unit_ids) and set(unexplained)=={o.observation_id for o in support.observations},"complete frozen dummy costs")
    expected_u=_number(numeric["machine_cost_contract"]["B2_unexplained"],"frozen unexplained",nonnegative=True)
    missing=tuple((u,_number(missing[u],"missing",nonnegative=True)) for u in support.unit_ids)
    unexplained=tuple((o.observation_id,_number(unexplained[o.observation_id],"unexplained",nonnegative=True)) for o in support.observations)
    _need(all(v==expected_u for _,v in unexplained),"unexplained penalty differs from frozen B2")
    return replace(support,component_ids=component_ids,missing_costs=missing,unexplained_costs=unexplained)


def _parent_set(values):
    _need(isinstance(values,(list,tuple,set,frozenset)) and bool(values),"finite nonempty parent SET required; unknown is not all-parent truth")
    _need(all(isinstance(x,str) and x for x in values),"parent IDs must be bound nonempty strings")
    _need(len(values)==len(set(values)),"duplicate parent SET member")
    return frozenset(values)


def _joint_families(support,gold,invariant,model):
    """Validate references/shape only; admission producer owns complete transport evidence."""
    obs={o.observation_id for o in support.observations};units=set(support.unit_ids)
    def parse(family,key,domain,complete):
        _need(isinstance(family,(tuple,list)) and len(family)>0,"complete nonempty joint family required")
        result=[];seen={};common=None
        for item in family:
            _need(isinstance(item,dict) and isinstance(item.get("map_id"),str) and item["map_id"] ,"unique joint map IDs required")
            mapping=item[key]
            _need(item["map_id"] not in seen or seen[item["map_id"]]==mapping,"conflicting duplicate joint map ID")
            seen[item["map_id"]]=mapping
            _need(isinstance(mapping,dict) and set(mapping)<=domain,"unknown joint reference")
            if complete:_need(set(mapping)==domain,"model map must cover every physical unit")
            if common is None:common=set(mapping)
            _need(set(mapping)==common,"all source variants must preserve the same usable observation domain")
            result.append((item["map_id"],{k:_parent_set(v) for k,v in mapping.items()}))
        return tuple(sorted(result,key=lambda x:x[0]))
    gold=parse(gold,"observation_parent_sets",obs,False);model=parse(model,"unit_parent_sets",units,True)
    parent_domain=set().union(*(set().union(*mapping.values()) if mapping else set() for _,mapping in model))
    _need(all(s<=parent_domain for _,mapping in gold for s in mapping.values()),"source parent absent from bound model graph")
    computed={o:gold[0][1][o] for o in gold[0][1] if all(mapping[o]==gold[0][1][o] for _,mapping in gold)}
    _need(isinstance(invariant,dict),"invariant SET mapping required")
    provided={o:_parent_set(v) for o,v in invariant.items()}
    _need(provided==computed and len(provided)>0,"M must equal exactly invariant supervised observations and be positive")
    return gold,provided,model


def _project(members,mapping):
    return frozenset().union(*(mapping[u] for u in members))


def backend_fingerprint():
    """Metadata only: actual SciPy MILP/wrapper/binary paths+SHA, no optimization call."""
    import importlib,hashlib,scipy
    from pathlib import Path
    milp_module=importlib.import_module("scipy.optimize._milp")
    wrapper=importlib.import_module(milp_module._highs_wrapper.__module__)
    binary=wrapper;observed=None
    if Path(wrapper.__file__).suffix==".py":
        binary=importlib.import_module("scipy.optimize._highspy._core")
    try:observed=".".join(str(getattr(binary,"HIGHS_VERSION_"+v)) for v in ("MAJOR","MINOR","PATCH"))
    except AttributeError:pass
    def item(module):
        path=Path(module.__file__).resolve()
        return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return dict(scipy_version=scipy.__version__,milp_source=item(milp_module),highs_wrapper=item(wrapper),highs_binary=item(binary),highs_version=observed or "unknown")


def _pin_backend(config):
    current=backend_fingerprint();pinned=config["backend"]
    _need(all(current[k]==pinned[k] for k in ("scipy_version","milp_source","highs_wrapper","highs_binary")),"actual SciPy/MILP/wrapper/binary differs from frozen run_config")
    # Version string is descriptive only; exact implementation hashes bind the
    # backend even when old bundled HiGHS exposes no version constants.
    return current


def _solver_config(config):
    required=dict(argmin_wall_seconds=5,record_wall_seconds=10,node_limit=100000,max_candidates=100000,max_variables=100000,threads=1,random_seed=0,mip_rel_gap=0)
    _need(all(type(config.get(k)) in (int,float) and not isinstance(config[k],bool) and config[k]==v for k,v in required.items()),"frozen finite MILP controls differ")
    return required


def _argmin(costs,choices,support,gold,model,*,constrained,config,record_deadline):
    """One full certified primary-objective MILP; selectors share all constrained observations."""
    from time import monotonic
    import numpy as np
    from scipy.optimize import milp,Bounds,LinearConstraint
    from scipy.sparse import csc_matrix
    started=monotonic();deadline=min(record_deadline,started+5.)
    obs=tuple(o.observation_id for o in support.observations);units=support.unit_ids
    selector_count=len(gold)*len(model) if constrained else 0
    n=len(choices)+selector_count
    _need(len(support.edges)<=100000 and n<=100000,"complete MILP graph/selector variable cap; never truncate")
    selector=tuple((gname,mname,gmap,mmap) for gname,gmap in gold for mname,mmap in model) if constrained else ()
    rowindices=[];columns=[];data=[];lower=[];upper=[]
    def add(entries,lo,hi):
        _need(monotonic()<deadline,"argmin budget exhausted during full matrix construction")
        index=len(lower)
        for column,value in entries:rowindices.append(index);columns.append(column);data.append(value)
        lower.append(lo);upper.append(hi)
    for oid in obs:add(((i,1.) for i,(o,_) in enumerate(choices) if o==oid),1.,1.)
    for uid in units:add(((i,1.) for i,(_,members) in enumerate(choices) if uid in members),1.,1.)
    if constrained:
        add(((len(choices)+i,1.) for i in range(len(selector))),1.,1.)
        supervised=set(gold[0][1])
        for i,(oid,members) in enumerate(choices):
            if oid not in supervised:continue
            if not members:add(((i,1.),),0.,0.);continue
            # x_choice <= sum selectors allowing THIS choice. A SINGLE y
            # simultaneously governs every observation, retaining whole joint G.
            compatible=((len(choices)+j,-1.) for j,(_,_,gmap,mmap) in enumerate(selector) if _project(members,mmap)==gmap[oid])
            add(((i,1.),*compatible),-np.inf,0.)
    matrix=csc_matrix((data,(rowindices,columns)),shape=(len(lower),n))
    objective=np.asarray(tuple(costs)+(0.,)*len(selector),dtype=float)
    _need(np.isfinite(objective).all(),"nonfinite objective")
    remaining=min(5.,deadline-monotonic());_need(remaining>0,"argmin budget exhausted before backend")
    # SciPy forwards unknown options to bundled HiGHS; these are frozen run controls.
    result=milp(objective,integrality=np.ones(n),bounds=Bounds(np.zeros(n),np.ones(n)),constraints=LinearConstraint(matrix,np.asarray(lower),np.asarray(upper)),options=dict(time_limit=remaining,node_limit=100000,mip_rel_gap=0.,threads=1,random_seed=0))
    _need(monotonic()<=deadline and monotonic()<=record_deadline,"certified solve returned beyond frozen deadline")
    if result.status!=0 or getattr(result,"mip_gap",None)!=0.:
        raise MarginFailure("argmin limit/infeasible/error or nonzero optimality gap",stage="G" if constrained else "A",backend_status=int(result.status),certificate=dict(status=int(result.status),message=str(result.message),elapsed_seconds=monotonic()-started,mip_gap=getattr(result,"mip_gap",None)))
    vector=np.asarray(result.x,dtype=float);_need(vector.shape==(n,) and np.isfinite(vector).all(),"invalid primal")
    rounded=np.rint(vector)
    _need(np.max(np.abs(vector-rounded))<=1e-6 and np.all((rounded>=0)&(rounded<=1)),"nonintegral primal")
    activity=matrix@rounded
    _need(np.all(activity>=np.asarray(lower)-1e-7) and np.all(activity<=np.asarray(upper)+1e-7),"violated exact-cover/joint constraint")
    value=fsum(float(objective[i]) for i in np.flatnonzero(rounded))
    fun=float(result.fun);dual=float(result.mip_dual_bound)
    _need(isfinite(fun) and isfinite(dual) and abs(value-fun)<=1e-7*max(1.,abs(value),abs(fun)) and abs(value-dual)<=1e-7*max(1.,abs(value),abs(dual)),"objective/dual inconsistency")
    _need(getattr(result,"mip_node_count",0)<=100000,"node cap exceeded")
    selected=tuple(int(i) for i in np.flatnonzero(rounded[:len(choices)]))
    selector_ids=tuple((selector[i-len(choices)][0],selector[i-len(choices)][1]) for i in np.flatnonzero(rounded) if i>=len(choices))
    return selected,dict(objective=value,dual_bound=dual,mip_gap=0.,status=0,node_count=getattr(result,"mip_node_count",None),elapsed_seconds=monotonic()-started,variables=n,selector_ids=selector_ids,selected_choices=tuple(choices[i] for i in selected),tie_rule="fixed-version singlethread seed0 backend optimal primary objective; not chemical uniqueness")


def loss(centers_ppm,support,allowed_joint_parent_sets,invariant_parent_sets,model_unit_parent_sets,solver_config):
    """Return scalar differentiable hinge plus detached certificates; no optimizer or implicit retries.

    Both exact argmins share this function's10s. Any failure raises MarginFailure;
    root must stop the paired experiment, never skip this record. Joint completeness
    and graph/source transport provenance are established by margin_admission, not
    authenticated by shape validation here. No K-limited competitor is substituted.
    """
    from time import monotonic
    import torch
    entered=monotonic();deadline=entered+10.
    _solver_config(solver_config);backend=_pin_backend(solver_config)
    _need(type(support) is FixedSupport and support.normalizer_convention=="reduced","frozen reduced support required")
    _need(bool(support.component_ids) and len(support.missing_costs)==len(support.unit_ids) and len(support.unexplained_costs)==len(support.observations),"complete fixed dummy/component support")
    gold,invariant,model=_joint_families(support,allowed_joint_parent_sets,invariant_parent_sets,model_unit_parent_sets)
    local=local_cost_tensors(support,centers_ppm)
    _need(all(bool(torch.isfinite(v.detach())) for v in local.values()),"nonfinite current center costs")
    choices=tuple(sorted(local,key=lambda x:(x[0],x[1])))+tuple((None,(u,)) for u,_ in support.missing_costs)+tuple((o,()) for o,_ in support.unexplained_costs)
    _need(len(support.edges)<=100000 and len(choices)<=100000,"complete candidate/variable cap")
    template=centers_ppm if torch.is_tensor(centers_ppm) else next(iter(centers_ppm.values()))
    zero=template.sum()*0
    tensors=tuple(local[key] for key in choices[:len(local)])+tuple(zero+v for _,v in support.missing_costs)+tuple(zero+v for _,v in support.unexplained_costs)
    values=tuple(float(v.detach().cpu()) for v in tensors)
    errors=[]
    for oid,members in choices:
        errors.append(0 if oid not in invariant else int(not members or all(_project(members,mapping)!=invariant[oid] for _,mapping in model)))
    _need(monotonic()<deadline,"shared record budget exhausted before argmin")
    chosen_g,cert_g=_argmin(values,choices,support,gold,model,constrained=True,config=solver_config,record_deadline=deadline)
    try:
        chosen_a,cert_a=_argmin(tuple(v-d for v,d in zip(values,errors)),choices,support,gold,model,constrained=False,config=solver_config,record_deadline=deadline)
    except MarginFailure as exc:
        exc.stage="A";exc.G=cert_g
        raise
    # Selected indices are detached discrete decisions. Gradients flow only
    # through Ftheta at the two certified whole assignments on unchanged support.
    g=sum((tensors[i] for i in chosen_g),zero)
    a=sum((tensors[i] for i in chosen_a),zero)-sum(errors[i] for i in chosen_a)
    hinge=(g-a)/len(invariant)
    _need(bool(torch.isfinite(hinge.detach())) and monotonic()<=deadline,"nonfinite/late hinge")
    detached=float(hinge.detach().cpu())
    _need(detached>=-1e-7*max(1.,abs(cert_g["objective"]),abs(cert_a["objective"])),"negative certified structured hinge")
    return dict(loss=hinge,M=len(invariant),G=cert_g,A_loss_augmented=cert_a,backend=backend,elapsed_seconds=monotonic()-entered,d_at_A=sum(errors[i] for i in chosen_a),support_edges=len(support.edges),graph_refrozen=False,new_chemical_uniqueness_claim=False)
