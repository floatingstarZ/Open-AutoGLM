# 格式转换工具 (convert_format.py)

## 概述

`convert_format.py` 提供了整个trace（对话历史）在Claude格式和当前项目格式之间的双向转换功能。

## 格式说明

### 当前格式 (Current Format)

Open-AutoGLM项目使用的对话历史格式：

```python
[
    {
        "role": "system",
        "content": "你是一个智能体分析专家..."
    },
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "外卖下单四杯蜜雪冰城的奶昔\n\n{\"current_app\": \"文件\"}"
            }
        ]
    },
    {
        "role": "assistant",
        "content": "<think>用户想要点外卖，需要先打开美团应用。</think><answer>do(action=\"Launch\", app=\"美团\")</answer>"
    },
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "** Screen Info **\n\n{\"current_app\": \"美团\"}"
            }
        ]
    },
    {
        "role": "assistant",
        "content": "<think>需要点击外卖入口。</think><answer>do(action=\"Tap\", element=[120, 190])</answer>"
    }
]
```

**特点：**
- system消息：纯字符串格式的content
- user消息：content是数组，包含text块（可能还有image块）
- assistant消息：content是字符串，格式为 `<think>...</think><answer>...</answer>`

### Claude格式 (Claude Format)

Claude API使用的对话历史格式：

```python
[
    {
        "role": "system",
        "content": "你是一个智能体分析专家..."
    },
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "外卖下单四杯蜜雪冰城的奶昔\n\n{\"current_app\": \"文件\"}"
            }
        ]
    },
    {
        "role": "assistant",
        "content": [
            {
                "type": "thinking",
                "thinking": "用户想要点外卖，需要先打开美团应用。",
                "signature": "uuid-string"
            },
            {
                "type": "tool_use",
                "id": "toolu_bdrk_xxxxx",
                "name": "Launch",
                "input": {
                    "app": "美团"
                }
            }
        ]
    },
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "** Screen Info **\n\n{\"current_app\": \"美团\"}"
            }
        ]
    },
    {
        "role": "assistant",
        "content": [
            {
                "type": "thinking",
                "thinking": "需要点击外卖入口。"
            },
            {
                "type": "tool_use",
                "id": "toolu_bdrk_xxxxx",
                "name": "Tap",
                "input": {
                    "coordinate": [120, 190]
                }
            }
        ]
    }
]
```

**特点：**
- system消息：与当前格式相同
- user消息：与当前格式相同
- assistant消息：content是数组，包含thinking、tool_use、text块

## 主要函数

### 1. current_to_claude(messages, current_image_scale=None, claude_image_scale=None)

将当前格式的对话历史转换为Claude格式。

**参数：**
- `messages` (List[Dict[str, Any]]): 当前格式的消息列表
- `current_image_scale` (Optional[List[int]]): 当前格式中的图像分辨率 [width, height]，如果提供则进行坐标缩放
- `claude_image_scale` (Optional[List[int]]): Claude推理时的图像分辨率 [width, height]，如果提供则进行坐标缩放

**返回：**
- `List[Dict[str, Any]]`: Claude格式的消息列表

**示例1: 不带坐标缩放**

```python
from judge_tools.convert_format import current_to_claude

# 当前格式的对话历史
current_messages = [
    {"role": "system", "content": "你是一个智能助手..."},
    {"role": "user", "content": [{"type": "text", "text": "任务描述"}]},
    {"role": "assistant", "content": "<think>思考过程</think><answer>do(action=\"Tap\", element=[120, 190])</answer>"}
]

# 转换为Claude格式（不缩放坐标）
claude_messages = current_to_claude(current_messages)

# claude_messages:
# [
#     {"role": "system", "content": "你是一个智能助手..."},
#     {"role": "user", "content": [{"type": "text", "text": "任务描述"}]},
#     {
#         "role": "assistant",
#         "content": [
#             {"type": "thinking", "thinking": "思考过程", "signature": "..."},
#             {"type": "tool_use", "id": "toolu_...", "name": "Tap", "input": {"coordinate": [120, 190]}}
#         ]
#     }
# ]
```

