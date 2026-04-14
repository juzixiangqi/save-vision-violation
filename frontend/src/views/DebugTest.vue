<template>
  <div class="debug-page">
    <el-page-header title="调试测试" @back="goBack">
      <template #extra>
        <el-button @click="goToDashboard">返回面板</el-button>
      </template>
    </el-page-header>

    <div class="debug-content">
      <el-row :gutter="20">
        <!-- 左侧控制面板 -->
        <el-col :span="8">
          <el-card class="control-card">
            <template #header>
              <span>测试控制</span>
            </template>

            <!-- 视频选择 -->
            <el-form label-position="top">
              <el-form-item label="测试视频">
                <el-select 
                  v-model="selectedVideo" 
                  placeholder="选择测试视频"
                  @change="onVideoSelect"
                  style="width: 100%"
                >
                  <el-option
                    v-for="video in availableVideos"
                    :key="video.id"
                    :label="video.name"
                    :value="video.source"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="视频路径">
                <el-input 
                  v-model="videoPath" 
                  placeholder="输入视频文件路径"
                  @blur="loadVideoInfo"
                >
                  <template #append>
                    <el-button @click="loadVideoInfo">加载</el-button>
                  </template>
                </el-input>
              </el-form-item>

              <!-- 视频信息 -->
              <div v-if="videoInfo" class="video-info">
                <el-divider />
                <el-descriptions :column="2" size="small" border>
                  <el-descriptions-item label="总帧数">
                    {{ videoInfo.total_frames }}
                  </el-descriptions-item>
                  <el-descriptions-item label="FPS">
                    {{ videoInfo.fps?.toFixed(1) }}
                  </el-descriptions-item>
                  <el-descriptions-item label="分辨率">
                    {{ videoInfo.width }}x{{ videoInfo.height }}
                  </el-descriptions-item>
                  <el-descriptions-item label="时长">
                    {{ formatDuration(videoInfo.duration) }}
                  </el-descriptions-item>
                </el-descriptions>
              </div>

              <!-- 流控制按钮 -->
              <el-form-item>
                <el-button 
                  v-if="!isStreaming"
                  type="primary" 
                  @click="startStream" 
                  :loading="starting"
                  :disabled="!videoPath || !videoInfo"
                  style="width: 100%"
                >
                  <el-icon><VideoPlay /></el-icon>
                  开始播放
                </el-button>
                <el-button 
                  v-else
                  type="danger" 
                  @click="stopStream" 
                  style="width: 100%"
                >
                  <el-icon><VideoPause /></el-icon>
                  停止播放
                </el-button>
              </el-form-item>

              <!-- 播放速度 -->
              <el-form-item label="播放速度" v-if="videoInfo">
                <el-slider 
                  v-model="playSpeed" 
                  :min="0.1"
                  :max="3"
                  :step="0.1"
                  show-input
                  :disabled="isStreaming"
                />
              </el-form-item>

              <!-- 跳帧 -->
              <el-form-item label="跳帧" v-if="videoInfo">
                <el-input-number 
                  v-model="frameSkip" 
                  :min="0"
                  :max="10"
                  :disabled="isStreaming"
                />
                <span class="hint">每N帧处理一次</span>
              </el-form-item>
            </el-form>

            <!-- 检测日志 -->
            <el-divider />
            <div class="detection-log">
              <h4>检测日志</h4>
              <el-scrollbar height="200px">
                <div v-if="currentFrame" class="log-content">
                  <p><strong>帧号:</strong> {{ currentFrame.frame_number }} / {{ currentFrame.total_frames }}</p>
                  <p><strong>检测到人员:</strong> {{ currentFrame.detections?.persons || 0 }} 人</p>
                  <p><strong>检测到姿态:</strong> {{ currentFrame.detections?.poses || 0 }} 个</p>
                  <p><strong>违规数量:</strong> 
                    <el-tag :type="currentFrame.detections?.violations?.length > 0 ? 'danger' : 'success'">
                      {{ currentFrame.detections?.violations?.length || 0 }}
                    </el-tag>
                  </p>

                  <!-- 人员区域分布 -->
                  <div v-if="currentFrame.detections?.track_zones" class="log-section">
                    <p class="section-title">人员区域:</p>
                    <ul class="detail-list">
                      <li v-for="(zone, trackId) in currentFrame.detections.track_zones" :key="trackId">
                        {{ trackId }}: <el-tag size="small" :type="zone ? 'primary' : 'info'">{{ zone || '无区域' }}</el-tag>
                      </li>
                    </ul>
                  </div>

                  <!-- 违规详情 -->
                  <div v-if="currentFrame.detections?.violations?.length > 0" class="log-section">
                    <p class="section-title error">违规详情:</p>
                    <ul class="detail-list">
                      <li v-for="(v, i) in currentFrame.detections.violations" :key="i" class="error-item">
                        人员 {{ v.track_id || v.person_id }}: {{ v.from_zone || v.origin_zone }} → {{ v.to_zone || v.drop_zone }}
                      </li>
                    </ul>
                  </div>
                </div>
                <el-empty v-else description="暂无检测数据" :image-size="60" />
              </el-scrollbar>
            </div>
          </el-card>
        </el-col>

        <!-- 右侧预览区域 -->
        <el-col :span="16">
          <el-card class="preview-card">
            <template #header>
              <span>检测结果预览</span>
              <el-tag v-if="isStreaming" type="success" style="margin-left: 10px">
                播放中
              </el-tag>
              <el-tag v-else-if="currentFrame" type="info" style="margin-left: 10px">
                已暂停
              </el-tag>
            </template>

            <div class="preview-container">
              <div v-if="currentFrame" class="image-wrapper">
                <img :src="currentFrame.image" alt="检测结果" class="result-image" />
              </div>
              <el-empty 
                v-else 
                description="点击「开始播放」按钮查看结果" 
                :image-size="120"
              >
                <template #image>
                  <el-icon :size="60" color="#909399"><Picture /></el-icon>
                </template>
              </el-empty>
            </div>

            <!-- 图例 -->
            <div v-if="currentFrame" class="legend">
              <el-divider />
              <h4>图例说明</h4>
              <div class="legend-items">
                <div class="legend-item">
                  <span class="color-box" style="background: #00FF00;"></span>
                  <span>人员检测框</span>
                </div>
                <div class="legend-item">
                  <span class="color-box" style="background: #00FFFF;"></span>
                  <span>姿态关键点</span>
                </div>
                <div class="legend-item">
                  <span class="color-box" style="background: #0000FF;"></span>
                  <span>骨架连线</span>
                </div>
                <div class="legend-item">
                  <span class="color-box" style="background: #800080;"></span>
                  <span>区域边界</span>
                </div>
                <div class="legend-item">
                  <span class="color-box" style="background: #FF0000;"></span>
                  <span>违规标记</span>
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { VideoPlay, VideoPause, Picture } from '@element-plus/icons-vue'
import api from '../api'

