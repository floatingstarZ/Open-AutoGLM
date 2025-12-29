# convert_format.py 修复总结

## 修复的问题

### 1. ✅ 工具名称不一致（严重问题）

**问题**：工具名称与 Claude API 实际要求不匹配

**修复前**：
- `"Long Press"` ❌
- `"Double Tap"` ❌

**修复后**：
- `"LongPress"` ✅
- `"DoubleClick"` ✅

**修复位置**：
- `_parse_assistant_to_claude()` line 782-793
- `_parse_claude_to_assistant()` line 866-886
- `_scale_action_coordinates()` line 327

### 2. ✅ LongPress 缺少 duration 字段（严重问题）

**问题**：LongPress 工具缺少必填的 `duration` 字段

**修复前**：
```python
if action_type in ["Tap", "Long Press", "Double Tap"]:
    tool_input["coordinate"] = action["element"]
    # ❌ 缺少 duration
```

**修复后**：
```python
elif action_type in ["Long Press", "LongPress"]:
    action_type = "LongPress"
    tool_input["coordinate"] = action["element"]
    tool_input["duration"] = action.get("duration", 2.0)  # ✅ 添加 duration
```

**修复位置**：
- `_parse_assistant_to_claude()` line 782-788
- `_parse_claude_to_assistant()` line 866-877

### 3. ✅ 缺少 tool_result 消息支持（严重问题）

**问题**：完全缺少 `tool_result` 消息类型的处理

**影响**：
- Current → Claude：生成的消息无法被 Claude API 接受
- Claude → Current：tool_result 无法正确转换

**修复后**：
- `current_to_claude()`: 自动检测并生成 tool_result 消息（line 401-437）
- `claude_to_current()`: 正确提取 tool_result 内容（line 516-560）

**核心逻辑**：
```python
# 检查前一条是否是 assistant 的 tool_use
if 前一条是 tool_use:
    # 当前 user 消息应该是 tool_result
    claude_messages.append({
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": converted_content
        }]
    })
```

### 4. ✅ image 块格式验证（新增功能）

**新增函数**：
- `_ensure_image_format_claude()`: 确保 image 块符合 Claude 格式（line 71-111）
- `_ensure_image_format_current()`: 确保 image 块符合 Current 格式（line 114-144）

**功能**：自动转换 image 块格式
```python
# 转换前
{"type": "image", "data": "..."}

# 转换后（Claude 格式）
{
    "type": "image",
    "source": {
        "type": "base64",
        "media_type": "image/png",
        "data": "..."
    }
}
```

### 5. ✅ Screenshot dimensions 更新（新增功能）

**新增函数**：
- `_update_screenshot_dimensions()`: 更新 system-reminder 中的截图尺寸（line 147-189）

**功能**：坐标缩放时同步更新截图尺寸信息
```python
# 转换前
"<system-reminder>Screenshot dimensions: (1000x1000, png)</system-reminder>"

# 转换后（缩放到 1092x1092）
"<system-reminder>Screenshot dimensions: (1092x1092, png)</system-reminder>"
```

## 测试结果

运行 `test_convert_format.py`，所有测试通过 ✅

### 测试 1: 工具名称和 duration 字段
- ✅ Tap 工具正确转换
- ✅ LongPress 工具正确转换，包含 duration 字段
- ✅ DoubleClick 工具正确转换

### 测试 2: tool_result 消息生成
- ✅ tool_result 消息正确生成
- ✅ tool_use_id 正确关联

### 测试 3: 往返转换一致性
- ✅ Current → Claude → Current 转换一致
- ✅ duration 字段正确保留
- ✅ 坐标误差在 1-2 像素范围内（符合预期）

## 修复的文件

- `judge_tools/convert_format.py`: 主要修复文件
- `judge_tools/test_convert_format.py`: 新增测试文件
- `judge_tools/CONVERT_FORMAT_FIXES.md`: 本文档

## 向后兼容性

所有修复都保持向后兼容：
- 支持旧的工具名称（"Long Press", "Double Tap"）
- 自动转换为新的工具名称（"LongPress", "DoubleClick"）
- 如果缺少 duration，使用默认值 2.0 秒

## 使用建议

### 1. Current → Claude（用于调用 Claude API）

```python
from convert_format import current_to_claude

# 转换消息
claude_messages = current_to_claude(
    messages=current_messages,
    claude_image_scale=[1092, 1092]  # Claude 推理时的图像分辨率
)

# 调用 Claude API
response = claude_api.call(messages=claude_messages)
```

### 2. Claude → Current（用于保存或评估）

```python
from convert_format import claude_to_current

# 转换消息
current_messages = claude_to_current(
    messages=claude_messages,
    claude_image_scale=[1092, 1092]  # 原始图像分辨率
)

# 保存或用于后续处理
save_to_file(current_messages)
```

## 注意事项

1. **坐标缩放**：转换时会自动处理坐标缩放，从相对坐标（0-1000）转换到绝对坐标
2. **tool_result 自动识别**：不需要手动标记 tool_result，会自动根据上下文判断
3. **image 格式**：会自动确保 image 块符合 Claude API 格式要求
4. **Screenshot dimensions**：会随坐标缩放自动更新

## 相关文件

- 实际 Claude 格式参考：`claude_takeover/model_client.py`
- 工具定义：`claude_takeover/tools.py`
- 系统提示词：`claude_takeover/system_prompt.py`
