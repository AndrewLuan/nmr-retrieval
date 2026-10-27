# 功能概述：已审conditional4公开副本，实际源SHA与portableSHA分别绑定。
# 关系：显式runtime授权/源码闭包；保留原终态、once、边界、预算与科学谓词。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding
authorize()
"""功能概述：独立条件completion同步合成测试；不读任何真实test表或运行科学函数。
验证partition只依身份顺序，保守边界/已保存完整结果、started replay拒绝、永久exclusive写入、AST科学body不变。
监督fixture只用受控signal.pause进程验证固定wall终止/leader回收，无重试、性能benchmark或真实记录。
临时目录生命周期涵盖整个fixture，supervise_process负责finally进程树清理；失败后断言退出和无survivor。
"""
from pathlib import Path
import ast,copy,hashlib,importlib.util,json,os,sys,tempfile,unittest
from unittest.mock import patch
from types import SimpleNamespace
import TEST_STAGE_B_completion as c
import TEST_STAGE_B_completion_report as r
D=Path(__file__).resolve().parent
class PartitionTests(unittest.TestCase):
    def test_ambiguous_boundary(self):self.assertEqual(c.partition(["a","b","c"],["a"],{"a","b"}),dict(prefix=["a"],boundary=["b"],suffix=["c"]))
    def test_no_start_log_still_boundary(self):self.assertEqual(c.partition(["a","b","c"],[],set())["suffix"],["b","c"])
    def test_complete_unused(self):self.assertEqual(c.partition(["a"],["a"],{"a"})["suffix"],[])
    def test_only_boundary_no_suffix(self):self.assertEqual(c.partition(["a"],[],set())["suffix"],[])
    def test_nonprefix_reject(self):
        with self.assertRaises(ValueError):c.partition(["a","b"],["b"],set())
    def test_started_suffix_reject(self):
        with self.assertRaises(ValueError):c.partition(["a","b","c"],[],{"b"})
    def test_duplicate_queue_reject(self):
        with self.assertRaises(ValueError):c.partition(["a","a"],[],set())
    def test_foreign_reject(self):
        with self.assertRaises(ValueError):c.partition(["a"],[],{"foreign"})
    def test_recover_saved_final_without_retry(self):self.assertEqual(c.partition(["a","b","c"],["a"],{"a","b"},["b"]),dict(prefix=["a","b"],boundary=[],suffix=["c"]))
    def test_recovery_not_next_reject(self):
        with self.assertRaises(ValueError):c.partition(["a","b","c"],["a"],{"a","c"},["c"])
    def test_recovery_plus_further_started_reject(self):
        with self.assertRaises(ValueError):c.partition(["a","b","c"],["a"],{"a","b","c"},["b"])
class DurableTests(unittest.TestCase):
    def test_claim_no_release_or_directory_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"claim.json";c.write(p,dict(run="original",release="one"))
            for changed in (dict(run="original",release="two"),dict(run="original",directory="other")):
                with self.assertRaises(FileExistsError):c.write(p,changed)
            self.assertEqual(json.loads(p.read_text())["release"],"one")
    def test_started_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"id.execution_started.json";c.write(p,dict(input_id="id"))
            with self.assertRaises(FileExistsError):c.write(p,{})
    def test_missing_boundary_initial_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):r.read_saved(tmp,dict(output_sha256={}),"evaluation/x.not_started.json")
    def test_boundary_preserves_eligibility(self):
        row=dict(metric="exact_observation",observation_id="o",eligible=True,prediction_supported=False,success=False,reason_codes=["unknown"],failure_labels=["unknown"],context=[],eligibility_reason_codes=["frozen"],eligibility_determinator=["proof"])
        original={m:[copy.deepcopy(row)] for m in ("B0","B1","B2")};new=r.boundary_rows(original)
        for m in original:
            for k in ("eligible","eligibility_determinator","eligibility_reason_codes","failure_labels"):self.assertEqual(new[m][0][k],original[m][0][k])
        self.assertNotIn("interrupted_unknown_boundary",original["B0"][0]["reason_codes"])
    def test_boundary_cannot_launder_saved_success(self):
        with self.assertRaises(ValueError):r.boundary_rows({m:[dict(prediction_supported=True,success=True)] for m in ("B0","B1","B2")})
