import { createRouter, createWebHistory } from 'vue-router'
import Layout from '@/views/Layout.vue'
import Chat from '@/views/Chat.vue'
import Detect from '@/views/Detect.vue'
import Predict from '@/views/Predict.vue'
import Knowledge from '@/views/Knowledge.vue'

const routes = [
  {
    path: '/',
    component: Layout,
    redirect: '/chat',
    children: [
      { path: 'chat', name: 'Chat', component: Chat },
      { path: 'detect', name: 'Detect', component: Detect },
      { path: 'predict', name: 'Predict', component: Predict },
      { path: 'knowledge', name: 'Knowledge', component: Knowledge },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/chat',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
