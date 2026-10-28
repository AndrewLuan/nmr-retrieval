"""功能：用标准库假对象检查 assignment-margin 续跑与离线评估准入契约。

代码关系：从 nmr_transfer/h_assignment_margin_train.py 抽取续跑控制函数；从
research/peak_assignment/h_assignment_margin 的三个适配器抽取元数据门禁。
_extract 只编译选定函数，FakeOwner/FakeMetrics 模拟带环的资源所有者；
MarginRuntimeContracts 核保留作业、剩余曝光、异常停止和 finally 释放。
MarginMetadataGates 核共享门禁一致、关闭 release 和失败终态被拒绝。
输入全为人工身份与控制 JSON，输出仅在 TemporaryDirectory 内；不导入业务模块、
torch/scipy，不加载权重，不调用实际训练、forward、solver、评估或资源探测。
弱引用检查证明 Python 所有者释放，不能据此推断真实 RSS 或科学结果。
"""
import ast
import copy
import gc
import hashlib
import json
import random
import tempfile
import time
import unittest
import weakref
from collections import Counter
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
TRAINER = ROOT / "nmr_transfer/h_assignment_margin_train.py"
ADAPTERS = ROOT / "research/peak_assignment/h_assignment_margin"


def _tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def _extract(path, names, **environment):
    nodes = [node for node in _tree(path).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in nodes} != set(names):
        raise AssertionError("requested control function missing")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), environment)
    return environment


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FakeOwner:
    def __init__(self, track, kind, seed=None):
        self.track, self.kind, self.seed = track, kind, seed
        self.cycle = self
        track["refs"].append((kind, weakref.ref(self)))
        if kind in ("model", "teacher"):
            self.parameter = FakeOwner(track, "parameter")
            self.cache = lambda: self

    def __deepcopy__(self, memo):
        return FakeOwner(self.track, "teacher", self.seed)

    def to(self, _):
        return self

    def eval(self):
        return self

    def requires_grad_(self, _):
        return self

    def parameters(self):
        return [self.parameter]

    def state_dict(self):
        return {"synthetic_seed": self.seed}


class FakeMetrics(dict):
    def __init__(self, track, batch, keys):
        super().__init__({key: 0 for key in keys})
        self.owner, self.cycle = batch, self
        track["refs"].append(("metrics", weakref.ref(self)))


class MarginRuntimeContracts(unittest.TestCase):
    def run_completion(self, failure=False):
        constants = {}
        for node in _tree(TRAINER).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"SEEDS", "MARGIN_ACCOUNTING_KEYS"}:
                        constants[target.id] = ast.literal_eval(node.value)
        env = _extract(TRAINER, {"paired_train", "epoch_order", "identity_order_sha256"},
                       copy=copy, gc=gc, hashlib=hashlib, json=json, random=random,
                       time=time, Path=Path, **constants)
        ids = ["synthetic:%04d" % i for i in range(615)]
        orders = {seed: env["identity_order_sha256"]([
            [ids[i] for i in batch] for batches in env["epoch_order"](615, seed)
            for batch in batches]) for seed in constants["SEEDS"]}
        retained = dict(seed=211, variant="A", steps=770, checkpoint="synthetic_retained.pt",
                        sha256="a" * 64, actual_order_sha256=orders[211],
                        selection="final_epoch_10_only")
        track = dict(refs=[], starts=[], steps=Counter(), saves=[], statuses={})
        state = {}

        def live():
            return [kind for kind, ref in track["refs"] if ref() is not None]

        def factory():
            self.assertEqual(live(), [], "previous job retains owners before next factory")
            track["starts"].append(state["seed"])
            return FakeOwner(track, "model", state["seed"])

        def optimizer(model):
            value = FakeOwner(track, "optimizer")
            value.owner = model
            return value

        def step(model, teacher, batch, optimizer, *, variant, margin_records):
            self.assertEqual(model.seed, teacher.seed)
            if failure:
                raise RuntimeError("synthetic_step_failure")
            track["steps"][model.seed, variant] += 1
            return FakeMetrics(track, batch, constants["MARGIN_ACCOUNTING_KEYS"])

        env.update(
            torch=SimpleNamespace(manual_seed=lambda seed: state.update(seed=seed),
                                  save=lambda value, path: track["saves"].append(path.name)),
            Batch=SimpleNamespace(from_data_list=lambda _: FakeOwner(track, "batch")),
            configure_head=optimizer, train_step=step, validate_release=lambda *_: None,
            sha256=lambda path: hashlib.sha256(str(path).encode()).hexdigest(),
            atomic_json=lambda path, value: track["statuses"].update({path.name: value}))
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "models"
            was_enabled = gc.isenabled()
            gc.disable()
            try:
                if failure:
                    try:
                        env["paired_train"](factory, list(range(615)), [{} for _ in ids],
                            "synthetic_release", ids, out,
                            completion=dict(reused_result=retained, order_sha256=orders[211]))
                    except RuntimeError as exc:
                        self.assertEqual(str(exc), "synthetic_step_failure")
                        tb = exc.__traceback__
                        while tb.tb_frame.f_code.co_name != "paired_train":
                            tb = tb.tb_next
                        self.assertTrue(all(tb.tb_frame.f_locals[name] is None
                            for name in ("model", "teacher", "optimizer", "batch", "metrics", "p")))
                        tb = None
                    else:
                        self.fail("synthetic failure was swallowed")
                    result, history = None, []
                else:
                    result = env["paired_train"](factory, list(range(615)), [{} for _ in ids],
                        "synthetic_release", ids, out,
                        completion=dict(reused_result=retained, order_sha256=orders[211]))
                    history = [json.loads(line) for line in (out / "history.jsonl").read_text().splitlines()]
                gc.collect()
                self.assertEqual(live(), [])
            finally:
                if was_enabled:
                    gc.enable()
        return track, retained, result, history, orders

    def test_retained_A_and_three_fixed_jobs_release_owners(self):
        track, retained, result, history, orders = self.run_completion()
        self.assertEqual(result[0], retained)
        self.assertEqual([(r["seed"], r["variant"], r["steps"]) for r in result],
                         [(211, "A", 770), (211, "B", 770), (193, "A", 770), (193, "B", 770)])
        self.assertEqual(track["starts"], [211, 193, 193])
        self.assertEqual(track["steps"], Counter({(211, "B"): 770, (193, "A"): 770, (193, "B"): 770}))
        self.assertEqual(track["saves"], ["211_B_epoch10.pt", "193_A_epoch10.pt", "193_B_epoch10.pt"])
        self.assertEqual([r["cumulative_steps"] for r in history], list(range(1, 2311)))
        for row in result:
            self.assertEqual(row["actual_order_sha256"], orders[row["seed"]])
        self.assertEqual({kind for kind, _ in track["refs"]},
                         {"model", "teacher", "parameter", "optimizer", "batch", "metrics"})

    def test_failure_stops_before_next_job_and_releases_locals(self):
        track, *_ = self.run_completion(failure=True)
        self.assertEqual(track["starts"], [211])
        self.assertEqual(track["saves"], [])
        stopped = track["statuses"]["paired_stop.json"]
        self.assertFalse(stopped["retry"])
        self.assertEqual((stopped["seed"], stopped["variant"], stopped["steps"]), (211, "B", 0))


