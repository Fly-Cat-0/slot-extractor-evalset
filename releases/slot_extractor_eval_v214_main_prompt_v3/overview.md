# 数据集概览

## 这版数据集是什么

这版主评估集是当前 Slot-Extractor 任务的高信噪比主集：

- 文件：`eval.jsonl`
- 总样本数：`214`
- 对齐当前 `prompt_v3`

它优先服务于当前微调目标：

- 稳定输出合法 JSON
- 准确抽取预约字段
- 正确判断下一步动作
- 需要时正确调用工具
- 尽量不幻觉、不越界

## 制作思路

这版不是从零重做，而是在原始评估集基础上逐步整理得到：

1. 先统一任务逻辑和 `prompt_v3`。
2. 修正明显和当前规则冲突的 label。
3. 补齐关键分支：
   - `requested_technician`
   - `recommended`
   - `candidates=[]`
   - `project=未知` 时的追问
   - 工具参数组合
4. 把来源不清晰、容易混入编排层状态的问题样本拆出去，不放进主集。

所以这版主集的原则是：

- 尽量贴近当前 prompt 逻辑
- 尽量贴近真实系统里可能出现的上游上下文
- 尽量让失败反映模型能力问题，而不是数据来源问题

## 大致分布

主集 `214` 条的任务分布：

- `ask_missing_info`：`75`
- `technician_tool_call`：`38`
- `final_appointment`：`42`
- `unrelated`：`35`
- `confirmation`：`12`
- `weather_tool_call`：`7`
- `weather_tip`：`5`

可以看出这版主集还是以三类主干任务为主：

- `ask`
- `tool_call`
- `final`

这和当前训练目标是一致的，因为模型最核心的工作仍然是：

- 多轮上下文理解
- 结构化提取
- 工具判断

## confirmation 覆盖

主集里的 confirmation 不追求把所有稀有边界都塞满，而是保留更高信噪比的确认样本。

当前 confirmation 子类大致是：

- `confirm`：`7`
- `cancel`：`4`
- `unknown`：`1`

一些更激进、更容易受系统来源影响的 confirmation 探针，被单独拆到了：

- `probes_state_only_confirmation_8.jsonl`


## 怎么用

如果你的目标是：

- 做主模型评估
- 对齐当前微调目标
- 比较 checkpoint / prompt 改动

优先用 `eval.jsonl`。

如果你想额外看边界鲁棒性，再单独跑两个 probe 文件。

## 已知问题 / 使用提醒

这版数据集默认把 `history` 当作“系统上游已经发生过的上下文”来使用。

这意味着：

- `history` 里的 assistant 文本不一定能由当前 `prompt.md` 对应的 Slot-Extractor 模块直接生成
- 一部分 `history` 更像来自上游确认消息层、业务反馈层或预约执行层
- 因此，这个数据集主要用于评估“给定上下文后，当前模块是否能做出正确 JSON 决策”
- 不适合直接拿来证明“当前 prompt 本身可以逐轮生成所有 history 里的 assistant 话术”

如果后续要继续提高数据纯度，可以继续按这个原则清理：

- 保留有明确上游来源的 `history`
- 单独拆出来源悬空或编排态混入的 probe
