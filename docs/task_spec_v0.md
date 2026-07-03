# Slot-Extractor 任务边界与输出 Schema v0

## 1. 项目定位

本项目要微调的模型不是通用客服，也不是完整预约 Agent，而是 AppointmentAgent 中的一个受限模块：

> Slot-Extractor：预约场景下的结构化信息抽取与动作决策模型。

它的目标是把中文多轮预约对话转换成稳定、合法、可校验的 JSON，并决定下一步应该追问、调用工具、输出最终预约结果、识别无关请求，还是识别用户确认/否定/改口。

上线后链路应从：

```text
用户输入 -> 远端 LLM -> 解析 JSON -> 工具/业务流程
```

替换为：

```text
用户输入 -> 本地 Slot-Extractor -> JSON 校验 -> 工具/业务流程
```

## 2. 核心边界

### 2.1 模型负责什么

模型只负责能从 `history + user_input + current_time + available_tools + tool_results` 中推断出来的内容。

| 能力 | 说明 | 输出影响 |
|---|---|---|
| 字段抽取 | 从对话中抽取服务项目、技师名、时间、时长、性别偏好等 | 填充预约字段 |
| 相对时间标准化 | 结合 `current_time` 将“明天下午两点”“下周三”“周末下午”转为绝对时间 | 输出 `YYYY-MM-DD HH:mm` |
| 意图判断 | 判断用户是在预约、确认、否定、取消、改口，还是无关输入 | 决定 `action` |
| 缺口判断 | 判断必填信息是否缺失 | 输出 `missing_info` |
| 动作决策 | 判断下一步是 `ask`、`tool_call`、`final`、`unrelated`、`confirmation` | 输出动作 JSON |
| 工具参数组织 | 当需要查业务事实时，把已抽取字段组织成工具参数 | 输出 `tool_name` 与 `arguments` |
| 克制输出 | 对无法从输入或工具结果确认的信息输出 `未知`，不编造 | 降低幻觉 |

一句话：

> 模型负责理解语言、抽字段、转时间、判断动作、组织工具参数。

### 2.2 工具/数据库/业务系统负责什么

凡是依赖真实世界、数据库、排班、库存、权限或外部服务的事实，都不能让模型判断。

| 外部事实或动作 | 应由谁处理 | 为什么不能交给模型 |
|---|---|---|
| 技师是否真实存在 | 技师数据库 / `find_technicians` | 模型没有真实名单 |
| 技师是否有空 | 排班系统 / `find_technicians` | 需要实时档期 |
| 技师性别、资质、专长 | 技师数据库 | 需要业务源数据 |
| 服务项目是否存在 | 项目库 | 模型可能编造项目 |
| 项目价格、优惠、会员权益 | 业务系统 | 依赖实时配置 |
| 门店是否营业 | 门店营业时间系统 | 依赖业务规则和日期 |
| 天气 | 天气工具 / `get_current_weather` | 外部实时信息 |
| 订单是否创建成功 | 预约创建接口 | 需要真实写库 |
| 订单号、支付状态 | 订单系统 | 不能由模型生成 |
| 用户身份、权限、历史订单 | 用户系统 | 涉及真实用户数据 |
| 候选列表外的技师/项目 | 工具或业务系统确认 | 模型必须避免幻觉 |

一句话：

> 能从对话里抽出来的交给模型；需要查真实事实的交给工具或业务系统。

### 2.3 非目标

本模型不做以下事情：

- 不直接创建预约订单。
- 不判断技师真实可用性。
- 不判断真实天气。
- 不判断真实价格、优惠、会员权益。
- 不输出自然语言客服回复作为最终业务结果。
- 不编造候选技师、候选项目、排班、天气或订单号。
- 不替代业务系统的最终校验。

## 3. 输入 Schema

第一版模型输入固定为以下结构。训练、评估、线上推理必须尽量保持同构。

