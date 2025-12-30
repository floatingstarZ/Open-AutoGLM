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
from datetime import datetime

from openai import OpenAI
from phone_agent.config.prompts import ABSOLUTE_COORD_SYSTEM_PROMPT

# 导入坐标转换函数
try:
    from .convert_format import current_relative_to_absolute
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    try:
        from convert_format import current_relative_to_absolute
    except ImportError:
        # 如果导入失败，尝试从当前目录导入
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from convert_format import current_relative_to_absolute


# ====================== Configuration ======================
# 默认配置
DEFAULT_API_KEY = "sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn"
DEFAULT_BASE_URL = "https://api-gateway.glm.ai/v1"
# DEFAULT_MODEL_NAME = "doubao-1.5-thinking-pro-vision-250415"
# DEFAULT_MODEL_NAME = "claude-sonnet-4-5-20250929"
DEFAULT_MODEL_NAME = "claude-sonnet-4-5-20250929-thinking"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5
# TARGET_WIDTH = 512  # 图片缩放的目标宽度（短边）
#                 # 默认缩放：短边缩放到TARGET_WIDTH，保持宽高比
#                 if width < height:
#                     new_width = TARGET_WIDTH
#                     new_height = int(height * (TARGET_WIDTH / width))
#                 else:
#                     new_height = TARGET_WIDTH
#                     new_width = int(width * (TARGET_WIDTH / height))
            
DEFAULT_JUDGE_STEPS_K = 5  # 评估最后K步的默认值

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
            "loop_detected": {
                "type": "boolean",
                "description": "是否检测到死循环（3次以上重复相同或相似的动作）"
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
            "refined_thinking": {
                "type": "string",
                "description": "如果判断为不合理(verdict=false)，提供简要的修正思考（1-2句话说明为什么这样做）；如果判断为合理，则返回空字符串"
            },
            "refined_action": {
                "type": "string",
                "description": "如果判断为不合理(verdict=false)，提供修正后的动作（使用绝对像素坐标，如：do(action=\"Tap\", element=[540, 960])）；如果判断为合理，则返回空字符串"
            },
            "repair_suggestions": {
                "type": "string",
                "description": "修复建议文本，说明为什么原action不合理以及为什么修正后的action是正确的"
            }
        },
        "required": ["verdict", "scores", "loop_detected", "failed_steps", "model_score", "model_confidence", "refined_thinking", "refined_action", "repair_suggestions"]
    }
}

