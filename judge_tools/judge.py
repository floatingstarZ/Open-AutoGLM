"""
评估GUIAgent模型输出的合理性

参考 step3_judge_trace.py 的实现，对GUIAgent模型的输出进行评估。
"""

import json
import base64
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
from PIL import Image
import io

from openai import OpenAI


# ====================== Configuration ======================
# 默认配置
DEFAULT_API_KEY = "sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn"
DEFAULT_BASE_URL = "https://api-gateway.glm.ai/v1"
DEFAULT_MODEL_NAME = "doubao-1.5-thinking-pro-vision-250415"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5

# Judge工具定义
JUDGE_TOOL = {
    "name": "Judge",
    "description": "返回模型执行的审计与判定结果",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "boolean",
                "description": "判断输出是否合理"
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
                "description": "模型对输出质量的判断分数 (0-100整数)，表示该输出满足用户需求的程度"
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

JUDGE_PROMPT_TEMPLATE = """你是一个专注于模型执行审计与判定的智能体。
任务：基于GUIAgent模型的输入和输出，判断该次输出是否**合理**，**必须使用Judge工具返回结构化的判定结果**。

--- GUIAgent模型的System Prompt ---
以下是GUIAgent模型在生成输出时所遵循的system prompt，你需要根据这些规则来评估模型的输出是否符合要求：

<system_prompt>
{trace_system_prompt}
</system_prompt>

--- 输入说明 ---
- model_input: GUIAgent模型的文本输入（对话历史，不包含system prompt，只包含user和assistant消息）
- screenshot_path: GUIAgent模型的图像输入路径（当前屏幕截图）
- format_model_output: 模型输出的格式化后的输出（assistant的回复）

--- Judge工具定义 ---
工具名称: Judge
描述: 返回模型执行的审计与判定结果

输入参数:
- verdict (boolean): 判断输出是否合理
- scores (object): 包含三个评分维度的对象
  - requirement_satisfaction (integer, 0-100): 需求满足度 - 输出是否满足用户需求
  - reasoning_correctness (integer, 0-100): 推理正确性 - 思考过程是否合理
  - conciseness (integer, 0-100): 简洁性 - 输出是否简洁明了
- failed_steps (array): 失败步骤数组，如果没有发现失败步骤，请返回空数组 []。每个元素必须包含：
  - step_id (string): 步骤标识（如 "thinking" 或 "action"）
  - snippet (string): 步骤内容片段（不超过 200 字符）
  - why_failed (string): 失败原因说明
- model_score (integer, 0-100): 模型对输出质量的判断分数，表示该输出满足用户需求的程度
- model_confidence (integer, 0-100): 判定的置信度
- repair_suggestions (string): 修复建议文本，必须是一段连续文字（至少 2-4 句），描述可直接用于下一次执行的具体、可操作修正策略

必需参数: verdict, scores, failed_steps, model_score, model_confidence, repair_suggestions

--- 输出格式要求（重要） ---
**你必须严格按照以下JSON格式输出Judge工具的结果，不要添加任何其他文本或说明！**

输出格式：
```json
{{
  "name": "Judge",
  "arguments": {{
    "verdict": true,
    "scores": {{
      "requirement_satisfaction": 85,
      "reasoning_correctness": 80,
      "conciseness": 75
    }},
    "failed_steps": [],
    "model_score": 80,
    "model_confidence": 85,
    "repair_suggestions": "修复建议文本..."
  }}
}}
```

注意：
- 必须输出有效的JSON格式
- verdict必须是布尔值（true或false，小写）
- scores中的三个分值必须是0-100之间的整数
- failed_steps必须是数组，如果没有失败步骤则返回空数组[]
- model_score和model_confidence必须是0-100之间的整数
- repair_suggestions必须是字符串

--- 评估原则（采用宽松和鼓励性标准） ---
**请采用宽松和实用的评估标准，重点评估模型是否朝着正确方向努力并提供有价值的结果。**
- 理解用户需求的本质，认可模型对需求的合理解读
- 充分考虑实际操作环境中的各种限制因素
- 鼓励模型在困难情况下做出的合理判断和有价值的尝试
- 重点关注"是否有助于用户解决问题"而不是"是否完美无缺"
- 只要模型提供了实质性的帮助或进展，就应给予积极评价

--- 评估要点 ---
1. **格式正确性**: 检查输出是否符合system prompt中要求的格式（<think>...</think><answer>...</answer>）
2. **动作合理性**: 检查action是否符合当前屏幕状态和用户需求，是否符合system prompt中定义的操作指令格式
3. **推理逻辑**: 检查thinking部分是否提供了合理的推理过程
4. **坐标有效性**: 如果包含坐标，检查坐标是否在合理范围内
5. **上下文一致性**: 检查输出是否与对话历史一致
6. **规则遵循性**: 检查输出是否遵循system prompt中定义的操作指令和规则

--- 立即执行 ---
现在，请基于你收到的 model_input、screenshot 和 format_model_output 进行评估，严格按照上述JSON格式输出Judge工具的结果。
"""


# ====================== Utility Functions ======================

def load_image_as_base64(image_path: str, scaled_width: Optional[int] = None, scaled_height: Optional[int] = None) -> Optional[str]:
    """
    加载图片，可选缩放，并转换为base64
    
    Args:
        image_path: 图片文件路径
        scaled_width: 目标宽度（None = 不缩放）
        scaled_height: 目标高度（None = 不缩放）
    
    Returns:
        Base64编码的图片字符串
    """
    try:
        # 如果是相对路径，尝试从traces目录查找
        if not os.path.isabs(image_path):
            # 尝试从当前工作目录或traces目录查找
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
            # 转换为RGB模式（如果需要）
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # 缩放图片（如果提供了缩放参数）
            if scaled_width is not None and scaled_height is not None and scaled_width > 0 and scaled_height > 0:
                img = img.resize((scaled_width, scaled_height), Image.LANCZOS)

            # 转换为base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            b64_code = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return b64_code
    except Exception as e:
        print(f"[ERROR] Failed to load image {image_path}: {e}")
        return None


def extract_system_prompt(model_input: list[dict[str, Any]]) -> str:
    """
    从model_input中提取system prompt
    
    Args:
        model_input: GUIAgent模型的输入（对话历史）
    
    Returns:
        system prompt字符串，如果没有找到则返回空字符串
    """
    for msg in model_input:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            return content if isinstance(content, str) else str(content)
    return ""


def convert_model_input_to_openai_format(model_input: list[dict[str, Any]], screenshot_base64: Optional[str] = None, exclude_system: bool = True) -> list[dict[str, Any]]:
    """
    将model_input转换为OpenAI格式的消息列表
    
    Args:
        model_input: GUIAgent模型的输入（对话历史）
        screenshot_base64: 截图的base64编码（可选）
        exclude_system: 是否排除system消息（默认True，因为system prompt会嵌入到judge prompt中）
    
    Returns:
        OpenAI格式的消息列表
    """
    openai_messages = []
    
    for i, msg in enumerate(model_input):
        role = msg.get("role")
        content = msg.get("content", "")
        is_last_user = (role == "user" and i == len(model_input) - 1)
        
        # 跳过system消息（如果exclude_system为True）
        if role == "system" and exclude_system:
            continue
        
        # 处理system消息（如果exclude_system为False）
        if role == "system":
            openai_messages.append({
                "role": "system",
                "content": content if isinstance(content, str) else str(content)
            })
        
        # 处理user消息
        elif role == "user":
            if isinstance(content, list):
                # 列表格式，可能包含图片
                converted_content = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            converted_content.append({
                                "type": "text",
                                "text": item.get("text", "")
                            })
                        elif item.get("type") == "image_url":
                            # 已经是image_url格式
                            converted_content.append(item)
                        elif item.get("type") == "image":
                            # 处理image类型（可能包含base64数据）
                            image_data = item.get("image", "")
                            if image_data.startswith("data:"):
                                url = image_data
                            else:
                                url = f"data:image/png;base64,{image_data}"
                            converted_content.append({
                                "type": "image_url",
                                "image_url": {"url": url}
                            })
                    else:
                        converted_content.append({"type": "text", "text": str(item)})
                
                # 如果提供了screenshot_base64，添加到最后一个user消息
                if screenshot_base64 and is_last_user:
                    converted_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}"
                        }
                    })
                
                openai_messages.append({
                    "role": "user",
                    "content": converted_content
                })
            else:
                # 字符串格式
                content_list = [{"type": "text", "text": str(content)}]
                if screenshot_base64 and is_last_user:
                    content_list.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}"
                        }
                    })
                openai_messages.append({
                    "role": "user",
                    "content": content_list
                })
        
        # 处理assistant消息
        elif role == "assistant":
            openai_messages.append({
                "role": "assistant",
                "content": content if isinstance(content, str) else str(content)
            })
    
    return openai_messages


