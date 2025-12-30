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
    ################################################################ 测试model_client
    # # 读取trace，收集消息，并转换为Claude格式
    # messages, image_scale = gather_message_from_trace(trace_file, 10, target_width=target_width, history_images_k=10)
    # with open('messages.json', 'wt+') as f:
    #     json.dump(messages, f, ensure_ascii=False, indent=2)
    
    # ##### 尝试1：失败尝试，无法直接继续用claude API，thinking中有signature
    # # claude_messages = current_to_claude(messages, image_scale=image_scale)
    # # claude_messages = claude_messages[0:3]
    # # with open('claude_messages.json', 'wt+') as f:
    # #     json.dump(claude_messages, f, ensure_ascii=False, indent=2)
    # # 调用Claude API
    # ##### 尝试2：messages最后的user加上prmopt，如果没有符合格式的话，依然无法正确输出（带thinking signature的格式）
    
    # # 将所有messages合并到一个user message中
    # merged_content = []
    
    # # 在最开始添加一个text message，表明这是之前的轨迹
    # merged_content.append({
    #     'type': 'text',
    #     'text': '以下是之前Agent执行的轨迹记录：'
    # })
    
    # # 遍历所有messages，按照text, image, text的循环格式合并
    # for msg in messages:
    #     role = msg.get('role', 'user')  # 默认为user
    #     content = msg.get('content', [])
        
    #     # 处理content数组
    #     if type(content) == str:
    #         merged_content.append({
    #             'type': 'text',
    #             'text': content
    #         })
    #     else:
    #         for item in content:
    #             if item.get('type') == 'text':
    #                 # 为text添加标志，表示是user还是assistant的消息
    #                 text_content = item.get('text', '')
    #                 role_label = '[USER]' if role == 'user' else '[ASSISTANT]'
    #                 merged_content.append({
    #                     'type': 'text',
    #                     'text': f'{role_label} {text_content}'
    #                 })
    #             elif item.get('type') == 'image':
    #                 # 直接添加image
    #                 merged_content.append(item)
        
    # # 创建新的messages列表，只包含一个user message
    # messages = [{
    #     'role': 'user',
    #     'content': merged_content
    # }]
    
    # continue_prompt = f'以上为之前Agent执行的trace，他使用的是不同的工具调用格式，请完成他的任务'
    # messages[-1]['content'].append({
    #     'type': 'text',
    #     'text': continue_prompt
    # })


    # model_client = ModelClient(
    #     api_key=api_key,
    #     model=model,
    #     api_url=api_url,
    #     target_width=target_width,
    #     trace_dir='./traces'
    # )
    # response = model_client.call_model(
    #     context=messages,
    #     screenshot_base64=None,
    #     current_package_name='',
    #     user_prompt=task
    # )
    # print(f'response: {response}')
    # # 保存响应
    # with open('response.json', 'wt+') as f:
    #     json.dump(response, f, ensure_ascii=False, indent=2)
    ################################################################


    agent = HDCTakeover(
        context=None,
        api_key=api_key,
        model=model,
        target_width=target_width,
        max_iterations=max_iterations,
        trace_dir='./traces'
    )
    context = agent.load_context_from_trace(trace_file, history_images_k=10)
    result = agent.run(task='')
    print(result)