// pages/index/index.js - 智能问答（文本 RAG 对话）
const { request } = require('../../utils/request');
const app = getApp();

const SUGGESTIONS = [
  '荔枝霜疫霉病怎么防治？',
  '荔枝蝽（臭屁虫）如何防治？',
  '当前物候期需要注意什么？',
  '果实膨大期如何施肥？',
];

// 物候期对象 → 可读文本
function formatPhenology(p) {
  if (!p) return '';
  if (typeof p === 'string') return p;
  return p.stage || p.name || JSON.stringify(p);
}

Page({
  data: {
    inputValue: '',
    messages: [],
    loading: false,
    suggestions: SUGGESTIONS,
    showSuggestions: true,
    scrollTop: 0,
  },

  onLoad() {
    this.setData({
      messages: [
        {
          role: 'assistant',
          content:
            '您好，我是荔知君 🍒 荔枝种植智能助手。\n\n您可以问我病虫害防治、肥水管理、物候期农事等问题，我会结合知识库为您解答。',
          sources: [],
        },
      ],
    });
  },

  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  // 发送（text 为建议问题或用户直接输入）
  send(text) {
    const query = (text || this.data.inputValue || '').trim();
    if (!query || this.data.loading) return;

    const messages = this.data.messages.concat([
      { role: 'user', content: query },
      { role: 'assistant', content: '', loading: true, sources: [] },
    ]);
    this.setData({
      messages,
      inputValue: '',
      loading: true,
      showSuggestions: false,
    });
    this.scrollToBottom();

    request({
      url: '/api/query',
      method: 'POST',
      data: {
        query,
        conversation_id: app.globalData.conversationId,
        use_query_expansion: true,
      },
    })
      .then((res) => {
        const msgs = this.data.messages;
        const idx = msgs.length - 1;
        msgs[idx] = {
          role: 'assistant',
          content: res.answer,
          sources: res.sources || [],
          intent: res.intent,
          confidence: res.confidence,
          confidenceText:
            res.confidence != null
              ? (res.confidence * 100).toFixed(0) + '%'
              : '',
          phenologyText: formatPhenology(res.phenology),
          latency: res.latency,
          loading: false,
        };
        this.setData({ messages: msgs, loading: false });
        this.scrollToBottom();
      })
      .catch((err) => {
        const msgs = this.data.messages;
        const idx = msgs.length - 1;
        msgs[idx] = {
          role: 'assistant',
          content: '抱歉，回答出错了：' + (err.message || '未知错误'),
          loading: false,
          error: true,
        };
        this.setData({ messages: msgs, loading: false });
        this.scrollToBottom();
      });
  },

  onSendTap() {
    this.send();
  },

  onSuggestionTap(e) {
    this.send(e.currentTarget.dataset.text);
  },

  // 通过不断增大 scrollTop 触发滚动到底部
  scrollToBottom() {
    this.setData({ scrollTop: this.data.scrollTop + 100000 });
  },
});
