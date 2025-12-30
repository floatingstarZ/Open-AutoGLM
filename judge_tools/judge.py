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
                "description": "判断最后一步输出是否合理（true表示合理，false表示Agent跑偏需要纠正）"
            },
            "scores": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "综合评分 (0-100整数)，评估最后一步动作的整体质量"
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
            "refined": {
                "type": "string",
                "description": "如果判断为不合理(verdict=false)，提供修正后的完整输出（格式：<think>修正思考</think><answer>修正动作</answer>，动作使用绝对像素坐标）；如果判断为合理，则返回空字符串"
            },
            "repair": {
                "type": "string",
                "description": "修复建议文本，说明为什么Agent跑偏以及如何纠正"
            }
        },
        "required": ["verdict", "scores", "model_score", "model_confidence", "refined", "repair"]
    }
}

JUDGE_PROMPT_TEMPLATE = """你是一个Agent执行监督者。你的核心任务是：判断Agent最后一步的执行是否合理，在Agent跑偏时给予可直接执行的纠正动作。

--- GUIAgent的System Prompt ---
以下是GUIAgent在生成输出时遵循的system prompt。坐标系统使用**绝对像素坐标**。

<system_prompt>
{trace_system_prompt}
</system_prompt>

--- 你将看到 ---
1. GUIAgent的完整对话历史（user和assistant消息交替）
2. 最近{judge_steps_k}个步骤的屏幕截图（从旧到新）
3. 最后{judge_steps_k}步的模型输出

**你需要综合评估最后{judge_steps_k}步的执行情况，判断最后一步是否合理。如果不合理，你的refined输出将直接替换Agent的原输出并立即执行。**

--- 输出格式要求 ---
**必须严格按照以下JSON格式输出Judge工具的结果。注意：JSON字符串中的引号必须转义为\\"**

```json
{{
  "name": "Judge",
  "arguments": {{
    "verdict": false,
    "scores": 60,
    "model_score": 55,
    "model_confidence": 80,
    "refined": "<think>需要点击屏幕中心的按钮来继续任务。</think><answer>do(action=\\"Tap\\", element=[540, 960])</answer>",
    "repair": "Agent点击了错误的位置，应该点击屏幕中心的按钮。"
  }}
}}
```

**重要：**
- 所有字符串值中的双引号都必须转义为\\"
- refined字段中的内容如果包含引号，必须转义
- repair字段中的内容如果包含引号，必须转义
- 不要在字符串中使用未转义的双引号

**字段说明：**
- verdict (boolean): 最后一步是否合理（true=合理继续，false=跑偏需纠正）
- scores (integer, 0-100): 综合评分，评估最后一步动作的整体质量
- model_score (integer, 0-100): 输出满足用户需求的程度
- model_confidence (integer, 0-100): 你对判定的置信度
- refined (string): **关键字段！** 如果verdict=false，提供修正后的完整输出（格式：<think>...</think><answer>...</answer>）
  - **这个输出将直接替换Agent的原输出并立即执行**
  - thinking部分简要说明为什么这样做（1-2句话）
  - thinking部分可以包含对接下来步骤的粗略规划
  - thinking需要以第一人称（Agent视角）叙述，不要使用第三人称
  - answer部分必须是可直接执行的动作，使用绝对像素坐标
  - 示例：<think>需要点击返回按钮退出当前死循环。</think><answer>do(action="Tap", element=[54, 108])</answer>
  - 如果verdict=true，返回空字符串
- repair (string): 说明为什么Agent跑偏以及如何纠正（用于日志和调试）

--- 评估准则 ---

**判断Agent是否跑偏的3个关键检查点：**

1. **任务推进性** - Agent的最近几步是否让任务有实质进展
   - 动作是否符合当前屏幕状态（按钮/输入框等元素是否存在）
   - 坐标是否有效（指向可交互元素）
   - 是否在向用户目标前进

2. **死循环检测** - Agent是否在进行重复（>=3次）
   - 重复点击相同位置但无效果
   - 在相同屏幕间反复切换
   - 重复输入相同内容但失败
   - 多次尝试同一个策略但仍然未成功
   → 发现死循环必须设置verdict=false，在refined中提供新策略

3. **多模态理解** - Agent是否正确理解了屏幕内容
   - 识别的UI元素与实际屏幕是否匹配
   - 动作类型是否符合元素类型（如对文本框使用Tap而非Type）


**判定原则：**
- verdict=true: 动作合理，Agent在正确轨道上，refined返回空字符串
- verdict=false: Agent跑偏，**必须**在refined中提供可立即执行的纠正动作
  - refined的格式：<think>简要说明</think><answer>完整可执行的动作</answer>
  - answer必须包含完整的do()函数调用，使用绝对像素坐标
  - **这个输出会直接替换Agent的原输出并执行，所以必须确保可执行**
- repair清晰说明问题所在和正确做法（用于日志）
- 对明显错误（死循环、无效操作）零容忍

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
        
        # 方法4: 尝试提取代码块中的JSON（使用贪婪匹配处理嵌套对象）
        json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()

            # 尝试直接解析
            try:
                result = json.loads(json_str)
                if isinstance(result, dict):
                    if result.get('name') == 'Judge' and 'arguments' in result:
                        return result['arguments']
                    elif 'verdict' in result:
                        return result
            except json.JSONDecodeError:
                pass

            # 如果直接解析失败，尝试修复常见问题
            try:
                # 1. 移除尾部逗号
                cleaned_json = re.sub(r',\s*}', '}', json_str)
                cleaned_json = re.sub(r',\s*]', ']', cleaned_json)

                # 2. 尝试解析修复后的JSON
                result = json.loads(cleaned_json)
                if isinstance(result, dict):
                    if result.get('name') == 'Judge' and 'arguments' in result:
                        return result['arguments']
                    elif 'verdict' in result:
                        return result
            except json.JSONDecodeError:
                pass

            # 最后的手段：打印详细错误信息
            print(f"[WARNING] Failed to parse JSON from code block")
            print(f"JSON preview: {json_str[:200]}...")
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
        - scores: 综合评分（0-100整数）
        - model_score: 模型评分（0-100）
        - model_confidence: 置信度（0-100）
        - refined: 修正后的完整输出（字符串，格式：<think>...</think><answer>...</answer>）
        - repair: 修复建议（字符串）
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
