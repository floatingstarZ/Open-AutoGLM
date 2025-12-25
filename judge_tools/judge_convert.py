"""
judge_convert.py - 对 convert_format 转换后的内容进行 judge

功能：
- 读取 convert 后的 trace 数据（Claude 格式）
- 将图片路径转换为 base64
- 调用 LLM 进行判断
- 保存结果

Usage:
python judge_convert.py --batch                           # 批量判断所有任务
python judge_convert.py --test <task_id>                   # 测试单个任务
python judge_convert.py --batch --workers 5                # 使用 5 个 worker
"""

import json
import base64
import os
import sys
import argparse
import traceback
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from copy import deepcopy
from PIL import Image
import io
import requests

# 导入当前项目的模块
from judge_tools.system_prompt import get_system_prompt
from judge_tools.tools import TOOLS
from judge_tools.convert_format import current_to_claude, claude_to_current

# ====================== Configuration ======================
# Input/Output directories
INPUT_DIR = "./traces"  # trace 文件目录
OUTPUT_DIR = "./judge_convert_results"  # judge 结果输出目录

# API 配置
API_KEY = "sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn"
BASE_URL = "https://api-gateway.glm.ai/v1/chat/completions"
MODEL_NAME = "claude-sonnet-4-5-20250929"

headers = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "interleaved-thinking-2025-05-14"
}

# Processing configuration
DEFAULT_MAX_WORKERS = 10
MAX_RETRIES = 3
RETRY_DELAY = 5

# Judge tool definition
JUDGE_TOOL = {
    "name": "Judge",
    "description": "返回模型执行的审计与判定结果",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "boolean",
                "description": "判断是否完成用户需求"
            },
            "scores": {
                "type": "object",
                "properties": {
                    "requirement_satisfaction": {"type": "integer", "minimum": 0, "maximum": 100},
                    "reasoning_correctness": {"type": "integer", "minimum": 0, "maximum": 100},
                    "conciseness": {"type": "integer", "minimum": 0, "maximum": 100}
                },
                "required": ["requirement_satisfaction", "reasoning_correctness", "conciseness"]
            },
            "failed_steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "string"},
                        "snippet": {"type": "string"},
                        "why_failed": {"type": "string"}
                    },
                    "required": ["step_id", "snippet", "why_failed"]
                }
            },
            "model_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "模型对轨迹质量的判断分数 (0-100整数)，表示该轨迹满足用户需求的程度"
            },
            "model_confidence": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "判定的置信度 (0-100整数)"
            },
            "repair_suggestions": {
                "type": "string",
                "description": "可直接用于下一次修正的修复建议文本"
            }
        },
        "required": ["verdict", "scores", "failed_steps", "model_score", "model_confidence", "repair_suggestions"]
    }
}

JUDGE_PROMPT = """你是一个专注于模型执行审计与判定的智能体。
任务：基于已有的execution_trace（模型执行记录）判断该次执行是否**完成了用户需求**，**必须使用Judge工具返回结构化的判定结果**。
Judge工具会根据审计结果，更新数据库，从而提升模型性能。

--- 输入说明 ---
- execution_trace: 之后进行的一系列对话都是模型之前执行的轨迹结果。
- 轨迹生产的system_prompt:
<system_prompt>
{trace_system_prompt}
</system_prompt>

--- 工具使用要求（重要） ---
**你必须使用Judge工具来返回审计结果，不要直接输出JSON文本！**
- 使用Judge工具时，需要提供以下参数：
  - verdict: 布尔值，判断是否完成用户需求
  - scores: 包含三个评分维度的对象 (requirement_satisfaction, reasoning_correctness, conciseness)，均为0-100整数
  - failed_steps: 失败步骤数组，每个步骤包含 step_id, snippet, why_failed
  - model_score: 模型对轨迹质量的判断分数 (0-100整数)，表示该轨迹满足用户需求的程度
  - model_confidence: 判定的置信度 (0-100整数)
  - repair_suggestions: 修复建议文本

--- 参数说明 ---
- verdict: 布尔值，true 或 false（小写，不是字符串）
- scores: 三个分值均为整数，取值区间 [0, 100]
  - requirement_satisfaction: 需求满足度 (0-100整数)
  - reasoning_correctness: 推理正确性 (0-100整数)
  - conciseness: 简洁性 (0-100整数)
- failed_steps: 数组；如果没有发现失败步骤，请返回空数组 []。每个元素必须包含：
  - step_id: 步骤标识
  - snippet: 步骤内容片段（不超过 200 字符）
  - why_failed: 失败原因说明
- model_score: 模型对轨迹质量的判断分数，取值区间 [0, 100] 整数
- model_confidence: 对本次判定的置信度，取值区间 [0, 100] 整数
- repair_suggestions: 必须是一段连续文字（至少 2-4 句），描述可直接用于下一次执行的具体、可操作修正策略

--- 评估原则（采用宽松和鼓励性标准） ---
**请采用宽松和实用的评估标准，重点评估模型是否朝着正确方向努力并提供有价值的结果。**
- 理解用户需求的本质，认可模型对需求的合理解读
- 充分考虑实际操作环境中的各种限制因素
- 鼓励模型在困难情况下做出的合理判断和有价值的尝试
- 重点关注"是否有助于用户解决问题"而不是"是否完美无缺"
- 只要模型提供了实质性的帮助或进展，就应给予积极评价

--- 立即执行 ---
现在，请基于你收到的 execution_trace 进行评估，使用Judge工具返回结构化结果。
"""

