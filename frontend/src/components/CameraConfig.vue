<template>
  <div class="camera-config">
    <el-form :model="form" label-width="120px">
      <el-form-item label="摄像头名称">
        <el-input v-model="form.name" placeholder="例如：入口摄像头" />
      </el-form-item>
      
      <el-form-item label="视频源">
        <el-radio-group v-model="sourceType">
          <el-radio label="file">本地文件</el-radio>
          <el-radio label="rtsp">RTSP流</el-radio>
          <el-radio label="hikvision">海康威视</el-radio>
        </el-radio-group>
      </el-form-item>
      
      <el-form-item label="文件路径" v-if="sourceType === 'file'">
        <el-input v-model="form.source" placeholder="例如：./test_video.mp4" />
      </el-form-item>
      
      <el-form-item label="RTSP地址" v-else-if="sourceType === 'rtsp'">
        <el-input v-model="form.source" placeholder="例如：rtsp://192.168.1.100:554/stream" />
      </el-form-item>
      
      <template v-else-if="sourceType === 'hikvision'">
        <el-form-item label="摄像头编码">
          <el-input v-model="form.cameraIndexCode" placeholder="例如：b567c3277cc14d07b3d04fe9e2ed5af1" />
          <span class="field-hint">海康威视监控点 indexCode</span>
        </el-form-item>
        
        <el-form-item label="AppKey">
          <el-input v-model="form.appKey" placeholder="例如：25205625" />
        </el-form-item>
        
        <el-form-item label="AppSecret">
          <el-input v-model="form.appSecret" type="password" placeholder="例如：yvYgVYYfTcpXdSHHnIov" show-password />
        </el-form-item>
        
        <el-form-item label="服务器地址">
          <el-input v-model="form.host" placeholder="例如：https://10.190.11.240" />
        </el-form-item>
        
        <el-form-item label="端口">
          <el-input-number v-model="form.port" :min="1" :max="65535" />
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="testHikvision" :loading="testingHikvision">
            测试获取RTSP
          </el-button>
        </el-form-item>
        
        <el-form-item label="RTSP地址" v-if="form.source">
          <el-input v-model="form.source" readonly />
          <span class="field-hint">获取到的实时RTSP流地址</span>
        </el-form-item>
      </template>
      
      <el-form-item label="帧率">
        <el-input-number v-model="form.fps" :min="1" :max="60" />
      </el-form-item>
      
      <el-form-item>
        <el-button type="primary" @click="addCamera">添加摄像头</el-button>
      </el-form-item>
    </el-form>
    
    <el-divider />
    
    <h4>已配置摄像头</h4>
    <el-table :data="modelValue" style="width: 100%" :key="tableKey">
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="source" label="视频源" show-overflow-tooltip />
      <el-table-column prop="fps" label="帧率" width="80" />
      <el-table-column label="操作" width="120">
        <template #default="{ $index }">
          <el-button type="danger" size="small" @click="removeCamera($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue'])

const sourceType = ref('file')
const tableKey = ref(0)
const testingHikvision = ref(false)

const form = reactive({
  name: '',
  source: '',
  fps: 25,
  enabled: true,
  // 海康威视配置
  cameraIndexCode: '',
  appKey: '',
  appSecret: '',
  host: 'https://10.190.11.240',
  port: 443
})

const addCamera = () => {
  if (!form.name || !form.source) {
    ElMessage.warning('请填写完整信息')
    return
  }
  
  const cameraConfig = {
    id: `cam_${Date.now()}`,
    name: form.name,
    source: form.source,
    fps: form.fps,
    enabled: true,
    source_type: sourceType.value
  }
  
  // 如果是海康威视，保存原始配置以便后续刷新
  if (sourceType.value === 'hikvision') {
    cameraConfig.hikvision_config = {
      cameraIndexCode: form.cameraIndexCode,
      appKey: form.appKey,
      appSecret: form.appSecret,
      host: form.host,
      port: form.port
    }
  }
  
  const newCameras = [...props.modelValue, cameraConfig]
  
  emit('update:modelValue', newCameras)
  tableKey.value++
  
  // 重置表单
  form.name = ''
  form.source = ''
  form.cameraIndexCode = ''
  form.appKey = ''
  form.appSecret = ''
  form.host = 'https://10.190.11.240'
  form.port = 443
  ElMessage.success('摄像头添加成功')
}

const testHikvision = async () => {
  if (!form.cameraIndexCode || !form.appKey || !form.appSecret) {
    ElMessage.warning('请填写摄像头编码、AppKey 和 AppSecret')
    return
  }
  
  testingHikvision.value = true
  try {
    const response = await api.getHikvisionRtsp({
      cameraIndexCode: form.cameraIndexCode,
      appKey: form.appKey,
      appSecret: form.appSecret,
      host: form.host,
      port: form.port
    })
    
    if (response.data.url) {
      form.source = response.data.url
      ElMessage.success('RTSP地址获取成功')
    } else {
      ElMessage.error('获取RTSP地址失败：' + (response.data.msg || '未知错误'))
    }
  } catch (error) {
    ElMessage.error('测试失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    testingHikvision.value = false
  }
}

const removeCamera = (index) => {
  const newCameras = [...props.modelValue]
  newCameras.splice(index, 1)
  emit('update:modelValue', newCameras)
  tableKey.value++
}
</script>

<style scoped>
.camera-config {
  padding: 20px;
}

.field-hint {
  display: block;
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}
</style>
