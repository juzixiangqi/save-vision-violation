<template>
  <el-card class="violation-list">
    <template #header>
      <div class="card-header">
        <span>违规事件</span>
        <el-button size="small" @click="clearAll">清空</el-button>
      </div>
    </template>
    
    <div class="violation-items" v-if="violations.length > 0">
      <el-timeline>
        <el-timeline-item
          v-for="(violation, index) in violations"
          :key="index"
          type="danger"
          :timestamp="violation.time"
          placement="top"
        >
          <el-card class="violation-card">
            <div class="violation-header">
              <el-tag type="danger" size="small">违规</el-tag>
              <span class="violation-time">{{ violation.time }}</span>
            </div>
            <div class="violation-body">
              <p><strong>人员:</strong> {{ violation.person_id }}</p>
              <p>
                <strong>路径:</strong>
                <el-tag size="small" type="info">{{ violation.origin_zone }}</el-tag>
                →
                <el-tag size="small" type="danger">{{ violation.drop_zone }}</el-tag>
              </p>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </div>
    
    <el-empty v-else description="暂无违规事件" />
  </el-card>
</template>

<script setup>
import { ref } from 'vue'

const violations = ref([])

const clearAll = () => {
  violations.value = []
}
</script>

<style scoped>
.violation-list {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.violation-items {
  max-height: 600px;
  overflow-y: auto;
}

.violation-card {
  margin-bottom: 10px;
  border-left: 4px solid #f56c6c;
}

.violation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.violation-time {
  font-size: 12px;
  color: #909399;
}

.violation-body p {
  margin: 5px 0;
  font-size: 13px;
}
</style>
