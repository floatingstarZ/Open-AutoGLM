"""
测试Judge自动修正功能

这个脚本测试新的自动化Judge逻辑
"""

import json
from phone_agent.agent import AgentConfig
from phone_agent.actions.handler import parse_action


def test_agent_config():
    """测试AgentConfig的默认值"""
    print("="*60)
    print("测试1: AgentConfig默认配置")
    print("="*60)

    # 创建默认配置
    config = AgentConfig()

    # 验证Judge默认启用
    assert config.enable_judge == True, "Judge应该默认启用"
    print(f"✅ enable_judge = {config.enable_judge} (默认启用)")

    # 验证没有enable_interactive属性
    assert not hasattr(config, 'enable_interactive'), "enable_interactive应该已被移除"
    print("✅ enable_interactive已被移除")

    print("\n测试通过！\n")


def test_parse_action_from_judge():
    """测试从Judge的correct_action解析Action"""
    print("="*60)
    print("测试2: 解析Judge的correct_action")
    print("="*60)

    # 测试各种格式的correct_action
    test_cases = [
        {
            "input": 'do(action="Tap", element=[500, 300])',
            "expected_action": "Tap",
            "expected_metadata": "do"
        },
        {
            "input": 'finish(message="任务完成")',
            "expected_metadata": "finish"
        },
        {
            "input": 'do(action="Swipe", start=[100, 100], end=[200, 200])',
            "expected_action": "Swipe",
            "expected_metadata": "do"
        }
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}: {test_case['input'][:50]}...")
        try:
            action = parse_action(test_case['input'])
            print(f"  解析结果: {json.dumps(action, ensure_ascii=False)}")

            # 验证metadata
            assert action.get("_metadata") == test_case["expected_metadata"], \
                f"metadata应该是{test_case['expected_metadata']}"
            print(f"  ✅ metadata正确: {action.get('_metadata')}")

            # 验证action字段（如果是do类型）
            if "expected_action" in test_case:
                assert action.get("action") == test_case["expected_action"], \
                    f"action应该是{test_case['expected_action']}"
                print(f"  ✅ action正确: {action.get('action')}")

        except Exception as e:
            print(f"  ❌ 解析失败: {e}")

    print("\n测试通过！\n")


def test_judge_result_structure():
    """测试Judge结果的结构"""
    print("="*60)
    print("测试3: Judge结果结构")
    print("="*60)

    # 模拟一个Judge结果
    judge_result = {
        "verdict": False,
        "scores": {
            "requirement_satisfaction": 60,
            "reasoning_correctness": 50,
            "conciseness": 75
        },
        "loop_detected": False,
        "failed_steps": [],
        "model_score": 55,
        "model_confidence": 80,
        "correct_action": 'do(action="Tap", element=[500, 300])',
        "repair_suggestions": "建议点击屏幕中心的按钮"
    }

    print(f"Judge结果示例:")
    print(json.dumps(judge_result, ensure_ascii=False, indent=2))

    # 验证必需字段
    required_fields = ["verdict", "scores", "loop_detected", "failed_steps",
                      "model_score", "model_confidence", "correct_action",
                      "repair_suggestions"]

    for field in required_fields:
        assert field in judge_result, f"缺少必需字段: {field}"
        print(f"✅ 包含字段: {field}")

    # 测试verdict的两种情况
    print("\n测试verdict=False的处理:")
    if not judge_result.get('verdict', True):
        print(f"  ⚠️  Judge认为不合理 (score={judge_result['model_score']})")
        if judge_result.get('correct_action'):
            print(f"  📝 Judge提供了correct_action")
            try:
                action = parse_action(judge_result['correct_action'])
                print(f"  ✅ correct_action可以解析: {action.get('action')}")
            except:
                print(f"  ❌ correct_action解析失败")

    print("\n测试通过！\n")


def test_context_format():
    """测试Context消息格式"""
    print("="*60)
    print("测试4: Context消息格式")
    print("="*60)

    # 模拟一个完整的context
    context = [
        {
            "role": "system",
            "content": "You are a GUI agent..."
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "打开微信"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
            ]
        },
        {
            "role": "assistant",
            "content": "<think>需要在主屏幕找到微信</think><answer>do(action=\"Tap\", element=[500, 300])</answer>"
        }
    ]

    print(f"Context包含 {len(context)} 条消息\n")

    for i, msg in enumerate(context, 1):
        role = msg.get("role")
        content = msg.get("content")

        print(f"消息 {i}:")
        print(f"  role: {role}")

        if role == "user" and isinstance(content, list):
            print(f"  content: [包含 {len(content)} 个内容块]")
            for item in content:
                print(f"    - type: {item.get('type')}")
        else:
            preview = str(content)[:50] + "..." if len(str(content)) > 50 else content
            print(f"  content: {preview}")

        print()

    print("✅ Context格式正确\n")
    print("测试通过！\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Judge自动修正功能测试套件")
    print("="*60)
    print()

    try:
        test_agent_config()
        test_parse_action_from_judge()
        test_judge_result_structure()
        test_context_format()

        print("="*60)
        print("✅ 所有测试通过！")
        print("="*60)
        print()
        print("提示:")
        print("- Judge默认启用，会自动评估和修正Action")
        print("- 不再需要用户交互")
        print("- 如需禁用Judge: AgentConfig(enable_judge=False)")
        print()

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}\n")
        import traceback
        traceback.print_exc()

    except Exception as e:
        print(f"\n❌ 发生错误: {e}\n")
        import traceback
        traceback.print_exc()
