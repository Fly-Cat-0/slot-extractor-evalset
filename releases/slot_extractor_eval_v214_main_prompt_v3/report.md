# Slot-Extractor Evaluator Report

- evalset: `/data/ZJ/slot_extractor_eval_package/data/test_v0_214_main_prompt_v3.jsonl`
- predictions: `/data/ZJ/slot_extractor_eval_package/predictions/qwen3_7_plus_main_v214_release.jsonl`
- n: `214`

## Primary Readout

- Strict：保守模板口径，`question contains` 更贴近字面要求，用来看 prompt 是否按模板输出。
- Wording-insensitive：使用 Semantic Slot 口径，只把追问是否覆盖缺失槽位作为通过条件。
- Gap：`Wording-insensitive - Strict`，主要反映问句措辞造成的保守扣分。

| 口径 | 整例通过 | 规则断言通过 |
|---|---:|---:|
| Strict | 188/214 (87.9%) | 2088/2186 (95.5%) |
| Wording-insensitive (Semantic Slot) | 192/214 (89.7%) | 2092/2186 (95.7%) |
| Gap | +4 cases (+1.9 pp) | +4 assertions (+0.2 pp) |

## Scorecard (Strict)

Strict 是保守口径，适合检查模型是否贴着 eval 模板输出。

| 维度 | 分数 | 说明 |
|---|---:|---|
| JSON 合法率 | 100.0% | json.loads 成功 |
| 整例通过率 | 87.9% | 该 case 所有规则均通过 |
| 规则断言通过率 | 95.5% | 所有 assertions 的平均通过率 |
| 指令 / 规则遵循 | 100.0% | JSON合法 + schema合规 + 越界字段=0 |
| 工具调用准确性 | 95.6% | action + tool_name + 参数 全中才算对 |
| 字段抽取准确性 | 96.6% | duration 97.4% \| gender 97.4% \| project 96.6% \| start_time 94.9% \| technician_name 96.6% |
| 意图判定准确性 | 94.9% | 主 action 分类准确率 |
| 克制与约束遵守 | 94.9% | 不该调时克制 + 不硬猜 + 边界约束 |
| 幻觉率 | 1.4% | 越低越好：gold_facts / tool_results 越界 |

## Three-Track Comparison

| 维度 | Strict | Soft Synonym | Semantic Slot | Semantic - Strict |
|---|---:|---:|---:|---:|
| JSON 合法率 | 100.0% | 100.0% | 100.0% | +0.0 pp |
| 整例通过率 | 87.9% | 89.7% | 89.7% | +1.9 pp |
| 规则断言通过率 | 95.5% | 95.7% | 95.7% | +0.2 pp |
| 指令 / 规则遵循 | 100.0% | 100.0% | 100.0% | +0.0 pp |
| 工具调用准确性 | 95.6% | 95.6% | 95.6% | +0.0 pp |
| 字段抽取准确性 | 96.6% | 96.6% | 96.6% | +0.0 pp |
| 意图判定准确性 | 94.9% | 94.9% | 94.9% | +0.0 pp |
| 克制与约束遵守 | 94.9% | 94.9% | 94.9% | +0.0 pp |
| 幻觉率 | 1.4% | 1.4% | 1.4% | +0.0 pp |

## Track 1 / Strict

原始严格轨：question contains 采用字面包含。

| 维度 | 分数 | 说明 |
|---|---:|---|
| JSON 合法率 | 100.0% | json.loads 成功 |
| 整例通过率 | 87.9% | 该 case 所有规则均通过 |
| 规则断言通过率 | 95.5% | 所有 assertions 的平均通过率 |
| 指令 / 规则遵循 | 100.0% | JSON合法 + schema合规 + 越界字段=0 |
| 工具调用准确性 | 95.6% | action + tool_name + 参数 全中才算对 |
| 字段抽取准确性 | 96.6% | duration 97.4% \| gender 97.4% \| project 96.6% \| start_time 94.9% \| technician_name 96.6% |
| 意图判定准确性 | 94.9% | 主 action 分类准确率 |
| 克制与约束遵守 | 94.9% | 不该调时克制 + 不硬猜 + 边界约束 |
| 幻觉率 | 1.4% | 越低越好：gold_facts / tool_results 越界 |

