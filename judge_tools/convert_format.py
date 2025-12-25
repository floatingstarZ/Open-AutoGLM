"""
格式转换工具：实现Claude格式 <-> 当前模型输出格式的双向转换

当前格式 (Current Format):
- 对话历史列表，包含system、user、assistant消息
- assistant消息格式: {"role": "assistant", "content": "<think>...</think><answer>...</answer>"}
- user消息格式: {"role": "user", "content": [{"type": "text", "text": "..."}, ...]}

Claude格式 (Claude Format):
- 对话历史列表，包含system、user、assistant消息
- assistant消息的content是数组: [{"type": "thinking", ...}, {"type": "tool_use", ...}, ...]
- user消息格式与当前格式基本相同
"""

import json
import re
import uuid
import secrets
import base64
from typing import Any, Dict, List, Optional, Tuple


# ====================== 工具函数 ======================

def _generate_tool_use_id() -> str:
    """
    生成 tool_use 的 id，格式为 toolu_bdrk_<25字符的base64url字符串>

    示例: toolu_bdrk_01X6wjmryLYG6mrfxRRBkpNZ
    """
    random_bytes = secrets.token_bytes(19)
    base64url_str = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    base64url_str = base64url_str[:25]
    return f"toolu_bdrk_{base64url_str}"


def _scale_coordinates_in_text(text: str, scale_x: float, scale_y: float) -> str:
    """
    缩放文本中的坐标

    支持的坐标格式：
    - [x, y]
    - [x,y]
    - (x, y)
    - (x,y)

    Args:
        text: 包含坐标的文本
        scale_x: X坐标缩放因子
        scale_y: Y坐标缩放因子

    Returns:
        缩放后的文本

    Examples:
        >>> _scale_coordinates_in_text("点击[123, 456]", 2.0, 2.0)
        "点击[246, 912]"
    """
    if scale_x == 1.0 and scale_y == 1.0:
        return text

    def replace_coord(match):
        """替换坐标的回调函数"""
        bracket_start = match.group(1)  # [ 或 (
        x = int(match.group(2))
        y = int(match.group(3))
        bracket_end = match.group(4)  # ] 或 )

        # 缩放坐标
        scaled_x = int(x * scale_x)
        scaled_y = int(y * scale_y)

        return f"{bracket_start}{scaled_x}, {scaled_y}{bracket_end}"

    # 匹配 [x, y] 或 [x,y] 或 (x, y) 或 (x,y) 格式
    # 坐标值必须是合理的范围（0-10000），避免误匹配其他数字对
    pattern = r'([\[\(])(\d{1,5})\s*,\s*(\d{1,5})([\]\)])'

    return re.sub(pattern, replace_coord, text)


def _parse_action_string(action_str: str) -> Dict[str, Any]:
    """
    解析action字符串为字典

    Args:
        action_str: action字符串，如 'do(action="Launch", app="抖音")' 或 'finish(message="完成")'

    Returns:
        解析后的action字典
    """
    # 提取函数名
    match = re.match(r'(\w+)\((.*)\)', action_str.strip())
    if not match:
        raise ValueError(f"Invalid action format: {action_str}")

    func_name = match.group(1)
    params_str = match.group(2)

    result = {"_metadata": func_name}

    # 解析参数 - 支持 key="value" 和 key=[x,y] 格式
    param_pattern = r'(\w+)=((?:"[^"]*")|(?:\[[^\]]*\]))'
    params = re.findall(param_pattern, params_str)

    for key, value in params:
        if value.startswith('"') and value.endswith('"'):
            result[key] = value[1:-1]
        elif value.startswith('[') and value.endswith(']'):
            try:
                result[key] = json.loads(value)
            except json.JSONDecodeError:
                result[key] = value
        else:
            result[key] = value

    return result


def _action_dict_to_string(action: Dict[str, Any]) -> str:
    """
    将action字典转换为字符串格式

    Args:
        action: action字典

    Returns:
        action字符串
    """
    metadata = action.get("_metadata", "do")
    params = []

    for key, value in action.items():
        if key == "_metadata":
            continue

        if isinstance(value, str):
            params.append(f'{key}="{value}"')
        elif isinstance(value, (list, tuple)):
            params.append(f'{key}={json.dumps(value)}')
        else:
            params.append(f'{key}={value}')

    return f'{metadata}({", ".join(params)})'


# ====================== 当前格式 <-> Claude格式 ======================

