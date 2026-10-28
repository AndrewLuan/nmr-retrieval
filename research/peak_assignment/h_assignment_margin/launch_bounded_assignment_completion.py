"""功能概述：固定H211剩余三作业的独立completion监督，不覆盖两次旧失败或已完成A段。
只接受root绑定plan、closed release及其单training_release翻转；关闭在子进程前拒绝。
verify_completion_bindings固定原615、合同/保留段/三作业/唯一输出；只对A权重做SHA，永不载入。
verify_completion_time_accounting核两原实际失败和floor(14387-302.6096761659719)=14084。
supervise沿冻结CPU2/GPU0/RSS4GiB监督新独占进程组；无重试或科学参数调整。
成功只表示保留211A加三新作业完整闭包，receipt明确保留旧failed exits/segment provenance。
CLI required --budget/--release/--completion-plan/--completion-plan-sha256/--out；本源码准备不执行科学调用。
"""
import argparse
import datetime
import hashlib
import importlib.metadata
import json
import math
import os
import platform
from pathlib import Path
import signal
import subprocess
import sys
import time

import psutil


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_ref(ref):
    if digest(ref["path"]) != ref["sha256"]:
        raise ValueError("bound_file_changed: " + ref["path"])


def verify_linux_backend(budget, run):
    """验证 JJ 实际 metadata 与 solver-config；只读文件，不导入 SciPy 或模型。"""
    metadata_ref = budget["linux_backend_metadata"]
    verify_ref(metadata_ref)
    metadata = json.loads(Path(metadata_ref["path"]).read_text())
    if platform.system() != "Linux" or not sys.platform.startswith("linux"):
        raise ValueError("jj_linux_runtime_required")
    if metadata.get("system") != "Linux":
        raise ValueError("linux_backend_metadata_system")
    if Path(metadata["python_executable"]).resolve() != Path(sys.executable).resolve():
        raise ValueError("linux_backend_interpreter_binding")
    backend = budget["record_solver_budget"]["backend"]
    if metadata.get("backend") != backend:
        raise ValueError("linux_backend_metadata_binding")
    if importlib.metadata.version("scipy") != backend["scipy_version"]:
        raise ValueError("linux_backend_scipy_version")
    binary_path = backend["highs_binary"]["path"]
    if not binary_path.endswith(".so") or "darwin" in binary_path.lower():
        raise ValueError("linux_backend_binary_required")
    for key in ("milp_source", "highs_wrapper", "highs_binary"):
        verify_ref(backend[key])
    solver_ref = run["inputs"]["solver_config"]
    verify_ref(solver_ref)
    solver = json.loads(Path(solver_ref["path"]).read_text())
    if solver != budget["record_solver_budget"]:
        raise ValueError("solver_budget_config_binding")
    limits = {k: v for k, v in solver.items() if k != "backend"}
    if limits != dict(argmin_wall_seconds=5, record_wall_seconds=10, node_limit=100000,
                      max_candidates=100000, max_variables=100000, threads=1,
                      random_seed=0, mip_rel_gap=0):
        raise ValueError("frozen_record_solver_budget")
    return metadata_ref


def load_bound(ref):
    verify_ref(ref)
    return json.loads(Path(ref["path"]).read_text())