## Track 2 / Soft Synonym

同义表达轨：question contains 允许预设近义表达命中。

| 维度 | 分数 | 说明 |
|---|---:|---|
| JSON 合法率 | 100.0% | json.loads 成功 |
| 整例通过率 | 89.7% | 该 case 所有规则均通过 |
| 规则断言通过率 | 95.7% | 所有 assertions 的平均通过率 |
| 指令 / 规则遵循 | 100.0% | JSON合法 + schema合规 + 越界字段=0 |
| 工具调用准确性 | 95.6% | action + tool_name + 参数 全中才算对 |
| 字段抽取准确性 | 96.6% | duration 97.4% \| gender 97.4% \| project 96.6% \| start_time 94.9% \| technician_name 96.6% |
| 意图判定准确性 | 94.9% | 主 action 分类准确率 |
| 克制与约束遵守 | 94.9% | 不该调时克制 + 不硬猜 + 边界约束 |
| 幻觉率 | 1.4% | 越低越好：gold_facts / tool_results 越界 |

## Track 3 / Semantic Slot

槽位覆盖轨：question contains 按缺失槽位语义覆盖判定。

| 维度 | 分数 | 说明 |
|---|---:|---|
| JSON 合法率 | 100.0% | json.loads 成功 |
| 整例通过率 | 89.7% | 该 case 所有规则均通过 |
| 规则断言通过率 | 95.7% | 所有 assertions 的平均通过率 |
| 指令 / 规则遵循 | 100.0% | JSON合法 + schema合规 + 越界字段=0 |
| 工具调用准确性 | 95.6% | action + tool_name + 参数 全中才算对 |
| 字段抽取准确性 | 96.6% | duration 97.4% \| gender 97.4% \| project 96.6% \| start_time 94.9% \| technician_name 96.6% |
| 意图判定准确性 | 94.9% | 主 action 分类准确率 |
| 克制与约束遵守 | 94.9% | 不该调时克制 + 不硬猜 + 边界约束 |
| 幻觉率 | 1.4% | 越低越好：gold_facts / tool_results 越界 |

## Hallucination Breakdown

| 类型 | 幻觉率 | 通过/总数 | 说明 |
|---|---:|---:|---|
| entity_hallucination | 0.0% | 42/42 | 技师 / 候选 / tool_results / gold_facts 越界 |
| external_fact_hallucination | 3.2% | 30/31 | weather / temperature / suggestion 外部事实越界 |

## By Task Type

| task_type | cases | 整例通过率 | 断言通过率 |
|---|---:|---:|---:|
| ask_missing_info | 75 | 80.0% | 94.6% |
| confirmation | 12 | 33.3% | 60.2% |
| final_appointment | 42 | 100.0% | 100.0% |
| technician_tool_call | 38 | 94.7% | 97.8% |
| unrelated | 35 | 100.0% | 100.0% |
| weather_tip | 5 | 80.0% | 97.5% |
| weather_tool_call | 7 | 100.0% | 100.0% |

## Failed Assertions

| count | assertion |
|---:|---|
| 7 | `action == confirmation` |
| 7 | `confirmation == confirm` |
| 7 | `change_request == false` |
| 7 | `changed_fields == []` |
| 7 | `finalize == true` |
| 5 | `not_exists(tool_name)` |
| 5 | `not_exists(arguments)` |
| 4 | `question contains 做多久` |
| 3 | `action == ask` |
| 3 | `start_time == 2026-06-09 14:00` |
| 3 | `gender == 未知` |
| 3 | `set(missing_info) == {duration}` |
| 3 | `info_complete == false` |
| 3 | `set(missing_info) == {start_time,duration}` |
| 2 | `project == 肩颈按摩` |
| 2 | `duration == 未知` |
| 2 | `technician_name == 小王` |
| 2 | `args.preference == 肩颈按摩` |
| 2 | `unrelated == false` |
| 1 | `technician_name == 李明` |
| 1 | `project == 按摩` |
| 1 | `start_time == 2026-06-17 15:00` |
| 1 | `start_time == 2026-06-10 10:00` |
| 1 | `technician_name == 王芳` |
| 1 | `start_time == 2026-06-10 15:00` |
| 1 | `tip contains 北京` |
| 1 | `action == tool_call` |
| 1 | `tool_name == find_technicians` |
| 1 | `args.start_time == 2026-06-09 14:00` |
| 1 | `args.duration == 90分钟` |

