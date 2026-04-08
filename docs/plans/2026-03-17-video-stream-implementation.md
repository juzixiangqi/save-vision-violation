# 视频实时测试与违规检测实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现视频实时播放测试功能，支持SSE流式传输处理后的帧和违规事件

**Architecture:** 使用 FastAPI SSE (Server-Sent Events) 实时推送处理后的视频帧，前端通过 EventSource 接收并显示，违规发生时高亮提示

**Tech Stack:** FastAPI StreamingResponse, Vue 3, EventSource, OpenCV, YOLOv8

---

## 前置检查

### 检查现有代码
- 阅读 `backend/app/api/monitor.py` - 了解现有API结构
- 阅读 `backend/app/core/debug_visualizer.py` - 了解可视化逻辑
- 阅读 `frontend/src/views/` - 了解前端页面结构

---

## Task 1: 后端 - 添加SSE流处理API

**Files:**
- Create: `backend/app/api/debug_stream.py`
- Modify: `backend/app/api/__init__.py` (注册路由)
- Modify: `backend/app/main.py` (包含新路由)

**Step 1: 创建 SSE 流处理模块**

创建 `backend/app/api/debug_stream.py`:

```python
import asyncio
import cv2
import base64
import json
from typing import Dict, Optional, Set
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime

from app.core.detector import YOLODetector
from app.core.violation_checker import ViolationChecker
from app.core.zone_manager import zone_manager
from app.core.debug_visualizer import DebugVisualizer
from app.core.state_machine import StateMachine

router = APIRouter(prefix="/api/monitor", tags=["debug-stream"])

# 活跃流跟踪
active_streams: Dict[str, bool] = {}


class StreamRequest(BaseModel):
    video_path: str
    camera_id: str = "debug"
    frame_skip: int = 0
    speed: float = 1.0


async def process_video_stream(
    video_path: str,
    camera_id: str,
    frame_skip: int,
    speed: float,
    stream_id: str
):
    """处理视频流并生成 SSE 事件"""
    global active_streams
    
    # 打开视频
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        yield f"event: error\ndata: {json.dumps({'message': f'无法打开视频: {video_path}'})}\n\n"
        return
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_delay = 1.0 / fps if fps > 0 else 0.033
    
    # 初始化组件
    detector = YOLODetector()
    checker = ViolationChecker()
    visualizer = DebugVisualizer(
        frame_width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        frame_height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    )
    
    # 重置区域管理器
    zone_manager.reload()
    
    frame_number = 0
    
    try:
        while active_streams.get(stream_id, False):
            ret, frame = cap.read()
            if not ret:
                # 视频结束
                yield f"event: end\ndata: {json.dumps({'type': 'end', 'message': '视频播放完成'})}\n\n"
                break
            
            frame_number += 1
            
            # 跳帧处理
            if frame_skip > 0 and frame_number % (frame_skip + 1) != 0:
                continue
            
            # 处理帧
            persons, poses = detector.detect(frame)
            boxes = []  # TODO: 箱子检测
            violations = checker.process_frame(persons, poses, boxes, camera_id)
            
            # 绘制标注
            frame_info = f"帧号: {frame_number}/{total_frames}"
            processed_frame = visualizer.draw_detections(
                frame, persons, poses, boxes, violations, camera_id, frame_info
            )
            
            # 编码为 base64
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 75]
            _, buffer = cv2.imencode(".jpg", processed_frame, encode_params)
            img_base64 = base64.b64encode(buffer).decode("utf-8")
            
            # 构建帧数据
            frame_data = {
                "type": "frame",
                "timestamp": datetime.now().isoformat(),
                "frame_number": frame_number,
                "total_frames": total_frames,
                "fps": round(fps, 1),
                "image": f"data:image/jpeg;base64,{img_base64}",
                "width": processed_frame.shape[1],
                "height": processed_frame.shape[0],
                "detections": {
                    "persons": len(persons),
                    "poses": len(poses),
                    "violations": violations
                }
            }
            
            yield f"event: frame\ndata: {json.dumps(frame_data)}\n\n"
            
            # 发送违规事件
            for violation in violations:
                violation_data = {
                    "type": "violation",
                    "timestamp": datetime.now().isoformat(),
                    "frame_number": frame_number,
                    "data": violation
                }
                yield f"event: violation\ndata: {json.dumps(violation_data)}\n\n"
            
            # 控制帧率
            await asyncio.sleep(frame_delay / speed)
            
    except Exception as e:
        error_data = {"type": "error", "message": str(e)}
        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
    finally:
        cap.release()
        if stream_id in active_streams:
            del active_streams[stream_id]


@router.post("/debug-stream")
async def start_debug_stream(request: StreamRequest):
    """启动视频调试流"""
    import uuid
    
    stream_id = str(uuid.uuid4())
    active_streams[stream_id] = True
    
    return StreamingResponse(
        process_video_stream(
            video_path=request.video_path,
            camera_id=request.camera_id,
            frame_skip=request.frame_skip,
            speed=request.speed,
            stream_id=stream_id
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Stream-Id": stream_id
        }
    )


@router.post("/debug-stream/stop")
async def stop_debug_stream(stream_id: str):
    """停止视频调试流"""
    if stream_id in active_streams:
        active_streams[stream_id] = False
        return {"message": "流已停止", "stream_id": stream_id}
    else:
        raise HTTPException(status_code=404, detail="流不存在或已停止")


@router.get("/debug-stream/status")
async def get_stream_status():
    """获取活跃流状态"""
    return {
        "active_streams": list(active_streams.keys()),
        "count": len(active_streams)
    }
```

