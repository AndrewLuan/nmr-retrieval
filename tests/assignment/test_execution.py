"""功能概述：用匿名合成小图检查 record driver 的完整三基线和进程生命周期。
主要职责：真实 worker 小图与手工目标比较，READY barrier 确认 solver stage 已进入等待后
超时 kill/reap；mock 时钟验证共享阶段 allowance，不固定 sleep、不重试、不运行真实数据。
代码库关系：execution、mapping 与仓库内 fixtures/identity_free_config.json 合成冻结schema；
该配置无源身份或实际校准产物；整个 fixture 的启动、触发、communicate 和回收均有界。
输入输出与副作用：只创建自有子进程，finally 清理；不操作其他 PID，无模型/API/Git。
"""
from dataclasses import asdict
import copy
import json
import math
import os
import sys
from time import monotonic
import unittest
from unittest.mock import patch
from nmr_assignment.execution import (execute_record,_worker_record,_prepare_record,_payload,_run_stage,
    MAX_INPUT_BYTES,numeric_config_from_frozen)
from nmr_assignment.mapping import build_capacity_layout,attach_prediction_carriers


def config():
    costs=dict(B0_B1_reference_scale_ppm={"1H":.3,"13C":2},
        B2_cost_convention="reduced_scale_normalizer",B2_gate_mode="standardized",
        B2_member_gate_multiplier=3,B2_pair_span_error_scale_multiplier=2,B2_delta=1.5,
        B2_merge_cost=math.log(2),smin_ppm={"1H":.05,"13C":.5},
        integral_policy="disabled_both_nuclei_first_round",missing_kappa_ordinary=math.log(3),
        missing_kappa_reduced_reporting=0,B1_unexplained=3,B2_unexplained=3.375,max_units_per_observation=2)
    budgets=dict(per_record_wall_seconds=10,mapping_and_candidates_seconds=2,B1_solver_seconds=2,
        B2_solver_seconds=5,result_validation_reserve_seconds=1,max_candidates_per_global_problem=50000,
        top_k=3,compute_margins=True,input_bytes_limit=MAX_INPUT_BYTES)
    return dict(costs=costs,budgets=budgets,tie_relative_tolerance=1e-7)


def payload(cfg=None):
    cfg=config() if cfg is None else cfg
    layout=build_capacity_layout(dict(nucleus="13C",parent_mass={"0":1,"1":1},
        isotope_count_verified=True,evidence_ids=["synthetic-structure"],partition_hypothesis_id="synthetic"))
    pred=attach_prediction_carriers(layout,[dict(component_id=str(i),owner_id=str(i),center_ppm=0,
        mass=1,sigma_ppm=2,sigma_source="synthetic") for i in (0,1)])
    return dict(observations=[dict(observation_id="p0",ppm=0)],predictions=asdict(pred),
        exchangeable_unit_ids=[],actual_window=None,numeric_config=cfg)


def encoded(value): return json.dumps(value,allow_nan=False).encode()