def extract_judge_result(llm_response: dict[str, Any]) -> dict[str, Any]:
    """
    从LLM响应中提取Judge结果
    
    期望的JSON格式：
    {
      "name": "Judge",
      "arguments": {
        "verdict": true,
        "scores": {...},
        ...
      }
    }
    
    Args:
        llm_response: LLM的响应字典
    
    Returns:
        Judge结果字典（arguments部分）
    """
    if 'choices' in llm_response and len(llm_response['choices']) > 0:
        message = llm_response['choices'][0].get('message', {})
        content = message.get('content', '')
        
        if not content:
            raise ValueError("Empty response content")
        
        # 尝试解析JSON格式的结果
        import re
        
        # 方法1: 尝试提取完整的JSON对象（包含name和arguments）
        json_match = re.search(r'\{[^{}]*"name"[^{}]*"Judge"[^{}]*"arguments"[^{}]*\{[^}]*\}[^}]*\}', content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(0))
                if isinstance(result, dict) and result.get('name') == 'Judge' and 'arguments' in result:
                    return result['arguments']
            except json.JSONDecodeError:
                pass
        
        # 方法2: 尝试提取arguments部分的JSON
        json_match = re.search(r'"arguments"\s*:\s*(\{[^}]*(?:\{[^}]*\}[^}]*)*\})', content, re.DOTALL)
        if json_match:
            try:
                arguments_str = json_match.group(1)
                return json.loads(arguments_str)
            except json.JSONDecodeError:
                pass
        
        # 方法3: 尝试提取包含verdict的JSON对象
        json_match = re.search(r'\{[^{}]*"verdict"[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(0))
                # 验证是否包含必需的字段
                if 'verdict' in result and 'scores' in result:
                    return result
            except json.JSONDecodeError:
                pass
        
        # 方法4: 尝试提取代码块中的JSON
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                if isinstance(result, dict) and result.get('name') == 'Judge' and 'arguments' in result:
                    return result['arguments']
                elif 'verdict' in result:
                    return result
            except json.JSONDecodeError:
                pass
        
        # 方法5: 尝试直接解析整个content为JSON
        try:
            result = json.loads(content.strip())
            if isinstance(result, dict):
                if result.get('name') == 'Judge' and 'arguments' in result:
                    return result['arguments']
                elif 'verdict' in result:
                    return result
        except json.JSONDecodeError:
            pass
        
        print(f"[ERROR] Cannot extract Judge result from response content:")
        print(f"Content preview: {content[:500]}...")
        raise ValueError("Cannot extract Judge result from response: no valid JSON found")

    print(f"[ERROR] Cannot extract Judge result from response: {llm_response}")
    raise ValueError("Cannot extract Judge result from response")


def extract_step_index_from_screenshot_path(screenshot_path: str) -> Optional[int]:
    """
    从screenshot路径中提取step_index
    
    Args:
        screenshot_path: 截图路径，如 "task_a550d5b1/step_5.png" 或 "step_5.png"
    
    Returns:
        step_index，如果无法提取则返回None
    """
    import re
    match = re.search(r'step_(\d+)\.png', screenshot_path)
    if match:
        return int(match.group(1))
    return None


def load_history_screenshots(trace_file_path: str, current_step_index: int, k: int = 5) -> list[tuple[int, str]]:
    """
    从trace文件中加载之前的K个步骤的截图路径
    
    Args:
        trace_file_path: trace文件路径
        current_step_index: 当前步骤索引
        k: 要加载的历史步骤数量
    
    Returns:
        列表，每个元素是(step_index, screenshot_path)的元组，按step_index升序排列
    """
    history_screenshots = []
    
    try:
        with open(trace_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 读取所有步骤
        for line in lines:
            try:
                step_data = json.loads(line.strip())
                if step_data.get("type") == "step":
                    step_index = step_data.get("step_index")
                    screenshot_path = step_data.get("screenshot_path")
                    if step_index and screenshot_path and step_index < current_step_index:
                        history_screenshots.append((step_index, screenshot_path))
            except json.JSONDecodeError:
                continue
        
        # 按step_index排序，取最近的K个
        history_screenshots.sort(key=lambda x: x[0])
        return history_screenshots[-k:] if len(history_screenshots) > k else history_screenshots
    
    except Exception as e:
        print(f"[WARNING] Failed to load history screenshots: {e}")
        return []


def judge_model_output(
    model_input: list[dict[str, Any]],
    screenshot_path: str,
    format_model_output: dict[str, Any],
    trace_file_path: Optional[str] = None,
    history_images_k: int = 5,
    judge_images_k: int = 5,
    api_key: str = DEFAULT_API_KEY,
    base_url: str = DEFAULT_BASE_URL,
    model_name: str = DEFAULT_MODEL_NAME,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = DEFAULT_RETRY_DELAY,
    scaled_width: Optional[int] = None,
    scaled_height: Optional[int] = None,
) -> dict[str, Any]:
    """
    评估GUIAgent模型的输出是否合理
    
    Args:
        model_input: GUIAgent模型的文本输入（对话历史）
        screenshot_path: GUIAgent模型的图像输入路径
        format_model_output: 模型输出的格式化后的输出
        trace_file_path: trace文件路径，用于加载历史截图（可选）
        history_images_k: 为之前的K个user message添加截图（默认5）
        judge_images_k: 在judge_user_message中添加最近的K张图片（默认5）
        api_key: API密钥
        base_url: API基础URL
        model_name: 模型名称
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
        scaled_width: 图片缩放宽度（可选）
        scaled_height: 图片缩放高度（可选）
    
    Returns:
        评估结果字典，包含：
        - verdict: 是否合理（布尔值）
        - scores: 评分字典
        - failed_steps: 失败步骤列表
        - model_score: 模型评分（0-100）
        - model_confidence: 置信度（0-100）
        - repair_suggestions: 修复建议
    """
    # 加载截图并转换为base64
    screenshot_base64 = load_image_as_base64(screenshot_path, scaled_width, scaled_height)
    if screenshot_base64 is None:
        raise ValueError(f"Failed to load screenshot from {screenshot_path}")
    
    # 提取system prompt
    trace_system_prompt = extract_system_prompt(model_input)
    
    # 构建judge prompt（嵌入system prompt）
    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(trace_system_prompt=trace_system_prompt)
    
    # 创建OpenAI客户端
    client = OpenAI(base_url=base_url, api_key=api_key)
    
    # 构建消息列表（排除system消息，因为已经嵌入到judge prompt中）
    messages = convert_model_input_to_openai_format(model_input, screenshot_base64, exclude_system=True)
    
    # 如果提供了trace_file_path，为之前的K个user message添加截图
    if trace_file_path and history_images_k > 0:
        current_step_index = extract_step_index_from_screenshot_path(screenshot_path)
        if current_step_index:
            history_screenshots = load_history_screenshots(trace_file_path, current_step_index, history_images_k)
            
            # 构建step_index到screenshot_path的映射
            step_to_screenshot = {step_idx: path for step_idx, path in history_screenshots}
            
            # 为之前的user message添加对应的截图
            # 需要找到model_input中对应的user message并添加图片
            trace_dir = os.path.dirname(trace_file_path)
            trace_root = os.path.dirname(trace_dir) if trace_dir else os.getcwd()
            
            # 遍历messages，为user消息添加对应的截图
            user_message_count = 0
            for i in range(len(messages) - 1, -1, -1):  # 从后往前遍历
                msg = messages[i]
                if msg.get("role") == "user":
                    user_message_count += 1
                    # 计算对应的step_index（假设user消息对应step_index = current_step_index - user_message_count + 1）
                    step_idx = current_step_index - user_message_count + 1
                    if step_idx in step_to_screenshot:
                        screenshot_rel_path = step_to_screenshot[step_idx]
                        screenshot_full_path = os.path.join(trace_root, screenshot_rel_path)
                        history_screenshot_base64 = load_image_as_base64(screenshot_full_path, scaled_width, scaled_height)
                        
                        if history_screenshot_base64:
                            # 添加图片到user message
                            content = msg.get("content", [])
                            if isinstance(content, list):
                                # 检查是否已经有图片
                                has_image = any(item.get("type") == "image_url" for item in content if isinstance(item, dict))
                                if not has_image:
                                    content.append({
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{history_screenshot_base64}"
                                        }
                                    })
                                    msg["content"] = content
                    
                    if user_message_count >= history_images_k:
                        break
    
    # 添加format_model_output作为assistant消息
    if format_model_output:
        assistant_content = format_model_output.get("content", "")
        messages.append({
            "role": "assistant",
            "content": assistant_content if isinstance(assistant_content, str) else str(assistant_content)
        })
    
    # 添加评估请求消息，包含最近的K张图片（包括当前截图）
    judge_user_content = ["请使用Judge工具对上述模型输出进行评估，判断输出是否合理。"]
    
    if trace_file_path and judge_images_k > 0:
        current_step_index = extract_step_index_from_screenshot_path(screenshot_path)
        if current_step_index:
            # 加载历史截图（包括当前步骤之前的步骤）
            history_screenshots = load_history_screenshots(trace_file_path, current_step_index + 1, judge_images_k - 1)
            
            # 添加历史截图（从旧到新）
            trace_dir = os.path.dirname(trace_file_path)
            trace_root = os.path.dirname(trace_dir) if trace_dir else os.getcwd()
            
            for step_idx, screenshot_rel_path in history_screenshots:
                screenshot_full_path = os.path.join(trace_root, screenshot_rel_path)
                history_screenshot_base64 = load_image_as_base64(screenshot_full_path, scaled_width, scaled_height)
                if history_screenshot_base64:
                    judge_user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{history_screenshot_base64}"
                        }
                    })
            
            # 最后添加当前截图
            judge_user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{screenshot_base64}"
                }
            })
    
    judge_user_message = {
        "role": "user",
        "content": judge_user_content if len(judge_user_content) > 1 else judge_user_content[0]
    }
    messages.append(judge_user_message)
    
    # 构建system prompt（只包含judge prompt）
    system_message = {
        "role": "system",
        "content": judge_prompt
    }
    
    # 准备API调用参数（不使用tools参数，工具定义已包含在system prompt中）
    api_params = {
        "model": model_name,
        "messages": [system_message] + messages,
        "max_tokens": 16384,
        "temperature": 0
    }
    
    # 重试机制
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(**api_params)
            
            # 转换为字典格式
            message = response.choices[0].message
            
            tool_calls_list = []
            if hasattr(message, 'tool_calls') and message.tool_calls:
                tool_calls_list = [
                    {
                        "id": tc.id,
                        "type": getattr(tc, 'type', 'function'),
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in message.tool_calls
                ]
            
            reasoning_content = getattr(message, 'reasoning_content', None)
            
            response_dict = {
                "choices": [{
                    "message": {
                        "role": message.role,
                        "content": message.content or "",
                        "tool_calls": tool_calls_list,
                        "reasoning_content": reasoning_content
                    }
                }],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                }
            }
            
            # 提取Judge结果
            judge_result = extract_judge_result(response_dict)
            
            return judge_result

        except Exception as e:
            print(f"[RETRY {attempt + 1}/{max_retries}] Request exception: {e}")
            import traceback
            traceback.print_exc()
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    raise Exception("LLM call failed after max retries")