JUDGE_PROMPT_TEMPLATE = """你是一个专注于模型执行审计与判定的智能体。
任务：基于GUIAgent模型的输入和输出，判断该次输出是否**合理**，**必须使用Judge工具返回结构化的判定结果**。

--- GUIAgent模型的System Prompt ---
以下是GUIAgent模型在生成输出时所遵循的system prompt，你需要根据这些规则来评估模型的输出是否符合要求。
注意：**坐标系统使用绝对像素坐标**

<system_prompt>
{trace_system_prompt}
</system_prompt>

--- 输入说明 ---
你将看到：
1. GUIAgent模型的完整对话历史（user和assistant消息交替）
2. 最近{judge_steps_k}个步骤的user消息包含对应的屏幕截图（从旧到新）
3. 最后{judge_steps_k}条assistant消息是最近{judge_steps_k}步的模型输出，你需要评估这{judge_steps_k}步是否合理
4. 通过查看对话历史和截图序列，你可以理解任务的执行过程，检测是否存在死循环或其他问题

**重要：你需要评估最后{judge_steps_k}步的整体合理性，而不仅仅是最后一步。**

--- Judge工具定义 ---
工具名称: Judge
描述: 返回模型执行的审计与判定结果

输入参数:
- verdict (boolean): 判断输出是否合理
- scores (object): 包含三个评分维度的对象
  - requirement_satisfaction (integer, 0-100): 需求满足度 - 动作是否满足用户需求
  - reasoning_correctness (integer, 0-100): 推理正确性 - 固定设置为100（不评估thinking）
  - conciseness (integer, 0-100): 简洁性 - 动作是否简洁明了
- loop_detected (boolean): 是否检测到死循环（3次以上重复相同或相似的动作）
- failed_steps (array): 失败步骤数组，如果没有发现失败步骤，请返回空数组 []。每个元素必须包含：
  - step_id (string): 步骤标识（应该是 "action"，不评估thinking）
  - snippet (string): 步骤内容片段（不超过 200 字符）
  - why_failed (string): 失败原因说明
- model_score (integer, 0-100): 模型对输出质量的判断分数，表示该输出满足用户需求的程度
- model_confidence (integer, 0-100): 判定的置信度
- refined_thinking (string): 如果最后一步判断为不合理(verdict=false)，提供对最后一步的简要修正思考（1-2句话说明为什么这样做）；如果最后一步合理，则返回空字符串。注意：这是对最后一步的纠正，不是对所有失败步骤的纠正。
- refined_action (string): 如果最后一步判断为不合理(verdict=false)，提供对最后一步的修正后的动作（使用绝对像素坐标，如：do(action="Tap", element=[540, 960])）；如果最后一步合理，则返回空字符串。注意：这是对最后一步的纠正，以让模型返回正常。
- repair_suggestions (string): 修复建议文本，说明为什么原action不合理以及为什么修正后的action是正确的。可以针对所有失败步骤提供建议。

必需参数: verdict, scores, loop_detected, failed_steps, model_score, model_confidence, refined_thinking, refined_action, repair_suggestions

--- 输出格式要求（重要） ---
**你必须严格按照以下JSON格式输出Judge工具的结果，不要添加任何其他文本或说明！**

输出格式：
```json
{{
  "name": "Judge",
  "arguments": {{
    "verdict": false,
    "scores": {{
      "requirement_satisfaction": 60,
      "reasoning_correctness": 100,
      "conciseness": 75
    }},
    "loop_detected": false,
    "failed_steps": [
      {{
        "step_id": "action",
        "snippet": "do(action=\\"Tap\\", element=[108, 192])",
        "why_failed": "点击位置错误，应该点击屏幕中心的按钮"
      }}
    ],
    "model_score": 55,
    "model_confidence": 80,
    "refined_thinking": "需要点击屏幕中心的按钮。",
    "refined_action": "do(action=\\"Tap\\", element=[540, 960])",
    "repair_suggestions": "原action点击了错误的位置[108, 192]（屏幕左上角），该位置没有可交互元素。正确的做法是点击屏幕中心的按钮，像素坐标为[540, 960]。"
  }}
}}
```

注意：
- 必须输出有效的JSON格式
- verdict必须是布尔值（true或false，小写）
- scores中的三个分值必须是0-100之间的整数，其中reasoning_correctness固定为100
- loop_detected必须是布尔值
- failed_steps必须是数组，如果没有失败步骤则返回空数组[]，只包含action相关的失败
- model_score和model_confidence必须是0-100之间的整数
- refined_thinking必须是字符串，如果verdict=true则为空字符串，如果verdict=false则提供简要的修正思考（1-2句话）
- refined_action必须是字符串，如果verdict=true则为空字符串，如果verdict=false则提供修正后的动作（需要转义引号，使用绝对像素坐标）
- repair_suggestions必须是字符串

--- 评估准则（CRITICAL - 必须严格遵循） ---

**重要提示：不评估thinking的正确性，只关注action是否合理！**
- thinking部分可以忽略，无论thinking内容如何，都不影响verdict的判断
- reasoning_correctness固定设置为100
- 只评估action是否符合当前屏幕状态和用户需求
- **你需要评估最后{judge_steps_k}步的整体合理性，检查这{judge_steps_k}步中是否有失败的步骤**

**1. 死循环检测（CRITICAL）**：
   - 检查最后{judge_steps_k}步中是否有3次或更多次重复相同或非常相似的动作
   - 重复动作的判断标准：
     * 完全相同的action类型和参数（如多次点击同一坐标）
     * 在相同或几乎相同的屏幕状态下执行相同类型的操作
     * 交替执行2-3个动作但没有实质进展
   - 如果检测到死循环，必须：
     * 设置loop_detected=true
     * 设置verdict=false
     * 在failed_steps中列出所有参与循环的步骤
     * 在refined_thinking和refined_action中提供对最后一步的修正输出（打破循环）

**2. 动作预测的合理性（评估最后{judge_steps_k}步）**：
   - 检查最后{judge_steps_k}步中每一步的action是否符合对应的屏幕状态
   - 检查每一步action的参数是否有效（如坐标是否在屏幕范围内）
   - 检查每一步action是否有助于完成用户任务
   - 检查每一步action是否符合system prompt中定义的操作格式
   - 将不合理的步骤添加到failed_steps列表中

**3. 上下文一致性（评估最后{judge_steps_k}步）**：
   - 检查最后{judge_steps_k}步的action是否形成合理的执行链
   - 检查是否有明显的逻辑跳跃或矛盾
   - 参考提供的历史截图，理解任务的执行进度
   - 将不一致的步骤添加到failed_steps列表中

**4. 格式正确性（评估最后{judge_steps_k}步）**：
   - 检查最后{judge_steps_k}步的输出是否符合system prompt中要求的格式（<think>...</think><answer>...</answer>）
   - 检查每一步action的格式是否正确
   - 将格式错误的步骤添加到failed_steps列表中

--- 评估原则 ---
- **评估最后{judge_steps_k}步的整体合理性**，检查这{judge_steps_k}步中是否有失败的步骤
- 如果最后K步中有任何一步不合理，设置verdict=false
- 将所有不合理的步骤（包括最后一步）添加到failed_steps列表中
- 死循环检测是**强制性的**，一旦发现必须标记
- **不评估thinking的正确性**，即使thinking有错误也不影响verdict判断
- **refined_thinking和refined_action只针对最后一步**：
  * 如果最后一步不合理（verdict=false），**必须**同时提供refined_thinking和refined_action，给出对最后一步的完整修正输出
  * 如果最后一步合理，refined_thinking和refined_action返回空字符串
  * refined_thinking应该简要说明修正后的思考（1-2句话），不需要过于详细
  * refined_action必须是可以直接执行的动作格式（如：do(action="Tap", element=[540, 960])，使用绝对像素坐标）
- repair_suggestions可以针对所有失败步骤提供建议
- 采用实用的评估标准，专注于action的正确性，不降低对明显错误（如死循环、错误的action）的判断标准

--- 立即执行 ---
现在，请基于你收到的对话历史、历史截图和最后{judge_steps_k}步的模型输出进行评估，严格按照上述JSON格式输出Judge工具的结果。
"""


