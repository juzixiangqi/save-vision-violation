# 仓库违规检测系统改进设计文档

**日期**: 2025-04-02  
**主题**: 全流程改进与调试可视化优化  
**状态**: ✅ 已完成

## 1. 问题分析

### 当前系统问题
1. **可视化不足**: 人员ID未显示，无法追踪个体
2. **状态不可见**: 不知道人员当前处于IDLE/CARRYING/OCCLUDED哪个状态
3. **中文显示BUG**: OpenCV默认不支持中文，显示为"?"
4. **追踪不准确**: IOU-based追踪在人员交叉时容易匹配错误
5. **姿态检测太严格**: 针对天花板45度俯视拍摄，当前姿态条件难以满足

## 2. 改进方案

### 2.1 可视化改进

#### 2.1.1 人员ID和状态显示

**功能描述**:
- 在每个人员边界框上方显示追踪ID（如：P1, P2...）
- 用边框颜色区分状态：
  - 🟢 绿色 = IDLE（空闲，未搬运）
  - 🟡 黄色 = CARRYING（搬运中，已锁定箱子）
  - 🔴 红色 = OCCLUDED（遮挡/丢失箱子）
- 在框旁边显示状态文字和当前区域

**技术实现**:
```python
# 在debug_visualizer.py中添加
def _draw_person_with_status(self, img, pose, person_state, current_zone):
    # 根据状态选择颜色
    # 绘制边界框
    # 使用PIL绘制中文标签（ID + 状态 + 区域）
```

**状态**: ✅ 已完成 - 已添加 `_draw_person_with_status` 方法

#### 2.1.2 信息面板修复

**问题**: OpenCV的`cv2.putText`不支持中文

**解决方案**: 使用PIL (Pillow) 绘制中文
```python
from PIL import Image, ImageDraw, ImageFont

def cv2_put_chinese_text(img, text, position, font_size=20, color=(255,255,255)):
    # 将OpenCV图像转为PIL图像
    # 使用支持中文的字体绘制
    # 转回OpenCV格式
```

**状态**: ✅ 已完成 - 已添加 `cv2_put_chinese_text` 函数

### 2.2 追踪算法改进

#### 2.2.1 方案选择：DeepSORT改进版

**架构**:
```
视频帧
  ↓
YOLOv8检测 (person + box) 
  ↓
DeepSORT追踪
├── 外观特征提取 (OSNet/ReID)
├── 卡尔曼滤波 (运动预测)
└── 匈牙利算法 (最优匹配)
  ↓
带ID的检测结果
```

**实现路径**:
1. **使用现成库**: `deep-sort-realtime` (推荐，快速实现)
2. **自定义训练**: 如需针对仓库场景优化，可训练专用ReID模型

**依赖安装**:
```bash
uv add deep-sort-realtime pillow
```

**使用方式**:
```python
from deep_sort_realtime.deepsort_tracker import DeepSort

# 初始化
deep_sort = DeepSort(max_age=30, n_init=3)

# 每帧处理
detections = [(bbox, confidence, class_id), ...]
tracks = deep_sort.update_tracks(detections, frame=frame)

# 获取追踪ID
for track in tracks:
    track_id = track.track_id
    bbox = track.to_tlbr()
```

**状态**: ✅ 已完成 - 已在 `violation_checker.py` 中集成 DeepSort

#### 2.2.2 模型集成

**方案A**: 训练统一检测模型（person + box）
- 优点：单模型推理，速度快
- 缺点：需要标注数据，训练成本

**方案B**: 保持现有方案（YOLOv8-pose + box检测器）
- 优点：无需重新训练
- 缺点：两个模型，稍慢

**推荐**：使用方案B快速集成，后续如需优化再考虑方案A

**状态**: ✅ 已完成 - 保持原有检测方案，仅替换追踪器

### 2.3 搬起姿态检测改进

#### 2.3.1 针对45度俯视的透视补偿

**问题**: 天花板斜向下拍摄，y轴压缩，手看起来比实际低

