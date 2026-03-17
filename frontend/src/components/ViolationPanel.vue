<template>
  <div class="violation-panel">
    <h3>违规事件</h3>
    
    <div v-if="violations.length === 0" class="no-violations">
      <el-empty description="暂无违规事件" />
    </div>
    
    <div v-else class="violation-list">
      <el-timeline>
        <el-timeline-item
          v-for="(violation, index) in sortedViolations"
          :key="index"
          type="danger"
          :timestamp="formatTime(violation.timestamp)"
          hollow
        >
          <el-card :class="{ 'latest': index === 0 }" shadow="hover">
            <template #header>
              <div class="card-header">
                <el-tag type="danger" size="small">违规</el-tag>
                <span class="frame-number">帧 #{{ violation.frame_number }}</span>
              </div>
            </template>
            
            <div class="violation-details">
              <p><strong>人员:</strong> {{ violation.data.person_id }}</p>
              <p><strong>起点区域:</strong> {{ violation.data.origin_zone }}</p>
              <p><strong>放置区域:</strong> {{ violation.data.drop_zone }}</p>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  violations: Array
})

const sortedViolations = computed(() => {
  return [...props.violations].reverse()
})

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN')
}
</script>

<style scoped>
.violation-panel {
  padding: 20px;
  background: #f5f7fa;
  border-radius: 4px;
  max-height: 600px;
  overflow-y: auto;
}

.violation-panel h3 {
  margin-top: 0;
  margin-bottom: 20px;
  color: #303133;
}

.no-violations {
  padding: 20px 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.frame-number {
  color: #909399;
  font-size: 12px;
}

.violation-details {
  font-size: 14px;
  line-height: 1.8;
}

.violation-details p {
  margin: 5px 0;
}

.latest {
  border: 2px solid #f56c6c;
}
</style>