@unittest.skipUnless(os.name=="posix","POSIX record process-group contract")
class ExecutionTests(unittest.TestCase):
    def test_real_json_worker_three_baselines_match_hand_oracle(self):
        result=execute_record(encoded(payload()),approved_numeric_config=config())
        self.assertEqual(result["status"],"completed",result)
        self.assertTrue(result["process_reaped"])
        methods=result["result"]["methods"]
        self.assertEqual(len(methods["B0"]["local"][0]["minimum_unit_ids"]),2)
        self.assertFalse(methods["B0"]["local"][0]["best_unique"])
        self.assertAlmostEqual(methods["B1"]["solver_result"]["best"]["objective"],math.log(3))
        self.assertAlmostEqual(methods["B2"]["solver_result"]["best"]["objective"],math.log(2))
        self.assertEqual(len(methods["B2"]["solver_result"]["best"]["assignments"]["p0"]),2)
        diagnostics=result["result"]["candidate_diagnostics"]
        self.assertTrue(diagnostics["B2"]["generation_complete"])
        self.assertEqual(len(diagnostics["B2"]["candidates"]),3)
        self.assertEqual(diagnostics["B0"]["shared_candidate_graph"],"B1")
        pair=[v for v in diagnostics["B2"]["candidates"] if len(v["environment_ids"])==2]
        self.assertAlmostEqual(pair[0]["cost"],math.log(2))
        for method in ("B1","B2"):
            self.assertTrue(methods[method]["certified"])
            self.assertTrue(methods[method]["solver_result"]["attempts"])
            self.assertEqual(methods[method]["identification_quotient"],"none")
            self.assertTrue(result["result"]["stage_audit"][method]["process_reaped"])
        with self.assertRaises(ProcessLookupError): os.kill(result["child_pid"],0)

    def test_started_stage_setup_timeout_kills_only_owned_pid_and_reaps(self):
        argv=[sys.executable,"-u","-c",
              'import threading,os;print("READY",os.getpgrp(),flush=True);threading.Event().wait()']
        stage=_run_stage({},timeout_seconds=1,argv=argv)
        self.assertIn("READY "+str(os.getpgrp()),stage["stdout"])
        self.assertEqual(stage["status"],"stage_timeout")
        self.assertTrue(stage["process_reaped"])
        with self.assertRaises(ProcessLookupError): os.kill(stage["child_pid"],0)

    def test_exited_stage_descendant_pipe_holder_cannot_block_cleanup(self):
        import socket
        from concurrent.futures import ThreadPoolExecutor
        # The guardian has a socket barrier and its own bounded failure exit;
        # no fixed sleep or repeated cancellation is used by the fixture.
        server=socket.socket(); server.bind(("127.0.0.1",0)); server.listen(1); server.settimeout(3)
        port=server.getsockname()[1]
        guardian=("import socket,os; s=socket.create_connection(('127.0.0.1',"+str(port)+"),timeout=5); "
            "s.settimeout(5); s.sendall(b'READY'); print('READY',flush=True); "
            "s.recv(4); s.close()")
        leader="import subprocess,sys;subprocess.Popen([sys.executable,'-u','-c',"+repr(guardian)+"]);sys.exit(0)"
        connection=None
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(_run_stage,{},timeout_seconds=1,argv=[sys.executable,"-u","-c",leader])
            try:
                connection,_=server.accept(); connection.settimeout(3)
                self.assertEqual(connection.recv(5),b"READY")
                result=future.result(timeout=3)
                self.assertEqual(result["status"],"stage_timeout")
                self.assertTrue(result["process_reaped"])
                self.assertIn("READY",result["stdout"])
                with self.assertRaises(ProcessLookupError): os.kill(result["child_pid"],0)
            finally:
                if connection is not None:
                    try:
                        connection.sendall(b"STOP")
                        self.assertEqual(connection.recv(1),b"")
                    finally: connection.close()
                server.close()

    def test_shared_stage_allowances_and_validation_reserve_not_reset(self):
        cfg=config(); cfg["budgets"]["per_record_wall_seconds"]=6
        now=[0.]; allowances=[]
        def blocked_stage(request,*,timeout_seconds,argv=None,raw_input=None):
            if raw_input is not None:
                prepared=_prepare_record(raw_input,cfg,started=0,total_deadline=6,pre_deadline=2)
                return dict(status="completed",result=prepared,process_reaped=True,child_pid=None,stdout="",stderr="")
            allowances.append(timeout_seconds); now[0]+=timeout_seconds
            return dict(status="stage_timeout",result=None,process_reaped=True,child_pid=None,stdout="READY",stderr="")
        with patch("nmr_assignment.execution.monotonic",side_effect=lambda:now[0]), \
             patch("nmr_assignment.costs.monotonic",side_effect=lambda:now[0]), \
             patch("nmr_assignment.execution._run_stage",side_effect=blocked_stage):
            result=_worker_record(encoded(payload(cfg)),cfg,started=0,total_deadline=6,pre_deadline=2)
        self.assertEqual(allowances,[2,3])
        self.assertFalse(result["methods"]["B1"]["certified"])
        self.assertFalse(result["methods"]["B2"]["certified"])
        self.assertTrue(result["methods"]["B1"]["timed_out"])

    def test_preprocessing_deadline_precedes_payload_decode(self):
        with patch("nmr_assignment.execution._payload") as decode:
            result=_worker_record(b"invalid",config(),started=0,total_deadline=0,pre_deadline=0)
        decode.assert_not_called()
        self.assertEqual(result["status"],"preprocessing_timeout")

    def test_input_cap_and_strict_nested_leakage_rejected(self):
        oversized=execute_record(b"x"*(MAX_INPUT_BYTES+1),approved_numeric_config=config())
        self.assertEqual(oversized["status"],"unsupported_input_budget")
        self.assertNotIn("child_pid",oversized)
        paths=[(),("observations",0),("predictions",),("predictions","layout"),
               ("predictions","carriers",0),("predictions","layout","units",0)]
        for path in paths:
            value=payload(); target=value
            for key in path: target=target[key]
            target["gold"]="leak"
            with self.assertRaises(ValueError): _payload(encoded(value),config())
        changed=payload(); changed["numeric_config"]["costs"]["B2_merge_cost"]=99
        with self.assertRaisesRegex(ValueError,"approved snapshot"):
            _payload(encoded(changed),config())

    def test_missing_prior_uses_actual_window_or_structural_exchange_only(self):
        cfg=config(); value=payload(cfg)
        value["actual_window"]={"lower_ppm":20,"upper_ppm":30}
        def no_solver(request,*,timeout_seconds):
            return dict(status="stage_timeout",result=None,process_reaped=True,child_pid=None,stdout="",stderr="")
        with patch("nmr_assignment.execution._run_stage",side_effect=no_solver):
            now=monotonic()
            outside=_prepare_record(encoded(value),cfg,started=now,total_deadline=now+10,pre_deadline=now+2)
            value["actual_window"]=None
            unknown=_prepare_record(encoded(value),cfg,started=now,total_deadline=now+10,pre_deadline=now+2)
        self.assertEqual(set(outside["relative_missing_costs"].values()),{0})
        self.assertEqual(set(unknown["relative_missing_costs"].values()),{math.log(3)})

    def test_hard_preprocessing_timeout_retains_all_three_method_failures(self):
        cfg=config(); now=monotonic()
        def blocked_preparation(request,*,timeout_seconds,argv=None,raw_input=None):
            self.assertIsNone(request)
            self.assertIsNotNone(raw_input)
            self.assertLessEqual(timeout_seconds,2)
            return dict(status="stage_timeout",result=None,process_reaped=True,child_pid=123,stdout="READY",stderr="")
        with patch("nmr_assignment.execution._run_stage",side_effect=blocked_preparation):
            result=_worker_record(encoded(payload(cfg)),cfg,started=now,total_deadline=now+10,pre_deadline=now+2)
        self.assertEqual(result["status"],"preprocessing_timeout")
        self.assertEqual(set(result["methods"]),{"B0","B1","B2"})
        self.assertTrue(all(not m["certified"] for m in result["methods"].values()))

    def test_b2_missing_scale_is_unsupported_without_hiding_b0_b1(self):
        cfg=config(); value=payload(cfg)
        for carrier in value["predictions"]["carriers"]:
            carrier["sigma_ppm"]=None; carrier["sigma_source"]="unknown"
        now=monotonic()
        result=_prepare_record(encoded(value),cfg,started=now,total_deadline=now+10,pre_deadline=now+2)
        self.assertEqual(result["status"],"prepared")
        self.assertTrue(result["methods"]["B0"]["certified"])
        self.assertIn("B1",result["candidates"])
        self.assertNotIn("B2",result["candidates"])
        self.assertEqual(result["methods"]["B2"]["status"],"unsupported_prediction")

    def test_frozen_numeric_extraction_has_no_metadata(self):
        cfg=config()
        frozen=dict(machine_cost_contract=dict(cfg["costs"],tie_relative_tolerance=1e-7),
                    computation_budget=cfg["budgets"],source_thread_id="must-not-enter")
        self.assertEqual(numeric_config_from_frozen(frozen),cfg)
        from pathlib import Path
        path=Path(__file__).resolve().parent/"fixtures/identity_free_config.json"
        actual=numeric_config_from_frozen(json.loads(path.read_text()))
        self.assertEqual(actual,cfg)


