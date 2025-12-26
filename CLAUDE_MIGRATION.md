# Claude 迁移文档

本文档说明如何使用迁移后的 Claude 功能。

## 迁移内容概览

从 `claude-for-phone/backend` 迁移了以下内容：

### 1. Claude API 客户端
- **文件**: `phone_agent/model/client_claude.py`
- **功能**:
  - ClaudeModelClient: Claude API 调用
  - 截图自动缩放（默认512px宽度）
  - 坐标自动转换（缩放 -> 真实）
  - ClaudeMessageBuilder: 消息构建工具

### 2. System Prompt 和 Tools
- **文件**:
  - `phone_agent/config/claude_prompt.py` - Claude 专用 system prompt（22KB+安全规则）
  - `phone_agent/config/claude_tools.py` - Claude 工具定义（10个工具 + TodoWrite）

### 3. 上下文管理
- **文件**: `phone_agent/context_manager.py`
- **功能**:
  - 自动管理图片数量（默认最多30张）
  - 移除最老的图片
  - 支持 OpenAI 和 Claude 两种格式

### 4. 架构调整
- **agent.py**: 移除 `run()` 函数，只保留 `step()` 函数，接收外部 context
- **main.py**: 新增 `run_task()` 函数，负责上下文管理和 trace logging

## 使用方式

### 方式1: 使用现有 OpenAI 兼容模型（默认）

```bash
python main.py "打开微信"
```

这种方式使用原有的 OpenAI 兼容 API（例如 autoglm-phone-9b）。

### 方式2: 使用 Claude API（命令行模式）✨ 新增

```bash
# 基本用法
python main.py --use-claude --claude-api-key sk-xxx "打开微信"

# 使用环境变量
export CLAUDE_API_KEY=sk-xxx
python main.py --use-claude "打开微信"

# 完整参数
python main.py \
  --use-claude \
  --claude-api-key sk-xxx \
  --claude-base-url https://api-gateway.glm.ai/v1 \
  --claude-model claude-sonnet-4-20250514 \
  --claude-screenshot-width 512 \
  "打开微信"

# 交互模式
python main.py --use-claude --claude-api-key sk-xxx
```

#### Claude 模式参数说明

- `--use-claude`: 启用 Claude API 模式
- `--claude-api-key`: Claude API 密钥（或使用 `CLAUDE_API_KEY` 环境变量）
- `--claude-base-url`: API 地址（默认：https://api-gateway.glm.ai/v1）
- `--claude-model`: 模型名称（默认：claude-sonnet-4-20250514）
- `--claude-screenshot-width`: 截图缩放宽度（默认：512px）

### 方式3: 使用 Claude API（编程模式）

参考 `examples/claude_example.py`:

```python
from phone_agent.model.client_claude import (
    ClaudeModelClient,
    ClaudeModelConfig,
    ClaudeMessageBuilder
)
from phone_agent.config.claude_prompt import get_claude_system_prompt
from phone_agent.config.claude_tools import CLAUDE_TOOLS

# 创建 Claude 客户端
claude_config = ClaudeModelConfig(
    api_key="your-api-key",
    base_url="https://api-gateway.glm.ai/v1",
    model_name="claude-sonnet-4-20250514"
)
client = ClaudeModelClient(claude_config)

# 调用 API
response = client.request(
    messages=context,
    system_prompt=get_claude_system_prompt(),
    tools=CLAUDE_TOOLS
)
```

## 核心差异

### OpenAI 兼容模式 vs Claude 模式

| 特性 | OpenAI 兼容模式 | Claude 模式 |
|------|----------------|------------|
| **API 格式** | OpenAI chat completion | Anthropic messages API |
| **System Prompt** | 简洁的中英文 prompt | 22KB+ 安全规则 prompt |
| **Tools** | 13个动作（含 Take_over, Call_API） | 10个工具（含 TodoWrite） |
| **Thinking** | 流式输出 `<think>` | 结构化 thinking block |
| **坐标** | 直接使用或转换 | 自动缩放到512px并转换 |
| **上下文** | 手动管理图片 | 自动管理（最多30张） |

## 文件结构

```
phone_agent/
├── model/
│   ├── client.py              # OpenAI 兼容客户端
│   └── client_claude.py       # Claude API 客户端 ✨ 新增
├── config/
│   ├── prompts.py            # OpenAI 兼容 prompts
│   ├── claude_prompt.py      # Claude system prompt ✨ 新增
│   └── claude_tools.py       # Claude tools 定义 ✨ 新增
├── context_manager.py        # 上下文管理器 ✨ 新增
└── agent.py                  # 简化的 PhoneAgent ✨ 修改

main.py                       # 添加 run_task() ✨ 修改
examples/
└── claude_example.py         # Claude 使用示例 ✨ 新增
```

## 快速开始

### OpenAI 兼容模式（默认）

```bash
# 使用默认的 OpenAI 兼容 API
python main.py --base-url http://localhost:8000/v1 --model autoglm-phone-9b "打开微信"
```

### Claude 模式

```bash
# 设置环境变量
export CLAUDE_API_KEY=sk-xxx

# 运行任务
python main.py --use-claude "打开微信"
```

## Claude Tools 列表

1. **Tap** - 点击屏幕
2. **LongPress** - 长按（0.5-10秒）
3. **DoubleClick** - 双击
4. **Launch** - 启动应用（51个白名单应用）
5. **Swipe** - 滑动手势
6. **Back** - 返回键
7. **Home** - Home键
8. **Type** - 文本输入（自动清空）
9. **Wait** - 等待（0.5-30秒）
10. **TodoWrite** - 任务管理（内部工具，不返回前端）

## 白名单应用

Claude Launch 工具支持51个中文应用，包括：
微信、小红书、淘宝、高德地图、美团、大众点评、抖音、bilibili、微博、快手、京东、携程、百度地图、飞书、腾讯视频、QQ音乐、keep、爱奇艺等。

完整列表见 `phone_agent/config/claude_tools.py` 中的 `APP_NAME_TO_PACKAGE` 字典。

## 安全特性

Claude system prompt 包含多层安全防护：

1. **注入防御层**: 防止屏幕内容注入恶意指令
2. **消息防御**: 防止消息内容伪装成指令
3. **元安全指令**: 规则不可变，不受任何输入修改
4. **社会工程防御**: 识别并拒绝操控性语言
5. **用户隐私保护**: 禁止输入密码、验证码等敏感信息
6. **CAPTCHA 检测**: 遇到验证码立即停止并通知用户

## 注意事项

1. **坐标转换**: Claude 模式自动将图片缩放到512px宽度，坐标会自动转换回真实屏幕坐标
2. **上下文工程**: 超过30张图片时自动移除最老的图片
3. **TodoWrite**: Claude 的 TodoWrite 工具在后端自动处理，不返回给前端
4. **单步执行**: 每次响应只能使用一个工具（CRITICAL 要求）

## Trace 格式兼容

迁移后的系统完全兼容现有的 trace 格式转换工具，可以使用 `judge_tools/judge_convert_claude_format.py` 进行格式转换。

## 技术支持

如有问题，请参考：
- `examples/claude_example.py` - 完整示例
- `phone_agent/model/client_claude.py` - 客户端实现
- `phone_agent/config/claude_prompt.py` - System prompt 详情