class MarginMetadataGates(unittest.TestCase):
    def test_segmented_helpers_match_and_current_failure_is_rejected(self):
        helpers = []
        for filename in ("cache_adapter.py", "score_adapter.py", "paired_summary.py"):
            path = ADAPTERS / filename
            helper = next(n for n in _tree(path).body
                          if isinstance(n, ast.FunctionDef) and n.name == "_validate_segmented_completion")
            helpers.append(ast.dump(helper, include_attributes=False))
            env = _extract(path, {"need", "_validate_segmented_completion"})
            with self.assertRaisesRegex(ValueError, "segmented_completion_status"):
                env["_validate_segmented_completion"](
                    {"schema": "bounded_H211_JJ_segmented_completion_execution_v1",
                     "status": "COMPLETION_FAILED_PRIOR_FAILURES_RETAINED"}, {}, [],
                    lambda _: self.fail("failed terminal must precede metadata reads"),
                    lambda _: self.fail("failed terminal must precede reference verification"))
        self.assertEqual(helpers, [helpers[0]] * 3)

    def test_closed_releases_reject_before_training_evidence(self):
        closed = dict(schema="frozen_AB_evaluation_release_v1", evaluation_release=False)
        forbidden = lambda *_: self.fail("closed release read training evidence")
        env = _extract(ADAPTERS / "score_adapter.py", {"need", "training_gate"},
                       read_ref=forbidden, checked_ref=forbidden)
        with self.assertRaisesRegex(ValueError, "evaluation_release_closed"):
            env["training_gate"](closed)
        env = _extract(ADAPTERS / "paired_summary.py", {"need", "validate_training_gate"}, read_ref=forbidden)
        with self.assertRaisesRegex(ValueError, "evaluation release closed"):
            env["validate_training_gate"](closed)
        with tempfile.TemporaryDirectory() as folder:
            release = Path(folder) / "release.json"
            release.write_text(json.dumps(closed))
            env = _extract(ADAPTERS / "cache_adapter.py", {"need", "validate_evaluation_release"},
                           sha=_sha, json=json, Path=Path, validate_training_success=forbidden)
            with self.assertRaisesRegex(ValueError, "evaluation_execution_closed"):
                env["validate_evaluation_release"](SimpleNamespace(release=release, release_sha256=_sha(release)))

    def test_nonzero_actual_terminal_cannot_open_any_adapter(self):
        failed = dict(success=False, actual_child_exit=1, actual_outer_exit=1,
                      stop_reason="synthetic_failure")
        release = dict(schema="frozen_AB_evaluation_release_v1", evaluation_release=True,
                       inputs={name: {"path": name, "sha256": "0" * 64} for name in
                               ("training_success_receipt", "training_complete", "exposure_order_receipt")},
                       final_checkpoints={key: {} for key in ("211_A", "211_B", "193_A", "193_B")})
        env = _extract(ADAPTERS / "score_adapter.py", {"need", "training_gate"},
                       read_ref=lambda _: failed, checked_ref=lambda _: None)
        with self.assertRaisesRegex(ValueError, "actual_training_not_successful"):
            env["training_gate"](release)
        with tempfile.TemporaryDirectory() as folder:
            for name, ref in release["inputs"].items():
                path = Path(folder) / (name + ".json")
                path.write_text(json.dumps(failed if name == "training_success_receipt" else {}))
                ref.update(path=str(path), sha256=_sha(path))
            env = _extract(ADAPTERS / "cache_adapter.py", {"need", "validate_training_success"},
                           sha=_sha, json=json, Path=Path)
            with self.assertRaisesRegex(ValueError, "training_actual_not_success"):
                env["validate_training_success"](release)
            env = _extract(ADAPTERS / "paired_summary.py", {"need", "validate_training_gate"},
                           read_ref=lambda ref: Path(ref["path"]), sha=_sha, json=json, MISSING=object())
            with self.assertRaisesRegex(ValueError, "successful paired training terminal required"):
                env["validate_training_gate"](release)


if __name__ == "__main__":
    unittest.main()
