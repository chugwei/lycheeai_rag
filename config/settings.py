"""
配置加载器 - 统一管理全局配置
"""
import os
import re
from pathlib import Path
from typing import Any
import yaml


# ${VAR_NAME} 插值正则
_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')


def _load_env_file():
    """自动加载项目根目录下的 .env 文件到环境变量"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path, override=False)
        except ImportError:
            # 手动解析 .env（降级方案）
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip()
                    # 去除引号
                    if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
                        value = value[1:-1]
                    if key not in os.environ:
                        os.environ[key] = value


class Config:
    """全局配置单例"""

    _instance = None
    _config: dict = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self.load()

    @classmethod
    def load(cls, config_path: str = None) -> dict:
        """加载 YAML 配置文件和 .env 环境变量"""
        # 优先加载 .env 环境变量
        _load_env_file()

        if config_path is None:
            # 默认配置文件路径：项目根目录下的 config/settings.yaml
            current_dir = Path(__file__).parent.parent
            config_path = current_dir / "config" / "settings.yaml"

        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            cls._config = yaml.safe_load(f)

        # ${VAR_NAME} 环境变量插值（在 .env 加载之后、路径解析之前）
        cls._interpolate_vars(cls._config)

        # 将相对路径转换为绝对路径（基于项目根目录）
        project_root = Path(__file__).parent.parent
        cls._resolve_paths(cls._config, project_root)

        # 环境变量覆盖（.env 中定义的 VECTOR_DB_TYPE 等可以覆盖 YAML 配置）
        env_overrides = {
            "VECTOR_DB_TYPE": ("vector_db", "type"),
            "MYSQL_HOST": ("vector_db", "mysql", "host"),
            "MYSQL_PORT": ("vector_db", "mysql", "port"),
            "MYSQL_USER": ("vector_db", "mysql", "user"),
            "MYSQL_PASSWORD": ("vector_db", "mysql", "password"),
            "MYSQL_DATABASE": ("vector_db", "mysql", "database"),
            "KG_TYPE": ("knowledge_graph", "type"),
            "EXTERNAL_API_KEY": ("llm", "external", "api_key"),
            "EXTERNAL_API_BASE_URL": ("llm", "external", "base_url"),
            "EXTERNAL_LLM_MODEL": ("llm", "external", "model"),
        }
        for env_key, config_keys in env_overrides.items():
            env_value = os.environ.get(env_key)
            if env_value:
                target = cls._config
                for key in config_keys[:-1]:
                    if key not in target:
                        target[key] = {}
                    target = target[key]
                target[config_keys[-1]] = env_value

        return cls._config

    @classmethod
    def _resolve_paths(cls, config: dict, base_dir: Path):
        """递归解析配置中的相对路径"""
        path_keys = {"chroma_path", "index_path", "graphml_path",
                     "raw_data_dir", "kg_data_path", "indexes_dir",
                     "prompts_dir", "file", "cache_dir",
                     "model_path", "models_dir"}
        for key, value in config.items():
            if key in path_keys and isinstance(value, str) and value.startswith("."):
                config[key] = str((base_dir / value).resolve())
            elif isinstance(value, dict):
                cls._resolve_paths(value, base_dir)

    @classmethod
    def _interpolate_vars(cls, obj: Any) -> Any:
        """
        递归遍历配置树，将字符串中的 ${VAR_NAME} 替换为对应环境变量值。

        - 纯 "${VAR}"（整串就是占位符）→ 替换为环境变量原始类型（保持 str）
        - 内嵌 "${VAR}" → 替换为字符串拼接
        - 环境变量未定义 → 替换为空字符串并发出 warning（日志在调用方处理）
        """
        if isinstance(obj, dict):
            for key in obj:
                obj[key] = cls._interpolate_vars(obj[key])
            return obj
        elif isinstance(obj, list):
            for i in range(len(obj)):
                obj[i] = cls._interpolate_vars(obj[i])
            return obj
        elif isinstance(obj, str):
            def _replacer(m):
                var_name = m.group(1)
                return os.environ.get(var_name, "")
            return _VAR_PATTERN.sub(_replacer, obj)
        return obj

    @classmethod
    def get(cls, key_path: str = None, default: Any = None) -> Any:
        """通过点号路径获取配置项，如 Config.get('llm.chat_model')"""
        if cls._config is None:
            cls.load()

        if key_path is None:
            return cls._config

        keys = key_path.split(".")
        value = cls._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    @classmethod
    def set(cls, key_path: str, value: Any):
        """设置配置项"""
        if cls._config is None:
            cls.load()

        keys = key_path.split(".")
        config = cls._config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value


# 模块级便捷函数
def get_config(key_path: str = None, default: Any = None) -> Any:
    return Config.get(key_path, default)
