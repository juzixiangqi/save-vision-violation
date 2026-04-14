<template>
  <div class="param-settings">
    <el-tabs type="border-card">
      <el-tab-pane label="人员搬运检测">
        <el-form :model="params.person_carry" label-width="150px">
          <el-form-item label="模型路径">
            <el-input v-model="params.person_carry.model" placeholder="person_carry.pt" @change="emitUpdate">
              <template #append>
                <el-button @click="browseModel">浏览</el-button>
              </template>
            </el-input>
            <span class="hint">自定义YOLO模型文件路径，用于检测搬箱子的人</span>
          </el-form-item>
          
          <el-form-item label="置信度阈值">
            <el-slider v-model="params.person_carry.confidence" :min="0.1" :max="1" :step="0.05" show-input @change="emitUpdate" />
            <span class="hint">检测结果的可信度阈值，低于此值的检测将被忽略</span>
          </el-form-item>
          
          <el-form-item label="IoU阈值">
            <el-slider v-model="params.person_carry.iou_threshold" :min="0.1" :max="1" :step="0.05" show-input @change="emitUpdate" />
            <span class="hint">非极大值抑制的IoU阈值，用于去除重叠检测框</span>
          </el-form-item>
          
          <el-form-item label="类别ID">
            <el-input-number v-model="params.person_carry.class_id" :min="0" :max="100" @change="emitUpdate" />
            <span class="hint">person_carry在模型中的类别ID（通常是0）</span>
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
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue'])

const defaultParams = {
  person_carry: {
    model: 'person_carry.pt',
    confidence: 0.5,
    iou_threshold: 0.45,
    class_id: 0
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

const browseModel = () => {
  // 这里可以添加文件选择对话框
  // 暂时使用简单的提示
  ElMessage.info('文件选择功能需要后端支持文件浏览API')
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
