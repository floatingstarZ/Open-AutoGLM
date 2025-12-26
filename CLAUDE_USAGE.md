# Claude 模式使用指南

## 快速开始

### 1. 设置 API Key

```bash
# 方式1: 环境变量（推荐）
export CLAUDE_API_KEY=sk-xxx

# 方式2: 命令行参数
python main.py --use-claude --claude-api-key sk-xxx "任务描述"
```

### 2. 运行任务

```bash
# 基本用法
python main.py --use-claude "打开微信"

# 交互模式
python main.py --use-claude
> Enter your task: 打开微信
> Enter your task: quit
```

## 命令行参数

### 必需参数

- `--use-claude`: 启用 Claude API 模式

### 可选参数

| 参数 | 环境变量 | 默认值 | 说明 |
|------|---------|--------|------|
| `--claude-api-key` | `CLAUDE_API_KEY` | EMPTY | Claude API 密钥 |
| `--claude-base-url` | `CLAUDE_BASE_URL` | https://api-gateway.glm.ai/v1 | API 地址 |
| `--claude-model` | `CLAUDE_MODEL` | claude-sonnet-4-20250514 | 模型名称 |
| `--claude-screenshot-width` | - | 512 | 截图缩放宽度 |

### 通用参数（同时适用于两种模式）

- `--max-steps`: 最大步数（默认：100）
- `--device-id`: 设备 ID
- `--device-type`: 设备类型（adb/hdc）
- `--lang`: 语言（cn/en）
- `--trace-root`: Trace 日志目录
- `--disable-trace`: 禁用 trace 日志
- `--quiet`: 静默模式

## 使用示例

### 示例1: 基本任务

```bash
export CLAUDE_API_KEY=sk-xxx
python main.py --use-claude "打开微信并搜索张三"
```

### 示例2: 自定义配置

```bash
python main.py \
  --use-claude \
  --claude-api-key sk-xxx \
  --claude-model claude-sonnet-4-5-20250929 \
  --claude-screenshot-width 720 \
  --max-steps 50 \
  "打开高德地图导航到北京"
```

### 示例3: 使用 HarmonyOS 设备

```bash
python main.py \
  --use-claude \
  --device-type hdc \
  --device-id xxx \
  "打开微信"
```

### 示例4: 调试模式

```bash
python main.py \
  --use-claude \
  --claude-api-key sk-xxx \
  --trace-root ./my_traces \
  "打开淘宝搜索iPhone"
```

## 输出示例

```
==================================================
Phone Agent - AI-powered phone automation
==================================================

📋 Configuration Parameters:
--------------------------------------------------
Model Configuration:
  Mode: Claude API
  Base URL: https://api-gateway.glm.ai/v1
  Model Name: claude-sonnet-4-20250514
  API Key: sk-CJc3Kj313cPY3hsg...
  Max Tokens: 16000
  Thinking Budget: 12800
  Screenshot Width: 512
  Language: cn

Agent Configuration:
  Max Steps: 100
  Language: cn
  Coordinate Mode: relative
  Screenshot Size: Original
  Verbose: True
  Enable Trace Logging: True
  Trace Root: ./traces

Device Configuration:
  Device Type: ADB
  Device ID: emulator-5554 (auto-detected)
==================================================

Task: 打开微信

📝 Trace logging enabled
   Task ID: task_20251226_1234
   Trace directory: /path/to/traces/task_20251226_1234

==================================================
💭 Calling Claude API...
--------------------------------------------------
💭 Thinking:
我需要打开微信应用...

🔧 Tool: Launch
   Input: {'app_name': '微信'}

✅ Task completed after 1 steps
📊 Trace saved: /path/to/traces/task_20251226_1234

Result: Task completed
```

## 与 OpenAI 模式对比

| 特性 | OpenAI 模式 | Claude 模式 |
|------|------------|------------|
| **API 格式** | OpenAI chat completion | Anthropic messages |
| **System Prompt** | 简洁（支持中英文） | 详细（22KB+ 安全规则） |
| **Tools** | 13个动作 | 10个工具 + TodoWrite |
| **Thinking** | 流式 `<think>` | 结构化 thinking block |
| **截图处理** | 可选缩放 | 自动缩放到512px |
| **坐标转换** | 手动或自动 | 自动（缩放 -> 真实） |
| **上下文管理** | 手动移除图片 | 自动管理（最多30张） |
| **安全特性** | 基础 | 多层防护 |

