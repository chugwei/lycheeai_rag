"""
荔枝图像识别与病虫害预测 API 客户端

封装13个外部API接口：
1.  雌雄花比例检测      POST /cixionghua/detect
2.  花穗数量检测         POST /huasui/detect
3.  梢量分割模型         POST /shaoliang/upload
4.  开花率检测           POST /kaihualv/detect_flower_rate
5.  果实个数检测(坐果率) POST /zuoguolv/upload
6.  白点检测             POST /baidian/detect
7.  果实检测             POST /guoshi/detect
8.  椿象预测             GET  /cx/predict
9.  霜疫霉病风险预测      GET  /symb/predict/orchard/auto
10. 炭疽病预测           POST /tjb/daily_process (+ 工具接口)
11. 新梢长度测量          POST /shao/detect_obb
12. 蒂蛀虫化蛹率检测      POST /dizhuchong/detect/
13. 产量预测服务          GET  /predictor/ (+ /predict + /features)
"""
import time
from typing import Optional, Dict, Any
import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_config


class LycheeAPIClient:
    """荔枝API统一客户端（优化7: 使用requests.Session复用连接, 优化10: 重试机制）"""

    def __init__(self):
        self.base_url = get_config("external_api.base_url",
                                   "http://89568cq9zc12.vicp.fun")
        self.timeout = get_config("external_api.timeout", 60)
        self.retry_times = get_config("external_api.retry_times", 2)
        self.default_city = get_config("external_api.default_city_code", "441284")
        # 优化7: 使用Session复用TCP连接
        self._session = requests.Session()
        self._session.headers.update({"Connection": "keep-alive"})

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _post_image(self, endpoint: str, image_bytes: bytes,
                    extra_data: dict = None) -> dict:
        """通用图片上传 POST 请求（优化10: 自动重试）"""
        url = f"{self.base_url}{endpoint}"
        files = {"file": ("image.jpg", image_bytes, "image/jpeg")}
        data = extra_data or {}

        logger.info(f"API 调用: POST {url}")
        try:
            response = self._session.post(
                url, files=files, data=data, timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API 调用失败 {url}: {e}")
            return {"error": str(e), "status": "failed"}

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _get(self, endpoint: str, params: dict = None) -> dict:
        """通用 GET 请求（优化10: 自动重试）"""
        url = f"{self.base_url}{endpoint}"
        logger.info(f"API 调用: GET {url}")
        try:
            response = self._session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API 调用失败 {url}: {e}")
            return {"error": str(e), "status": "failed"}

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _post_json(self, endpoint: str, json_data: dict = None) -> dict:
        """通用 JSON POST 请求（优化10: 自动重试）"""
        url = f"{self.base_url}{endpoint}"
        logger.info(f"API 调用: POST {url}")
        try:
            response = self._session.post(url, json=json_data, timeout=self.timeout)
            response.raise_for_status()
            return response.json() if response.content else {"status": "success"}
        except requests.exceptions.RequestException as e:
            logger.error(f"API 调用失败 {url}: {e}")
            return {"error": str(e), "status": "failed"}

    # ========== 接口1：雌雄花比例检测 ==========
    def detect_cixionghua(self, image_bytes: bytes) -> dict:
        """荔枝雌雄花比例检测"""
        return self._post_image("/cixionghua/detect", image_bytes)

    # ========== 接口2：花穗数量检测 ==========
    def detect_huasui(self, image_bytes: bytes) -> dict:
        """荔枝花穗数量检测"""
        return self._post_image("/huasui/detect", image_bytes)

    # ========== 接口3：梢量分割模型 ==========
    def detect_shaoliang(self, image_bytes: bytes) -> dict:
        """荔枝梢量分割"""
        return self._post_image("/shaoliang/upload", image_bytes)

    # ========== 接口4：开花率检测 ==========
    def detect_kaihualv(self, image_bytes: bytes) -> dict:
        """荔枝开花率检测"""
        return self._post_image("/kaihualv/detect_flower_rate", image_bytes)

    # ========== 接口5：果实个数检测（坐果率） ==========
    def detect_zuoguolv(self, image_bytes: bytes) -> dict:
        """荔枝果实个数检测（坐果率）"""
        return self._post_image("/zuoguolv/upload", image_bytes)

    # ========== 接口6：白点检测 ==========
    def detect_baidian(self, image_bytes: bytes) -> dict:
        """荔枝白点检测"""
        return self._post_image("/baidian/detect", image_bytes)

    # ========== 接口7：果实检测（成熟度） ==========
    def detect_guoshi(self, image_bytes: bytes) -> dict:
        """荔枝果实检测（绿果/半熟/成熟）"""
        return self._post_image("/guoshi/detect", image_bytes)

    # ========== 接口8：椿象预测 ==========
    def predict_chunxiang(self, city: str = None) -> dict:
        """椿象数量预测与风险评估"""
        params = {"city": city or self.default_city}
        return self._get("/cx/predict", params=params)

    # ========== 接口9：霜疫霉病风险预测 ==========
    def predict_shuangyimeibing(self, city_code: str = None) -> dict:
        """荔枝霜疫霉病发病风险预测"""
        endpoint = "/symb/predict/orchard/auto"
        params = {}
        if city_code:
            params["city_code"] = city_code
        return self._get(endpoint, params=params)

    # ========== 接口10：炭疽病预测 ==========
    def predict_tanjubing(self) -> dict:
        """荔枝炭疽病预测（收集10天气象数据）"""
        url = f"{self.base_url}/tjb/daily_process"
        logger.info(f"API 调用: POST {url}")
        try:
            response = requests.post(url, timeout=self.timeout)
            response.raise_for_status()
            text = response.text.strip()
            # 该接口返回纯文本（如 Succeed），不是 JSON
            if text.lower() in ("succeed", "success", "ok"):
                return {
                    "status": "processing",
                    "message": "炭疽病预测任务已提交，正在后台处理。",
                    "note": "外部服务暂未返回具体风险数值，请稍后通过 'tanjubing_latest' 查询最新结果。"
                }
            try:
                return response.json()
            except ValueError:
                return {"status": "processing", "message": text or "处理已触发"}
        except requests.exceptions.RequestException as e:
            logger.error(f"API 调用失败 {url}: {e}")
            return {"error": str(e), "status": "failed"}

    def get_tanjubing_latest(self, location_code: str) -> dict:
        """获取炭疽病最新预警数据"""
        return self._post_json("/tjb/get_new_result",
                               {"location_code": location_code})

    def get_tanjubing_history(self, datetime_str: str,
                              location_code: str) -> dict:
        """获取炭疽病历史预测结果"""
        return self._post_json("/tjb/get_history_result", {
            "datetime": datetime_str,
            "location_code": location_code
        })

    def update_tanjubing_weather(self, location_code: str) -> dict:
        """更新炭疽病天气数据"""
        return self._post_json("/tjb/update_weather_data",
                               {"location_code": location_code})

    def init_tanjubing_area(self, location_code: str) -> dict:
        """初始化炭疽病预测区域"""
        return self._post_json("/tjb/init_area",
                               {"location_code": location_code})

    # ========== 接口11：新梢长度测量 ==========
    def detect_shao(self, image_bytes: bytes) -> dict:
        """荔枝新梢长度与粗度测量"""
        return self._post_image("/shao/detect_obb", image_bytes)

    # ========== 接口12：蒂蛀虫化蛹率检测 ==========
    def detect_dizhuchong(self, image_bytes: bytes,
                          city_code: str = None,
                          city_name: str = None) -> dict:
        """荔枝蒂蛀虫化蛹率检测"""
        extra = {}
        if city_code:
            extra["city_code"] = city_code
        if city_name:
            extra["city_name"] = city_name
        return self._post_image("/dizhuchong/detect/", image_bytes, extra)

    # ========== 接口13：产量预测服务 ==========
    def get_predictor_health(self) -> dict:
        """产量预测服务健康检查"""
        return self._get("/predictor/")

    def get_yield_prediction(self) -> dict:
        """获取最新荔枝产量预测"""
        return self._get("/predictor/predict")

    def get_predictor_features(self) -> dict:
        """查看产量预测模型输入特征"""
        return self._get("/predictor/features")

    # ========== 便捷方法 ==========
    def get_result_image_url(self, result: dict) -> Optional[str]:
        """获取结果图片的完整URL（兼容旧版，调用新版提取逻辑）"""
        info = self.extract_result_image(result)
        return info.get("url")

    def extract_result_image(self, result: dict) -> dict:
        """
        从外部API响应中提取结果图片信息（递归搜索）

        根据接口文档V5，9个图像API的图片字段分布：
        - cixionghua/huasui/shaoliang/kaihualv/zuoguolv/shao: result_image_url（顶层，相对路径）
        - baidian/guoshi: processed_image_url（顶层，baidian的是绝对路径但指向127.0.0.1:8000）
        - dizhuchong: url + base64 嵌套在 detection_results 内

        返回:
            {"url": str|None, "base64": str|None, "mime": str|None, "source_key": str|None}
        """
        result_info = {"url": None, "base64": None, "mime": None, "source_key": None}

        # Step 1: 递归搜索所有层级，找图片URL和base64
        def _search(obj, depth=0):
            if depth > 6 or not isinstance(obj, (dict, list)):
                return
            if isinstance(obj, dict):
                for key, val in obj.items():
                    key_lower = key.lower()
                    # 检测图片URL字段
                    if isinstance(val, str) and not result_info["url"]:
                        if any(kw in key_lower for kw in ["image_url", "img_url", "processed", "visual", "result_url", "save_path", "save_image_path"]):
                            if val.startswith("http://") or val.startswith("https://") or val.startswith("/"):
                                result_info["url"] = val
                                result_info["source_key"] = key
                        elif key_lower == "url" and (val.startswith("http") or val.startswith("/")):
                            result_info["url"] = val
                            result_info["source_key"] = key
                    # 检测base64图片数据
                    if isinstance(val, str) and not result_info["base64"] and key_lower in ("base64", "image_base64", "img_base64"):
                        if len(val) > 100 and not val.startswith("http"):
                            result_info["base64"] = val
                            result_info["source_key"] = f"{result_info.get('source_key', '') or ''}.{key}" if result_info.get("source_key") else key
                    # 递归
                    _search(val, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    _search(item, depth + 1)

        _search(result)

        # Step 2: 修正URL —— 替换127.0.0.1为真实外部API地址（baidian接口的坑）
        if result_info["url"] and "127.0.0.1" in result_info["url"]:
            # 把 http://127.0.0.1:8000/path 替换为 http://89568cq9zc12.vicp.fun/path
            import re
            result_info["url"] = re.sub(r'http://127\.0\.0\.1:\d+', self.base_url.rstrip('/'), result_info["url"])
            result_info["source_key"] = (result_info.get("source_key") or "") + "(fixed_127.0.0.1)"

        # Step 3: 补全相对路径为完整URL
        if result_info["url"] and not result_info["url"].startswith("http"):
            # 确保base_url和path之间只有一个/
            base = self.base_url.rstrip("/")
            path = result_info["url"].lstrip("/")
            result_info["url"] = f"{base}/{path}"

        # Step 4: 如果API响应中已有base64但没找到MIME，设置默认值
        if result_info["base64"] and not result_info["mime"]:
            # 尝试从base64头判断格式
            b64_header = result_info["base64"][:30]
            if b64_header.startswith("/9j/"):
                result_info["mime"] = "image/jpeg"
            elif b64_header.startswith("iVBOR"):
                result_info["mime"] = "image/png"
            elif b64_header.startswith("R0lGOD"):
                result_info["mime"] = "image/gif"
            elif b64_header.startswith("UklGR"):
                result_info["mime"] = "image/webp"
            else:
                result_info["mime"] = "image/jpeg"

        return result_info

    def list_all_apis(self) -> dict:
        """列出所有可用API"""
        return {
            "image_apis": [
                {"id": 1, "name": "雌雄花比例检测", "method": "POST",
                 "endpoint": "/cixionghua/detect", "func": "detect_cixionghua"},
                {"id": 2, "name": "花穗数量检测", "method": "POST",
                 "endpoint": "/huasui/detect", "func": "detect_huasui"},
                {"id": 3, "name": "梢量分割模型", "method": "POST",
                 "endpoint": "/shaoliang/upload", "func": "detect_shaoliang"},
                {"id": 4, "name": "开花率检测", "method": "POST",
                 "endpoint": "/kaihualv/detect_flower_rate", "func": "detect_kaihualv"},
                {"id": 5, "name": "果实个数检测(坐果率)", "method": "POST",
                 "endpoint": "/zuoguolv/upload", "func": "detect_zuoguolv"},
                {"id": 6, "name": "白点检测", "method": "POST",
                 "endpoint": "/baidian/detect", "func": "detect_baidian"},
                {"id": 7, "name": "果实检测(成熟度)", "method": "POST",
                 "endpoint": "/guoshi/detect", "func": "detect_guoshi"},
                {"id": 11, "name": "新梢长度测量", "method": "POST",
                 "endpoint": "/shao/detect_obb", "func": "detect_shao"},
                {"id": 12, "name": "蒂蛀虫化蛹率检测", "method": "POST",
                 "endpoint": "/dizhuchong/detect/", "func": "detect_dizhuchong"},
            ],
            "prediction_apis": [
                {"id": 8, "name": "椿象预测", "method": "GET",
                 "endpoint": "/cx/predict", "func": "predict_chunxiang"},
                {"id": 9, "name": "霜疫霉病风险预测", "method": "GET",
                 "endpoint": "/symb/predict/orchard/auto", "func": "predict_shuangyimeibing"},
                {"id": 10, "name": "炭疽病预测", "method": "POST",
                 "endpoint": "/tjb/daily_process", "func": "predict_tanjubing"},
                {"id": 13, "name": "产量预测服务", "method": "GET",
                 "endpoint": "/predictor/predict", "func": "get_yield_prediction"},
            ]
        }
