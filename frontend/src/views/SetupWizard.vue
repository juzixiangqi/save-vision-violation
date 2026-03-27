<template>
  <div class="setup-wizard">
    <el-page-header title="仓库违规检测系统 - 初始化配置" />
    
    <div class="wizard-content">
      <el-steps :active="activeStep" finish-status="success" simple>
        <el-step title="服务配置" />
        <el-step title="摄像头配置" />
        <el-step title="区域绘制" />
        <el-step title="违规规则" />
        <el-step title="参数调优" />
        <el-step title="确认启动" />
      </el-steps>
      
      <div class="step-content">
        <!-- 步骤 0: 服务配置 -->
        <div v-if="activeStep === 0">
          <h3>步骤 1: 配置基础服务</h3>
          <el-card class="service-config-card">
            <template #header>
              <div class="card-header">
                <span>Redis 配置</span>
                <el-tag :type="serviceStatus.redis?.connected ? 'success' : 'danger'" size="small">
                  {{ serviceStatus.redis?.connected ? '已连接' : '未连接' }}
                </el-tag>
              </div>
            </template>
            <el-form :model="servicesConfig.redis" label-width="100px">
              <el-form-item label="主机地址">
                <el-input v-model="servicesConfig.redis.host" placeholder="localhost" />
              </el-form-item>
              <el-form-item label="端口">
                <el-input-number v-model="servicesConfig.redis.port" :min="1" :max="65535" />
              </el-form-item>
              <el-form-item label="数据库">
                <el-input-number v-model="servicesConfig.redis.db" :min="0" :max="15" />
              </el-form-item>
              <el-form-item label="密码">
                <el-input v-model="servicesConfig.redis.password" type="password" placeholder="无密码则留空" show-password />
              </el-form-item>
            </el-form>
          </el-card>

          <el-card class="service-config-card" style="margin-top: 20px;">
            <template #header>
              <div class="card-header">
                <span>RabbitMQ 配置</span>
                <el-tag :type="serviceStatus.rabbitmq?.connected ? 'success' : 'danger'" size="small">
                  {{ serviceStatus.rabbitmq?.connected ? '已连接' : '未连接' }}
                </el-tag>
              </div>
            </template>
            <el-form :model="servicesConfig.rabbitmq" label-width="100px">
              <el-form-item label="主机地址">
                <el-input v-model="servicesConfig.rabbitmq.host" placeholder="localhost" />
              </el-form-item>
              <el-form-item label="端口">
                <el-input-number v-model="servicesConfig.rabbitmq.port" :min="1" :max="65535" />
              </el-form-item>
              <el-form-item label="用户名">
                <el-input v-model="servicesConfig.rabbitmq.username" placeholder="guest" />
              </el-form-item>
              <el-form-item label="密码">
                <el-input v-model="servicesConfig.rabbitmq.password" type="password" placeholder="guest" show-password />
              </el-form-item>
              <el-form-item label="队列名">
                <el-input v-model="servicesConfig.rabbitmq.queue" placeholder="violations" />
              </el-form-item>
            </el-form>
          </el-card>

          <div class="service-test-actions">
            <el-button type="primary" @click="testServices" :loading="testingServices">
              测试连接
            </el-button>
            <el-button @click="loadServicesConfig">重置配置</el-button>
          </div>
        </div>

        <div v-if="activeStep === 1">
          <h3>步骤 2: 配置摄像头</h3>
          <CameraConfig v-model="cameras" />
        </div>
        
        <div v-if="activeStep === 2">
          <h3>步骤 3: 绘制监控区域</h3>
          <div v-if="cameras.length > 0" class="camera-selector">
            <el-select v-model="selectedCameraId" placeholder="选择摄像头" @change="loadCameraFrame">
              <el-option
                v-for="cam in cameras"
                :key="cam.id"
                :label="cam.name"
                :value="cam.id"
              />
            </el-select>
            
            <el-button type="primary" @click="loadCameraFrame" :loading="loadingFrame">
              刷新画面
            </el-button>
          </div>
          
          <ZoneEditor v-model="zones" :background-image="cameraFrame" :reference-width="cameraFrameWidth" :reference-height="cameraFrameHeight" />
        </div>
        
        <div v-if="activeStep === 3">
          <h3>步骤 4: 配置违规规则</h3>
          <RuleConfig v-model="rules" :zones="zones" />
        </div>
        
        <div v-if="activeStep === 4">
          <h3>步骤 5: 检测参数调优</h3>
          <ParamSettings v-model="detectionParams" />
        </div>
        
        <div v-if="activeStep === 5">
          <h3>步骤 6: 确认配置</h3>
          
          <!-- 服务状态检查 -->
          <el-card class="summary-card">
            <template #header>
              <span>服务连接状态</span>
              <el-tag :type="allServicesConnected ? 'success' : 'warning'" style="margin-left: 10px;">
                {{ allServicesConnected ? '全部正常' : '有服务未连接' }}
              </el-tag>
            </template>
            <div class="service-status-summary">
              <div class="status-item">
                <span>Redis:</span>
                <el-tag :type="serviceStatus.redis?.connected ? 'success' : 'danger'" size="small">
                  {{ serviceStatus.redis?.connected ? '已连接' : '未连接' }}
                </el-tag>
                <span v-if="serviceStatus.redis?.error" class="error-text">{{ serviceStatus.redis.error }}</span>
              </div>
              <div class="status-item">
                <span>RabbitMQ:</span>
                <el-tag :type="serviceStatus.rabbitmq?.connected ? 'success' : 'danger'" size="small">
                  {{ serviceStatus.rabbitmq?.connected ? '已连接' : '未连接' }}
                </el-tag>
                <span v-if="serviceStatus.rabbitmq?.error" class="error-text">{{ serviceStatus.rabbitmq.error }}</span>
              </div>
            </div>
          </el-card>
          
          <el-card class="summary-card" style="margin-top: 15px;">
            <template #header>
              <span>配置摘要</span>
            </template>
            
            <div class="summary-section">
              <h4>摄像头 ({{ cameras.length }})</h4>
              <el-tag v-for="cam in cameras" :key="cam.id" class="summary-tag">
                {{ cam.name }}
              </el-tag>
            </div>
            
            <div class="summary-section">
              <h4>区域 ({{ zones.length }})</h4>
              <el-tag v-for="zone in zones" :key="zone.id" 
                     class="summary-tag" :style="{ backgroundColor: zone.color }">
                {{ zone.name }}
              </el-tag>
            </div>
            
            <div class="summary-section">
              <h4>违规规则 ({{ rules.length }})</h4>
              <div v-for="rule in rules" :key="rule.id" class="rule-item">
                {{ rule.name }}: {{ getZoneName(rule.from_zone) }} → {{ getZoneName(rule.to_zone) }}
              </div>
            </div>
          </el-card>
          
          <div class="action-buttons">
            <el-button type="success" size="large" @click="startMonitoring" :loading="starting" :disabled="!allServicesConnected">
              启动监控
            </el-button>
          </div>
        </div>
      </div>
      
      <div class="step-actions">
        <el-button v-if="activeStep > 0" @click="prevStep">上一步</el-button>
        <el-button v-if="activeStep < 5" type="primary" @click="nextStep" :disabled="!canProceed">
          下一步
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useConfigStore } from '../stores/config'
import api from '../api'
import CameraConfig from '../components/CameraConfig.vue'
import ZoneEditor from '../components/ZoneEditor.vue'
import RuleConfig from '../components/RuleConfig.vue'
import ParamSettings from '../components/ParamSettings.vue'

