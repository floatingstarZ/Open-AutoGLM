# 格式转换工具 (convert_format.py)

## 概述

`convert_format.py` 提供了整个trace（对话历史）在Claude格式和当前项目格式之间的双向转换功能。

## 坐标系统说明 ⭐

这是最重要的概念！两种格式使用不同的坐标系统：

### 当前格式：相对坐标 (0-999)
- **坐标范围**：0-999（无论实际图像分辨率是多少）
- **坐标系统**：从左上角 (0,0) 到右下角 (999,999)
- **示例**：屏幕中心点始终是 [500, 500]，无论实际图像是720x1612还是1092x1092

### Claude格式：绝对坐标（基于实际图像分辨率）
- **坐标范围**：0-image_width, 0-image_height
- **坐标系统**：从左上角 (0,0) 到右下角 (image_width, image_height)
- **示例**：对于1092x1092的图像，屏幕中心点是 [546, 546]

### 坐标转换公式

**相对坐标 → 绝对坐标（current_to_claude）：**
```python
absolute_x = int(relative_x / 999 * image_width)
absolute_y = int(relative_y / 999 * image_height)
```

**绝对坐标 → 相对坐标（claude_to_current）：**
```python
relative_x = int(absolute_x / image_width * 999)
relative_y = int(absolute_y / image_height * 999)
```

**转换示例：**
```
相对坐标 [500, 500] (屏幕中心)
    ↓ 转换到1092x1092
绝对坐标 [546, 546]
    ↓ 转换回相对坐标
相对坐标 [499, 499] (1px精度损失)
```

---

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
- **坐标系统**：使用相对坐标（0-999范围）

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
- **坐标系统**：使用绝对坐标（基于实际图像分辨率）

## 主要函数

### 1. current_to_claude(messages, claude_image_scale=None)

将当前格式的对话历史转换为Claude格式，同时将相对坐标（0-999）转换为绝对坐标。

**参数：**
- `messages` (List[Dict[str, Any]]): 当前格式的消息列表
- `claude_image_scale` (Optional[List[int]]): Claude推理时的图像分辨率 [width, height]，用于将相对坐标转换为绝对坐标。如果不提供，坐标保持不变。

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

**示例2: 带坐标转换（相对坐标 → 绝对坐标）**

```python
from judge_tools.convert_format import current_to_claude

# 当前格式的对话历史（使用相对坐标0-999）
current_messages = [
    {"role": "assistant", "content": "<think>点击屏幕中心</think><answer>do(action=\"Tap\", element=[500, 500])</answer>"}
]

# 转换为Claude格式（转换为绝对坐标，基于1092x1092图像）
claude_messages = current_to_claude(
    current_messages,
    claude_image_scale=[1092, 1092]   # Claude推理时的图像分辨率
)

# 相对坐标 [500, 500] → 绝对坐标 [546, 546]
# 计算公式:
#   absolute_x = int(500 / 999 * 1092) = 546
#   absolute_y = int(500 / 999 * 1092) = 546
```

### 2. claude_to_current(messages, claude_image_scale=None)

将Claude格式的对话历史转换为当前格式，同时将绝对坐标转换为相对坐标（0-999）。

**参数：**
- `messages` (List[Dict[str, Any]]): Claude格式的消息列表
- `claude_image_scale` (Optional[List[int]]): Claude推理时的图像分辨率 [width, height]，用于将绝对坐标转换为相对坐标。如果不提供，坐标保持不变。

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

**示例2: 带坐标转换（绝对坐标 → 相对坐标）**

```python
from judge_tools.convert_format import claude_to_current

# Claude格式的对话历史（使用绝对坐标，基于1092x1092图像）
claude_messages = [
    {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "点击屏幕中心"},
            {"type": "tool_use", "name": "Tap", "input": {"coordinate": [546, 546]}}
        ]
    }
]

# 转换为当前格式（转换为相对坐标0-999）
current_messages = claude_to_current(
    claude_messages,
    claude_image_scale=[1092, 1092]  # Claude推理时的图像分辨率
)

# 绝对坐标 [546, 546] → 相对坐标 [499, 499]
# 计算公式:
#   relative_x = int(546 / 1092 * 999) = 499
#   relative_y = int(546 / 1092 * 999) = 499
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

### Thinking文本中的坐标

在转换过程中，thinking文本中的坐标也会被自动转换（相对坐标 ↔ 绝对坐标）：

**支持的坐标格式：**
- `[x, y]` - 方括号，带空格
- `[x,y]` - 方括号，不带空格
- `(x, y)` - 圆括号，带空格
- `(x,y)` - 圆括号，不带空格

**示例：**

```python
# 原始thinking（相对坐标0-999）
thinking = "我需要点击[500, 500]位置，然后从(300, 700)滑动到(300, 300)"

# 转换为Claude格式（绝对坐标，基于1092x1092）后
# "我需要点击[546, 546]位置，然后从(327, 765)滑动到(327, 327)"

# 转换回当前格式（相对坐标0-999）后
# "我需要点击[499, 499]位置，然后从(299, 699)到(299, 299)"
```

**注意：**
- 只匹配坐标值在0-10000范围内的数字对，避免误匹配其他数据
- 如果thinking中没有坐标，文本保持不变
- thinking中的坐标转换与action中的坐标转换使用相同的转换公式

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

### 示例1: 从trace文件转换为Claude格式（相对坐标 → 绝对坐标）

```python
import json
from judge_tools.convert_format import current_to_claude

