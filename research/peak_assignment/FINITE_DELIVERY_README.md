# 有限源相对交付核验入口

`verify_source_relative_finite_delivery.py` 是独立公开入口。原 `verify_source_relative_delivery.py`、强目标 verifier 与 `portable_runtime.py` 保持原字节。

仅支持已审原一次 score/package/report 成功的有限分支。预测原失败 EXIT1 保留，实际 builder receipt SHA、scope7889、固定身份及逐阶段 once/inventory/review 仍严格核验。H 固定 test unavailable、可信实验 gold 未建立及其它未完成目标不升格。此源码准备不表示实际交付完成；不支持尚未批准的 conditional4 协议。

使用 `templates/finite_delivery_runtime.example.json`，外部 owner 审核后提供显式授权和制品 workspace。执行传 `--runtime-manifest PATH --runtime-manifest-sha256 SHA`。源码与 schema SHA 必须精确匹配模板绑定；每个公开 helper 均先核授权和源码绑定。缺交付件返回 PENDING/EXIT2。不得把私有数据、身份、模型或实际输出复制到公开树。

`finite_delivery_synthetic_checks.py` 在隔离 Python、临时工作目录、无 PYTHONPATH 下运行23个合成元数据测试及默认拒绝/helper授权/源码漂移检查。原 test 字段形状保留，合成测试仅临时替换 identity/receipt pin 来检验契约，不是 actual 验收，不产生完成证书。不启动模型或科学评分。

实际 D 源 SHA 与 portable SHA 分别见 `finite_delivery_source_delta.json`；公开副本不能冒称原运行字节。原科学字段判断保留，新增仅外部 workspace、显式 runtime 绑定及每 helper 授权。
