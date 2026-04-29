<template>
  <div class="param-settings">
    <el-tabs type="border-card">
      <el-tab-pane label="模型API配置">
        <el-form :model="params.model_api" label-width="150px">
          <el-form-item label="API地址">
            <el-input v-model="params.model_api.url" placeholder="http://localhost:8000/predict" @change="emitUpdate">
            </el-input>
            <span class="hint">远程模型推理服务的URL地址</span>
          </el-form-item>
          
          <el-form-item label="请求超时">
            <el-input-number v-model="params.model_api.timeout" :min="1" :max="120" :step="1" @change="emitUpdate" />
            <span class="hint">API请求超时时间（秒）</span>
          </el-form-item>
          
          <el-form-item label="输入尺寸">
            <el-input-number v-model="params.model_api.imgsz" :min="320" :max="1280" :step="32" @change="emitUpdate" />
            <span class="hint">模型输入图片尺寸（如640、1280）</span>
          </el-form-item>
          
          <el-form-item label="置信度阈值">
            <el-slider v-model="params.model_api.confidence" :min="0.05" :max="1" :step="0.05" show-input @change="emitUpdate" />
            <span class="hint">检测结果的可信度阈值，低于此值的检测将被忽略</span>
          </el-form-item>
        </el-form>
      </el-tab-pane>
      
      <el-tab-pane label="异步检测配置">
        <el-form :model="params.async_detection" label-width="180px">
          <el-form-item label="启用异步检测">
            <el-switch v-model="params.async_detection.enabled" @change="emitUpdate" />
            <span class="hint">是否启用异步检测模式</span>
          </el-form-item>
          
          <el-form-item label="处理间隔">
            <el-input-number v-model="params.async_detection.process_interval" :min="1" :max="30" @change="emitUpdate" />
            <span class="hint">每N帧处理一次（如6表示每6帧调用一次API）</span>
          </el-form-item>
          
          <el-form-item label="API超时">
            <el-slider v-model="params.async_detection.api_timeout" :min="0.05" :max="1" :step="0.05" show-input @change="emitUpdate" />
            <span class="hint">单次API调用的超时时间（秒）</span>
          </el-form-item>
          
          <el-form-item label="最大并发数">
            <el-input-number v-model="params.async_detection.max_pending" :min="1" :max="10" @change="emitUpdate" />
            <span class="hint">最大并发API请求数</span>
          </el-form-item>
        </el-form>
      </el-tab-pane>
      
      <el-tab-pane label="轨迹追踪">
        <el-form :model="params.tracking" label-width="180px">
          <el-form-item label="最大丢失帧数">
            <el-input-number v-model="params.tracking.max_age" :min="10" :max="100" @change="emitUpdate" />
            <span class="hint">对象丢失多少帧后放弃追踪</span>
          </el-form-item>
          
          <el-form-item label="最小确认帧数">
            <el-input-number v-model="params.tracking.min_hits" :min="1" :max="10" @change="emitUpdate" />
            <span class="hint">需要连续检测多少帧才确认新对象</span>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { reactive, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue'])

const defaultParams = {
  model_api: {
    url: 'http://10.190.28.23:31674/predict',
    timeout: 30,
    imgsz: 640,
    confidence: 0.2
  },
  async_detection: {
    enabled: true,
    process_interval: 6,
    api_timeout: 0.25,
    max_pending: 4
  },
  tracking: {
    max_age: 30,
    min_hits: 3
  }
}

const params = reactive({
  ...defaultParams,
  ...props.modelValue
})

// 监听 props.modelValue 变化，同步更新本地状态
watch(() => props.modelValue, (newVal) => {
  Object.assign(params, defaultParams, newVal)
}, { deep: true, immediate: true })

const emitUpdate = () => {
  emit('update:modelValue', { ...params })
}
</script>

<style scoped>
.param-settings {
  padding: 20px;
}

.hint {
  display: block;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
}
</style>
