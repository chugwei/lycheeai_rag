"""
FastAPI 请求/响应模型
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any


class QueryRequest(BaseModel):
    """问答请求"""
    query: str = Field(..., description="用户问题", examples=["荔枝霜疫霉病怎么防治？"])
    conversation_id: Optional[str] = Field(None, description="对话ID（多轮对话）")
    phenology_date: Optional[str] = Field(None, description="物候期日期 YYYY-MM-DD",
                                          examples=["2025-06-15"])
    use_query_expansion: bool = Field(False, description="是否启用查询扩展")
    image_api_type: Optional[str] = Field("guoshi", description="图像识别API类型")


class SourceItem(BaseModel):
    """引用来源"""
    ref_id: int
    source: str
    text_preview: str
    retrieval_paths: List[str] = []
    rerank_score: float = 0.0


class QueryResponse(BaseModel):
    """问答响应"""
    answer: str
    sources: List[SourceItem] = []
    intent: str
    confidence: float
    conversation_id: str
    retrieval_paths_used: List[str] = []
    phenology: Optional[dict] = None
    image_analysis: Optional[dict] = None
    latency: float
    stage_timings: dict = {}


class ImageAnalysisRequest(BaseModel):
    """图像识别请求（指定API类型）"""
    api_type: str = Field(..., description="API类型",
                          examples=["guoshi", "cixionghua", "dizhuchong"])


class PredictionRequest(BaseModel):
    """预测类API请求"""
    api_type: str = Field(..., description="预测类型",
                          examples=["chunxiang", "shuangyimeibing",
                                   "tanjubing", "yield"])
    city_code: Optional[str] = Field(None, description="城市编码")
    location_code: Optional[str] = Field(None, description="9位地区编码（炭疽病用）")
    datetime_str: Optional[str] = Field(None, description="日期（历史查询用）")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    llm_available: bool
    llm_backend: Optional[str] = None
    llm_model: Optional[str] = None
    vector_db_status: str
    bm25_loaded: bool
    kg_loaded: bool


class LLMConfigRequest(BaseModel):
    """LLM 配置更新请求"""
    backend: Optional[str] = Field(None, description="后端类型: openai | external | ollama | auto")
    base_url: Optional[str] = Field(None, description="API 地址")
    api_key: Optional[str] = Field(None, description="API 密钥 (仅 external 后端)")
    model: Optional[str] = Field(None, description="模型名称")
    extra_body: Optional[str] = Field(None, description="额外请求体参数(JSON)，如 {\"enable_thinking\": false}")


class LLMConfigResponse(BaseModel):
    """LLM 当前配置"""
    backend: str
    active_backend: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key_configured: bool = False
    available_backends: List[str] = []
    extra_body: Optional[str] = Field(None, description="当前 extra_body 配置")