# ====================== Utility Functions ======================

# Correct signature format (如果需要替换 signature)
CORRECT_SIGNATURE = "EsEFCkgICBABGAIqQHXsKD1/aUKireB3UwhOwuCPMO7dmIoxh1ebYpil96SIhSDY6+FfLgdzDl+CrVtcvP0e1e4vvx8ZyKd6TBs+AY8SDHzUlsaACVPxpgj7uxoMnKabk2ORGarMQpFJIjBbV913unZ02CX31UFlR6AapRSwirJHaZ2utecTy6cX1upcntsH5ecbOu3NPUKy/pkqpgTOmOSSymCKrvg4UUXAeyL552KTWtrtYLbQE+6D42zg9lGEt1e52TM3j+fibsWBIss/8QlvBWSZaO0AgqHlp0TKKJni0Lq/sGwNUtvbc8TolZq/gsfRm1E+uxeCxCaIxzhqLo1t1I0SLhFDtMT5CXtgJ2wY+WUssr5laC1RFCuOvDoWjQYfLhCZ2gYyDMaewEnSdLxbbWt4kPjUeXS0x89zVeA2WUp4A/BL3jttJoV7MzL2EJJnsiEEy9UGAPHHUr3yFZfJ3U1Kmw5M3v8NJ4DgcTevfUHFfJUx52wfpUAyi/oZtXXT6w5g+2zAgzuTAUlyuZzi20fKemwpqzSOQRXnWgIvXW8Z3Wj4OqVBBx1zJIoeFBWpgTARt3cBN62NjYnC8TWmaxYU/JoTNH9zUH0+e1AMyrjfUnlkkT+45aGsATEfxn+wGNRJJTd9vAdPGrevf+4pKQzxAkeLnJy5k3hZbz1AKDVkV9CO4OyhQKeNhg8B3cTFAZ3MkbvQr0lb0Hlta4BTDQxBGELYAtM8p2lf3Poy8WrGqj6I/6y8lfyKCtto0LKn8jUAn/MHQkQZW7J+eUdoIVYtxWqad6RLVYm1PXJygoXyl/v8W2CrJ9jEqy5Ruj3Md5pw+sd7wqkRkmsxrSUm4eiiImZtFpJYrxdsGqjAnj/iBfqcQqxVtwQmNXI5fh3jHwNWCCdtlO1dBwpRBK0BWv5Dxpo4+kQMelSWHWnqx4ApGAE="


def replace_signature_in_messages(messages):
    """
    Replace all signature fields in messages with the correct format
    
    Args:
        messages: List of message dictionaries
        
    Returns:
        Messages with corrected signatures
    """
    messages = deepcopy(messages)
    
    for message in messages:
        if not isinstance(message, dict) or "content" not in message:
            continue
            
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
            
        for content_item in content:
            if isinstance(content_item, dict) and "signature" in content_item:
                content_item["signature"] = CORRECT_SIGNATURE
    
    return messages


