# Slot-Extractor Evaluator v0 设计说明

## 1. 评估目标

本 evaluator 用于对冻结评估集 `test_v0_200_candidate.jsonl` 跑规则判分。

它不使用 LLM judge。原因是本任务的模型输出是结构化 JSON，所有质量点都可以通过 `expected`、`assertions`、`gold_facts` 和 `tags` 做确定性判分。

## 2. 输入文件

### 2.1 评估集

路径：

```text
output/test_v0_200_candidate.jsonl
```

每条 case 包含：

- `id`：样本编号
- `task_type`：六类任务之一
- `layer`：ask / tool_call / final / unrelated / confirmation
- `input`：模型线上会看到的输入
- `expected`：标准答案，模型不可见
- `assertions`：逐条规则断言
- `gold_facts`：幻觉检测和边界检测参考
- `tags`：难例标签，用于切片分析

### 2.2 模型预测文件

预测文件也用 JSONL，每条必须带 `id`，并可采用以下任一格式：

```json
{"id":"ask-0001","output":{"action":"ask","missing_info":["project","start_time","duration"],"question":"...","info_complete":false}}
```

```json
{"id":"ask-0001","raw_output":"{\"action\":\"ask\",\"missing_info\":[\"project\",\"start_time\",\"duration\"],\"question\":\"...\",\"info_complete\":false}"}
```

也支持字段名：

- `output`
- `prediction`
- `pred`
- `raw_output`
- `model_output`
- `completion`
- `response`

如果没有这些字段，脚本会把除 `id` 以外的整条记录当作预测 JSON。

## 3. 支持的 assertion DSL

当前 evaluator 支持 `test_v0_200_candidate.jsonl` 中已经出现的规则形式：

- `field == value`
- `field != value`
- `args.field == value`
- `set(field) == {a,b}`
- `set(keys(arguments)) == {a,b,c}`
- `not_exists(field)`
- `question contains text`
- `technician_name in tool_results.find_technicians.technicians[].technician_name`
- `technician_name in tool_results.find_technicians.technicians[gender==女].technician_name`
- `technician_name in tool_results.find_technicians.technicians[available==true].technician_name`
- `technician_name in gold_facts.technicians_in_db`
- `no_field_outside_schema`
- `no_technician_outside_gold_facts`

注意：evaluator 以 case 中显式写出的 `assertions` 为准，不会额外发明更严格的规则。

## 4. 多维度分数

脚本将每条 assertion 映射到以下维度：

| 维度 | 含义 |
|---|---|
| JSON 合法率 | 模型输出能否被 `json.loads` 解析 |
| 指令/Schema 合规 | action schema、额外字段、工具参数边界 |
| 工具调用准确性 | `tool_name` 和 `arguments` 是否正确 |
| 字段抽取准确性 | `project`、`technician_name`、`start_time`、`duration`、`gender` 等 |
| 意图/动作准确性 | `ask/tool_call/final/unrelated/confirmation` 以及确认/取消/改口 |
| 克制与约束遵守 | `missing_info`、不该出现的字段、是否过早 final/tool_call |
| 幻觉率 | 显式的 `gold_facts` / `tool_results` 越界断言失败率 |

最终还会按：

- `task_type`
- `tags`
- 失败 assertion
- 失败 case

做切片汇总。

## 5. 运行方式

自检 evaluator 规则是否与评估集对齐：

```powershell
python scripts\evaluate_slot_extractor.py `
  --eval output\test_v0_200_candidate.jsonl `
  --use-expected `
  --out-dir output\eval_runs\selfcheck_expected_v0_200
```

当前自检结果：

```text
cases: 200
json_valid_rate: 100.0%
case_pass_rate: 100.0%
assertion_pass_rate: 100.0%
hallucination_rate: 0.0%
```

评估真实模型输出：

```powershell
python scripts\evaluate_slot_extractor.py `
  --eval output\test_v0_200_candidate.jsonl `
  --pred output\predictions\model_x.jsonl `
  --out-dir output\eval_runs\model_x_v0_200
```

输出目录包含：

- `report.md`：人读的多维度分数卡
- `summary.json`：机器可读汇总
- `per_case_results.jsonl`：逐 case、逐 assertion 判分明细

## 6. 设计口径

本 evaluator 的核心原则是：

> 不给一个笼统总分，而是把每条失败断言归因到具体能力维度。

这样后续看到模型失败时，可以直接判断应该：

- 补 SFT 数据
- 补 DPO rejected
- 调整六类配比
- 改输出 schema
- 收紧工具边界
- 还是修改线上 guardrail

