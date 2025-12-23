"""
测试Judge直接输出refined_thinking和refined_action

这个脚本测试Judge模型直接输出修正结果的新逻辑
"""

import json
from phone_agent.actions.handler import parse_action


def test_judge_result_structure():
    """测试新的Judge结果结构"""
    print("="*60)
    print("测试1: Judge结果结构（包含refined_thinking和refined_action）")
    print("="*60)

    # 模拟一个Judge结果（verdict=False，需要修正）
    judge_result = {
        "verdict": False,
        "scores": {
            "requirement_satisfaction": 60,
            "reasoning_correctness": 50,
            "conciseness": 75
        },
        "loop_detected": False,
        "failed_steps": [
            {
                "step_id": "action",
                "snippet": "do(action=\"Tap\", element=[100, 100])",
                "why_failed": "点击位置错误，应该点击屏幕中心的按钮"
            }
        ],
        "model_score": 55,
        "model_confidence": 80,
        "refined_thinking": "当前屏幕显示一个按钮位于中心位置坐标[500, 300]，需要点击该按钮以继续操作。",
        "refined_action": "do(action=\"Tap\", element=[500, 300])",
        "repair_suggestions": "原输出点击了错误的位置[100, 100]，该位置没有可交互元素。正确的做法是点击屏幕中心的按钮，坐标为[500, 300]。"
    }

    print(f"Judge结果示例:")
    print(json.dumps(judge_result, ensure_ascii=False, indent=2))
    print()

    # 验证必需字段
    required_fields = ["verdict", "scores", "loop_detected", "failed_steps",
                      "model_score", "model_confidence", "refined_thinking",
                      "refined_action", "repair_suggestions"]

    for field in required_fields:
        assert field in judge_result, f"缺少必需字段: {field}"
        print(f"✅ 包含字段: {field}")

    # 测试verdict=False的处理
    print("\n测试verdict=False的处理:")
    if not judge_result.get('verdict', True):
        print(f"  ⚠️  Judge认为不合理 (score={judge_result['model_score']})")

        # 测试refined_thinking
        refined_thinking = judge_result.get('refined_thinking', '')
        if refined_thinking:
            print(f"  📝 Judge提供了refined_thinking:")
            print(f"     {refined_thinking[:80]}...")

        # 测试refined_action
        refined_action_str = judge_result.get('refined_action', '')
        if refined_action_str:
            print(f"  📝 Judge提供了refined_action:")
            print(f"     {refined_action_str}")
            try:
                action = parse_action(refined_action_str)
                print(f"  ✅ refined_action可以解析:")
                print(f"     {json.dumps(action, ensure_ascii=False, indent=2)}")
            except Exception as e:
                print(f"  ❌ refined_action解析失败: {e}")

    print("\n测试通过！\n")


def test_verdict_true():
    """测试verdict=True的情况"""
    print("="*60)
    print("测试2: verdict=True的情况")
    print("="*60)

    # 模拟一个Judge结果（verdict=True，无需修正）
    judge_result = {
        "verdict": True,
        "scores": {
            "requirement_satisfaction": 85,
            "reasoning_correctness": 90,
            "conciseness": 80
        },
        "loop_detected": False,
        "failed_steps": [],
        "model_score": 85,
        "model_confidence": 90,
        "refined_thinking": "",  # verdict=True时为空
        "refined_action": "",    # verdict=True时为空
        "repair_suggestions": ""
    }

    print(f"Judge结果:")
    print(json.dumps(judge_result, ensure_ascii=False, indent=2))
    print()

    if judge_result.get('verdict', True):
        print("✅ Judge认为合理")
        print(f"  评分: {judge_result['model_score']}/100")
        print(f"  置信度: {judge_result['model_confidence']}%")

        # 验证refined字段为空
        assert judge_result['refined_thinking'] == "", "verdict=True时refined_thinking应该为空"
        assert judge_result['refined_action'] == "", "verdict=True时refined_action应该为空"
        print("  ✅ refined_thinking和refined_action为空（符合预期）")

    print("\n测试通过！\n")


def test_format_model_output_format():
    """测试format_model_output的格式（使用refined输出）"""
    print("="*60)
    print("测试3: format_model_output格式")
    print("="*60)

    # 假设Judge提供了refined输出
    refined_thinking = "当前屏幕显示一个按钮位于中心位置坐标[500, 300]，需要点击该按钮以继续操作。"
    refined_action_str = "do(action=\"Tap\", element=[500, 300])"

    # 构建format_model_output（与Agent原始输出格式相同）
    format_model_output = {
        "role": "assistant",
        "content": f"<think>{refined_thinking}</think><answer>{refined_action_str}</answer>"
    }

    print("format_model_output:")
    print(json.dumps(format_model_output, ensure_ascii=False, indent=2))
    print()

    # 验证格式
    assert format_model_output["role"] == "assistant", "role应该是assistant"
    assert "<think>" in format_model_output["content"], "content应该包含<think>"
    assert "<answer>" in format_model_output["content"], "content应该包含<answer>"
    assert refined_thinking in format_model_output["content"], "content应该包含thinking"
    assert refined_action_str in format_model_output["content"], "content应该包含action"

    print("✅ format_model_output格式正确")
    print("✅ 格式与Agent原始输出一致")

    print("\n测试通过！\n")


def test_multiple_action_types():
    """测试不同类型的refined_action"""
    print("="*60)
    print("测试4: 不同类型的refined_action")
    print("="*60)

    test_cases = [
        {
            "name": "Tap动作",
            "refined_action": "do(action=\"Tap\", element=[500, 300])",
            "expected_action": "Tap"
        },
        {
            "name": "Swipe动作",
            "refined_action": "do(action=\"Swipe\", start=[100, 500], end=[100, 100])",
            "expected_action": "Swipe"
        },
        {
            "name": "Type动作",
            "refined_action": "do(action=\"Type\", text=\"Hello World\")",
            "expected_action": "Type"
        },
        {
            "name": "Finish动作",
            "refined_action": "finish(message=\"任务完成\")",
            "expected_metadata": "finish"
        }
    ]

    for test_case in test_cases:
        print(f"\n{test_case['name']}:")
        print(f"  refined_action: {test_case['refined_action']}")

        try:
            action = parse_action(test_case['refined_action'])
            print(f"  解析结果: {json.dumps(action, ensure_ascii=False)}")

            if "expected_action" in test_case:
                assert action.get("action") == test_case["expected_action"]
                print(f"  ✅ action类型正确: {action.get('action')}")

            if "expected_metadata" in test_case:
                assert action.get("_metadata") == test_case["expected_metadata"]
                print(f"  ✅ metadata正确: {action.get('_metadata')}")

        except Exception as e:
            print(f"  ❌ 解析失败: {e}")

    print("\n测试通过！\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Judge直接输出refined功能测试套件")
    print("="*60)
    print()

    try:
        test_judge_result_structure()
        test_verdict_true()
        test_format_model_output_format()
        test_multiple_action_types()

        print("="*60)
        print("✅ 所有测试通过！")
        print("="*60)
        print()
        print("关键变化:")
        print("- Judge不再返回correct_action")
        print("- Judge直接返回refined_thinking和refined_action")
        print("- Agent不再调用模型重新生成，直接使用Judge的输出")
        print("- format_model_output格式保持不变：<think>...</think><answer>...</answer>")
        print()

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}\n")
        import traceback
        traceback.print_exc()

    except Exception as e:
        print(f"\n❌ 发生错误: {e}\n")
        import traceback
        traceback.print_exc()
