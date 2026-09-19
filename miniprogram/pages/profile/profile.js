// pages/profile/profile.js - 我的 / 微信登录
const auth = require('../../utils/auth');

function maskOpenid(openid) {
  if (!openid) return '';
  if (openid.length <= 7) return openid;
  return openid.slice(0, 3) + '****' + openid.slice(-4);
}

Page({
  data: {
    loggedIn: false,
    openidMasked: '',
    avatarUrl: '',
    nickname: '',
    loginLoading: false,
  },

  onShow() {
    this.refresh();
  },

  refresh() {
    const openid = auth.getOpenid();
    this.setData({
      loggedIn: !!auth.getToken(),
      openidMasked: maskOpenid(openid),
      avatarUrl: wx.getStorageSync('lychee_avatar') || '',
      nickname: wx.getStorageSync('lychee_nickname') || '',
    });
  },

  async onLogin() {
    if (this.data.loginLoading) return;
    this.setData({ loginLoading: true });
    try {
      await auth.login();
      this.refresh();
      wx.showToast({ title: '登录成功', icon: 'success' });
    } catch (err) {
      wx.showToast({
        title: '登录失败：' + (err.message || '未知错误'),
        icon: 'none',
      });
    } finally {
      this.setData({ loginLoading: false });
    }
  },

  onLogout() {
    auth.logout();
    this.refresh();
    wx.showToast({ title: '已退出登录', icon: 'none' });
  },

  // 微信昵称（新版本标准能力，bind:nickname 捕获微信提供的昵称）
  onNickname(e) {
    const name = e.detail.nickname || e.detail.value || '';
    if (name) {
      this.setData({ nickname: name });
      wx.setStorageSync('lychee_nickname', name);
    }
  },

  onNicknameInput(e) {
    const name = e.detail.value;
    this.setData({ nickname: name });
    wx.setStorageSync('lychee_nickname', name);
  },

  onChooseAvatar(e) {
    const url = e.detail.avatarUrl;
    this.setData({ avatarUrl: url });
    wx.setStorageSync('lychee_avatar', url);
  },
});
