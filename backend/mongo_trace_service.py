"""
MongoDB服务类，用于上传trace步骤和截图到MongoDB
"""

import base64
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError as exc:
    raise SystemExit(
        "pymongo is required. Install with `pip install pymongo` before using this service."
    ) from exc


class MongoTraceService:
    """MongoDB Trace服务类，负责上传trace步骤和截图"""

    def __init__(self,
                 mongo_uri: str = None,
                 database: str = "android-assistant-demo",
                 trace_collection: str = "claude-for-android-trace",
                 image_collection: str = "claude-for-android-image",
                 trace_root: str = None):
        """
        初始化MongoDB Trace服务

        Args:
            mongo_uri: MongoDB连接URI
            database: 数据库名称
            trace_collection: trace步骤集合名称
            image_collection: 截图集合名称
            trace_root: trace文件根目录
        """
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://demo:N0passwd_@10.50.62.10:27017/")
        self.database = database
        self.trace_collection_name = trace_collection
        self.image_collection_name = image_collection
        self.trace_root = Path(trace_root or os.getenv(
            "TRACE_ROOT",
            "/Users/aminer/Desktop/ZhiPu/Full-Time/Agent/2_Zh_Agent/trace_output/claude-for-phone",
        )).expanduser().resolve()

        # MongoDB客户端和集合（延迟初始化）
        self._client = None
        self._trace_collection = None
        self._image_collection = None

    def _init_connection(self):
        """初始化MongoDB连接"""
        if self._client is None:
            self._client = MongoClient(self.mongo_uri)
            self._trace_collection = self._client[self.database][self.trace_collection_name]
            self._image_collection = self._client[self.database][self.image_collection_name]

    def close_connection(self):
        """关闭MongoDB连接"""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._trace_collection = None
            self._image_collection = None

    def upload_to_mongo(self,
                    step_data: dict,
                    screenshot_base64: Optional[str] = None) -> bool:
        """
        上传对话trace数据到MongoDB

        Args:
            step_data: 步骤数据，包含所有必需字段
            screenshot_base64: 可选的截图base64数据

        Returns:
            bool: 上传是否成功
        """
        try:
            self._init_connection()

            # 上传步骤数据
            filter_doc = {
                "date_folder": step_data["date_folder"],
                "category_label": step_data["category_label"],
                "task_batch": step_data["task_batch"],
                "task_id": step_data["task_id"],
                "step_index": step_data["step_index"],
            }

            self._trace_collection.replace_one(filter_doc, step_data, upsert=True)

            # 处理截图数据
            if screenshot_base64:
                # 从image_path中提取step_index
                step_index = step_data["step_index"]

                # 生成图片文档
                image_doc = {
                    "date_folder": step_data["date_folder"],
                    "category_label": step_data["category_label"],
                    "task_batch": step_data["task_batch"],
                    "task_id": step_data["task_id"],
                    "step_index": step_index,
                    "image_type": "raw",
                    "file_name": f"image_step{step_index}.png",
                    "relative_path": step_data["image_path"],
                    "upload_timestamp": step_data["upload_timestamp"],
                    "data_base64": screenshot_base64,
                    "md5": hashlib.md5(base64.b64decode(screenshot_base64)).hexdigest(),
                    "size_bytes": len(base64.b64decode(screenshot_base64)),
                }

                filter_doc = {
                    "date_folder": step_data["date_folder"],
                    "category_label": step_data["category_label"],
                    "task_batch": step_data["task_batch"],
                    "task_id": step_data["task_id"],
                    "file_name": f"image_step{step_index}.png",
                }

                self._image_collection.replace_one(filter_doc, image_doc, upsert=True)

            return True

        except Exception as e:
            print(f"[ERROR] Failed to upload trace data: {e}")
            return False