```json
{
  "history": "多轮历史对话，字符串，可为空",
  "user_input": "当前用户最新一句话",
  "current_time": "YYYY-MM-DD HH:mm",
  "available_tools": [
    {
      "name": "find_technicians",
      "description": "按技师姓名、服务项目、时间、时长查询技师是否存在与是否可预约。",
      "parameters": {
        "technician_name": "string | 未知",
        "project": "string | 未知",
        "start_time": "YYYY-MM-DD HH:mm | 未知",
        "duration": "string | 未知"
      }
    },
    {
      "name": "get_current_weather",
      "description": "查询指定地点和时间的天气。",
      "parameters": {
        "location": "string | 未知",
        "time": "YYYY-MM-DD HH:mm | 未知"
      }
    }
  ],
  "tool_results": {},
  "candidate_technicians": [],
  "candidate_projects": []
}
```

### 3.1 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `history` | 是 | 当前轮之前的多轮上下文；没有历史时为空字符串 |
| `user_input` | 是 | 当前用户最新输入 |
| `current_time` | 是 | 系统注入的当前时间，用于相对时间标准化 |
| `available_tools` | 是 | 当前可用工具及其参数定义 |
| `tool_results` | 否 | 上一轮或当前流程已有的工具返回结果 |
| `candidate_technicians` | 否 | 已知候选技师列表，用于防止编造 |
| `candidate_projects` | 否 | 已知候选项目列表，用于防止编造 |

## 4. 输出总规则

模型必须只输出 JSON，不输出 Markdown、不输出解释文本、不输出多段内容。

所有输出必须满足：

- JSON 可解析。
- 只使用 Schema 内字段。
- 不输出 Schema 外字段。
- 时间统一为 `YYYY-MM-DD HH:mm`。
- 不确定字段统一填 `未知`，不要用空字符串、`null`、`N/A` 混用。
- 外部事实没有工具结果支撑时，不得写死为真。
- 如果需要查事实，输出 `tool_call`，不要直接 `final`。
- 如果信息不全，输出 `ask`，不要猜。

## 5. Action Schema

第一版保留 5 种动作：

```json
{
  "action": "ask | tool_call | final | unrelated | confirmation"
}
```

注意：训练任务类型是 6 类，但动作类型是 5 种。类型 2 和类型 6 都属于 `tool_call`，只是调用的工具和业务含义不同。

### 5.1 Action 优先级

当一句用户输入同时带有多种信号时，第一版按以下优先级判定：

1. **纯确认/否定/取消/改口**优先输出 `confirmation`。例如“对，就这样”“不行”“算了”“换李明”“改到后天”，如果本轮只表达确认或修改意图，不直接补齐完整预约 JSON。
2. **改口后需要重新查外部事实**时输出 `tool_call`。例如历史里已有项目/时间/技师，用户说“改到晚上七点再查一下”或“项目改成精油按摩”，且需要重新确认技师/档期/项目支持性，应调用 `find_technicians`。
3. **工具结果已返回，且用户本轮补齐缺失槽位或从候选中选择具体技师**时，可以输出 `final`。例如工具返回多个可约技师后，用户说“第二个，做60分钟”；或助手问“时长多久？”，用户回答“90分钟”。
4. **缺必填信息**时输出 `ask`，不要猜。
5. **超出 Slot-Extractor 边界**时输出 `unrelated`，不要回答业务系统、隐私、价格、订单等外部问题。

一句话：纯确认/纯改口归 `confirmation`；改口后要查事实归 `tool_call`；工具结果已支撑且本轮补齐/选择后才归 `final`。

## 6. 六类任务定义

| 类型 | 名称 | 典型场景 | 目标输出 |
|---|---|---|---|
| 类型 1 | 信息不全 / 追问 | 用户想预约，但缺项目、时间、时长、技师等必要信息 | `action=ask` |
| 类型 2 | 技师/档期/业务事实工具调用 | 用户指定了技师或时间，需要查技师是否存在、是否可约 | `action=tool_call`，通常 `tool_name=find_technicians` |
| 类型 3 | 最终预约 JSON | 信息已完整，且必要工具结果已返回 | `action=final` |
| 类型 4 | 无关 / 拒答 / 路由 | 用户输入与预约无关，或超出本模块能力 | `action=unrelated` |
| 类型 5 | 确认 / 否定 / 取消 / 改口 | 用户说“对，就这样”“算了”“换一个”“不是小王” | `action=confirmation` |
| 类型 6 | 天气 / 特殊工具分支 | 预约后询问天气、出行提示等外部信息 | `action=tool_call`，通常 `tool_name=get_current_weather` |

