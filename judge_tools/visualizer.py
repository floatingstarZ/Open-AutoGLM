"""
Judge输入输出可视化工具

支持两种模式：
1. HTML生成模式：生成静态HTML文件
2. Web服务模式：启动简单的HTTP服务器查看

使用方法：
    # 生成HTML文件
    python visualizer.py <judge_io.json> --html

    # 启动web服务
    python visualizer.py <judge_io.json> --serve --port 8000

    # 可视化整个trace目录（所有judge结果）
    python visualizer.py <trace_dir> --all
"""

import argparse
import base64
import json
import os
import re
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any


def extract_text_from_message(content: Any) -> str:
    """从消息内容中提取纯文本"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return "\n".join(text_parts)
    return str(content)


def count_images_in_message(content: Any) -> int:
    """统计消息中的图片数量"""
    if isinstance(content, list):
        return sum(1 for item in content if isinstance(item, dict) and item.get("type") == "image_url")
    return 0


def generate_html(judge_io_data: dict[str, Any], output_path: str) -> None:
    """生成HTML可视化文件"""

    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Judge 输入输出可视化</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
        }}

        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}

        .header .meta {{
            opacity: 0.9;
            font-size: 14px;
        }}

        .section {{
            padding: 30px;
            border-bottom: 1px solid #e0e0e0;
        }}

        .section:last-child {{
            border-bottom: none;
        }}

        .section-title {{
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 20px;
            color: #667eea;
            display: flex;
            align-items: center;
        }}

        .section-title::before {{
            content: "";
            width: 4px;
            height: 20px;
            background: #667eea;
            margin-right: 10px;
            border-radius: 2px;
        }}

        .message {{
            margin-bottom: 20px;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #ddd;
        }}

        .message.system {{
            background: #f8f9fa;
            border-left-color: #6c757d;
        }}

        .message.user {{
            background: #e3f2fd;
            border-left-color: #2196F3;
        }}

        .message.assistant {{
            background: #f3e5f5;
            border-left-color: #9c27b0;
        }}

        .message-header {{
            display: flex;
            align-items: center;
            margin-bottom: 10px;
            font-weight: 600;
        }}

        .role-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            margin-right: 10px;
        }}

        .role-badge.system {{
            background: #6c757d;
            color: white;
        }}

        .role-badge.user {{
            background: #2196F3;
            color: white;
        }}

        .role-badge.assistant {{
            background: #9c27b0;
            color: white;
        }}

        .message-content {{
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 14px;
            line-height: 1.6;
            color: #444;
        }}

        .images {{
            margin-top: 15px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}

        .image-container {{
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            overflow: hidden;
            background: #fafafa;
        }}

        .image-container img {{
            max-width: 1024px;
            max-height: 1024px;
            width: auto;
            height: auto;
            display: block;
            cursor: pointer;
            transition: transform 0.2s;
        }}

        .image-container img:hover {{
            transform: scale(1.02);
        }}

        .image-label {{
            padding: 8px;
            font-size: 12px;
            color: #666;
            background: #f5f5f5;
            text-align: center;
        }}

        .result-card {{
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
        }}

        .result-row {{
            display: flex;
            margin-bottom: 12px;
            align-items: flex-start;
        }}

        .result-label {{
            font-weight: 600;
            color: #495057;
            min-width: 180px;
            flex-shrink: 0;
        }}

        .result-value {{
            color: #212529;
        }}

        .verdict-badge {{
            display: inline-block;
            padding: 6px 16px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 14px;
        }}

        .verdict-badge.true {{
            background: #d4edda;
            color: #155724;
        }}

        .verdict-badge.false {{
            background: #f8d7da;
            color: #721c24;
        }}

        .score-bar {{
            width: 100%;
            max-width: 300px;
            height: 24px;
            background: #e9ecef;
            border-radius: 12px;
            overflow: hidden;
            position: relative;
        }}

        .score-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 12px;
            font-weight: 600;
            transition: width 0.3s ease;
        }}

        .failed-steps {{
            background: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 8px;
            padding: 15px;
            margin-top: 10px;
        }}

        .failed-step {{
            margin-bottom: 10px;
            padding: 10px;
            background: white;
            border-radius: 4px;
        }}

        .failed-step:last-child {{
            margin-bottom: 0;
        }}

        .correct-action {{
            background: #d1ecf1;
            border: 1px solid #17a2b8;
            border-radius: 8px;
            padding: 15px;
            margin-top: 10px;
        }}

        .refined-thinking {{
            background: #e7f3ff;
            border: 1px solid #0066cc;
            border-radius: 8px;
            padding: 15px;
            margin-top: 10px;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}

        .refined-action {{
            background: #d1ecf1;
            border: 1px solid #17a2b8;
            border-radius: 8px;
            padding: 15px;
            margin-top: 10px;
        }}

        .reasoning-content {{
            margin-top: 10px;
        }}

        .reasoning-content pre {{
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            padding: 15px;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 13px;
            line-height: 1.6;
            max-height: 600px;
            overflow-y: auto;
        }}

        .correct-action pre {{
            background: white;
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
            margin-top: 8px;
        }}

        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}

        .stat-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}

        .stat-label {{
            font-size: 12px;
            color: #6c757d;
            margin-bottom: 5px;
        }}

        .stat-value {{
            font-size: 24px;
            font-weight: 700;
            color: #212529;
        }}

        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.9);
            cursor: pointer;
        }}

        .modal img {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            max-width: 90%;
            max-height: 90%;
        }}

        .tag {{
            display: inline-block;
            padding: 4px 10px;
            background: #e9ecef;
            border-radius: 12px;
            font-size: 12px;
            margin-right: 8px;
            color: #495057;
        }}

        .tag.warning {{
            background: #fff3cd;
            color: #856404;
        }}

        @media (max-width: 768px) {{
            .container {{
                margin: 0;
                border-radius: 0;
            }}

            .section {{
                padding: 20px;
            }}

            .images {{
                grid-template-columns: 1fr;
            }}

            .stats {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Judge 输入输出可视化</h1>
            <div class="meta">
                <div>时间戳: {timestamp}</div>
                <div>截图路径: {screenshot_path}</div>
            </div>
        </div>

        <!-- 统计信息 -->
        <div class="section">
            <div class="section-title">📊 统计信息</div>
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-label">总消息数</div>
                    <div class="stat-value">{total_messages}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">包含图片的消息</div>
                    <div class="stat-value">{messages_with_images}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">总图片数</div>
                    <div class="stat-value">{total_images}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Token使用</div>
                    <div class="stat-value">{total_tokens}</div>
                </div>
            </div>
        </div>

        <!-- System Prompt -->
        <div class="section">
            <div class="section-title">⚙️ System Prompt</div>
            <div class="message system">
                <div class="message-header">
                    <span class="role-badge system">System</span>
                </div>
                <div class="message-content">{system_content}</div>
            </div>
        </div>

        <!-- 对话历史 -->
        <div class="section">
            <div class="section-title">💬 对话历史</div>
            {messages_html}
        </div>

        <!-- Judge结果 -->
        <div class="section">
            <div class="section-title">✅ Judge 评估结果</div>
            {judge_result_html}
        </div>

        <!-- 原始响应 -->
        <div class="section">
            <div class="section-title">📝 原始响应</div>
            <div class="result-card">
                <pre style="overflow-x: auto; font-size: 12px; line-height: 1.4;">{raw_response}</pre>
            </div>
        </div>
    </div>

    <!-- 图片模态框 -->
    <div id="imageModal" class="modal" onclick="closeModal()">
        <img id="modalImage" src="" alt="Full size image">
    </div>

    <script>
        function openModal(src) {{
            document.getElementById('imageModal').style.display = 'block';
            document.getElementById('modalImage').src = src;
        }}

        function closeModal() {{
            document.getElementById('imageModal').style.display = 'none';
        }}

        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                closeModal();
            }}
        }});
    </script>
</body>
</html>
"""

    # 提取数据
    timestamp = judge_io_data.get("timestamp", "Unknown")
    screenshot_path = judge_io_data.get("screenshot_path", "Unknown")
    input_data = judge_io_data.get("input", {})
    output_data = judge_io_data.get("output", {})

    system_message = input_data.get("system_message", {})
    messages = input_data.get("messages", [])
    judge_result = output_data.get("judge_result", {})
    raw_response = output_data.get("raw_response", {})

    # 统计信息
    total_messages = len(messages)
    messages_with_images = sum(1 for msg in messages if count_images_in_message(msg.get("content")) > 0)
    total_images = sum(count_images_in_message(msg.get("content")) for msg in messages)
    total_tokens = raw_response.get("usage", {}).get("total_tokens", 0)

    # 生成system content
    system_content = extract_text_from_message(system_message.get("content", ""))

    # 生成消息HTML
    messages_html_parts = []
    for idx, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        text_content = extract_text_from_message(content)
        image_count = count_images_in_message(content)

        message_html = f"""
        <div class="message {role}">
            <div class="message-header">
                <span class="role-badge {role}">{role}</span>
                <span style="color: #999; font-size: 12px;">Message #{idx + 1}</span>
                {f'<span class="tag">📷 {image_count} 张图片</span>' if image_count > 0 else ''}
            </div>
            <div class="message-content">{text_content if text_content else '<em>无文本内容</em>'}</div>
        """

        # 添加图片
        if isinstance(content, list):
            images_html = []
            img_idx = 0
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    img_url = item.get("image_url", {}).get("url", "")
                    img_idx += 1
                    images_html.append(f"""
                    <div class="image-container">
                        <img src="{img_url}" alt="Image {img_idx}" onclick="openModal(this.src)">
                        <div class="image-label">图片 {img_idx}</div>
                    </div>
                    """)

            if images_html:
                message_html += f"""
                <div class="images">
                    {''.join(images_html)}
                </div>
                """

        message_html += "</div>"
        messages_html_parts.append(message_html)

    messages_html = "\n".join(messages_html_parts)

    # 生成judge结果HTML
    verdict = judge_result.get("verdict", False)
    scores = judge_result.get("scores", {})
    loop_detected = judge_result.get("loop_detected", False)
    failed_steps = judge_result.get("failed_steps", [])
    model_score = judge_result.get("model_score", 0)
    model_confidence = judge_result.get("model_confidence", 0)
    # 支持新旧两种格式
    correct_action = judge_result.get("correct_action", "")
    refined_thinking = judge_result.get("refined_thinking", "")
    refined_action = judge_result.get("refined_action", "")
    repair_suggestions = judge_result.get("repair_suggestions", "")
    reasoning_content = judge_result.get("reasoning_content", "")

    judge_result_html = f"""
    <div class="result-card">
        <div class="result-row">
            <div class="result-label">最终判定 (Verdict):</div>
            <div class="result-value">
                <span class="verdict-badge {str(verdict).lower()}">
                    {'✅ 合理' if verdict else '❌ 不合理'}
                </span>
                {f'<span class="tag warning">⚠️ 检测到死循环</span>' if loop_detected else ''}
            </div>
        </div>

        <div class="result-row">
            <div class="result-label">模型评分:</div>
            <div class="result-value">
                <div class="score-bar">
                    <div class="score-fill" style="width: {model_score}%">{model_score}/100</div>
                </div>
            </div>
        </div>

        <div class="result-row">
            <div class="result-label">置信度:</div>
            <div class="result-value">
                <div class="score-bar">
                    <div class="score-fill" style="width: {model_confidence}%">{model_confidence}/100</div>
                </div>
            </div>
        </div>

        <div class="result-row">
            <div class="result-label">需求满足度:</div>
            <div class="result-value">
                <div class="score-bar">
                    <div class="score-fill" style="width: {scores.get('requirement_satisfaction', 0)}%">
                        {scores.get('requirement_satisfaction', 0)}/100
                    </div>
                </div>
            </div>
        </div>

        <div class="result-row">
            <div class="result-label">推理正确性:</div>
            <div class="result-value">
                <div class="score-bar">
                    <div class="score-fill" style="width: {scores.get('reasoning_correctness', 0)}%">
                        {scores.get('reasoning_correctness', 0)}/100
                    </div>
                </div>
            </div>
        </div>

        <div class="result-row">
            <div class="result-label">简洁性:</div>
            <div class="result-value">
                <div class="score-bar">
                    <div class="score-fill" style="width: {scores.get('conciseness', 0)}%">
                        {scores.get('conciseness', 0)}/100
                    </div>
                </div>
            </div>
        </div>
    """

    # 失败步骤
    if failed_steps:
        failed_steps_html = '<div class="failed-steps"><strong>❌ 失败步骤:</strong><br>'
        for step in failed_steps:
            failed_steps_html += f"""
            <div class="failed-step">
                <strong>Step ID:</strong> {step.get('step_id', 'N/A')}<br>
                <strong>片段:</strong> {step.get('snippet', 'N/A')}<br>
                <strong>失败原因:</strong> {step.get('why_failed', 'N/A')}
            </div>
            """
        failed_steps_html += '</div>'
        judge_result_html += f"""
        <div class="result-row">
            <div class="result-label">失败步骤:</div>
            <div class="result-value">{failed_steps_html}</div>
        </div>
        """

    # 修正后的思考（新格式）
    if refined_thinking:
        judge_result_html += f"""
        <div class="result-row">
            <div class="result-label">修正后的思考:</div>
            <div class="result-value">
                <div class="refined-thinking">
                    {refined_thinking}
                </div>
            </div>
        </div>
        """

    # 修正后的动作（新格式）
    if refined_action:
        judge_result_html += f"""
        <div class="result-row">
            <div class="result-label">修正后的动作:</div>
            <div class="result-value">
                <div class="refined-action">
                    <pre>{refined_action}</pre>
                </div>
            </div>
        </div>
        """

    # 正确动作（旧格式，向后兼容）
    if correct_action and not refined_action:
        judge_result_html += f"""
        <div class="result-row">
            <div class="result-label">正确动作建议:</div>
            <div class="result-value">
                <div class="correct-action">
                    <pre>{correct_action}</pre>
                </div>
            </div>
        </div>
        """

    # 修复建议
    if repair_suggestions:
        judge_result_html += f"""
        <div class="result-row">
            <div class="result-label">修复建议:</div>
            <div class="result-value">{repair_suggestions}</div>
        </div>
        """

    # 推理过程（reasoning_content）
    if reasoning_content:
        judge_result_html += f"""
        <div class="result-row">
            <div class="result-label">推理过程:</div>
            <div class="result-value">
                <div class="reasoning-content">
                    <pre>{reasoning_content}</pre>
                </div>
            </div>
        </div>
        """

    judge_result_html += "</div>"

    # 原始响应
    raw_response_str = json.dumps(raw_response, ensure_ascii=False, indent=2)

    # 填充模板
    html_content = html_template.format(
        timestamp=timestamp,
        screenshot_path=screenshot_path,
        total_messages=total_messages,
        messages_with_images=messages_with_images,
        total_images=total_images,
        total_tokens=total_tokens,
        system_content=system_content,
        messages_html=messages_html,
        judge_result_html=judge_result_html,
        raw_response=raw_response_str,
    )

    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✅ HTML文件已生成: {output_path}")


