#!/usr/bin/env python3
"""二次质检模块：Qwen3-VL-2B @ llama.cpp（本地部署，LLM-GPU/ViT-CPU 混合推理）

在 YOLO 检出缺陷后、HTTP 推送前复核：
- 问答模板固定（qc_prompt.txt 文件调入）：开放提问图片存在何种异常，
  回答限定 16 类（15 种缺陷 + 未发现异常），格式"图片场景描述：…，图片存在的异常：…"
- gate 模式：YOLO 检出的事件全部被模型报告才推送（当前 2B 模型确认率偏高，暂不启用）
- record 模式（默认）：复检结论记入报警 JSON，不影响推送
- fail-open：质检服务故障/超时/解析失败一律放行，绝不因质检环节漏报
"""
import base64
import logging
import os
import re
import subprocess
import time
from io import BytesIO

import requests
from PIL import Image

import config

log = logging.getLogger("qc")

LLAMA_SVC = "llama-server"
LLAMA_HEALTH = "http://127.0.0.1:8080/health"


def llama_active():
    """llama-server 服务是否在运行"""
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", LLAMA_SVC],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def ensure_llama_running(wait_s=120):
    """按需模式：精筛需要 llama-server 但服务未运行时自动拉起并等待就绪。
    返回 True=就绪 / False=等待超时（调用方按 fail-open 处理）。"""
    if not config.QC_ON_DEMAND or llama_active():
        return True
    log.info("按需拉起 %s（模型加载约 30~60 秒，期间报警按 fail-open 放行）...", LLAMA_SVC)
    subprocess.run(["sudo", "-n", "systemctl", "start", LLAMA_SVC],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            if requests.get(LLAMA_HEALTH, timeout=2).status_code == 200:
                log.info("%s 已就绪", LLAMA_SVC)
                return True
        except Exception:
            pass
        time.sleep(2)
    log.error("%s 等待就绪超时（%ds）", LLAMA_SVC, wait_s)
    return False


def stop_llama_if_idle():
    """精筛关闭时停掉 llama-server，释放约 2GB 显存/内存（仅按需模式）。"""
    if not config.QC_ON_DEMAND or not llama_active():
        return
    subprocess.run(["sudo", "-n", "systemctl", "stop", LLAMA_SVC],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info("精筛关闭，已停止 %s 释放资源", LLAMA_SVC)

# G 码 -> 算法中文名（协议第 4 节报警事件编号表）
EVENT_CN = {
    "G001": "罐道梁（横）弯曲变形",
    "G002": "罐道梁（横）压板缺失",
    "G003": "罐道（竖）变形",
    "G004": "罐道（竖）破损",
    "G005": "罐道梁支座螺栓缺失",
    "G006": "电缆卡子脱落",
    "G007": "电缆开裂",
    "G008": "风水管路卡子脱落缺失",
    "G009": "风水管路变形",
    "G010": "风水管路滴水",
    "G011": "井底楔形罐道断裂",
    "G012": "井底楔形罐道缺失",
    "G013": "井底楔形罐道固定件脱落",
    "G014": "井壁混凝土裂纹",
    "G015": "井壁表面剥落",
}
# 算法中文名 -> G 码（答案解析用）
NAME_TO_CODE = {v: k for k, v in EVENT_CN.items()}
NONE_FLAG = "未发现异常"

_PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qc_prompt.txt")
with open(_PROMPT_PATH, encoding="utf-8") as _f:
    _prompt_text = _f.read().strip()
# 两阶段模板：以独占一行的 === 分隔（第一段=场景观察，第二段=带 {scene} 的判别模板）
# 无分隔线时整体作为单阶段模板使用（向后兼容）
if "\n===\n" in _prompt_text:
    PROMPT_STAGE1, PROMPT_STAGE2 = [p.strip() for p in _prompt_text.split("\n===\n")]
else:
    PROMPT_STAGE1, PROMPT_STAGE2 = None, _prompt_text


def qc_switch_on():
    """质检热开关：开关文件内容 on/off，每张图处理前读取，即时生效。
    文件缺失或不可读时回退 config.QC_ENABLE 默认策略。"""
    try:
        with open(config.QC_SWITCH_FILE, encoding="utf-8") as f:
            return f.read().strip().lower() != "off"
    except OSError:
        return config.QC_ENABLE


def det_event_codes(detections):
    """[(cls_id, ...)] -> 按出现顺序去重的事件编码列表"""
    codes = []
    for cls_id, *_ in detections:
        code = config.EVENT_CODES.get(config.CLASS_NAMES.get(cls_id, ""), "")
        if code and code not in codes:
            codes.append(code)
    return codes


def parse_answer(answer):
    """解析模板化回答 -> (场景描述, 模型报告的 G 码列表)
    格式：图片场景描述：……，图片存在的异常：……
    """
    scene, anomaly_part = "", answer
    m = re.search(r"图片场景描述[：:](.*?)(?:，|\n|,)?图片存在的异常[：:]", answer, re.S)
    if m:
        scene = m.group(1).strip()
        m2 = re.search(r"图片存在的异常[：:](.*)", answer, re.S)
        if m2:
            anomaly_part = m2.group(1)
    # 在异常段落中匹配 16 类名称（按长度降序避免子串误匹配）
    codes = []
    for name in sorted(NAME_TO_CODE, key=len, reverse=True):
        if name in anomaly_part and NAME_TO_CODE[name] not in codes:
            codes.append(NAME_TO_CODE[name])
    if NONE_FLAG in anomaly_part:
        codes = []
    return scene, codes


class QCClient:
    def __init__(self, url=None, timeout=None):
        self.url = url or config.QC_URL
        self.timeout = timeout or config.QC_TIMEOUT

    def check(self, image_path, detections):
        """对一张检出缺陷的原图做复核。
        :param image_path: 原图路径（用原图而非带框图，避免检测框诱导模型）
        :param detections: [(cls_id, conf, ...), ...] 与 sender 相同结构
        :return: {"passed": bool, "events": [G码], "confirmed": [G码],
                  "scene": str, "answer": str, "latency_ms": int, "model": str}
        """
        yolo_codes = det_event_codes(detections)

        result = {
            "passed": True,              # 默认放行（fail-open）
            "events": yolo_codes,
            "confirmed": [],
            "scene": "",
            "answer": "",
            "latency_ms": 0,
            "model": "qwen3-vl-2b",
        }
        t0 = time.time()
        try:
            # 按需模式：精筛开启但 llama-server 未运行时自动拉起（等就绪，超时 fail-open）
            if not ensure_llama_running():
                raise RuntimeError("llama-server 按需拉起超时")

            def _ask(prompt):
                """单次问答：返回模型回答文本"""
                payload = {
                    "model": "qwen3-vl-2b",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url",
                             "image_url": {"url": self._encode_image(image_path)}},
                        ],
                    }],
                    "max_tokens": config.QC_MAX_TOKENS,
                    "temperature": config.QC_TEMPERATURE,
                }
                r = requests.post(self.url, json=payload, timeout=self.timeout)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()

            if PROMPT_STAGE1 is not None:
                # 两阶段（思维链）：先纯观察描述 -> 再带描述对照类别判别
                scene_raw = _ask(PROMPT_STAGE1)
                answer = _ask(PROMPT_STAGE2.replace("{scene}", scene_raw))
            else:
                answer = _ask(PROMPT_STAGE2)
            result["latency_ms"] = int((time.time() - t0) * 1000)

            result["scene"], result["confirmed"] = parse_answer(answer)
            result["answer"] = answer[:300]
            # gate 判定：YOLO 检出的事件须全部被模型报告
            result["passed"] = all(c in result["confirmed"] for c in yolo_codes)
            log.info("质检 %s（%dms）: 检出%s 模型报告%s",
                     "通过" if result["passed"] else "否决",
                     result["latency_ms"], yolo_codes, result["confirmed"] or ["未发现异常"])
        except Exception as e:
            result["latency_ms"] = int((time.time() - t0) * 1000)
            result["answer"] = f"[质检服务异常，放行] {e}"
            log.error("质检服务异常（放行）: %s", e)
        return result

    @staticmethod
    def _encode_image(image_path):
        """读图 -> 长边等比缩放 -> JPEG base64 data URL"""
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        resize = config.QC_RESIZE
        if max(w, h) > resize:
            scale = resize / max(w, h)
            # 兼容旧版 Pillow：无 Resampling 枚举时回退 Image.LANCZOS
            resample = getattr(Image, "Resampling", Image).LANCZOS
            img = img.resize((int(w * scale), int(h * scale)), resample)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
