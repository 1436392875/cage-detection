#!/usr/bin/env python3
"""检测服务统一控制接口（本地 HTTP，127.0.0.1:8082）

常驻服务运行期间可通过 curl 即时查看与调整，无需重启：
  查看状态：  curl http://127.0.0.1:8082/status
  质检开关：  curl -X POST http://127.0.0.1:8082/params -d '{"qc":"off"}'
  调整阈值：  curl -X POST http://127.0.0.1:8082/params -d '{"conf_th":0.4}'

设计说明：
- 独立守护线程承载 HTTP，只读写参数标志，不触碰推理链路（主循环仍单线程串行）
- qc 开关持久化到开关文件（重启后保持），其余参数为运行时热调、重启后回退 config.py
"""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
from qc import ensure_llama_running, qc_switch_on, stop_llama_if_idle

log = logging.getLogger("api")


class ControlAPI:
    """参数控制中心：持有 detector/qc_client 引用，实现热参数读写
    qc 开关切换时联动 llama-server（按需模式）：开=后台预热拉起，关=停止释放资源"""

    def __init__(self, detector, qc_client):
        self.detector = detector
        self.qc_client = qc_client
        self.lock = threading.Lock()

    def status(self):
        with self.lock:
            return {
                "qc": "on" if qc_switch_on() else "off",
                "conf_th": self.detector.conf_th,
                "iou_th": self.detector.iou_th,
                "qc_timeout": self.qc_client.timeout,
                "qc_max_tokens": config.QC_MAX_TOKENS,
                "qc_resize": config.QC_RESIZE,
                "qc_temperature": config.QC_TEMPERATURE,
                "qc_mode": config.QC_MODE,
                "send_mode": config.SEND_MODE,
                "http_url": config.HTTP_SEND["url"],
            }

    @staticmethod
    def _apply_qc(v):
        """qc 开关落盘 + llama-server 联动（按需模式）"""
        with open(config.QC_SWITCH_FILE, "w", encoding="utf-8") as f:
            f.write(v)
        if v == "on":
            # 后台预热拉起（不阻塞接口响应，加载约 30~60 秒）
            threading.Thread(target=ensure_llama_running, daemon=True,
                             name="llama-prewarm").start()
        else:
            stop_llama_if_idle()

    def set_params(self, params):
        """应用一组热参数，返回 (已应用dict, 未知键list, 错误list)"""
        applied, unknown, errors = {}, [], []
        with self.lock:
            for k, v in params.items():
                try:
                    if k == "qc":
                        if v not in ("on", "off"):
                            raise ValueError("qc 只接受 on/off")
                        self._apply_qc(v)
                    elif k == "conf_th":
                        self.detector.conf_th = float(v)
                    elif k == "iou_th":
                        self.detector.iou_th = float(v)
                    elif k == "qc_timeout":
                        self.qc_client.timeout = int(v)
                    elif k == "qc_max_tokens":
                        config.QC_MAX_TOKENS = int(v)
                    elif k == "qc_resize":
                        config.QC_RESIZE = int(v)
                    elif k == "qc_temperature":
                        t = float(v)
                        if not 0 <= t <= 1:
                            raise ValueError("温度须在 0~1 之间")
                        config.QC_TEMPERATURE = t
                    else:
                        unknown.append(k)
                        continue
                    applied[k] = v
                except (TypeError, ValueError, OSError) as e:
                    errors.append(f"{k}: {e}")
        if applied:
            log.info("控制接口热调参数: %s", applied)
        return applied, unknown, errors

    def make_handler(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.startswith("/status"):
                    self._send(200, {"code": 0, "data": api.status()})
                else:
                    self._send(404, {"code": 1, "msg": f"未知路径 {self.path}"})

            def do_POST(self):
                if not self.path.startswith("/params"):
                    self._send(404, {"code": 1, "msg": f"未知路径 {self.path}"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    params = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(params, dict):
                        raise ValueError("请求体须为 JSON 对象")
                except (ValueError, json.JSONDecodeError) as e:
                    self._send(400, {"code": 1, "msg": f"参数解析失败: {e}"})
                    return
                applied, unknown, errors = api.set_params(params)
                resp = {"code": 0, "applied": applied, "data": api.status()}
                if unknown:
                    resp["unknown"] = unknown
                if errors:
                    resp["errors"] = errors
                self._send(200, resp)

            def log_message(self, fmt, *args):
                pass  # 访问日志走统一 logging

        return Handler

    def start(self, host="127.0.0.1", port=None):
        port = port or config.API_PORT
        srv = ThreadingHTTPServer((host, port), self.make_handler())
        t = threading.Thread(target=srv.serve_forever, daemon=True, name="control-api")
        t.start()
        log.info("控制接口就绪: http://%s:%d (GET /status, POST /params)", host, port)
        return srv
