# Judge Tools - 模型输出评估工具

这个工具集用于评估GUIAgent模型的输出是否合理，并提供可视化界面查看评估结果。

## 文件说明

- `judge.py` - 主要评估脚本，调用大模型对trace进行判断
- `judge_convert.py` - 对 convert_format 转换后的内容进行 judge（支持 trace.jsonl 格式）
- `judge_base.py` - 基础工具（如果存在）
- `visualizer.py` - 可视化工具，生成HTML页面展示评估结果
- `convert_format.py` - 格式转换工具，实现当前格式 <-> Claude格式的双向转换

## 快速开始

### 0. 评估 convert 后的 trace（推荐用于完整任务评估）

`judge_convert.py` 用于评估整个任务的执行轨迹，它会：
1. 读取 trace.jsonl 文件，收集所有步骤的对话历史
2. 将当前格式转换为 Claude 格式（使用 convert_format.py）
3. 将图片路径转换为 base64
4. 调用 LLM 对整个任务进行判断

**批量评估所有任务：**
```bash
python judge_tools/judge_convert.py --batch
```

**评估单个任务：**
```bash
python judge_tools/judge_convert.py --test task_20251224_1447
```

**自定义输入输出目录：**
```bash
python judge_tools/judge_convert.py --batch --input ./traces --output ./judge_results
```

**使用多个 worker 并行处理：**
```bash
python judge_tools/judge_convert.py --batch --workers 5
```

**限制处理数量（用于测试）：**
```bash
python judge_tools/judge_convert.py --batch --limit 10
```

评估结果会保存为 JSON 文件，包含：
- `task_id`: 任务ID
- `is_pass`: 是否通过（model_score >= 60）
- `model_score`: 模型评分 (0-100)
- `model_confidence`: 置信度 (0-100)
- `verdict`: 是否完成用户需求
- `scores`: 三个维度的评分
- `failed_steps`: 失败步骤列表
- `repair_suggestions`: 修复建议

### 1. 评估单个步骤

```bash
python judge_tools/judge.py <trace_file_path> [step_index]
```

示例：
```bash
python judge_tools/judge.py traces/task_a550d5b1/trace.jsonl 6
```

这会：
1. 读取指定步骤的数据
2. 调用judge模型进行评估
3. 保存原始输入输出到 `traces/task_xxx/judge_io_step_6.json`
4. 打印评估结果

### 2. 可视化评估结果

生成HTML文件：
```bash
python judge_tools/visualizer.py traces/task_xxx/judge_io_step_6.json --html
```

启动Web服务器查看：
```bash
python judge_tools/visualizer.py traces/task_xxx/judge_io_step_6.json --serve --port 8000
```

浏览器会自动打开，显示：
- 📊 统计信息（消息数、图片数、Token使用）
- ⚙️ System Prompt
- 💬 完整对话历史（包括图片）
- ✅ Judge评估结果（verdict、scores、loop_detected等）
- 📝 原始LLM响应

### 3. 批量处理整个trace目录

```bash
# 查找所有judge_io文件
python judge_tools/visualizer.py traces/task_xxx/ --all --html

# 启动服务查看第一个
python judge_tools/visualizer.py traces/task_xxx/ --serve
```

## Judge评估准则

Judge模型会根据以下准则评估GUIAgent的输出：

### 1. Thinking合理性
- thinking是否与当前屏幕状态相符
- 推理过程是否逻辑清晰、前后一致
- thinking的结论是否与action一致

### 2. 死循环检测（CRITICAL）
- 检查是否有3次或更多次重复相同或相似的动作
- 包括：
  - 完全相同的action类型和参数
  - 在相同屏幕状态下重复操作
  - 交替执行无进展的动作

### 3. 动作预测合理性
- action是否符合当前屏幕状态
- 参数是否有效（如坐标范围）
- action是否有助于完成任务

### 4. 上下文一致性
- 当前步骤是否与之前步骤形成合理的执行链
- 是否有明显的逻辑跳跃或矛盾

### 5. 格式正确性
- 输出格式是否符合要求
- JSON格式是否正确

## Judge输出字段说明

```json
{
  "verdict": false,              // 是否合理（布尔值）
  "loop_detected": true,         // 是否检测到死循环
  "scores": {
    "requirement_satisfaction": 60,  // 需求满足度 (0-100)
    "reasoning_correctness": 50,     // 推理正确性 (0-100)
    "conciseness": 75                // 简洁性 (0-100)
  },
  "model_score": 55,             // 模型评分 (0-100)
  "model_confidence": 80,        // 置信度 (0-100)
  "correct_action": "{...}",     // 正确动作建议（JSON字符串）
  "failed_steps": [...],         // 失败步骤列表
  "repair_suggestions": "..."    // 修复建议文本
}
```

## 配置

### 修改默认配置

编辑 `judge.py` 文件中的配置：

```python
DEFAULT_API_KEY = "your-api-key"
DEFAULT_BASE_URL = "https://api-gateway.glm.ai/v1"
DEFAULT_MODEL_NAME = "doubao-1.5-thinking-pro-vision-250415"
```

### 调整历史图片数量

默认会为最近5个步骤的user message添加截图。可以通过参数调整：

```python
result = judge_model_output(
    model_input=model_input,
    screenshot_path=screenshot_path,
    format_model_output=format_model_output,
    trace_file_path=trace_file,
    history_images_k=3,  # 只加载最近3个步骤的截图
)
```

## 可视化界面功能

1. **交互式图片查看** - 点击图片可全屏查看
2. **进度条显示** - 各项评分以进度条形式展示
3. **循环检测标记** - 如果检测到死循环会有⚠️标记
4. **失败步骤高亮** - 失败的步骤会以黄色背景显示
5. **响应式设计** - 支持手机、平板、桌面浏览

## 故障排除

### 图片无法显示
- 检查judge_io.json中的图片数据是否是base64格式
- 确保图片数据以 `data:image/png;base64,` 开头

### 无法启动Web服务
- 检查端口是否被占用，尝试其他端口：`--port 8001`
- 确保有读取HTML文件的权限

### Judge评估结果不准确
- 检查history_images_k参数，确保加载了足够的历史截图
- 查看System Prompt是否正确嵌入
- 检查模型是否支持vision功能

## 示例工作流

```bash
# 1. 运行agent生成trace
python your_agent_script.py

# 2. 评估最后一个步骤（假设是step 10）
python judge_tools/judge.py traces/task_xxx/trace.jsonl 10

# 3. 可视化评估结果
python judge_tools/visualizer.py traces/task_xxx/judge_io_step_10.json --serve

# 4. 浏览器自动打开，查看详细评估结果
```

## 高级用法

### 保存到自定义路径

```python
result = judge_model_output(
    ...,
    save_io=True,
    save_io_path="/custom/path/judge_result.json"
)
```

### 禁用自动保存

```python
result = judge_model_output(
    ...,
    save_io=False
)
```

### 自定义HTML输出

```bash
python judge_tools/visualizer.py input.json --html -o custom_name.html
```

## 贡献

如果发现问题或有改进建议，请提交issue或PR。
