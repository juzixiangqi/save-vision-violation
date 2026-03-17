<template>
  <div class="video-player">
    <!-- 视频显示区域 -->
    <div class="video-container" :class="{ 'violation-flash': showViolationFlash }">
      <img
        v-if="currentFrame"
        :src="currentFrame"
        class="video-frame"
        alt="视频帧"
      />
      <div v-else class="placeholder">
        <el-empty description="点击播放开始测试" />
      </div>
      
      <!-- 帧信息叠加 -->
      <div class="frame-info" v-if="isPlaying">
        <el-tag size="small" type="info">
          帧: {{ currentFrameNumber }}/{{ totalFrames }}
        </el-tag>
        <el-tag size="small" type="info" style="margin-left: 8px;">
          FPS: {{ currentFps }}
        </el-tag>
      </div>
    </div>
    
    <!-- 控制栏 -->
    <div class="controls">
      <el-button
        :type="isPlaying ? 'danger' : 'primary'"
        @click="togglePlay"
      >
        <el-icon v-if="isPlaying"><VideoPause /></el-icon>
        <el-icon v-else><VideoPlay /></el-icon>
        {{ isPlaying ? '停止' : '播放' }}
      </el-button>
      
      <el-slider
        v-model="progress"
        :max="100"
        :disabled="!totalFrames"
        class="progress-slider"
        :show-stops="false"
      />
      
      <el-select v-model="playbackSpeed" size="small" style="width: 100px">
        <el-option label="0.5x" :value="0.5" />
        <el-option label="1.0x" :value="1.0" />
        <el-option label="2.0x" :value="2.0" />
      </el-select>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { VideoPlay, VideoPause } from '@element-plus/icons-vue'

const props = defineProps({
  isPlaying: Boolean,
  currentFrame: String,
  currentFrameNumber: Number,
  totalFrames: Number,
  currentFps: Number,
  violations: Array
})

const emit = defineEmits(['toggle-play', 'update-speed'])

const playbackSpeed = ref(1.0)
const showViolationFlash = ref(false)
const progress = computed({
  get: () => {
    if (!props.totalFrames || props.totalFrames === 0) return 0
    return (props.currentFrameNumber / props.totalFrames) * 100
  },
  set: (val) => {
    // 只读，不处理设置
  }
})

const togglePlay = () => {
  emit('toggle-play')
}

// 触发违规闪烁效果
const flashViolation = () => {
  showViolationFlash.value = true
  setTimeout(() => {
    showViolationFlash.value = false
  }, 1000)
}

// 监听速度变化
watch(playbackSpeed, (newVal) => {
  emit('update-speed', newVal)
})

defineExpose({
  flashViolation,
  playbackSpeed
})
</script>

<style scoped>
.video-player {
  width: 100%;
}

.video-container {
  position: relative;
  background: #000;
  border-radius: 4px;
  overflow: hidden;
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.video-container.violation-flash {
  animation: flash-red 1s ease-in-out;
}

@keyframes flash-red {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 108, 108, 0); }
  50% { box-shadow: 0 0 20px 5px rgba(245, 108, 108, 0.8); border: 3px solid #f56c6c; }
}

.video-frame {
  max-width: 100%;
  max-height: 600px;
  object-fit: contain;
}

.placeholder {
  padding: 40px;
}

.frame-info {
  position: absolute;
  bottom: 10px;
  left: 10px;
  display: flex;
}

.controls {
  margin-top: 15px;
  display: flex;
  align-items: center;
  gap: 15px;
}

.progress-slider {
  flex: 1;
}
</style>
