// app.js - 全局生命周期与共享数据
const auth = require('./utils/auth');

App({
  globalData: {
    // 多轮对话会话 ID：每次小程序启动生成一个，后端据此维护上下文
    conversationId: '',
  },

  onLaunch() {
    this.globalData.conversationId =
      'mp_' + Date.now() + '_' + Math.floor(Math.random() * 1e6);

    // 启动即静默登录，提前拿到用户令牌（失败不影响其它功能）
    auth.login().catch(() => {});
  },

  onShow() {},
  onHide() {},
});
