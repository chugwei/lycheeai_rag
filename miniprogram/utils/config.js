// utils/config.js
// 后端 API 基础地址配置
// ⚠️ 必须是「已备案的 HTTPS 公网域名」，并在微信公众平台后台配置为 request/uploadFile 合法域名。
// TODO: 将下面的占位域名替换为你部署好的 LycheeAI 后端地址（例如 https://lychee.example.com）
const BASE_URL = 'https://YOUR_BACKEND_DOMAIN';

// 图像识别 API 类型列表 —— 与后端 external_apis/api_client.py 中 LycheeAPIClient 保持一致
const IMAGE_API_TYPES = [
  { key: 'guoshi', name: '果实成熟度' },
  { key: 'cixionghua', name: '雌雄花比例' },
  { key: 'huasui', name: '花穗数量' },
  { key: 'shaoliang', name: '梢量' },
  { key: 'kaihualv', name: '开花率' },
  { key: 'zuoguolv', name: '坐果率' },
  { key: 'baidian', name: '白点检测' },
  { key: 'shao', name: '新梢长度' },
  { key: 'dizhuchong', name: '蒂蛀虫化蛹率' },
];

module.exports = {
  BASE_URL,
  IMAGE_API_TYPES,
};