类型 6 补充规则：

- 如果天气查询所需的地点或时间已能从上下文确定，应输出 `tool_call`，调用 `get_current_weather`。
- 如果天气查询缺少地点或时间，应输出 `ask` 追问缺失参数。
- 天气分支的 `missing_info` 可以包含工具参数级缺口，例如 `location`、`time`。
- 模型不能直接输出 `weather`、`temperature`、`suggestion` 等天气事实，除非这些来自已有 `tool_results`。

## 7. 各 Action 的输出格式

### 7.1 `ask`：信息不全

适用条件：

- 用户表达了预约意图。
- 但缺少必要字段。
- 目前无法进入工具调用或最终预约。

输出格式：

```json
{
  "action": "ask",
  "missing_info": ["project", "start_time", "duration"],
  "question": "请问您想预约什么项目、具体几点、做多久？",
  "info_complete": false
}
```

字段规则：

- `missing_info` 只能包含缺失字段名。
- `question` 应只追问缺失项。
- 不能把未确认字段猜出来。
- 如果用户已经明确提供了某些槽位，`ask` 可以携带这些已抽取字段，例如 `technician_name` 或 `gender`。
- `ask` 中携带的槽位只能来自用户输入或上下文，不能来自模型猜测，不能写入外部事实。

### 7.2 `tool_call`：工具调用

适用条件：

- 需要查询技师是否存在。
- 需要查询技师是否可约。
- 需要查询天气。
- 需要查询其他外部业务事实。

技师查询输出格式：

```json
{
  "action": "tool_call",
  "tool_name": "find_technicians",
  "arguments": {
    "technician_name": "小王",
    "project": "肩颈按摩",
    "start_time": "2026-06-09 14:00",
    "duration": "未知"
  }
}
```

天气查询输出格式：

```json
{
  "action": "tool_call",
  "tool_name": "get_current_weather",
  "arguments": {
    "location": "门店所在地",
    "time": "2026-06-09 14:00"
  }
}
```

字段规则：

- `tool_name` 必须来自 `available_tools`。
- `arguments` 只能包含该工具允许的参数。
- 已知参数必须正确填入。
- 未知参数统一填 `未知`。
- 不能输出不存在的工具名。

### 7.3 `final`：最终预约 JSON

适用条件：

- 必填信息已完整。
- 需要查询的外部事实已有工具结果支撑。
- 可以交给后续业务系统创建订单或进入确认流程。

输出格式：

```json
{
  "action": "final",
  "project": "肩颈按摩",
  "technician_name": "小王",
  "start_time": "2026-06-09 14:00",
  "duration": "60分钟",
  "gender": "未知",
  "info_complete": true,
  "missing_info": [],
  "unrelated": false
}
```

字段规则：

- `project`：服务项目；未知时填 `未知`。
- `technician_name`：指定技师；未指定时填 `未知`。
- `start_time`：绝对时间；无法确定时不能 `final`，应 `ask`。
- `duration`：服务时长；缺失时通常应 `ask`，除非业务允许默认值。
- `gender`：用户提到性别偏好才填写，否则 `未知`。
- `info_complete`：最终预约信息是否完整。
- `missing_info`：完整时为空数组。
- `unrelated`：最终预约场景固定为 `false`。

### 7.4 `unrelated`：无关或超出边界

适用条件：

- 用户问题与预约流程无关。
- 用户要求模型做非预约任务。
- 用户请求超出本模块职责。

输出格式：

```json
{
  "action": "unrelated",
  "unrelated": true,
  "reason": "用户输入与预约流程无关"
}
```

字段规则：

- 不要回答用户的无关问题。
- 不要混入预约字段。
- 不要调用无关工具。

### 7.5 `confirmation`：确认、否定、取消、改口

适用条件：

- 用户确认当前方案。
- 用户否定当前方案。
- 用户取消预约。
- 用户修改已经提供过的信息。

输出格式：

```json
{
  "action": "confirmation",
  "confirmation": "confirm | deny | cancel | change | unknown",
  "change_request": false,
  "changed_fields": [],
  "finalize": true,
  "unrelated": false
}
```

字段规则：

