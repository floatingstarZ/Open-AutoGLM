# Judge & Interactive Mode 使用指南

## 概述

本项目已经增强了 `PhoneAgent`，增加了以下新功能：

1. **Judge 功能**: 在每个 step 后，使用 judge 模型评估当前步骤是否合理
2. **Interactive 模式**: 在每个 step 后等待用户输入，让用户选择是否继续
3. **Refine 功能**: 当 judge 认为步骤不合理时，根据建议自动重新生成动作
4. **Full Context**: 保留包含所有图片的完整对话历史

## 主要改进

### 1. AgentConfig 新增配置项

```python
from phone_agent.agent import AgentConfig

config = AgentConfig(
    # Judge 配置
    enable_judge=True,  # 启用 judge 功能
    judge_api_key="your-api-key",
    judge_base_url="https://api-gateway.glm.ai/v1",
    judge_model_name="claude-sonnet-4-5-20250929",
    judge_history_images_k=5,  # Judge 时使用最近 K 个截图

    # Interactive 配置
    enable_interactive=True,  # 启用交互模式
)
```

### 2. 新增属性

```python
agent = PhoneAgent(model_config, agent_config)

# 获取不包含图片的上下文（节省内存）
context = agent.context

# 获取包含所有图片的完整上下文
full_context = agent.full_context
```

## 工作流程

### Judge-Only 模式 (`enable_judge=True`, `enable_interactive=False`)

1. Agent 执行一个 step，生成 action
2. Judge 模型评估这个 action
3. 如果 judge 认为不合理（`verdict=False`）：
   - 显示评估结果（分数、置信度、建议）
   - 自动调用 refine 功能重新生成 action
   - 使用 refined action 继续执行
4. 如果 judge 认为合理（`verdict=True`）：
   - 显示评估结果
   - 直接执行 original action

### Interactive-Only 模式 (`enable_judge=False`, `enable_interactive=True`)

1. Agent 执行一个 step，生成 action
2. 等待用户输入，提供选项：
   - 1: 继续执行
   - 2: 跳过此步骤
   - q: 退出任务
3. 根据用户选择执行相应操作

### Judge + Interactive 模式 (`enable_judge=True`, `enable_interactive=True`)

1. Agent 执行一个 step，生成 action
2. Judge 模型评估这个 action
3. 如果 judge 认为不合理（`verdict=False`）：
   - 显示评估结果（分数、置信度、建议）
   - 自动调用 refine 功能重新生成 action
   - 等待用户输入，提供选项：
     - 1: 使用原始动作
     - 2: 使用修正后的动作
     - 3: 跳过此步骤
     - q: 退出任务
4. 如果 judge 认为合理（`verdict=True`）：
   - 显示评估结果
   - 等待用户输入，提供选项：
     - 1: 继续执行
     - 2: 跳过此步骤
     - q: 退出任务

## 使用示例

### 示例 1: 仅启用 Judge（自动修正）

```python
from phone_agent import PhoneAgent
from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig

model_config = ModelConfig(
    base_url="http://localhost:8000/v1",
    model_name="autoglm-phone-9b",
)

agent_config = AgentConfig(
    enable_judge=True,
    enable_interactive=False,
)

agent = PhoneAgent(model_config, agent_config)
result = agent.run("打开微信")
```

### 示例 2: 仅启用 Interactive（手动控制）

```python
agent_config = AgentConfig(
    enable_judge=False,
    enable_interactive=True,
)

agent = PhoneAgent(model_config, agent_config)
result = agent.run("打开微信")
# 每一步都会等待用户确认
```

### 示例 3: 启用 Judge + Interactive（完整功能）

```python
agent_config = AgentConfig(
    enable_judge=True,
    enable_interactive=True,
    judge_api_key="your-api-key",
    judge_base_url="https://api-gateway.glm.ai/v1",
    judge_model_name="claude-sonnet-4-5-20250929",
)

agent = PhoneAgent(model_config, agent_config)
result = agent.run("打开微信并发送消息给张三")
# Judge 会评估每一步，并提供修正建议
# 用户可以选择使用原始动作、修正后的动作，或跳过
```

