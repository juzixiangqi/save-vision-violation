# 视频实时测试与违规检测设计

**创建日期**: 2026-03-17  
**目标**: 实现视频实时播放测试，支持连续帧违规检测

## 问题背景

当前系统仅支持单帧测试 (`/api/monitor/debug-process`)，但违规检测是基于动作序列的：
- 人员在A区域搬起箱子（状态：Idle → Carrying）
- 运输过程中可能经历遮挡（状态：Carrying → Occluded）
- 在B区域放下箱子（状态：Occluded/ Carrying → Idle）
- 系统判断：如果 origin_zone ≠ drop_zone 且违反规则，则判定违规

因此需要实时连续播放视频，状态机才能正确工作并检测违规。

## 设计方案

### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              VideoPlayer.vue 组件                        │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │    │
│  │  │  视频控制栏   │  │  画布显示区   │  │  违规事件列表 │  │    │
│  │  │  (播放/暂停)  │  │  (实时帧)    │  │  (高亮显示)  │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                            │                                     │
│                    EventSource (SSE)                             │
│                            │                                     │
└────────────────────────────┼─────────────────────────────────────┘
                             │
┌────────────────────────────┼─────────────────────────────────────┐
│                     Backend (FastAPI)                            │
│                            │                                     │
│  ┌─────────────────────────▼─────────────────────────────────┐   │
│  │              /api/monitor/debug-stream                     │   │
│  │                    (SSE Endpoint)                          │   │
│  │                                                            │   │
│  │  ┌────────────┐    ┌────────────┐    ┌────────────┐      │   │
│  │  │ 视频读取    │ -> │ YOLO检测   │ -> │ 状态机处理  │      │   │
│  │  │ (OpenCV)   │    │ (Person/   │    │ (违规检测)  │      │   │
│  │  │            │    │  Pose)     │    │            │      │   │
│  │  └────────────┘    └────────────┘    └────────────┘      │   │
│  │         │                                   │              │   │
│  │         ▼                                   ▼              │   │
│  │  ┌─────────────────────────────────────────────────────┐  │   │
│  │  │           DebugVisualizer (绘制标注)                 │  │   │
│  │  └─────────────────────────────────────────────────────┘  │   │
│  │         │                                                │   │
│  │         ▼                                                │   │
│  │  ┌─────────────────────────────────────────────────────┐  │   │
│  │  │  SSE Stream (Base64图片 + 元数据 + 违规事件)          │  │   │
│  │  └─────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## API 设计

### 新增接口

**POST /api/monitor/debug-stream**

启动视频流处理并返回 SSE 数据流。

**请求参数**:
```json
{
  "video_path": "string",      // 视频文件路径
  "camera_id": "string",       // 摄像头ID（用于违规记录）
  "frame_skip": 0,             // 跳帧数，0表示不跳帧
  "speed": 1.0                 // 播放速度倍率 (0.5, 1.0, 2.0)
}
```

**SSE 响应格式**:
```
event: frame
data: {
  "type": "frame",
  "timestamp": 1234567890,
  "frame_number": 150,
  "total_frames": 3000,
  "image": "data:image/jpeg;base64,/9j/4AAQ...",
  "width": 1920,
  "height": 1080,
  "detections": {
    "persons": [...],
    "poses": [...],
    "violations": [...]
  }
}

event: violation
data: {
  "type": "violation",
  "timestamp": 1234567890,
  "frame_number": 150,
  "data": {
    "person_id": "person_1",
    "origin_zone": "zone_a",
    "drop_zone": "zone_b",
    "violation_type": "box_move_violation"
  }
}

event: end
data: {"type": "end", "message": "视频播放完成"}
```

**POST /api/monitor/debug-stream/stop**

停止正在进行的视频流测试。

## 前端组件设计

### 组件结构

