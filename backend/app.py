"""
Backend API for Claude Phone Agent
Provides REST API endpoints for frontend to interact with Claude
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from datetime import datetime
import os
import json
import base64
import copy
import traceback
import argparse
# import psutil
from conversation_manager import ConversationManager
from model_interface import ModelInterface
from copy import deepcopy

# Try to import MongoDB service, make it optional
try:
    from mongo_trace_service import MongoTraceService
    MONGO_AVAILABLE = True
except ImportError as e:
    print(f"Warning: MongoDB service not available: {e}")
    MongoTraceService = None
    MONGO_AVAILABLE = False

# Default configuration
DEFAULT_API_KEY = "sk-CJc3Kj313cPY3hsg28zIDGQ8vKkxhtXn"
DEFAULT_BASE_URL = "https://api-gateway.glm.ai/v1"
DEFAULT_MODEL_NAME = "claude-sonnet-4-5-20250929"
# DEFAULT_MODEL_NAME = "claude-sonnet-4-20250514"
# DEFAULT_MODEL_NAME = "doubao-1.5-thinking-pro-vision-250415"

# Parse command line arguments
parser = argparse.ArgumentParser(description='Claude Phone Agent Backend')
parser.add_argument('--use-mongodb', action='store_true',
                    help='Enable MongoDB storage (default: local storage)')
parser.add_argument('--port', type=int, default=8097,
                    help='Port to run the server on (default: 8097)')
parser.add_argument('--api-key', type=str, default=None,
                    help=f'API key for Claude API (default: {DEFAULT_API_KEY[:20]}...)')
parser.add_argument('--api-url', type=str, default=f'{DEFAULT_BASE_URL}/messages',
                    help=f'API URL for Claude API (default: {DEFAULT_BASE_URL}/messages)')
parser.add_argument('--model', type=str, default=DEFAULT_MODEL_NAME,
                    help=f'Model to use (default: {DEFAULT_MODEL_NAME})')
parser.add_argument('--target-width', type=int, default=512,
                    help='Target width for screenshot resizing (default: 512)')
args, unknown = parser.parse_known_args()  # Use parse_known_args to avoid conflicts with Flask

# Set API key: command line arg > env var > default
if args.api_key is None:
    args.api_key = os.getenv("OPENAI_API_KEY", DEFAULT_API_KEY)

# Global configuration
USE_MONGODB = args.use_mongodb and MONGO_AVAILABLE
if args.use_mongodb and not MONGO_AVAILABLE:
    print("Warning: MongoDB requested but not available, falling back to local storage")
    USE_MONGODB = False

# Setup logging
os.makedirs("logs", exist_ok=True)
logfile = f'logs/backend_{datetime.now().strftime("%Y%m%d%H%M%S")}.log'
logging.basicConfig(
    filename=logfile,
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%-Y%m-%d %H:%M:%S'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize managers
conversation_manager = ConversationManager()
# Note: ModelInterface instances are created per-request to avoid state conflicts

# Initialize MongoDB Trace Service (only if enabled)
if USE_MONGODB:
    mongo_trace_service = MongoTraceService()
    logger.info("MongoDB storage enabled")
else:
    mongo_trace_service = None
    logger.info("Local storage enabled (MongoDB disabled)")

# Create storage directories
os.makedirs("screenshots", exist_ok=True)
os.makedirs("traces", exist_ok=True)  # For local trace storage

def replace_image_data_with_paths(data, base_path, step_index):
    """
    递归替换数据中的图片base64数据为路径

    Args:
        data: 要处理的数据（dict或list）
        base_path: 图片存储的基础路径
        step_index: 当前步骤索引

    Returns:
        处理后的数据
    """
    import copy

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key == "type" and value == "image":
                # 这是一个图片块，需要处理
                result[key] = value
            elif key == "source" and isinstance(value, dict) and "data" in value:
                # 替换图片数据为路径
                image_path = f"{base_path}_{step_index}.png"
                result[key] = {
                    "type": value.get("type", "base64"),
                    "media_type": value.get("media_type", "image/png"),
                    "data": image_path  # 用路径替换base64数据
                }
            else:
                result[key] = replace_image_data_with_paths(value, base_path, step_index)
        return result
    elif isinstance(data, list):
        return [replace_image_data_with_paths(item, base_path, idx) for idx, item in enumerate(data)]
    else:
        return data


def count_turn_index(context):
    """
    Count the turn index by counting screenshots in the context.

    Args:
        context: Conversation context

    Returns:
        Turn index (0-based)
    """
    count = 0
    for message in context:
        if message.get("role") == "user" and "content" in message:
            for content_block in message.get("content", []):
                # Check for direct images
                if isinstance(content_block, dict) and content_block.get("type") == "image":
                    count += 1
                # Check for images in tool_result
                elif isinstance(content_block, dict) and content_block.get("type") == "tool_result":
                    tool_content = content_block.get("content", [])
                    if isinstance(tool_content, list):
                        for item in tool_content:
                            if isinstance(item, dict) and item.get("type") == "image":
                                count += 1
    return count


def save_screenshot(conversation_id, turn_index, screenshot_base64):
    """
    Save screenshot to file.

    Args:
        conversation_id: Conversation ID
        turn_index: Turn index (0-based)
        screenshot_base64: Base64 encoded screenshot
    """
    try:
        filename = f"screenshots/{conversation_id}-{turn_index}.png"
        image_data = base64.b64decode(screenshot_base64)
        with open(filename, "wb") as f:
            f.write(image_data)
        logger.debug(f"Saved screenshot to {filename}")
    except Exception as e:
        logger.error(f"Error saving screenshot: {str(e)}", exc_info=True)


def save_trace_locally(step_data, screenshot_base64):
    """
    Save trace data locally to JSON file.

    Args:
        step_data: Step data dictionary
        screenshot_base64: Base64 encoded screenshot

    Returns:
        bool: Success status
    """
    try:
        task_id = step_data.get("task_id")
        step_index = step_data.get("step_index")

        # Create directory structure: traces/task_id/
        trace_dir = f"traces/{task_id}"
        os.makedirs(trace_dir, exist_ok=True)

        # Save step data to JSON
        trace_file = f"{trace_dir}/step_{step_index}.json"
        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(step_data, f, ensure_ascii=False, indent=2)

        # Save screenshot if provided
        if screenshot_base64:
            screenshot_file = f"{trace_dir}/image_step{step_index}.png"
            image_data = base64.b64decode(screenshot_base64)
            with open(screenshot_file, "wb") as f:
                f.write(image_data)

        logger.info(f"Saved trace locally: {trace_file}")
        return True

    except Exception as e:
        logger.error(f"Error saving trace locally: {str(e)}", exc_info=True)
        return False
        
@app.route('/api/conversation', methods=['POST'])
def handle_conversation():
    """
    Handle a conversation request from frontend.

    Request body:
    {
        "conversation_id": str,  # UUID for the conversation
        "screenshot": str,  # base64 encoded screenshot (optional)
        "current_package_name": str,  # Current app package name (optional)
        "prompt": str,  # User's prompt (required for first message)
        "step": int  # Expected number of user messages in history (excluding current round, optional)
    }

    Response:
    {
        "return_type": str,  # "tool_use" or "text"
        "text": str,  # Only for return_type = "text"
        "stop_reason": str,  # Only for return_type = "text", e.g., "finish", "sensitive", "notool", etc.
        "name": str,  # Only for return_type = "tool_use"
        "input": {
            "package_name": str,  # Only for Launch
            "coordinate": [int, int],  # Only for Tap, LongPress, DoubleClick
            "duration": float,  # Only for Wait, LongPress
            "text": str,  # Only for Type
            "start_coordinate": [int, int],  # Only for Swipe
            "end_coordinate": [int, int],  # Only for Swipe
        }
    }
    """
    try:
        data = request.json
        logger.info(f"Received request: {data.get('conversation_id')}")

        # Validate required fields
        conversation_id = data.get('conversation_id')
        if not conversation_id:
            return jsonify({"error": "conversation_id is required"}), 400

        # Get or create conversation context
        context = conversation_manager.get_or_create_context(conversation_id)

        # Handle step synchronization
        client_step = data.get('step')
        if client_step is not None:
            # Truncate context if client step is behind
            context = conversation_manager.sync_context_with_step(conversation_id, context, client_step)
            logger.info(f"Client step: {client_step}, Context synced")
            print("---- liuyongbin ----")
            print(len([x for x in context if x["role"] == "user"]))
            print("---- liuyongbin ----")

        # Extract request data
        screenshot_base64 = data.get('screenshot')
        current_package_name = data.get('current_package_name', '')
        user_prompt = data.get('prompt', '')

        # Save screenshot if provided
        if screenshot_base64:
            turn_index = count_turn_index(context)
            save_screenshot(conversation_id, turn_index, screenshot_base64)

        # Create a new ModelInterface instance for this request
        # This ensures dimension tracking is isolated per request
        model_interface = ModelInterface(
            api_key=args.api_key,
            api_url=args.api_url,
            model=args.model,
            target_width=args.target_width
        )

        # Call model to get response
        output = model_interface.call_model(
            context=context,
            screenshot_base64=screenshot_base64,
            current_package_name=current_package_name,
            user_prompt=user_prompt
        )
        response = output["response"]
        model = output["model"]
        current_app = output["current_app"]
        origin_size = output["origin_size"]
        scaled_size = output["scaled_size"]

        response["step"] = len([x for x in context if x["role"] == "user"])

        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "full_logs")
        os.makedirs(log_dir, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        log_filename = os.path.join(log_dir, f"{timestamp}.json")
        log_data = context
        with open(log_filename, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)

        # Save conversation trace (MongoDB or local)
        try:
            step = response["step"]
            # Create step data according to existing structure
            timestamp = datetime.now().isoformat()

            # Generate proper directory structure for image path
            date_folder = datetime.now().strftime("%y%m%d")  # e.g., 251023
            category_label = "only_for_test"  # 根据实际场景设置
            task_batch = 'batch_test'

            # 处理 model_input 中的图片数据，将base64替换为路径
            input_base_path = f"{conversation_id}"
            replaced_context = replace_image_data_with_paths(deepcopy(context), input_base_path, step)
            model_input = replaced_context[:-1]
            model_output = replaced_context[-1]['content']

            step_data = {
                "model": model,
                "step_index": step,
                "task_id": conversation_id,
                "trace_generate_timestamp": timestamp,
                "current_app": current_app,
                "image_path": f"{conversation_id}/image_step{step}.png" if screenshot_base64 else "",

                "origin_size": origin_size,
                "scaled_size": scaled_size,
                "model_input": model_input,
                "model_output": model_output,

                "date_folder": date_folder,
                "category_label": category_label,

                "task_batch": task_batch,
                "upload_timestamp": datetime.now().strftime("%Y%m%d%H%M%S"),
                "right_steps": -1,  # 初始化为-1

            }

            # Save to MongoDB or local storage based on configuration
            if USE_MONGODB:
                success = mongo_trace_service.upload_to_mongo(
                    step_data=step_data,
                    screenshot_base64=screenshot_base64,
                )
                if success:
                    logger.info(f"Successfully uploaded conversation {conversation_id} to MongoDB")
                else:
                    logger.warning(f"Failed to upload conversation {conversation_id} to MongoDB")
            else:
                success = save_trace_locally(step_data, screenshot_base64)
                if success:
                    logger.info(f"Successfully saved conversation {conversation_id} locally")
                else:
                    logger.warning(f"Failed to save conversation {conversation_id} locally")


        except Exception as e:
            logger.error(f"Error saving trace: {str(e)}", exc_info=True)
            # Continue with response even if trace save fails

        # Update conversation context (without the assistant message for normal flow)
        conversation_manager.update_context(conversation_id, context)

        logger.info(f"Response generated: {response.get('return_type')}")
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error handling conversation: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/conversation/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    """
    Delete a conversation and its context.
    """
    try:
        conversation_manager.delete_context(conversation_id)
        logger.info(f"Deleted conversation: {conversation_id}")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.
    """
    return jsonify({"status": "healthy"}), 200


if __name__ == '__main__':
    # Determine API key source
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        api_key_source = "Environment variable (OPENAI_API_KEY)"
    else:
        api_key_source = "Default config"

    print("\n" + "=" * 70)
    print("Claude Phone Agent Backend")
    print("=" * 70)
    print(f"Storage mode:     {'MongoDB' if USE_MONGODB else 'Local (traces/)'}")
    print(f"Port:             {args.port}")
    print(f"Model:            {args.model}")
    print(f"API URL:          {args.api_url}")
    print(f"Target width:     {args.target_width}")
    print(f"API Key:          {args.api_key[:20]}... ({api_key_source})")
    print(f"MongoDB available: {'Yes' if MONGO_AVAILABLE else 'No'}")
    print("=" * 70 + "\n")

    logger.info("Starting Claude Phone Agent Backend...")
    logger.info(f"Storage mode: {'MongoDB' if USE_MONGODB else 'Local'}")
    logger.info(f"Port: {args.port}")
    logger.info(f"Model: {args.model}")
    logger.info(f"Target width: {args.target_width}")
    app.run(host='0.0.0.0', port=args.port, debug=False)
