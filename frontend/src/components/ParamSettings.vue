<template>
  <div class="param-settings">
    <el-tabs type="border-card">
      <el-tab-pane label="YOLO检测">
        <el-form :model="params.yolo" label-width="150px">
          <el-form-item label="置信度阈值">
            <el-slider v-model="params.yolo.confidence" :min="0.1" :max="1" :step="0.05" show-input />
          </el-form-item>
          
          <el-form-item label="IoU阈值">
            <el-slider v-model="params.yolo.iou_threshold" :min="0.1" :max="1" :step="0.05" show-input />
          </el-form-item>
        </el-form>
      </el-tab-pane>
      
      <el-tab-pane label="搬起检测">
        <el-form :model="params.lift_detection" label-width="180px">
          <el-form-item label="双手距离阈值">
            <el-input-number v-model="params.lift_detection.hands_distance_threshold" :min="50" :max="300" />
          </el-form-item>
          
          <el-form-item label="连续帧数">
            <el-input-number v-model="params.lift_detection.consecutive_frames" :min="3" :max="15" />
            <span class="hint">需要连续多少帧满足条件才触发</span>
          </el-form-item>
        </el-form>
      </el-tab-pane>
      
      <el-tab-pane label="放下检测">
        <el-form :model="params.drop_detection" label-width="180px">
          <el-form-item label="手上升阈值">
            <el-input-number v-model="params.drop_detection.hands_rise_threshold" :min="10" :max="100" />
          </el-form-item>
          
          <el-form-item label="遮挡超时">
            <el-input-number v-model="params.drop_detection.occlusion_timeout" :min="3" :max="10" />
            <span class="hint">遮挡超过此时间强制视为放下</span>
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
  yolo: {
    confidence: 0.5,
    iou_threshold: 0.45
  },
  lift_detection: {
    hands_distance_threshold: 150,
    consecutive_frames: 5
  },
  drop_detection: {
    hands_rise_threshold: 30,
    occlusion_timeout: 5
  }
}

const params = reactive({
  ...defaultParams,
  ...props.modelValue
})

watch(params, (newVal) => {
  emit('update:modelValue', { ...newVal })
}, { deep: true })

// 监听 props.modelValue 变化，同步更新本地状态
watch(() => props.modelValue, (newVal) => {
  Object.assign(params, defaultParams, newVal)
}, { deep: true, immediate: true })
</script>

<style scoped>
.param-settings {
  padding: 20px;
}

.hint {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}
</style>
