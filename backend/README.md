# Claude Phone Agent Backend

后端API服务,用于处理前端请求并与Claude API交互。

## 功能特性

- RESTful API接口
- 会话管理(支持多个并发会话)
- 自动截图缩放和处理
- 上下文工程(自动管理图像数量)
- 完整的工具调用解析

## 安装

1. 安装依赖:
```bash
cd backend
pip install -r requirements.txt
```

2. 设置环境变量:
```bash
export OPENAI_API_KEY="your_api_key_here"
```

## 运行

```bash
python app.py
```

服务将在 `http://0.0.0.0:8020` 上启动。

## API 接口

### POST /api/conversation

发送消息并获取响应。

**请求体:**
```json
{
  "conversation_id": "uuid-string",
  "screenshot": "base64-encoded-image",  // 可选
  "current_package_name": "com.example.app",  // 可选
  "prompt": "用户的提示文本"  // 首次消息必需
}
```

**响应 - 工具调用:**
```json
{
  "return_type": "tool_use",
  "name": "Tap",
  "input": {
    "coordinate": [100, 200]
  }
}
```

**响应 - 文本:**
```json
{
  "return_type": "text",
  "text": "[finish] 任务已完成!",
  "stop_reason": "finish"
}
```

### DELETE /api/conversation/<conversation_id>

删除会话上下文。

### GET /api/health

健康检查接口。

## 响应格式

### return_type: "tool_use"

工具调用响应,包含要执行的操作:

- **Launch**: 启动应用
  ```json
  {"name": "Launch", "input": {"package_name": "com.xingin.xhs"}}
  ```

- **Tap**: 点击
  ```json
  {"name": "Tap", "input": {"coordinate": [100, 200]}}
  ```

- **Swipe**: 滑动
  ```json
  {"name": "Swipe", "input": {"start_coordinate": [100, 500], "end_coordinate": [100, 200]}}
  ```

- **Type**: 输入文本
  ```json
  {"name": "Type", "input": {"text": "搜索内容"}}
  ```

- **Wait**: 等待
  ```json
  {"name": "Wait", "input": {"duration": 2.0}}
  ```

- **LongPress**: 长按
  ```json
  {"name": "LongPress", "input": {"coordinate": [100, 200], "duration": 2.0}}
  ```

- **DoubleClick**: 双击
  ```json
  {"name": "DoubleClick", "input": {"coordinate": [100, 200]}}
  ```

- **Home**: 返回主屏幕
  ```json
  {"name": "Home", "input": {}}
  ```

- **Back**: 返回
  ```json
  {"name": "Back", "input": {}}
  ```

### return_type: "text"

文本响应,表示任务结束或需要用户介入:

**stop_reason 值:**
- `finish`: 任务成功完成
- `sensitive`: 检测到敏感页面(支付、密码输入等)
- `notool`: 无需工具调用,纯文本回复
- `captcha`: 检测到验证码,需要人工处理
- `verification`: 需要用户确认的敏感操作
- `toxic`: 请求违反安全策略

## 架构

```
backend/
├── app.py                    # Flask应用主文件
├── conversation_manager.py   # 会话管理模块
├── model_interface.py        # Claude API接口模块
├── requirements.txt          # Python依赖
└── README.md                # 本文档
```

## 日志

日志保存在 `logs/` 目录下,格式为 `backend_YYYYMMDDHHMMSS.log`。

## 注意事项

1. 确保设置了 `OPENAI_API_KEY` 环境变量
2. 后端自动处理截图缩放(最短边512像素)
3. 上下文自动管理,最多保留30张图片
4. 支持多个并发会话,每个会话独立管理上下文