**Step 2: 在 API 包中注册路由**

修改 `backend/app/api/__init__.py`:

```python
from fastapi import APIRouter
from app.api import config, zones, rules, monitor, debug_stream

api_router = APIRouter()

api_router.include_router(config.router)
api_router.include_router(zones.router)
api_router.include_router(rules.router)
api_router.include_router(monitor.router)
api_router.include_router(debug_stream.router)  # 添加这一行
```

**Step 3: 验证导入路径**

如果 `backend/app/api/__init__.py` 不存在，需要创建它。

**Step 4: 测试后端API**

启动后端服务：
```bash
cd backend
uv run python run.py
```

测试API是否注册成功：
```bash
curl http://localhost:8000/api/monitor/debug-stream/status
```

Expected: `{"active_streams": [], "count": 0}`

**Step 5: Commit**

```bash
git add backend/app/api/debug_stream.py backend/app/api/__init__.py
git commit -m "feat: add SSE video debug stream API"
```

---

## Task 2: 前端 - 创建视频调试页面

**Files:**
- Create: `frontend/src/views/DebugMonitor.vue`
- Create: `frontend/src/components/VideoPlayer.vue`
- Modify: `frontend/src/router/index.js`

**Step 1: 创建 VideoPlayer 组件**

创建 `frontend/src/components/VideoPlayer.vue`:

```vue
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
        :icon="isPlaying ? VideoPause : VideoPlay"
      >
        {{ isPlaying ? '停止' : '播放' }}
      </el-button>
      
      <el-slider
        v-model="progress"
        :max="100"
        :disabled="!totalFrames"
        class="progress-slider"
        show-stops
        :marks="violationMarks"
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
import { ref, computed } from 'vue'
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
const progress = ref(0)

// 违规时间点标记
const violationMarks = computed(() => {
  const marks = {}
  if (props.totalFrames && props.violations) {
    props.violations.forEach(v => {
      if (v.frame_number) {
        const percent = (v.frame_number / props.totalFrames) * 100
        marks[Math.round(percent)] = {
          style: { color: '#f56c6c' },
          label: '⚠️'
        }
      }
    })
  }
  return marks
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
```

**Step 2: 创建 ViolationPanel 组件**

创建 `frontend/src/components/ViolationPanel.vue`:

```vue
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
          :type="'danger'"
          :timestamp="formatTime(violation.timestamp)"
          :hollow="true"
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
```

**Step 3: 创建 DebugMonitor 页面**

创建 `frontend/src/views/DebugMonitor.vue`:

