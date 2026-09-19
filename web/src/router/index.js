import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    redirect: '/chat',
    children: [
      { path: 'chat', name: 'Chat', component: () => import('@/views/Chat.vue') },
      { path: 'detect', name: 'Detect', component: () => import('@/views/Detect.vue') },
      { path: 'predict', name: 'Predict', component: () => import('@/views/Predict.vue') },
      { path: 'knowledge', name: 'Knowledge', component: () => import('@/views/Knowledge.vue') },
    ],
  },
  {
    path: '/404',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/404',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router