import sys
sys.path.append('../')
from claude_takeover.adb_takeover import ADBTakeover
from claude_takeover.model_client import ModelClient
from claude_takeover.system_prompt import SYSTEM_PROMPT
from claude_takeover.tools import TOOLS
from claude_takeover.hdc_takeover import HDCTakeover
import json
from judge_tools.convert_format import current_to_claude, gather_message_from_trace



if __name__ == '__main__':
    api_key = 'sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn'
    model = 'claude-sonnet-4-5-20250929'
    api_url = 'https://api-gateway.glm.ai/v1/messages'
    target_width = 512
    max_iterations = 100
    trace_file = '/Users/huangziyue/Open-AutoGLM/traces/task_20251229_1056/trace.jsonl'
    task = '打开淘宝，搜索手机'
    # 读取trace，收集消息，并转换为Claude格式
    messages, image_scale = gather_message_from_trace(trace_file, 10, target_width=target_width, history_images_k=10)
    with open('messages.json', 'wt+') as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    claude_messages = current_to_claude(messages, image_scale=image_scale)
    claude_messages = claude_messages[0:3]
    
    # with open('claude_messages.json', 'wt+') as f:
    #     json.dump(claude_messages, f, ensure_ascii=False, indent=2)
    with open('claude_messages.json', 'r') as f:
        claude_messages = json.load(f)
    # 调用Claude API
    model_client = ModelClient(
        api_key=api_key,
        model=model,
        api_url=api_url,
        target_width=target_width,
        trace_dir='./traces'
    )
    response = model_client.call_model(
        context=claude_messages,
        screenshot_base64=None,
        current_package_name='',
        user_prompt=task
    )
    # 保存响应
    with open('response.json', 'wt+') as f:
        json.dump(response, f, ensure_ascii=False, indent=2)

    # agent = HDCTakeover(
    #     context=context,
    #     api_key=api_key,
    #     model=model,
    #     target_width=target_width,
    #     max_iterations=max_iterations,
    #     trace_dir=trace_dir
    # )
    # result = agent.run(task=task)
    # print(result)