- `confirm`：如“对”“就这样”“可以”。
- `deny`：如“不是”“不对”“不行”。
- `cancel`：如“算了”“不要了”“取消”。
- `change`：如“换一个”“改到后天”“不是小王，是李师傅”。
- `unknown`：无法确定用户意图。
- 有改口时，`changed_fields` 填写被修改字段，如 `["start_time"]`、`["technician_name"]`。

## 8. 标准字段集合

预约相关字段第一版固定为：

| 字段 | 类型 | 说明 | 未知策略 |
|---|---|---|---|
| `action` | enum | 模型动作 | 必填 |
| `project` | string | 服务项目 | `未知` |
| `technician_name` | string | 技师名 | `未知` |
| `start_time` | string | 预约开始时间 | `未知` 或追问 |
| `duration` | string | 服务时长 | `未知` 或追问 |
| `gender` | enum/string | 性别偏好 | `未知` |
| `info_complete` | boolean | 信息是否完整 | 必填于 `final/ask` |
| `missing_info` | array | 缺失字段列表 | 无缺失时 `[]` |
| `tool_name` | string | 工具名 | 仅 `tool_call` |
| `arguments` | object | 工具参数 | 仅 `tool_call` |
| `unrelated` | boolean | 是否无关 | 相关时 `false` |
| `confirmation` | enum | 确认/否定/取消/改口 | 仅 `confirmation` |
| `change_request` | boolean | 是否改口 | 仅 `confirmation` |
| `changed_fields` | array | 改口字段 | 仅 `confirmation` |
| `finalize` | boolean | 是否可最终确认 | 仅 `confirmation` |

## 9. 工具契约

### 9.1 `find_technicians`

用途：

查询技师是否存在、是否可约、是否满足指定项目和时间。

输入参数：

```json
{
  "technician_name": "string | 未知",
  "project": "string | 未知",
  "start_time": "YYYY-MM-DD HH:mm | 未知",
  "duration": "string | 未知"
}
```

返回结果示例：

```json
{
  "technicians": [
    {
      "technician_name": "小王",
      "available": true,
      "project_supported": true,
      "start_time": "2026-06-09 14:00"
    }
  ]
}
```

边界说明：

- 模型只能决定是否调用该工具。
- 模型不能自行判断技师是否存在。
- 模型不能自行判断技师是否可约。
- 工具返回为空时，模型不能编造替代技师。

### 9.2 `get_current_weather`

用途：

查询预约时间附近的天气，用于预约后提醒或出行建议。

输入参数：

```json
{
  "location": "string | 未知",
  "time": "YYYY-MM-DD HH:mm | 未知"
}
```

返回结果示例：

```json
{
  "weather": "小雨",
  "temperature": "22°C",
  "suggestion": "建议带伞"
}
```

边界说明：

- 模型不能自行编造天气。
- 用户询问天气时，若时间或地点缺失，应先追问或填 `未知` 交给工具侧处理。
- 天气分支属于六类任务中的类型 6。

## 10. 正反例边界

### 10.1 需要追问，而不是工具调用

用户：

```text
明天下午帮我约个按摩
```

原因：

- 有预约意图。
- 有相对日期和大致时间段。
- 缺具体项目、具体时间、时长。

正确输出：

```json
{
  "action": "ask",
  "missing_info": ["project", "start_time", "duration"],
  "question": "可以，请问您想预约什么项目、明天下午具体几点、做多久？",
  "info_complete": false
}
```

### 10.2 需要工具调用，而不是最终预约

用户：

```text
小王明天下午两点有空吗？
```

已知：

```json
{
  "current_time": "2026-06-08 10:00",
  "available_tools": ["find_technicians"]
}
```

正确输出：

```json
{
  "action": "tool_call",
  "tool_name": "find_technicians",
  "arguments": {
    "technician_name": "小王",
    "project": "未知",
    "start_time": "2026-06-09 14:00",
    "duration": "未知"
  }
}
```

错误输出：

```json
{
  "action": "final",
  "technician_name": "小王",
  "start_time": "2026-06-09 14:00",
  "info_complete": true
}
```

错误原因：

模型不能自行判断小王是否有空。

### 10.3 可以最终输出

输入中已有工具结果：

