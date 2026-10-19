#!/usr/bin/env python3
"""单张图片 TensorRT 推理验证脚本（验证用，非正式链路代码）"""
import sys
import time
import numpy as np
import cv2
import tensorrt as trt
from cuda import cudart

ENGINE_PATH = "/home/nvidia/2026/detector/engine/best_fp16.engine"
CLASS_NAMES = {
    0: 'jingbi_hntlw', 1: 'jingbi_bmbl', 2: 'guandao_dl', 3: 'guandao_qs',
    4: 'guandao_gdjtl', 5: 'dianlan_dlkl', 6: 'liang_wq', 7: 'liang_bx',
    8: 'liang_ps', 9: 'shu_sd', 10: 'shu_bx', 11: 'shu_ps',
    12: 'luoshuan_qs', 13: 'fengshui_glbx', 14: 'fengshui_glds',
}
CONF_TH = 0.35
IOU_TH = 0.45
INPUT_SIZE = 640


def check(err):
    if err[0] != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f"CUDA error: {err}")


def letterbox(img, size=640):
    """等比缩放 + 灰边填充到 size x size，返回 (输入张量, 缩放比, 填充量)"""
    h, w = img.shape[:2]
    scale = min(size / h, size / w)
    nh, nw = int(h * scale), int(w * scale)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    top, left = (size - nh) // 2, (size - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    # BGR->RGB, HWC->CHW, /255
    blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    return np.ascontiguousarray(blob), scale, left, top


def nms_numpy(boxes, scores, iou_th):
    """纯 numpy NMS。boxes: (N,4) xyxy"""
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_th]
    return keep


def main(img_path):
    logger = trt.Logger(trt.Logger.WARNING)
    with open(ENGINE_PATH, 'rb') as f:
        engine_bytes = f.read()
    runtime = trt.Runtime(logger)
    engine = runtime.deserialize_cuda_engine(engine_bytes)
    context = engine.create_execution_context()
    ctx = engine.create_execution_context()  # noqa: F841（占位避免误删）

    # 输入输出绑定
    bindings = []
    for i in range(engine.num_io_tensors):
        name = engine.get_tensor_name(i)
        shape = engine.get_tensor_shape(name)
        dtype = trt.nptype(engine.get_tensor_dtype(name))
        size = abs(int(np.prod(shape)))
        # 分配显存
        check(cudart.cudaSetDevice(0))
        err, d_ptr = cudart.cudaMalloc(size * np.dtype(dtype).itemsize)
        check((err, d_ptr))
        bindings.append(d_ptr)
        if engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
            in_name, in_shape, in_dtype, d_in = name, shape, dtype, d_ptr
            print(f"输入: {name} shape={shape} dtype={dtype}")
        else:
            out_name, out_shape, out_dtype, d_out = name, shape, dtype, d_ptr
            print(f"输出: {name} shape={shape} dtype={dtype}")

    # 读图 + 预处理
    img = cv2.imread(img_path)
    if img is None:
        print(f"读图失败: {img_path}")
        sys.exit(1)
    blob, scale, dx, dy = letterbox(img, INPUT_SIZE)

    # H2D
    check(cudart.cudaSetDevice(0))
    err, = cudart.cudaMemcpy(d_in, blob.ctypes.data,
                             blob.nbytes, cudart.cudaMemcpyKind.cudaMemcpyHostToDevice)
    if err != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f"H2D failed: {err}")
    context.set_tensor_address(in_name, int(d_in))
    context.set_tensor_address(out_name, int(d_out))

    t0 = time.time()
    if not context.execute_async_v3(0):
        raise RuntimeError("execute_async_v3 返回 False")
    # 同步
    err, = cudart.cudaStreamSynchronize(0)
    if err != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f"sync failed: {err}")
    dt = (time.time() - t0) * 1000

    # D2H
    out = np.empty(out_shape, dtype=out_dtype)
    err, = cudart.cudaMemcpy(out.ctypes.data, d_out,
                             out.nbytes, cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost)
    if err != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f"D2H failed: {err}")

    # 后处理: out 形状 (1, 4+nc, N) -> 转置
    pred = out[0]  # (19, 8400)
    boxes_cxcywh = pred[:4, :]      # cx, cy, w, h（640 坐标系）
    scores_all = pred[4:, :]        # (15, 8400)
    cls_ids = scores_all.argmax(axis=0)
    confs = scores_all.max(axis=0)
    mask = confs > CONF_TH
    if not mask.any():
        print(f"\n[{img_path}] 推理耗时 {dt:.1f}ms，无检出（阈值 {CONF_TH}）")
        return

    b = boxes_cxcywh[:, mask].T
    confs_f = confs[mask]
    cls_f = cls_ids[mask]
    # cxcywh -> xyxy（640 坐标）
    xy = np.zeros((len(b), 4), dtype=np.float32)
    xy[:, 0] = b[:, 0] - b[:, 2] / 2
    xy[:, 1] = b[:, 1] - b[:, 3] / 2
    xy[:, 2] = b[:, 0] + b[:, 2] / 2
    xy[:, 3] = b[:, 1] + b[:, 3] / 2
    keep = nms_numpy(xy, confs_f, IOU_TH)
    xy, confs_f, cls_f = xy[keep], confs_f[keep], cls_f[keep]

    print(f"\n[{img_path.split('/')[-1]}] 推理耗时 {dt:.1f}ms，检出 {len(xy)} 个目标:")
    # 映射回原图坐标
    H, W = img.shape[:2]
    for box, cf, cl in zip(xy, confs_f, cls_f):
        x1 = max(0, int((box[0] - dx) / scale))
        y1 = max(0, int((box[1] - dy) / scale))
        x2 = min(W, int((box[2] - dx) / scale))
        y2 = min(H, int((box[3] - dy) / scale))
        name = CLASS_NAMES.get(int(cl), str(cl))
        print(f"  {name:16s} conf={cf:.2f}  box=({x1},{y1},{x2},{y2})")
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(img, f"{name} {cf:.2f}", (x1, max(y1 - 6, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    out_path = "/home/nvidia/2026/detector/data_out/verify_" + img_path.split('/')[-1]
    cv2.imwrite(out_path, img)
    print(f"标注图已存: {out_path}")

    # 释放
    for p in bindings:
        cudart.cudaFree(p)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/home/nvidia/2026/detector/data_in/testset/luoshuan_20261009001147.jpg")
