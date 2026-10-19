#!/usr/bin/env python3
"""TensorRT 推理封装：引擎加载一次、常驻显存，detect() 返回检测结果"""
import numpy as np
import cv2
import tensorrt as trt
from cuda import cudart

import config


def _ck(err_pair):
    """检查 cudart 返回值（形如 (err, ...) 或 err）"""
    err = err_pair[0] if isinstance(err_pair, tuple) else err_pair
    if isinstance(err, cudart.cudaError_t) and err != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f"CUDA error: {err}")
    return err_pair


class TRTDetector:
    def __init__(self, engine_path=None, conf_th=None, iou_th=None):
        self.conf_th = conf_th if conf_th is not None else config.CONF_TH
        self.iou_th = iou_th if iou_th is not None else config.IOU_TH
        self.size = config.INPUT_SIZE

        logger = trt.Logger(trt.Logger.WARNING)
        with open(engine_path or config.ENGINE_PATH, "rb") as f:
            self.engine = trt.Runtime(logger).deserialize_cuda_engine(f.read())
        if self.engine is None:
            raise RuntimeError(f"引擎反序列化失败: {engine_path}")
        self.context = self.engine.create_execution_context()

        _ck(cudart.cudaSetDevice(0))
        # 建立非默认流，消除 TRT 警告并避免多余同步
        _ck(cudart.cudaStreamCreate())

        # 分配输入输出显存（一次性常驻）
        self._io = {}  # name -> dict(ptr, shape, dtype, size)
        for i in range(self.engine.num_io_tensors):
            name = engine_name = self.engine.get_tensor_name(i)
            shape = tuple(self.engine.get_tensor_shape(name))
            dtype = trt.nptype(self.engine.get_tensor_dtype(name))
            nbytes = int(np.prod(shape)) * np.dtype(dtype).itemsize
            err, ptr = _ck(cudart.cudaMalloc(nbytes))
            self._io[name] = dict(ptr=int(ptr), shape=shape, dtype=dtype, nbytes=nbytes)
            self.context.set_tensor_address(name, int(ptr))
            if self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                self.in_name = name
            else:
                self.out_name = name

        # 生成一个 cuda stream 供执行用
        err, self.stream = _ck(cudart.cudaStreamCreate())

    # ---------- 预处理 ----------
    def _letterbox(self, img):
        h, w = img.shape[:2]
        scale = min(self.size / h, self.size / w)
        nh, nw = int(h * scale), int(w * scale)
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
        top, left = (self.size - nh) // 2, (self.size - nw) // 2
        canvas[top:top + nh, left:left + nw] = resized
        blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        return np.ascontiguousarray(blob), scale, left, top

    # ---------- NMS ----------
    @staticmethod
    def _nms(boxes, scores, iou_th):
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

    # ---------- 推理 ----------
    def detect(self, img_bgr):
        """返回 [(class_id, conf, x1, y1, x2, y2)]，坐标为原图像素坐标"""
        blob, scale, dx, dy = self._letterbox(img_bgr)
        io_in = self._io[self.in_name]

        _ck(cudart.cudaMemcpyAsync(
            io_in["ptr"], blob.ctypes.data, blob.nbytes,
            cudart.cudaMemcpyKind.cudaMemcpyHostToDevice, self.stream))
        if not self.context.execute_async_v3(self.stream):
            raise RuntimeError("TensorRT execute_async_v3 返回 False")
        _ck(cudart.cudaStreamSynchronize(self.stream))

        io_out = self._io[self.out_name]
        out = np.empty(io_out["shape"], dtype=io_out["dtype"])
        _ck(cudart.cudaMemcpyAsync(
            out.ctypes.data, io_out["ptr"], out.nbytes,
            cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost, self.stream))
        _ck(cudart.cudaStreamSynchronize(self.stream))

        # 后处理: (1, 4+nc, N) -> 置信度过滤 + NMS
        pred = out[0]
        boxes_c = pred[:4, :].T          # (N,4) cx,cy,w,h
        scores = pred[4:, :]             # (nc,N)
        cls_ids = scores.argmax(axis=0)
        confs = scores.max(axis=0)
        mask = confs > self.conf_th
        if not mask.any():
            return []

        b = boxes_c[mask]
        cf, cl = confs[mask], cls_ids[mask]
        xy = np.stack([b[:, 0] - b[:, 2] / 2, b[:, 1] - b[:, 3] / 2,
                       b[:, 0] + b[:, 2] / 2, b[:, 1] + b[:, 3] / 2], axis=1)
        keep = self._nms(xy, cf, self.iou_th)
        xy, cf, cl = xy[keep], cf[keep], cl[keep]

        H, W = img_bgr.shape[:2]
        dets = []
        for box, c, k in zip(xy, cf, cl):
            x1 = int(np.clip((box[0] - dx) / scale, 0, W - 1))
            y1 = int(np.clip((box[1] - dy) / scale, 0, H - 1))
            x2 = int(np.clip((box[2] - dx) / scale, 0, W - 1))
            y2 = int(np.clip((box[3] - dy) / scale, 0, H - 1))
            dets.append((int(k), float(c), x1, y1, x2, y2))
        return dets

    @staticmethod
    def draw(img, detections):
        """在图上叠加检测框与标签，返回新图"""
        vis = img.copy()
        for cls_id, conf, x1, y1, x2, y2 in detections:
            name = config.CLASS_NAMES.get(cls_id, str(cls_id))
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(vis, f"{name} {conf:.2f}", (x1, max(y1 - 6, 14)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        return vis


if __name__ == "__main__":
    # 自测：python3 infer.py <图片路径>
    import sys, time
    det = TRTDetector()
    img = cv2.imread(sys.argv[1] if len(sys.argv) > 1
                     else "/home/nvidia/2026/detector/data_in/testset/luoshuan_20261009001147.jpg")
    for i in range(3):  # 首次含预热
        t0 = time.time()
        r = det.detect(img)
        print(f"第{i+1}次: {(time.time()-t0)*1000:.1f}ms 检出{len(r)}个 -> {r}")
