import json

src_pth = f'/Users/huangziyue/CodeGeeXProjects/claude-for-phone/data.json'
to_check_pth = f'/Users/huangziyue/Open-AutoGLM/claude_takeover/data.json'
with open(src_pth, 'r') as f:
    src_messages = json.load(f)
with open(to_check_pth, 'r') as f:
    to_check_messages = json.load(f)

print(src_messages.keys())
print(to_check_messages.keys())
for key in ['max_tokens', 'system', 'thinking', 'tools', 'model']:
    # print(f'{key}: {src_messages[key]}')
    # print(f'{key}: {to_check_messages[key]}')
    print('-' * 50)
    if str(src_messages[key]) != str(to_check_messages[key]):
        print(f'{key} is different')
        # print(f'src_messages[key]: {src_messages[key]}')
        # print('-' * 50)
        # print(f'to_check_messages[key]: {to_check_messages[key]}')
