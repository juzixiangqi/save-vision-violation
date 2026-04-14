# 箱子轨迹追踪功能实现总结

## 完成的修改

### 1. `backend/app/core/violation_checker.py`

#### 新增属性（__init__ 中）
- `box_tracker`: ByteTrack 追踪器实例，用于追踪箱子
- `box_trajectories`: Dict[str, List[Tuple[float, float]]] - 追踪ID到轨迹点的映射
- `box_id_mapping`: Dict[str, str] - 原始检测ID到追踪ID的映射

#### 修改的方法
- **`process_frame`**: 
  - 现在返回三元组：`(violations, track_to_pose_mapping, box_tracking_info)`
  - 使用 `_track_boxes_with_byte_track` 方法追踪所有检测到的箱子
  - 在搬运检测中使用追踪后的箱子ID
  - 记录被搬运箱子的轨迹
  - 构建并返回箱子追踪信息字典

#### 新增的方法
- **`_track_boxes_with_byte_track(boxes)`**: 
  - 使用 ByteTrack 追踪器追踪所有箱子
  - 返回追踪后的箱子列表和原始ID到追踪ID的映射
  - 匹配逻辑基于IoU和距离

- **`_compute_iou(box1, box2)`**:
  - 计算两个边界框的IoU（交并比）
  - 用于追踪匹配

- **`_record_box_trajectory(box_id, tracked_boxes)`**:
  - 记录被搬运箱子的轨迹
  - 限制轨迹长度为最近30个点

### 2. `backend/app/core/debug_visualizer.py`

#### 修改的方法
- **`draw_detections`**: 
  - 新增参数 `box_tracking_info: Dict` - 箱子追踪信息
  - 如果只显示被搬运的箱子，使用箱子追踪信息中的 `carried_box_ids`
  - 为被搬运的箱子绘制轨迹线

#### 新增的方法
- **`_draw_box_trajectory(img, trajectory, color)`**:
  - 绘制箱子的运动轨迹
  - 使用渐变透明度和线条粗细显示轨迹历史
  - 每隔3个点绘制一个轨迹点

#### 修改的方法
- **`process_video_frame_debug`**:
  - 更新为接收新的返回值三元组
  - 传递 `box_tracking_info` 给 `draw_detections`

### 3. `backend/app/api/debug_stream.py`

#### 修改的方法
- **`process_frame_sync`**:
  - 更新为返回五元组：`(processed_frame, poses, boxes, violations, box_tracking_info)`
  - 传递 `box_tracking_info` 给可视化器

- **`process_video_stream`**:
  - 接收新的返回值 `box_tracking_info`

- **`do_detection` (在 debug-frame 端点中)**:
  - 接收所有返回值，包括 `box_tracking_info`

## 功能特点

1. **稳定的箱子ID追踪**: 使用 ByteTrack 算法，基于IoU和距离匹配，确保同一箱子在不同帧间保持相同的追踪ID

2. **轨迹记录**: 只记录被搬运箱子的轨迹，节省内存和处理资源

3. **可视化增强**: 
   - 只显示被搬运箱子的边界框（黄色）和轨迹
   - 违规箱子显示为红色
   - 轨迹线使用渐变效果，最新的点更亮、更粗

4. **向后兼容**: 如果没有箱子追踪信息，可视化器会回退到旧的行为

## 测试结果

所有测试均通过：
- ✓ 箱子追踪功能测试
- ✓ 区域管理器测试
- ✓ 状态机测试

## 使用方式

修改后的代码会自动在检测流程中使用：
1. 检测箱子
2. 使用 ByteTrack 追踪箱子分配稳定ID
3. 检测搬运事件（使用追踪后的箱子ID）
4. 记录被搬运箱子的轨迹
5. 在可视化中显示被搬运箱子的轨迹
