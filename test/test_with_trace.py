#!/usr/bin/env python3
"""
基于 trace.jsonl 的某一行进行推理（只使用 model_input）

参考 judge_tools/judge.py 的实现，读取 trace.jsonl 文件中的某一行，
提取 model_input，处理图片占位符，调用模型进行推理。
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Any, Optional
import time

import json
import base64
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
from PIL import Image
import io
from datetime import datetime

from openai import OpenAI
import sys
sys.path.append('../')
from phone_agent.config.prompts import ABSOLUTE_COORD_SYSTEM_PROMPT
from judge_tools.judge import convert_model_input_to_openai_format



TARGET_WIDTH = 512


def load_image_as_base64(image_path: str, scaled_width: Optional[int] = None, scaled_height: Optional[int] = None, scale_image: bool = False) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """
    加载图片，默认缩放（短边缩放到TARGET_WIDTH），并转换为base64
    
    Args:
        image_path: 图片文件路径
        scaled_width: 目标宽度（None = 使用默认缩放）
        scaled_height: 目标高度（None = 使用默认缩放）
        scale_image: 是否缩放图片
    
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

            # # 缩放图片
            # if scale_image:
            #     if scaled_width is not None and scaled_height is not None and scaled_width > 0 and scaled_height > 0:
            #         # 使用指定的缩放尺寸
            #         new_width, new_height = scaled_width, scaled_height
            #     else:
            #         # 默认缩放：短边缩放到TARGET_WIDTH，保持宽高比
            #         if width < height:
            #             new_width = TARGET_WIDTH
            #             new_height = int(height * (TARGET_WIDTH / width))
            #         else:
            #             new_height = TARGET_WIDTH
            #             new_width = int(width * (TARGET_WIDTH / height))
            #     img = img.resize((new_width, new_height), Image.LANCZOS)
            # else:
            #     new_width, new_height = width, height

            TARGET_WIDTH = 1084
            if width < height:
                new_width = TARGET_WIDTH
                new_height = int(height * (TARGET_WIDTH / width))
                print(f'宽度尺度: TARGET_WIDTH / width = {TARGET_WIDTH / width}')
            else:
                new_height = TARGET_WIDTH
                new_width = int(width * (TARGET_WIDTH / height))
            img = img.resize((new_width, new_height), Image.LANCZOS)
            print(f'图像尺寸: {img.size}')

            # 转换为base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            b64_code = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return b64_code, new_width, new_height
    except Exception as e:
        print(f"[ERROR] Failed to load image {image_path}: {e}")
        return None, None, None

# 默认配置
DEFAULT_API_KEY = "sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn"
DEFAULT_BASE_URL = "https://api-gateway.glm.ai/v1"
# DEFAULT_MODEL_NAME = "claude-sonnet-4-5-20250929-thinking"
DEFAULT_MODEL_NAME = "claude-sonnet-4-20250514-thinking"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5