def load_image_as_base64(image_path, scaled_width=None, scaled_height=None):
    """
    Load image, scale if needed, and convert to base64
    
    Args:
        image_path: Path to image file
        scaled_width: Target width for scaling (None = no scaling)
        scaled_height: Target height for scaling (None = no scaling)
    
    Returns:
        Base64 encoded image string
    """
    try:
        # 如果是相对路径，尝试从 traces 目录查找
        if not os.path.isabs(image_path):
            possible_paths = [
                image_path,
                os.path.join("traces", image_path),
                os.path.join(os.getcwd(), "traces", image_path),
            ]
            found = False
            for path in possible_paths:
                if os.path.exists(path):
                    image_path = path
                    found = True
                    break
            if not found:
                raise FileNotFoundError(f"Image file not found: {image_path}")
        
        with Image.open(image_path) as img:
            # Convert to RGB mode if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Scale image if scaling parameters are provided
            if scaled_width is not None and scaled_height is not None and scaled_width > 0 and scaled_height > 0:
                img = img.resize((scaled_width, scaled_height), Image.LANCZOS)

            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            b64_code = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return b64_code
    except Exception as e:
        print(f"[ERROR] Failed to load image {image_path}: {e}")
        return None


def convert_file_paths_to_base64(trace_data, task_dir, scaled_width=None, scaled_height=None):
    """
    Convert file paths in trace to base64 image data, with optional scaling

    Args:
        trace_data: Data from trace.json or trace.jsonl
        task_dir: Absolute path of task directory
        scaled_width: Target width for scaling images (from metadata)
        scaled_height: Target height for scaling images (from metadata)

    Returns:
        Converted trace data
    """
    trace_data = deepcopy(trace_data)
    context = trace_data.get("context", [])

    for message in context:
        if message.get("role") != "user":
            continue

        for content in message.get("content", []):
            if not isinstance(content, dict):
                continue

            # Process direct images
            if content.get("type") == "image":
                source = content.get("source", {})
                if source.get("type") == "file":
                    rel_path = source.get("path", "")
                    # 处理相对路径：如果路径包含 task_id，需要从 traces 根目录查找
                    if os.path.isabs(rel_path):
                        abs_path = rel_path
                    elif "/" in rel_path or "\\" in rel_path:
                        # 路径包含目录分隔符，可能是 "task_xxx/step_1.png" 格式
                        # 从 traces 根目录查找
                        traces_root = os.path.dirname(task_dir) if task_dir else "traces"
                        abs_path = os.path.join(traces_root, rel_path)
                    else:
                        # 只是文件名，在 task_dir 中查找
                        abs_path = os.path.join(task_dir, rel_path)

                    b64_data = load_image_as_base64(abs_path, scaled_width, scaled_height)
                    if b64_data:
                        content["source"] = {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64_data
                        }

            # Process images in tool_result
            elif content.get("type") == "tool_result":
                for item in content.get("content", []):
                    if isinstance(item, dict) and item.get("type") == "image":
                        source = item.get("source", {})
                        if source.get("type") == "file":
                            rel_path = source.get("path", "")
                            abs_path = os.path.join(task_dir, rel_path)

                            b64_data = load_image_as_base64(abs_path, scaled_width, scaled_height)
                            if b64_data:
                                item["source"] = {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64_data
                                }

    return trace_data


