# 修改违规检测为 person_carry 追踪实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将系统从YOLO-pose+box检测改为检测自定义YOLO模型的person_carry类别，并基于区域轨迹追踪判定违规

**Architecture:** 使用自定义YOLO模型直接检测搬箱子的人，为每个检测到的person_carry对象分配track_id进行轨迹追踪，当对象从规则设定的from_zone移动到to_zone时触发违规判定

**Tech Stack:** FastAPI, Vue 3, YOLOv8, RabbitMQ, Redis

---

## 任务总览

### 后端任务
1. 修改配置模型 - 移除pose/box参数，新增person_carry参数
2. 重构检测器 - 使用自定义YOLO模型检测person_carry
3. 简化状态机 - 移除箱子相关逻辑，专注person_carry追踪
4. 修改检测处理流程 - 集成新的检测器和状态机
5. 添加轨迹追踪逻辑 - 为person_carry对象分配track_id并追踪

### 前端任务
6. 更新参数设置组件 - 移除搬起/放下检测，新增person_carry配置
7. 更新配置类型定义 - 匹配后端新结构

---

## Task 1: 修改配置模型 (backend/app/config/models.py)

**文件:**
- 修改: `backend/app/config/models.py`

**步骤1: 移除旧的参数类**

移除 `PoseParams` 和 `BoxDetectionParams` 类定义（第37-47行）

**步骤2: 添加新的person_carry配置类**

在第37行添加：
```python
class PersonCarryParams(BaseModel):
    """自定义YOLO模型检测搬箱子的人"""
    model: str = "person_carry.pt"  # 模型路径
    confidence: float = 0.5  # 检测置信度
    iou_threshold: float = 0.45  # NMS IoU阈值
    class_id: int = 0  # person_carry类别的ID
```

**步骤3: 移除LiftDetectionParams和DropDetectionParams**

移除第55-66行的 `LiftDetectionParams` 和 `DropDetectionParams` 类

**步骤4: 修改DetectionParams类**

将第68-74行的 `DetectionParams` 改为：
```python
class DetectionParams(BaseModel):
    person_carry: PersonCarryParams = PersonCarryParams()  # 搬箱子人员检测
    tracking: TrackingParams = TrackingParams()
```

**步骤5: 验证修改**

检查语法：
```bash
cd backend && python -c "from app.config.models import *; print('OK')"
```
预期输出: `OK`

**步骤6: Commit**

```bash
git add backend/app/config/models.py
git commit -m "feat(config): 添加person_carry配置，移除pose和box参数"
```

---

## Task 2: 重构检测器 (backend/app/core/detector.py)

**文件:**
- 修改: `backend/app/core/detector.py`

**步骤1: 简化数据类**

将 `Detection` 和 `Pose` dataclass 改为只保留需要的字段：
```python
@dataclass
class Detection:
    id: str  # track_id
    bbox: List[float]  # [x1, y1, x2, y2]
    confidence: float
    center: Tuple[float, float]
    class_name: str = "person_carry"
```

移除 `Pose` dataclass

**步骤2: 重构YOLODetector类**

将第80-103行的 `__init__` 改为：
```python
class YOLODetector:
    def __init__(self):
        config = config_manager.get_config()
        self.detection_params = config.detection_params
        
        # 加载person_carry检测模型
        self.model = load_yolo_model(self.detection_params.person_carry.model)
        print(f"[Detector] 已加载person_carry检测模型: {self.detection_params.person_carry.model}")
        
        self.id_counter = 0
```

**步骤3: 修改detect方法**

