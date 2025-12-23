"""
测试judge_from_full_context函数

这个脚本演示如何使用简化的judge_from_full_context函数
"""

import json


def create_sample_full_context():
    """创建一个示例的full_context用于测试"""
    full_context = [
        # System message
        {
            "role": "system",
            "content": "You are a GUI agent that helps users complete tasks on mobile devices."
        },
        # User message with screenshot
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "打开微信\n\n** Screen Info **\n\nCurrent App: Launcher"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                    }
                }
            ]
        },
        # Assistant message
        {
            "role": "assistant",
            "content": "<think>需要在主屏幕上找到微信图标并点击</think><answer>do(action=\"Tap\", element=[500, 300])</answer>"
        },
        # Another user message with screenshot
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "** Screen Info **\n\nCurrent App: WeChat"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                    }
                }
            ]
        },
        # Final assistant message to be judged
        {
            "role": "assistant",
            "content": "<think>微信已经打开,任务完成</think><answer>finish(message=\"已成功打开微信\")</answer>"
        }
    ]
    return full_context


def test_basic_functionality():
    """测试基本功能"""
    from judge_tools.judge import judge_from_full_context

    print("="*60)
    print("测试1: 基本功能测试")
    print("="*60)

    full_context = create_sample_full_context()

    print(f"\nFull context包含 {len(full_context)} 条消息:")
    for i, msg in enumerate(full_context):
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, list):
            print(f"  {i+1}. {role}: [包含 {len(content)} 个内容块]")
        else:
            preview = content[:50] + "..." if len(content) > 50 else content
            print(f"  {i+1}. {role}: {preview}")

    print("\n调用judge_from_full_context...")
    try:
        result = judge_from_full_context(
            full_context=full_context,
            history_images_k=2,  # 只保留最近2个user message的图片
        )

        print("\n✅ 判断成功!")
        print(f"Verdict: {result.get('verdict')}")
        print(f"Model Score: {result.get('model_score')}")
        print(f"Model Confidence: {result.get('model_confidence')}")
        print(f"Loop Detected: {result.get('loop_detected')}")
        if result.get('repair_suggestions'):
            print(f"Repair Suggestions: {result.get('repair_suggestions')[:100]}...")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_history_images_filtering():
    """测试history_images_k过滤功能"""
    from judge_tools.judge import judge_from_full_context

    print("\n" + "="*60)
    print("测试2: history_images_k过滤功能")
    print("="*60)

    # 创建包含多个user message的context
    full_context = [
        {"role": "system", "content": "System prompt"},
    ]

    # 添加5个user message,每个都有图片
    for i in range(1, 6):
        full_context.append({
            "role": "user",
            "content": [
                {"type": "text", "text": f"Step {i}"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,step{i}"
                    }
                }
            ]
        })
        full_context.append({
            "role": "assistant",
            "content": f"<think>Processing step {i}</think><answer>do(action=\"Tap\", element=[100, 100])</answer>"
        })

    print(f"\n创建了包含5个user message的context")
    print(f"测试history_images_k=3,应该只保留最后3个user message的图片")

    # 注意: 这个测试只是为了验证函数接受参数,实际判断需要调用API
    # 在生产环境中你可以检查发送给API的消息中图片数量是否正确
    print("\n提示: 此测试需要有效的API密钥才能完整运行")
    print("如果你有API密钥,请取消注释下面的代码:")
    print("""
    try:
        result = judge_from_full_context(
            full_context=full_context,
            history_images_k=3,
        )
        print("✅ 测试通过!")
    except Exception as e:
        print(f"⚠️  {e}")
    """)


def test_empty_context():
    """测试空context的错误处理"""
    from judge_tools.judge import judge_from_full_context

    print("\n" + "="*60)
    print("测试3: 空context错误处理")
    print("="*60)

    try:
        result = judge_from_full_context(full_context=[])
        print("❌ 应该抛出错误但没有")
    except ValueError as e:
        print(f"✅ 正确捕获错误: {e}")
    except Exception as e:
        print(f"⚠️  捕获了意外的错误类型: {e}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("judge_from_full_context 函数测试")
    print("="*60)
    print()

    # 测试空context
    test_empty_context()

    # 测试history_images过滤
    test_history_images_filtering()

    # 注意: 基本功能测试需要有效的API密钥
    print("\n" + "="*60)
    print("注意: 完整功能测试需要有效的judge API密钥")
    print("如果你想运行完整测试,请设置环境变量或修改judge.py中的默认配置")
    print("="*60)

    # 如果你有API密钥,取消注释下面这行
    # test_basic_functionality()
