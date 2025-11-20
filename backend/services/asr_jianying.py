import datetime
import logging
import hashlib
import hmac
import json
import os
import time
import uuid
import zlib
from typing import Dict, Tuple, Union

import requests


# from ASRData import ASRDataSeg
# from BaseASR import BaseASR

class JianYingASR:
    # 新版接口参数常量
    APP_SDK_VERSION = "48.0.0"
    APP_VERSION = "5.9.0"
    PF = "3"
    LAN = "zh-hans"
    LOC = "cn"
    USER_AGENT = "Cronet/TTNetVersion:3024dcd7 2023-10-18 QuicVersion:4bf243e0 2023-04-17"
    X_SS_DP = "3704"

    def __init__(self, audio_path: Union[str, bytes], use_cache: bool = False, need_word_time_stamp: bool = False,
                 start_time: float = 0, end_time: float = 6000):
        self.audio_path = audio_path
        self.use_cache = use_cache
        self.end_time = end_time
        self.start_time = start_time

        # AWS credentials
        self.session_token = None
        self.secret_key = None
        self.access_key = None

        # Upload details
        self.store_uri = None
        self.auth = None
        self.upload_id = None
        self.session_key = None
        self.upload_hosts = None

        self.need_word_time_stamp = need_word_time_stamp
        self.tdid = "3943278516897751" if datetime.datetime.now().year != 2024 else f"{uuid.getnode():012d}"

        self.file_binary = None
        self.crc32_hex = None

    def _prepare_file(self):
        if isinstance(self.audio_path, bytes):
            self.file_binary = self.audio_path
        else:
            with open(self.audio_path, "rb") as f:
                self.file_binary = f.read()
        self.crc32_hex = format(zlib.crc32(self.file_binary) & 0xFFFFFFFF, "08x")

    def run(self, callback=None):
        data = self._run(callback)
        return data

    def submit(self) -> str:
        """Submit the task"""
        url = "https://lv-pc-api-sinfonlinec.ulikecam.com/lv/v1/audio_subtitle/submit"
        payload = {
            "adjust_endtime": 200,
            "audio": self.store_uri,
            "caption_type": 0,
            "client_request_id": str(uuid.uuid4()),
            "max_lines": 1,
            "songs_info": [{"end_time": self.end_time, "id": "", "start_time": self.start_time}],
            "words_per_line": 16
        }

        sign, device_time = self._generate_sign_parameters(url='/lv/v1/audio_subtitle/submit', pf=self.PF,
                                                           appvr=self.APP_VERSION, tdid=self.tdid)
        x_ss_stub = self._calc_x_ss_stub(payload)
        headers = self._build_headers(device_time, sign, x_ss_stub)
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=1000.0)
            response.raise_for_status()
            resp = response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"提交任务失败: 网络错误: {e}")
        except Exception:
            text = ''
            try:
                text = response.text[:300]
            except Exception:
                pass
            raise RuntimeError(f"提交任务失败: 返回解析错误, 状态码 {response.status_code}, 响应片段: {text}")
        query_id = (resp.get('data') or {}).get('id')
        if not query_id:
            raise RuntimeError("提交任务失败: 返回未包含任务ID")
        return query_id

    def upload(self):
        """Upload the file"""
        self._prepare_file()
        self._upload_sign()
        self._upload_auth()
        self._upload_file()
        self._upload_check()
        uri = self._upload_commit()
        return uri

    def query(self, query_id: str):
        """Query the task"""
        url = "https://lv-pc-api-sinfonlinec.ulikecam.com/lv/v1/audio_subtitle/query"
        payload = {
            "id": query_id,
            "pack_options": {"need_attribute": True}
        }
        sign, device_time = self._generate_sign_parameters(url='/lv/v1/audio_subtitle/query', pf=self.PF,
                                                           appvr=self.APP_VERSION, tdid=self.tdid)
        x_ss_stub = self._calc_x_ss_stub(payload)
        headers = self._build_headers(device_time, sign, x_ss_stub)
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=1000.0)
            response.raise_for_status()
            raw = response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"查询任务失败: 网络错误: {e}")
        except Exception:
            text = ''
            try:
                text = response.text[:300]
            except Exception:
                pass
            raise RuntimeError(f"查询任务失败: 返回解析错误, 状态码 {response.status_code}, 响应片段: {text}")

        # 规范化返回结构：抽取 data，确保 utterances 列表及字段一致
        data = raw.get('data', {}) if isinstance(raw, dict) else {}
        # 某些情况下 data 可能是 JSON 字符串
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}

        utterances = data.get('utterances', []) if isinstance(data, dict) else []
        if not isinstance(utterances, list):
            utterances = []

        for u in utterances:
            # 统一文本字段
            text = u.get('text') or u.get('transcript') or ''
            u['text'] = text
            u['transcript'] = text
            # 统一时间字段类型为整数毫秒
            try:
                u['start_time'] = int(round(float(u.get('start_time', 0))))
            except (TypeError, ValueError):
                u['start_time'] = 0
            try:
                u['end_time'] = int(round(float(u.get('end_time', 0))))
            except (TypeError, ValueError):
                u['end_time'] = 0
            # 规范化字级时间戳（若存在）
            if isinstance(u.get('words'), list):
                for w in u['words']:
                    w['text'] = w.get('text', '')
                    try:
                        w['start_time'] = int(round(float(w.get('start_time', 0))))
                    except (TypeError, ValueError):
                        w['start_time'] = 0
                    try:
                        w['end_time'] = int(round(float(w.get('end_time', 0))))
                    except (TypeError, ValueError):
                        w['end_time'] = 0

        # 补充缺省字段，保证结构稳定
        if 'attribute' not in data:
            data['attribute'] = {}
        if 'hit_cache' not in data:
            data['hit_cache'] = False
        if 'model' not in data:
            data['model'] = ''

        # 返回仅 data，避免上层再解析顶层 envelope
        return data

    def _run(self, callback=None):
        try:
            if callback:
                callback(20, "正在上传...")
            self.upload()
            if callback:
                callback(50, "提交任务...")
            query_id = self.submit()
            if callback:
                callback(60, "获取结果...")
            resp_data = self.query(query_id)
            if callback:
                callback(100, "转录完成")
            return resp_data
        except Exception as e:
            raise RuntimeError(f"ASR 失败: {e}")

    def _make_segments(self, resp_data: dict) -> list:
        utterances = None
        if isinstance(resp_data, dict):
            if 'data' in resp_data and isinstance(resp_data['data'], dict) and 'utterances' in resp_data['data']:
                utterances = resp_data['data']['utterances']
            elif 'utterances' in resp_data and isinstance(resp_data['utterances'], list):
                utterances = resp_data['utterances']

        if isinstance(utterances, list):
            if self.need_word_time_stamp and any(isinstance(u.get('words'), list) for u in utterances):
                return [{
                    'text': (w.get('text', '').strip()),
                    'start_time': w.get('start_time', 0),
                    'end_time': w.get('end_time', 0),
                } for u in utterances for w in u.get('words', [])]
            else:
                return [{
                    'text': ((u.get('text') or u.get('transcript') or '').strip()),
                    'start_time': u.get('start_time', 0),
                    'end_time': u.get('end_time', 0),
                } for u in utterances]

        raise ValueError("未识别的 ASR 响应结构")

    def _get_key(self):
        return f"{self.__class__.__name__}-{self.crc32_hex}-{self.need_word_time_stamp}"

    def _generate_sign_parameters(self, url: str, pf: str = '3', appvr: str = '5.9.0', tdid='') -> \
            Tuple[str, str]:
        """Generate signature and timestamp via an HTTP request"""
        current_time = str(int(time.time()))
        data = {
            'url': url,
            'current_time': current_time,
            'pf': pf,
            'appvr': appvr,
            'tdid': self.tdid
        }
        get_sign_url = 'https://asrtools-update.bkfeng.top/sign'
        try:
            response = requests.post(get_sign_url, json=data, timeout=1000.0)
            response.raise_for_status()
            response_data = response.json()
            sign = response_data.get('sign')
            if not sign:
                raise ValueError("No 'sign' in response")
        except requests.RequestException as e:
            raise RuntimeError(f"签名接口请求失败: {e}")
        except Exception as ve:
            text = ''
            try:
                text = response.text[:300]
            except Exception:
                pass
            raise RuntimeError(f"签名接口返回解析错误, 状态码 {getattr(response,'status_code', '未知')}, 响应片段: {text}, 错误: {ve}")
        return sign.lower(), current_time

    def _build_headers(self, device_time: str, sign: str, x_ss_stub: str = '') -> Dict[str, str]:
        """Build headers for requests (updated to latest curl parameters)"""
        headers = {
            'User-Agent': self.USER_AGENT,
            'App-Sdk-Version': self.APP_SDK_VERSION,
            'appvr': self.APP_VERSION,
            'device-time': str(device_time),
            'lan': self.LAN,
            'loc': self.LOC,
            'pf': self.PF,
            'sign': sign,
            'sign-ver': "1",
            'tdid': self.tdid,
            'X-SS-DP': self.X_SS_DP,
            'Content-Type': 'application/json'
        }
        if x_ss_stub:
            headers['x-ss-stub'] = x_ss_stub
        return headers

    def _calc_x_ss_stub(self, payload: dict) -> str:
        """计算 x-ss-stub（POST体的MD5十六进制小写）"""
        body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        return hashlib.md5(body.encode('utf-8')).hexdigest()

    def _uplosd_headers(self):
        headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36 Thea/1.0.1",
            'Authorization': self.auth,
            'Content-CRC32': self.crc32_hex,
        }
        return headers

    def _upload_sign(self):
        """Get upload sign"""
        url = "https://lv-pc-api-sinfonlinec.ulikecam.com/lv/v1/upload_sign"
        payload = json.dumps({"biz": "pc-recognition"})
        sign, device_time = self._generate_sign_parameters(url='/lv/v1/upload_sign', pf=self.PF,
                                                           appvr=self.APP_VERSION, tdid=self.tdid)
        headers = self._build_headers(device_time, sign)
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=1000.0)
            response.raise_for_status()
            login_data = response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"上传签名获取失败: 网络错误: {e}")
        except Exception:
            text = ''
            try:
                text = response.text[:300]
            except Exception:
                pass
            raise RuntimeError(f"上传签名获取失败: 返回解析错误, 状态码 {response.status_code}, 响应片段: {text}")
        try:
            self.access_key = login_data['data']['access_key_id']
            self.secret_key = login_data['data']['secret_access_key']
            self.session_token = login_data['data']['session_token']
        except Exception as e:
            raise RuntimeError(f"上传签名获取失败: 返回结构缺失: {e}")
        return self.access_key, self.secret_key, self.session_token

    def _upload_auth(self):
        """Get upload authorization"""
        if isinstance(self.audio_path, bytes):
            file_size = len(self.audio_path)
        else:
            file_size = os.path.getsize(self.audio_path)
        request_parameters = f'Action=ApplyUploadInner&FileSize={file_size}&FileType=object&IsInner=1&SpaceName=lv-mac-recognition&Version=2020-11-19&s=5y0udbjapi'

        t = datetime.datetime.utcnow()
        amz_date = t.strftime('%Y%m%dT%H%M%SZ')
        datestamp = t.strftime('%Y%m%d')
        headers = {
            "x-amz-date": amz_date,
            "x-amz-security-token": self.session_token
        }
        signature = aws_signature(self.secret_key, request_parameters, headers, region="cn", service="vod")
        authorization = f"AWS4-HMAC-SHA256 Credential={self.access_key}/{datestamp}/cn/vod/aws4_request, SignedHeaders=x-amz-date;x-amz-security-token, Signature={signature}"
        headers["authorization"] = authorization
        try:
            response = requests.get(f"https://vod.bytedanceapi.com/?{request_parameters}", headers=headers, timeout=1000.0)
            response.raise_for_status()
            store_infos = response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"上传鉴权获取失败: 网络错误: {e}")
        except Exception:
            text = ''
            try:
                text = response.text[:300]
            except Exception:
                pass
            raise RuntimeError(f"上传鉴权获取失败: 返回解析错误, 状态码 {response.status_code}, 响应片段: {text}")

        self.store_uri = store_infos['Result']['UploadAddress']['StoreInfos'][0]['StoreUri']
        self.auth = store_infos['Result']['UploadAddress']['StoreInfos'][0]['Auth']
        self.upload_id = store_infos['Result']['UploadAddress']['StoreInfos'][0]['UploadID']
        self.session_key = store_infos['Result']['UploadAddress']['SessionKey']
        self.upload_hosts = store_infos['Result']['UploadAddress']['UploadHosts'][0]
        self.store_uri = store_infos['Result']['UploadAddress']['StoreInfos'][0]['StoreUri']
        return store_infos

    def _upload_file(self):
        """Upload the file"""
        url = f"https://{self.upload_hosts}/{self.store_uri}?partNumber=1&uploadID={self.upload_id}"
        headers = self._uplosd_headers()
        try:
            response = requests.put(url, data=self.file_binary, headers=headers, timeout=1000.0)
        except requests.RequestException as e:
            raise RuntimeError(f"文件上传失败: 网络错误: {e}")
        resp_data = {}
        success_flag = None
        try:
            resp_data = response.json()
            success_flag = resp_data.get('success')
        except Exception:
            pass
        ok = response.status_code in (200, 204)
        if success_flag is not None:
            ok = (success_flag == 0)
        if not ok:
            text = ''
            try:
                text = response.text[:300]
            except Exception:
                pass
            raise RuntimeError(f"文件上传失败: 状态码 {response.status_code}, 响应片段: {text}")
        return resp_data

    def _upload_check(self):
        """Check upload result"""
        url = f"https://{self.upload_hosts}/{self.store_uri}?uploadID={self.upload_id}"
        payload = f"1:{self.crc32_hex}"
        headers = self._uplosd_headers()
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=1000.0)
            response.raise_for_status()
            resp_data = response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"上传校验失败: 网络错误: {e}")
        except Exception:
            text = ''
            try:
                text = response.text[:300]
            except Exception:
                pass
            raise RuntimeError(f"上传校验失败: 返回解析错误, 状态码 {response.status_code}, 响应片段: {text}")
        return resp_data

    def _upload_commit(self):
        """Commit the uploaded file"""
        url = f"https://{self.upload_hosts}/{self.store_uri}?uploadID={self.upload_id}&partNumber=1&x-amz-security-token={self.session_token}"
        headers = self._uplosd_headers()
        try:
            response = requests.put(url, data=self.file_binary, headers=headers, timeout=1000.0)
        except requests.RequestException as e:
            raise RuntimeError(f"上传提交失败: 网络错误: {e}")
        if response.status_code not in (200, 204):
            text = ''
            try:
                text = response.text[:300]
            except Exception:
                pass
            raise RuntimeError(f"上传提交失败: 状态码 {response.status_code}, 响应片段: {text}")
        return self.store_uri


def sign(key: bytes, msg: str) -> bytes:
    """使用HMAC-SHA256生成签名"""
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()


def get_signature_key(secret_key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    """生成用于AWS签名的密钥"""
    k_date = sign(('AWS4' + secret_key).encode('utf-8'), date_stamp)
    k_region = sign(k_date, region_name)
    k_service = sign(k_region, service_name)
    k_signing = sign(k_service, 'aws4_request')
    return k_signing


def aws_signature(secret_key: str, request_parameters: str, headers: Dict[str, str],
                  method: str = "GET", payload: str = '', region: str = "cn", service: str = "vod") -> str:
    """生成AWS签名"""
    canonical_uri = '/'
    canonical_querystring = request_parameters
    canonical_headers = '\n'.join([f"{key}:{value}" for key, value in headers.items()]) + '\n'
    signed_headers = ';'.join(headers.keys())
    payload_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    amzdate = headers["x-amz-date"]
    datestamp = amzdate.split('T')[0]

    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = f"{algorithm}\n{amzdate}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"

    signing_key = get_signature_key(secret_key, datestamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature
