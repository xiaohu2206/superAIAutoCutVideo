import json
import logging
import time
from typing import Optional, List

import requests

from .asr_data import ASRDataSeg
from .asr_base import BaseASR


__version__ = "0.0.3"

API_BASE_URL = "https://member.bilibili.com/x/bcut/rubick-interface"

# 申请上传
API_REQ_UPLOAD = API_BASE_URL + "/resource/create"

# 提交上传
API_COMMIT_UPLOAD = API_BASE_URL + "/resource/create/complete"

# 创建任务
API_CREATE_TASK = API_BASE_URL + "/task"

# 查询结果
API_QUERY_RESULT = API_BASE_URL + "/task/result"


class BcutASR(BaseASR):
    """必剪 语音识别接口"""
    headers = {
        'User-Agent': 'Bilibili/1.0.0 (https://www.bilibili.com)',
        'Content-Type': 'application/json'
    }

    def __init__(self, audio_path: [str, bytes], use_cache: bool = False):
        super().__init__(audio_path, use_cache=use_cache)
        self.session = requests.Session()
        self.task_id: Optional[str] = None
        self.__etags: List[str] = []

        self.__in_boss_key: Optional[str] = None
        self.__resource_id: Optional[str] = None
        self.__upload_id: Optional[str] = None
        self.__upload_urls: List[str] = []
        self.__per_size: Optional[int] = None
        self.__clips: Optional[int] = None

        self.__download_url: Optional[str] = None

    @staticmethod
    def test_connection(timeout: int = 6) -> dict:
        try:
            resp = requests.get(API_BASE_URL, timeout=timeout)
            ok = int(resp.status_code) < 500
            if ok:
                return {"success": True, "status_code": int(resp.status_code)}
            return {"success": False, "status_code": int(resp.status_code)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def upload(self) -> None:
        """申请上传"""
        if not self.file_binary:
            raise ValueError("none set data")
        payload = json.dumps({
            "type": 2,
            "name": "audio.mp3",
            "size": len(self.file_binary),
            "ResourceFileType": "mp3",
            "model_id": "8",
        })

        resp = requests.post(
            API_REQ_UPLOAD,
            data=payload,
            headers=self.headers
        )
        resp.raise_for_status()
        resp = resp.json()
        resp_data = resp["data"]

        self.__in_boss_key = resp_data["in_boss_key"]
        self.__resource_id = resp_data["resource_id"]
        self.__upload_id = resp_data["upload_id"]
        self.__upload_urls = resp_data["upload_urls"]
        self.__per_size = resp_data["per_size"]
        self.__clips = len(resp_data["upload_urls"])

        logging.info(
            f"申请上传成功, 总计大小{resp_data['size'] // 1024}KB, {self.__clips}分片, 分片大小{resp_data['per_size'] // 1024}KB: {self.__in_boss_key}"
        )
        self.__upload_part()
        self.__commit_upload()

    def __upload_part(self) -> None:
        """上传音频数据"""
        for clip in range(self.__clips or 0):
            start_range = clip * (self.__per_size or 0)
            end_range = (clip + 1) * (self.__per_size or 0)
            logging.info(f"开始上传分片{clip}: {start_range}-{end_range}")
            resp = requests.put(
                self.__upload_urls[clip],
                data=self.file_binary[start_range:end_range],
                headers=self.headers
            )
            resp.raise_for_status()
            etag = resp.headers.get("Etag")
            if etag:
                self.__etags.append(etag)
            logging.info(f"分片{clip}上传成功: {etag}")

    def __commit_upload(self) -> None:
        """提交上传数据"""
        data = json.dumps({
            "InBossKey": self.__in_boss_key,
            "ResourceId": self.__resource_id,
            "Etags": ",".join(self.__etags),
            "UploadId": self.__upload_id,
            "model_id": "8",
        })
        resp = requests.post(
            API_COMMIT_UPLOAD,
            data=data,
            headers=self.headers
        )
        resp.raise_for_status()
        resp = resp.json()
        self.__download_url = resp["data"]["download_url"]
        logging.info(f"提交成功")

    def create_task(self) -> str:
        """开始创建转换任务"""
        resp = requests.post(
            API_CREATE_TASK, json={"resource": self.__download_url, "model_id": "8"}, headers=self.headers
        )
        resp.raise_for_status()
        resp = resp.json()
        self.task_id = resp["data"]["task_id"]
        logging.info(f"任务已创建: {self.task_id}")
        return self.task_id

    def result(self, task_id: Optional[str] = None):
        """查询转换结果"""
        resp = requests.get(API_QUERY_RESULT, params={"model_id": 7, "task_id": task_id or self.task_id}, headers=self.headers)
        resp.raise_for_status()
        resp = resp.json()
        return resp["data"]

    def _run(self, callback: Optional[callable] = None):
        if callback:
            try:
                callback(20, "正在上传音频到服务...")
            except Exception:
                pass
        self.upload()

        if callback:
            try:
                callback(40, "上传完成，创建识别任务...")
            except Exception:
                pass
        self.create_task()

        if callback:
            try:
                callback(55, "任务已创建，开始轮询结果...")
            except Exception:
                pass
        # 轮询检查任务状态
        for _ in range(500):
            task_resp = self.result()
            if task_resp.get("state") == 4:
                break
            time.sleep(1)

        if callback:
            try:
                callback(95, "转换完成，解析结果...")
            except Exception:
                pass
        logging.info(f"转换成功")
        return json.loads(task_resp["result"])

    def _make_segments(self, resp_data: dict) -> List[ASRDataSeg]:
        return [ASRDataSeg(u.get('text') or u.get('transcript') or '', u['start_time'], u['end_time']) for u in resp_data['utterances']]
