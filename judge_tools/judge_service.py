"""
Judge Service: 评估GUIAgent模型输出的合理性

这是一个简化的judge服务，输入已经包含内嵌图片的对话历史，无需处理截图加载和坐标转换。
"""

import json
import time
from typing import Any, Dict, Optional

from openai import OpenAI
from phone_agent.config.prompts import ABSOLUTE_COORD_SYSTEM_PROMPT


# ====================== Configuration ======================
# 默认配置
DEFAULT_API_KEY = "sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn"
DEFAULT_BASE_URL = "https://api-gateway.glm.ai/v1"
DEFAULT_MODEL_NAME = "claude-sonnet-4-5-20250929-thinking"
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
2. 对话历史中已经内嵌了相关步骤的屏幕截图
3. 最后一步的模型输出

**你需要综合评估对话历史，判断最后一步是否合理。如果不合理，你的refined输出将直接替换Agent的原输出并立即执行。**

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


def judge_model_output(
    conversation_history: list[dict[str, Any]],
    api_key: str = DEFAULT_API_KEY,
    base_url: str = DEFAULT_BASE_URL,
    model_name: str = DEFAULT_MODEL_NAME,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = DEFAULT_RETRY_DELAY,
) -> dict[str, Any]:
    """
    评估GUIAgent模型的输出是否合理

    Args:
        conversation_history: 已经包含内嵌图片的对话历史（user/assistant消息序列，不含system）
        api_key: API密钥
        base_url: API基础URL
        model_name: 模型名称
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）

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
    # 构建judge prompt（嵌入GUIAgent的system prompt）
    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(
        trace_system_prompt=ABSOLUTE_COORD_SYSTEM_PROMPT,
    )

    # 创建OpenAI客户端
    client = OpenAI(base_url=base_url, api_key=api_key)

    # 使用传入的conversation_history作为消息列表
    messages = conversation_history.copy()

    # 验证输入
    if not messages:
        raise ValueError("Conversation history is empty")

    # 添加judge请求消息（纯文本，不包含图片）
    judge_user_message = {
        "role": "user",
        "content": "请使用Judge工具对上述模型输出进行评估，判断是否合理"
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
    print("Judge Service - 使用示例")
    print("=" * 60)
    print("""
示例代码:

from judge_service import judge_model_output

# 准备已经包含图片的对话历史
conversation_history = [
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "请打开设置"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
        ]
    },
    {
        "role": "assistant",
        "content": "<think>需要点击设置图标</think><answer>do(action='Tap', element=[100, 200])</answer>"
    },
    # ... 更多对话
]

# 调用judge服务
result = judge_model_output(
    conversation_history=conversation_history,
    api_key="your-api-key",
    base_url="https://api-gateway.glm.ai/v1",
    model_name="claude-sonnet-4-5-20250929-thinking"
)

print(result)
# 输出: {'verdict': True, 'scores': 85, ...}
    """)
