// utils/request.js - 统一网络请求封装（Promise 化，自动携带登录令牌）
const { BASE_URL } = require('./config');

const TOKEN_KEY = 'lychee_token';

/**
 * 统一的 wx.request 封装
 * @param {Object} options { url, method, data, header }
 * @param {Boolean} _retried 内部用于防止 401 无限重试
 * @returns {Promise<any>} 解析为响应体 data
 */
function request(options, _retried) {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync(TOKEN_KEY) || '';
    const header = Object.assign(
      { 'Content-Type': 'application/json' },
      token ? { Authorization: 'Bearer ' + token } : {},
      options.header || {}
    );

    wx.request({
      url: BASE_URL + options.url,
      method: options.method || 'GET',
      data: options.data || {},
      header,
      timeout: 60000,
      success(res) {
        // 令牌失效：重新登录后重试一次
        if (res.statusCode === 401 && !_retried) {
          const auth = require('./auth');
          auth
            .login()
            .then(() => request(options, true).then(resolve).catch(reject))
            .catch(reject);
          return;
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          const msg =
            (res.data && (res.data.detail || res.data.message)) || '请求失败';
          reject({ statusCode: res.statusCode, message: msg });
        }
      },
      fail(err) {
        reject({
          statusCode: -1,
          message: '网络错误，请检查网络或后端域名配置',
          detail: err,
        });
      },
    });
  });
}

module.exports = {
  request,
  BASE_URL,
  TOKEN_KEY,
};