class RecoveryTests(unittest.TestCase):
    def test_partial_final_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"raw").mkdir();(root/"evaluation").mkdir();(root/"raw/b.json").write_text("{")
            self.assertEqual(c.recoverable_next(root,["a","b"],["a"]),[])
    def test_complete_failed_result_recovered_without_status_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"raw").mkdir();(root/"evaluation").mkdir()
            row=dict(metric="exact_observation",observation_id="o",context=[],eligible=True,eligibility_reason_codes=[],eligibility_determinator=[])
            initial={m:[copy.deepcopy(row)] for m in ("B0","B1","B2")}
            final={m:dict(metadata=dict(input_id="b",roles=["native_test"]),rows=copy.deepcopy(rows),pipeline_status=None) for m,rows in initial.items()}
            (root/"raw/b.json").write_text(json.dumps(dict(input_id="b",raw_execution=dict(status="failed"))))
            (root/"evaluation/b.json").write_text(json.dumps(final));(root/"evaluation/b.not_started.json").write_text(json.dumps(initial))
            self.assertEqual(c.recoverable_next(root,["a","b","c"],["a"]),["b"])
class CollectionTests(unittest.TestCase):
    def test_prefix_boundary_suffix_fixed_denominators(self):
        reporter=c.module(D/"TEST_STAGE_B_report.py","synthetic_frozen_report_collect")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/"old";new=root/"new";ledger={};ivs=[]
            for directory,ids in ((old,["a","b"]),(new,["c"])):
                (directory/"evaluation").mkdir(parents=True);(directory/"raw").mkdir()
                for iid in ids:
                    ledger[iid]=dict(record_id="record-"+iid,connectivity_sha256="graph-"+iid)
                    initial={};final={}
                    for method in ("B0","B1","B2"):
                        context=list(dict(baseline=method,truth_basis="source_relative_current_serialization",nucleus="13C",task_semantics="derived_serialized_value_bin",target_level="parent",target_semantics="set",record_id="record-"+iid,connectivity_id="graph-"+iid).items())
                        row=dict(metric="exact_observation",observation_id="obs",context=context,eligible=True,prediction_supported=False,success=False,reason_codes=["unsupported"],failure_labels=["unknown"],eligibility_reason_codes=["frozen"],eligibility_determinator=[])
                        initial[method]=[row];final[method]=dict(rows=[copy.deepcopy(row)],metadata=dict(input_id=iid,roles=["native_test"]),pipeline_status=None)
                    c.write(directory/"evaluation"/(iid+".not_started.json"),initial)
                    if iid!="b":
                        c.write(directory/"evaluation"/(iid+".json"),final);c.write(directory/"raw"/(iid+".json"),dict(input_id=iid,plan_sha256="plan"))
                ivs.append(dict(output_sha256=c.inventory(directory)))
            bundles,origins=r.collect_rows(["a","b","c"],dict(prefix=["a"],boundary=["b"],suffix=["c"]),old,ivs[0],new,ivs[1],reporter,ledger,"plan")
            self.assertEqual(set(bundles),{"a","b","c"});self.assertEqual(origins["b"],"boundary_saved_initial_unknown")
            self.assertTrue(all(v["eligible"] for b in bundles.values() for m in b.values() for v in m["rows"]))
            self.assertFalse(any(v["success"] for b in bundles.values() for m in b.values() for v in m["rows"]))
