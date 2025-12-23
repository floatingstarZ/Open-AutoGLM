# Judge自动修正功能说明

## 概述

移除了人机交互模式，实现了基于Judge的完全自动化Action修正流程。Judge现在会自动评估每个Action，并在发现问题时自动应用修正。

## 主要变化

### 1. 移除Interactive模式

**删除的配置项**:
- `enable_interactive`: 已完全移除

**删除的方法**:
- `_handle_user_interaction`: 处理用户交互的方法

**影响**:
- 不再需要用户在每个步骤后手动选择
- Agent完全自动化运行

### 2. Judge默认启用

**配置变化**:
```python
# 之前
enable_judge: bool = False  # 默认禁用

# 现在
enable_judge: bool = True   # 默认启用
```

### 3. 自动化Judge流程

新的执行流程如下：

```
1. Agent输出Action预测
   ↓
2. Judge评估Action
   ↓
3. Judge判断:
   - verdict=True (合理) → 使用原Action
   - verdict=False (不合理) → 尝试修正
   ↓
4. 如果需要修正:
   a. 优先使用Judge的correct_action（如果有）
   b. 如果没有correct_action，使用Refine Action
   c. 更新_context和_full_context
   ↓
5. 执行最终Action
```

### 4. 新增方法: `_apply_judge_decision`

**功能**: 根据Judge结果自动选择最终执行的Action

**逻辑**:
1. 如果Judge未启用或verdict=True（合理）→ 使用原Action
2. 如果verdict=False（不合理）:
   - 首先尝试解析Judge提供的`correct_action`
   - 如果`correct_action`不可用或解析失败，使用refined action
   - 如果都不可用，回退到原Action

**返回值**:
```python
(final_action, final_response, action_was_refined)
```

### 5. Context更新逻辑

当使用refined action时，会自动更新`_context`和`_full_context`:

```python
if action_was_refined:
    # 移除原始的assistant消息
    self._context.pop()
    self._full_context.pop()

    # 添加refined后的assistant消息
    self._context.append(refined_assistant_msg)
    self._full_context.append(refined_assistant_msg)
```

这确保了对话历史的一致性，后续的Action会基于修正后的历史进行决策。

## 使用示例

### 基本使用（Judge自动启用）

```python
from phone_agent import PhoneAgent
from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig

model_config = ModelConfig(
    base_url="http://localhost:8000/v1",
    model_name="autoglm-phone-9b",
)

agent_config = AgentConfig(
    # Judge默认启用，会自动评估和修正
    judge_api_key="your-api-key",
    judge_base_url="https://api-gateway.glm.ai/v1",
    judge_model_name="claude-sonnet-4-5-20250929",
    judge_history_images_k=5,
)

agent = PhoneAgent(model_config, agent_config)
result = agent.run("打开微信并发送消息")
```

### 禁用Judge（更快执行）

```python
agent_config = AgentConfig(
    enable_judge=False,  # 禁用Judge，直接执行
)

agent = PhoneAgent(model_config, agent_config)
result = agent.run("打开微信")
```

## 执行示例

运行示例程序：

```bash
# 使用Judge（自动修正）
python example_judge_interactive.py 1

# 不使用Judge（更快）
python example_judge_interactive.py 2

# 逐步执行（带Judge）
python example_judge_interactive.py 3
```

## Judge工作流程示例

### 场景1: Action正确

```
1. Agent输出: do(action="Tap", element=[500, 300])
2. Judge评估: verdict=True, score=85
3. 输出: ✅ Judge认为当前步骤合理 (评分: 85/100)
4. 执行: 原Action
```

### 场景2: Action错误，Judge提供correct_action

```
1. Agent输出: do(action="Tap", element=[100, 100])
2. Judge评估: verdict=False, score=30
   correct_action: 'do(action="Tap", element=[500, 300])'
3. 输出: ⚠️ Judge认为当前步骤存在问题
        🎯 使用Judge建议的正确动作
4. 执行: Judge的correct_action
5. Context更新: 替换为correct_action
```

### 场景3: Action错误，使用Refine

```
1. Agent输出: do(action="Swipe", start=[100, 100], end=[100, 200])
2. Judge评估: verdict=False, score=40
   correct_action: ""  (Judge没有提供具体动作)
3. Refine: 重新调用模型，根据Judge建议生成新动作
4. 输出: 🔄 使用Refined动作
5. 执行: Refined action
6. Context更新: 替换为refined action
```

## 技术细节

### correct_action的格式

Judge返回的`correct_action`是一个JSON格式的字符串，例如：

```json
{
  "correct_action": "do(action=\"Tap\", element=[500, 300])"
}
```

代码会自动解析这个字符串并转换为Action字典。

### Context更新的重要性

更新Context确保了：
1. **一致性**: 后续步骤基于修正后的历史
2. **可追溯**: Trace日志记录了实际执行的Action
3. **Judge准确性**: Judge评估时看到的是修正后的历史

### 性能考虑

- **启用Judge**: 每步需要额外的API调用（Judge + 可能的Refine）
- **禁用Judge**: 直接执行，速度更快但可能出错
- **建议**: 重要任务启用Judge，简单任务可禁用

## 与旧版本的兼容性

### 已移除的功能
- `enable_interactive`配置项
- `_handle_user_interaction`方法
- 用户交互相关的提示和输入

### 迁移指南

如果你的代码使用了`enable_interactive`：

```python
# 旧代码
agent_config = AgentConfig(
    enable_judge=True,
    enable_interactive=True,  # 已移除
)

# 新代码（自动修正）
agent_config = AgentConfig(
    enable_judge=True,  # 会自动修正，无需交互
)

# 或者禁用Judge
agent_config = AgentConfig(
    enable_judge=False,  # 完全自动化，无Judge
)
```

## 相关文件

- `phone_agent/agent.py`: 主要修改
  - 移除`enable_interactive`配置
  - 删除`_handle_user_interaction`方法
  - 新增`_apply_judge_decision`方法
  - 更新`_execute_step`的Judge逻辑

- `example_judge_interactive.py`: 示例更新
  - 移除Interactive相关示例
  - 简化为3个示例：With Judge, Without Judge, Step-by-step

- `judge_tools/judge.py`: Judge功能（已在之前重构）
  - 使用`judge_from_full_context`简化调用

## 调试建议

如果遇到问题：

1. **开启verbose模式**:
   ```python
   agent_config = AgentConfig(verbose=True)
   ```

2. **查看Judge评估结果**: 会显示verdict, score, suggestions

3. **检查Trace日志**:
   - 位置: `traces/task_xxx/trace.jsonl`
   - 包含每步的Judge结果和实际执行的Action

4. **临时禁用Judge**:
   ```python
   agent_config = AgentConfig(enable_judge=False)
   ```

## 后续优化方向

1. 添加Judge结果的缓存机制
2. 支持自定义Judge策略（如只在特定条件下修正）
3. 统计和分析Judge的修正率和准确率
4. 支持多个Judge模型的投票机制