### 示例 4: 访问完整上下文

```python
agent = PhoneAgent(model_config, agent_config)
result = agent.run("打开微信")

# 获取完整上下文（包含所有图片）
full_context = agent.full_context
print(f"Full context has {len(full_context)} messages")

# 可以将完整上下文用于其他用途，例如：
# - 保存完整对话历史
# - 用于离线分析
# - 传递给其他模型进行评估
```

## Judge 评估结果

Judge 模型会返回以下信息：

```python
{
    "verdict": False,  # 是否合理
    "scores": {
        "requirement_satisfaction": 60,  # 需求满足度 (0-100)
        "reasoning_correctness": 50,     # 推理正确性 (0-100)
        "conciseness": 75                 # 简洁性 (0-100)
    },
    "loop_detected": True,  # 是否检测到死循环
    "failed_steps": [
        {
            "step_id": "thinking",
            "snippet": "思考内容片段...",
            "why_failed": "失败原因说明"
        }
    ],
    "model_score": 55,        # 总体评分 (0-100)
    "model_confidence": 80,   # 置信度 (0-100)
    "correct_action": '{"action": "Tap", "coordinate": [100, 200]}',  # 建议的正确动作
    "repair_suggestions": "修复建议文本..."  # 详细的修复建议
}
```

## Refine 功能

当 judge 认为步骤不合理时，refine 功能会：

1. 根据 judge 的评估结果构建 refine prompt
2. 包含以下信息：
   - 评分和置信度
   - 失败原因
   - 修复建议
   - 建议的正确动作（如果有）
3. 调用模型重新生成 action
4. 返回 refined action 供用户选择

## 配置建议

### 开发调试阶段

建议启用 Interactive 模式，以便在每一步手动验证：

```python
agent_config = AgentConfig(
    enable_judge=True,
    enable_interactive=True,
    verbose=True,  # 显示详细日志
)
```

### 生产环境

可以只启用 Judge 模式，让系统自动修正：

```python
agent_config = AgentConfig(
    enable_judge=True,
    enable_interactive=False,
    verbose=False,
)
```

### 完全自动化

如果不需要任何干预，可以禁用两者：

```python
agent_config = AgentConfig(
    enable_judge=False,
    enable_interactive=False,
)
```

## 注意事项

1. **Judge API 配置**: 确保配置正确的 API key 和 base URL
2. **性能影响**: 启用 judge 会增加每个 step 的执行时间（需要额外的 API 调用）
3. **Full Context 内存**: `full_context` 包含所有图片，会占用更多内存
4. **Trace Logging**: Judge 功能会自动利用 trace logging 中的历史截图
5. **错误处理**: Judge 失败不会中断任务执行，只会记录警告

## 运行示例

```bash
# 运行示例 1: Judge-only 模式
python example_judge_interactive.py 1

# 运行示例 2: Interactive-only 模式
python example_judge_interactive.py 2

# 运行示例 3: Judge + Interactive 模式
python example_judge_interactive.py 3

# 运行示例 4: Step-by-step 执行
python example_judge_interactive.py 4
```

## 代码架构

### 新增方法

- `_judge_step()`: 调用 judge 模型评估当前步骤
- `_refine_action()`: 根据 judge 建议重新生成动作
- `_handle_user_interaction()`: 处理用户交互，提供选项

### 修改的方法

- `_execute_step()`: 集成了 judge、refine 和用户交互功能
- `run()`: 初始化 `_full_context`
- `reset()`: 重置 `_full_context`

### 新增属性

- `_full_context`: 保存包含所有图片的完整对话历史
- `full_context` (property): 公开访问完整上下文

## 相关文件

- `phone_agent/agent.py`: 主要实现
- `judge_tools/judge.py`: Judge 模型调用
- `example_judge_interactive.py`: 使用示例
- `JUDGE_INTERACTIVE_GUIDE.md`: 本文档