class TerminalTests(unittest.TestCase):
    def test_guard_kill_true_shape_inner_unobserved(self):
        terminal=dict(schema="TEST_STAGE_B_phase_actual_v1",phase="score",status="FAILED_OR_PARTIAL_RETAINED_NO_RETRY",started_UTC="2026-10-27T20:00:00+00:00",finished_UTC="2026-10-27T22:00:00+00:00",actual_outer_exit=1,actual_worker_exit=-9,actual_inner_exit=None,termination_reason="wall_limit",last_worker_stage="phase_child_running",leader_reaped=True,owned_survivors=[],once_claim=dict(path="claim",sha256="a"*64))
        original=copy.deepcopy(terminal);self.assertIsNone(c.validate_terminal(terminal)["actual_inner_exit"]);self.assertEqual(terminal,original);self.assertNotIn("child_output_inventory",terminal)
    def test_unknown_outer_rejected(self):
        with self.assertRaises(ValueError):c.validate_terminal(dict(actual_outer_exit=None))
    def test_success_original_unused(self):
        with self.assertRaises(ValueError):c.validate_terminal(dict(actual_outer_exit=0))
    def test_survivor_rejected(self):
        with self.assertRaises(ValueError):c.validate_terminal(dict(actual_outer_exit=1,termination_reason="wall_limit",leader_reaped=True,owned_survivors=[1],once_claim={}))