**示例2: 带坐标缩放**

```python
from judge_tools.convert_format import current_to_claude

# 当前格式的对话历史（坐标基于720x1612）
current_messages = [
    {"role": "assistant", "content": "<think>点击搜索</think><answer>do(action=\"Tap\", element=[360, 800])</answer>"}
]

# 转换为Claude格式（坐标缩放到1092x1092）
claude_messages = current_to_claude(
    current_messages,
    current_image_scale=[720, 1612],  # 当前分辨率
    claude_image_scale=[1092, 1092]   # Claude分辨率
)

# 坐标从 [360, 800] 缩放到 [546, 541]
# 计算公式:
#   claude_x = int(360 * 1092 / 720) = 546
#   claude_y = int(800 * 1092 / 1612) = 541
```

### 2. claude_to_current(messages, claude_image_scale=None, current_image_scale=None)

将Claude格式的对话历史转换为当前格式。

**参数：**
- `messages` (List[Dict[str, Any]]): Claude格式的消息列表
- `claude_image_scale` (Optional[List[int]]): Claude推理时的图像分辨率 [width, height]，如果提供则进行坐标缩放
- `current_image_scale` (Optional[List[int]]): 当前格式中的图像分辨率 [width, height]，如果提供则进行坐标缩放

**返回：**
- `List[Dict[str, Any]]`: 当前格式的消息列表

**示例1: 不带坐标缩放**

```python
from judge_tools.convert_format import claude_to_current

# Claude格式的对话历史
claude_messages = [
    {"role": "system", "content": "你是一个智能助手..."},
    {"role": "user", "content": [{"type": "text", "text": "任务描述"}]},
    {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "思考过程"},
            {"type": "tool_use", "name": "Tap", "input": {"coordinate": [120, 190]}}
        ]
    }
]

# 转换为当前格式（不缩放坐标）
current_messages = claude_to_current(claude_messages)

# current_messages:
# [
#     {"role": "system", "content": "你是一个智能助手..."},
#     {"role": "user", "content": [{"type": "text", "text": "任务描述"}]},
#     {"role": "assistant", "content": "<think>思考过程</think><answer>do(action=\"Tap\", element=[120, 190])</answer>"}
# ]
```

**示例2: 带坐标缩放**

```python
from judge_tools.convert_format import claude_to_current

# Claude格式的对话历史（坐标基于1092x1092）
claude_messages = [
    {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "点击搜索"},
            {"type": "tool_use", "name": "Tap", "input": {"coordinate": [546, 541]}}
        ]
    }
]

# 转换为当前格式（坐标缩放到720x1612）
current_messages = claude_to_current(
    claude_messages,
    claude_image_scale=[1092, 1092],  # Claude分辨率
    current_image_scale=[720, 1612]   # 当前分辨率
)

# 坐标从 [546, 541] 缩放到 [360, 798]
# 计算公式:
#   current_x = int(546 * 720 / 1092) = 360
#   current_y = int(541 * 1612 / 1092) = 798
```

### 3. 辅助函数

#### extract_thinking_and_action(content)

从assistant content中提取thinking和action字符串。

```python
from judge_tools.convert_format import extract_thinking_and_action

content = "<think>需要点击搜索</think><answer>do(action=\"Tap\", element=[360, 800])</answer>"
thinking, action_str = extract_thinking_and_action(content)

print(thinking)    # "需要点击搜索"
print(action_str)  # "do(action=\"Tap\", element=[360, 800])"
```

#### build_assistant_content(thinking, action_str)

构建assistant content字符串。

```python
from judge_tools.convert_format import build_assistant_content

thinking = "需要点击搜索"
action_str = "do(action=\"Tap\", element=[360, 800])"

content = build_assistant_content(thinking, action_str)
print(content)
# "<think>需要点击搜索</think><answer>do(action=\"Tap\", element=[360, 800])</answer>"
```

