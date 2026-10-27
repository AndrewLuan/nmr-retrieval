# 功能：导出峰归属的数据契约；不加载数据、权重或求解器。
# 职责：InferenceInput 接收严格推理输入，AssignmentOutput 表达集合归属及证据。
# 关系与输入输出：实现位于 contracts.py，由同步合成测试验证；导入无外部副作用。
from .contracts import AssignmentOutput, InferenceInput

__all__ = ["AssignmentOutput", "InferenceInput"]