## 支持的应用（Launch 工具）

Claude 模式支持51个白名单应用：

```
微信、小红书、淘宝、高德地图、美团、大众点评、抖音、京东、携程、
bilibili、微博、快手、去哪儿、百度地图、飞书、腾讯视频、QQ音乐、
腾讯新闻、keep、汽水音乐、爱奇艺、芒果TV、红果短剧、网易云音乐、
贝壳找房、安居客、七猫免费小说、番茄免费小说、喜马拉雅、QQ邮箱、
知乎、拼多多、饿了么、淘宝闪购、京东秒送、应用宝、美柚、今日头条、
滴滴出行、优酷视频、QQ、快手极速版、肯德基、豆瓣、同花顺、支付宝、
豆包、星穹铁道、恋与深空
```

## 注意事项

### 1. API Key 安全

- 不要将 API Key 硬编码在脚本中
- 使用环境变量或安全的配置文件
- 不要将 API Key 提交到版本控制系统

### 2. 截图缩放

- Claude 模式会自动将截图缩放到指定宽度（默认512px）
- 坐标会自动转换回真实设备坐标
- 不支持 `--screenshot-size` 参数（使用 `--claude-screenshot-width` 代替）

### 3. 上下文限制

- 自动管理图片数量（最多30张）
- 超过限制时自动移除最老的图片
- 可以通过修改代码调整限制

### 4. 工具限制

- 每次响应只能使用一个工具（Claude 的 CRITICAL 要求）
- Launch 工具只支持白名单应用
- TodoWrite 工具在后端自动处理，不返回给前端

### 5. 安全特性

- 遇到 CAPTCHA 会自动停止
- 检测到敏感屏幕（黑屏）会停止
- 不会输入密码、验证码等敏感信息
- 详见 `phone_agent/config/claude_prompt.py` 中的安全规则

## 故障排查

### 问题1: API 连接失败

```
Error: Connection refused
```

**解决方案**:
- 检查 `--claude-base-url` 是否正确
- 检查网络连接
- 确认 API 服务是否可用

### 问题2: API Key 无效

```
Error: 401 Unauthorized
```

**解决方案**:
- 检查 API Key 是否正确
- 确认 API Key 有效期
- 使用 `--claude-api-key` 或设置 `CLAUDE_API_KEY` 环境变量

### 问题3: 模型不存在

```
Error: Model 'xxx' not found
```

**解决方案**:
- 检查 `--claude-model` 参数
- 确认模型名称拼写正确
- 使用默认模型：`claude-sonnet-4-20250514`

### 问题4: 设备未连接

```
❌ No devices connected
```

**解决方案**:
- 运行 `adb devices` 或 `hdc list targets` 检查设备
- 确保 USB 调试已启用
- 尝试重新连接设备

## 高级用法

### 1. 批量执行任务

```bash
#!/bin/bash
export CLAUDE_API_KEY=sk-xxx

tasks=(
  "打开微信"
  "打开淘宝搜索iPhone"
  "打开高德地图"
)

for task in "${tasks[@]}"; do
  echo "Executing: $task"
  python main.py --use-claude "$task"
  sleep 5
done
```

### 2. 自定义 Trace 分析

```bash
# 启用 trace 日志
python main.py --use-claude --trace-root ./custom_traces "打开微信"

# 分析 trace
python judge_tools/visualizer.py ./custom_traces/task_xxx
```

### 3. 多设备并行

```bash
# 设备1
python main.py --use-claude --device-id device1 "任务1" &

# 设备2
python main.py --use-claude --device-id device2 "任务2" &

wait
```

## 相关文档

- [迁移文档](CLAUDE_MIGRATION.md) - 详细的迁移说明和架构说明
- [Claude 示例](examples/claude_example.py) - 编程方式使用 Claude API
- [主 README](README.md) - 项目总体说明

## 技术支持

如遇问题，请：
1. 查看 trace 日志：`./traces/task_xxx/`
2. 检查配置参数是否正确
3. 参考故障排查章节
4. 提交 issue 到项目仓库