def current_to_claude(
    messages: List[Dict[str, Any]],
    claude_image_scale: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """
    将当前格式的对话历史转换为Claude格式

    当前格式使用相对坐标(0-999)，Claude格式使用绝对坐标(基于实际图像分辨率)

    Args:
        messages: 当前格式的消息列表
        claude_image_scale: Claude推理时的图像分辨率 [width, height]，用于将相对坐标转换为绝对坐标

    Returns:
        Claude格式的消息列表

    Examples:
        >>> current = [
        ...     {"role": "system", "content": "系统提示词..."},
        ...     {"role": "user", "content": [{"type": "text", "text": "任务描述"}]},
        ...     {"role": "assistant", "content": "<think>思考</think><answer>do(action=\"Tap\", element=[500,500])</answer>"}
        ... ]
        >>> # 相对坐标[500,500] -> 绝对坐标[546,546] (基于1092x1092)
        >>> claude = current_to_claude(current, claude_image_scale=[1092, 1092])
    """
    claude_messages = []

    # 计算从相对坐标(0-999)到绝对坐标的缩放因子
    # relative_to_absolute: absolute = relative / 999 * image_size
    scale_x = 1.0
    scale_y = 1.0
    if claude_image_scale:
        scale_x = claude_image_scale[0] / 999.0
        scale_y = claude_image_scale[1] / 999.0

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role == "system":
            # system消息保持不变
            claude_messages.append({
                "role": "system",
                "content": content
            })

        elif role == "user":
            # user消息保持不变（已经是正确格式）
            claude_messages.append({
                "role": "user",
                "content": content
            })

        elif role == "assistant":
            # 解析assistant消息并转换为Claude格式
            claude_content = _parse_assistant_to_claude(content, scale_x, scale_y)
            claude_messages.append({
                "role": "assistant",
                "content": claude_content
            })

    return claude_messages


def claude_to_current(
    messages: List[Dict[str, Any]],
    claude_image_scale: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """
    将Claude格式的对话历史转换为当前格式

    Claude格式使用绝对坐标(基于实际图像分辨率)，当前格式使用相对坐标(0-999)

    Args:
        messages: Claude格式的消息列表
        claude_image_scale: Claude推理时的图像分辨率 [width, height]，用于将绝对坐标转换为相对坐标

    Returns:
        当前格式的消息列表

    Examples:
        >>> claude = [
        ...     {"role": "system", "content": "系统提示词..."},
        ...     {"role": "user", "content": [{"type": "text", "text": "任务描述"}]},
        ...     {"role": "assistant", "content": [
        ...         {"type": "thinking", "thinking": "思考"},
        ...         {"type": "tool_use", "name": "Tap", "input": {"coordinate": [546, 546]}}
        ...     ]}
        ... ]
        >>> # 绝对坐标[546,546] -> 相对坐标[500,500] (基于1092x1092)
        >>> current = claude_to_current(claude, claude_image_scale=[1092, 1092])
    """
    current_messages = []

    # 计算从绝对坐标到相对坐标(0-999)的缩放因子
    # absolute_to_relative: relative = absolute / image_size * 999
    scale_x = 1.0
    scale_y = 1.0
    if claude_image_scale:
        scale_x = 999.0 / claude_image_scale[0]
        scale_y = 999.0 / claude_image_scale[1]

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role == "system":
            # system消息保持不变
            current_messages.append({
                "role": "system",
                "content": content
            })

        elif role == "user":
            # user消息保持不变
            current_messages.append({
                "role": "user",
                "content": content
            })

        elif role == "assistant":
            # 转换Claude格式的assistant消息为当前格式
            current_content = _parse_claude_to_assistant(content, scale_x, scale_y)
            current_messages.append({
                "role": "assistant",
                "content": current_content
            })

    return current_messages


def _parse_assistant_to_claude(content: str, scale_x: float = 1.0, scale_y: float = 1.0) -> List[Dict[str, Any]]:
    """
    解析assistant的content字符串为Claude格式的content数组

    Args:
        content: "<think>...</think><answer>...</answer>" 格式的字符串
        scale_x: X坐标缩放因子 (claude_width / current_width)
        scale_y: Y坐标缩放因子 (claude_height / current_height)

    Returns:
        Claude格式的content数组
    """
    claude_content = []

    # 提取thinking
    think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
    if think_match:
        thinking_text = think_match.group(1).strip()
        if thinking_text:
            # 缩放thinking文本中的坐标
            scaled_thinking = _scale_coordinates_in_text(thinking_text, scale_x, scale_y)
            claude_content.append({
                "type": "thinking",
                "thinking": scaled_thinking,
                "signature": str(uuid.uuid4())
            })

    # 提取answer
    answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
    if answer_match:
        answer_text = answer_match.group(1).strip()

        # 解析action
        try:
            action = _parse_action_string(answer_text)
            metadata = action.get("_metadata")

            if metadata == "finish":
                # finish操作转换为text
                message = action.get("message", "")
                claude_content.append({
                    "type": "text",
                    "text": message
                })
            else:
                # do操作转换为tool_use
                action_type = action.get("action", "")
                tool_input = {}

                # 转换坐标字段名并缩放坐标
                if action_type in ["Tap", "Long Press", "Double Tap"]:
                    if "element" in action:
                        element = action["element"]
                        # 缩放坐标
                        scaled_coordinate = [
                            int(element[0] * scale_x),
                            int(element[1] * scale_y)
                        ]
                        tool_input["coordinate"] = scaled_coordinate
                    # 如果有message字段，也加入input
                    if "message" in action:
                        tool_input["message"] = action["message"]
                elif action_type == "Swipe":
                    if "start" in action and "end" in action:
                        start = action["start"]
                        end = action["end"]
                        # 缩放起始和结束坐标
                        scaled_start = [
                            int(start[0] * scale_x),
                            int(start[1] * scale_y)
                        ]
                        scaled_end = [
                            int(end[0] * scale_x),
                            int(end[1] * scale_y)
                        ]
                        tool_input["start_coordinate"] = scaled_start
                        tool_input["end_coordinate"] = scaled_end
                else:
                    # 其他操作，复制所有非metadata和action的字段
                    tool_input = {k: v for k, v in action.items()
                                 if k not in ["_metadata", "action"]}

                claude_content.append({
                    "type": "tool_use",
                    "id": _generate_tool_use_id(),
                    "name": action_type,
                    "input": tool_input
                })
        except ValueError as e:
            raise Exception(f"Error parsing action string: \n", '-'*100 + '\n', str(e), '-'*100 + '\n')

    return claude_content


def _parse_claude_to_assistant(content: Any, scale_x: float = 1.0, scale_y: float = 1.0) -> str:
    """
    解析Claude格式的content为当前格式的assistant content字符串

    Args:
        content: Claude格式的content（可能是数组或字符串）
        scale_x: X坐标缩放因子 (current_width / claude_width)
        scale_y: Y坐标缩放因子 (current_height / claude_height)

    Returns:
        "<think>...</think><answer>...</answer>" 格式的字符串
    """
    # 如果content已经是字符串，直接返回
    if isinstance(content, str):
        return content

    # 如果不是列表，转换为字符串
    if not isinstance(content, list):
        return str(content)

    thinking = ""
    action_str = ""

    for block in content:
        block_type = block.get("type")

        if block_type == "thinking":
            thinking_text = block.get("thinking", "")
            # 缩放thinking文本中的坐标
            thinking = _scale_coordinates_in_text(thinking_text, scale_x, scale_y)

        elif block_type == "tool_use":
            tool_name = block.get("name", "")
            tool_input = block.get("input", {})

            # 构建action字典
            action = {
                "_metadata": "do",
                "action": tool_name
            }

            # 转换坐标字段名并缩放坐标
            if tool_name in ["Tap", "Long Press", "Double Tap"]:
                if "coordinate" in tool_input:
                    coordinate = tool_input["coordinate"]
                    # 缩放坐标
                    scaled_element = [
                        int(coordinate[0] * scale_x),
                        int(coordinate[1] * scale_y)
                    ]
                    action["element"] = scaled_element
                if "message" in tool_input:
                    action["message"] = tool_input["message"]
            elif tool_name == "Swipe":
                if "start_coordinate" in tool_input and "end_coordinate" in tool_input:
                    start_coordinate = tool_input["start_coordinate"]
                    end_coordinate = tool_input["end_coordinate"]
                    # 缩放起始和结束坐标
                    scaled_start = [
                        int(start_coordinate[0] * scale_x),
                        int(start_coordinate[1] * scale_y)
                    ]
                    scaled_end = [
                        int(end_coordinate[0] * scale_x),
                        int(end_coordinate[1] * scale_y)
                    ]
                    action["start"] = scaled_start
                    action["end"] = scaled_end
            else:
                # 其他操作，直接复制所有字段
                action.update(tool_input)

            # 转换为字符串
            action_str = _action_dict_to_string(action)

        elif block_type == "text":
            text_content = block.get("text", "")
            # 作为finish处理
            action = {
                "_metadata": "finish",
                "message": text_content
            }
            action_str = _action_dict_to_string(action)

    # 构建最终字符串
    return f"<think>{thinking}</think><answer>{action_str}</answer>"


# ====================== 辅助函数 ======================

def extract_thinking_and_action(content: str) -> Tuple[str, str]:
    """
    从assistant content中提取thinking和action字符串

    Args:
        content: "<think>...</think><answer>...</answer>" 格式的字符串

    Returns:
        (thinking, action_str) 元组
    """
    # 提取thinking
    think_match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
    thinking = think_match.group(1).strip() if think_match else ""

    # 提取answer
    answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
    action_str = answer_match.group(1).strip() if answer_match else ""

    return thinking, action_str


def build_assistant_content(thinking: str, action_str: str) -> str:
    """
    构建assistant content字符串

    Args:
        thinking: 思考内容
        action_str: action字符串

    Returns:
        "<think>...</think><answer>...</answer>" 格式的字符串
    """
    return f"<think>{thinking}</think><answer>{action_str}</answer>"


# ====================== 示例用法 ======================

if __name__ == "__main__":
    # 示例1: 不带缩放的转换
    print("=" * 80)
    print("示例1: 不带缩放的转换（当前格式 -> Claude格式 -> 当前格式）")
    print("=" * 80)

    current_messages = [
        {
            "role": "system",
            "content": "你是一个智能助手..."
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "外卖下单四杯蜜雪冰城的奶昔\n\n{\"current_app\": \"文件\"}"
                }
            ]
        },
        {
            "role": "assistant",
            "content": "<think>用户想要点外卖，需要先打开美团应用。</think><answer>do(action=\"Launch\", app=\"美团\")</answer>"
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "** Screen Info **\n\n{\"current_app\": \"美团\"}"
                }
            ]
        },
        {
            "role": "assistant",
            "content": "<think>需要点击外卖入口。</think><answer>do(action=\"Tap\", element=[120, 190])</answer>"
        }
    ]

    # 不带缩放的转换
    claude_messages = current_to_claude(current_messages)
    converted_back = claude_to_current(claude_messages)

    # 验证一致性
    for i, (orig, conv) in enumerate(zip(current_messages, converted_back)):
        if orig["role"] == "assistant":
            orig_thinking, orig_action = extract_thinking_and_action(orig["content"])
            conv_thinking, conv_action = extract_thinking_and_action(conv["content"])
            print(f"消息 {i}:")
            print(f"  原始action: {orig_action}")
            print(f"  转换action: {conv_action}")
            print(f"  一致性: {orig_action == conv_action}")
    print()

    # 示例2: 坐标转换（相对坐标 <-> 绝对坐标）
    print("=" * 80)
    print("示例2: 坐标转换（相对坐标0-999 <-> 绝对坐标）")
    print("=" * 80)

    # Claude图像分辨率
    claude_image_scale = [1092, 1092]

    print(f"Claude图像分辨率: {claude_image_scale}")
    print(f"Current坐标范围: 0-999 (相对坐标)")
    print(f"Claude坐标范围: 0-{claude_image_scale[0]}, 0-{claude_image_scale[1]} (绝对坐标)")
    print()

    # 原始消息（使用相对坐标0-999）
    original_with_coords = [
        {
            "role": "assistant",
            "content": "<think>点击屏幕中央</think><answer>do(action=\"Tap\", element=[500, 500])</answer>"
        },
        {
            "role": "assistant",
            "content": "<think>向下滑动</think><answer>do(action=\"Swipe\", start=[500, 700], end=[500, 300])</answer>"
        }
    ]

    print("原始坐标（相对坐标，范围0-999）:")
    for msg in original_with_coords:
        _, action = extract_thinking_and_action(msg["content"])
        print(f"  {action}")
    print()

    # 转换为Claude格式（相对坐标 -> 绝对坐标）
    claude_with_scaling = current_to_claude(
        original_with_coords,
        claude_image_scale=claude_image_scale
    )

    print("Claude格式（绝对坐标，基于1092x1092）:")
    for msg in claude_with_scaling:
        if msg["role"] == "assistant":
            for block in msg["content"]:
                if block["type"] == "tool_use":
                    print(f"  {block['name']}: {block['input']}")
    print()

    # 转换回当前格式（绝对坐标 -> 相对坐标）
    converted_back_with_scaling = claude_to_current(
        claude_with_scaling,
        claude_image_scale=claude_image_scale
    )

    print("转换回当前格式（相对坐标，范围0-999）:")
    for msg in converted_back_with_scaling:
        _, action = extract_thinking_and_action(msg["content"])
        print(f"  {action}")
    print()

    # 验证往返转换的精度
    print("=" * 80)
    print("验证: 检查往返转换的坐标精度")
    print("=" * 80)
    for i, (orig, conv) in enumerate(zip(original_with_coords, converted_back_with_scaling)):
        orig_thinking, orig_action = extract_thinking_and_action(orig["content"])
        conv_thinking, conv_action = extract_thinking_and_action(conv["content"])

        # 解析坐标
        orig_dict = _parse_action_string(orig_action)
        conv_dict = _parse_action_string(conv_action)

        print(f"消息 {i}:")
        print(f"  原始: {orig_action}")
        print(f"  转换: {conv_action}")

        # 检查坐标差异
        if "element" in orig_dict and "element" in conv_dict:
            diff_x = abs(orig_dict["element"][0] - conv_dict["element"][0])
            diff_y = abs(orig_dict["element"][1] - conv_dict["element"][1])
            print(f"  坐标差异: X={diff_x}px, Y={diff_y}px")
        elif "start" in orig_dict and "start" in conv_dict:
            diff_start_x = abs(orig_dict["start"][0] - conv_dict["start"][0])
            diff_start_y = abs(orig_dict["start"][1] - conv_dict["start"][1])
            diff_end_x = abs(orig_dict["end"][0] - conv_dict["end"][0])
            diff_end_y = abs(orig_dict["end"][1] - conv_dict["end"][1])
            print(f"  起点差异: X={diff_start_x}px, Y={diff_start_y}px")
            print(f"  终点差异: X={diff_end_x}px, Y={diff_end_y}px")
        print()

    # 示例3: Thinking中的坐标转换
    print("=" * 80)
    print("示例3: Thinking中的坐标转换")
    print("=" * 80)

    # 包含坐标的thinking（相对坐标0-999）
    thinking_with_coords = [
        {
            "role": "assistant",
            "content": "<think>我需要点击屏幕上的[500, 500]位置，这是搜索按钮的坐标。还要滑动从(300, 700)到(300, 300)。</think><answer>do(action=\"Tap\", element=[500, 500])</answer>"
        }
    ]

    print("原始thinking（相对坐标0-999）:")
    orig_think, _ = extract_thinking_and_action(thinking_with_coords[0]["content"])
    print(f"  {orig_think}")
    print()

    # 转换为Claude格式（相对坐标 -> 绝对坐标）
    claude_thinking = current_to_claude(
        thinking_with_coords,
        claude_image_scale=[1092, 1092]
    )

    print("Claude格式thinking（绝对坐标，基于1092x1092）:")
    if claude_thinking[0]["role"] == "assistant":
        for block in claude_thinking[0]["content"]:
            if block["type"] == "thinking":
                print(f"  {block['thinking']}")
    print()

    # 转换回当前格式（绝对坐标 -> 相对坐标）
    current_thinking_back = claude_to_current(
        claude_thinking,
        claude_image_scale=[1092, 1092]
    )

    print("转换回当前格式thinking（相对坐标0-999）:")
    conv_think, _ = extract_thinking_and_action(current_thinking_back[0]["content"])
    print(f"  {conv_think}")
    print()

    # 测试_scale_coordinates_in_text函数
    print("=" * 80)
    print("测试: _scale_coordinates_in_text 函数")
    print("=" * 80)

    test_cases = [
        ("点击[123, 456]", 2.0, 2.0, "点击[246, 912]"),
        ("从(100, 200)滑动到(300, 400)", 1.5, 0.5, "从(150, 100)滑动到(450, 200)"),
        ("坐标是 [50,100] 和 [200,300]", 2.0, 2.0, "坐标是 [100, 200] 和 [400, 600]"),
        ("没有坐标的文本", 2.0, 2.0, "没有坐标的文本"),
    ]

    for text, scale_x, scale_y, expected in test_cases:
        result = _scale_coordinates_in_text(text, scale_x, scale_y)
        status = "✓" if result == expected else "✗"
        print(f"{status} 输入: {text}")
        print(f"  缩放: X={scale_x}, Y={scale_y}")
        print(f"  预期: {expected}")
        print(f"  结果: {result}")
        print()