将第105-155行的 `detect` 方法改为：
```python
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """检测搬箱子的人"""
        detections = []
        
        results = self.model(
            frame,
            conf=self.detection_params.person_carry.confidence,
            iou=self.detection_params.person_carry.iou_threshold,
        )
        
        for result in results:
            if result.boxes is None:
                continue
                
            for i, box in enumerate(result.boxes):
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                
                # 只检测person_carry类别
                if cls != self.detection_params.person_carry.class_id:
                    continue
                
                bbox = box.xyxy[0].cpu().numpy().tolist()
                x1, y1, x2, y2 = bbox
                center = ((x1 + x2) / 2, (y1 + y2) / 2)
                
                self.id_counter += 1
                detections.append(
                    Detection(
                        id=f"person_carry_{self.id_counter}",
                        bbox=[float(x) for x in bbox],
                        confidence=conf,
                        center=center,
                    )
                )
        
        return detections
```

**步骤4: 移除detect_boxes方法和POSE_KEYPOINTS**

移除第157-224行的 `detect_boxes` 方法和 `POSE_KEYPOINTS` 常量

**步骤5: 验证修改**

```bash
cd backend && python -c "from app.core.detector import YOLODetector; print('OK')"
```
预期输出: `OK`

**步骤6: Commit**

```bash
git add backend/app/core/detector.py
git commit -m "feat(detector): 重构为person_carry专用检测器"
```

---

## Task 3: 简化状态机 (backend/app/core/state_machine.py)

**文件:**
- 修改: `backend/app/core/state_machine.py`

**步骤1: 修改PersonState枚举**

将第8-12行的枚举改为：
```python
class PersonState(Enum):
    IDLE = "idle"
    TRACKING = "tracking"  # 正在追踪中
```

**步骤2: 修改PersonStateData数据类**

将第14-25行的数据类改为：
```python
@dataclass
class PersonStateData:
    track_id: str
    state: PersonState
    origin_zone: Optional[str] = None
    current_zone: Optional[str] = None
    last_update: datetime = field(default_factory=datetime.now)
    position_history: List[Dict] = field(default_factory=list)
    last_seen: datetime = field(default_factory=datetime.now)
```

**步骤3: 重写StateMachine类**

将第27-154行的状态机改为：
```python
class StateMachine:
    """person_carry对象轨迹追踪状态机"""
    
    def __init__(self):
        self.tracks: Dict[str, PersonStateData] = {}
    
    def get_track(self, track_id: str) -> Optional[PersonStateData]:
        """获取追踪对象状态"""
        return self.tracks.get(track_id)
    
    def start_tracking(self, track_id: str, zone: Optional[str]) -> bool:
        """开始追踪新对象"""
        if track_id not in self.tracks:
            self.tracks[track_id] = PersonStateData(
                track_id=track_id,
                state=PersonState.IDLE,
                origin_zone=zone,
                current_zone=zone,
            )
            return True
        return False
    
    def update_position(self, track_id: str, position: tuple, zone: Optional[str]):
        """更新对象位置和区域"""
        if track_id not in self.tracks:
            self.tracks[track_id] = PersonStateData(
                track_id=track_id,
                state=PersonState.IDLE,
            )
        
        track = self.tracks[track_id]
        track.last_seen = datetime.now()
        
        # 记录首次出现的区域为origin_zone
        if track.origin_zone is None and zone is not None:
            track.origin_zone = zone
            track.state = PersonState.TRACKING
        
        # 更新当前区域
        if zone is not None:
            track.current_zone = zone
        
        # 记录位置历史
        track.position_history.append({
            "position": position,
            "zone": zone,
            "timestamp": datetime.now().isoformat(),
        })
        
        # 保持最近100个位置
        if len(track.position_history) > 100:
            track.position_history = track.position_history[-100:]
        
        track.last_update = datetime.now()
    
    def check_violation(self, track_id: str, rules: List[Dict]) -> Optional[Dict]:
        """
        检查是否违反规则
        规则格式: {"from_zone": "A", "to_zone": "B", "name": "规则名称"}
        返回违规数据或None
        """
        track = self.tracks.get(track_id)
        if not track:
            return None
        
        if track.state != PersonState.TRACKING:
            return None
        
        # 检查是否满足任何规则
        for rule in rules:
            if (track.origin_zone == rule.get("from_zone") and 
                track.current_zone == rule.get("to_zone")):
                # 违规！
                violation = {
                    "track_id": track_id,
                    "rule_name": rule.get("name", "未知规则"),
                    "from_zone": track.origin_zone,
                    "to_zone": track.current_zone,
                    "origin_zone_name": rule.get("from_zone"),
                    "target_zone_name": rule.get("to_zone"),
                    "trajectory": track.position_history.copy(),
                    "timestamp": datetime.now().isoformat(),
                }
                return violation
        
        return None
    
    def reset_track(self, track_id: str):
        """重置追踪对象状态"""
        if track_id in self.tracks:
            del self.tracks[track_id]
    
    def cleanup_stale_tracks(self, timeout_seconds: int = 30) -> List[str]:
        """清理长时间未见的追踪对象，返回被清理的track_id列表"""
        now = datetime.now()
        stale_ids = []
        
        for track_id, track in list(self.tracks.items()):
            elapsed = (now - track.last_seen).total_seconds()
            if elapsed > timeout_seconds:
                stale_ids.append(track_id)
                del self.tracks[track_id]
        
        return stale_ids
```