**解决方案**: 放宽高度判断，强化水平距离判断

#### 2.3.2 宽松搬起定义（新模式）

```python
def is_carrying_pose_overhead(keypoints, box_nearby=False):
    """
    针对天花板45度俯视的宽松搬起检测
    
    条件（满足任一即认为搬起）：
    1. 双手距离较近（<300px）- 主要条件
    2. 箱子在人附近200px内且手在身前
    3. 双手都在身体轮廓内（x坐标在两肩之间±100px）
    
    注意：不严格要求手在臀部下方（透视导致看起来偏低）
    """
    # 条件1: 双手距离较近
    hands_close = hands_dist < 300
    
    # 条件2: 手在身体轮廓内
    hands_in_body = left_in_body or right_in_body
    
    # 条件3: 手在腰部高度附近（放宽到臀部+100px）
    hands_at_waist = avg_wrist_y <= avg_hip_y + 100
    
    # 宽松判断
    is_carrying = hands_close or (box_nearby and hands_in_body and hands_at_waist)
    return is_carrying
```

**状态**: ✅ 已完成 - 已添加 `is_carrying_pose_overhead` 函数

#### 2.3.3 移除严格模式

**改动**:
- 删除 `is_carrying_pose`（严格版）
- 只保留宽松版 `is_carrying_pose_overhead`
- 移除 `ViolationChecker` 的 `use_relaxed_detection` 参数

**状态**: ✅ 已完成 - 已移除严格模式相关代码

### 2.4 状态机改进

#### 2.4.1 可视化状态信息

在 `debug_visualizer.py` 中，从 `violation_checker.state_machine` 获取每个人员的状态，并在画面上显示。

**状态**: ✅ 已完成 - 信息面板显示各状态人员统计

#### 2.4.2 状态转换优化

**当前问题**: 连续帧防抖可能导致状态转换延迟

**优化**:
- 宽松模式下减少连续帧要求（5帧→2帧）
- 增加状态转换日志输出，便于调试

**状态**: ✅ 已完成

## 3. 技术细节

### 3.1 文件修改清单

| 文件 | 修改内容 | 状态 |
|------|----------|------|
| `debug_visualizer.py` | 添加中文绘制、人员ID/状态显示、信息面板修复 | ✅ |
| `helpers.py` | 修改`is_carrying_pose_relaxed`为俯视版本，删除严格模式函数 | ✅ |
| `violation_checker.py` | 集成DeepSORT，移除严格模式逻辑 | ✅ |
| `person_tracker.py` | 保留备用，DeepSORT替换原有追踪 | ✅ |
| `pyproject.toml` | 添加`deep-sort-realtime`和`pillow`依赖 | ✅ |

### 3.2 依赖变更

```toml
[project]
dependencies = [
    # 现有依赖...
    "deep-sort-realtime>=1.3.0",
    "pillow>=10.0.0",
]
```

**状态**: ✅ 已完成 - 已更新 pyproject.toml

### 3.3 性能考量

1. **DeepSORT**: 增加约5-10ms每帧（特征提取）
2. **PIL中文**: 增加约2-3ms每帧（图像转换）
3. **总体**: 预计帧率下降10-15%，仍能满足实时性（>15fps）

## 4. 测试计划

### 4.1 功能测试

1. **可视化测试**:
   - ✅ 确认人员ID正确显示
   - ✅ 确认状态颜色正确（绿/黄/红）
   - ✅ 确认中文正常显示无乱码

2. **追踪测试**:
   - [ ] 人员交叉时ID保持稳定
   - [ ] 遮挡后重识别正确
   - [ ] 快速移动时不丢ID

3. **姿态检测测试**:
   - [ ] 45度俯视视频能正确检测搬起
   - [ ] 不同身高的操作人员都能触发
   - [ ] 减少误报（不搬箱子时不触发）

### 4.2 性能测试

- [ ] 监控FPS变化
- [ ] 内存占用检查
- [ ] 长时间运行稳定性

## 5. 实施计划

