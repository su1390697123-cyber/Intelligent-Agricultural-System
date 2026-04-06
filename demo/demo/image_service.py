import os
import os
import base64
import requests
import logging
import io
from PIL import Image
from ultralytics import YOLO

from .config_loader import get_api_key

logger = logging.getLogger(__name__)

# --- 1. 配置百度云 API 凭证 ---
# 请前往百度智能云控制台 (console.bce.baidu.com) 创建应用获取
BAIDU_API_KEY = get_api_key("BAIDU_API_KEY")
BAIDU_SECRET_KEY = get_api_key("BAIDU_SECRET_KEY")

def get_baidu_access_token():
    """获取百度 API 的访问凭证 (Access Token)"""
    if not BAIDU_API_KEY or not BAIDU_SECRET_KEY:
        logger.error("未配置 BAIDU_API_KEY 或 BAIDU_SECRET_KEY")
        return None

    auth_url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": BAIDU_API_KEY,
        "client_secret": BAIDU_SECRET_KEY
    }
    try:
        # 设置超时时间，防止进程假死
        response = requests.post(auth_url, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        logger.error(f"获取百度 Access Token 失败: {e}")
        return None

def recognize_plant(image_content):
    """
    调用百度植物识别 API
    :param image_content: 图片文件的二进制数据 (如 file.read())
    """
    access_token = get_baidu_access_token()
    if not access_token:
        return {"error": "系统配置错误：无法获取百度 API 鉴权 Token"}

    request_url = f"https://aip.baidubce.com/rest/2.0/image-classify/v1/plant?access_token={access_token}"

    try:
        # 百度 API 要求图片必须经过 Base64 编码
        img_base64 = base64.b64encode(image_content).decode('utf-8')

        # 官方文档要求必须设置 content-type 为 application/x-www-form-urlencoded
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        payload = {"image": img_base64}

        response = requests.post(request_url, data=payload, headers=headers, timeout=15)
        response.raise_for_status()

        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"百度植物识别 API 请求失败: {e}")
        return {"error": "网络请求异常，请稍后再试"}
    except Exception as e:
        logger.error(f"图片处理或解析失败: {e}")
        return {"error": "图片处理异常"}


# ================= 新增：YOLOv8 虫害识别服务 =================

# 全局加载 YOLO 模型（只在 Django 启动时加载一次）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, 'models', 'best.pt')

try:
    logger.info(f"正在加载 YOLO 模型: {MODEL_PATH}")
    yolo_model = YOLO(MODEL_PATH)
    logger.info("✅ YOLOv8 模型加载成功！")
except Exception as e:
    logger.error(f"❌ YOLOv8 模型加载失败: {e}")
    yolo_model = None


def recognize_pest_yolo(image_content):
    """
    调用本地 YOLOv8 模型进行虫害检测，仅返回纯数据 JSON
    :param image_content: 图片文件的二进制数据 (如 file.read())
    """
    if not yolo_model:
        return {"error": "YOLO模型未正确加载"}

    try:
        # 将二进制图片转为 PIL Image，YOLO 需要这个格式
        image = Image.open(io.BytesIO(image_content)).convert("RGB")

        # 推理！使用之前图表分析出的最佳阈值 conf=0.31
        results = yolo_model(image, conf=0.31)
        result = results[0]

        detections = []
        # 遍历所有被框出来的虫子
        for box in result.boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            class_name = yolo_model.names[cls_id]

            # 获取边界框坐标 (如果你想给前端提供画框坐标的话)
            x1, y1, x2, y2 = box.xyxy[0].tolist()

            detections.append({
                "name": class_name,
                "confidence": round(conf, 4),
                "box": [round(x1), round(y1), round(x2), round(y2)]
            })

        # 按置信度从高到低排序
        detections.sort(key=lambda x: x['confidence'], reverse=True)

        annotated_img_array = result.plot()  # YOLO 返回 numpy 数组 (BGR格式)
        annotated_img = Image.fromarray(annotated_img_array[..., ::-1])  # 转换成常规的 RGB 格式

        # 🌟 把图片存入内存并转为 Base64 字符串
        buffered = io.BytesIO()
        annotated_img.save(buffered, format="JPEG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        if detections:
            # detections 已经按置信度排过序了，直接拿第 0 个
            final_pest_name = detections[0]['name']
        else:
            final_pest_name = "未检测到虫害"

            # 🌟 组装给前端的“傻瓜式”极简 JSON
        return {
            "status": "success",
            "pest_name": final_pest_name,  # 前端直接拿去显示或者查图谱
            "image_base64": img_base64  # 前端直接塞进 <img src="...">
        }

    except Exception as e:
        logger.error(f"YOLO 图片处理异常: {e}")
        return {"error": f"虫害识别处理异常: {str(e)}"}
