# Trace Logging

Phone Agent 提供了完整的 trace logging 功能，用于记录 agent 执行过程中的每一步操作和截图，便于调试、分析和复现。

## 功能特点

- **自动记录**：每次任务执行自动记录所有步骤
- **完整截图**：保存每一步的屏幕截图
- **详细信息**：记录模型输入/输出、思考过程、执行动作等
- **结构化存储**：使用 JSON Lines 格式，便于解析和分析
- **可选启用**：可以随时启用或禁用 trace logging

## 快速开始

### 启用 Trace Logging

```python
from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

# 配置 agent 并启用 trace logging
agent_config = AgentConfig(
    enable_trace_logging=True,  # 启用 trace logging
    trace_root="./traces",      # 可选：指定 trace 存储目录
)

agent = PhoneAgent(agent_config=agent_config)

# 执行任务 - trace 会自动记录
result = agent.run("打开微信发消息给张三")
```

### 查看 Trace 文件

执行后，trace 文件会保存在以下结构中：

```
traces/
  task_a1b2c3d4/              # 任务 ID
    trace.jsonl               # Trace 数据（JSON Lines 格式）
    step_1.png                # 第 1 步截图
    step_2.png                # 第 2 步截图
    step_3.png                # 第 3 步截图
    ...
```

## Trace 数据格式

### trace.jsonl 文件

Trace 文件使用 JSON Lines 格式，每行是一个 JSON 对象。包含以下类型的记录：

#### 1. 任务开始 (task_start)

```json
{
  "type": "task_start",
  "task_id": "task_a1b2c3d4",
  "task_description": "打开微信发消息给张三",
  "timestamp": "2025-12-19T10:30:00.123456"
}
```

#### 2. 执行步骤 (step)

```json
{
  "type": "step",
  "task_id": "task_a1b2c3d4",
  "step_index": 1,
  "timestamp": "2025-12-19T10:30:01.234567",
  "screenshot_path": "task_a1b2c3d4/step_1.png",
  "current_app": "com.tencent.mm",
  "screen_size": {
    "width": 1080,
    "height": 2400
  },
  "model_input": [
    {
      "role": "system",
      "content": "..."
    },
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "打开微信发消息给张三"
        },
        {
          "type": "image",
          "placeholder": "<image_removed_from_trace>"
        }
      ]
    }
  ],
  "model_output": "do(action=\"Launch\", app=\"微信\")",
  "thinking": "用户想要打开微信并发送消息，首先需要启动微信应用...",
  "action": {
    "_metadata": "do",
    "action": "Launch",
    "app": "微信"
  }
}
```

#### 3. 任务结束 (task_end)

```json
{
  "type": "task_end",
  "task_id": "task_a1b2c3d4",
  "timestamp": "2025-12-19T10:30:15.345678",
  "total_steps": 5,
  "result": "消息发送成功",
  "success": true
}
```

## 配置选项

### AgentConfig 参数

- `enable_trace_logging` (bool): 是否启用 trace logging，默认为 `True`
- `trace_root` (str): Trace 文件存储根目录，默认为 `"./traces"`

### 示例

```python
# 禁用 trace logging
agent_config = AgentConfig(
    enable_trace_logging=False,
)

# 自定义 trace 目录
agent_config = AgentConfig(
    enable_trace_logging=True,
    trace_root="/data/phone_agent_traces",
)
```

## 解析 Trace 文件

### 读取 trace.jsonl

```python
import json

def read_trace(trace_file):
    """读取并解析 trace 文件"""
    with open(trace_file, 'r', encoding='utf-8') as f:
        for line in f:
            record = json.loads(line)

            if record['type'] == 'task_start':
                print(f"任务: {record['task_description']}")

            elif record['type'] == 'step':
                print(f"步骤 {record['step_index']}:")
                print(f"  动作: {record['action']}")
                print(f"  截图: {record['screenshot_path']}")

            elif record['type'] == 'task_end':
                print(f"结果: {record['result']}")
                print(f"成功: {record['success']}")
                print(f"总步骤: {record['total_steps']}")

# 使用示例
read_trace("traces/task_a1b2c3d4/trace.jsonl")
```

### 查看截图

```python
from PIL import Image

def view_screenshots(task_dir):
    """查看任务的所有截图"""
    import glob

    screenshots = sorted(glob.glob(f"{task_dir}/step_*.png"))

    for screenshot in screenshots:
        img = Image.open(screenshot)
        img.show()
        print(f"显示截图: {screenshot}")

# 使用示例
view_screenshots("traces/task_a1b2c3d4")
```

## 最佳实践

### 1. 开发和调试时启用

在开发和调试阶段，建议启用 trace logging：

```python
agent_config = AgentConfig(
    enable_trace_logging=True,
    verbose=True,  # 同时启用详细输出
)
```

### 2. 生产环境选择性启用

在生产环境中，可以根据需要启用或禁用：

```python
import os

agent_config = AgentConfig(
    # 通过环境变量控制
    enable_trace_logging=os.getenv("ENABLE_TRACE", "false").lower() == "true",
)
```

### 3. 定期清理 Trace 文件

Trace 文件可能会占用大量磁盘空间，建议定期清理：

```bash
# 删除 7 天前的 trace 文件
find ./traces -type d -mtime +7 -exec rm -rf {} +
```

### 4. 分析失败的任务

当任务失败时，trace 文件可以帮助分析原因：

```python
import json

def analyze_failed_task(trace_file):
    """分析失败任务的 trace"""
    with open(trace_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

        # 读取最后一行（任务结束记录）
        end_record = json.loads(lines[-1])

        if not end_record.get('success', True):
            print(f"任务失败: {end_record.get('result')}")

            # 打印所有步骤
            for line in lines[1:-1]:  # 跳过开始和结束
                step = json.loads(line)
                if step['type'] == 'step':
                    print(f"步骤 {step['step_index']}: {step['action']}")
```

## 常见问题

### Q: Trace 文件占用太多空间怎么办？

A: 可以考虑以下方案：
1. 定期清理旧的 trace 文件
2. 只在需要时启用 trace logging
3. 使用压缩存储（手动压缩旧 trace 目录）

### Q: 如何禁用截图保存但保留 trace 数据？

A: 当前版本暂不支持此功能，但可以通过修改 `trace_logger.py` 中的 `log_step` 方法实现。

### Q: Trace 文件可以上传到远程存储吗？

A: 可以。在 `TraceLogger` 中添加自定义逻辑，将文件上传到 S3、OSS 等对象存储服务。

## 参考

- [trace_logging_example.py](../examples/trace_logging_example.py) - 完整使用示例
- [trace_logger.py](../phone_agent/trace_logger.py) - 源代码实现
