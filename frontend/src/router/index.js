import { createRouter, createWebHistory } from 'vue-router'
import SetupWizard from '../views/SetupWizard.vue'
import Dashboard from '../views/Dashboard.vue'
import Settings from '../views/Settings.vue'
import DebugTest from '../views/DebugTest.vue'

const routes = [
  {
    path: '/',
    name: 'Setup',
    component: SetupWizard
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: Dashboard
  },
  {
    path: '/settings',
    name: 'Settings',
    component: Settings
  },
  {
    path: '/debug',
    name: 'Debug',
    component: DebugTest
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
