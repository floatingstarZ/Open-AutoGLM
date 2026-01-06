"""
Trace可视化工具

支持可视化 trace.jsonl 文件，显示最后一个非task_end的step的对话历史，
以及所有步骤的截图。

使用方法：
    # 生成HTML文件
    python trace_visualizer.py <trace.jsonl> --html

    # 启动web服务
    python trace_visualizer.py <trace.jsonl> --serve --port 8000

    # 可视化整个trace目录（所有trace文件）
    python trace_visualizer.py <trace_dir> --all
"""

import argparse
import base64
import json
import os
import io
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Optional
from PIL import Image


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


def load_image_as_base64(image_path: str, scaled_width: Optional[int] = None, scaled_height: Optional[int] = None) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """
    加载图片，并转换为base64（参考judge.py的实现）
    
    Args:
        image_path: 图片文件路径
        scaled_width: 目标宽度（None = 使用原始尺寸）
        scaled_height: 目标高度（None = 使用原始尺寸）
    
    Returns:
        (Base64编码的图片字符串, 缩放后的宽度, 缩放后的高度)
    """
    try:
        # 如果是相对路径，尝试从traces目录查找
        if not os.path.isabs(image_path):
            # 尝试从当前工作目录或traces目录查找
            possible_paths = [
                image_path,
                os.path.join("traces", image_path),
                os.path.join(os.getcwd(), "traces", image_path),
            ]
            found = False
            for path in possible_paths:
                if os.path.exists(path):
                    image_path = path
                    found = True
                    break
            if not found:
                raise FileNotFoundError(f"Image file not found: {image_path}")
        
        with Image.open(image_path) as img:
            # 转换为RGB模式（如果需要）
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # 获取原始尺寸
            width, height = img.size

            # 缩放图片
            if scaled_width is not None and scaled_height is not None and scaled_width > 0 and scaled_height > 0:
                # 使用指定的缩放尺寸
                new_width, new_height = scaled_width, scaled_height
            else:
                new_width, new_height = width, height
            
            img = img.resize((new_width, new_height), Image.LANCZOS)

            # 转换为base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            b64_code = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return b64_code, new_width, new_height
    except Exception as e:
        print(f"[WARNING] Failed to load image {image_path}: {e}")
        return None, None, None


def load_trace_data(trace_file: str) -> dict[str, Any]:
    """加载trace.jsonl数据"""
    steps = []
    task_start = None
    task_end = None
    
    trace_dir = os.path.dirname(os.path.abspath(trace_file))
    
    with open(trace_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                data_type = data.get("type")
                
                if data_type == "task_start":
                    task_start = data
                elif data_type == "task_end":
                    task_end = data
                elif data_type == "step":
                    # 将截图路径转换为绝对路径
                    screenshot_path = data.get("screenshot_path", "")
                    if screenshot_path and not os.path.isabs(screenshot_path):
                        # 截图路径可能是相对路径，需要相对于trace目录
                        # 如果路径包含目录名（如 task_xxx/step_1.png），先尝试直接join
                        # 如果不存在，则只使用文件名（截图应该在同一个目录下）
                        full_path = os.path.join(trace_dir, screenshot_path)
                        if not os.path.exists(full_path):
                            # 尝试只使用文件名
                            filename = os.path.basename(screenshot_path)
                            full_path = os.path.join(trace_dir, filename)
                        screenshot_path = full_path
                    data["screenshot_path"] = screenshot_path
                    
                    # 注意：不在每个step中嵌入图片，而是在最后统一处理
                    # 这样可以确保所有步骤的截图都嵌入到对应的user消息中
                    
                    steps.append(data)
            except json.JSONDecodeError as e:
                print(f"警告: 无法解析行: {e}")
                continue
    
    # 找到最后一个非task_end的step
    last_step = steps[-1] if steps else None
    
    # 收集所有步骤的截图路径映射（step_index -> screenshot_path）
    screenshots_map = {}
    all_screenshots = []
    for step in steps:
        step_index = step.get("step_index", 0)
        screenshot_path = step.get("screenshot_path", "")
        if screenshot_path and os.path.exists(screenshot_path):
            screenshots_map[step_index] = screenshot_path
            all_screenshots.append({
                "step_index": step_index,
                "path": screenshot_path,
                "timestamp": step.get("timestamp", ""),
                "current_app": step.get("current_app", ""),
            })
    
    # 在最后一步的model_input中，将所有步骤的截图嵌入到对应的user消息中
    # 参考judge.py的逻辑：第1个user消息对应step 1，第2个user消息对应step 2，等等
    if last_step:
        model_input = last_step.get("model_input", [])
        user_msg_index = 0
        for msg in model_input:
            if msg.get("role") == "user":
                user_msg_index += 1
                # user_msg_index对应step_index
                if user_msg_index in screenshots_map:
                    screenshot_path = screenshots_map[user_msg_index]
                    screenshot_base64, _, _ = load_image_as_base64(screenshot_path)
                    if screenshot_base64:
                        content = msg.get("content", [])
                        # 确保content是列表格式
                        if isinstance(content, str):
                            content = [{"type": "text", "text": content}]
                        elif not isinstance(content, list):
                            content = [{"type": "text", "text": str(content)}]
                        
                        # 检查是否已经有图片（避免重复添加）
                        has_image = any(
                            isinstance(item, dict) and item.get("type") == "image_url"
                            for item in content
                        )
                        
                        if not has_image:
                            # 添加截图到user消息
                            content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{screenshot_base64}"
                                }
                            })
                            msg["content"] = content
        # 更新last_step的model_input
        last_step["model_input"] = model_input
    
    return {
        "task_start": task_start,
        "task_end": task_end,
        "last_step": last_step,
        "all_steps": steps,
        "all_screenshots": all_screenshots,
        "trace_dir": trace_dir,
    }