**步骤4: 验证修改**

```bash
cd backend && python -c "from app.core.state_machine import StateMachine; print('OK')"
```
预期输出: `OK`

**步骤5: Commit**

```bash
git add backend/app/core/state_machine.py
git commit -m "feat(state_machine): 简化为person_carry轨迹追踪状态机"
```

---

## Task 4: 添加简单轨迹追踪器 (backend/app/core/tracker.py)

**文件:**
- 创建: `backend/app/core/tracker.py`

**步骤1: 创建简单的IOU追踪器**

```python
"""
简单的IOU-based轨迹追踪器
为每个person_carry检测分配稳定的track_id
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class Track:
    id: str
    bbox: List[float]
    center: Tuple[float, float]
    age: int = 0
    hits: int = 1


def calculate_iou(box1: List[float], box2: List[float]) -> float:
    """计算两个bbox的IOU"""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    if x2 <= x1 or y2 <= y1:
        return 0.0
    
    intersection = (x2 - x1) * (y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0.0


class SimpleTracker:
    """简单的IOU-based多目标追踪器"""
    
    def __init__(self, max_age: int = 30, min_hits: int = 3, iou_threshold: float = 0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.tracks: Dict[str, Track] = {}
        self.next_id = 1
    
    def update(self, detections: List) -> List[Track]:
        """
        更新追踪器，将检测与现有轨迹匹配
        
        Args:
            detections: Detection对象列表
            
        Returns:
            当前活跃的Track列表
        """
        # 如果没有检测，更新现有轨迹的age
        if not detections:
            for track in list(self.tracks.values()):
                track.age += 1
            
            # 移除超时的轨迹
            self.tracks = {
                k: v for k, v in self.tracks.items() 
                if v.age < self.max_age
            }
            
            return list(self.tracks.values())
        
        # 计算IOU矩阵
        matched_tracks = set()
        matched_detections = set()
        
        for det_idx, det in enumerate(detections):
            best_iou = 0.0
            best_track_id = None
            
            for track_id, track in self.tracks.items():
                if track_id in matched_tracks:
                    continue
                    
                iou = calculate_iou(det.bbox, track.bbox)
                if iou > best_iou and iou >= self.iou_threshold:
                    best_iou = iou
                    best_track_id = track_id
            
            if best_track_id:
                # 匹配成功，更新轨迹
                track = self.tracks[best_track_id]
                track.bbox = det.bbox
                track.center = det.center
                track.age = 0
                track.hits += 1
                matched_tracks.add(best_track_id)
                matched_detections.add(det_idx)
                
                # 更新检测对象的id为track_id
                det.id = best_track_id
        
        # 为未匹配的检测创建新轨迹
        for det_idx, det in enumerate(detections):
            if det_idx not in matched_detections:
                track_id = f"track_{self.next_id}"
                self.next_id += 1
                
                self.tracks[track_id] = Track(
                    id=track_id,
                    bbox=det.bbox,
                    center=det.center,
                )
                det.id = track_id
        
        # 增加未匹配轨迹的age
        for track_id in self.tracks:
            if track_id not in matched_tracks:
                self.tracks[track_id].age += 1
        
        # 移除超时的轨迹
        self.tracks = {
            k: v for k, v in self.tracks.items() 
            if v.age < self.max_age
        }
        
        # 返回满足min_hits的轨迹
        return [
            track for track in self.tracks.values() 
            if track.hits >= self.min_hits or track.age == 0
        ]
    
    def reset(self):
        """重置追踪器"""
        self.tracks.clear()
        self.next_id = 1
```