def verify_completion_time_accounting(budget, plan):
    """两次旧失败按实际秒数扣除；不改写旧退出，不把诊断时间充作新预算。"""
    refs=plan["prior_failed_attempts"]
    expected={"original_initialization":"d94721f057ba6e00fff24fa28539dff3759ce12b53943ca9b349354202ccb64b","JJ_resource_stop":"4a43c91e968b468f160e0fdc4ad3733e45e7f6e7fea87a35f2821929b4bad0e8"}
    if set(refs)!=set(expected):raise ValueError("two_original_failed_receipts_required")
    original={}
    for name,h in expected.items():
        if refs[name]["sha256"]!=h:raise ValueError("prior_receipt_SHA")
        original[name]=load_bound(refs[name])
    first=original["original_initialization"];second=original["JJ_resource_stop"]
    if first.get("success") is not False or first.get("actual_child_exit")!=1 or first.get("actual_outer_exit")!=1:raise ValueError("original_initialization_failure_preserved")
    if second.get("success") is not False or second.get("actual_child_exit")!=-15 or second.get("actual_outer_exit")!=1 or second.get("stop_reason")!="resource_rss_limit":raise ValueError("JJ_resource_failure_preserved")
    first_elapsed=first["elapsed_seconds"];second_elapsed=second["elapsed_seconds"]
    if not all(type(x) in (int,float) and math.isfinite(x) and x>=0 for x in (first_elapsed,second_elapsed)):raise ValueError("prior_elapsed_invalid")
    if first["budget"]["resources"]["max_wall_seconds"]!=14400 or second["budget"]["resources"]["max_wall_seconds"]!=14387:raise ValueError("original_wall_budgets")
    recovery_remaining=math.floor(14400-first_elapsed)
    remaining=math.floor(recovery_remaining-second_elapsed)
    if recovery_remaining!=14387 or second_elapsed!=302.6096761659719 or remaining!=14084 or budget["resources"]["max_wall_seconds"]!=remaining:raise ValueError("completion_remaining_wall_budget")
    return dict(prior_failed_receipts=refs,original_initialization=dict(actual_child_exit=1,actual_outer_exit=1,success=False,elapsed_seconds=first_elapsed),JJ_resource_stop=dict(actual_child_exit=-15,actual_outer_exit=1,success=False,stop_reason="resource_rss_limit",elapsed_seconds=second_elapsed),remaining_wall_seconds=remaining,diagnostics_accounted_separately=True)


def verify_completion_bindings(budget, release, plan_path, plan_sha, out):
    """核plan DAG、唯一输出、保留段及closed→approved仅单flag变化。无模型或历史权重反序列化。"""
    plan_ref=dict(path=str(plan_path),sha256=plan_sha)
    if budget.get("completion_plan")!=plan_ref or release.get("completion_plan")!=plan_ref:raise ValueError("completion_plan_three_way_binding")
    plan=load_bound(plan_ref)
    keys={"schema","run_config","trainer","continuation_contract","completed_segment_identity","prior_failed_attempts","remaining_jobs","retained_job","resources","output_directory"}
    if set(plan)!=keys or plan["schema"]!="H211_fixed_AB_completion_plan_v1":raise ValueError("completion_plan_schema")
    resources=dict(cpu_threads=2,gpu_count=0,max_wall_seconds=14084,max_process_tree_rss_bytes=4294967296)
    schedule=[dict(seed=211,variant="B",steps=770),dict(seed=193,variant="A",steps=770),dict(seed=193,variant="B",steps=770)]
    if plan["resources"]!=resources or budget["resources"]!=resources or plan["remaining_jobs"]!=schedule or plan["retained_job"]!="211_A":raise ValueError("fixed_completion_schedule_resources")
    if str(out)!=plan["output_directory"]:raise ValueError("fixed_completion_output_directory")
    if plan["run_config"]!=budget["run_config"] or plan["trainer"]!=release["sources"]["trainer"]:raise ValueError("plan_source_run_binding")
    for name in ("run_config","trainer","continuation_contract","completed_segment_identity"):verify_ref(plan[name])
    if plan["continuation_contract"]["sha256"]!="56feca689a1824fe60a479dafc848be10244167b9bacc4c2ef9a98ec00a18d3e" or plan["completed_segment_identity"]["sha256"]!="2cffa7ffc26d41a1bec303c663f244ab9179dc7527f96da06bd93e065212e384":raise ValueError("root_contract_identity_binding")
    contract=load_bound(plan["continuation_contract"]);identity=load_bound(plan["completed_segment_identity"])
    if contract["schema"]!="H211_completion_continuation_contract_v1" or identity["schema"]!="H211_completed_segment_identity_v1":raise ValueError("contract_identity_schema")
    for name in ("resources","remaining_jobs","retained_job","output_directory","prior_failed_attempts","completed_segment_identity"):
        if contract[name]!=plan[name]:raise ValueError("contract_plan_binding:"+name)
    for name in ("checkpoint","history","source_run_config","source_execution_receipt","source_execution_budget"):verify_ref(identity[name])
    if identity["checkpoint"]["sha256"]!="813ba60ac804ae109eb7abf14aab26498eeabf1c62662583a301581ff5884a06" or identity["history"]["sha256"]!="bb0c985f199f013a91b38b72bd29ba9047c120c9cb9b13c64967479a1eee46c3":raise ValueError("retained_segment_literal_binding")
    job=identity["completed_job"]
    if (job["seed"],job["variant"],job["steps"],job["selection"])!=(211,"A",770,"final_epoch_10_only") or job["checkpoint"]!=identity["checkpoint"]["path"] or job["sha256"]!=identity["checkpoint"]["sha256"]:raise ValueError("retained_job_binding")
    closed=load_bound(budget["closed_release"])
    if closed.get("training_release") is not False:raise ValueError("closed_release_snapshot_required")
    approved=dict(closed,training_release=True)
    if release!=approved:raise ValueError("approved_release_only_training_flag_delta")
    accounting=verify_completion_time_accounting(budget,plan)
    return plan,identity,accounting


