# Judge函数重构说明

## 概述

重构了judge功能,创建了一个新的简化函数`judge_from_full_context`,它只需要传入`full_context`即可完成判断,不再需要`model_input`、`screenshot_path`、`format_model_output`和`trace_file_path`等参数。

## 主要变化

### 1. 新增函数: `judge_from_full_context`

**位置**: `judge_tools/judge.py`

**函数签名**:
```python
def judge_from_full_context(
    full_context: list[dict[str, Any]],
    history_images_k: int = 5,
    api_key: str = DEFAULT_API_KEY,
    base_url: str = DEFAULT_BASE_URL,
    model_name: str = DEFAULT_MODEL_NAME,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = DEFAULT_RETRY_DELAY,
) -> dict[str, Any]:
```

**参数说明**:
- `full_context`: 完整的对话历史,包含system、user(带图片)和assistant消息。最后一个消息应该是需要评估的assistant消息
- `history_images_k`: 保留最近K个user message的截图(默认5)。例如K=5,则只为最后5个user message保留截图
- 其他参数: API配置参数(api_key, base_url, model_name等)

**返回值**: 与原`judge_model_output`函数相同的评估结果字典

### 2. history_images_k逻辑重新实现

新函数中的`history_images_k`逻辑:

1. **计数user消息**: 遍历`full_context`,统计user消息的数量
2. **确定保留范围**: 计算从哪个user消息开始保留图片
   - 例如: 如果有10个user消息,`history_images_k=5`,则保留第6-10个user消息的图片
3. **过滤图片**: 对于不在保留范围内的user消息,移除其`content`中的`image_url`类型内容,只保留`text`类型内容

**核心代码**:
```python
if history_images_k > 0:
    total_user_msgs = user_msg_count
    start_keeping_images_from = max(1, total_user_msgs - history_images_k + 1)

    for msg in messages:
        if msg.get("role") == "user":
            user_index = msg.pop("_user_msg_index", 0)

            # 如果这个user message不在保留范围内,移除图片
            if user_index < start_keeping_images_from:
                content = msg.get("content", [])
                if isinstance(content, list):
                    msg["content"] = [
                        item for item in content
                        if item.get("type") != "image_url"
                    ]
```

### 3. 更新调用代码

**位置**: `phone_agent/agent.py`

**变化**:
- 导入: `from judge_tools.judge import judge_from_full_context`
- `_judge_step`方法简化:
  - 移除了临时文件创建、screenshot保存等逻辑
  - 直接传入`self._full_context`
  - 不再需要`screenshot_path`和`screenshot_base64`参数(保留是为了向后兼容)

**简化后的调用**:
```python
judge_result = judge_from_full_context(
    full_context=self._full_context,
    history_images_k=self.agent_config.judge_history_images_k,
    api_key=self.agent_config.judge_api_key,
    base_url=self.agent_config.judge_base_url,
    model_name=self.agent_config.judge_model_name,
)
```

## 优势

1. **接口简化**: 只需要传入`full_context`,大大简化了调用代码
2. **逻辑内聚**: history_images_k的处理逻辑完全在judge函数内部,不需要外部处理
3. **无需临时文件**: 不再需要创建临时截图文件,直接使用full_context中已有的base64图片
4. **更易维护**: 减少了外部依赖(如trace_file_path),降低了维护成本
5. **向后兼容**: 保留了原`judge_model_output`函数,不影响其他可能的使用者

## 测试

创建了测试脚本`test_judge_from_full_context.py`,包含:
1. 空context错误处理测试
2. history_images_k过滤功能测试
3. 基本功能测试框架(需要有效的API密钥)

运行测试:
```bash
python test_judge_from_full_context.py
```

## 使用示例

```python
from judge_tools.judge import judge_from_full_context

# 假设你有一个包含完整对话历史的full_context
full_context = [
    {"role": "system", "content": "System prompt..."},
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "用户指令"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
        ]
    },
    {"role": "assistant", "content": "<think>...</think><answer>...</answer>"},
    # ... 更多消息
]

# 调用judge
result = judge_from_full_context(
    full_context=full_context,
    history_images_k=5,  # 只保留最近5个user message的图片
)

print(f"Verdict: {result['verdict']}")
print(f"Score: {result['model_score']}")
```

## 兼容性说明

- **原函数保留**: `judge_model_output`函数保持不变,现有代码仍可使用
- **新项目推荐**: 新项目应优先使用`judge_from_full_context`
- **迁移建议**: 如果你的代码使用了`judge_model_output`,可以逐步迁移到`judge_from_full_context`,只需要:
  1. 将`model_input`和最后的assistant消息合并为完整的`full_context`
  2. 确保user消息中已包含图片(在`full_context`中应该已经有)
  3. 移除`screenshot_path`、`format_model_output`、`trace_file_path`参数

## 后续计划

1. 考虑废弃`judge_model_output`,完全迁移到新函数
2. 添加更多单元测试
3. 优化图片过滤逻辑,支持更灵活的配置
