#!/usr/bin/env python3
"""主循环：持续遍历 WATCH_DIR，按时间戳取最旧处理，顺次单线程执行
处理链：取最旧 .jpg -> YOLO26 推理 -> 画框存 results -> 报警发送 -> 删除原图
"""
import argparse
import logging
import os
import shutil
import sys
import time

import cv2

import config
from api import ControlAPI
from infer import TRTDetector
from qc import QCClient, qc_switch_on, stop_llama_if_idle
from sender import AlarmSender

os.makedirs("/home/nvidia/2026/detector/logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler("/home/nvidia/2026/detector/logs/pipeline.log")],
)
log = logging.getLogger("pipeline")


def parse_filename(name):
    """按协议解析文件名业务字段；不合规命名返回 None（回退 mtime 排序）"""
    m = config.FILENAME_RE.match(name)
    if not m:
        return None
    ts, robot, task, angle, encoder, reserved = m.groups()
    return {
        "timestamp": ts,
        "robot_id": robot,
        "task_id": task,
        "camera_angle": angle,
        "encoder_pos": encoder,
        "reserved": reserved,
        # 20261009143025123 -> 2026-10-09 14:30:25.123
        "time_str": f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}.{ts[14:17]}",
    }


def sort_key(path):
    """排序键：优先文件名内 17 位时间戳，否则回退文件 mtime（最旧优先）"""
    meta = parse_filename(os.path.basename(path))
    if meta:
        return (0, meta["timestamp"])
    return (1, f"{os.path.getmtime(path):.6f}")


def list_pending(watch_dir):
    """待处理文件列表：只认 .jpg，跳过临时文件和处理中文件"""
    out = []
    try:
        for name in os.listdir(watch_dir):
            if name.endswith(config.TMP_SUFFIX):
                continue
            if name.endswith(config.PROCESSING_SUFFIX):
                continue  # 上次中断遗留的，重启时由 recover 处理
            if name.lower().endswith(config.IMG_EXTS):
                out.append(os.path.join(watch_dir, name))
    except FileNotFoundError:
        os.makedirs(watch_dir, exist_ok=True)
    return out


def recover(watch_dir):
    """启动恢复：上次中断遗留的 .processing 文件改回 .jpg 重新入队"""
    try:
        for name in os.listdir(watch_dir):
            if name.endswith(config.PROCESSING_SUFFIX):
                src = os.path.join(watch_dir, name)
                dst = src[:-len(config.PROCESSING_SUFFIX)]
                os.rename(src, dst)
                log.info("恢复中断文件: %s", name)
    except FileNotFoundError:
        pass


def process_one(path, detector, sender, result_dir, fail_dir, qc_client=None):
    """处理单个文件的完整链路，返回 True=报警 / False=无报警 / None=失败"""
    name = os.path.basename(path)

    # 1. 标记处理中（防重复入队）
    proc_path = path + config.PROCESSING_SUFFIX
    os.rename(path, proc_path)

    # 2. 读取
    img = cv2.imread(proc_path)
    if img is None:
        os.makedirs(fail_dir, exist_ok=True)
        shutil.move(proc_path, os.path.join(fail_dir, name))
        log.error("读图失败，移入 failed: %s", name)
        return None

    # 3. 推理
    t0 = time.time()
    detections = detector.detect(img)
    infer_ms = (time.time() - t0) * 1000

    # 4. 画框 + 存结果（与原图同名，目录区分）
    os.makedirs(result_dir, exist_ok=True)
    result_path = os.path.join(result_dir, name)
    cv2.imwrite(result_path, TRTDetector.draw(img, detections))

    # 5/6. 报警判定 -> 二次质检（热开关控制） -> 发送
    alarm_dets = [d for d in detections if d[0] in config.ALARM_CLASSES]
    if alarm_dets:
        meta = parse_filename(name) or {}
        qc_result, push = None, True
        if qc_client is not None and qc_switch_on():
            qc_result = qc_client.check(proc_path, alarm_dets)
            push = qc_result["passed"] or config.QC_MODE == "record"
        elif qc_client is not None:
            log.info("质检热开关关闭，跳过多模态质检: %s", name)
        sender.send_alarm(name, result_path, alarm_dets, meta,
                          qc=qc_result, push=push)
        if not push:
            log.warning("质检否决，本次报警未推送: %s", name)

    # 7. 清理：处理完删除原图
    os.remove(proc_path)

    log.info("完成 %s：推理 %.1fms 检出 %d 报警 %d",
             name, infer_ms, len(detections), len(alarm_dets))
    return len(alarm_dets) > 0


def run(watch_dir, once=False):
    result_dir = os.path.join(os.path.dirname(watch_dir), "results")
    fail_dir = os.path.join(os.path.dirname(watch_dir), "failed")
    alarm_dir = os.path.join(os.path.dirname(watch_dir), "alarms")
    detector = TRTDetector()
    sender = AlarmSender(alarm_dir=alarm_dir)
    # 质检客户端始终创建（无连接开销），每张图按热开关决定是否调用
    qc_client = QCClient()
    # 统一控制接口（独立守护线程，仅读写参数标志，不影响单线程推理链路）
    ControlAPI(detector, qc_client).start()
    log.info("链路启动：watch=%s result=%s send=%s qc=%s(%s) 开关文件=%s",
             watch_dir, result_dir, config.SEND_MODE,
             "on" if qc_switch_on() else "off", config.QC_MODE,
             config.QC_SWITCH_FILE)
    recover(watch_dir)

    # 启动时资源对齐：精筛关闭则停掉 llama-server 释放显存/内存（按需模式）
    if not qc_switch_on():
        stop_llama_if_idle()

    last_reconcile = time.time()
    while True:
        # 周期兜底（60s）：开关文件被直接改成 off 时也能回收 llama-server
        now = time.time()
        if now - last_reconcile > 60:
            last_reconcile = now
            if not qc_switch_on():
                stop_llama_if_idle()
        files = sorted(list_pending(watch_dir), key=sort_key)
        if not files:
            if once:
                log.info("单次模式：目录已空，退出")
                break
            time.sleep(config.POLL_INTERVAL)
            continue
        oldest = files[0]
        try:
            process_one(oldest, detector, sender, result_dir, fail_dir, qc_client)
        except Exception:
            log.exception("处理异常: %s", oldest)


def main():
    ap = argparse.ArgumentParser(description="罐笼图像检测常驻服务")
    ap.add_argument("--watch-dir", default=config.WATCH_DIR,
                    help="监控目录（默认 %(default)s）")
    ap.add_argument("--once", action="store_true",
                    help="把当前目录处理完即退出（测试用）")
    args = ap.parse_args()
    os.makedirs("/home/nvidia/2026/detector/logs", exist_ok=True)
    run(args.watch_dir, args.once)


if __name__ == "__main__":
    main()