def generate_html(trace_data: dict[str, Any], output_path: str) -> None:
    """生成HTML可视化文件"""
    
    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trace 可视化</title>
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

        .step-info {{
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
        }}

        .step-row {{
            display: flex;
            margin-bottom: 12px;
            align-items: flex-start;
        }}

        .step-label {{
            font-weight: 600;
            color: #495057;
            min-width: 180px;
            flex-shrink: 0;
        }}

        .step-value {{
            color: #212529;
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

        .screenshot-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}

        .screenshot-item {{
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            overflow: hidden;
            background: #fafafa;
        }}

        .screenshot-item img {{
            width: 100%;
            height: auto;
            display: block;
            cursor: pointer;
        }}

        .screenshot-info {{
            padding: 10px;
            background: #f5f5f5;
            font-size: 12px;
            color: #666;
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

            .screenshot-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📱 Trace 可视化</h1>
            <div class="meta">
                <div>任务ID: {task_id}</div>
                <div>任务描述: {task_description}</div>
                <div>时间戳: {timestamp}</div>
            </div>
        </div>

        <!-- 统计信息 -->
        <div class="section">
            <div class="section-title">📊 统计信息</div>
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-label">总步骤数</div>
                    <div class="stat-value">{total_steps}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">截图数量</div>
                    <div class="stat-value">{total_screenshots}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">最后步骤索引</div>
                    <div class="stat-value">{last_step_index}</div>
                </div>
            </div>
        </div>

        <!-- 最后一步信息 -->
        <div class="section">
            <div class="section-title">🎯 最后一步详情</div>
            {last_step_info}
        </div>

        <!-- 对话历史 -->
        <div class="section">
            <div class="section-title">💬 对话历史</div>
            {messages_html}
        </div>

        <!-- 所有截图 -->
        <div class="section">
            <div class="section-title">📸 所有步骤截图</div>
            {screenshots_html}
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

    task_start = trace_data.get("task_start", {})
    task_end = trace_data.get("task_end", {})
    last_step = trace_data.get("last_step")
    all_steps = trace_data.get("all_steps", [])
    all_screenshots = trace_data.get("all_screenshots", [])
    trace_dir = trace_data.get("trace_dir", "")
    
    # 提取任务信息
    task_id = task_start.get("task_id", "Unknown")
    task_description = task_start.get("task_description", "Unknown")
    timestamp = task_start.get("timestamp", "Unknown")
    
    # 统计信息
    total_steps = len(all_steps)
    total_screenshots = len(all_screenshots)
    last_step_index = last_step.get("step_index", 0) if last_step else 0
    
    # 生成最后一步信息
    if last_step:
        last_step_info = f"""
        <div class="step-info">
            <div class="step-row">
                <div class="step-label">步骤索引:</div>
                <div class="step-value">{last_step.get('step_index', 'N/A')}</div>
            </div>
            <div class="step-row">
                <div class="step-label">时间戳:</div>
                <div class="step-value">{last_step.get('timestamp', 'N/A')}</div>
            </div>
            <div class="step-row">
                <div class="step-label">当前应用:</div>
                <div class="step-value">{last_step.get('current_app', 'N/A')}</div>
            </div>
            <div class="step-row">
                <div class="step-label">屏幕尺寸:</div>
                <div class="step-value">{last_step.get('screen_size', {})}</div>
            </div>
            <div class="step-row">
                <div class="step-label">模型输出:</div>
                <div class="step-value"><pre style="white-space: pre-wrap;">{last_step.get('model_output', 'N/A')}</pre></div>
            </div>
            <div class="step-row">
                <div class="step-label">思考过程:</div>
                <div class="step-value"><pre style="white-space: pre-wrap;">{last_step.get('thinking', 'N/A')}</pre></div>
            </div>
            <div class="step-row">
                <div class="step-label">执行动作:</div>
                <div class="step-value"><pre style="white-space: pre-wrap;">{json.dumps(last_step.get('action', {}), ensure_ascii=False, indent=2)}</pre></div>
            </div>
        </div>
        """
    else:
        last_step_info = "<p>没有找到步骤数据</p>"
    
    # 生成消息HTML（参考visualizer.py的实现）
    messages_html_parts = []
    if last_step:
        model_input = last_step.get("model_input", [])
        for idx, msg in enumerate(model_input):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            text_content = extract_text_from_message(content)
            image_count = 0
            if isinstance(content, list):
                image_count = sum(1 for item in content if isinstance(item, dict) and item.get("type") == "image_url")
            
            message_html = f"""
            <div class="message {role}">
                <div class="message-header">
                    <span class="role-badge {role}">{role}</span>
                    <span style="color: #999; font-size: 12px;">Message #{idx + 1}</span>
                    {f'<span class="tag">📷 {image_count} 张图片</span>' if image_count > 0 else ''}
                </div>
                <div class="message-content">{text_content if text_content else '<em>无文本内容</em>'}</div>
            """
            
            # 添加图片（参考visualizer.py的实现）
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
    
    messages_html = "\n".join(messages_html_parts) if messages_html_parts else "<p>没有对话历史</p>"
    
    # 生成所有截图HTML
    screenshots_html_parts = []
    for screenshot in all_screenshots:
        step_index = screenshot.get("step_index", 0)
        screenshot_path = screenshot.get("path", "")
        timestamp = screenshot.get("timestamp", "")
        current_app = screenshot.get("current_app", "")
        
        # 将图片转换为base64
        screenshot_base64, _, _ = load_image_as_base64(screenshot_path)
        
        if screenshot_base64:
            img_base64 = f"data:image/png;base64,{screenshot_base64}"
            screenshots_html_parts.append(f"""
            <div class="screenshot-item">
                <img src="{img_base64}" alt="Step {step_index}" onclick="openModal(this.src)">
                <div class="screenshot-info">
                    <div><strong>Step {step_index}</strong></div>
                    <div>应用: {current_app}</div>
                    <div>时间: {timestamp}</div>
                </div>
            </div>
            """)
    
    screenshots_html = f"""
    <div class="screenshot-grid">
        {''.join(screenshots_html_parts)}
    </div>
    """ if screenshots_html_parts else "<p>没有找到截图</p>"
    
    # 填充模板
    html_content = html_template.format(
        task_id=task_id,
        task_description=task_description,
        timestamp=timestamp,
        total_steps=total_steps,
        total_screenshots=total_screenshots,
        last_step_index=last_step_index,
        last_step_info=last_step_info,
        messages_html=messages_html,
        screenshots_html=screenshots_html,
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


def find_trace_files(directory: str) -> list[str]:
    """查找目录下所有的trace.jsonl文件"""
    trace_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file == "trace.jsonl":
                trace_files.append(os.path.join(root, file))
    return sorted(trace_files)


def main():
    parser = argparse.ArgumentParser(description="Trace可视化工具")
    parser.add_argument("path", help="trace.jsonl文件路径或trace目录")
    parser.add_argument("--html", action="store_true", help="生成HTML文件（默认）")
    parser.add_argument("--serve", action="store_true", help="启动web服务器")
    parser.add_argument("--port", type=int, default=8000, help="Web服务器端口（默认8000）")
    parser.add_argument("--all", action="store_true", help="处理目录下所有trace文件")
    parser.add_argument("--output", "-o", help="输出HTML文件路径")
    
    args = parser.parse_args()
    
    # 检查路径
    if not os.path.exists(args.path):
        print(f"❌ 路径不存在: {args.path}")
        return
    
    # 处理目录或单个文件
    if os.path.isdir(args.path):
        trace_files = find_trace_files(args.path)
        if not trace_files:
            print(f"❌ 目录中没有找到trace.jsonl文件: {args.path}")
            return
        
        print(f"📁 找到 {len(trace_files)} 个trace.jsonl文件:")
        for f in trace_files:
            print(f"  - {f}")
        
        if args.all:
            # 处理所有文件
            for trace_file in trace_files:
                process_single_file(trace_file, args)
        else:
            # 只处理第一个
            print(f"\n使用 --all 参数处理所有文件，或指定单个文件路径")
            process_single_file(trace_files[0], args)
    else:
        # 处理单个文件
        process_single_file(args.path, args)


def process_single_file(trace_file: str, args):
    """处理单个trace文件"""
    print(f"\n📄 处理文件: {trace_file}")
    
    # 加载数据
    trace_data = load_trace_data(trace_file)
    
    # 确定输出路径
    if args.output:
        html_output = args.output
    else:
        base_name = os.path.splitext(trace_file)[0]
        html_output = f"{base_name}_visualization.html"
    
    # 生成HTML
    generate_html(trace_data, html_output)
    
    # 启动服务器（如果需要）
    if args.serve:
        serve_html(html_output, args.port)


if __name__ == "__main__":
    main()