# ====================== Utility Functions ======================

def load_image_as_base64(image_path: str, scaled_width: Optional[int] = None, scaled_height: Optional[int] = None) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """
    加载图片，并转换为base64
    
    Args:
        image_path: 图片文件路径
        scaled_width: 目标宽度（None = 使用默认缩放）
        scaled_height: 目标高度（None = 使用默认缩放）
    
    Returns:
        (Base64编码的图片字符串, 缩放后的宽度, 缩放后的高度)
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

            # 获取原始尺寸
            width, height = img.size

            # 缩放图片
            if scaled_width is not None and scaled_height is not None and scaled_width > 0 and scaled_height > 0:
                # 使用指定的缩放尺寸
                new_width, new_height = scaled_width, scaled_height
            else:
                new_width, new_height = width, height
            
            img = img.resize((new_width, new_height), Image.LANCZOS)

            # 转换为base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            b64_code = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return b64_code, new_width, new_height
    except Exception as e:
        print(f"[ERROR] Failed to load image {image_path}: {e}")
        return None, None, None


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


# def load_screen_size(trace_file_path: str, step_index: Optional[int] = None) -> Optional[list[int]]:
#     """
#     从trace文件中加载屏幕分辨率信息

#     Args:
#         trace_file_path: trace文件路径
#         step_index: 步骤索引（可选，如果提供则只从该步骤读取）

#     Returns:
#         屏幕分辨率 [width, height]，如果未找到则返回None
#     """
#     try:
#         with open(trace_file_path, 'r', encoding='utf-8') as f:
#             lines = f.readlines()

#         # 如果指定了step_index，只读取该步骤
#         if step_index is not None and 1 <= step_index <= len(lines):
#             try:
#                 step_data = json.loads(lines[step_index - 1].strip())
#                 if step_data.get("type") == "step":
#                     screen_info = step_data.get("screen_size", {})
#                     if screen_info:
#                         width = screen_info.get("width")
#                         height = screen_info.get("height")
#                         if width and height:
#                             return [width, height]
#             except (json.JSONDecodeError, KeyError):
#                 pass