class ReceiptTests(unittest.TestCase):
    """合成 backend 日志只测试接线；绝不调用 solve_assignment。"""
    def fixture(self):
        from nmr_assignment.execution import canonical_digest
        value=payload(); value["observations"]=[dict(observation_id="p0",ppm=0),dict(observation_id="p1",ppm=.1)]
        value["predictions"]["carriers"][1]["center_ppm"]=10
        def fake_stage(request,*,timeout_seconds,argv=None,raw_input=None):
            if raw_input is not None:
                now=monotonic()
                body=_prepare_record(raw_input,config(),started=now,total_deadline=now+10,pre_deadline=now+2)
            else:
                obs=request["observation_ids"]; units=request["unit_ids"]
                choices={(c["observation_id"],tuple(c["environment_ids"])):c["cost"] for c in request["candidates"]}
                assignment={o:[units[i]] if (o,(units[i],)) in choices else [] for i,o in enumerate(obs)}
                used={u for us in assignment.values() for u in us}; missing=sorted(set(units)-used)
                objective=sum(choices[o,tuple(us)] if us else request["unexplained_costs"][o] for o,us in assignment.items())+sum(request["missing_costs"][u] for u in missing)
                def attempt(purpose,cost):
                    return dict(purpose=purpose,status="optimal",raw_status=0,message="SYNTHETIC",optimal=True,
                        timed_out=False,objective=cost,mip_gap=0.,dual_bound=cost)
                body=dict(best=dict(objective=objective,assignments=assignment,unobserved=missing,
                        unexplained=[o for o,us in assignment.items() if not us],certified=True),
                    alternatives=[],status="optimal",optimal=True,timed_out=False,top_k_certified=False,
                    exhausted=False,identification_quotient="none",margins={o:dict(value=1.,status="optimal",
                        certified=True,alternative_objective=objective+1) for o in obs},
                    attempts=[attempt("best",objective)]+[attempt("margin:"+o,objective+1) for o in obs],
                    execution_problem_sha256=canonical_digest(request))
            return dict(status="completed",result=body,process_reaped=True,child_pid=None,stdout="",stderr="")
        now=monotonic()
        with patch("nmr_assignment.execution._run_stage",side_effect=fake_stage):
            body=_worker_record(encoded(value),config(),started=now,total_deadline=now+10,pre_deadline=now+2)
        from types import SimpleNamespace
        watchdog=SimpleNamespace(stdout=json.dumps(body),stderr="",timed_out=False,exit_code=0,
                                 process_reaped=True,child_pid=None)
        with patch("nmr_assignment.watchdog.run_isolated",return_value=watchdog):
            envelope=execute_record(encoded(value),approved_numeric_config=config(),input_id="synthetic",
                                    prediction_artifact_sha256="5"*64)
        return value,envelope

    def verify(self,value,envelope,method="B1"):
        from nmr_assignment.execution import verify_execution_method,canonical_digest
        from nmr_assignment.diagnostics import DiagnosticBinding
        binding=DiagnosticBinding("synthetic","source_relative_current_serialization","13C",
            "derived_serialized_value_bin","5"*64,"6"*64,canonical_digest(config()))
        return verify_execution_method(envelope,encoded(value),approved_numeric_config=config(),input_id="synthetic",
            prediction_artifact_sha256="5"*64,method=method,binding=binding)

    def reseal_synthetic(self,value,envelope):
        from nmr_assignment.execution import _make_execution_receipt
        envelope["execution_receipt"]=_make_execution_receipt(encoded(value),config(),envelope,
            input_id="synthetic",prediction_artifact_sha256="5"*64)

    def test_actual_producer_and_common_verifier_synthetic_backend(self):
        value,envelope=self.fixture()
        for method in ("B0","B1","B2"):
            result=self.verify(value,envelope,method)
            self.assertTrue(result["certified"],result)
        self.assertEqual(envelope["execution_receipt"]["payload"]["input_binding"]["input_id"],"synthetic")

    def test_changed_inputs_or_backend_payload_reject_old_receipt(self):
        value,envelope=self.fixture()
        for attack in ("carrier","observation","identity","candidate","attempt","margin","no_receipt"):
            v=copy.deepcopy(value); e=copy.deepcopy(envelope)
            if attack=="carrier": v["predictions"]["carriers"][0]["center_ppm"]+=100
            elif attack=="observation": v["observations"][0]["ppm"]+=100
            elif attack=="identity": e["input_id"]="foreign"
            elif attack=="candidate": e["result"]["candidate_diagnostics"]["B1"]["candidates"][0]["cost"]+=1
            elif attack=="attempt": e["result"]["methods"]["B1"]["solver_result"]["attempts"][0]["objective"]+=1
            elif attack=="margin": e["result"]["methods"]["B1"]["solver_result"]["margins"]["p0"]["value"]=-1
            else: e.pop("execution_receipt")
            self.assertFalse(self.verify(v,e)["certified"],attack)

    def test_B0_reuse_legal_B1_reuse_illegal_even_with_synthetic_receipt(self):
        value,envelope=self.fixture()
        local=self.verify(value,envelope,"B0")
        self.assertTrue(local["certified"],local)
        self.assertEqual(local["assignments"]["p0"],local["assignments"]["p1"])
        best=envelope["result"]["methods"]["B1"]["solver_result"]["best"]
        best["assignments"]["p1"]=best["assignments"]["p0"]
        self.reseal_synthetic(value,envelope)
        self.assertFalse(self.verify(value,envelope)["certified"])

    def test_inconsistent_best_objective_and_backend_attempt_rejected_after_reseal(self):
        value,envelope=self.fixture()
        raw=envelope["result"]["methods"]["B1"]["solver_result"]
        raw["best"]["objective"]=.2; raw["attempts"][0]["objective"]=.2
        self.reseal_synthetic(value,envelope)
        self.assertFalse(self.verify(value,envelope)["certified"])

    def test_negative_gap_cannot_become_determinate_after_reseal(self):
        value,envelope=self.fixture()
        envelope["result"]["methods"]["B1"]["solver_result"]["margins"]["p0"].update(value=-1,alternative_objective=-1)
        self.reseal_synthetic(value,envelope)
        verified=self.verify(value,envelope)
        self.assertFalse(verified["observation_determinate"]["p0"])
        self.assertFalse(verified["margin_scores"]["p0"]["margin_certified"])

    def test_inherited_deadlines_never_reset_or_relax(self):
        from types import SimpleNamespace
        watched=[]
        def capture(argv,raw,*,timeout_seconds):
            watched.append((argv,timeout_seconds))
            return SimpleNamespace(stdout="{}",stderr="",timed_out=False,exit_code=0,process_reaped=True,child_pid=None)
        with patch("nmr_assignment.execution.monotonic",return_value=100.),patch("nmr_assignment.watchdog.run_isolated",side_effect=capture):
            execute_record(encoded(payload()),approved_numeric_config=config(),record_started_at=99.,record_deadline=109.,preprocessing_deadline=101.)
            self.assertEqual(watched[0][1],9.)
            self.assertEqual(watched[0][0][watched[0][0].index("--pre-deadline")+1],"101.0")
            for kwargs in (dict(record_started_at=101.),dict(record_started_at=99.,record_deadline=110.),
                           dict(record_started_at=99.,preprocessing_deadline=102.)):
                with self.assertRaises(ValueError): execute_record(encoded(payload()),approved_numeric_config=config(),**kwargs)
            expired=execute_record(encoded(payload()),approved_numeric_config=config(),record_started_at=97.)
            self.assertEqual(expired["status"],"preprocessing_timeout")
            self.assertEqual(len(watched),1)

    def test_parent_receipt_overshoot_revokes_certification(self):
        value,envelope=self.fixture()
        from types import SimpleNamespace
        now=[100.]
        watched=SimpleNamespace(stdout=json.dumps(envelope["result"]),stderr="",timed_out=False,exit_code=0,
                                process_reaped=True,child_pid=None)
        def late(*args,**kwargs): now[0]=111.; return {}
        with patch("nmr_assignment.execution.monotonic",side_effect=lambda:now[0]), \
             patch("nmr_assignment.watchdog.run_isolated",return_value=watched), \
             patch("nmr_assignment.execution._make_execution_receipt",side_effect=late):
            result=execute_record(encoded(value),approved_numeric_config=config(),input_id="synthetic",prediction_artifact_sha256="5"*64)
        self.assertTrue(result["timed_out"])
        self.assertNotIn("execution_receipt",result)
        self.assertTrue(all(not m["certified"] for m in result["result"]["methods"].values()))


if __name__=="__main__": unittest.main()
