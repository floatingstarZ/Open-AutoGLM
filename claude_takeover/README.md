# Claude Takeover Module

Claude Takeover 模块允许你在**不启动后端服务**的情况下，直接使用 Claude API 进行手机自动化。

## 特性

- ✅ **无需后端服务**：直接调用 Claude API，不依赖 backend/app.py
- ✅ **支持已有上下文**：可以从已有的对话上下文继续推理
- ✅ **简化的日志**：只保存本地文件，去掉了 MongoDB 依赖
- ✅ **支持 Android (ADB)** 和 **HarmonyOS (HDC)**
- ✅ **参考 phone_agent 风格**：代码结构清晰，易于理解

## 目录结构

```
claude_takeover/
├── __init__.py          # 模块初始化
├── model_client.py      # Claude API 客户端（简化版，无 MongoDB）
├── system_prompt.py     # 系统提示词
├── tools.py             # 工具定义
├── adb_takeover.py      # Android (ADB) 接管代理
├── hdc_takeover.py      # HarmonyOS (HDC) 接管代理
└── README.md            # 本文档
```

## 使用方法

### 1. Android 设备 (ADB)

#### 从头开始新任务

```bash
python -m claude_takeover.adb_takeover --task "打开淘宝，搜索手机"
```

#### 从已有上下文继续

```bash
# 假设你有一个 context.json 文件（从 backend 保存的上下文）
python -m claude_takeover.adb_takeover --context context.json
```

#### 自定义配置

```bash
python -m claude_takeover.adb_takeover \
    --task "打开美团外卖" \
    --max-iterations 50 \
    --api-key "your-api-key" \
    --model "claude-sonnet-4-5-20250929" \
    --target-width 512
```

### 2. HarmonyOS 设备 (HDC)

#### 从头开始新任务

```bash
python -m claude_takeover.hdc_takeover --task "打开美团外卖，搜索附近美食"
```

#### 从已有上下文继续

```bash
python -m claude_takeover.hdc_takeover --context context.json
```

#### 指定设备（多设备场景）

```bash
python -m claude_takeover.hdc_takeover \
    --task "打开小红书，搜索旅行攻略" \
    --device-id "192.168.1.100:5555"
```

### 3. 在 Python 代码中使用

```python
from claude_takeover import ADBTakeover, HDCTakeover

# Android 设备
adb_agent = ADBTakeover(
    context=[],  # 空列表表示从头开始，或传入已有上下文
    api_key="your-api-key",
    model="claude-sonnet-4-5-20250929",
    max_iterations=100
)
result = adb_agent.run(task="打开淘宝，搜索手机")
print(f"结果: {result}")

# HarmonyOS 设备
hdc_agent = HDCTakeover(
    context=[],
    api_key="your-api-key",
    device_id=None,  # None 表示自动检测
    max_iterations=100
)
result = hdc_agent.run(task="打开美团外卖，搜索附近美食")
print(f"结果: {result}")
```

## 参数说明

### ADBTakeover / HDCTakeover

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context` | List[Dict] | `[]` | 已有对话上下文（可选） |
| `api_key` | str | 环境变量 | Claude API Key |
| `model` | str | `claude-sonnet-4-5-20250929` | 模型名称 |
| `target_width` | int | `512` | 截图缩放宽度 |
| `max_iterations` | int | `100` | 最大迭代次数 |
| `device_id` | str | `None` | 设备 ID（仅 HDC，None 表示自动检测） |
| `trace_dir` | str | `traces/` | Trace 保存目录 |

### 命令行参数

```
--task TEXT              任务描述（从头开始时使用）
--context PATH           上下文文件路径（JSON格式）
--api-key TEXT           Claude API key
--model TEXT             模型名称
--max-iterations INT     最大迭代次数
--target-width INT       截图缩放宽度
--device-id TEXT         设备ID（仅HDC）
--trace-dir PATH         Trace保存目录
```

## 与原 mock_app 的区别

| 功能 | 原 mock_app.py | claude_takeover |
|------|----------------|-----------------|
| **后端依赖** | 需要启动 backend/app.py | ❌ 不需要 |
| **调用方式** | HTTP 请求到后端 | ✅ 直接调用 Claude API |
| **上下文管理** | 后端管理 | ✅ 本地管理，可传入已有上下文 |
| **日志保存** | MongoDB + 本地 | ✅ 仅本地文件（简化） |
| **代码风格** | 独立脚本 | ✅ 模块化，参考 phone_agent |

## 上下文格式

上下文是一个 JSON 数组，每个元素是一条消息：

```json
[
  {
    "role": "user",
    "content": [
      {"type": "text", "text": "打开淘宝"},
      {"type": "image", "source": {...}}
    ]
  },
  {
    "role": "assistant",
    "content": [
      {"type": "thinking", "thinking": "我需要..."},
      {"type": "tool_use", "name": "Launch", "input": {...}}
    ]
  }
]
```

## 环境变量

```bash
# 设置 API Key（可选，也可通过命令行参数指定）
export OPENAI_API_KEY="your-api-key"
```

## 注意事项

1. **ADB/HDC 连接**：确保设备已通过 ADB 或 HDC 连接
2. **API Key**：确保设置了有效的 Claude API Key
3. **上下文文件**：如果从已有上下文继续，确保 context.json 格式正确
4. **设备权限**：确保 ADB/HDC 有足够的权限执行操作

## 示例：从 backend 保存的上下文继续

如果你之前使用 backend 进行了一些操作，并想继续：

1. 从 backend 的 `full_logs/` 目录找到最新的日志文件
2. 提取其中的 `context` 部分保存为 `context.json`
3. 运行：

```bash
python -m claude_takeover.adb_takeover --context context.json
```

或者在代码中：

```python
import json
from claude_takeover import ADBTakeover

# 加载上下文
with open('context.json', 'r') as f:
    context = json.load(f)

# 创建代理并继续
agent = ADBTakeover(context=context)
result = agent.run()  # 不需要 task，因为已有上下文
```

## 故障排除

### 1. 导入错误

```
❌ 无法导入 HDC 模块
```

**解决方案**：确保在 `Open-AutoGLM` 目录中运行，或将其添加到 PYTHONPATH：

```bash
export PYTHONPATH=/path/to/Open-AutoGLM:$PYTHONPATH
```

### 2. 设备未连接

```
❌ 未检测到设备
```

**解决方案**：
- Android: 运行 `adb devices` 检查连接
- HarmonyOS: 运行 `hdc list targets` 检查连接

### 3. API 调用失败

```
❌ 模型调用失败
```

**解决方案**：
- 检查 API Key 是否正确
- 检查网络连接
- 检查 API URL 是否可访问

## 许可证

与 Open-AutoGLM 主项目保持一致