const router = useRouter()

// 状态
const selectedVideo = ref('')
const videoPath = ref('')
const videoInfo = ref(null)
const availableVideos = ref([])

// 视频流状态
const isStreaming = ref(false)
const starting = ref(false)
const streamId = ref(null)
const eventSource = ref(null)
const currentFrame = ref(null)
const playSpeed = ref(1.0)
const frameSkip = ref(0)

// 加载可用的视频列表
onMounted(async () => {
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

// 清理资源
onUnmounted(() => {
  stopStream()
})

// 选择视频
const onVideoSelect = (source) => {
  videoPath.value = source
  loadVideoInfo()
}

// 加载视频信息
const loadVideoInfo = async () => {
  if (!videoPath.value) {
    videoInfo.value = null
    return
  }

  try {
    const response = await api.getVideoInfo(videoPath.value)
    videoInfo.value = response.data
    ElMessage.success('视频信息加载成功')
  } catch (error) {
    ElMessage.error('加载视频信息失败: ' + (error.response?.data?.detail || error.message))
    videoInfo.value = null
  }
}

// 开始视频流
const startStream = async () => {
  if (!videoPath.value) {
    ElMessage.warning('请选择视频')
    return
  }

  starting.value = true
  
  try {
    // 发送开始流请求
    const response = await api.startDebugStream(
      videoPath.value,
      'debug',
      frameSkip.value,
      playSpeed.value
    )
    
    if (!response.ok) {
      throw new Error('启动视频流失败')
    }
    
    // 获取 stream ID
    streamId.value = response.headers.get('X-Stream-Id')
    
    // 创建 EventSource 连接
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    
    isStreaming.value = true
    starting.value = false
    
    // 读取 SSE 数据
    readStream(reader, decoder)
    
    ElMessage.success('视频流已启动')
  } catch (error) {
    ElMessage.error('启动视频流失败: ' + error.message)
    starting.value = false
  }
}

// 读取流数据
const readStream = async (reader, decoder) => {
  let buffer = ''
  
  try {
    while (isStreaming.value) {
      const { done, value } = await reader.read()
      
      if (done) {
        break
      }
      
      // 将新数据追加到缓冲区
      buffer += decoder.decode(value, { stream: true })
      
      // 按 SSE 事件分隔符分割 (\n\n)
      const events = buffer.split('\n\n')
      
      // 保留最后一个不完整的部分
      buffer = events.pop() || ''
      
      // 处理完整的 SSE 事件
      for (const eventText of events) {
        if (!eventText.trim()) continue
        
        const lines = eventText.split('\n')
        let eventType = null
        let eventData = null
        
        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            eventData = line.slice(5).trim()
          }
        }
        
        if (eventType && eventData) {
          handleStreamEvent(eventType, eventData)
        }
      }
    }
  } catch (error) {
    if (isStreaming.value) {
      console.error('Stream error:', error)
      ElMessage.error('视频流中断: ' + error.message)
    }
  } finally {
    isStreaming.value = false
    streamId.value = null
  }
}

