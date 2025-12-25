# convert_format.py 使用说明

## 概述

`convert_format.py` 是一个用于在Claude API格式和当前模型输出格式之间进行转换的工具。

## 格式差异

### 当前格式 (Current Format)

```json
[
  {
    "role": "system",
    "content": "系统提示词..."
  },
  {
    "role": "user",
    "content": [
      {"type": "text", "text": "任务描述"}
    ]
  },
  {
    "role": "assistant",
    "content": "<think>思考过程</think><answer>do(action=\"Tap\", element=[500, 500])</answer>"
  }
]
```

**特点：**
- 包含system消息
- user消息的content是列表
- assistant消息的content是字符串，格式为 `<think>...</think><answer>...</answer>`
- 使用相对坐标 (0-999)

### Claude格式 (Claude Format)

```json
[
  {
    "role": "user",
    "content": [
      {"type": "text", "text": "任务描述"},
      {
        "type": "image",
        "source": {
          "type": "base64",
          "media_type": "image/png",
          "data": "iVBORw0KGgo..."
        }
      }
    ]
  },
  {
    "role": "assistant",
    "content": [
      {
        "type": "thinking",
        "thinking": "思考过程",
        "signature": "base64编码的签名..."
      },
      {
        "type": "tool_use",
        "id": "toolu_bdrk_...",
        "name": "Tap",
        "input": {"coordinate": [542, 1207]}
      }
    ]
  }
]
```

**特点：**
- 通常不包含system消息（通过API单独传递）
- user消息可能包含多个text块和image块
- assistant消息的content是列表，包含thinking和tool_use块
- 使用绝对坐标（基于实际图像分辨率）

## 主要功能

### 1. current_to_claude

将当前格式转换为Claude格式。

```python
from judge_tools.convert_format import current_to_claude

claude_messages = current_to_claude(
    messages,
    claude_image_scale=[1084, 2412]  # Claude推理时的图像分辨率
)
```

**参数：**
- `messages`: 当前格式的消息列表
- `claude_image_scale`: 可选，Claude图像分辨率 [width, height]，用于坐标缩放

### 2. claude_to_current

将Claude格式转换为当前格式。

```python
from judge_tools.convert_format import claude_to_current

current_messages = claude_to_current(
    messages,
    claude_image_scale=[1084, 2412]  # Claude推理时的图像分辨率
)
```

**参数：**
- `messages`: Claude格式的消息列表
- `claude_image_scale`: 可选，Claude图像分辨率 [width, height]，用于坐标缩放

## 坐标转换

### 原理

- **当前格式**使用相对坐标 (0-999)，与屏幕实际分辨率无关
- **Claude格式**使用绝对坐标，基于实际图像分辨率

### 转换公式

```python
# Current -> Claude (相对坐标 -> 绝对坐标)
scale_x = claude_width / 999.0
scale_y = claude_height / 999.0
absolute_x = int(relative_x * scale_x)
absolute_y = int(relative_y * scale_y)

# Claude -> Current (绝对坐标 -> 相对坐标)
scale_x = 999.0 / claude_width
scale_y = 999.0 / claude_height
relative_x = int(absolute_x * scale_x)
relative_y = int(absolute_y * scale_y)
```

### 精度说明

由于浮点数舍入，往返转换可能产生 **1-2像素** 的误差，这是正常现象且在可接受范围内。

**示例：**
```
原始: [500, 500]
-> Claude (1084x2412): [542, 1207]
-> Current: [499, 499]
误差: 1像素
```

## 使用示例

### 示例1: 基本转换

```python
from judge_tools.convert_format import current_to_claude, claude_to_current

# 当前格式的消息
current_messages = [
    {
        "role": "system",
        "content": "你是一个智能助手"
    },
    {
        "role": "user",
        "content": [{"type": "text", "text": "打开抖音"}]
    },
    {
        "role": "assistant",
        "content": "<think>需要打开抖音</think><answer>do(action=\"Launch\", app=\"抖音\")</answer>"
    }
]

# 转换为Claude格式
claude_messages = current_to_claude(current_messages)

# 转换回当前格式
back_to_current = claude_to_current(claude_messages)
```

### 示例2: 带坐标缩放

```python
from judge_tools.convert_format import current_to_claude, claude_to_current

# 当前格式（相对坐标0-999）
current_messages = [
    {
        "role": "assistant",
        "content": "<think>点击搜索</think><answer>do(action=\"Tap\", element=[500, 500])</answer>"
    }
]

# 转换为Claude格式（绝对坐标）
claude_messages = current_to_claude(
    current_messages,
    claude_image_scale=[1084, 2412]
)

# 结果: coordinate=[542, 1207]

# 转换回当前格式（相对坐标）
back_to_current = claude_to_current(
    claude_messages,
    claude_image_scale=[1084, 2412]
)

# 结果: element=[499, 499] (有1像素误差)
```

### 示例3: 处理真实数据

```python
import json
from judge_tools.convert_format import claude_to_current

# 加载Claude格式数据
with open('claude_log.json', 'r') as f:
    claude_messages = json.load(f)

# 转换为当前格式
current_messages = claude_to_current(
    claude_messages,
    claude_image_scale=[1084, 2412]
)

# 保存转换后的数据
with open('current_format.json', 'w') as f:
    json.dump(current_messages, f, ensure_ascii=False, indent=2)
```

## 支持的操作类型

### 坐标操作
- **Tap**: `element=[x,y]` ↔ `coordinate=[x,y]`
- **Long Press**: `element=[x,y]` ↔ `coordinate=[x,y]`
- **Double Tap**: `element=[x,y]` ↔ `coordinate=[x,y]`
- **Swipe**: `start=[x1,y1], end=[x2,y2]` ↔ `start_coordinate=[x1,y1], end_coordinate=[x2,y2]`

### 其他操作
- **Launch**: `app="xxx"`
- **Type**: `text="xxx"`
- **Wait**: `duration="x seconds"`
- **Back**: 无参数
- **Home**: 无参数
- **finish**: 转换为text块

## 注意事项

1. **System消息处理**
   - Claude格式通常不包含system消息
   - 转换时会保留system消息，但实际使用Claude API时可能需要单独处理

2. **图像块处理**
   - user消息中的image块会被保留
   - image使用source字段（type、media_type、data）

3. **Thinking签名**
   - thinking块的signature是base64编码的随机字节
   - 每次转换会生成新的signature

4. **坐标精度**
   - 往返转换可能有1-2像素误差
   - 误差在可接受范围内

## 测试

运行测试示例：

```bash
python example_convert.py
```

## 参考文件

- `/Users/huangziyue/CodeGeeXProjects/claude-for-phone/full_logs/20251224142941.json` - Claude格式示例
- `/Users/huangziyue/Open-AutoGLM/traces/task_20251224_1447/trace.jsonl` - 当前格式示例
