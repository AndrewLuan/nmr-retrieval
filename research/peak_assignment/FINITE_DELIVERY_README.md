# 有限源相对交付核验入口

`verify_source_relative_finite_delivery.py` 是独立公开入口。原 `verify_source_relative_delivery.py`、强目标 verifier 与 `portable_runtime.py` 保持原字节。

支持已审原一次 score/package/report 成功分支，以及原失败终态加唯一完成后缀的已审分段元数据分支。后者严格核全部终态/输入封存/保守分区/逐阶段claim与plan-release-input-map、保存边界分母、read/execution journal、封存输出和实际应用独审；N0没有当前native报告路径时明确拒绝。预测原失败 EXIT1 保留，实际 builder receipt SHA、scope7889、固定身份及逐阶段 once/inventory/review 仍严格核验。H 固定 test unavailable、可信实验 gold 未建立及其它未完成目标不升格。此源码准备不表示实际交付完成；该源码不代表真实分段终态或实际报告已经存在，也不授权重启或第三段。

使用 `templates/finite_delivery_runtime.example.json`，外部 owner 审核后提供显式授权和制品 workspace。执行传 `--runtime-manifest PATH --runtime-manifest-sha256 SHA`。源码与 schema SHA 必须精确匹配模板绑定；每个公开 helper 均先核授权和源码绑定。缺交付件返回 PENDING/EXIT2。不得把私有数据、身份、模型或实际输出复制到公开树。

`finite_delivery_synthetic_checks.py` 在隔离 Python、临时工作目录、无 PYTHONPATH 下运行48个合成元数据测试及默认拒绝/helper授权/源码漂移检查。原 test 字段形状保留，合成测试仅临时替换 identity/receipt/source pin 来检验契约，不是 actual 验收，不产生完成证书。不启动模型或科学评分。

实际 D 源 SHA 与 portable SHA 分别见 `finite_delivery_source_delta.json`；公开副本不能冒称原运行字节。原科学字段判断保留，新增仅外部 workspace、显式 runtime 绑定及每 helper 授权。

## 最终分段元数据增量

源自最终 actual verifier55694119、schema80ddb82f、tests89eb62f9及原Numerical ea6d审查。实际原suite/owner/plan/phase、native conditional4四源、frozen report/estimator SHA全部仍为原actual-artifact proof；外部workspace必须提供原证据字节。不得自动改为portable源码SHA，也不声称新public源码是实际原运行源码。public runtime只绑定本公开entry/schema，源码映射另列。report plan的suffix inventory/path/output root与原input seal，以及实际report receipt精确输入map均核验，不从review flags推实际完成。

48个合成测试继承23个once和25个segmented反例；临时identityfree文件/替换pin只是测试，不是actual验收。其原作者全套约32秒，公开双源逐helper哈希增加I/O；公开隔离检查已测81.615秒，含主入口总计85.234秒；跨平台文件系统与CPU调度会影响逐helper哈希耗时，因此同fixture隔离子进程统一设300秒有界等待上限（约实测总耗时的3.5倍），只包围测试进程启动、完整检查和退出，超时杀并等待，无sleep/retry。科学预算不变。ROOT显式解析外部workspace，helper每次核runtime授权及entry/schema SHA。
