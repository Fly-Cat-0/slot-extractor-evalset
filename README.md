# Slot-Extractor Eval Bundle

这是一个适合直接上传到 GitHub 的精简评测包，包含：

- 冻结评测集
- 任务说明文档
- 规则判分脚本
- 多轮鲁棒性评测脚本
- 一个最小 `toy_predictions` 示例

不包含：

- 本地实验结果
- 大体积模型预测文件
- 临时缓存与运行输出

## 目录

```text
slot_extractor_eval_github_bundle/
  data/
    test_v0_200_candidate.jsonl
  docs/
    task_spec_v0.md
    evaluator_design_v0.md
  predictions/
    toy_predictions.jsonl
  scripts/
    evaluate_slot_extractor.py
    evaluate_multiturn_robustness.py
    convert_slot_llamafactory_predictions.py
```

## 快速开始

```bash
cd slot_extractor_eval_github_bundle
python scripts/evaluate_slot_extractor.py \
  --eval data/test_v0_200_candidate.jsonl \
  --use-expected \
  --out-dir eval_runs/selfcheck_expected_v0_200
```

期望输出：

```text
cases: 200
json_valid_rate: 100.0%
case_pass_rate: 100.0%
assertion_pass_rate: 100.0%
hallucination_rate: 0.0%
```

## 评估真实预测

预测文件格式支持：

```json
{"id":"ask-0001","output":{"action":"ask","missing_info":["project","start_time","duration"],"question":"...","info_complete":false}}
```

或：

```json
{"id":"ask-0001","raw_output":"{\"action\":\"ask\",\"missing_info\":[\"project\",\"start_time\",\"duration\"],\"question\":\"...\",\"info_complete\":false}"}
```

运行：

```bash
python scripts/evaluate_slot_extractor.py \
  --eval data/test_v0_200_candidate.jsonl \
  --pred predictions/model_x.jsonl \
  --out-dir eval_runs/model_x
```

输出：

- `eval_runs/model_x/report.md`
- `eval_runs/model_x/summary.json`
- `eval_runs/model_x/per_case_results.jsonl`

## 多轮鲁棒性

`evaluate_multiturn_robustness.py` 只统计 `tags` 含“多轮”的样本，并要求同一条样本在 3 次重复运行里全部通过才算通过：

```bash
python scripts/evaluate_multiturn_robustness.py \
  --eval data/test_v0_200_candidate.jsonl \
  --pred run1.jsonl run2.jsonl run3.jsonl \
  --out-dir eval_runs/multi_turn_robustness_3x
```
