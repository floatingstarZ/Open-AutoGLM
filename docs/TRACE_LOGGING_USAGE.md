# Trace Logging 开启/关闭指南

本文档详细说明如何控制 trace logging 功能的开启和关闭。

## 📌 默认状态

**Trace logging 默认是开启的**，执行任务时会自动记录到 `./traces` 目录。

---

## 🔧 三种控制方式

### 1️⃣ 命令行参数（推荐）

#### ✅ 开启（默认）

```bash
# 默认开启，不需要额外参数
python main.py "打开微信"

# 或者显式指定 trace 目录
python main.py --trace-root ./my_traces "打开微信"
```

#### ❌ 关闭

```bash
# 使用 --disable-trace 参数关闭
python main.py --disable-trace "打开微信"
```

#### 📁 自定义存储目录

```bash
# 指定自定义目录
python main.py --trace-root /path/to/traces "打开微信"
```

---

### 2️⃣ 环境变量

#### ✅ 设置 Trace 目录

```bash
# Linux/MacOS
export PHONE_AGENT_TRACE_ROOT=/path/to/traces
python main.py "打开微信"

# Windows PowerShell
$env:PHONE_AGENT_TRACE_ROOT = "C:\traces"
python main.py "打开微信"

# Windows CMD
set PHONE_AGENT_TRACE_ROOT=C:\traces
python main.py "打开微信"
```

#### ❌ 关闭（需要配合命令行参数）

```bash
# 即使设置了环境变量，也可以通过命令行参数关闭
python main.py --disable-trace "打开微信"
```

---

### 3️⃣ Python API

#### ✅ 开启（默认）

```python
from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig

# 方式1：使用默认配置（已开启）
agent = PhoneAgent()
agent.run("打开微信")

# 方式2：显式开启
agent_config = AgentConfig(
    enable_trace_logging=True,  # 开启
)
agent = PhoneAgent(agent_config=agent_config)
agent.run("打开微信")

# 方式3：指定自定义目录
agent_config = AgentConfig(
    enable_trace_logging=True,
    trace_root="/path/to/traces",
)
agent = PhoneAgent(agent_config=agent_config)
agent.run("打开微信")
```

#### ❌ 关闭

```python
from phone_agent.agent import AgentConfig

agent_config = AgentConfig(
    enable_trace_logging=False,  # 关闭
)
agent = PhoneAgent(agent_config=agent_config)
agent.run("打开微信")
```

---

## 📋 完整命令示例

### 示例 1: 默认配置（开启 trace）

```bash
python main.py --base-url http://localhost:8000/v1 --model autoglm-phone-9b "打开微信"
```

**结果**：Trace 保存在 `./traces/task_xxx/`

---

### 示例 2: 关闭 trace

```bash
python main.py --disable-trace --base-url http://localhost:8000/v1 --model autoglm-phone-9b "打开微信"
```

**结果**：不记录 trace

---

### 示例 3: 自定义 trace 目录

```bash
python main.py --trace-root /data/my_traces --base-url http://localhost:8000/v1 --model autoglm-phone-9b "打开微信"
```

**结果**：Trace 保存在 `/data/my_traces/task_xxx/`

---

### 示例 4: 交互模式 + 关闭 trace

```bash
python main.py --disable-trace --base-url http://localhost:8000/v1 --model autoglm-phone-9b

# 进入交互模式后输入任务
Enter your task: 打开微信
```

---

## 🔍 查看 Trace 文件

### 默认位置

```bash
ls ./traces/
# 输出示例：
# task_a1b2c3d4/
# task_e5f6g7h8/
```

### 查看特定任务

```bash
# 查看 trace 数据
cat ./traces/task_a1b2c3d4/trace.jsonl

# 查看截图
ls ./traces/task_a1b2c3d4/*.png
```

---

## 🎯 常见使用场景

### 场景 1: 开发调试（开启 trace）

```bash
# 完整记录执行过程用于调试
python main.py --trace-root ./debug_traces "打开微信发消息"
```

### 场景 2: 性能测试（关闭 trace）

```bash
# 避免 IO 影响性能测试
python main.py --disable-trace "执行100次操作"
```

### 场景 3: 生产环境（条件性开启）

```python
import os
from phone_agent.agent import AgentConfig

# 只在遇到错误时开启 trace
enable_trace = os.getenv("DEBUG_MODE", "false").lower() == "true"

agent_config = AgentConfig(
    enable_trace_logging=enable_trace,
)
```

---

## 💡 最佳实践

### ✅ 推荐做法

1. **开发阶段**：保持开启，便于调试
   ```bash
   python main.py "your task"
   ```

2. **生产环境**：通过环境变量控制
   ```bash
   export PHONE_AGENT_TRACE_ROOT=/var/log/phone_agent_traces
   python main.py "your task"
   ```

3. **自动化测试**：关闭以提高速度
   ```bash
   python main.py --disable-trace "test task"
   ```

### ❌ 避免的做法

1. 不要在生产环境使用默认的 `./traces` 目录（可能权限不足）
2. 不要忘记定期清理旧的 trace 文件
3. 不要在性能敏感场景开启 trace

---

## 📊 参数优先级

当多种方式同时使用时，优先级如下：

```
命令行参数 > Python API 配置 > 环境变量
```

**示例**：

```bash
# 设置环境变量
export PHONE_AGENT_TRACE_ROOT=/env/traces

# 命令行参数会覆盖环境变量
python main.py --trace-root /cmd/traces "task"
# 结果：使用 /cmd/traces
```

---

## ❓ 常见问题

### Q1: 如何确认 trace 是否开启？

**A**: 查看命令行输出或检查 `./traces` 目录是否有新文件。

### Q2: trace 文件占用太多空间怎么办？

**A**: 定期清理或关闭 trace logging：

```bash
# 清理 7 天前的 trace
find ./traces -type d -mtime +7 -exec rm -rf {} +

# 或者关闭 trace
python main.py --disable-trace "task"
```

### Q3: 能否只记录失败的任务？

**A**: 当前版本不支持，但可以通过脚本实现：

```python
from phone_agent import PhoneAgent

try:
    agent = PhoneAgent()  # 开启 trace
    result = agent.run("task")

    # 如果成功，删除 trace
    if "completed" in result.lower():
        import shutil
        shutil.rmtree(f"./traces/{agent._current_task_id}")
except Exception as e:
    # 失败时保留 trace
    print(f"Task failed, trace saved for debugging")
```

---

## 📚 相关文档

- [TRACE_LOGGING.md](./TRACE_LOGGING.md) - Trace 数据格式详解
- [trace_logging_example.py](../examples/trace_logging_example.py) - 代码示例
- [README.md](../README.md) - 项目主文档