def serve_html(html_path: str, port: int = 8000):
    """启动简单的HTTP服务器"""
    import webbrowser
    import threading

    # 切换到HTML文件所在目录
    html_dir = os.path.dirname(os.path.abspath(html_path))
    html_filename = os.path.basename(html_path)

    os.chdir(html_dir)

    class CustomHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            # 简化日志输出
            print(f"[{self.address_string()}] {format % args}")

    server = HTTPServer(('localhost', port), CustomHandler)

    print(f"🌐 启动Web服务器: http://localhost:{port}/{html_filename}")
    print(f"📂 服务目录: {html_dir}")
    print("按 Ctrl+C 停止服务器")

    # 在浏览器中打开
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}/{html_filename}")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
        server.shutdown()


def find_judge_io_files(directory: str) -> list[str]:
    """查找目录下所有的judge_io文件"""
    judge_io_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.startswith("judge_io") and file.endswith(".json"):
                judge_io_files.append(os.path.join(root, file))
    return sorted(judge_io_files)


def main():
    parser = argparse.ArgumentParser(description="Judge输入输出可视化工具")
    parser.add_argument("path", help="judge_io.json文件路径或trace目录")
    parser.add_argument("--html", action="store_true", help="生成HTML文件（默认）")
    parser.add_argument("--serve", action="store_true", help="启动web服务器")
    parser.add_argument("--port", type=int, default=8000, help="Web服务器端口（默认8000）")
    parser.add_argument("--all", action="store_true", help="处理目录下所有judge_io文件")
    parser.add_argument("--output", "-o", help="输出HTML文件路径")

    args = parser.parse_args()

    # 检查路径
    if not os.path.exists(args.path):
        print(f"❌ 路径不存在: {args.path}")
        return

    # 处理目录或单个文件
    if os.path.isdir(args.path):
        judge_io_files = find_judge_io_files(args.path)
        if not judge_io_files:
            print(f"❌ 目录中没有找到judge_io文件: {args.path}")
            return

        print(f"📁 找到 {len(judge_io_files)} 个judge_io文件:")
        for f in judge_io_files:
            print(f"  - {f}")

        if args.all:
            # 处理所有文件
            for judge_io_file in judge_io_files:
                process_single_file(judge_io_file, args)
        else:
            # 只处理第一个
            print(f"\n使用 --all 参数处理所有文件，或指定单个文件路径")
            process_single_file(judge_io_files[0], args)
    else:
        # 处理单个文件
        process_single_file(args.path, args)


def process_single_file(judge_io_file: str, args):
    """处理单个judge_io文件"""
    print(f"\n📄 处理文件: {judge_io_file}")

    # 读取数据
    with open(judge_io_file, 'r', encoding='utf-8') as f:
        judge_io_data = json.load(f)

    # 确定输出路径
    if args.output:
        html_output = args.output
    else:
        base_name = os.path.splitext(judge_io_file)[0]
        html_output = f"{base_name}.html"

    # 生成HTML
    generate_html(judge_io_data, html_output)

    # 启动服务器（如果需要）
    if args.serve:
        serve_html(html_output, args.port)


if __name__ == "__main__":
    main()