# 读取trace文件中的model_input
with open("traces/task_xxx/trace.jsonl", "r") as f:
    for line in f:
        step = json.loads(line)
        if step["type"] == "step":
            # 获取当前格式的对话历史（使用相对坐标0-999）
            current_messages = step["model_input"]

            # Claude推理时的图像分辨率（例如1092x1092）
            claude_image_scale = [1092, 1092]

            # 转换为Claude格式（相对坐标 → 绝对坐标）
            claude_messages = current_to_claude(
                current_messages,
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
示例2: 坐标转换（相对坐标0-999 <-> 绝对坐标）
================================================================================
Claude图像分辨率: [1092, 1092]
Current坐标范围: 0-999 (相对坐标)
Claude坐标范围: 0-1092, 0-1092 (绝对坐标)

原始坐标（相对坐标，范围0-999）:
  do(action="Tap", element=[500, 500])
  do(action="Swipe", start=[500, 700], end=[500, 300])

Claude格式（绝对坐标，基于1092x1092）:
  Tap: {'coordinate': [546, 546]}
  Swipe: {'start_coordinate': [546, 765], 'end_coordinate': [546, 327]}

转换回当前格式（相对坐标，范围0-999）:
  do(action="Tap", element=[499, 499])
  do(action="Swipe", start=[499, 699], end=[499, 299])

================================================================================
验证: 检查往返转换的坐标精度
================================================================================
消息 0:
  原始: do(action="Tap", element=[500, 500])
  转换: do(action="Tap", element=[499, 499])
  坐标差异: X=1px, Y=1px

消息 1:
  原始: do(action="Swipe", start=[500, 700], end=[500, 300])
  转换: do(action="Swipe", start=[499, 699], end=[499, 299])
  起点差异: X=1px, Y=1px
  终点差异: X=1px, Y=1px
```

从测试结果可以看出：
- **不带转换**：往返转换100%一致
- **带转换**：往返转换误差在1像素（由于整数舍入），在实际使用中完全可以接受

#### Thinking中的坐标转换测试

```
================================================================================
示例3: Thinking中的坐标转换
================================================================================
原始thinking（相对坐标0-999）:
  我需要点击屏幕上的[500, 500]位置，这是搜索按钮的坐标。还要滑动从(300, 700)到(300, 300)。

Claude格式thinking（绝对坐标，基于1092x1092）:
  我需要点击屏幕上的[546, 546]位置，这是搜索按钮的坐标。还要滑动从(327, 765)到(327, 327)。

转换回当前格式thinking（相对坐标0-999）:
  我需要点击屏幕上的[499, 499]位置，这是搜索按钮的坐标。还要滑动从(299, 699)到(299, 299)。

================================================================================
测试: _scale_coordinates_in_text 函数
================================================================================
✓ 输入: 点击[123, 456]
  缩放: X=2.0, Y=2.0
  预期: 点击[246, 912]
  结果: 点击[246, 912]

✓ 输入: 从(100, 200)滑动到(300, 400)
  缩放: X=1.5, Y=0.5
  预期: 从(150, 100)滑动到(450, 200)
  结果: 从(150, 100)滑动到(450, 200)

✓ 输入: 坐标是 [50,100] 和 [200,300]
  缩放: X=2.0, Y=2.0
  预期: 坐标是 [100, 200] 和 [400, 600]
  结果: 坐标是 [100, 200] 和 [400, 600]

✓ 输入: 没有坐标的文本
  缩放: X=2.0, Y=2.0
  预期: 没有坐标的文本
  结果: 没有坐标的文本
```

测试表明：
- thinking中的坐标能够被正确识别和缩放
- 支持 `[x, y]` 和 `(x, y)` 两种格式，以及带/不带空格的变体
- 不包含坐标的文本保持不变

## 注意事项

1. **坐标系统差异** ⭐ **（最重要）**：
   - **当前格式**：使用**相对坐标**（0-999范围），与实际图像分辨率无关
   - **Claude格式**：使用**绝对坐标**（基于实际图像分辨率）
   - 转换时必须提供`claude_image_scale`参数才能正确转换坐标
   - 如果不提供`claude_image_scale`，坐标不会转换（可能导致错误）

2. **坐标转换公式**：
   - **相对 → 绝对**：`absolute = int(relative / 999 * image_size)`
   - **绝对 → 相对**：`relative = int(absolute / image_size * 999)`
   - 由于整数除法的舍入，往返转换可能有1-2像素的误差
   - **重要**：坐标转换不仅作用于action中的坐标，也作用于thinking文本中的坐标

3. **Thinking中的坐标转换**：
   - 支持的坐标格式：`[x, y]`、`[x,y]`、`(x, y)`、`(x,y)`
   - 示例：thinking中包含"点击[500, 500]位置"，转换后变为"点击[546, 546]位置"（基于1092x1092）
   - 坐标值范围限制：0-10000（避免误匹配其他数字对）
   - 不匹配的格式不会被转换（保持原样）

4. **往返转换精度**：
   - 不带转换：`claude_to_current(current_to_claude(x)) == x` （100%一致）
   - 带转换：由于整数舍入，可能有1-2像素误差（实际使用中可接受）
   - 示例：[500, 500] → [546, 546] → [499, 499]（1px误差）

5. **坐标字段名**：注意不同格式中坐标字段的命名差异：
   - 当前格式：`element`（单点）、`start`/`end`（滑动）
   - Claude格式：`coordinate`（单点）、`start_coordinate`/`end_coordinate`（滑动）

6. **finish操作**：finish操作在两种格式中的表示方式不同：
   - 当前格式：`finish(message="...")`
   - Claude格式：`{"type": "text", "text": "..."}`

7. **错误处理**：如果action字符串解析失败，会将其作为text类型处理，不会抛出异常。

8. **UUID生成**：每次转换都会生成新的signature和tool_use ID，不保留原始ID。

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