class SeamRegressionTests(unittest.TestCase):
    def test_partial_tmp_is_touched_and_rejected_outside_boundary(self):
        for directory,name in (("evaluation","c.not_started.json.tmp"),("evaluation","c.json.tmp"),("raw","c.payload.json.tmp"),("raw","c.json.tmp")):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/directory).mkdir();(root/directory/name).write_text("{")
                self.assertEqual(c.touched_ids(root),{"c"})
                with self.assertRaises(ValueError):c.partition(["a","b","c"],["a"],c.touched_ids(root))
                self.assertEqual(c.recoverable_next(root,["a","b","c"],["a"]),[])
    def test_saved_bundle_matching_off_P1_integration(self):
        reporter=c.module(D/"TEST_STAGE_B_report.py","saved_only_P1_real_guard")
        axes=[];applied=[];expected={}
        for method,status,threshold in (("B0","off_insufficient_support",None),("B1","off_audit_rejected",999),("B2","off_audit_rejected",123)):
            semantic=dict(method=method,nucleus="13C",truth_basis="source_relative_current_serialization",task_semantics="derived_serialized_value_bin",target_level="parent",target_semantics="set",endpoint="per_peak_compatibility",sampling_unit="observation")
            axis=dict(semantic,cohort_sha256="synthetic-cohort",source_sha256="synthetic-source",label_sha256="synthetic-label",rule_sha256="synthetic-rule")
            axes.append(dict(axis=axis,status=status,threshold=threshold,published_ids=[]))
            row=SimpleNamespace(observation_id="obs",context=tuple(dict(baseline=method,**{k:v for k,v in semantic.items() if k not in ("method","endpoint","sampling_unit")}).items()))
            bundle=dict(rows=[],metadata=dict(input_id="synthetic",roles=["native_test"]),pipeline_status=dict(observation_determinate={"obs":True}))
            # Actual saved-only shape: no reference/mapping/certificate/margin.
            value=r.frozen_off_application(row,bundle,axes);applied.append(dict(input_id="synthetic",**value))
            expected[("synthetic",method,"obs")]=dict(semantic_axis=semantic,pipeline_available=True)
            self.assertEqual(value["stored_threshold"],threshold);self.assertFalse(value["publication_enabled"])
            self.assertNotIn("margin",value);self.assertNotIn("margin_certified",value)
        self.assertEqual(reporter.validate_threshold_applications(applied,expected,axes)["validated_applications"],3)
        corrupted=copy.deepcopy(applied);corrupted[1]["stored_threshold"]=1000
        with self.assertRaises(ValueError):reporter.validate_threshold_applications(corrupted,expected,axes)
    def test_complete_validate_path_terminal_bindings(self):
        # Only file loading/literalSHA IO is synthetic; production complete
        # validate predicates, inventory, partition and terminal logic execute.
        with tempfile.TemporaryDirectory() as tmp:
            rootbase=Path(tmp).resolve();root=rootbase/"old";(root/"evaluation").mkdir(parents=True);(root/"raw").mkdir()
            (root/"record_completion_ledger.json").write_text(json.dumps([dict(input_id="a")]))
            (root/"evaluation/b.not_started.json").write_text(json.dumps({m:[dict(prediction_supported=False,success=False)] for m in ("B0","B1","B2")}))
            claimroot=rootbase/"once";claimroot.mkdir()
            item=lambda n,h=None:dict(path=n,sha256=h or n+"-hash")
            suiteitem=item("suite","aed363b9438186765745f4f568f71ba183904dc4b3f2c60ccef8c7831f79baf7")
            originalitem=item("original","f5270fc73c400d9a112273c02ef6ae5c1f209d8614886c700a0388681f69f74e")
            owneritem=item("owner","7c1cf21c46fb852b7e3cb430bab6f52b4e6babe211372ac223cb14b573150d82")
            phaseitem=item("phase","7e12a1fc4ced86c6749b8937eb2903b2cb09aa6ef318576a15eab210068d96b7")
            delegate=item("delegate","89abefe3ef4e90675cb911bf56e34df329bd279887bd5255144a8e5aa8fe8cb5")
            budget=dict(CPU_threads=1,GPU=0,RSS_bytes=8589934592,total_wall_seconds=7200,record_workers=1,cleanup_seconds=60)
            suite=dict(once_claim_root=str(claimroot),score_repo="synthetic-repo",budget=dict(score=budget),implementations=dict(locked_caller=item("caller",c.CALLER_SHA)))
            original=dict(repo="synthetic-repo",output_directory=str(root),input_ids=["a","b","c"],inputs={},implementations=[])
            owner=dict(schema="original_owner_test_stage_B_execution_release_v1",decision="ALLOW_ONCE_C_FIXED_TEST_STAGE_B",suite_manifest_sha256=suiteitem["sha256"],once_claim_root=str(claimroot),release_id="synthetic-original")
            config=dict(ordered_input_ids=original["input_ids"],original_C_identity_count=3637,output_directory=str(root),delegate_plan=originalitem,delegate_owner_release=delegate)
            phase=dict(schema="TEST_STAGE_B_execution_phase_v1",phase="score",suite_manifest_sha256=suiteitem["sha256"],budget=budget,config=item("config"))
            claimpath=str(claimroot/(hashlib.sha256((owner["release_id"]+"\0score\0execution").encode()).hexdigest()+".json"));claimitem=item(claimpath)
            claim=dict(schema="TEST_STAGE_B_persistent_once_claim_v1",phase="score",scope="execution",suite_manifest_sha256=suiteitem["sha256"],owner_release_sha256=owneritem["sha256"],release_id=owner["release_id"],claim_PID=123)
            request=dict(suite=suiteitem,release=owneritem,phase=phaseitem)
            inputs={v["path"]:v["sha256"] for v in (suiteitem,owneritem,phaseitem,phase["config"])};inputs.update({v["path"]:v["sha256"] for v in suite["implementations"].values()});inputs.update({v["path"]:v["sha256"] for v in config.values() if isinstance(v,dict) and "path" in v})
            terminal=dict(schema="TEST_STAGE_B_phase_actual_v1",phase="score",status="FAILED_OR_PARTIAL_RETAINED_NO_RETRY",started_UTC="2026-10-27T20:00:00+00:00",finished_UTC="2026-10-27T22:00:00+00:00",actual_outer_exit=1,actual_worker_exit=-9,actual_inner_exit=None,termination_reason="wall_limit",leader_reaped=True,owned_survivors=[],once_claim=claimitem,child_PID=123,request_items=request,phase_input_sha256=inputs,last_worker_stage="phase_child_running")
            objects=dict(suite=suite,original=original,owner=owner,phase=phase,config=config,terminal=terminal,partial=dict(output_sha256=c.inventory(root)),inputseal=dict(input_sha256={}));objects[claimpath]=claim
            plan=dict(schema="TEST_STAGE_B_conditional_completion_plan_v1",execution_authorized=True,segment_index=2,third_segment_allowed=False,scope_authorization=item("authorization",c.AUTH_SHA),original_suite=suiteitem,original_scoring_plan=originalitem,original_delegate_release=delegate,original_terminal_receipt=item("terminal"),original_claim=claimitem,original_partial_inventory=item("partial"),original_input_inventory=item("inputseal"),ordered_suffix_ids=["c"],interrupted_unknown_ids=["b"],budget=dict(budget,total_wall_seconds=615),output_directory=str(rootbase/"completion_segment_2/result"),started_directory=str(rootbase/"completion_segment_2/started"),segment_claim_path=str(claimroot/"CONDITIONAL_COMPLETION_SEGMENT_2.json"))
            def run(objects):
                actualsha=c.sha
                with patch.object(c,"load",side_effect=lambda it:objects[it["path"]]),patch.object(c,"sha",side_effect=lambda p:c.AUTH_SHA if p=="authorization" else actualsha(p)),patch.dict(os.environ,{"TEST_STAGE_B_COMPLETION_SUFFIX_N":"1"}):return c.validate(plan)
            self.assertIsNone(run(copy.deepcopy(objects))[2]["actual_inner_exit"])
            mutations=[("phase",lambda x:x["terminal"].update(phase="prediction")),("owner",lambda x:x["terminal"]["request_items"]["release"].update(sha256="wrong")),("phase_manifest",lambda x:x["terminal"]["request_items"]["phase"].update(sha256="wrong")),("suite",lambda x:x["terminal"]["request_items"]["suite"].update(path="wrong")),("claim_owner",lambda x:x[claimpath].update(owner_release_sha256="wrong")),("input_closure",lambda x:x["terminal"]["phase_input_sha256"].update(foreign="wrong")),("schema",lambda x:x["terminal"].update(schema="UNRELATED_TERMINAL")),("status",lambda x:x["terminal"].update(status="COMPLETED"))]
            for name,mutate in mutations:
                with self.subTest(name=name):
                    changed=copy.deepcopy(objects);mutate(changed)
                    with self.assertRaises((ValueError,KeyError)):run(changed)
            # Known partial tmp suffix evidence traverses complete validate too.
            (root/"evaluation/c.not_started.json.tmp").write_text("{");changed=copy.deepcopy(objects);changed["partial"]["output_sha256"]=c.inventory(root)
            with self.assertRaises(ValueError):run(changed)