def save(path, value):
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def snapshot(pid):
    try:
        root = psutil.Process(pid)
        tree = [root] + root.children(recursive=True)
    except psutil.NoSuchProcess:
        return 0
    total = 0
    for process in tree:
        try:
            total += process.memory_info().rss
        except psutil.NoSuchProcess:
            pass
    return total


def stop_group(child):
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        return child.wait(timeout=10)


def supervise(budget, release_path, out, plan_path, plan_sha):
    release = json.loads(release_path.read_text())
    if release.get("training_release") is not True:
        raise ValueError("training_release_closed")
    if budget.get("schema")!="H211_fixed_AB_completion_budget_v1":raise ValueError("completion_budget_schema")
    verify_ref(budget["run_config"])
    verify_ref(budget["launcher"])
    if Path(budget["launcher"]["path"]).resolve() != Path(__file__).resolve():
        raise ValueError("executed_launcher_binding")
    run = json.loads(Path(budget["run_config"]["path"]).read_text())
    if release.get("run_config_sha256") != budget["run_config"]["sha256"]:
        raise ValueError("release_run_config_binding")
    if release.get("inputs") != run["inputs"] or release.get("admitted_input_ids") != run["input_ids"]:
        raise ValueError("release_data_domain_binding")
    if len(run["input_ids"]) != 615 or run["device"] != "cpu":
        raise ValueError("frozen_execution_domain")
    resources = budget["resources"]
    if resources != dict(cpu_threads=2, gpu_count=0, max_wall_seconds=14084,
                         max_process_tree_rss_bytes=4294967296):
        raise ValueError("frozen_outer_budget")
    if budget["fixed_update_budget"] != dict(
            seeds=[211, 193], arms=["A", "B"], epochs=10, batch=8, records=615,
            steps_per_arm_seed=770, drop_last=False):
        raise ValueError("frozen_fixed_update_budget")
    if budget.get("retry") is not False or budget.get("release_required") is not True:
        raise ValueError("closed_release_and_no_retry_required")
    plan,identity,accounting = verify_completion_bindings(budget,release,plan_path,plan_sha,out)
    metadata_ref = verify_linux_backend(budget, run)
    for ref in list(release["inputs"].values()) + list(release["sources"].values()):
        verify_ref(ref)
    out.mkdir(exist_ok=False)
    command = [sys.executable, "-m", "nmr_transfer.h_assignment_margin_train",
               "--run-config", budget["run_config"]["path"], "--release", str(release_path),
               "--completion-plan",str(plan_path),"--completion-plan-sha256",plan_sha,
               "--out", str(out / "models")]
    env = dict(os.environ, OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2",
               CUDA_VISIBLE_DEVICES="", PYTHONHASHSEED="0")
    started = time.monotonic()
    receipt = dict(schema="bounded_H211_JJ_segmented_completion_execution_v1", command=command,
                   started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   budget=budget, release_sha256=digest(release_path), success=False,
                   linux_backend_metadata=metadata_ref,
                   prior_failed_attempts=accounting,completion_plan=dict(path=str(plan_path),sha256=plan_sha),
                   retained_segment_identity=plan["completed_segment_identity"],retained_211_A_checkpoint=identity["checkpoint"],
                   stop_reason=None, actual_child_exit=None, peak_tree_rss_bytes=0)
    save(out / "claim.json", receipt)
    child = None
    try:
        with (out / "stdout.log").open("w") as stdout, (out / "stderr.log").open("w") as stderr:
            child = subprocess.Popen(command, cwd=budget["working_directory"], env=env,
                                     stdout=stdout, stderr=stderr, start_new_session=True)
            receipt["pid"] = child.pid
            last_status = -30.
            while child.poll() is None:
                elapsed = time.monotonic() - started
                rss = snapshot(child.pid)
                receipt["peak_tree_rss_bytes"] = max(receipt["peak_tree_rss_bytes"], rss)
                if elapsed >= resources["max_wall_seconds"]:
                    receipt["stop_reason"] = "resource_wall_limit"
                elif rss > resources["max_process_tree_rss_bytes"]:
                    receipt["stop_reason"] = "resource_rss_limit"
                if receipt["stop_reason"]:
                    stop_group(child)
                    break
                if elapsed - last_status >= 30:
                    save(out / "status.json", dict(receipt, elapsed_seconds=elapsed, state="running"))
                    last_status = elapsed
                time.sleep(.25)
            receipt["actual_child_exit"] = child.wait()
        if receipt["stop_reason"] is None and child.returncode != 0:
            receipt["stop_reason"] = "child_engineering_initialization_or_solver_failure"
        if receipt["stop_reason"] is None:
            complete = json.loads((out / "models/complete.json").read_text())
            jobs = complete["results"]
            if len(jobs) != 4 or {(r["seed"], r["variant"]) for r in jobs} != {
                    (211, "A"), (211, "B"), (193, "A"), (193, "B")}:
                raise ValueError("incomplete_fixed_four_jobs")
            for row in jobs:
                if row["steps"] != 770 or row["selection"] != "final_epoch_10_only":
                    raise ValueError("paired_update_budget_mismatch")
                verify_ref(dict(path=row["checkpoint"], sha256=row["sha256"]))
            for seed in (211, 193):
                paired = [r for r in jobs if r["seed"] == seed]
                if not paired[0].get("actual_order_sha256") or len({
                        r.get("actual_order_sha256") for r in paired}) != 1:
                    raise ValueError("paired_actual_order_mismatch")
            for ref in list(release["inputs"].values()) + list(release["sources"].values()):
                verify_ref(ref)
            verify_ref(budget["run_config"])
            verify_ref(budget["launcher"])
            verify_linux_backend(budget, run)
            verify_completion_bindings(budget,release,plan_path,plan_sha,out)
            if digest(release_path) != receipt["release_sha256"]:
                raise ValueError("release_changed_during_run")
            if jobs[0]!=identity["completed_job"]:raise ValueError("retained_A_result_changed")
            expected_new=[(211,"B"),(193,"A"),(193,"B")]
            if [(j["seed"],j["variant"]) for j in jobs[1:]]!=expected_new or complete.get("completed_new_jobs")!=jobs[1:]:raise ValueError("exact_three_new_jobs_required")
            expected_provenance=dict(completion_plan_sha256=plan_sha,continuation_contract=plan["continuation_contract"],completed_segment_identity=plan["completed_segment_identity"],retained_A_source=identity["checkpoint"],prior_failed_receipts=[plan["prior_failed_attempts"]["original_initialization"],plan["prior_failed_attempts"]["JJ_resource_stop"]])
            provenance=complete["completion_provenance"]
            if any(provenance.get(k)!=v for k,v in expected_provenance.items()):raise ValueError("segmented_completion_provenance_binding")
            if complete.get("validation_calls")!=0 or complete.get("test_calls")!=0 or complete.get("checkpoint_selection")!="epoch10_only":raise ValueError("completion_no_eval_scope")
            receipt["completion_provenance"]=provenance
            receipt["completed_new_jobs"]=jobs[1:]
            receipt["status"]="SEGMENTED_COMPLETION_SUCCESS_PRIOR_FAILURES_RETAINED"
            receipt["original_attempts_success"]=False
            receipt["success"] = True
            receipt["completed_jobs"] = jobs
    except BaseException as exc:
        receipt["stop_reason"] = receipt["stop_reason"] or "engineering_or_completion_binding_failure"
        receipt["exception"] = dict(type=type(exc).__name__, message=str(exc))
        if child is not None and child.poll() is None:
            stop_group(child)
        if child is not None:
            receipt["actual_child_exit"] = child.poll()
    if not receipt["success"]:receipt["status"]="COMPLETION_FAILED_PRIOR_FAILURES_RETAINED"
    receipt["elapsed_seconds"] = time.monotonic() - started
    receipt["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    receipt["actual_outer_exit"] = 0 if receipt["success"] else 1
    save(out / "receipt.json", receipt)
    (out / "EXIT_CODE").write_text(str(receipt["actual_outer_exit"]) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))
    return receipt["actual_outer_exit"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--completion-plan",required=True)
    parser.add_argument("--completion-plan-sha256",required=True)
    args = parser.parse_args()
    return supervise(json.loads(Path(args.budget).read_text()), Path(args.release), Path(args.out),Path(args.completion_plan),args.completion_plan_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