## 转换细节

### Action类型转换

#### 1. 坐标操作（Tap、Long Press、Double Tap）

- **当前格式 → Claude格式：** `element` → `coordinate`
- **Claude格式 → 当前格式：** `coordinate` → `element`

```python
# 当前格式
"do(action=\"Tap\", element=[120, 190])"

# ↓↓↓ 转换后 ↓↓↓

# Claude格式
{
    "type": "tool_use",
    "name": "Tap",
    "input": {"coordinate": [120, 190]}
}
```

#### 2. 滑动操作（Swipe）

- **当前格式 → Claude格式：** `start`/`end` → `start_coordinate`/`end_coordinate`
- **Claude格式 → 当前格式：** `start_coordinate`/`end_coordinate` → `start`/`end`

```python
# 当前格式
"do(action=\"Swipe\", start=[100, 500], end=[100, 200])"

# ↓↓↓ 转换后 ↓↓↓

# Claude格式
{
    "type": "tool_use",
    "name": "Swipe",
    "input": {
        "start_coordinate": [100, 500],
        "end_coordinate": [100, 200]
    }
}
```

#### 3. 其他操作（Launch、Type、Back等）

参数直接传递，不需要字段名转换。

```python
# 当前格式
"do(action=\"Launch\", app=\"美团\")"

# ↓↓↓ 转换后 ↓↓↓

# Claude格式
{
    "type": "tool_use",
    "name": "Launch",
    "input": {"app": "美团"}
}
```

#### 4. 结束操作（finish）

- **当前格式 → Claude格式：** `finish(message="...")` → `{"type": "text", "text": "..."}`
- **Claude格式 → 当前格式：** `{"type": "text", "text": "..."}` → `finish(message="...")`

```python
# 当前格式
"finish(message=\"任务完成\")"

# ↓↓↓ 转换后 ↓↓↓

# Claude格式
{
    "type": "text",
    "text": "任务完成"
}
```

## 完整使用示例

### 示例1: 从trace文件转换为Claude格式（带坐标缩放）

```python
import json
from judge_tools.convert_format import current_to_claude

# 读取trace文件中的model_input
with open("traces/task_xxx/trace.jsonl", "r") as f:
    for line in f:
        step = json.loads(line)
        if step["type"] == "step":
            # 获取当前格式的对话历史和屏幕尺寸
            current_messages = step["model_input"]
            screen_size = step["screen_size"]

            # 当前格式使用的图像分辨率
            current_image_scale = [screen_size["width"], screen_size["height"]]

            # Claude推理时的图像分辨率（例如1092x1092）
            claude_image_scale = [1092, 1092]

            # 转换为Claude格式（坐标会自动缩放）
            claude_messages = current_to_claude(
                current_messages,
                current_image_scale=current_image_scale,
                claude_image_scale=claude_image_scale
            )

            # 使用Claude格式进行评估或其他操作
            print(json.dumps(claude_messages, ensure_ascii=False, indent=2))
```

### 示例2: Claude API响应转换回当前格式

```python
from judge_tools.convert_format import claude_to_current

# Claude API返回的对话历史
claude_response = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": [...]},
    {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "..."},
            {"type": "tool_use", "name": "Tap", "input": {...}}
        ]
    }
]

# 转换为当前格式
current_messages = claude_to_current(claude_response)

# 可以继续使用当前格式进行后续处理
```

### 示例3: 往返转换验证

```python
from judge_tools.convert_format import current_to_claude, claude_to_current, extract_thinking_and_action

# 原始数据
original = [
    {"role": "assistant", "content": "<think>思考</think><answer>do(action=\"Tap\", element=[100, 200])</answer>"}
]

# 转换为Claude格式
claude_format = current_to_claude(original)

# 转换回当前格式
converted_back = claude_to_current(claude_format)

# 验证一致性
orig_thinking, orig_action = extract_thinking_and_action(original[0]["content"])
conv_thinking, conv_action = extract_thinking_and_action(converted_back[0]["content"])

assert orig_action == conv_action  # 应该完全一致
```