class SourceTests(unittest.TestCase):
    def test_scientific_run_AST_only_one_hook(self):
        source=(D/"TEST_STAGE_B_C_caller.py").read_text();self.assertEqual(c.sha(D/"TEST_STAGE_B_C_caller.py"),c.CALLER_SHA)
        tree=ast.parse(source);old=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="run")
        new=ast.parse(c.transformed_run(source)).body[0]
        class Remove(ast.NodeTransformer):
            def visit_Expr(self,node):
                if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=="completion_started":return None
                return self.generic_visit(node)
        self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(Remove().visit(new),include_attributes=False))
    def test_hook_after_deadlines_before_read(self):
        source=c.transformed_run((D/"TEST_STAGE_B_C_caller.py").read_text())
        self.assertLess(source.index("preprocessing_deadline ="),source.index("completion_started("));self.assertLess(source.index("completion_started("),source.index("        one ="))
    def test_original_P1_reused(self):
        source=(D/"TEST_STAGE_B_completion_report.py").read_text();self.assertIn("reporter.validate_threshold_applications(applied,expected,frozen)",source);self.assertIn("reporter.estimate_native_test(rows",source)
    def test_frozen_supervisor_timeout_cleanup(self):
        # Blocks on a signal, not an arbitrary timed sleep; business wall drives cleanup.
        frozen=c.module(D/"TEST_STAGE_B_phase_supervisor.py","synthetic_completion_supervisor")
        with tempfile.TemporaryDirectory() as tmp:
            result=frozen.supervise_process([sys.executable,"-c","import signal; signal.pause()"],directory=tmp,prefix="synthetic",budget=dict(CPU_threads=1,RSS_bytes=8589934592,total_wall_seconds=.2,cleanup_seconds=2),cwd=tmp,phase="synthetic")
            self.assertEqual(result["termination_reason"],"wall_limit");self.assertEqual(result["actual_outer_exit"],1);self.assertTrue(result["leader_reaped"]);self.assertEqual(result["owned_survivors"],[])
if __name__=="__main__":unittest.main(verbosity=2)
