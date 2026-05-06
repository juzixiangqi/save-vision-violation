# -*- coding: UTF-8 -*-
import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Optional, Dict, Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 默认配置（向后兼容）
host = "https://10.190.11.240"
port = "443"
artemis = "artemis"
appKey = "25205625"
appSecret = "yvYgVYYfTcpXdSHHnIov"
methon = "POST"


def _signature(appSecret, methon, appKey, artemis, api):
    """请求头构造"""
    t = time.time()
    nowTime = lambda: int(round(t * 1000))
    timestamp = nowTime()
    timestamp = str(timestamp)
    nonce = str(uuid.uuid1())
    secret = str(appSecret).encode("utf-8")
    message = str(
        methon
        + "\n*/*\napplication/json\nx-ca-key:"
        + appKey
        + "\nx-ca-nonce:"
        + nonce
        + "\nx-ca-timestamp:"
        + timestamp
        + "\n/"
        + artemis
        + api
    ).encode("utf-8")
    signature = base64.b64encode(
        hmac.new(secret, message, digestmod=hashlib.sha256).digest()
    )

    header_dict = dict()
    header_dict["Accept"] = "*/*"
    header_dict["Content-Type"] = "application/json"
    header_dict["X-Ca-Key"] = appKey
    header_dict["X-Ca-Signature"] = signature
    header_dict["X-Ca-timestamp"] = timestamp
    header_dict["X-Ca-nonce"] = nonce
    header_dict["X-Ca-Signature-Headers"] = "x-ca-key,x-ca-nonce,x-ca-timestamp"

    return header_dict


def get_video_area_rtsp_info(code, config: Dict[str, Any] = None):
    """
    根据对应监控点indexCode获取时效性rtsp流
    
    Args:
        code: Camera indexCode
        config: 可选，海康配置字典，包含 host, port, appKey, appSecret
    """
    api = "/api/video/v2/cameras/previewURLs"
    payload = {
        "cameraIndexCode": code,
        "transmode": 1,
        "streamType": 0,
        "protocol": "rtsp",
    }
    
    # 使用传入的配置或默认配置
    cfg_host = config.get("host") if config else host
    cfg_port = str(config.get("port", 443)) if config else port
    cfg_app_key = config.get("appKey") if config else appKey
    cfg_app_secret = config.get("appSecret") if config else appSecret
    
    url = cfg_host + ":" + cfg_port + "/" + artemis + api
    try:
        data = requests.post(
            url,
            headers=_signature(cfg_app_secret, methon, cfg_app_key, artemis, api),
            json=payload,
            verify=False,
            timeout=10,
        )
        return json.loads(data.text)
    except Exception as e:
        print(f"[RTSPClient] Request failed: {e}")
        return {"code": "-1", "msg": str(e)}


def get_rtsp_stream(code, config: Dict[str, Any] = None) -> Optional[str]:
    """Get RTSP stream URL based on camera code

    Args:
        code: Camera indexCode
        config: 可选，海康配置字典，包含 host, port, appKey, appSecret

    Returns:
        Optional[str]: RTSP stream URL or None
    """
    try:
        result = get_video_area_rtsp_info(code, config)
        print(f"[RTSPClient] Hikvision API response: {json.dumps(result, indent=2, ensure_ascii=False)}")
        if (
            result.get("code") == "0"
            and result.get("data")
            and result.get("data").get("url")
        ):
            return result.get("data").get("url")
        print(
            f"[RTSPClient] Failed to get RTSP stream: {result.get('msg', 'Unknown error')}"
        )
        return None
    except Exception as e:
        print(f"[RTSPClient] Exception occurred while getting RTSP stream: {str(e)}")
        return None


class RTSPClient:
    """RTSP流获取客户端"""

    def __init__(self):
        pass

    def get_stream_url(self, camera_code: str, config: Dict[str, Any] = None) -> Optional[str]:
        """获取摄像头RTSP流地址
        
        Args:
            camera_code: 摄像头 indexCode
            config: 可选，海康配置字典，包含 host, port, appKey, appSecret
        """
        return get_rtsp_stream(camera_code, config)


# 全局RTSP客户端实例
rtsp_client = RTSPClient()
