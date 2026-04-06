import os
import json
import logging
import requests
from .config_loader import get_api_key

# 引入原作者封装好的图谱数据库连接
try:
    from toolkit.pre_load import neo_con
except ImportError:
    neo_con = None
    logging.warning("未能导入 neo_con，知识图谱 RAG 功能可能受限。")

logger = logging.getLogger(__name__)

GEMINI_API_KEY = get_api_key("GEMINI_API_KEY")


def get_llm_response(prompt, provider="gemini"):
    """
    统一的 LLM 调用入口
    """
    if provider == "gemini":
        return _call_gemini_rag(prompt)
    else:
        return f"错误：未知的模型提供商 '{provider}'"


def _ask_gemini_raw(prompt_text, response_json=False):
    """底层基础工具：向 Gemini 发送请求"""
    if not GEMINI_API_KEY:
        raise ValueError("系统配置错误：未配置 Gemini API Key。")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}

    # 【新增】：如果要求 JSON 格式，就在请求体里加上强制约束
    if response_json:
        payload["generationConfig"] = {"responseMimeType": "application/json"}

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_gemini_rag(user_prompt):
    """
    核心 RAG 逻辑：提取实体 -> 查询图谱 -> 融合生成
    """
    try:
        # ==========================================
        # 第一步：实体提取 (Entity Extraction - 强制 JSON 模式)
        # ==========================================
        extract_prompt = (
            "请从以下农业问题中提取出一个核心实体名称（例如：具体的农作物、病虫害名称）。\n"
            "如果没有明确的农业实体，请提取为 '无'。\n"
            "你必须严格返回一个 JSON 对象，格式为：{\"entity\": \"实体名称\"}\n\n"
            f"问题：{user_prompt}"
        )

        try:
            # 开启 response_json=True 强制 API 层面只输出 JSON
            raw_json_str = _ask_gemini_raw(extract_prompt, response_json=True)

            # 将大模型返回的纯 JSON 字符串解析为 Python 字典
            entity_data = json.loads(raw_json_str)
            raw_entity = entity_data.get("entity", "无")

            # 基础安全清洗（防注入）
            entity_name = raw_entity.strip().replace('"', '').replace("'", "").replace('\n', '')

            # 如果名字异常长，说明提取失败
            if len(entity_name) > 15:
                entity_name = "无"

            logger.info(f"LLM 最终提取的实体为: {entity_name}")

        except json.JSONDecodeError as e:
            logger.error(f"大模型未返回标准 JSON: {e}\n原始输出: {raw_json_str}")
            entity_name = "无"
        except Exception as e:
            logger.error(f"实体提取失败: {e}")
            entity_name = "无"

        # ==========================================
        # 第二步：检索图谱 (Knowledge Retrieval)
        # ==========================================
        kg_context = ""
        # 只要不是"无"，并且数据库连接存在，就去查库
        if entity_name and entity_name != "无" and neo_con:
            try:
                # 调用原作者写好的查询方法
                relations = neo_con.getEntityRelationbyEntity(entity_name)
                if relations and len(relations) > 0:
                    kg_context = json.dumps(relations, ensure_ascii=False)
                    logger.info(f"成功从图谱中检索到 {entity_name} 的数据。")
            except Exception as db_e:
                logger.error(f"图谱查询出错，跳过该实体的检索: {db_e}")
                kg_context = ""  # 如果数据库还是报错了，我们捕获它，不让整个程序崩溃

        # ==========================================
        # 第三步：增强生成 (Augmented Generation)
        # ==========================================
        system_instruction = (
            "你是一个专业的农业知识图谱问答助手。"
            "请客观、准确地解答用户的农业问题。"
        )

        # 如果从数据库查到了数据，就塞进提示词里
        if kg_context:
            system_instruction += (
                "\n\n【重要提示】：我已经为你检索到了本地知识图谱中的相关数据，"
                "请优先基于以下图谱数据来回答用户问题。如果图谱数据不够全面，你可以补充你的专业知识。\n"
                f"【本地知识图谱数据】：\n{kg_context}\n"
            )
        else:
            system_instruction += (
                "\n\n（注意：本地图谱未检索到相关实体，请依靠你的内置专业知识进行解答。）\n"
            )

        final_prompt = f"{system_instruction}\n\n【用户问题】：{user_prompt}"

        # 拿着融合了图谱数据的最终提示词，去问 AI 要最终答案
        final_answer = _ask_gemini_raw(final_prompt)

        valid_entity = entity_name if (entity_name and entity_name != "无") else None

        # 可以在答案末尾加个友好的图谱跳转提示
        if kg_context:
            final_answer += f"\n\n---\n💡 **提示**：以上回答参考了知识图谱实体【{entity_name}】，[点击这里查看完整图谱关系](/search_entity?user_text={entity_name})。"

        return {
            "reply": final_answer,
            "entity": valid_entity
        }


    except requests.exceptions.RequestException as e:
        logger.error(f"网络请求失败: {e}")
        return {"reply": "抱歉，调用 AI 服务时出现网络异常，请稍后再试。", "entity": None}

    except Exception as e:
        logger.error(f"RAG 处理流程发生错误: {e}")
        return {"reply": f"抱歉，系统处理时发生未知错误：{str(e)}", "entity": None}
