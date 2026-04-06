import os
import json
import logging

logger = logging.getLogger(__name__)

# 获取当前文件所在目录，并拼接出配置文件的完整路径
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'api_config.json')

def get_api_key(key_name):
    """
    获取 API Key，优先级：配置文件 > 环境变量
    """
    config_val = ""
    
    # 1. 尝试从配置文件中读取
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 读取对应的值，并去除可能的首尾空格
                config_val = config.get(key_name, "").strip()
        except json.JSONDecodeError:
            logger.error(f"配置文件 {CONFIG_FILE_PATH} 格式错误，请检查 JSON 语法。")
        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            
    # 2. 如果配置文件里填了有效的值，直接返回
    if config_val:
        return config_val
        
    # 3. 如果没填（空字符串）或文件不存在，回退到获取环境变量
    return os.environ.get(key_name, "").strip()