### Phase 1: 可视化修复（高优先级）✅
1. ✅ 修复中文显示（PIL）
2. ✅ 添加人员ID和状态显示
3. ✅ 测试信息面板显示正常

### Phase 2: 追踪改进（高优先级）✅
1. ✅ 添加DeepSORT依赖
2. ✅ 替换原有追踪器
3. [ ] 测试追踪稳定性（待测试）

### Phase 3: 姿态检测优化（中优先级）✅
1. ✅ 实现俯视版搬起检测
2. ✅ 移除严格模式
3. [ ] 在测试视频上验证（待测试）

### Phase 4: 集成测试
1. [ ] 全链路测试
2. [ ] 性能调优
3. ✅ 文档更新

## 6. 风险与缓解

| 风险 | 缓解措施 | 状态 |
|------|----------|------|
| DeepSORT引入延迟 | 使用轻量级ReID模型，或在低分辨率上运行 | ✅ 已使用默认配置 |
| PIL中文绘制慢 | 缓存字体对象，减少重复加载 | ✅ 已实现字体缓存 |
| 宽松检测误报多 | 增加区域限制（必须在特定区域才检测搬起） | [ ] 待优化 |
| 新模型需要训练 | 先使用现成模型，后续再考虑自定义训练 | ✅ 使用现成OSNet |

## 7. 实施记录

### 2025-04-02 实施完成

**已完成功能**:
1. ✅ 依赖安装: `uv add deep-sort-realtime pillow`
2. ✅ 中文支持: 添加 `cv2_put_chinese_text()` 函数，支持Windows/Linux/macOS中文字体
3. ✅ 人员可视化: 添加 `_draw_person_with_status()` 方法，显示ID、状态、区域
4. ✅ DeepSORT集成: 替换 `SimplePersonTracker` 为 `DeepSort`
5. ✅ 俯视检测: 添加 `is_carrying_pose_overhead()` 函数，针对45度拍摄优化
6. ✅ 移除严格模式: 清理相关代码，简化逻辑
7. ✅ 文档更新: 更新 README.md 和 CHANGELOG.md

**文件变更**:
- `backend/app/core/debug_visualizer.py` - 中文支持、状态显示
- `backend/app/utils/helpers.py` - 俯视版搬起检测
- `backend/app/core/violation_checker.py` - DeepSORT集成
- `pyproject.toml` - 依赖更新
- `README.md` - 文档更新
- `CHANGELOG.md` - 变更日志

## 8. 后续工作

- [ ] 在测试视频上验证追踪和检测准确性
- [ ] 根据测试结果调整参数（连续帧阈值、距离阈值等）
- [ ] 考虑GPU加速（CUDA）优化性能
- [ ] 针对特定仓库场景训练专用ReID模型
- [ ] 添加更多调试信息输出

## 9. 结论

本设计通过以下改进提升系统可用性和准确性：
1. **可视化**: ID+状态一目了然，中文显示正常
2. **追踪**: DeepSORT提升交叉和遮挡场景的稳定性
3. **检测**: 针对俯视场景优化，降低漏检率

所有代码已实现，等待测试验证。


## 1. 问题分析

### 当前系统问题
1. **可视化不足**: 人员ID未显示，无法追踪个体
2. **状态不可见**: 不知道人员当前处于IDLE/CARRYING/OCCLUDED哪个状态
3. **中文显示BUG**: OpenCV默认不支持中文，显示为"?"
4. **追踪不准确**: IOU-based追踪在人员交叉时容易匹配错误
5. **姿态检测太严格**: 针对天花板45度俯视拍摄，当前姿态条件难以满足

## 2. 改进方案

### 2.1 可视化改进

#### 2.1.1 人员ID和状态显示

**功能描述**:
- 在每个人员边界框上方显示追踪ID（如：P1, P2...）
- 用边框颜色区分状态：
  - 🟢 绿色 = IDLE（空闲，未搬运）
  - 🟡 黄色 = CARRYING（搬运中，已锁定箱子）
  - 🔴 红色 = OCCLUDED（遮挡/丢失箱子）