## 测试

运行以下命令测试所有转换函数：

```bash
python judge_tools/convert_format.py
```

测试将执行：
1. 不带缩放的转换（100%一致性）
2. 带坐标缩放的转换（验证缩放精度）
3. 往返转换精度验证

示例输出：
```
================================================================================
示例1: 不带缩放的转换（当前格式 -> Claude格式 -> 当前格式）
================================================================================
消息 2:
  原始action: do(action="Launch", app="美团")
  转换action: do(action="Launch", app="美团")
  一致性: True
消息 4:
  原始action: do(action="Tap", element=[120, 190])
  转换action: do(action="Tap", element=[120, 190])
  一致性: True

================================================================================
示例2: 带坐标缩放的转换
================================================================================
当前图像分辨率: [720, 1612]
Claude图像分辨率: [1092, 1092]
缩放因子: X=1.5167, Y=0.6774

原始坐标（基于720x1612）:
  do(action="Tap", element=[360, 800])
  do(action="Swipe", start=[360, 1200], end=[360, 400])

Claude格式（坐标缩放到1092x1092）:
  Tap: {'coordinate': [546, 541]}
  Swipe: {'start_coordinate': [546, 812], 'end_coordinate': [546, 270]}

转换回当前格式（坐标恢复到720x1612）:
  do(action="Tap", element=[360, 798])
  do(action="Swipe", start=[360, 1198], end=[360, 398])

================================================================================
验证: 检查往返转换的坐标精度
================================================================================
消息 0:
  原始: do(action="Tap", element=[360, 800])
  转换: do(action="Tap", element=[360, 798])
  坐标差异: X=0px, Y=2px

消息 1:
  原始: do(action="Swipe", start=[360, 1200], end=[360, 400])
  转换: do(action="Swipe", start=[360, 1198], end=[360, 398])
  起点差异: X=0px, Y=2px
  终点差异: X=0px, Y=2px
```

从测试结果可以看出：
- **不带缩放**：往返转换100%一致
- **带缩放**：往返转换误差在1-2像素（由于整数舍入），在实际使用中完全可以接受

## 注意事项

1. **坐标缩放**：
   - 如果提供了`current_image_scale`和`claude_image_scale`参数，坐标会自动缩放
   - 缩放公式：`target_coord = int(source_coord * target_size / source_size)`
   - 由于整数除法的舍入，往返转换可能有1-2像素的误差
   - 如果不提供缩放参数，坐标保持不变

2. **往返转换一致性**：
   - 不带缩放：`claude_to_current(current_to_claude(x)) == x` （100%一致）
   - 带缩放：由于整数舍入，可能有1-2像素误差

3. **坐标字段名**：注意不同格式中坐标字段的命名差异：
   - 当前格式：`element`（单点）、`start`/`end`（滑动）
   - Claude格式：`coordinate`（单点）、`start_coordinate`/`end_coordinate`（滑动）

4. **finish操作**：finish操作在两种格式中的表示方式不同：
   - 当前格式：`finish(message="...")`
   - Claude格式：`{"type": "text", "text": "..."}`

5. **错误处理**：如果action字符串解析失败，会将其作为text类型处理，不会抛出异常。

6. **UUID生成**：每次转换都会生成新的signature和tool_use ID，不保留原始ID。

## 集成到judge流程

在judge流程中使用格式转换：

```python
from judge_tools.convert_format import current_to_claude
from judge_tools.judge import judge_model_output

# 从trace读取数据
with open("traces/task_xxx/trace.jsonl", "r") as f:
    for line in f:
        step = json.loads(line)
        if step["type"] == "step":
            # 获取当前格式的对话历史
            current_messages = step["model_input"]

            # 转换为Claude格式（如果judge需要Claude格式）
            claude_messages = current_to_claude(current_messages)

            # 使用judge评估（具体参数根据judge.py的要求调整）
            # result = judge_model_output(...)
```