```
views/
└── DebugMonitor.vue           # 主页面
    ├── VideoPlayer.vue        # 视频播放器组件
    │   ├── PlaybackControls   # 播放控制栏
    │   └── CanvasRenderer     # 画布渲染
    └── ViolationPanel.vue     # 违规事件面板
```

### VideoPlayer 组件

**Props**:
- `videoPath`: string - 视频文件路径
- `cameraId`: string - 摄像头ID

**状态管理**:
- `isPlaying`: boolean - 是否播放中
- `currentFrame`: number - 当前帧号
- `totalFrames`: number - 总帧数
- `fps`: number - 当前FPS
- `violations`: Array - 违规事件列表

**方法**:
- `startStream()`: 启动 SSE 连接
- `stopStream()`: 停止 SSE 连接
- `handleFrame(data)`: 处理帧数据
- `handleViolation(data)`: 处理违规事件

**视觉效果**:
- 违规发生时：
  - 视频画面边框闪烁红色
  - 违规事件高亮显示在右侧面板
  - 播放进度条标记违规时间点

## 后端实现

### 核心流程

1. **初始化阶段**:
   - 验证视频文件可访问
   - 初始化检测器、违规检查器、状态机
   - 重置区域管理器

2. **流处理循环**:
   ```python
   async def stream_video(video_path, camera_id, frame_skip, speed):
       cap = cv2.VideoCapture(video_path)
       detector = YOLODetector()
       checker = ViolationChecker()
       visualizer = DebugVisualizer()
       
       while not stopped and frame_available:
           ret, frame = cap.read()
           if not ret:
               break
           
           # 处理帧
           persons, poses = detector.detect(frame)
           boxes = []  # TODO: 箱子检测
           violations = checker.process_frame(persons, poses, boxes, camera_id)
           
           # 绘制标注
           processed = visualizer.draw_detections(
               frame, persons, poses, boxes, violations, camera_id
           )
           
           # 编码并发送
           yield encode_frame(processed, violations)
           
           # 控制帧率
           await asyncio.sleep(frame_delay / speed)
   ```

3. **停止机制**:
   - 使用全局字典跟踪活跃流
   - 客户端断开或调用停止API时中断循环

### 关键类修改

**DebugVisualizer**:
- 添加 `reset()` 方法重置状态机
- 添加帧号和时间戳显示

**ViolationChecker**:
- 确保每轮测试状态机重新初始化

## 数据流

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  视频帧   │ --> │  检测    │ --> │ 状态更新  │
└──────────┘     └──────────┘     └──────────┘
                                          │
                                          ▼
┌──────────┐     ┌──────────┐     ┌──────────┐
│  客户端   │ <-- │  SSE流   │ <-- │ 违规判断  │
└──────────┘     └──────────┘     └──────────┘
```

## 错误处理

1. **视频文件无法打开**:
   - 返回 HTTP 400，提示检查文件路径

2. **处理过程中出错**:
   - SSE 发送 error 事件，前端显示错误信息
   - 保持连接，尝试继续处理下一帧

3. **客户端断开**:
   - 检测 SSE 连接关闭
   - 清理资源，停止视频处理

## 性能考虑

1. **跳帧支持**: 通过 `frame_skip` 参数降低处理频率
2. **图片压缩**: JPEG 质量控制在 70-80%，平衡清晰度和带宽
3. **分辨率适配**: 支持原始分辨率或缩放（可配置）

## 测试策略

1. **单元测试**:
   - 测试 SSE 流正确发送数据
   - 测试停止机制正常工作

2. **集成测试**:
   - 使用测试视频验证完整流程
   - 验证违规检测在实时流下工作正常

## 依赖

- 后端: FastAPI SSE 支持（使用 `fastapi.responses.StreamingResponse`）
- 前端: 原生 EventSource API（无需额外库）

## 部署注意事项

1. 确保视频文件路径对后端服务可访问
2. 设置合理的超时时间（长视频可能需要更长时间）
3. 考虑并发流数量限制（CPU密集型任务）