**步骤2: 验证修改**

```bash
cd backend && python -c "from app.core.tracker import SimpleTracker; print('OK')"
```
预期输出: `OK`

**步骤3: Commit**

```bash
git add backend/app/core/tracker.py
git commit -m "feat(tracker): 添加简单的IOU-based多目标追踪器"
```

---

## Task 5: 修改检测处理流程 (backend/app/core/processor.py)

**文件:**
- 修改: `backend/app/core/processor.py` (如果不存在则创建)
- 或者修改现有的视频处理文件

让我先检查现有文件：
```bash
cd backend && find . -name "*.py" | grep -E "(process|monitor)" | head -20
```

**步骤1: 检查并读取现有处理文件**

如果存在视频处理文件，修改它以集成新的检测器、追踪器和状态机。

假设文件是 `backend/app/core/video_processor.py`，修改要点：

```python
"""
视频处理和违规检测主流程
"""

from typing import Optional, List
import cv2
import numpy as np
from datetime import datetime

from app.core.detector import YOLODetector, Detection
from app.core.tracker import SimpleTracker
from app.core.state_machine import StateMachine, PersonState
from app.config.manager import config_manager
from app.services.rabbitmq import rabbitmq_client
from app.services.redis import redis_client


class VideoProcessor:
    """视频处理和违规检测处理器"""
    
    def __init__(self):
        self.detector = YOLODetector()
        self.tracker = SimpleTracker(
            max_age=30,
            min_hits=3,
            iou_threshold=0.3
        )
        self.state_machine = StateMachine()
        self.config = config_manager.get_config()
        
    def process_frame(self, frame: np.ndarray, camera_id: str) -> dict:
        """
        处理单帧视频
        
        Returns:
            处理结果，包含检测、追踪和违规信息
        """
        result = {
            "detections": [],
            "tracks": [],
            "violations": [],
            "frame_info": {
                "camera_id": camera_id,
                "timestamp": datetime.now().isoformat(),
            }
        }
        
        # 1. 检测person_carry
        detections = self.detector.detect(frame)
        result["detections"] = [
            {
                "id": d.id,
                "bbox": d.bbox,
                "confidence": d.confidence,
                "center": d.center,
            }
            for d in detections
        ]
        
        # 2. 更新追踪器
        tracks = self.tracker.update(detections)
        result["tracks"] = [
            {
                "id": t.id,
                "bbox": t.bbox,
                "center": t.center,
                "hits": t.hits,
            }
            for t in tracks
        ]
        
        # 3. 更新状态机并检查违规
        violation_rules = [
            {
                "from_zone": rule.from_zone,
                "to_zone": rule.to_zone,
                "name": rule.name,
            }
            for rule in self.config.violation_rules
            if rule.enabled
        ]
        
        for track in tracks:
            # 确定当前区域
            current_zone = self._get_zone_for_position(track.center)
            
            # 更新状态机
            if track.hits == 1:
                # 新轨迹
                self.state_machine.start_tracking(track.id, current_zone)
            
            self.state_machine.update_position(track.id, track.center, current_zone)
            
            # 检查违规
            violation = self.state_machine.check_violation(track.id, violation_rules)
            if violation:
                result["violations"].append(violation)
                
                # 发送RabbitMQ消息
                self._send_violation_alert(violation, camera_id)
                
                # 重置该轨迹（避免重复报警）
                self.state_machine.reset_track(track.id)
        
        # 4. 清理过期轨迹
        stale_tracks = self.state_machine.cleanup_stale_tracks(timeout_seconds=30)
        if stale_tracks:
            print(f"[Processor] 清理过期轨迹: {stale_tracks}")
        
        return result
    
    def _get_zone_for_position(self, position: tuple) -> Optional[str]:
        """判断位置属于哪个区域"""
        x, y = position
        
        for zone in self.config.zones:
            # 简单的点在多边形内判断
            if self._point_in_polygon(x, y, zone.points):
                return zone.id
        
        return None
    
    def _point_in_polygon(self, x: float, y: float, polygon: List[List[float]]) -> bool:
        """判断点是否在多边形内（射线法）"""
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    def _send_violation_alert(self, violation: dict, camera_id: str):
        """发送违规警报到RabbitMQ"""
        message = {
            "type": "violation",
            "camera_id": camera_id,
            "track_id": violation["track_id"],
            "rule_name": violation["rule_name"],
            "from_zone": violation["from_zone"],
            "to_zone": violation["to_zone"],
            "timestamp": violation["timestamp"],
            "trajectory_summary": violation["trajectory"][-10:] if violation["trajectory"] else [],
        }
        
        try:
            rabbitmq_client.publish(message)
            print(f"[Processor] 违规警报已发送: {violation['rule_name']}")
        except Exception as e:
            print(f"[Processor] 发送违规警报失败: {e}")
```

