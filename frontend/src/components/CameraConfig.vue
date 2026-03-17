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
        </el-radio-group>
      </el-form-item>
      
      <el-form-item label="文件路径" v-if="sourceType === 'file'">
        <el-input v-model="form.source" placeholder="例如：./test_video.mp4" />
      </el-form-item>
      
      <el-form-item label="RTSP地址" v-else>
        <el-input v-model="form.source" placeholder="例如：rtsp://192.168.1.100:554/stream" />
      </el-form-item>
      
      <el-form-item label="帧率">
        <el-input-number v-model="form.fps" :min="1" :max="60" />
      </el-form-item>
      
      <el-form-item>
        <el-button type="primary" @click="addCamera">添加摄像头</el-button>
      </el-form-item>
    </el-form>
    
    <el-divider />
    
    <h4>已配置摄像头</h4>
    <el-table :data="cameras" style="width: 100%">
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
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue'])

const cameras = ref([...props.modelValue])
const sourceType = ref('file')

const form = reactive({
  name: '',
  source: '',
  fps: 25,
  enabled: true
})

watch(cameras, (newVal) => {
  emit('update:modelValue', newVal)
}, { deep: true })

// 监听 props.modelValue 变化，同步更新本地状态
watch(() => props.modelValue, (newVal) => {
  cameras.value = [...newVal]
}, { deep: true })

const addCamera = () => {
  if (!form.name || !form.source) {
    ElMessage.warning('请填写完整信息')
    return
  }
  
  cameras.value.push({
    id: `cam_${Date.now()}`,
    name: form.name,
    source: form.source,
    fps: form.fps,
    enabled: true
  })
  
  form.name = ''
  form.source = ''
  ElMessage.success('摄像头添加成功')
}

const removeCamera = (index) => {
  cameras.value.splice(index, 1)
}
</script>

<style scoped>
.camera-config {
  padding: 20px;
}
</style>