def call_llm_judge(trace_messages, max_retries=MAX_RETRIES):
    """Call LLM to judge"""
    # 获取 system prompt
    trace_system_prompt = get_system_prompt()  # 使用迁移过来的 system prompt
    judge_prompt = JUDGE_PROMPT.format(trace_system_prompt=trace_system_prompt)

    # Replace signature format in messages
    trace_messages = replace_signature_in_messages(trace_messages)

    # Add judge request message
    judge_user_message = {
        "role": "user",
        "content": [{
            "type": "text",
            "text": "模型已经执行完毕，请使用并只使用Judge工具给出详尽的审计与判定结果，禁止使用其他工具进行输出。"
        }]
    }
    trace_messages.append(judge_user_message)

    # Build tool list (包含所有工具 + Judge 工具)
    judge_tools = deepcopy(TOOLS)
    judge_tools.append(JUDGE_TOOL)

    # Build request
    data = {
        "max_tokens": 26000,
        "system": judge_prompt,
        "messages": trace_messages,
        "thinking": {
            "type": "enabled",
            "budget_tokens": 12800
        },
        "tools": judge_tools,
        "model": MODEL_NAME
    }

    # Retry mechanism
    for attempt in range(max_retries):
        try:
            response = requests.post(
                url=BASE_URL,
                headers=headers,
                json=data,
                timeout=(60, 600)
            )
            print(f"[RESPONSE] {response}")

            if response.ok:
                return response.json()
            else:
                print(f"[RETRY {attempt + 1}/{max_retries}] API request failed: {response.status_code}")
                traceback.print_exc()
                if attempt < max_retries - 1:
                    import time
                    time.sleep(RETRY_DELAY)

        except Exception as e:
            print(f"[RETRY {attempt + 1}/{max_retries}] Request exception: {e}")
            traceback.print_exc()
            if attempt < max_retries - 1:
                import time
                time.sleep(RETRY_DELAY)

    raise Exception("LLM call failed after max retries")


def extract_judge_result(llm_response):
    """Extract judge result from LLM response"""
    if 'content' in llm_response:
        for content_item in llm_response['content']:
            if content_item.get('type') == 'tool_use' and content_item.get('name') == 'Judge':
                return content_item.get('input', {})
    
    # 尝试从 choices 中提取
    if 'choices' in llm_response and len(llm_response['choices']) > 0:
        message = llm_response['choices'][0].get('message', {})
        if 'content' in message:
            for content_item in message['content']:
                if isinstance(content_item, dict) and content_item.get('type') == 'tool_use' and content_item.get('name') == 'Judge':
                    return content_item.get('input', {})
    
    print(f"[ERROR] Cannot extract Judge result from response: {llm_response}")
    raise ValueError("Cannot extract Judge result from response")