// 用于存储当前图片URL以便释放
let currentImageUrl = null

// 处理流事件
const handleStreamEvent = (eventType, data) => {
  try {
    const parsedData = JSON.parse(data)

    switch (eventType) {
      case 'frame':
        // 将 base64 转换为 Blob URL 以提高性能
        if (parsedData.image && parsedData.image.startsWith('data:image')) {
          // 释放之前的 URL
          if (currentImageUrl) {
            URL.revokeObjectURL(currentImageUrl)
          }
          // 创建新的 Blob URL
          const base64Data = parsedData.image.split(',')[1]
          const byteCharacters = atob(base64Data)
          const byteNumbers = new Array(byteCharacters.length)
          for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i)
          }
          const byteArray = new Uint8Array(byteNumbers)
          const blob = new Blob([byteArray], { type: 'image/jpeg' })
          currentImageUrl = URL.createObjectURL(blob)
          parsedData.image = currentImageUrl
        }
        currentFrame.value = parsedData
        break
      case 'violation':
        // 违规事件已在 frame 数据中处理，这里可以添加额外的提示
        console.log('Violation detected:', parsedData)
        break
      case 'error':
        ElMessage.error('流错误: ' + parsedData.message)
        stopStream()
        break
      case 'end':
        ElMessage.success('视频播放完成')
        stopStream()
        break
    }
  } catch (error) {
    console.error('Error parsing stream data:', error)
  }
}

// 停止视频流
const stopStream = async () => {
  isStreaming.value = false

  if (streamId.value) {
    try {
      await api.stopDebugStream(streamId.value)
    } catch (error) {
      console.error('Error stopping stream:', error)
    }
    streamId.value = null
  }

  if (eventSource.value) {
    eventSource.value.close()
    eventSource.value = null
  }

  // 释放图片 URL
  if (currentImageUrl) {
    URL.revokeObjectURL(currentImageUrl)
    currentImageUrl = null
  }
}

// 格式化时长
const formatDuration = (seconds) => {
  if (!seconds) return '0s'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  if (mins > 0) {
    return `${mins}分${secs}秒`
  }
  return `${secs}秒`
}

// 导航
const goBack = () => {
  stopStream()
  router.back()
}

const goToDashboard = () => {
  stopStream()
  router.push('/dashboard')
}
</script>

<style scoped>
.debug-page {
  max-width: 1600px;
  margin: 0 auto;
  padding: 20px;
}

.debug-content {
  margin-top: 20px;
}

.control-card {
  height: calc(100vh - 140px);
  overflow: auto;
}

.video-info {
  margin: 15px 0;
}

.preview-card {
  height: calc(100vh - 140px);
}

.preview-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
  background: #f5f7fa;
  border-radius: 4px;
}

.image-wrapper {
  width: 100%;
  display: flex;
  justify-content: center;
}

.result-image {
  max-width: 100%;
  max-height: 600px;
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.detection-log {
  margin-top: 20px;
}

.detection-log h4 {
  margin-bottom: 10px;
  color: #303133;
}

.log-content {
  padding: 10px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
}

.log-content p {
  margin: 5px 0;
}

.log-section {
  margin-top: 10px;
}

.section-title {
  font-weight: bold;
  color: #606266;
  margin-bottom: 5px;
}

.section-title.error {
  color: #f56c6c;
}

.detail-list {
  margin: 0;
  padding-left: 20px;
  color: #606266;
}

.detail-list li {
  margin: 3px 0;
}

.error-item {
  color: #f56c6c;
}

.legend {
  margin-top: 20px;
}

.legend h4 {
  margin-bottom: 10px;
  color: #303133;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #606266;
}

.color-box {
  width: 16px;
  height: 16px;
  border-radius: 3px;
  border: 1px solid #dcdfe6;
}

.hint {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}
</style>