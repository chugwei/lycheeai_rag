"""
对话状态管理器

功能：
1. 维护多轮对话的上下文状态
2. 跟踪当前意图和物候期
3. 缓存上一轮检索结果
4. 过期清理
"""
import time
import uuid
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from loguru import logger

from config.settings import get_config


@dataclass
class ConversationState:
    """对话状态"""
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    history: list = field(default_factory=list)
    current_intent: Optional[str] = None
    current_phenology: Optional[dict] = None
    last_retrieved_docs: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


class StateManager:
    """对话状态管理器"""

    def __init__(self):
        self.storage = get_config("conversation.storage", "memory")
        self.max_history = get_config("conversation.max_history_turns", 10)
        self.timeout = get_config("conversation.timeout_seconds", 1800)

        if self.storage == "redis":
            import redis
            redis_url = get_config("conversation.redis_url", "redis://localhost:6379")
            self.redis = redis.from_url(redis_url)
        else:
            self.conversations: dict = {}

    def get_or_create(self, conversation_id: str = None) -> ConversationState:
        """获取或创建对话状态"""
        if conversation_id and self._exists(conversation_id):
            state = self._load(conversation_id)
            # 检查是否超时
            if time.time() - state.last_active > self.timeout:
                logger.info(f"对话 {conversation_id} 已超时，创建新对话")
                state = ConversationState()
            else:
                return state

        state = ConversationState()
        self._save(state)
        return state

    def update(self, state: ConversationState,
               user_input: str, assistant_response: str):
        """更新对话状态"""
        state.history.append({
            "user": user_input,
            "assistant": assistant_response,
            "timestamp": time.time()
        })

        # 限制历史长度
        if len(state.history) > self.max_history:
            state.history = state.history[-self.max_history:]

        state.last_active = time.time()
        self._save(state)

    def _exists(self, conversation_id: str) -> bool:
        if self.storage == "redis":
            return self.redis.exists(f"conv:{conversation_id}")
        return conversation_id in self.conversations

    def _load(self, conversation_id: str) -> ConversationState:
        if self.storage == "redis":
            data = self.redis.get(f"conv:{conversation_id}")
            if data:
                return ConversationState(**json.loads(data))
        return self.conversations.get(conversation_id)

    def _save(self, state: ConversationState):
        if self.storage == "redis":
            self.redis.setex(
                f"conv:{state.conversation_id}",
                self.timeout,
                json.dumps(asdict(state), default=str)
            )
        else:
            self.conversations[state.conversation_id] = state

    def clear(self, conversation_id: str):
        """清除指定对话"""
        if self.storage == "redis":
            self.redis.delete(f"conv:{conversation_id}")
        else:
            self.conversations.pop(conversation_id, None)
