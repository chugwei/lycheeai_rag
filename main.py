"""
LycheeAI LangChain 版本 - FastAPI 入口

API 端点与原系统完全一致，前端无需修改即可对接。
"""
import sys
import json
import asyncio
import base64
import hashlib
import hmac
import time
from pathlib import Path
from typing import Optional

# Python 3.8 兼容：asyncio.to_thread 在 3.9 才引入
if sys.version_info < (3, 9):
    from functools import partial
    async def _to_thread_compat(func, /, *args, **kwargs):
        loop = asyncio.get_running_loop()
        if kwargs:
            return await loop.run_in_executor(None, partial(func, *args, **kwargs))
        return await loop.run_in_executor(None, func, *args)
    asyncio.to_thread = _to_thread_compat

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from loguru import logger

from config.settings import Config
from api.schemas import (
    QueryRequest, QueryResponse, PredictionRequest,
    HealthResponse, SourceItem, LLMConfigRequest, LLMConfigResponse,
)
from api.knowledge_routes import router as knowledge_router
from external_apis.api_client import LycheeAPIClient

# 加载配置
Config.load()

# 创建 FastAPI 应用
app = FastAPI(
    title="LycheeAI 荔知君 RAG系统 (LangChain版)",
    description="基于 LangChain 框架的荔枝种植垂直领域 RAG 问答系统 API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 知识库路由
app.include_router(knowledge_router)

# ==================== LLM分析Prompt构建 ====================

API_CHINESE_NAMES = {
    "cixionghua": "雌雄花比例检测",
    "huasui": "花穗数量检测",
    "shaoliang": "梢量分割",
    "kaihualv": "开花率检测",
    "zuoguolv": "坐果率检测",
    "baidian": "白点检测",
    "guoshi": "果实成熟度检测",
    "shao": "新梢长度测量",
    "dizhuchong": "蒂蛀虫化蛹率检测",
}


def _build_api_analysis_prompt(api_type: str, result: dict) -> str:
    """根据API类型和返回结果，构建LLM分析Prompt"""
    api_name = API_CHINESE_NAMES.get(api_type, api_type)
    data = result.get("detection_results") or result.get("results") or result

    param_lines = []
    if api_type == "cixionghua":
        param_lines.append(f"- 雄花数量：{data.get('male_count', '未知')}")
        param_lines.append(f"- 雌花数量：{data.get('female_count', '未知')}")
        param_lines.append(f"- 雌花比例：{data.get('female_ratio', '未知')}%")
    elif api_type == "huasui":
        param_lines.append(f"- 花穗数量：{data.get('count', '未知')}")
    elif api_type == "shaoliang":
        param_lines.append(f"- 梢量占比：{data.get('msg1', '未知')}")
    elif api_type == "kaihualv":
        param_lines.append(f"- 开花率：{data.get('flower_rate', '未知')}%")
    elif api_type == "zuoguolv":
        param_lines.append(f"- 果实个数：{data.get('fruit_count', '未知')}")
    elif api_type == "baidian":
        param_lines.append(f"- 白点数量：{data.get('white_spots_count', '未知')}")
        if data.get("message"):
            param_lines.append(f"- 检测信息：{data['message']}")
    elif api_type == "guoshi":
        counts = data.get("counts", {})
        if isinstance(counts, dict):
            param_lines.append(f"- 青果数：{counts.get('green', 0)}")
            param_lines.append(f"- 半熟果数：{counts.get('semi_ripe', 0)}")
            param_lines.append(f"- 熟果数：{counts.get('ripe', 0)}")
    elif api_type == "shao":
        param_lines.append(f"- 检测梢数：{data.get('total_boxes', '未知')}")
        param_lines.append(f"- 平均长度：{data.get('avg_length', '未知')} cm")
        param_lines.append(f"- 平均粗度：{data.get('avg_thickness', '未知')} cm")
    elif api_type == "dizhuchong":
        param_lines.append(f"- 化蛹率：{data.get('pupation_rate', '未知')}%")
        param_lines.append(f"- 风险等级：{data.get('risk_level', '未知')}")
        param_lines.append(f"- 成虫数：{data.get('adult_count', '未知')}")
        param_lines.append(f"- 茧数：{data.get('cocoon_count', '未知')}")
    else:
        param_lines.append(f"- 原始数据：{json.dumps(result, ensure_ascii=False)[:200]}")

    params_str = "\n".join(param_lines)
    return f"""你是一个专业的荔枝种植专家。以下是荔枝{api_name}的检测结果：

{params_str}

请直接输出以下两部分内容（用中文），不要输出任何思考过程、分析步骤或推理链：

1. 【当前状况总结】用1-2句话概括当前荔枝园的检测状况，指出关键指标是否正常。

2. 【决策建议】给出1-3条具体、可操作的管理建议，包括建议采取的措施和理由。"""


# ==================== 管理员认证 ====================

ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
TOKEN_SECRET = "lycheeai-secret-key-2026"
TOKEN_EXPIRE = 86400


def _make_token() -> str:
    payload = json.dumps({"user": ADMIN_USER, "t": int(time.time()) + TOKEN_EXPIRE})
    sig = hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def _verify_token(token: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = decoded.rsplit(".", 1)
        expected_sig = hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        if sig != expected_sig:
            return False
        data = json.loads(payload)
        return data.get("user") == ADMIN_USER and data.get("t", 0) >= time.time()
    except Exception:
        return False


def require_admin(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, "需要登录")
    token = authorization.replace("Bearer ", "")
    if not _verify_token(token):
        raise HTTPException(401, "令牌无效或已过期")
    return True


# ==================== API 端点 ====================

@app.post("/api/auth/login", tags=["系统"])
async def admin_login(data: dict):
    """管理员登录"""
    if data.get("username") == ADMIN_USER and data.get("password") == ADMIN_PASS:
        return {"token": _make_token(), "user": ADMIN_USER}
    raise HTTPException(401, "用户名或密码错误")


@app.get("/api/health", response_model=HealthResponse, tags=["系统"])
async def health_check():
    """健康检查"""
    try:
        from rag_chain import get_pipeline
        pipeline = get_pipeline()
        llm_available = True
        llm_backend = "external"
        llm_model = Config.get("llm.external.model", "deepseek-v4-flash")
    except Exception:
        llm_available = False
        llm_backend = "unavailable"
        llm_model = None

    # 检查 BM25
    from data_pipeline.bm25_indexer import BM25Indexer
    bm25 = BM25Indexer()
    bm25_loaded = bm25.load()

    # 检查向量库
    db_type = Config.get("vector_db.type", "milvus_mysql")
    if db_type == "milvus_mysql":
        vector_status = "milvus+mysql"
    elif db_type == "milvus":
        vector_status = "milvus"
    else:
        vector_status = "chroma"

    return HealthResponse(
        status="running",
        llm_available=llm_available,
        llm_backend=llm_backend,
        llm_model=llm_model,
        vector_db_status=vector_status,
        bm25_loaded=bm25_loaded,
        kg_loaded=Path(Config.get("knowledge_graph.graphml_path", "")).exists(),
    )


@app.post("/api/query", response_model=QueryResponse, tags=["RAG问答"])
async def query(request: QueryRequest):
    """纯文本 RAG 问答"""
    try:
        from rag_chain import get_pipeline
        pipeline = get_pipeline()

        result = await asyncio.to_thread(
            pipeline.run,
            query=request.query,
            conversation_id=request.conversation_id,
            phenology_date=request.phenology_date,
            use_query_expansion=request.use_query_expansion,
        )

        return QueryResponse(
            answer=result.answer,
            sources=[SourceItem(**s) for s in result.sources],
            intent=result.intent,
            confidence=result.confidence,
            conversation_id=result.conversation_id,
            retrieval_paths_used=result.retrieval_paths_used,
            phenology=result.phenology,
            latency=result.latency,
        )
    except Exception as e:
        logger.error(f"问答失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query/image", response_model=QueryResponse, tags=["RAG问答"])
async def query_with_image(
    query: str = Form(...),
    image: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    phenology_date: Optional[str] = Form(None),
    image_api_type: str = Form("guoshi"),
):
    """带图片的 RAG 问答"""
    try:
        from rag_chain import get_pipeline
        pipeline = get_pipeline()

        image_bytes = await image.read()
        result = await asyncio.to_thread(
            pipeline.run,
            query=query,
            image_bytes=image_bytes,
            image_api_type=image_api_type,
            conversation_id=conversation_id,
            phenology_date=phenology_date,
        )

        return QueryResponse(
            answer=result.answer,
            sources=[SourceItem(**s) for s in result.sources],
            intent=result.intent,
            confidence=result.confidence,
            conversation_id=result.conversation_id,
            retrieval_paths_used=result.retrieval_paths_used,
            phenology=result.phenology,
            image_analysis=result.image_analysis,
            latency=result.latency,
        )
    except Exception as e:
        logger.error(f"图文问答失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/image/analyze", tags=["图像识别"])
async def analyze_image(
    image: UploadFile = File(...),
    api_type: str = Form("guoshi"),
    city_code: Optional[str] = Form(None),
    city_name: Optional[str] = Form(None),
):
    """单独调用图像识别 API，并调用LLM生成分析建议"""
    try:
        image_bytes = await image.read()
        client = LycheeAPIClient()

        api_map = {
            "cixionghua": lambda: client.detect_cixionghua(image_bytes),
            "huasui": lambda: client.detect_huasui(image_bytes),
            "shaoliang": lambda: client.detect_shaoliang(image_bytes),
            "kaihualv": lambda: client.detect_kaihualv(image_bytes),
            "zuoguolv": lambda: client.detect_zuoguolv(image_bytes),
            "baidian": lambda: client.detect_baidian(image_bytes),
            "guoshi": lambda: client.detect_guoshi(image_bytes),
            "shao": lambda: client.detect_shao(image_bytes),
            "dizhuchong": lambda: client.detect_dizhuchong(
                image_bytes, city_code=city_code, city_name=city_name
            ),
        }

        if api_type not in api_map:
            raise HTTPException(400, f"不支持的API类型: {api_type}")

        result = api_map[api_type]()

        # 调用LLM生成分析建议
        try:
            from llm_factory import create_llm_for_analysis
            llm = create_llm_for_analysis()
            prompt = _build_api_analysis_prompt(api_type, result)
            messages = [
                {"role": "system", "content": "你是一个荔枝种植专家。请直接回答问题，不要输出任何思考过程、分析步骤或推理链。"},
                {"role": "user", "content": prompt},
            ]
            response = llm.invoke(messages)
            result["llm_analysis"] = response.content.strip()
        except Exception as e:
            logger.warning(f"LLM分析生成失败: {e}")
            result["llm_analysis"] = None
            result["llm_analysis_error"] = str(e)[:80]

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图像识别失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/predict", tags=["预测服务"])
async def predict(request: PredictionRequest):
    """调用预测类 API"""
    try:
        client = LycheeAPIClient()

        if request.api_type == "chunxiang":
            return client.predict_chunxiang(city=request.city_code)
        elif request.api_type == "shuangyimeibing":
            return client.predict_shuangyimeibing(city_code=request.city_code)
        elif request.api_type == "tanjubing":
            return client.predict_tanjubing()
        elif request.api_type == "tanjubing_latest":
            if not request.location_code:
                raise HTTPException(400, "需要 location_code 参数")
            return client.get_tanjubing_latest(request.location_code)
        elif request.api_type == "tanjubing_history":
            if not (request.location_code and request.datetime_str):
                raise HTTPException(400, "需要 location_code 和 datetime_str 参数")
            return client.get_tanjubing_history(request.datetime_str, request.location_code)
        elif request.api_type == "yield":
            return client.get_yield_prediction()
        elif request.api_type == "yield_features":
            return client.get_predictor_features()
        elif request.api_type == "yield_health":
            return client.get_predictor_health()
        else:
            raise HTTPException(400, f"不支持的预测类型: {request.api_type}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/apis", tags=["系统"])
async def list_apis():
    """列出所有可用的外部 API"""
    return LycheeAPIClient().list_all_apis()


@app.get("/api/llm/config", response_model=LLMConfigResponse, tags=["LLM配置"])
async def get_llm_config():
    """获取当前 LLM 配置"""
    return LLMConfigResponse(
        backend="external",
        active_backend="external",
        base_url=Config.get("llm.external.base_url"),
        model=Config.get("llm.external.model", "deepseek-v4-flash"),
        api_key_configured=bool(Config.get("llm.external.api_key")),
        available_backends=["external"],
    )


@app.post("/api/llm/config", response_model=LLMConfigResponse, tags=["LLM配置"])
async def set_llm_config(request: LLMConfigRequest):
    """运行时切换 LLM 配置（LangChain 版本仅支持 external）"""
    if request.api_key:
        Config.set("llm.external.api_key", request.api_key)
    if request.base_url:
        Config.set("llm.external.base_url", request.base_url)
    if request.model:
        Config.set("llm.external.model", request.model)

    # 重建管线
    import rag_chain as rc
    rc._pipeline = None

    return LLMConfigResponse(
        backend="external",
        active_backend="external",
        base_url=Config.get("llm.external.base_url"),
        model=Config.get("llm.external.model", "deepseek-v4-flash"),
        api_key_configured=bool(Config.get("llm.external.api_key")),
        available_backends=["external"],
    )


# ==================== SPA 前端 ====================
# 挂载 Vue3 前端静态文件（必须放在所有 API 路由之后）
from fastapi.responses import FileResponse

FRONTEND_DIR = Path(__file__).parent / "web" / "dist"
if FRONTEND_DIR.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """SPA fallback - 所有非API路径返回 index.html"""
        file_path = FRONTEND_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    logger.info(f"前端静态目录已挂载: {FRONTEND_DIR}")
else:
    logger.warning(f"前端构建产物不存在: {FRONTEND_DIR}，跳过静态文件挂载")


def start_server(host: str = None, port: int = None):
    """启动 FastAPI 服务（LangChain 版本默认端口 18889，避免与原系统 18888 冲突）"""
    import uvicorn
    host = host or Config.get("server.host", "0.0.0.0")
    port = port or 18889  # LangChain 版本使用不同端口
    logger.info(f"启动 LangChain RAG 服务: http://localhost:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
