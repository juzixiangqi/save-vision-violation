import base64
import hashlib
import hmac
import json
import time
import uuid

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/hikvision", tags=["hikvision"])


class HikvisionConfig(BaseModel):
    cameraIndexCode: str
    appKey: str
    appSecret: str
    host: str = "https://10.190.11.240"
    port: int = 443


def signature(app_secret, method, app_key, artemis, api):
    """生成海康威视API请求头"""
    t = time.time()
    timestamp = str(int(round(t * 1000)))
    nonce = str(uuid.uuid1())

    secret = str(app_secret).encode("utf-8")
    message = str(
        method
        + "\n*/*\napplication/json\nx-ca-key:"
        + app_key
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

    header_dict = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "X-Ca-Key": app_key,
        "X-Ca-Signature": signature,
        "X-Ca-timestamp": timestamp,
        "X-Ca-nonce": nonce,
        "X-Ca-Signature-Headers": "x-ca-key,x-ca-nonce,x-ca-timestamp",
    }

    return header_dict


def get_video_area_rtsp_info(config: HikvisionConfig):
    """根据监控点indexCode获取时效性rtsp流"""
    api = "/api/video/v2/cameras/previewURLs"
    payload = {
        "cameraIndexCode": config.cameraIndexCode,
        "transmode": 1,
        "streamType": 0,
        "protocol": "rtsp",
    }

    artemis = "artemis"
    url = f"{config.host}:{config.port}/{artemis}{api}"

    try:
        headers = signature(config.appSecret, "POST", config.appKey, artemis, api)
        response = requests.post(
            url, headers=headers, json=payload, verify=False, timeout=10
        )
        return json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"请求海康威视API失败: {str(e)}")


@router.post("/rtsp")
async def get_hikvision_rtsp(config: HikvisionConfig):
    """获取海康威视摄像头RTSP流地址"""
    try:
        result = get_video_area_rtsp_info(config)

        if (
            result.get("code") == "0"
            and result.get("data")
            and result.get("data").get("url")
        ):
            return {"code": "0", "msg": "success", "url": result["data"]["url"]}
        else:
            return {
                "code": result.get("code", "-1"),
                "msg": result.get("msg", "获取RTSP地址失败"),
                "url": None,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取RTSP流失败: {str(e)}")
