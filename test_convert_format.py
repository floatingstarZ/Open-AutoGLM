"""
测试convert_format.py的格式转换功能
"""

import json
import sys
from judge_tools.convert_format import current_to_claude, claude_to_current

def load_claude_format(file_path):
    """加载Claude格式的对话历史"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_trace_format(file_path):
    """加载trace格式的对话历史（读取最后一行的model_input）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        last_line = lines[-1]
        data = json.loads(last_line)
        return data.get('model_input', [])

def compare_formats(claude_messages, trace_messages):
    """对比两种格式的差异"""
    print("=" * 80)
    print("格式对比")
    print("=" * 80)

    print(f"\nClaude格式消息数: {len(claude_messages)}")
    print(f"Trace格式消息数: {len(trace_messages)}")

    # 对比每条消息
    for i, (claude_msg, trace_msg) in enumerate(zip(claude_messages, trace_messages)):
        print(f"\n消息 {i}:")
        print(f"  Claude role: {claude_msg.get('role')}")
        print(f"  Trace role: {trace_msg.get('role')}")

        if claude_msg.get('role') != trace_msg.get('role'):
            print(f"  ⚠️  角色不匹配!")
            continue

        role = claude_msg.get('role')

        if role == 'system':
            # system消息都是字符串
            print(f"  两者都是system消息")

        elif role == 'user':
            # user消息都是content数组
            claude_content = claude_msg.get('content', [])
            trace_content = trace_msg.get('content', [])

            print(f"  Claude content项数: {len(claude_content)}")
            print(f"  Trace content项数: {len(trace_content)}")

            # 检查每个content项
            for j, (c_item, t_item) in enumerate(zip(claude_content, trace_content)):
                c_type = c_item.get('type')
                t_type = t_item.get('type')
                print(f"    项 {j}: Claude type={c_type}, Trace type={t_type}")

                if c_type == 'image':
                    print(f"      Claude有image (source with {len(c_item.get('source', {}).get('data', ''))} bytes)")

        elif role == 'assistant':
            # assistant消息格式不同
            claude_content = claude_msg.get('content')
            trace_content = trace_msg.get('content')

            if isinstance(claude_content, list):
                print(f"  Claude content是列表，包含 {len(claude_content)} 项")
                for item in claude_content:
                    print(f"    - {item.get('type')}")
            else:
                print(f"  Claude content类型: {type(claude_content)}")

            if isinstance(trace_content, str):
                print(f"  Trace content是字符串")
                # 提取think和answer
                import re
                think_match = re.search(r'<think>(.*?)</think>', trace_content, re.DOTALL)
                answer_match = re.search(r'<answer>(.*?)</answer>', trace_content, re.DOTALL)
                if think_match:
                    print(f"    有thinking")
                if answer_match:
                    print(f"    有answer: {answer_match.group(1).strip()[:50]}...")
            else:
                print(f"  Trace content类型: {type(trace_content)}")

def test_conversion():
    """测试格式转换"""
    print("\n" + "=" * 80)
    print("测试 Claude格式 -> Current格式 转换")
    print("=" * 80)

    # 加载Claude格式
    claude_file = '/Users/huangziyue/CodeGeeXProjects/claude-for-phone/full_logs/20251224142941.json'
    claude_messages = load_claude_format(claude_file)

    print(f"\n原始Claude格式: {len(claude_messages)} 条消息")

    # 转换为Current格式
    # 注意：需要知道图片分辨率来正确转换坐标
    # 从第一条user消息中提取图片尺寸
    image_scale = None
    for msg in claude_messages:
        if msg.get('role') == 'user':
            for item in msg.get('content', []):
                if item.get('type') == 'image':
                    # 假设从system-reminder中提取了尺寸信息
                    # 这里我们使用固定值
                    image_scale = [512, 1139]  # 从system-reminder看到的尺寸
                    break
            if image_scale:
                break

    if not image_scale:
        print("警告: 未找到图片尺寸信息，使用默认值 [1084, 2412]")
        image_scale = [1084, 2412]

    print(f"图片分辨率: {image_scale}")

    # 只转换前5条消息作为示例
    claude_sample = claude_messages[:5]
    current_messages = claude_to_current(claude_sample, claude_image_scale=image_scale)

    print(f"\n转换后的Current格式: {len(current_messages)} 条消息")

    # 打印转换结果
    for i, msg in enumerate(current_messages):
        print(f"\n消息 {i} ({msg['role']}):")
        if msg['role'] == 'assistant':
            content = msg.get('content', '')
            if isinstance(content, str) and len(content) > 200:
                print(f"  {content[:200]}...")
            else:
                print(f"  {content}")

    # 测试往返转换
    print("\n" + "=" * 80)
    print("测试往返转换 (Current -> Claude -> Current)")
    print("=" * 80)

    claude_back = current_to_claude(current_messages, claude_image_scale=image_scale)
    current_back = claude_to_current(claude_back, claude_image_scale=image_scale)

    # 验证assistant消息的一致性
    for i, (orig, back) in enumerate(zip(current_messages, current_back)):
        if orig['role'] == 'assistant':
            print(f"\n消息 {i}:")
            print(f"  原始: {orig['content'][:100]}...")
            print(f"  往返: {back['content'][:100]}...")
            print(f"  一致: {orig['content'] == back['content']}")

if __name__ == '__main__':
    # 首先对比两种格式的差异
    claude_file = '/Users/huangziyue/CodeGeeXProjects/claude-for-phone/full_logs/20251224142941.json'
    trace_file = '/Users/huangziyue/Open-AutoGLM/traces/task_20251224_1447/trace.jsonl'

    try:
        claude_messages = load_claude_format(claude_file)
        trace_messages = load_trace_format(trace_file)

        # 只对比前10条消息
        compare_formats(claude_messages[:10], trace_messages[:10])
    except Exception as e:
        print(f"对比格式时出错: {e}")
        import traceback
        traceback.print_exc()

    # 测试转换功能
    try:
        test_conversion()
    except Exception as e:
        print(f"测试转换时出错: {e}")
        import traceback
        traceback.print_exc()
