#!/usr/bin/env python3
"""报警发送模块：
- local 模式：报警 JSON + 带框结果图本地暂存（alarms/ + results/）
- http 模式：按《罐笼设备图像检测算法结果上传协议 v1.0》POST 推送带标记结果图
- ftp 模式：FTP 回传（旧方案，保留作回退）
发送失败不影响主链路：本地记录保留，可补发。
"""
import json
import logging
import os
import time
from ftplib import FTP, error_perm

import requests

import config

log = logging.getLogger("sender")


def build_push_name(filename, detections):
    """构造推送文件名：原名（去扩展名）+ 事件编码依次追加 + .jpg
    例：20261009..._0000000000.jpg + [G001, G002] -> 20261009..._0000000000_G001_G002.jpg
    """
    base = os.path.splitext(filename)[0]
    codes = []
    for cls_id, *_ in detections:
        code = config.EVENT_CODES.get(config.CLASS_NAMES.get(cls_id, str(cls_id)))
        if code and code not in codes:
            codes.append(code)
    return f"{base}_{'_'.join(codes)}.jpg" if codes else filename


class AlarmSender:
    def __init__(self, mode=None, alarm_dir=None):
        self.mode = mode or config.SEND_MODE
        self.alarm_dir = alarm_dir or config.ALARM_DIR

    # ---------- 报警入口 ----------
    def send_alarm(self, filename, result_path, detections, meta, qc=None, push=True):
        """发送一条报警。
        :param filename:    原始文件名（协议命名，含时间戳等字段）
        :param result_path: 带框结果图绝对路径（与原图同名，存 results 目录）
        :param detections:  [(cls_id, conf, x1, y1, x2, y2), ...]
        :param meta:        从文件名解析出的业务字段 dict
        :param qc:          二次质检结果 dict（可选，None=未质检）
        :param push:        False 时仅本地落盘不推送（质检否决场景）
        """
        push_name = build_push_name(filename, detections)
        record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "filename": filename,
            "push_name": push_name,
            "meta": meta,
            "detections": [
                {"class": config.CLASS_NAMES.get(k, str(k)),
                 "event": config.EVENT_CODES.get(config.CLASS_NAMES.get(k, str(k))),
                 "conf": round(c, 3),
                 "box": [x1, y1, x2, y2]}
                for k, c, x1, y1, x2, y2 in detections
            ],
            "result_image": result_path,
        }
        if qc is not None:
            record["qc"] = qc
        # 1) 本地暂存（回传失败时的兜底与审计）
        rec_path = self._save_local(record, filename)
        # 2) 推送（质检否决时 push=False，仅本地留档）
        if not push:
            log.warning("报警未推送（质检否决或手动抑制），本地记录已保留: %s", push_name)
            return record
        if self.mode == "http":
            self._post_http(push_name, result_path)
        elif self.mode == "ftp":
            self._upload_ftp(rec_path, result_path)
        return record

    # ---------- 本地暂存 ----------
    def _save_local(self, record, filename):
        os.makedirs(self.alarm_dir, exist_ok=True)
        base = os.path.splitext(filename)[0]
        rec_path = os.path.join(self.alarm_dir, base + ".json")
        with open(rec_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        log.info("报警记录已落盘（%d 个目标）: %s", len(record["detections"]), rec_path)
        return rec_path

    # ---------- HTTP 推送（协议 v1.0） ----------
    def _post_http(self, push_name, result_path):
        cfg = config.HTTP_SEND
        url, field = cfg["url"], cfg["field"]
        attempts = cfg["max_retry"] + 1
        for i in range(attempts):
            try:
                with open(result_path, "rb") as f:
                    resp = requests.post(
                        url,
                        files={field: (push_name, f, "application/jpg")},
                        timeout=cfg["timeout"],
                    )
                ok = resp.status_code == 200
                if ok:
                    try:  # 响应体若有 code 字段则一并校验
                        ok = resp.json().get("code", 0) == 0
                    except ValueError:
                        pass
                if ok:
                    log.info("报警已推送 HTTP[%s]: %s", url, push_name)
                    return
                log.error("推送被拒绝（HTTP %s）: %s", resp.status_code, resp.text[:200])
            except Exception as e:
                log.error("HTTP 推送异常: %s", e)
            if i < attempts - 1:
                time.sleep(2)
        log.error("HTTP 推送最终失败（本地记录已保留，可补发）: %s", push_name)

    # ---------- FTP 回传（旧方案回退） ----------
    @staticmethod
    def _ftp_upload_one(ftp, local_path, remote_name):
        """单个文件上传：.uploading 临时名 + RNFR/RNTO 重命名（与收图协议同风格）"""
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {remote_name}.uploading", f)
        ftp.rename(f"{remote_name}.uploading", remote_name)

    def _upload_ftp(self, rec_path, result_path):
        cfg = config.FTP_SEND
        remote_dir = cfg["remote_dir"]
        try:
            ftp = FTP()
            ftp.connect(cfg["host"], cfg["port"], timeout=15)
            ftp.login(cfg["user"], cfg["passwd"])
            ftp.set_pasv(True)
            # 目录不存在则创建（幂等）
            try:
                ftp.mkd(remote_dir)
            except error_perm:
                pass  # 已存在
            ftp.cwd(remote_dir)
            self._ftp_upload_one(ftp, result_path, os.path.basename(result_path))
            self._ftp_upload_one(ftp, rec_path, os.path.basename(rec_path))
            ftp.quit()
            log.info("报警已回传 FTP[%s:%s/%s]: %s",
                     cfg["host"], cfg["port"], remote_dir, os.path.basename(result_path))
        except Exception as e:
            # 回传失败不阻断链路，本地记录保留可补发
            log.error("FTP 回传失败（本地记录已保留）: %s", e)
