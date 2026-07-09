# Slot-Extractor Eval Release

GitHub 上传时优先看这三个文件：

- `eval.jsonl`
- `prompt.md`
- `overview.md`
- `report.md`

## Main Files

- `eval.jsonl`
  - 当前主评估集
  - 总样本数：`214`
- `prompt.md`
  - 当前使用的 `prompt_v3`
- `overview.md`
  - 数据集构造思路和大致分布说明
- `report.md`
  - 对应 `214` 主评估集的远端 API 测试报告
  - 模型：`qwen3.7-plus`

## Extra Files

- `probe_state_only_confirmation.jsonl`
  - 单独拆出的 confirmation 探针
- `probe_async_pending.jsonl`
  - 单独拆出的 async/pending 探针
- `construction.md`
  - 更细一点的拆分和构造说明

## Validation

- main eval self-check: `214/214`
- packaged report is the remote API report for the `214` main evalset

## Known Caveat

- `history` is treated as upstream context, not as text that must be directly generatable by the current `prompt.md`.
- In other words, this eval package assumes a larger agent system around the Slot-Extractor module.
- Some `history` lines are better understood as coming from an upstream confirmation/message layer or business-result layer.
- So this package is suitable for evaluating `history -> JSON action/slot decision`, but not for validating whether the current prompt alone can reproduce every `history` utterance.