**步骤2: Commit**

```bash
git add backend/app/core/processor.py
git commit -m "feat(processor): 实现person_carry轨迹追踪和违规检测流程"
```

---

## Task 6: 更新前端参数设置组件 (frontend/src/components/ParamSettings.vue)

**文件:**
- 修改: `frontend/src/components/ParamSettings.vue`

**步骤1: 重写组件**

将文件内容改为：
```vue
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
```

**步骤2: Commit**

```bash
git add frontend/src/components/ParamSettings.vue
git commit -m "feat(frontend): 更新参数设置组件为person_carry配置"
```

---

## Task 7: 更新前端API类型 (frontend/src/api/index.js)

**文件:**
- 修改: `frontend/src/api/index.js`

检查是否需要更新API调用以匹配新的配置结构。

**步骤1: 验证API兼容性**

确保API调用能够正确处理新的配置格式。如果没有特殊类型要求，可能不需要修改。

**步骤2: Commit**

如果需要修改：
```bash
git add frontend/src/api/index.js
git commit -m "chore(frontend): 更新API类型定义适配新配置结构"
```

---

## Task 8: 更新stores中的配置类型 (frontend/src/stores/config.js)

**文件:**
- 修改: `frontend/src/stores/config.js`

**步骤1: 检查并更新默认值**

确保config store中的默认值与新的配置结构匹配。

```javascript
// 检查并更新detectionParams默认值
detectionParams: {
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
```

**步骤2: Commit**

```bash
git add frontend/src/stores/config.js
git commit -m "feat(frontend): 更新config store默认值"
```

---

## Task 9: 整合测试

**步骤1: 创建测试脚本**