const router = useRouter()
const configStore = useConfigStore()

const activeStep = ref(0)
const starting = ref(false)
const selectedCameraId = ref('')
const cameraFrame = ref('')
const cameraFrameWidth = ref(1920)
const cameraFrameHeight = ref(1080)
const loadingFrame = ref(false)

const cameras = ref([])
const zones = ref([])
const rules = ref([])
const detectionParams = ref({})

// 服务配置
const servicesConfig = ref({
  redis: {
    host: 'localhost',
    port: 6379,
    db: 0,
    password: ''
  },
  rabbitmq: {
    host: 'localhost',
    port: 5672,
    username: 'guest',
    password: 'guest',
    queue: 'violations'
  }
})

// 服务状态
const serviceStatus = ref({
  redis: { connected: false, error: null },
  rabbitmq: { connected: false, error: null }
})

const testingServices = ref(false)

onMounted(async () => {
  await configStore.loadConfig()
  cameras.value = [...configStore.cameras]
  zones.value = [...configStore.zones]
  rules.value = [...configStore.rules]
  detectionParams.value = configStore.detectionParams || {}
  
  // 加载服务配置
  await loadServicesConfig()
  
  // 检查服务状态
  await checkServicesStatus()
})

const canProceed = computed(() => {
  switch (activeStep.value) {
    case 0: return true // 服务配置步骤，总是可以继续
    case 1: return cameras.value.length > 0
    case 2: return zones.value.length >= 2
    case 3: return rules.value.length > 0
    default: return true
  }
})

const allServicesConnected = computed(() => {
  return serviceStatus.value.redis?.connected && serviceStatus.value.rabbitmq?.connected
})

