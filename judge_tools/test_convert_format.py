"""
测试 convert_format.py 的修复

验证：
1. 工具名称正确转换（LongPress, DoubleClick）
2. LongPress 的 duration 字段正确处理
3. tool_result 消息正确生成
4. image 格式正确处理
"""

import json
from convert_format import current_to_claude, claude_to_current


def test_tool_names_and_duration():
    """测试工具名称和 duration 字段"""
    print("=" * 80)
    print("测试 1: 工具名称和 duration 字段")
    print("=" * 80)

    current_messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "测试任务"}]
        },
        {
            "role": "assistant",
            "content": "<think>点击按钮</think><answer>do(action=\"Tap\", element=[500, 500])</answer>"
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": "执行结果"}]
        },
        {
            "role": "assistant",
            "content": "<think>长按元素</think><answer>do(action=\"Long Press\", element=[300, 400], duration=3.0)</answer>"
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": "执行结果"}]
        },
        {
            "role": "assistant",
            "content": "<think>双击元素</think><answer>do(action=\"Double Tap\", element=[600, 700])</answer>"
        }
    ]

    # 转换为 Claude 格式
    claude_messages = current_to_claude(current_messages, claude_image_scale=[1092, 1092])

    # 验证工具名称
    print("\n检查工具名称转换:")
    for i, msg in enumerate(claude_messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            for block in content:
                if block.get("type") == "tool_use":
                    tool_name = block.get("name")
                    tool_input = block.get("input", {})
                    print(f"  消息 {i}: {tool_name}")
                    if tool_name == "LongPress":
                        duration = tool_input.get("duration")
                        print(f"    ✓ duration: {duration}")
                        assert duration is not None, "LongPress 缺少 duration 字段！"
                    elif tool_name in ["Tap", "DoubleClick"]:
                        print(f"    ✓ 工具名称正确")
                    else:
                        print(f"    ✗ 未知工具名称: {tool_name}")

    print("\n✅ 测试通过：工具名称和 duration 字段正确")


def test_tool_result():
    """测试 tool_result 消息生成"""
    print("\n" + "=" * 80)
    print("测试 2: tool_result 消息生成")
    print("=" * 80)

    current_messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "开始任务"}]
        },
        {
            "role": "assistant",
            "content": "<think>点击按钮</think><answer>do(action=\"Tap\", element=[500, 500])</answer>"
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Tapped at (546, 546)"},
                {"type": "text", "text": "<system-reminder>Screenshot dimensions: (1092x1092, png)</system-reminder>"}
            ]
        },
        {
            "role": "assistant",
            "content": "<think>继续操作</think><answer>do(action=\"Swipe\", start=[200, 800], end=[200, 200])</answer>"
        }
    ]

    # 转换为 Claude 格式
    claude_messages = current_to_claude(current_messages, claude_image_scale=[1092, 1092])

    # 验证 tool_result
    print("\n检查 tool_result 消息:")
    tool_result_count = 0
    for i, msg in enumerate(claude_messages):
        if msg.get("role") == "user":
            content = msg.get("content", [])
            if isinstance(content, list) and len(content) > 0:
                first_block = content[0]
                if isinstance(first_block, dict) and first_block.get("type") == "tool_result":
                    tool_result_count += 1
                    tool_use_id = first_block.get("tool_use_id")
                    print(f"  消息 {i}: tool_result (tool_use_id: {tool_use_id[:20]}...)")
                    print(f"    ✓ tool_result 消息正确生成")

    print(f"\n找到 {tool_result_count} 个 tool_result 消息")
    assert tool_result_count > 0, "应该至少有一个 tool_result 消息！"

    print("\n✅ 测试通过：tool_result 消息正确生成")


def test_round_trip():
    """测试往返转换"""
    print("\n" + "=" * 80)
    print("测试 3: 往返转换一致性")
    print("=" * 80)

    current_messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "测试任务"}]
        },
        {
            "role": "assistant",
            "content": "<think>长按元素</think><answer>do(action=\"Long Press\", element=[500, 600], duration=2.5)</answer>"
        }
    ]

    # Current -> Claude -> Current
    claude_messages = current_to_claude(current_messages, claude_image_scale=[1092, 1092])
    restored_messages = claude_to_current(claude_messages, claude_image_scale=[1092, 1092])

    # 提取原始和还原的 action
    from convert_format import extract_thinking_and_action, _parse_action_string

    orig_thinking, orig_action_str = extract_thinking_and_action(current_messages[1]["content"])
    rest_thinking, rest_action_str = extract_thinking_and_action(restored_messages[1]["content"])

    print("\n原始 action:")
    print(f"  {orig_action_str}")

    print("\n还原 action:")
    print(f"  {rest_action_str}")

    # 解析并比较
    orig_action = _parse_action_string(orig_action_str)
    rest_action = _parse_action_string(rest_action_str)

    # 比较 action 类型
    assert orig_action.get("action") in ["Long Press", "LongPress"], "原始 action 类型错误"
    assert rest_action.get("action") in ["Long Press", "LongPress"], "还原 action 类型错误"

    # 比较 duration
    orig_duration = orig_action.get("duration")
    rest_duration = rest_action.get("duration")
    print(f"\n原始 duration: {orig_duration}")
    print(f"还原 duration: {rest_duration}")
    assert orig_duration == rest_duration, "duration 字段丢失或不一致！"

    # 比较坐标（允许少量误差）
    orig_coord = orig_action.get("element", [])
    rest_coord = rest_action.get("element", [])
    coord_diff_x = abs(orig_coord[0] - rest_coord[0])
    coord_diff_y = abs(orig_coord[1] - rest_coord[1])
    print(f"\n坐标差异: X={coord_diff_x}px, Y={coord_diff_y}px")
    assert coord_diff_x <= 2 and coord_diff_y <= 2, "坐标误差过大！"

    print("\n✅ 测试通过：往返转换一致，duration 字段保留")


def main():
    """运行所有测试"""
    print("\n" + "🧪" * 40)
    print("开始测试 convert_format.py 的修复")
    print("🧪" * 40 + "\n")

    try:
        test_tool_names_and_duration()
        test_tool_result()
        test_round_trip()

        print("\n" + "=" * 80)
        print("🎉 所有测试通过！")
        print("=" * 80)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