创建 `backend/test_person_carry.py`：
```python
"""测试person_carry检测和追踪功能"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.detector import YOLODetector
from app.core.tracker import SimpleTracker
from app.core.state_machine import StateMachine
from app.config.models import ViolationRule
import numpy as np


def test_detector():
    """测试检测器"""
    print("[Test] 测试检测器...")
    
    # 需要实际的模型文件才能测试
    # detector = YOLODetector()
    # frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # detections = detector.detect(frame)
    # print(f"检测到 {len(detections)} 个对象")
    
    print("[Test] 检测器类导入成功 ✓")


def test_tracker():
    """测试追踪器"""
    print("[Test] 测试追踪器...")
    
    tracker = SimpleTracker(max_age=30, min_hits=3, iou_threshold=0.3)
    
    # 模拟检测
    class MockDet:
        def __init__(self, bbox, center):
            self.bbox = bbox
            self.center = center
            self.id = None
    
    detections = [
        MockDet([100, 100, 200, 200], (150, 150)),
        MockDet([300, 300, 400, 400], (350, 350)),
    ]
    
    tracks = tracker.update(detections)
    print(f"第1帧: {len(tracks)} 个轨迹")
    
    # 移动一点位置
    detections2 = [
        MockDet([105, 105, 205, 205], (155, 155)),
        MockDet([305, 305, 405, 405], (355, 355)),
    ]
    
    tracks = tracker.update(detections2)
    print(f"第2帧: {len(tracks)} 个轨迹")
    
    print("[Test] 追踪器测试通过 ✓")


def test_state_machine():
    """测试状态机"""
    print("[Test] 测试状态机...")
    
    sm = StateMachine()
    
    # 模拟规则
    rules = [
        {"from_zone": "zone_a", "to_zone": "zone_b", "name": "A区域到B区域违规"},
    ]
    
    # 开始追踪
    sm.start_tracking("track_1", "zone_a")
    assert sm.get_track("track_1").origin_zone == "zone_a"
    
    # 更新位置
    sm.update_position("track_1", (100, 100), "zone_a")
    
    # 移动到B区域
    sm.update_position("track_1", (500, 500), "zone_b")
    
    # 检查违规
    violation = sm.check_violation("track_1", rules)
    assert violation is not None
    assert violation["from_zone"] == "zone_a"
    assert violation["to_zone"] == "zone_b"
    
    print(f"[Test] 违规检测成功: {violation['rule_name']}")
    print("[Test] 状态机测试通过 ✓")


if __name__ == "__main__":
    test_detector()
    test_tracker()
    test_state_machine()
    print("\n[✓] 所有测试通过！")
```

**步骤2: 运行测试**

```bash
cd backend && python test_person_carry.py
```

预期输出：
```
[Test] 测试检测器...
[Test] 检测器类导入成功 ✓
[Test] 测试追踪器...
第1帧: 2 个轨迹
第2帧: 2 个轨迹
[Test] 追踪器测试通过 ✓
[Test] 测试状态机...
[Test] 违规检测成功: A区域到B区域违规
[Test] 状态机测试通过 ✓

[✓] 所有测试通过！
```

**步骤3: Commit**

```bash
git add backend/test_person_carry.py
git commit -m "test: 添加person_carry追踪功能测试脚本"
```

---

## 总结

完成以上所有任务后，系统将：

1. ✅ 使用自定义YOLO模型检测 `person_carry` 类别
2. ✅ 为每个检测到的对象分配稳定的 `track_id` 进行轨迹追踪
3. ✅ 记录对象的 `origin_zone` 和轨迹历史
4. ✅ 当对象从规则的 `from_zone` 移动到 `to_zone` 时触发违规
5. ✅ 发送RabbitMQ违规消息
6. ✅ 前端配置界面支持person_carry参数设置

**注意事项：**
- 需要准备训练好的 `person_carry.pt` 模型文件
- 建议在实际部署前用真实视频流测试追踪效果
- 可以调整 `iou_threshold`、`max_age`、`min_hits` 参数优化追踪性能

---

## 执行命令

开始执行时，依次运行：

```bash
# Task 1
cd backend && python -c "from app.config.models import *; print('OK')"

# Task 2
cd backend && python -c "from app.core.detector import YOLODetector; print('OK')"

# Task 3
cd backend && python -c "from app.core.state_machine import StateMachine; print('OK')"

# Task 4
cd backend && python -c "from app.core.tracker import SimpleTracker; print('OK')"

# Task 9
cd backend && python test_person_carry.py
```
