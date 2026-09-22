# CI、benchmark 与自动 workflow 架构

目标是让每次改动都有可追溯的质量证据，让发布消费这些证据。沿用现有
PR 快速检查、合并后 Python 全版本矩阵，以及 Claude Code 原生 plugin eval。

![CI、基准和发布的证据路径](../../../.github/assets/diagrams/08-ci-benchmark.architecture.svg)

架构图由 Archify 2.16.0 生成；[源文件与复现](../../reference/diagram-gallery.md#ci-benchmarks-and-release-evidence)。

## 四层验证

| 层 | 触发 | 回答的问题 | 判定 |
|---|---|---|---|
| PR 必需检查 | 每个 PR，按改动选择重型任务 | 功能、分发、接线和证据判定是否正确？ | 确定性缺陷阻止合并 |
| 合并后兼容性 | main 每次提交 | Python 3.9–3.14 是否保持兼容？ | 全矩阵必须成功后才可发布 |
| 离线基准 | PR 确定性质量检查；独立定时及手动比较 | memory 是否召回该召回的知识、排除不适用知识，代价多少？ | 质量硬约束；耗时仅报告 |
| 模型行为评测 | 有明确参数和额度的手动运行 | 同一任务加装 plugin 后是否改善？ | WITH/WITHOUT、样本完整性、安全性分别判定 |

已有 Git co-change 检索 benchmark 和 self-assess 周报保留。它们各自回答组件
检索效果和仓库健康问题，不能替代 memory 正确性或模型行为收益。

## 基准协议

memory 基准使用独立、可读、固定的任务与期望记录集合。真实临时 Git 仓库
提供 accepted records、分支未接受内容、过期来源和撤回记录。记录每个案例的
期望与实际 ID、召回率、误召回、UTF-8 字节预算和运行时间。无匹配案例独立
检查，不让空集合把总体 recall 分母冲高。错误或缺失证据保留为 unjudged。

比较 base 与 head 时，两者使用同一份当前 benchmark harness 和 fixture，
以独立进程导入各自实现。结果绑定实现 SHA、fixture/harness 摘要、Python、OS、
Git 与样本数量。保存原始耗时及中位数，不对共享 runner 的抖动设伪精确门槛。
比较器拒绝协议、fixture、案例、环境或样本不一致的结果。

这些合成任务是工程回归基准；它们不证明真实用户生产力提升，也不测量
dream 的语义综合能力。模型是否更有效，需要单独的行为评测。

## 模型评测

沿用锁定的 Claude Code 及 native `plugin eval --ablation with-without`。
汇总器检查完整双臂、预期案例与运行次数、有限且有效的分数、运行状态及
实际 grader 结果。不能把缺失的 delta、成本或样本默认为零。安全性 grader
是独立硬约束，不允许在平均分里被其他成功项抵消。

运行前验证 model、runs、concurrency、threshold 和 max-cost 参数，在任何
provider 请求之前拒绝越界输入。原生 cost ceiling 是客户端的估算/停止机制，
不能保证第三方供应商实际账单。保留并发 1、固定超时和手动触发；本轮不启动
付费评测，不为没有观测过的质量声称改进百分比。

## 发布与自动维护

release 的只读 verification job 按 repository、main、push 事件、workflow 和
exact SHA 查询 CI 与 postmerge 结果。仅全部成功后才让有写权限的 tag job
运行；缺失、取消、失败或超时均不能发布。手动入口也遵守同样规则。
不引入从不可信 PR 下载执行产物的特权 `workflow_run`。

保留 Dependabot 对 action、开发工具、Claude host 的审阅式更新。补齐可选
runtime 依赖的维护，所有自动化仍通过正常 PR 和必需检查，不自动批准或合并。

## 取舍

没有把所有测试、网络 corpus、模型调用塞进每个 PR：现有分层已有价值。
也不做依赖历史 artifact 的全局性能硬阈值：runner 环境与样本不匹配时，
一个看似精确的百分比会误导。优先让原始数据、基线身份和判定规则可复现。