def load_trace_data(trace_file_path):
    """
    加载 trace 数据，支持 trace.json 和 trace.jsonl 格式
    
    对于 trace.jsonl，会收集所有步骤的对话历史，构建完整的 context
    
    Args:
        trace_file_path: trace 文件路径
        
    Returns:
        trace 数据字典，包含 context 字段（Claude 格式的消息列表）
    """
    if not os.path.exists(trace_file_path):
        raise FileNotFoundError(f"Trace file not found: {trace_file_path}")
    
    if trace_file_path.endswith('.jsonl'):
        # 读取 jsonl 格式，收集所有步骤的对话历史
        all_messages = []
        metadata = {}
        screen_size = None
        
        with open(trace_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    step_data = json.loads(line)
                    step_type = step_data.get("type")
                    
                    if step_type == "task_start":
                        # 保存任务描述
                        if "task_description" not in metadata:
                            metadata["task_description"] = step_data.get("task_description", "")
                    
                    elif step_type == "step":
                        # 获取屏幕尺寸用于坐标转换
                        screen_info = step_data.get("screen_size", {})
                        if screen_info and not screen_size:
                            screen_size = [screen_info.get("width", 1000), screen_info.get("height", 1000)]
                        
                        # 获取 format_model_output（assistant 的回复）
                        format_output = step_data.get("format_model_output", {})
                        
                        # 获取 model_input（当前格式的对话历史）
                        model_input = step_data.get("model_input", [])
                        
                        # 获取截图路径
                        screenshot_path = step_data.get("screenshot_path", "")
                        
                        # 构建当前步骤的消息
                        # 策略：只添加新的 user 和 assistant 消息
                        # 由于 model_input 包含完整历史，我们只需要最后一个 user 消息和对应的 assistant 消息
                        
                        if model_input:
                            # 找到最后一个 user 消息
                            last_user_msg = None
                            for msg in reversed(model_input):
                                if msg.get("role") == "user":
                                    last_user_msg = msg
                                    break
                            
                            if last_user_msg:
                                # 复制 user 消息内容
                                user_content = deepcopy(last_user_msg.get("content", []))
                                
                                # 添加截图路径（如果需要）
                                if screenshot_path and isinstance(user_content, list):
                                    # 检查是否已经有图片
                                    has_image = False
                                    for item in user_content:
                                        if isinstance(item, dict) and item.get("type") == "image":
                                            has_image = True
                                            break
                                    
                                    if not has_image:
                                        # 添加图片路径（稍后会转换为 base64）
                                        user_content.append({
                                            "type": "image",
                                            "source": {
                                                "type": "file",
                                                "path": screenshot_path
                                            }
                                        })
                                
                                # 添加 user 消息
                                all_messages.append({
                                    "role": "user",
                                    "content": user_content
                                })
                        
                        # 添加 assistant 消息
                        if format_output and format_output.get("role") == "assistant":
                            all_messages.append(format_output)
        
        # 构建返回数据
        result = {
            "context": all_messages,
            "metadata": metadata
        }
        
        if screen_size:
            result["metadata"]["scaled_screen_width"] = screen_size[0]
            result["metadata"]["scaled_screen_height"] = screen_size[1]
        
        return result
    else:
        # 读取 json 格式（期望包含 context 字段）
        with open(trace_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 如果已经是 convert 后的格式（包含 context），直接返回
            if "context" in data:
                return data
            # 否则尝试转换
            raise ValueError("trace.json format not supported. Please use trace.jsonl or convert to Claude format first.")


def judge_single_task(task_id, input_dir=INPUT_DIR, output_dir=OUTPUT_DIR):
    """
    Judge a single task

    Args:
        task_id: Task ID
        input_dir: trace 文件目录
        output_dir: judge 结果输出目录

    Returns:
        Judge result dictionary
    """
    try:
        # Read trace file
        task_dir = os.path.join(input_dir, task_id)
        
        # 尝试读取 trace.json 或 trace.jsonl
        trace_file = None
        for filename in ['trace.json', 'trace.jsonl']:
            candidate = os.path.join(task_dir, filename)
            if os.path.exists(candidate):
                trace_file = candidate
                break
        
        if trace_file is None:
            raise FileNotFoundError(f"Trace file not found in {task_dir}")

        # 加载 trace 数据
        trace_data = load_trace_data(trace_file)
        
        # 检查数据格式
        if "context" not in trace_data:
            raise ValueError(f"Trace data format not supported: missing 'context' field")

        # Get scaling parameters from metadata
        metadata = trace_data.get("metadata", {})
        scaled_screen_width = metadata.get("scaled_screen_width", None)
        scaled_screen_height = metadata.get("scaled_screen_height", None)
        
        if scaled_screen_width and scaled_screen_height:
            print(f"[INFO] Using scaling parameters from metadata: {scaled_screen_width}x{scaled_screen_height}")
        else:
            print(f"[WARNING] Missing scaled_screen_width or scaled_screen_height in metadata. Images will not be scaled.")
            # 使用默认值
            scaled_screen_width = 1000
            scaled_screen_height = 1000

        # 获取 context（当前格式的消息列表）
        current_messages = trace_data.get("context", [])
        
        # 将当前格式转换为 Claude 格式（用于 judge）
        # 注意：convert_format 需要图像分辨率用于坐标转换
        claude_image_scale = [scaled_screen_width, scaled_screen_height]
        trace_messages = current_to_claude(current_messages, claude_image_scale=claude_image_scale)
        
        # Convert file paths to base64 (with scaling if metadata available)
        # 注意：这里需要处理 Claude 格式中的图片路径
        trace_data_claude = {
            "context": trace_messages,
            "metadata": metadata
        }
        trace_data_claude = convert_file_paths_to_base64(trace_data_claude, task_dir, scaled_screen_width, scaled_screen_height)
        
        # 更新 trace_messages（包含转换后的 base64 图片）
        trace_messages = trace_data_claude.get("context", [])

        # Call LLM to judge
        llm_response = call_llm_judge(trace_messages)

        # Extract judge result
        judge_result = extract_judge_result(llm_response)

        # Format output
        model_score = judge_result.get('model_score', 0)
        is_pass = model_score >= 60

        result = {
            "task_id": task_id,
            "is_pass": is_pass,
            "model_score": model_score,
            "model_confidence": judge_result.get('model_confidence', 0),
            "verdict": judge_result.get('verdict', False),
            "scores": judge_result.get('scores', {}),
            "failed_steps": judge_result.get('failed_steps', []),
            "repair_suggestions": judge_result.get('repair_suggestions', ''),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "original_response": llm_response
        }

        # Save result
        os.makedirs(output_dir, exist_ok=True)
        result_file = os.path.join(output_dir, f"{task_id}.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"[SUCCESS] {task_id} - score: {model_score}, pass: {is_pass}")
        return result

    except Exception as e:
        print(f"[ERROR] {task_id} - {str(e)}")
        traceback.print_exc()

        # Save error result
        error_result = {
            "task_id": task_id,
            "is_pass": False,
            "model_score": 0,
            "error": str(e),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        os.makedirs(output_dir, exist_ok=True)
        result_file = os.path.join(output_dir, f"{task_id}.json")
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)

        return error_result


def get_all_task_ids(input_dir=INPUT_DIR):
    """Get all task_ids"""
    if not os.path.exists(input_dir):
        return []

    task_ids = []
    for item in os.listdir(input_dir):
        item_path = os.path.join(input_dir, item)
        
        # 检查是否有 trace.json 或 trace.jsonl
        trace_file = None
        for filename in ['trace.json', 'trace.jsonl']:
            candidate = os.path.join(item_path, filename)
            if os.path.exists(candidate):
                trace_file = candidate
                break

        if os.path.isdir(item_path) and trace_file:
            task_ids.append(item)

    return task_ids


def batch_judge(input_dir=INPUT_DIR, output_dir=OUTPUT_DIR,
                max_workers=DEFAULT_MAX_WORKERS, limit=None):
    """
    Batch judge all tasks

    Args:
        input_dir: trace 文件目录
        output_dir: judge 结果输出目录
        max_workers: Maximum parallel workers
        limit: Maximum number of tasks to process
    """
    # Get all task_ids
    task_ids = get_all_task_ids(input_dir)

    if not task_ids:
        print("No tasks found")
        return

    print(f"Found {len(task_ids)} tasks")

    if limit:
        task_ids = task_ids[:limit]
        print(f"Limiting to first {limit} tasks")

    # Statistics
    success_count = 0
    failed_count = 0
    total_score = 0

    # Parallel processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(judge_single_task, task_id, input_dir, output_dir): task_id
            for task_id in task_ids
        }

        with tqdm(total=len(task_ids), desc="Judge progress") as pbar:
            for future in as_completed(future_to_task):
                task_id = future_to_task[future]
                try:
                    result = future.result()

                    if result.get("is_pass"):
                        success_count += 1
                    else:
                        failed_count += 1

                    total_score += result.get("model_score", 0)

                except Exception as e:
                    print(f"[ERROR] Exception processing task {task_id}: {e}")
                    failed_count += 1

                pbar.update(1)

    # Print statistics
    print("\n" + "="*60)
    print("Judge completed")
    print("="*60)
    print(f"Total tasks: {len(task_ids)}")
    print(f"Passed: {success_count}")
    print(f"Failed: {failed_count}")
    if task_ids:
        avg_score = total_score / len(task_ids)
        print(f"Average score: {avg_score:.2f}")
    print("="*60 + "\n")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Judge traces after convert_format conversion",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Function mode
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--batch', '-b', action='store_true', help='Batch judge all tasks')
    mode_group.add_argument('--test', '-t', type=str, metavar='TASK_ID', help='Test single task')

    # Optional parameters
    parser.add_argument('--input', type=str, default=INPUT_DIR,
                       help=f'trace file directory (default: {INPUT_DIR})')
    parser.add_argument('--output', type=str, default=OUTPUT_DIR,
                       help=f'judge result output directory (default: {OUTPUT_DIR})')
    parser.add_argument('--workers', '-w', type=int, default=DEFAULT_MAX_WORKERS,
                       help=f'Number of parallel workers (default: {DEFAULT_MAX_WORKERS})')
    parser.add_argument('--limit', type=int, help='Maximum number of tasks to process')

    args = parser.parse_args()

    try:
        if args.test:
            # Single test
            print(f"Testing task: {args.test}")
            judge_single_task(args.test, args.input, args.output)
            print("Test completed")

        elif args.batch:
            # Batch processing
            print("Starting batch judge")
            batch_judge(args.input, args.output, args.workers, args.limit)

    except KeyboardInterrupt:
        print("\nUser interrupted")
    except Exception as e:
        print(f"[ERROR] Program exception: {e}")
        traceback.print_exc()


if __name__ == '__main__':
    main()