if __name__ == "__main__":
    # 示例用法
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python judge.py <trace_file_path> [step_index]")
        print("Example: python judge.py traces/task_a550d5b1/trace.jsonl 6")
        sys.exit(1)
    
    trace_file = sys.argv[1]
    step_index = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    
    # 读取trace文件
    with open(trace_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        if step_index > len(lines):
            print(f"Error: step_index {step_index} exceeds file length {len(lines)}")
            sys.exit(1)
        
        step_data = json.loads(lines[step_index - 1])
    
    # 提取数据
    model_input = step_data.get("model_input", [])
    screenshot_path = step_data.get("screenshot_path", "")
    format_model_output = step_data.get("format_model_output", {})
    
    # 构建完整的screenshot路径
    trace_dir = os.path.dirname(trace_file)
    screenshot_name = Path(screenshot_path).name
    screenshot_path = os.path.join(trace_dir, screenshot_name)
    
    print(f"Evaluating step {step_index} from {trace_file}")
    print(f"Screenshot: {screenshot_path}")
    print(f"Model output: {format_model_output.get('content', '')[:100]}...")
    
    # 执行评估
    try:
        result = judge_model_output(
            model_input=model_input,
            screenshot_path=screenshot_path,
            format_model_output=format_model_output,
            trace_file_path=trace_file,
            history_images_k=5,  # 为之前的5个user message添加截图
            judge_images_k=5     # 在judge_user_message中添加最近的5张图片
        )
        
        print("\n" + "="*60)
        print("评估结果:")
        print("="*60)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
