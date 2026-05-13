<template>
  <div class="dashboard">
    <el-page-header title="监控面板">
      <template #extra>
        <el-button type="danger" @click="stopMonitoring" v-if="isRunning">停止监控</el-button>
        <el-button type="primary" @click="startMonitoring" v-else>启动监控</el-button>
        <el-button @click="goToDebug">调试测试</el-button>
        <el-button @click="goToSettings">设置</el-button>
      </template>
    </el-page-header>
    
    <el-alert
      v-if="backendOffline"
      title="后端服务已离线"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
    />
    
    <div class="dashboard-content">
      <el-row :gutter="20">
        <el-col :span="16">
          <el-card class="status-card">
            <template #header>
              <span>系统状态</span>
            </template>
            
            <div class="status-grid">
              <div class="status-item">
                <div class="status-label">监控状态</div>
                <div class="status-value">
                  <el-tag :type="isRunning ? 'success' : 'info'">
                    {{ isRunning ? '运行中' : '已停止' }}
                  </el-tag>
                </div>
              </div>
              <div class="status-item">
                <div class="status-label">Redis连接</div>
                <div class="status-value">
                  <el-tag :type="redisStatus ? 'success' : 'danger'">
                    {{ redisStatus ? '正常' : '断开' }}
                  </el-tag>
                </div>
              </div>
              <div class="status-item">
                <div class="status-label">RabbitMQ连接</div>
                <div class="status-value">
                  <el-tag :type="rabbitmqStatus ? 'success' : 'danger'">
                    {{ rabbitmqStatus ? '正常' : '断开' }}
                  </el-tag>
                </div>
              </div>
              <div class="status-item">
                <div class="status-label">跟踪人员</div>
                <div class="status-value">{{ trackedPersons }}</div>
              </div>
            </div>
          </el-card>
        </el-col>
        
        <el-col :span="8">
          <ViolationList />
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
import ViolationList from '../components/ViolationList.vue'

const router = useRouter()
const isRunning = ref(false)
const redisStatus = ref(false)
const rabbitmqStatus = ref(false)
const trackedPersons = ref(0)
const backendOffline = ref(false)
let statusInterval = null
const NORMAL_INTERVAL = 2000
const OFFLINE_INTERVAL = 10000

onMounted(() => {
  checkStatus()
  startPolling(NORMAL_INTERVAL)
})

onUnmounted(() => {
  stopPolling()
})

const startPolling = (interval) => {
  stopPolling()
  statusInterval = setInterval(checkStatus, interval)
}

const stopPolling = () => {
  if (statusInterval) {
    clearInterval(statusInterval)
    statusInterval = null
  }
}

const checkStatus = async () => {
  try {
    // 获取监控状态
    const response = await api.getStatus()
    const status = response.data
    isRunning.value = Object.values(status.streams).some(s => s.running)
    redisStatus.value = status.redis.connected
    trackedPersons.value = status.redis.persons_tracked
    
    // 获取服务状态
    const servicesResponse = await api.getServicesStatus()
    const servicesStatus = servicesResponse.data
    redisStatus.value = servicesStatus.redis?.connected || false
    rabbitmqStatus.value = servicesStatus.rabbitmq?.connected || false
    
    // 后端恢复在线，切回高频轮询
    if (backendOffline.value) {
      backendOffline.value = false
      startPolling(NORMAL_INTERVAL)
    }
  } catch (error) {
    // 后端离线时，切到低频轮询，避免刷屏
    if (error.isBackendOffline && !backendOffline.value) {
      backendOffline.value = true
      startPolling(OFFLINE_INTERVAL)
    }
  }
}

const startMonitoring = async () => {
  try {
    await api.startMonitoring()
    ElMessage.success('监控已启动')
    isRunning.value = true
  } catch (error) {
    ElMessage.error('启动失败: ' + error.message)
  }
}

const stopMonitoring = async () => {
  try {
    await api.stopMonitoring()
    ElMessage.success('监控已停止')
    isRunning.value = false
  } catch (error) {
    ElMessage.error('停止失败: ' + error.message)
  }
}

const goToSettings = () => {
  router.push('/settings')
}

const goToDebug = () => {
  router.push('/debug')
}
</script>

<style scoped>
.dashboard {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.status-item {
  text-align: center;
  padding: 15px;
  background: #f5f7fa;
  border-radius: 8px;
}

.status-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.status-value {
  font-size: 18px;
  font-weight: bold;
}
</style>
