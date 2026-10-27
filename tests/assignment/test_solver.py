"""功能概述：用独立穷举检验成本无关的全局归属求解器，不接触真实谱、标签或模型。
主要职责：enumerate_solutions 逐观测枚举选择并独立检查环境守恒；SolverTests 比较
MILP 的最佳解、完整 Top3、每峰排除赋值后的 margin，并覆盖 dummy、重叠、空集与非法输入。
代码库关系：仅测试 nmr_assignment.solver；超时测试替换后端返回状态或计时器，以确定性
验证非最优 incumbent 不获认证。正常数学测试使用真实 scipy.optimize.milp，未 mock 求解。
输入输出与副作用：只构造小型合成成本问题，unittest 断言失败即报错；无数据读写、外部
服务、参数搜索或训练。相同成本解仅比较合法身份及成本秩，不要求 HiGHS 指定 tie 顺序。
"""

import itertools
import math
import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from nmr_assignment.solver import Candidate, solve_assignment


def enumerate_solutions(obs, env, candidates, missing, unexplained):
    options = {j: [((), unexplained[j])] for j in obs}
    for candidate in candidates:
        options[candidate.observation_id].append((tuple(sorted(candidate.environment_ids)), candidate.cost))
    results = []
    for selected in itertools.product(*(options[j] for j in obs)):
        consumed = [i for members, _ in selected for i in members]
        if len(consumed) != len(set(consumed)):
            continue
        assignment = dict(zip(obs, (members for members, _ in selected)))
        unobserved = tuple(sorted(set(env) - set(consumed)))
        objective = math.fsum([cost for _, cost in selected] + [missing[i] for i in unobserved])
        results.append((objective, assignment, unobserved))
    return sorted(results, key=lambda item: item[0])


