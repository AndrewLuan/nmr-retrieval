# 功能概述：已审Stage B公开迁移副本；原实际运行与public源码SHA分开，不携带真实输入。
# 接口：所有外部路径/身份/SHA显式绑定，runtime授权与原suite/phase/once/review四门共同约束。
# 关系：复用公共同目录与既有nmr_assignment；保持原预算、输出协议、固定分母和校准off规则。
from portable_stage_runtime import authorize, with_runtime
from portable_runtime import binding, workspace, artifact_path, repository
"""功能概述：Stage B caller规则SHA接线的独立纯metadata回归。
读取原Cval rule/calibration控制制品，不读取test/原始峰或运行check_plan/模型/求解/评分。
验证35ea规则文件与012f数字配置分层绑定，原543a calibration bytes与off状态不变。
合成变异只在内存/临时文件；既有组件与execution受审源不修改、不重跑。
"""
import copy, json, tempfile, unittest
from pathlib import Path
import TEST_STAGE_B_control as ctl
import TEST_STAGE_B_C_caller as caller
D = workspace()

def item(p):
    return dict(path=str(p), sha256=ctl.sha(p))

class CalRuleIO(unittest.TestCase):

    def setUp(self):
        self.rule = artifact_path('C_val_scoring_rule_contract.json')
        self.cal = artifact_path('C_val_assignment_results/calibration_artifacts.json')
        self.numeric = artifact_path('numerical_implementation_config.json')
        self.artifacts = [dict(axis=copy.deepcopy(x['axis'])) for x in json.loads(self.cal.read_text())]
        self.plan = dict(Cval_scoring_rule_contract=item(self.rule), inputs=dict(numeric_config=item(self.numeric)))
        self.A = dict(extraction=dict(numeric_config=item(self.numeric)))
        self.before = (ctl.sha(self.rule), ctl.sha(self.cal), ctl.sha(self.numeric))
        self.addCleanup(lambda: self.assertEqual(self.before, (ctl.sha(self.rule), ctl.sha(self.cal), ctl.sha(self.numeric))))

    def test_actual_Cval_control_metadata_accepts_distinct_hashes(self):
        self.assertNotEqual(self.plan['Cval_scoring_rule_contract']['sha256'], self.plan['inputs']['numeric_config']['sha256'])
        self.assertEqual(caller.bind_Cval_rule_contract(self.plan, self.artifacts, self.A), caller.CVAL_RULE_CONTRACT_SHA)

    def test_original_bad_numeric_as_axis_rejected(self):
        for a in self.artifacts:
            a['axis']['rule_sha256'] = self.plan['inputs']['numeric_config']['sha256']
        with self.assertRaisesRegex(ValueError, 'same_calibration_rule_contract_snapshot'):
            caller.bind_Cval_rule_contract(self.plan, self.artifacts, self.A)

    def test_zero_rule_sha_rejected(self):
        self.plan['Cval_scoring_rule_contract']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'original_Cval_rule_contract_SHA_required'):
            caller.bind_Cval_rule_contract(self.plan, self.artifacts, self.A)

    def test_missing_rule_item_rejected(self):
        self.plan.pop('Cval_scoring_rule_contract')
        with self.assertRaisesRegex(ValueError, 'original_Cval_rule_contract_SHA_required'):
            caller.bind_Cval_rule_contract(self.plan, self.artifacts, self.A)

    def test_current_numeric_mismatch_rejected(self):
        self.plan['inputs']['numeric_config']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Cval_rule_numeric_current_A_binding'):
            caller.bind_Cval_rule_contract(self.plan, self.artifacts, self.A)

    def test_A_numeric_mismatch_rejected(self):
        self.A['extraction']['numeric_config']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Cval_rule_numeric_current_A_binding'):
            caller.bind_Cval_rule_contract(self.plan, self.artifacts, self.A)

    def test_rule_bytes_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'rule.json'
            p.write_bytes(self.rule.read_bytes() + b'\n')
            self.plan['Cval_scoring_rule_contract']['path'] = str(p)
            with self.assertRaisesRegex(ValueError, 'artifact_SHA'):
                caller.bind_Cval_rule_contract(self.plan, self.artifacts, self.A)

    def test_original_rule_relocates_without_rewriting_provenance_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'rule.json'
            p.write_bytes(self.rule.read_bytes())
            self.plan['Cval_scoring_rule_contract']['path'] = str(p)
            self.assertEqual(caller.bind_Cval_rule_contract(self.plan, self.artifacts, self.A), caller.CVAL_RULE_CONTRACT_SHA)
if __name__ == '__main__':
    unittest.main(verbosity=2)
