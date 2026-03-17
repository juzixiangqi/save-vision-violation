<template>
  <div class="debug-monitor">
    <el-page-header title="视频实时调试" @back="goBack">
      <template #extra>
        <el-button @click="goToDashboard">返回面板</el-button>
      </template>
    </el-page-header>
    
    <el-row :gutter="20" class="content">
      <el-col :span="16">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>视频播放器</span>
              <div class="video-info" v-if="videoInfo">
                <el-tag size="small">{{ videoInfo.width }}x{{ videoInfo.height }}</el-tag>
                <el-tag size="small" style="margin-left: 8px;">{{ Math.round(videoInfo.duration) }}s</el-tag>
              </div>
            </div>
          </template>
          
          <VideoPlayer
            ref="videoPlayerRef"
            :is-playing="isPlaying"
            :current-frame="currentFrame"
            :current-frame-number="currentFrameNumber"
            :total-frames="totalFrames"
            :current-fps="currentFps"
            :violations="violations"
            @toggle-play="togglePlay"
            @update-speed="updateSpeed"
          />
          
          <div class="settings" style="margin-top: 15px;">
            <el-form :inline="true" size="small">
              <el-form-item label="视频路径">
                <el-select 
                  v-model="selectedVideo" 
                  placeholder="选择测试视频"
                  @change="onVideoSelect"
                  style="width: 250px"
                  clearable
                >
                  <el-option
                    v-for="video in availableVideos"
                    :key="video.id"
                    :label="video.name"
                    :value="video.source"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="或输入路径">
                <el-input v-model="videoPath" placeholder="输入视频文件路径" style="width: 250px" />
              </el-form-item>
              <el-form-item label="跳帧">
                <el-input-number v-model="frameSkip" :min="0" :max="10" size="small" />
              </el-form-item>
            </el-form>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="8">
        <ViolationPanel :violations="violations" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import VideoPlayer from '../components/VideoPlayer.vue'
import ViolationPanel from '../components/ViolationPanel.vue'
import api from '../api'

const router = useRouter()
const videoPlayerRef = ref(null)

// 状态
const isPlaying = ref(false)
const currentFrame = ref('')
const currentFrameNumber = ref(0)
const totalFrames = ref(0)
const currentFps = ref(0)
const violations = ref([])
const videoInfo = ref(null)
const availableVideos = ref([])
const selectedVideo = ref('')

// 设置
const videoPath = ref('')
const frameSkip = ref(0)
const playbackSpeed = ref(1.0)

// 流控制
let abortController = null
let streamId = null

onMounted(async () => {
  // 加载可用的视频列表
  try {
    const response = await api.getCameras()
    const cameras = response.data
    availableVideos.value = cameras.filter(c => c.enabled).map(c => ({
      id: c.id,
      name: c.name || c.id,
      source: c.source
    }))
  } catch (error) {
    console.error('Failed to load cameras:', error)
  }
})

onUnmounted(() => {
  stopStream()
})

const goBack = () => {
  router.back()
}

const goToDashboard = () => {
  router.push('/dashboard')
}

const onVideoSelect = (source) => {
  if (source) {
    videoPath.value = source
  }
}

const updateSpeed = (speed) => {
  playbackSpeed.value = speed
}

const togglePlay = async () => {
  if (isPlaying.value) {
    stopStream()
  } else {
    startStream()
  }
}

const startStream = async () => {
  if (!videoPath.value) {
    ElMessage.warning('请输入视频路径')
    return
  }
  
  try {
    // 先获取视频信息
    const infoRes = await api.getVideoInfo(videoPath.value)
    videoInfo.value = infoRes.data
    totalFrames.value = videoInfo.value.total_frames
    
    // 重置状态
    violations.value = []
    currentFrameNumber.value = 0
    
    // 创建 AbortController 用于取消请求
    abortController = new AbortController()
    
    // 启动 SSE 流
    const response = await fetch('/api/monitor/debug-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_path: videoPath.value,
        camera_id: 'debug',
        frame_skip: frameSkip.value,
        speed: playbackSpeed.value
      }),
      signal: abortController.signal
    })
    
    if (!response.ok) {
      throw new Error('启动流失败')
    }
    
    streamId = response.headers.get('X-Stream-Id')
    isPlaying.value = true
    
    // 处理 SSE 流
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    
    let buffer = ''
    
    while (isPlaying.value) {
      try {
        const { done, value } = await reader.read()
        if (done) break
        
        buffer += decoder.decode(value, { stream: true })
        
        // 解析 SSE 事件
        const lines = buffer.split('\n')
        buffer = lines.pop() // 保留不完整的行
        
        let event = null
        let data = null
        
        for (const line of lines) {
          if (line.startsWith('event:')) {
            event = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            data = line.slice(5).trim()
          } else if (line === '' && event && data) {
            handleSSEEvent(event, data)
            event = null
            data = null
          }
        }
      } catch (e) {
        if (e.name === 'AbortError') {
          console.log('Stream aborted')
          break
        }
        throw e
      }
    }
    
  } catch (error) {
    if (error.name !== 'AbortError') {
      ElMessage.error('播放失败: ' + error.message)
    }
    isPlaying.value = false
  }
}

const handleSSEEvent = (event, data) => {
  try {
    const parsed = JSON.parse(data)
    
    switch (event) {
      case 'frame':
        currentFrame.value = parsed.image
        currentFrameNumber.value = parsed.frame_number
        currentFps.value = parsed.fps
        break
        
      case 'violation':
        violations.value.push({
          timestamp: parsed.timestamp,
          frame_number: parsed.frame_number,
          data: parsed.data
        })
        // 触发闪烁效果
        videoPlayerRef.value?.flashViolation()
        ElMessage.warning(`检测到违规！帧 #${parsed.frame_number}`)
        break
        
      case 'error':
        ElMessage.error('流错误: ' + parsed.message)
        break
        
      case 'end':
        ElMessage.success('视频播放完成')
        isPlaying.value = false
        break
    }
  } catch (e) {
    console.error('解析SSE数据失败:', e)
  }
}

const stopStream = async () => {
  isPlaying.value = false
  
  // 中止 fetch 请求
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  
  // 通知后端停止
  if (streamId) {
    try {
      await fetch('/api/monitor/debug-stream/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stream_id: streamId })
      })
    } catch (e) {
      console.error('停止流失败:', e)
    }
    streamId = null
  }
}
</script>

<style scoped>
.debug-monitor {
  padding: 20px;
}

.content {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.video-info {
  display: flex;
}

.settings {
  padding: 15px 0;
  border-top: 1px solid #ebeef5;
}
</style>