```vue
<template>
  <div class="debug-monitor">
    <el-page-header title="视频调试测试" @back="goBack" />
    
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
          />
          
          <div class="settings" style="margin-top: 15px;">
            <el-form :inline="true" size="small">
              <el-form-item label="视频路径">
                <el-input v-model="videoPath" placeholder="输入视频文件路径" style="width: 300px" />
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
import { ref, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import VideoPlayer from '../components/VideoPlayer.vue'
import ViolationPanel from '../components/ViolationPanel.vue'

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

// 设置
const videoPath = ref('')
const frameSkip = ref(0)

// EventSource
let eventSource = null
let streamId = null

const goBack = () => {
  router.back()
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
    const infoRes = await fetch(`/api/monitor/debug-video-info?video_path=${encodeURIComponent(videoPath.value)}`)
    if (!infoRes.ok) {
      throw new Error('无法获取视频信息')
    }
    videoInfo.value = await infoRes.json()
    totalFrames.value = videoInfo.value.total_frames
    
    // 启动 SSE 流
    const speed = videoPlayerRef.value?.playbackSpeed || 1.0
    const response = await fetch('/api/monitor/debug-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_path: videoPath.value,
        camera_id: 'debug',
        frame_skip: frameSkip.value,
        speed: speed
      })
    })
    
    if (!response.ok) {
      throw new Error('启动流失败')
    }
    
    streamId = response.headers.get('X-Stream-Id')
    
    // 处理 SSE 流
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    
    isPlaying.value = true
    violations.value = []
    
    while (isPlaying.value) {
      const { done, value } = await reader.read()
      if (done) break
      
      const text = decoder.decode(value)
      const lines = text.split('\n')
      
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
    }
    
  } catch (error) {
    ElMessage.error('播放失败: ' + error.message)
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
  }
}

onUnmounted(() => {
  stopStream()
})
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
</style>
```

**Step 4: 添加路由**

修改 `frontend/src/router/index.js`:

```javascript
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  // ... 现有路由
  {
    path: '/debug-monitor',
    name: 'DebugMonitor',
    component: () => import('../views/DebugMonitor.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
```

**Step 5: 在导航菜单中添加入口**

找到前端导航菜单组件（可能在 `App.vue` 或单独的导航组件），添加：

```vue
<el-menu-item index="/debug-monitor">
  <el-icon><VideoPlay /></el-icon>
  <span>视频调试</span>
</el-menu-item>
```

**Step 6: Commit**

```bash
git add frontend/src/components/VideoPlayer.vue

git add frontend/src/components/ViolationPanel.vue

git add frontend/src/views/DebugMonitor.vue

git add frontend/src/router/index.js
git commit -m "feat: add video debug monitor page with SSE support"
```

---

## Task 3: 前端 - 修复 CORS 和路径问题

**Files:**
- Modify: `frontend/vite.config.js`

**Step 1: 确保代理配置正确**

修改 `frontend/vite.config.js`，确保 `/api` 代理到后端：

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // SSE 需要保持连接
        ws: true,
      }
    }
  }
})
```

**Step 2: Commit**

```bash
git add frontend/vite.config.js
git commit -m "fix: update vite proxy config for SSE support"
```

---

## Task 4: 集成测试

**Step 1: 测试完整流程**

1. 启动后端：
```bash
cd backend
uv run python run.py
```

2. 启动前端：
```bash
cd frontend
npm run dev
```

3. 打开浏览器访问 `http://localhost:5173/debug-monitor`

4. 输入测试视频路径，点击播放

**Step 2: 验证功能**

- [ ] 视频正常播放
- [ ] 帧号正确显示
- [ ] 违规事件被检测并显示
- [ ] 违规时视频边框闪烁
- [ ] 停止按钮正常工作
- [ ] 速度调整有效

**Step 3: Commit**

```bash
git commit -m "test: verify video debug stream functionality"
```

---

## Task 5: 文档更新

**Files:**
- Modify: `README.md` 或创建新文档

**Step 1: 添加使用说明**

在 README 中添加视频调试功能说明：

```markdown
## 视频实时调试

### 使用方法

1. 启动后端服务
2. 启动前端开发服务器
3. 访问 `http://localhost:5173/debug-monitor`
4. 输入视频文件绝对路径
5. 点击"播放"开始测试

### 功能特性

- 实时播放带标注的视频流
- 自动检测违规事件
- 违规发生时视频边框闪烁提示
- 支持调整播放速度 (0.5x, 1.0x, 2.0x)
- 支持跳帧处理（提高性能）

### API 端点

- `POST /api/monitor/debug-stream` - 启动视频流（SSE）
- `POST /api/monitor/debug-stream/stop` - 停止视频流
- `GET /api/monitor/debug-stream/status` - 查看活跃流状态
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add video debug stream usage instructions"
```

---

## 完成总结

实现完成后，系统将具备：

1. **后端**: SSE 流式传输处理后的视频帧和违规事件
2. **前端**: 实时视频播放器，违规高亮提示
3. **用户体验**: 完整的动作序列可视化，违规瞬间立即知晓

**测试建议**:
- 使用包含完整搬箱子动作的视频测试
- 验证从A区搬起箱子运到B区的违规检测
- 检查状态机是否正确跟踪（Idle → Carrying → Idle）