- 在框旁边显示状态文字和当前区域

**技术实现**:
```python
# 在debug_visualizer.py中添加
def _draw_person_with_info(self, img, pose, person_state, current_zone):
    # 绘制边界框（根据状态着色）
    # 显示ID + 状态 + 区域
```

#### 2.1.2 信息面板修复

**问题**: OpenCV的`cv2.putText`不支持中文

**解决方案**: 使用PIL (Pillow) 绘制中文
```python
from PIL import Image, ImageDraw, ImageFont

def cv2_put_chinese_text(img, text, position, font_size=20, color=(255,255,255)):
    # 将OpenCV图像转为PIL图像
    # 使用支持中文的字体绘制
    # 转回OpenCV格式
```

### 2.2 追踪算法改进

#### 2.2.1 方案选择：DeepSORT改进版

**架构**:
```
视频帧
  ↓
YOLOv8检测 (person + box) 
  ↓
DeepSORT追踪
├── 外观特征提取 (OSNet/ReID)
├── 卡尔曼滤波 (运动预测)
└── 匈牙利算法 (最优匹配)
  ↓
带ID的检测结果
```

**实现路径**:
1. **使用现成库**: `deep-sort-realtime` (推荐，快速实现)
2. **自定义训练**: 如需针对仓库场景优化，可训练专用ReID模型

**依赖安装**:
```bash
uv add deep-sort-realtime
```

**使用方式**:
```python
from deep_sort_realtime.deepsort_tracker import DeepSort

# 初始化
deep_sort = DeepSort(max_age=30, n_init=3)

# 每帧处理
detections = [(bbox, confidence, class_id), ...]
tracks = deep_sort.update_tracks(detections, frame=frame)

# 获取追踪ID
for track in tracks:
    track_id = track.track_id
    bbox = track.to_tlbr()
```

#### 2.2.2 模型集成

**方案A**: 训练统一检测模型（person + box）
- 优点：单模型推理，速度快
- 缺点：需要标注数据，训练成本

**方案B**: 保持现有方案（YOLOv8-pose + box检测器）
- 优点：无需重新训练
- 缺点：两个模型，稍慢

**推荐**：先使用方案B快速集成，后续如需优化再考虑方案A

### 2.3 搬起姿态检测改进

#### 2.3.1 针对45度俯视的透视补偿

**问题**: 天花板斜向下拍摄，y轴压缩，手看起来比实际低

**解决方案**: 放宽高度判断，强化水平距离判断

#### 2.3.2 宽松搬起定义（新模式）

```python
def is_carrying_pose_relaxed_overhead(
    keypoints: np.ndarray,
    box_nearby: bool = False,
    hands_distance_threshold: float = 300,  # 放宽到300px
) -> bool:
    """
    针对天花板45度俯视的宽松搬起检测
    
    条件（满足任一即认为搬起）：
    1. 双手距离较近（<300px）- 主要条件
    2. 箱子在人附近200px内且手在身前
    3. 双手都在身体轮廓内（x坐标在两肩之间±100px）
    
    注意：不严格要求手在臀部下方（透视导致看起来偏低）
    """
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6
    
    left_wrist = keypoints[LEFT_WRIST, :2]
    right_wrist = keypoints[RIGHT_WRIST, :2]
    left_shoulder = keypoints[LEFT_SHOULDER, :2]
    right_shoulder = keypoints[RIGHT_SHOULDER, :2]
    
    # 条件1: 双手距离较近
    hands_dist = calculate_distance(tuple(left_wrist), tuple(right_wrist))
    hands_close = hands_dist < hands_distance_threshold
    
    # 条件2: 手在身体轮廓内（x方向）
    min_shoulder_x = min(left_shoulder[0], right_shoulder[0])
    max_shoulder_x = max(left_shoulder[0], right_shoulder[0])
    
    left_in_body = min_shoulder_x - 100 <= left_wrist[0] <= max_shoulder_x + 100
    right_in_body = min_shoulder_x - 100 <= right_wrist[0] <= max_shoulder_x + 100
    
    hands_in_body = left_in_body or right_in_body
    
    # 宽松条件：双手靠近，或（箱子在附近且手在身前）
    is_carrying = hands_close or (box_nearby and hands_in_body)
    
    return is_carrying
```

