# 条件性第二段源码（仅迁移准备）

四个 `TEST_STAGE_B_completion*.py` 来自原 Transport C1/C2/C3 已审稳定源码。此公开迁移不是实际终态、后缀可执行性或完成验收。只有原失败真实终态、无存活进程、完整输入与产物 inventory、固定 prefix/boundary/未开始 suffix、独立 review 与新精确 owner release 全部满足，才允许第二段；原失败、边界 unknown、已完成记录永久保留，不得第三段。

公开版本复用 `portable_runtime.py` 的显式 runtime SHA/defaultdeny，所有 helper 核四源SHA闭包；监督器向 child 传同一 runtime。`templates/conditional_completion_runtime_bindings.example.json` 默认无授权。它列出实际原 metadata pins 和 public source SHA 分别绑定。实际 D/JJ 的 suite/plan/owner/phase SHA 不等于重新定位后的制品 SHA；重新定位的外部控制必须独立冻结并明确审计新 exact bindings，不能拿原 actual review 冒充新 public 源审核。原 authority pin、字段谓词、完整映射/分母/once/终态/阈值 OFF 均保留。

原 caller5485、supervisor2e6b、reportcdf 的 public 副本 SHA 不同。仅这些源码绑定与四个路径敏感 metadata SHA 改为显式外部绑定，模板保留原 actual pin 来源；没有自动重写原证据。started hook 只适配既有 public caller 单行赋值格式，AST 回归验证原 run body 只加同位置 hook，deadline 顺序不变。CPU1/thread1/worker1/GPU0/RSS8GiB、15*N+600/cleanup60、每记录10s/cap50000不变。

`conditional_completion_synthetic_checks.py` 从临时CWD以隔离Python、无PYTHONPATH运行30个原合成测试，包括原终态/claim/input闭包、malformed tmp touched、保存OFF阈值、不重算reference/margin，及受控signal.pause进程的wall终止回收。该fixture的业务wall .2秒、cleanup2秒保持原测试，外层子进程30秒有界，失败杀子并等待，无sleep/retry。另核三接口、默认拒绝、helper拒绝与四源闭包缺项拒绝。不读真实test/模型/评分；不是actual验收。

finite公开入口仍只支持原一次完整成功分支。本次不迁移任何尚未独审的 segmented finite 验收协议，也不生成completion。原实际与public来源SHA见 `conditional_completion_source_delta.json`。