class SolverTests(unittest.TestCase):
    def assert_matches_enumeration(self, obs, env, candidates, missing, unexplained):
        expected = enumerate_solutions(obs, env, candidates, missing, unexplained)
        result = solve_assignment(obs, env, candidates, missing, unexplained)
        self.assertEqual(result.status, "optimal")
        self.assertTrue(result.optimal)
        self.assertTrue(result.top_k_certified)
        self.assertEqual(result.identification_quotient, "none")
        actual = (result.best,) + result.alternatives
        self.assertEqual(len(actual), min(3, len(expected)))
        self.assertEqual([x.objective for x in actual], [x[0] for x in expected[:3]])
        keys = [tuple(sorted(x.assignments.items())) for x in actual]
        self.assertEqual(len(keys), len(set(keys)))
        for solution in actual:
            self.assertTrue(solution.certified)
            self.assertIn((solution.objective, solution.assignments, solution.unobserved), expected)
            consumed = [i for members in solution.assignments.values() for i in members]
            self.assertEqual(len(consumed), len(set(consumed)))
            self.assertEqual(set(consumed) | set(solution.unobserved), set(env))
            self.assertFalse(set(consumed) & set(solution.unobserved))
            self.assertEqual(set(solution.assignments), set(obs))
            self.assertEqual(set(solution.unexplained), {j for j in obs if not solution.assignments[j]})
        for j in obs:
            alternatives = [x for x in expected if x[1][j] != result.best.assignments[j]]
            margin = result.margins[j]
            self.assertTrue(margin.certified)
            if alternatives:
                self.assertEqual(margin.status, "optimal")
                self.assertAlmostEqual(margin.value, alternatives[0][0] - result.best.objective)
            else:
                self.assertEqual(margin.status, "no_alternative")
                self.assertIsNone(margin.value)
        if len(expected) < 3:
            self.assertTrue(result.exhausted)
        return result

    def test_missing_and_unexplained(self):
        result = self.assert_matches_enumeration(
            ("signal", "impurity"), ("a", "b"), [Candidate("signal", ("a",), 0.)],
            {"a": 4., "b": 2.}, {"signal": 4., "impurity": 1.})
        self.assertEqual(result.best.unobserved, ("b",))
        self.assertEqual(result.best.unexplained, ("impurity",))
        self.assertEqual(len(result.alternatives), 1)

    def test_pair_and_shared_resource(self):
        result = self.assert_matches_enumeration(
            ("p", "q"), ("a", "b", "c"),
            [Candidate("p", ("a", "b"), 0.), Candidate("p", ("a",), 2.),
             Candidate("q", ("b",), 0.), Candidate("q", ("c",), 1.)],
            dict.fromkeys(("a", "b", "c"), 5.), {"p": 10., "q": 10.})
        self.assertEqual(result.best.assignments, {"p": ("a", "b"), "q": ("c",)})

    def test_margin_reoptimizes_other_peaks(self):
        result = self.assert_matches_enumeration(
            ("p", "q"), ("a", "b"),
            [Candidate("p", ("a",), 0.), Candidate("p", ("b",), 1.),
             Candidate("q", ("a",), 2.), Candidate("q", ("b",), 0.)],
            {"a": 100., "b": 100.}, {"p": 100., "q": 100.})
        self.assertEqual(result.margins["p"].value, 3.)
        self.assertEqual(result.margins["q"].value, 3.)

    def test_margin_not_just_second_global_solution(self):
        result = self.assert_matches_enumeration(
            ("p", "q"), ("a", "b"),
            [Candidate("p", ("a",), 0.), Candidate("q", ("b",), 0.)],
            {"a": 10., "b": 1.}, {"p": 10., "q": 1.})
        self.assertEqual(result.alternatives[0].assignments["p"], ("a",))
        self.assertEqual(result.margins["p"].value, 20.)
        self.assertEqual(result.margins["q"].value, 2.)

    def test_ties_and_candidate_order(self):
        candidates = [Candidate(j, (i,), 0.) for j in ("p", "q") for i in ("a", "b")]
        result = self.assert_matches_enumeration(("p", "q"), ("a", "b"), candidates,
                                               {"a": 1., "b": 1.}, {"p": 1., "q": 1.})
        self.assertEqual(result.margins["p"].value, 0.)
        reversed_result = solve_assignment(("q", "p"), ("b", "a"), candidates[::-1],
                                           {"a": 1., "b": 1.}, {"p": 1., "q": 1.})
        self.assertEqual(result.best.assignments, reversed_result.best.assignments)

    def test_empty_observations_and_environments(self):
        for obs, env in [((), ()), (("p",), ()), ((), ("a",)), (("p",), ("a",))]:
            with self.subTest(obs=obs, env=env):
                self.assert_matches_enumeration(obs, env, [], dict.fromkeys(env, 2.), dict.fromkeys(obs, 3.))

    def test_random_small_problems_against_exhaustive_oracle(self):
        rng = random.Random(319)
        for case in range(45):
            obs = tuple(f"p{x}" for x in range(rng.randrange(4)))
            env = tuple(f"e{x}" for x in range(rng.randrange(4)))
            subsets = [(x,) for x in env] + list(itertools.combinations(env, 2))
            candidates = [Candidate(j, group, rng.randrange(-4, 17) / 2)
                          for j in obs for group in subsets if rng.random() < .7]
            missing = {i: rng.randrange(-2, 9) / 2 for i in env}
            unexplained = {j: rng.randrange(-2, 9) / 2 for j in obs}
            with self.subTest(case=case):
                self.assert_matches_enumeration(obs, env, candidates, missing, unexplained)

    def test_nonfinite_costs_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), True, "1"):
            for position in range(3):
                with self.subTest(value=value, position=position), self.assertRaises(ValueError):
                    solve_assignment(("p",), ("a",), [Candidate("p", ("a",), value if position == 0 else 0.)],
                                     {"a": value if position == 1 else 1.}, {"p": value if position == 2 else 1.})

    def test_invalid_identity_and_candidate_inputs(self):
        invalid = [Candidate("unknown", ("a",), 0.), Candidate("p", ("unknown",), 0.),
                   Candidate("p", (), 0.), Candidate("p", ("a", "a"), 0.),
                   Candidate("p", ("a", "b", "c"), 0.)]
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                solve_assignment(("p",), ("a",), [candidate], {"a": 1.}, {"p": 1.})
        for candidates in ([Candidate("p", ("a",), 0.)] * 2,
                           [Candidate("p", ("a", "b"), 0.), Candidate("p", ("b", "a"), 1.)]):
            with self.assertRaises(ValueError):
                solve_assignment(("p",), ("a", "b"), candidates, {"a": 1., "b": 1.}, {"p": 1.})
        for obs, env, missing, unexplained in [(("p", "p"), (), {}, {"p": 1.}),
                                             (("p",), ("a",), {}, {"p": 1.}),
                                             ((), (), {"extra": 1.}, {})]:
            with self.assertRaises(ValueError):
                solve_assignment(obs, env, [], missing, unexplained)
        for obs in ("p", None, (1,)):
            with self.assertRaises(ValueError):
                solve_assignment(obs, (), [], {}, {})

    def test_missing_or_nonoptimal_backend_solution_has_no_confidence(self):
        for status in (1, 2, 3, 4):
            backend = SimpleNamespace(status=status, message="backend stopped", x=None)
            with self.subTest(status=status), patch("nmr_assignment.solver.milp", return_value=backend):
                result = solve_assignment(("p",), (), [], {}, {"p": 1.})
            self.assertIsNone(result.best)
            self.assertFalse(result.optimal)
            self.assertFalse(result.top_k_certified)
            self.assertFalse(result.margins["p"].certified)
            self.assertIsNone(result.margins["p"].value)

    def test_nonoptimal_incumbent_never_certified(self):
        result = SimpleNamespace(status=1, message="Time limit reached", x=[1., 0., 0.],
                                 mip_gap=.5, mip_dual_bound=-1.)
        with patch("nmr_assignment.solver.milp", return_value=result):
            solved = solve_assignment(("p",), ("a",), [Candidate("p", ("a",), 0.)], {"a": 1.}, {"p": 1.})
        self.assertIsNotNone(solved.best)
        self.assertFalse(solved.best.certified)
        self.assertFalse(solved.optimal)
        self.assertFalse(solved.top_k_certified)
        self.assertTrue(solved.timed_out)
        self.assertIsNone(solved.margins["p"].value)
        self.assertEqual(solved.margins["p"].status, "best_not_optimal")

    def test_total_budget_expiration_before_backend(self):
        with patch("nmr_assignment.solver.monotonic", side_effect=[0., 2.]), \
                patch("nmr_assignment.solver.milp") as backend:
            result = solve_assignment(("p",), (), [], {}, {"p": 1.}, time_limit=1.)
        backend.assert_not_called()
        self.assertIsNone(result.best)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.top_k_certified)

    def test_later_timeout_does_not_invalidate_proven_best(self):
        first = SimpleNamespace(status=0, message="Optimal", x=[1., 0., 0.], mip_gap=0., mip_dual_bound=0.)
        limited = SimpleNamespace(status=1, message="Time limit reached", x=None)
        with patch("nmr_assignment.solver.milp", side_effect=[first, limited, limited]):
            result = solve_assignment(("p",), ("a",), [Candidate("p", ("a",), 0.)], {"a": 1.}, {"p": 1.})
        self.assertTrue(result.optimal)
        self.assertTrue(result.best.certified)
        self.assertFalse(result.top_k_certified)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.margins["p"].certified)
        self.assertIsNone(result.margins["p"].value)

    def test_fractional_and_infeasible_incumbents_rejected(self):
        for vector in ([.5, .5, .5], [1., 1., 0.], [float("nan"), 0., 0.]):
            with self.subTest(vector=vector), patch("nmr_assignment.solver.milp", return_value=
                    SimpleNamespace(status=0, message="Optimal", x=vector)):
                result = solve_assignment(("p",), ("a",), [Candidate("p", ("a",), 0.)], {"a": 1.}, {"p": 1.})
            self.assertIsNone(result.best)
            self.assertEqual(result.status, "error")
            self.assertFalse(result.optimal)

    def test_requested_top_one_and_optional_margins(self):
        result = solve_assignment(("p",), ("a",), [Candidate("p", ("a",), 0.)],
                                  {"a": 1.}, {"p": 1.}, top_k=1, compute_margins=False)
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.alternatives, ())
        self.assertTrue(result.top_k_certified)
        self.assertEqual(result.margins["p"].status, "not_requested")


if __name__ == "__main__":
    unittest.main()
