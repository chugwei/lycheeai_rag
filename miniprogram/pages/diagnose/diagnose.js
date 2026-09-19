// pages/diagnose/diagnose.js - 果园识病（图文问答）
const { BASE_URL, IMAGE_API_TYPES } = require('../../utils/config');
const app = getApp();

// 默认选中「果实成熟度」（index 在 IMAGE_API_TYPES 中）
const DEFAULT_INDEX = IMAGE_API_TYPES.findIndex((t) => t.key === 'guoshi');

function formatPhenology(p) {
  if (!p) return '';
  if (typeof p === 'string') return p;
  return p.stage || p.name || JSON.stringify(p);
}

// 把后端 image_analysis 整理为可读文本
function formatImageAnalysis(analysis) {
  if (!analysis) return '';
  if (analysis.llm_analysis) return analysis.llm_analysis;
  const detail = analysis.detection_results || analysis.results;
  if (detail) {
    try {
      return JSON.stringify(detail, null, 2);
    } catch (e) {
      return String(detail);
    }
  }
  return JSON.stringify(analysis, null, 2);
}

Page({
  data: {
    apiTypes: IMAGE_API_TYPES,
    apiIndex: DEFAULT_INDEX < 0 ? 0 : DEFAULT_INDEX,
    apiType: IMAGE_API_TYPES[DEFAULT_INDEX < 0 ? 0 : DEFAULT_INDEX].key,
    apiTypeName: IMAGE_API_TYPES[DEFAULT_INDEX < 0 ? 0 : DEFAULT_INDEX].name,
    imagePath: '',
    question: '',
    result: null,
    loading: false,
  },

  onApiChange(e) {
    const idx = Number(e.detail.value);
    this.setData({
      apiIndex: idx,
      apiType: this.data.apiTypes[idx].key,
      apiTypeName: this.data.apiTypes[idx].name,
    });
  },

  chooseImage() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const path = res.tempFiles[0].tempFilePath;
        this.setData({ imagePath: path, result: null });
      },
    });
  },

  previewImage() {
    if (this.data.imagePath) {
      wx.previewImage({ urls: [this.data.imagePath] });
    }
  },

  removeImage() {
    this.setData({ imagePath: '', result: null });
  },

  onQuestionInput(e) {
    this.setData({ question: e.detail.value });
  },

  submit() {
    if (!this.data.imagePath) {
      wx.showToast({ title: '请先选择图片', icon: 'none' });
      return;
    }
    if (this.data.loading) return;
    this.setData({ loading: true, result: null });

    const that = this;
    wx.uploadFile({
      url: BASE_URL + '/api/query/image',
      filePath: this.data.imagePath,
      name: 'image',
      formData: {
        query:
          this.data.question ||
          '请根据这张图片分析荔枝生长状况，并给出田间管理建议',
        image_api_type: this.data.apiType,
        conversation_id: app.globalData.conversationId,
      },
      timeout: 60000,
      success(res) {
        try {
          const data = JSON.parse(res.data);
          if (res.statusCode >= 200 && res.statusCode < 300) {
            that.setData({
              result: {
                answer: data.answer,
                imageAnalysis: formatImageAnalysis(data.image_analysis),
                sources: data.sources || [],
                intent: data.intent,
                confidenceText:
                  data.confidence != null
                    ? (data.confidence * 100).toFixed(0) + '%'
                    : '',
                phenologyText: formatPhenology(data.phenology),
              },
              loading: false,
            });
          } else {
            throw new Error(data.detail || data.message || '识别失败');
          }
        } catch (err) {
          wx.showToast({ title: '解析失败：' + err.message, icon: 'none' });
          that.setData({ loading: false });
        }
      },
      fail() {
        wx.showToast({ title: '上传失败，请检查网络或域名配置', icon: 'none' });
        that.setData({ loading: false });
      },
    });
  },
});