#         # 否则遍历所有步骤，找到第一个包含screen_size的步骤
#         for line in lines:
#             try:
#                 step_data = json.loads(line.strip())
#                 if step_data.get("type") == "step":
#                     screen_info = step_data.get("screen_size", {})
#                     if screen_info:
#                         width = screen_info.get("width")
#                         height = screen_info.get("height")
#                         if width and height:
#                             return [width, height]
#             except (json.JSONDecodeError, KeyError):
#                 continue

#         return None

#     except Exception as e:
#         print(f"[WARNING] Failed to load screen size: {e}")
#         return None


def load_screenshots_mapping(trace_file_path: str, current_step_index: int) -> dict[int, str]:
    """
    从trace文件中加载步骤索引到截图路径的映射

    Args:
        trace_file_path: trace文件路径
        current_step_index: 当前步骤索引

    Returns:
        字典，键为step_index，值为screenshot_path（相对路径）
    """
    screenshots_map = {}

    try:
        with open(trace_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 读取所有步骤，构建映射
        for line in lines:
            try:
                step_data = json.loads(line.strip())
                if step_data.get("type") == "step":
                    step_index = step_data.get("step_index")
                    screenshot_path = step_data.get("screenshot_path")
                    # 收集当前步骤及之前的截图
                    if step_index and screenshot_path and step_index <= current_step_index:
                        screenshots_map[step_index] = screenshot_path
            except json.JSONDecodeError:
                continue

        return screenshots_map

    except Exception as e:
        print(f"[WARNING] Failed to load screenshots mapping: {e}")
        return {}


def save_judge_io(
    messages: list[dict[str, Any]],
    system_message: dict[str, Any],
    response_dict: dict[str, Any],
    judge_result: dict[str, Any],
    trace_file_path: Optional[str],
    save_path: Optional[str],
    screenshot_path: str,
) -> None:
    """
    保存judge模型的原始输入输出

    Args:
        messages: 发送给judge模型的消息列表
        system_message: system消息
        response_dict: 模型的原始响应
        judge_result: 提取后的judge结果
        trace_file_path: trace文件路径
        save_path: 保存路径（可选）
        screenshot_path: 当前截图路径
    """
    # 确定保存路径
    if save_path:
        output_path = save_path
    elif trace_file_path:
        # 保存到trace目录下
        trace_dir = os.path.dirname(trace_file_path)
        step_index = extract_step_index_from_screenshot_path(screenshot_path)
        if step_index:
            output_path = os.path.join(trace_dir, f"judge_io_step_{step_index}.json")
        else:
            output_path = os.path.join(trace_dir, "judge_io.json")
    else:
        # 默认保存到当前目录
        output_path = "judge_io.json"

    # 构建保存的数据
    io_data = {
        "timestamp": datetime.now().isoformat(),
        "screenshot_path": screenshot_path,
        "input": {
            "system_message": system_message,
            "messages": messages,
        },
        "output": {
            "raw_response": response_dict,
            "judge_result": judge_result,
        }
    }

    # 保存到文件
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(io_data, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Judge I/O saved to: {output_path}")
    except Exception as e:
        print(f"[WARNING] Failed to save judge I/O: {e}")


def judge_model_output(
    model_input: list[dict[str, Any]],
    screenshot_path: str,
    format_model_output: dict[str, Any],
    trace_file_path: Optional[str] = None,
    history_images_k: int = DEFAULT_JUDGE_STEPS_K,
    api_key: str = DEFAULT_API_KEY,
    base_url: str = DEFAULT_BASE_URL,
    model_name: str = DEFAULT_MODEL_NAME,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = DEFAULT_RETRY_DELAY,
    scaled_width: Optional[int] = None,
    scaled_height: Optional[int] = None,
    save_io: bool = True,
    save_io_path: Optional[str] = None,
) -> dict[str, Any]:
    """
    评估GUIAgent模型的输出是否合理

    Args:
        model_input: GUIAgent模型的文本输入（对话历史，包含system prompt）
        screenshot_path: 当前步骤的截图路径
        format_model_output: 模型输出的格式化后的输出
        trace_file_path: trace文件路径，用于加载历史截图（可选）
        history_images_k: 为最近的K个user message添加截图（包括当前步骤，默认5）
                         例如：K=5且当前step=10，则为step 6,7,8,9,10的user message添加截图
        api_key: API密钥
        base_url: API基础URL
        model_name: 模型名称
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
        scaled_width: 图片缩放宽度（可选）
        scaled_height: 图片缩放高度（可选）
        save_io: 是否保存原始输入输出（默认True）
        save_io_path: 保存路径（可选，默认保存到trace目录下的judge_io.json）

    Returns:
        评估结果字典，包含：
        - verdict: 是否合理（布尔值）
        - scores: 评分字典
        - loop_detected: 是否检测到死循环（布尔值）
        - failed_steps: 失败步骤列表
        - model_score: 模型评分（0-100）
        - model_confidence: 置信度（0-100）
        - refined_thinking: 修正后的思考（字符串）
        - refined_action: 修正后的动作（字符串）
        - repair_suggestions: 修复建议
        - reasoning_content: 模型的推理过程（字符串，如果存在）
    """
    # 构建judge prompt（嵌入GUIAgent的system prompt和K值）
    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
        trace_system_prompt=ABSOLUTE_COORD_SYSTEM_PROMPT,
        judge_steps_k=history_images_k
    )

    # 创建OpenAI客户端
    client = OpenAI(base_url=base_url, api_key=api_key)

    # 构建消息列表（排除system消息，不添加截图）
    messages = convert_model_input_to_openai_format(model_input, screenshot_base64=None, exclude_system=True)

    # 初始化缩放尺寸变量
    scaled_w = None
    scaled_h = None
    
    # 为最近的K个user message添加对应的截图
    if trace_file_path and history_images_k > 0:
        current_step_index = extract_step_index_from_screenshot_path(screenshot_path)
        if current_step_index:
            # 加载截图映射（step_index -> screenshot_path）
            screenshots_map = load_screenshots_mapping(trace_file_path, current_step_index)

            # 获取trace的根目录
            trace_dir = os.path.dirname(trace_file_path)
            trace_root = os.path.dirname(trace_dir) if trace_dir else os.getcwd()

            # 计算要添加截图的起始步骤（只为最近的K个步骤添加截图）
            start_step = max(1, current_step_index - history_images_k + 1)

            # 遍历messages，为符合条件的user message添加对应的截图
            user_msg_index = 0
            for msg in messages:
                if msg.get("role") == "user":
                    user_msg_index += 1
                    # 只为最近的K个步骤添加截图
                    if user_msg_index >= start_step and user_msg_index in screenshots_map:
                        screenshot_rel_path = screenshots_map[user_msg_index]
                        screenshot_full_path = os.path.join(trace_root, screenshot_rel_path)
                        screenshot_base64, img_w, img_h = load_image_as_base64(screenshot_full_path, scaled_width, scaled_height)
                        
                        # 保存最后一个截图的缩放尺寸
                        if screenshot_base64:
                            scaled_w, scaled_h = img_w, img_h

                        if screenshot_base64:
                            # 确保content是列表格式
                            content = msg.get("content", [])
                            if isinstance(content, str):
                                content = [{"type": "text", "text": content}]
                            elif not isinstance(content, list):
                                content = [{"type": "text", "text": str(content)}]

                            # 添加图片到user message
                            content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{screenshot_base64}"
                                }
                            })
                            msg["content"] = content
    else:
        raise Exception("No trace file provided")
    # 添加format_model_output作为assistant消息
    if not format_model_output:
        raise Exception("Judge Error: No format model output provided")
    messages.append(format_model_output)

    # 在添加judge_user_message之前，转换format_model_output中的坐标
    # 获取当前截图的缩放尺寸（用于坐标转换）
    # 如果之前加载过截图，使用其缩放尺寸；否则加载一次获取尺寸
    if scaled_w is None or scaled_h is None:
        _, scaled_w, scaled_h = load_image_as_base64(screenshot_path, scaled_width, scaled_height)
        
    converted_messages = current_relative_to_absolute(messages, image_scale=[scaled_w, scaled_h])
    messages = converted_messages

    # 添加judge请求消息（纯文本，不包含图片）
    judge_user_message = {
        "role": "user",
        "content": f"请使用Judge工具对上述最后{history_images_k}步的模型输出进行评估，判断这{history_images_k}步是否合理"
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
            print(message)
            
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
            
            # 如果有reasoning_content，添加到最终输出中
            if reasoning_content:
                judge_result['reasoning_content'] = reasoning_content

            # 保存原始输入输出
            if save_io:
                save_judge_io(
                    messages=messages,
                    system_message=system_message,
                    response_dict=response_dict,
                    judge_result=judge_result,
                    trace_file_path=trace_file_path,
                    save_path=save_io_path,
                    screenshot_path=screenshot_path
                )

            return judge_result

        except Exception as e:
            print(f"[RETRY {attempt + 1}/{max_retries}] Request exception: {e}")
            import traceback
            traceback.print_exc()
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

    raise Exception("LLM call failed after max retries")


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Judge工具：评估GUIAgent模型输出的合理性",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 评估第6步
  python judge.py traces/task_xxx/trace.jsonl 6

  # 评估最后一步，调整历史图片数量
  python judge.py traces/task_xxx/trace.jsonl -k 3

  # 禁用自动保存
  python judge.py traces/task_xxx/trace.jsonl 6 --no-save
        """
    )

    parser.add_argument("trace_file", help="trace.jsonl文件路径")
    parser.add_argument("step_index", nargs="?", type=int, help="要评估的步骤索引（默认：读取最后一个step）")
    parser.add_argument("-k", "--history-images", type=int, default=DEFAULT_JUDGE_STEPS_K,
                       help=f"加载最近K个步骤的截图（默认：{DEFAULT_JUDGE_STEPS_K}）")
    parser.add_argument("--no-save", action="store_true",
                       help="不保存judge的输入输出")
    parser.add_argument("--output", "-o", help="自定义保存路径")

    args = parser.parse_args()

    # 读取trace文件
    try:
        with open(args.trace_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"❌ 文件不存在: {args.trace_file}")
        sys.exit(1)

    # 确定step_index
    if args.step_index is None:
        # 找到最后一个step类型的记录
        for i in range(len(lines) - 1, -1, -1):
            try:
                data = json.loads(lines[i].strip())
                if data.get("type") == "step":
                    step_index = i + 1  # 转换为1-based索引
                    break
            except json.JSONDecodeError:
                continue
        else:
            print(f"❌ 未找到有效的step记录")
            sys.exit(1)
    else:
        step_index = args.step_index

    if step_index > len(lines) or step_index < 1:
        print(f"❌ step_index {step_index} 超出范围 (1-{len(lines)})")
        sys.exit(1)

    # 解析step数据
    try:
        step_data = json.loads(lines[step_index - 1])
    except json.JSONDecodeError:
        print(f"❌ 第{step_index}行不是有效的JSON")
        sys.exit(1)

    if step_data.get("type") != "step":
        print(f"⚠️  警告: 第{step_index}行不是step类型记录")

    # 提取数据
    model_input = step_data.get("model_input", [])
    screenshot_path = step_data.get("screenshot_path", "")
    format_model_output = step_data.get("format_model_output", {})

    # 构建完整的screenshot路径
    trace_dir = os.path.dirname(args.trace_file)
    screenshot_name = Path(screenshot_path).name
    screenshot_path = os.path.join(trace_dir, screenshot_name)

    print(f"📋 评估步骤: {step_index}")
    print(f"📂 Trace文件: {args.trace_file}")
    print(f"📷 截图路径: {screenshot_path}")
    print(f"🖼️  历史图片数: {args.history_images}")
    print(f"💾 保存I/O: {'否' if args.no_save else '是'}")
    if format_model_output:
        content = format_model_output.get('content', '')
        preview = content[:100] + "..." if len(content) > 100 else content
        print(f"📝 模型输出预览: {preview}")

    # 执行评估
    try:
        result = judge_model_output(
            model_input=model_input,
            screenshot_path=screenshot_path,
            format_model_output=format_model_output,
            trace_file_path=args.trace_file,
            history_images_k=args.history_images,
            save_io=not args.no_save,
            save_io_path=args.output,
        )

        print("\n" + "="*60)
        print("✅ 评估结果:")
        print("="*60)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
