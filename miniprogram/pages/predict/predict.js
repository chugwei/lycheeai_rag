// pages/predict/predict.js - 风险预警（调用 /api/predict）
const { request } = require('../../utils/request');

// 预测类型与所需参数（与后端 main.py /api/predict 对齐）
const PREDICT_TYPES = [
  { key: 'chunxiang', name: '春象发生期预测', need: 'city', desc: '需城市编码' },
  { key: 'shuangyimeibing', name: '霜疫霉病预测', need: 'city', desc: '需城市编码' },
  { key: 'tanjubing', name: '炭疽病发生期预测', need: '', desc: '无需参数' },
  { key: 'tanjubing_latest', name: '炭疽病最新数据', need: 'location', desc: '需 9 位地区编码' },
  { key: 'tanjubing_history', name: '炭疽病历史数据', need: 'location_date', desc: '需地区编码 + 日期' },
  { key: 'yield', name: '荔枝产量预测', need: '', desc: '无需参数' },
  { key: 'yield_features', name: '产量预测特征', need: '', desc: '无需参数' },
  { key: 'yield_health', name: '预测模型健康度', need: '', desc: '无需参数' },
];

Page({
  data: {
    types: PREDICT_TYPES,
    typeIndex: 0,
    typeKey: PREDICT_TYPES[0].key,
    typeName: PREDICT_TYPES[0].name,
    need: PREDICT_TYPES[0].need,
    cityCode: '',
    locationCode: '',
    dateStr: '',
    result: '',
    loading: false,
  },

  onTypeChange(e) {
    const idx = Number(e.detail.value);
    const t = this.data.types[idx];
    this.setData({
      typeIndex: idx,
      typeKey: t.key,
      typeName: t.name,
      need: t.need,
      result: '',
    });
  },

  onCityInput(e) {
    this.setData({ cityCode: e.detail.value });
  },
  onLocationInput(e) {
    this.setData({ locationCode: e.detail.value });
  },
  onDateInput(e) {
    this.setData({ dateStr: e.detail.value });
  },

  async onSubmit() {
    if (this.data.loading) return;
    const { typeKey, need, cityCode, locationCode, dateStr } = this.data;

    if (need === 'city' && !cityCode.trim()) {
      wx.showToast({ title: '请输入城市编码', icon: 'none' });
      return;
    }
    if ((need === 'location' || need === 'location_date') && !locationCode.trim()) {
      wx.showToast({ title: '请输入地区编码', icon: 'none' });
      return;
    }
    if (need === 'location_date' && !dateStr.trim()) {
      wx.showToast({ title: '请输入日期', icon: 'none' });
      return;
    }

    const body = { api_type: typeKey };
    if (cityCode.trim()) body.city_code = cityCode.trim();
    if (locationCode.trim()) body.location_code = locationCode.trim();
    if (dateStr.trim()) body.datetime_str = dateStr.trim();

    this.setData({ loading: true, result: '' });
    try {
      const res = await request({
        url: '/api/predict',
        method: 'POST',
        data: body,
      });
      this.setData({
        result: JSON.stringify(res, null, 2),
        loading: false,
      });
    } catch (err) {
      wx.showToast({
        title: '预测失败：' + (err.message || '未知错误'),
        icon: 'none',
      });
      this.setData({ loading: false });
    }
  },

  copyResult() {
    if (this.data.result) {
      wx.setClipboardData({ data: this.data.result });
    }
  },
});
