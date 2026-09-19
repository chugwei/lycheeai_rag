// utils/auth.js - 微信登录与令牌管理
const { request } = require('./request');

const TOKEN_KEY = 'lychee_token';
const OPENID_KEY = 'lychee_openid';

function getToken() {
  return wx.getStorageSync(TOKEN_KEY) || '';
}

function setToken(token) {
  if (token) {
    wx.setStorageSync(TOKEN_KEY, token);
  } else {
    wx.removeStorageSync(TOKEN_KEY);
  }
}

function getOpenid() {
  return wx.getStorageSync(OPENID_KEY) || '';
}

/**
 * 微信登录：若已有有效令牌直接复用，否则 wx.login 拿 code 换后端令牌
 * @returns {Promise<string>} token
 */
function login() {
  const existing = getToken();
  if (existing) {
    return Promise.resolve(existing);
  }
  return new Promise((resolve, reject) => {
    wx.login({
      success(res) {
        if (!res.code) {
          reject(new Error('获取 login code 失败'));
          return;
        }
        request({
          url: '/api/auth/wechat-login',
          method: 'POST',
          data: { code: res.code },
        })
          .then((data) => {
            setToken(data.token);
            if (data.openid) wx.setStorageSync(OPENID_KEY, data.openid);
            resolve(data.token);
          })
          .catch(reject);
      },
      fail(err) {
        reject(err);
      },
    });
  });
}

function logout() {
  setToken('');
  wx.removeStorageSync(OPENID_KEY);
}

module.exports = {
  getToken,
  getOpenid,
  login,
  logout,
};
