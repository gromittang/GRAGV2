import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/chat',
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/ChatPage.vue'),
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('../views/KnowledgePage.vue'),
  },
  {
    path: '/knowledge/:kbId',
    name: 'KnowledgeDetail',
    component: () => import('../views/KnowledgePage.vue'),
  },
  {
    path: '/query',
    name: 'Query',
    component: () => import('../views/QueryPage.vue'),
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsPage.vue'),
  },
  {
    path: '/pm-studio',
    name: 'PMStudio',
    component: () => import('../views/PMStudioPage.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