def load_trace_step(trace_file_path: str, step_index: Optional[int] = None) -> dict[str, Any]:
    """
    从 trace.jsonl 文件中加载指定步骤的数据
    
    Args:
        trace_file_path: trace.jsonl 文件路径
        step_index: 步骤索引（1-based），如果为 None 则读取最后一个 step
    
    Returns:
        步骤数据字典
    """
    try:
        with open(trace_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise FileNotFoundError(f"文件不存在: {trace_file_path}")
    
    # 确定 step_index
    if step_index is None:
        # 找到最后一个 step 类型的记录
        for i in range(len(lines) - 1, -1, -1):
            try:
                data = json.loads(lines[i].strip())
                if data.get("type") == "step":
                    step_index = i + 1  # 转换为 1-based 索引
                    break
            except json.JSONDecodeError:
                continue
        else:
            raise ValueError("未找到有效的 step 记录")
    else:
        step_index = step_index
    
    if step_index > len(lines) or step_index < 1:
        raise ValueError(f"step_index {step_index} 超出范围 (1-{len(lines)})")
    
    # 解析 step 数据
    try:
        step_data = json.loads(lines[step_index - 1])
    except json.JSONDecodeError:
        raise ValueError(f"第 {step_index} 行不是有效的 JSON")
    
    if step_data.get("type") != "step":
        print(f"⚠️  警告: 第 {step_index} 行不是 step 类型记录")
    
    return step_data




def infer_from_trace(
    trace_file_path: str,
    step_index: Optional[int] = None,
    api_key: str = DEFAULT_API_KEY,
    base_url: str = DEFAULT_BASE_URL,
    model_name: str = DEFAULT_MODEL_NAME,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = DEFAULT_RETRY_DELAY,
    load_screenshots: bool = True,
) -> dict[str, Any]:
    """
    基于 trace.jsonl 的某一行进行推理
    
    Args:
        trace_file_path: trace.jsonl 文件路径
        step_index: 步骤索引（1-based），如果为 None 则读取最后一个 step
        api_key: API 密钥
        base_url: API 基础 URL
        model_name: 模型名称
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
        load_screenshots: 是否加载截图（如果 model_input 中有占位符）
    
    Returns:
        推理结果字典，包含：
        - content: 模型输出的文本内容
        - reasoning_content: 推理过程（如果模型支持）
        - usage: token 使用统计
    """
    # 加载 trace 步骤数据
    step_data = load_trace_step(trace_file_path, step_index)
    
    # 提取数据
    model_input = step_data.get("model_input", [])
    screenshot_path = step_data.get("screenshot_path", "")
    actual_step_index = step_data.get("step_index", step_index)
    
    print(f"📋 推理步骤: {actual_step_index if actual_step_index else step_index}")
    print(f"📂 Trace 文件: {trace_file_path}")
    if screenshot_path:
        print(f"📷 截图路径: {screenshot_path}")
    
    # 处理 model_input，加载截图
    screenshot_base64 = None
    if load_screenshots and screenshot_path:
        # 构建完整的截图路径
        trace_dir = os.path.dirname(trace_file_path)
        screenshot_name = Path(screenshot_path).name
        screenshot_full_path = os.path.join(trace_dir, screenshot_name)
        
        # 加载截图
        screenshot_base64, _, _ = load_image_as_base64(screenshot_full_path)
        if screenshot_base64:
            print(f"✅ 已加载截图: {screenshot_full_path}")
        else:
            print(f"⚠️  警告: 无法加载截图 {screenshot_full_path}，将使用原始 model_input")
    
    # 将 model_input 转换为 OpenAI 格式（保留 system 消息）
    messages = convert_model_input_to_openai_format(
        model_input,
        screenshot_base64=screenshot_base64,
        exclude_system=False  # 保留 system 消息
    )
    
    # 创建 OpenAI 客户端
    client = OpenAI(base_url=base_url, api_key=api_key)
    
    # 准备 API 调用参数
    api_params = {
        "model": model_name,
        "messages": messages,
        "max_tokens": 16384,
        "temperature": 0
    }

    
    # 重试机制
    for attempt in range(max_retries):
        try:
            print(f"\n🔄 调用模型 API (尝试 {attempt + 1}/{max_retries})...")
            response = client.chat.completions.create(**api_params)
            
            # 提取响应内容
            message = response.choices[0].message
            content = message.content or ""
            reasoning_content = getattr(message, 'reasoning_content', None)
            
            result = {
                "content": content,
                "reasoning_content": reasoning_content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                }
            }
            
            print("✅ 推理完成")
            return result
            
        except Exception as e:
            print(f"[RETRY {attempt + 1}/{max_retries}] 请求异常: {e}")
            import traceback
            traceback.print_exc()
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    raise Exception("模型调用失败，已达到最大重试次数")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="基于 trace.jsonl 的某一行进行推理（只使用 model_input）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 推理最后一个 step
  python test_with_trace.py traces/task_xxx/trace.jsonl

  # 推理第 6 步
  python test_with_trace.py traces/task_xxx/trace.jsonl 6

  # 指定模型和 API
  python test_with_trace.py traces/task_xxx/trace.jsonl 6 --model glm-4.1v-base --base-url http://localhost:8000/v1
        """
    )
    
    parser.add_argument("trace_file", help="trace.jsonl 文件路径")
    parser.add_argument("step_index", nargs="?", type=int, help="要推理的步骤索引（默认：最后一个 step）")
    parser.add_argument("--api-key", type=str, default=DEFAULT_API_KEY, help=f"API 密钥（默认：{DEFAULT_API_KEY}）")
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL, help=f"API 基础 URL（默认：{DEFAULT_BASE_URL}）")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL_NAME, help=f"模型名称（默认：{DEFAULT_MODEL_NAME}）")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES, help=f"最大重试次数（默认：{DEFAULT_MAX_RETRIES}）")
    parser.add_argument("--retry-delay", type=int, default=DEFAULT_RETRY_DELAY, help=f"重试延迟（秒）（默认：{DEFAULT_RETRY_DELAY}）")
    parser.add_argument("--no-screenshots", action="store_true", help="不加载截图")
    parser.add_argument("--output", "-o", help="保存输出到文件（JSON 格式）")
    
    args = parser.parse_args()
    
    # 执行推理
    try:
        result = infer_from_trace(
            trace_file_path=args.trace_file,
            step_index=args.step_index,
            api_key=args.api_key,
            base_url=args.base_url,
            model_name=args.model,
            max_retries=args.max_retries,
            retry_delay=args.retry_delay,
            load_screenshots=not args.no_screenshots,
        )
        
        # 输出结果
        print("\n" + "="*60)
        print("✅ 推理结果:")
        print("="*60)
        
        if result.get("reasoning_content"):
            print("\n📝 推理过程:")
            print("-" * 60)
            print(result["reasoning_content"])
            print("-" * 60)
        
        print("\n💬 模型输出:")
        print("-" * 60)
        print(result["content"])
        print("-" * 60)
        
        print("\n📊 Token 使用统计:")
        usage = result.get("usage", {})
        print(f"  - Prompt tokens: {usage.get('prompt_tokens', 0)}")
        print(f"  - Completion tokens: {usage.get('completion_tokens', 0)}")
        print(f"  - Total tokens: {usage.get('total_tokens', 0)}")
        
        # 保存到文件
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n💾 结果已保存到: {args.output}")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

