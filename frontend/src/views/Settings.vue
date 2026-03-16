<template>
  <div class="settings">
    <el-page-header @back="goBack" title="系统设置" />
    
    <div class="settings-content">
      <el-tabs type="border-card">
        <el-tab-pane label="摄像头">
          <CameraConfig v-model="cameras" />
        </el-tab-pane>
        
        <el-tab-pane label="区域">
          <ZoneEditor v-model="zones" />
        </el-tab-pane>
        
        <el-tab-pane label="规则">
          <RuleConfig v-model="rules" :zones="zones" />
        </el-tab-pane>
        
        <el-tab-pane label="参数">
          <ParamSettings v-model="detectionParams" />
        </el-tab-pane>
      </el-tabs>
      
      <div class="actions">
        <el-button type="primary" @click="saveAll">保存所有配置</el-button>
        <el-button @click="resetConfig">重置</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useConfigStore } from '../stores/config'
import CameraConfig from '../components/CameraConfig.vue'
import ZoneEditor from '../components/ZoneEditor.vue'
import RuleConfig from '../components/RuleConfig.vue'
import ParamSettings from '../components/ParamSettings.vue'

const router = useRouter()
const configStore = useConfigStore()

const cameras = ref([])
const zones = ref([])
const rules = ref([])
const detectionParams = ref({})

onMounted(async () => {
  await configStore.loadConfig()
  cameras.value = [...configStore.cameras]
  zones.value = [...configStore.zones]
  rules.value = [...configStore.rules]
  detectionParams.value = { ...configStore.detectionParams }
})

const saveAll = async () => {
  try {
    await configStore.saveCameras(cameras.value)
    await configStore.saveZones(zones.value)
    await configStore.saveRules(rules.value)
    await configStore.saveDetectionParams(detectionParams.value)
    ElMessage.success('配置已保存')
  } catch (error) {
    ElMessage.error('保存失败: ' + error.message)
  }
}

const resetConfig = () => {
  cameras.value = [...configStore.cameras]
  zones.value = [...configStore.zones]
  rules.value = [...configStore.rules]
  detectionParams.value = { ...configStore.detectionParams }
  ElMessage.info('已重置为上次保存的配置')
}

const goBack = () => {
  router.push('/dashboard')
}
</script>

<style scoped>
.settings {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.settings-content {
  margin-top: 20px;
}

.actions {
  margin-top: 20px;
  text-align: center;
}
</style>
