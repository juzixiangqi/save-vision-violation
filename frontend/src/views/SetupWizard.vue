<template>
  <div class="setup-wizard">
    <el-page-header title="仓库违规检测系统 - 初始化配置" />
    
    <div class="wizard-content">
      <el-steps :active="activeStep" finish-status="success" simple>
        <el-step title="摄像头配置" />
        <el-step title="区域绘制" />
        <el-step title="违规规则" />
        <el-step title="参数调优" />
        <el-step title="确认启动" />
      </el-steps>
      
      <div class="step-content">
        <div v-if="activeStep === 0">
          <h3>步骤 1: 配置摄像头</h3>
          <CameraConfig v-model="cameras" />
        </div>
        
        <div v-if="activeStep === 1">
          <h3>步骤 2: 绘制监控区域</h3>
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
          
          <ZoneEditor v-model="zones" :background-image="cameraFrame" />
        </div>
        
        <div v-if="activeStep === 2">
          <h3>步骤 3: 配置违规规则</h3>
          <RuleConfig v-model="rules" :zones="zones" />
        </div>
        
        <div v-if="activeStep === 3">
          <h3>步骤 4: 检测参数调优</h3>
          <ParamSettings v-model="detectionParams" />
        </div>
        
        <div v-if="activeStep === 4">
          <h3>步骤 5: 确认配置</h3>
          <el-card class="summary-card">
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
            <el-button type="success" size="large" @click="startMonitoring" :loading="starting">
              启动监控
            </el-button>
          </div>
        </div>
      </div>
      
      <div class="step-actions">
        <el-button v-if="activeStep > 0" @click="prevStep">上一步</el-button>
        <el-button v-if="activeStep < 4" type="primary" @click="nextStep" :disabled="!canProceed">
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
const loadingFrame = ref(false)

const cameras = ref([])
const zones = ref([])
const rules = ref([])
const detectionParams = ref({})

onMounted(async () => {
  await configStore.loadConfig()
  cameras.value = [...configStore.cameras]
  zones.value = [...configStore.zones]
  rules.value = [...configStore.rules]
  detectionParams.value = configStore.detectionParams || {}
})

const canProceed = computed(() => {
  switch (activeStep.value) {
    case 0: return cameras.value.length > 0
    case 1: return zones.value.length >= 2
    case 2: return rules.value.length > 0
    default: return true
  }
})

const nextStep = async () => {
  await saveCurrentStep()
  if (activeStep.value < 4) {
    activeStep.value++
    // 进入区域绘制步骤时，默认选择第一个摄像头
    if (activeStep.value === 1 && cameras.value.length > 0 && !selectedCameraId.value) {
      selectedCameraId.value = cameras.value[0].id
      await loadCameraFrame()
    }
  }
}

const prevStep = () => {
  if (activeStep.value > 0) activeStep.value--
}

const saveCurrentStep = async () => {
  try {
    switch (activeStep.value) {
      case 0: await configStore.saveCameras(cameras.value); break
      case 1: await configStore.saveZones(zones.value); break
      case 2: await configStore.saveRules(rules.value); break
      case 3: await configStore.saveDetectionParams(detectionParams.value); break
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
    ElMessage.success('画面加载成功')
  } catch (error) {
    ElMessage.error('加载画面失败: ' + (error.response?.data?.detail || error.message))
    cameraFrame.value = ''
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
</style>