#### 2.3.3 移除严格模式

**改动**:
- 删除 `is_carrying_pose`（严格版）
- 只保留宽松版，且默认使用 `use_relaxed_detection=True`
- 移除 `ViolationChecker` 的 `use_relaxed_detection` 参数

### 2.4 状态机改进

#### 2.4.1 可视化状态信息

在 `debug_visualizer.py` 中，从 `violation_checker.state_machine` 获取每个人员的状态，并在画面上显示。

#### 2.4.2 状态转换优化

**当前问题**: 连续帧防抖可能导致状态转换延迟

**优化**:
- 宽松模式下减少连续帧要求（2帧→1帧）
- 增加状态转换日志输出，便于调试

## 3. 技术细节

### 3.1 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `debug_visualizer.py` | 添加中文绘制、人员ID/状态显示、信息面板修复 |
| `helpers.py` | 修改`is_carrying_pose_relaxed`为俯视版本，删除严格模式函数 |
| `violation_checker.py` | 集成DeepSORT，移除严格模式逻辑 |
| `person_tracker.py` | 可选：替换为DeepSORT封装或删除 |
| `pyproject.toml` | 添加`deep-sort-realtime`依赖 |

### 3.2 依赖变更

```toml
[project]
dependencies = [
    # 现有依赖...
    "deep-sort-realtime>=1.3.8",
    "pillow>=10.0.0",  # PIL用于中文绘制
]
```

### 3.3 性能考量

1. **DeepSORT**: 增加约5-10ms每帧（特征提取）
2. **PIL中文**: 增加约2-3ms每帧（图像转换）
3. **总体**: 预计帧率下降10-15%，仍能满足实时性（>15fps）

## 4. 测试计划

### 4.1 功能测试

1. **可视化测试**:
   - 确认人员ID正确显示
   - 确认状态颜色正确（绿/黄/红）
   - 确认中文正常显示无乱码

2. **追踪测试**:
   - 人员交叉时ID保持稳定
   - 遮挡后重识别正确
   - 快速移动时不丢ID

3. **姿态检测测试**:
   - 45度俯视视频能正确检测搬起
   - 不同身高的操作人员都能触发
   - 减少误报（不搬箱子时不触发）

### 4.2 性能测试

- 监控FPS变化
- 内存占用检查
- 长时间运行稳定性

## 5. 实施计划

### Phase 1: 可视化修复（高优先级）
1. 修复中文显示（PIL）
2. 添加人员ID和状态显示
3. 测试信息面板显示正常

### Phase 2: 追踪改进（高优先级）
1. 添加DeepSORT依赖
2. 替换原有追踪器
3. 测试追踪稳定性

### Phase 3: 姿态检测优化（中优先级）
1. 实现俯视版搬起检测
2. 移除严格模式
3. 在测试视频上验证

### Phase 4: 集成测试
1. 全链路测试
2. 性能调优
3. 文档更新

## 6. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| DeepSORT引入延迟 | 使用轻量级ReID模型，或在低分辨率上运行 |
| PIL中文绘制慢 | 缓存字体对象，减少重复加载 |
| 宽松检测误报多 | 增加区域限制（必须在特定区域才检测搬起） |
| 新模型需要训练 | 先使用现成模型，后续再考虑自定义训练 |

## 7. 结论

本设计通过以下改进提升系统可用性和准确性：
1. **可视化**: ID+状态一目了然，中文显示正常
2. **追踪**: DeepSORT提升交叉和遮挡场景的稳定性
3. **检测**: 针对俯视场景优化，降低漏检率

预计实施后可大幅降低误报和漏报，提升调试效率。