```json
{
  "tool_results": {
    "find_technicians": {
      "technicians": [
        {
          "technician_name": "小王",
          "available": true,
          "project_supported": true,
          "start_time": "2026-06-09 14:00"
        }
      ]
    }
  }
}
```

用户：

```text
60分钟，就这个
```

正确输出：

```json
{
  "action": "final",
  "project": "肩颈按摩",
  "technician_name": "小王",
  "start_time": "2026-06-09 14:00",
  "duration": "60分钟",
  "gender": "未知",
  "info_complete": true,
  "missing_info": [],
  "unrelated": false
}
```

### 10.4 无关输入

用户：

```text
你能帮我写一段 Python 代码吗？
```

正确输出：

```json
{
  "action": "unrelated",
  "unrelated": true,
  "reason": "用户输入与预约流程无关"
}
```

### 10.5 确认/取消/改口

历史：

```text
助手：小王明天下午两点可以预约，是否确认？
```

用户：

```text
算了，不约了
```

正确输出：

```json
{
  "action": "confirmation",
  "confirmation": "cancel",
  "change_request": false,
  "changed_fields": [],
  "finalize": false,
  "unrelated": false
}
```

用户：

```text
不是小王，换李师傅
```

正确输出：

```json
{
  "action": "confirmation",
  "confirmation": "change",
  "change_request": true,
  "changed_fields": ["technician_name"],
  "finalize": false,
  "unrelated": false
}
```

### 10.6 天气工具分支

历史：

```text
助手：已为您暂定 2026-06-09 14:00 的肩颈按摩。
```

用户：

```text
那天下雨吗？要不要带伞？
```

正确输出：

```json
{
  "action": "tool_call",
  "tool_name": "get_current_weather",
  "arguments": {
    "location": "门店所在地",
    "time": "2026-06-09 14:00"
  }
}
```

## 11. 训练与评估约束

后续构造数据集时必须遵守：

- `task_spec_v0.md` 是第一版任务边界来源。
- 先基于本文件构造冻结评估集 `test_v0.jsonl`。
- 再构造训练集 `train.jsonl` 和验证集 `val.jsonl`。
- 评估集字段 `expected`、`assertions`、`gold_facts`、`tags` 不得进入训练 prompt。
- 训练样本只包含模型线上会看到的输入，以及标准 label。
- 所有数据必须可追溯到版本、生成脚本和人工检查记录。

### 11.1 Eval assertion DSL

评估集中的 `assertions` 是给评估器使用的规则字符串。第一版允许以下形式：

| 形式 | 语义 |
|---|---|
| `field == value` | expected / model output 中字段必须等于指定值 |
| `args.field == value` | `tool_call.arguments.field` 必须等于指定值 |
| `set(field) == {a,b}` | 数组字段按集合比较，不要求顺序 |
| `set(keys(arguments)) == {a,b,c}` | 工具参数 key 集合必须完全一致 |
| `not_exists(field)` | 输出中不得出现该字段 |
| `question contains text` | 追问文案应包含关键提示词；冻结评估时可作为辅助断言，主分数以 `missing_info` 为准 |
| `technician_name in tool_results.find_technicians.technicians[].technician_name` | final 选择的技师必须来自工具返回 |
| `technician_name in tool_results.find_technicians.technicians[gender==女].technician_name` | final 选择的技师必须来自满足过滤条件的工具返回 |
| `no_field_outside_schema` | 输出不得包含当前 action schema 之外的字段 |
| `no_technician_outside_gold_facts` | 未经工具或 gold_facts 支撑时不得编造技师 |

实现评估器时，`question contains ...` 建议降权或仅用于定位问题；结构化主分数应优先来自 action、字段值、工具参数、缺失字段和 hallucination 约束。

## 12. 第一版验收标准

模型通过第一版上线候选评估，应至少满足：

- JSON 合法率 >= 98%。
- Schema 合规率 >= 98%。
- 字段抽取准确率 >= 90%。
- 工具调用准确率 >= 90%。
- 意图/动作判断准确率 >= 95%。
- 幻觉率 <= 3%。
- 量化后质量回退 <= 2%。
- CPU 完整输出 P95 控制在 1.5-2.0 秒附近。

以上阈值是第一版建议线，可在真实业务约束明确后调整。
