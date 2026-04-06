import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render

# 导入我们刚刚在第一阶段写好的两个服务模块
from .llm_service import get_llm_response
from .image_service import recognize_plant, recognize_pest_yolo

@csrf_exempt
def llm_chat_api(request):
    """处理大模型问答请求的 API 接口"""
    if request.method == 'POST':
        try:
            # 1. 解析前端传来的 JSON 数据
            data = json.loads(request.body)
            user_message = data.get('message', '').strip()
            
            if not user_message:
                return JsonResponse({'status': 'error', 'msg': '消息不能为空'})

            # ========== 【新增：前端 Mock 测试通道】 ==========
            if user_message == "模拟回复" or user_message == "测试":
                return JsonResponse({
                    'status': 'success',
                    'data': {
                    'reply': "这是一段**模拟的 AI 回答**。\n\n小麦生病了通常是因为感染了真菌，例如赤霉病。建议及时喷洒相关的杀菌剂，并注意田间排水。\n\n（*注：此为前端调试用的 Mock 数据，未实际调用大模型和消耗配额。*）",                            'entity': "小麦"  # 模拟成功提取了实体，触发前端的 iframe 渲染
                    }
                })

            # 2. 调用大模型服务获取回答
            llm_result = get_llm_response(prompt=user_message, provider="gemini")

            # 3. 将结果打包为 JSON 返回
            # 【修改这里】：直接把整个字典丢进 data 里
            return JsonResponse({
                'status': 'success',
                'data': llm_result  # 这里面现在包含了 'reply' 和 'entity'
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'msg': '无效的 JSON 数据格式'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': str(e)})
            
    return JsonResponse({'status': 'error', 'msg': '此接口仅支持 POST 请求'})

@csrf_exempt
def image_recognize_api(request):
    """处理植物图片识别请求的 API 接口"""
    if request.method == 'POST':
        try:
            # 1. 接收前端通过 FormData 上传的图片文件
            image_file = request.FILES.get('image')
            
            if not image_file:
                return JsonResponse({'status': 'error', 'msg': '未收到图片文件'})

            # ========== 【新增：前端 Mock 测试通道】 ==========
            # 如果上传的文件名中包含 'test' 或 '测试'
            file_name = image_file.name.lower()
            if 'test' in file_name or '测试' in file_name:
                return JsonResponse({
                    'status': 'success',
                    'data': {
                        'crop_type': '蔷薇',  # 模拟识别出了原项目中带有的实体
                        'confidence': 0.9999,
                        'raw_data': [{'name': '蔷薇', 'score': 0.9999}]
                    }
                })
            # ==================================================

            # 2. 读取文件的二进制数据并调用百度识图服务
            image_content = image_file.read()
            baidu_result = recognize_plant(image_content)

            # 3. 处理服务的返回结果
            if "error" in baidu_result:
                return JsonResponse({'status': 'error', 'msg': baidu_result["error"]})

            # 4. 提取百度的识别结果并返回给前端
            results = baidu_result.get("result", [])
            if results and len(results) > 0:
                # 获取置信度最高的第一条结果
                top_match = results[0]
                return JsonResponse({
                    'status': 'success', 
                    'data': {
                        'crop_type': top_match.get('name', '未知植物'),
                        'confidence': top_match.get('score', 0),
                        'raw_data': results # 保留所有备选结果供前端参考
                    }
                })
            else:
                return JsonResponse({'status': 'error', 'msg': '未能识别出任何植物'})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': str(e)})

    return JsonResponse({'status': 'error', 'msg': '此接口仅支持 POST 请求'})

# 🌟 新增的虫害识别专属接口
@csrf_exempt
def pest_recognize_api(request):
    if request.method == 'POST':
        image_file = request.FILES.get('image')
        if not image_file:
            return JsonResponse({'status': 'error', 'msg': '没有收到图片文件'})

        try:
            # 读取前端传来的图片二进制流，喂给 YOLO
            image_content = image_file.read()
            result = recognize_pest_yolo(image_content)

            if "error" in result:
                return JsonResponse({'status': 'error', 'msg': result["error"]})

            return JsonResponse(result)

        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': f'服务器内部错误: {str(e)}'})

    return JsonResponse({'status': 'error', 'msg': '仅支持POST请求'})

def ai_chat_page(request):
    """返回 AI 问答的 HTML 页面"""
    return render(request, 'ai_chat.html')

def image_recognize_page(request):
    """返回植物识别的 HTML 页面"""
    return render(request, 'image_recognize.html')

def pest_recognize_page(request):
    return render(request, 'pest_recognize.html')