## Failing Cases

| id | task_type | failed dimensions | failed assertions |
|---|---|---|---|
| confirmation-0002 | ask_missing_info | field_extraction, intent_action, restraint_constraint | `action == ask; project == 肩颈按摩; technician_name == 李明; start_time == 2026-06-09 14:00; duration == 未知; gender == 未知; ... +4` |
| ask-0003 | ask_missing_info | field_extraction, restraint_constraint | `project == 按摩; set(missing_info) == {start_time,duration}` |
| tool-call-0004 | ask_missing_info | field_extraction | `start_time == 2026-06-17 15:00` |
| confirmation-0003 | confirmation | intent_action | `action == confirmation; confirmation == confirm; change_request == false; changed_fields == []; finalize == true` |
| confirmation-0004 | ask_missing_info | restraint_constraint | `set(missing_info) == {start_time,duration}` |
| confirmation-0005 | ask_missing_info | field_extraction | `start_time == 2026-06-10 10:00` |
| ask-0010 | ask_missing_info | restraint_constraint | `set(missing_info) == {start_time,duration}` |
| confirmation-0008 | ask_missing_info | field_extraction, intent_action, restraint_constraint | `action == ask; project == 肩颈按摩; technician_name == 王芳; start_time == 2026-06-09 14:00; duration == 未知; gender == 未知; ... +4` |
| confirmation-0010 | confirmation | intent_action | `action == confirmation; confirmation == confirm; change_request == false; changed_fields == []; finalize == true` |
| confirmation-0012 | ask_missing_info | field_extraction, restraint_constraint | `start_time == 2026-06-10 15:00; set(missing_info) == {duration}` |
| weather-0007 | weather_tip | hallucination | `tip contains 北京` |
| ask-0037 | ask_missing_info | field_extraction | `technician_name == 小王` |
| tool-call-0034 | technician_tool_call | intent_action, restraint_constraint, tool_call | `action == tool_call; tool_name == find_technicians; args.start_time == 2026-06-09 14:00; args.duration == 90分钟; args.technician_name == 小王; args.preference == 肩颈按摩; ... +2` |
| tool-call-0038 | technician_tool_call | tool_call | `args.preference == 肩颈按摩` |
| confirmation-0014 | confirmation | intent_action | `action == confirmation; confirmation == confirm; change_request == false; changed_fields == []; finalize == true` |
| confirmation-0022 | confirmation | intent_action | `action == confirmation; confirmation == confirm; change_request == false; changed_fields == []; finalize == true` |
| confirmation-0023 | ask_missing_info | restraint_constraint | `set(missing_info) == {project,duration}` |
| confirmation-0027 | confirmation | intent_action, restraint_constraint | `action == confirmation; confirmation == confirm; change_request == false; changed_fields == []; finalize == true; unrelated == false; ... +2` |
| missing-p1-0005 | ask_missing_info | restraint_constraint | `question contains 做多久` |
| missing-p1-0008 | ask_missing_info | restraint_constraint | `question contains 做多久` |
| missing-p2-0003 | ask_missing_info | field_extraction, intent_action, restraint_constraint | `action == ask; project == 未知; technician_name == 小王; start_time == 2026-06-09 14:00; duration == 60分钟; gender == 未知; ... +5` |
| missing-p2-0004 | ask_missing_info | restraint_constraint | `question contains 做多久` |
| missing-p2-0008 | ask_missing_info | restraint_constraint | `question contains 做多久` |
| missing-p1-0003 | confirmation | intent_action | `confirmation == unknown; finalize == false` |
| missing-p1-0004 | confirmation | intent_action, restraint_constraint | `action == confirmation; confirmation == confirm; change_request == false; changed_fields == []; finalize == true; unrelated == false; ... +2` |
| missing-p1-0018 | confirmation | intent_action | `action == confirmation; confirmation == confirm; change_request == false; changed_fields == []; finalize == true` |