// 加载服务配置
const loadServicesConfig = async () => {
  try {
    const response = await api.getServicesConfig()
    if (response.data.redis) {
      servicesConfig.value.redis = { ...servicesConfig.value.redis, ...response.data.redis }
    }
    if (response.data.rabbitmq) {
      servicesConfig.value.rabbitmq = { ...servicesConfig.value.rabbitmq, ...response.data.rabbitmq }
    }
  } catch (error) {
    console.error('加载服务配置失败:', error)
  }
}

// 测试服务连接
const testServices = async () => {
  testingServices.value = true
  try {
    // 先保存配置
    await api.updateServicesConfig({
      redis: servicesConfig.value.redis,
      rabbitmq: servicesConfig.value.rabbitmq
    })
    
    // 然后测试连接
    const response = await api.getServicesStatus()
    serviceStatus.value = response.data
    
    if (response.data.all_connected) {
      ElMessage.success('所有服务连接正常')
    } else {
      ElMessage.warning('部分服务连接失败，请检查配置')
    }
  } catch (error) {
    ElMessage.error('测试连接失败: ' + error.message)
  } finally {
    testingServices.value = false
  }
}

// 检查服务状态
const checkServicesStatus = async () => {
  try {
    const response = await api.getServicesStatus()
    serviceStatus.value = response.data
  } catch (error) {
    console.error('检查服务状态失败:', error)
  }
}

const nextStep = async () => {
  await saveCurrentStep()
  if (activeStep.value < 5) {
    activeStep.value++
    // 进入区域绘制步骤时，默认选择第一个摄像头
    if (activeStep.value === 2 && cameras.value.length > 0 && !selectedCameraId.value) {
      selectedCameraId.value = cameras.value[0].id
      await loadCameraFrame()
    }
    // 进入确认步骤时，检查服务状态
    if (activeStep.value === 5) {
      await checkServicesStatus()
    }
  }
}

const prevStep = () => {
  if (activeStep.value > 0) activeStep.value--
}

const saveCurrentStep = async () => {
  try {
    switch (activeStep.value) {
      case 0: // 服务配置步骤
        await api.updateServicesConfig({
          redis: servicesConfig.value.redis,
          rabbitmq: servicesConfig.value.rabbitmq
        })
        break
      case 1: await configStore.saveCameras(cameras.value); break
      case 2: await configStore.saveZones(zones.value); break
      case 3: await configStore.saveRules(rules.value); break
      case 4: await configStore.saveDetectionParams(detectionParams.value); break
    }
  } catch (error) {
    ElMessage.error('保存失败: ' + error.message)
  }
}

const startMonitoring = async () => {
  starting.value = true
  try {
    await api.startMonitoring()
    ElMessage.success('监控已启动')
    router.push('/dashboard')
  } catch (error) {
    ElMessage.error('启动失败: ' + error.message)
  } finally {
    starting.value = false
  }
}

const getZoneName = (zoneId) => {
  const zone = zones.value.find(z => z.id === zoneId)
  return zone ? zone.name : zoneId
}

const loadCameraFrame = async () => {
  if (!selectedCameraId.value) {
    ElMessage.warning('请先选择一个摄像头')
    return
  }

  loadingFrame.value = true
  try {
    const response = await api.getCameraFrame(selectedCameraId.value)
    cameraFrame.value = response.data.image
    
    // 获取图片尺寸
    if (response.data.width && response.data.height) {
      cameraFrameWidth.value = response.data.width
      cameraFrameHeight.value = response.data.height
    } else {
      // 如果没有返回尺寸，使用Image对象解析
      const img = new Image()
      img.onload = () => {
        cameraFrameWidth.value = img.width
        cameraFrameHeight.value = img.height
      }
      img.src = response.data.image
    }
    
    ElMessage.success('画面加载成功')
  } catch (error) {
    ElMessage.error('加载画面失败: ' + (error.response?.data?.detail || error.message))
    cameraFrame.value = ''
    cameraFrameWidth.value = 1920
    cameraFrameHeight.value = 1080
  } finally {
    loadingFrame.value = false
  }
}
</script>

<style scoped>
.setup-wizard {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.step-content {
  margin: 30px 0;
  min-height: 400px;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-top: 30px;
}

.summary-card {
  margin: 20px 0;
}

.summary-section {
  margin-bottom: 20px;
}

.summary-tag {
  margin-right: 10px;
  margin-bottom: 5px;
}

.action-buttons {
  text-align: center;
  margin-top: 30px;
}

.camera-selector {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
  align-items: center;
}

.camera-selector .el-select {
  width: 300px;
}

.service-config-card {
  max-width: 600px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.service-test-actions {
  margin-top: 20px;
  display: flex;
  gap: 10px;
}

.service-status-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.error-text {
  color: #f56c6c;
  font-size: 12px;
}
</style>
