#!/usr/bin/env python3
"""全局配置：路径、模型参数、报警类别、发送目标"""

# ============ 目录规划 ============
# 正式部署（FTP 部署后启用，与 vsftpd local_root 对应）
BASE_DIR = "/data/ftp"
WATCH_DIR = BASE_DIR + "/images"     # FTP 落地目录，只认 .jpg，忽略 .uploading
RESULT_DIR = BASE_DIR + "/results"   # 带框结果图（与原图同名）
FAIL_DIR = BASE_DIR + "/failed"      # 无法处理的损坏文件
ALARM_DIR = BASE_DIR + "/alarms"     # 报警记录（JSON，待协议实装后由此发送）

# 本地测试目录（--watch-dir 覆盖时使用）
TEST_BASE = "/home/nvidia/2026/detector"

# ============ 模型 ============
ENGINE_PATH = "/home/nvidia/2026/detector/engine/best_fp16.engine"
INPUT_SIZE = 640
CONF_TH = 0.35
IOU_TH = 0.45

# 类别名（与训练一致）
CLASS_NAMES = {
    0: "jingbi_hntlw", 1: "jingbi_bmbl", 2: "guandao_dl", 3: "guandao_qs",
    4: "guandao_gdjtl", 5: "dianlan_dlkl", 6: "liang_wq", 7: "liang_bx",
    8: "liang_ps", 9: "shu_sd", 10: "shu_bx", 11: "shu_ps",
    12: "luoshuan_qs", 13: "fengshui_glbx", 14: "fengshui_glds",
}
# 报警类别：全部 15 类均上报
ALARM_CLASSES = set(CLASS_NAMES.keys())

# ============ 主循环 ============
POLL_INTERVAL = 1.0        # 目录为空时的轮询间隔（秒）
PROCESSING_SUFFIX = ".processing"  # 处理中的状态后缀
TMP_SUFFIX = ".uploading"  # FTP 临时文件后缀（不处理）
IMG_EXTS = (".jpg",)       # 协议约定小写 .jpg

# 协议文件名正则：17位时间_3位机器人_3位任务_4位角度_4位编码器_10位预留.jpg
import re
FILENAME_RE = re.compile(
    r"^(\d{17})_(\d{3})_(\d{3})_(\d{4})_(\d{4})_(\d{10})\.jpg$"
)

# ============ 发送（报警结果上传，协议 v1.0） ============
# local = 仅本地暂存（alarms/ JSON + results/ 带框图）
# http = 按《罐笼设备图像检测算法结果上传协议 v1.0》POST 推送带标记结果图
# ftp  = FTP 回传（旧方案，保留作回退）
SEND_MODE = "http"

# 报警事件编码：模型类别 -> G 码（协议第 4 节报警事件编号表）
# 注：shu_sd 语义未定暂归 G004，待算法组确认
# G006/G008（电缆/风水管路卡子脱落）已在算法确认文档计划内（第一批），但数据集类别里
# 就没有这两类（文档备注"补光灯坏，采集受阻"，样本未形成标注），待补采后加入训练迭代
EVENT_CODES = {
    "liang_wq":      "G001",  # 罐道梁（横）弯曲变形
    "liang_bx":      "G001",  # 罐道梁（横）变形（已确认归 G001）
    "liang_ps":      "G002",  # 罐道梁（横）压板缺失
    "shu_bx":        "G003",  # 罐道（竖）变形
    "shu_ps":        "G004",  # 罐道（竖）破损
    "shu_sd":        "G004",  # 暂归破损（语义未定，待算法组确认）
    "luoshuan_qs":   "G005",  # 罐道梁支座螺栓缺失
    "dianlan_dlkl":  "G007",  # 电缆开裂
    "fengshui_glbx": "G009",  # 风水管路变形
    "fengshui_glds": "G010",  # 风水管路滴水
    "guandao_dl":    "G011",  # 井底楔形罐道断裂
    "guandao_qs":    "G012",  # 井底楔形罐道缺失
    "guandao_gdjtl": "G013",  # 井底楔形罐道固定件脱落
    "jingbi_hntlw":  "G014",  # 井壁混凝土裂纹
    "jingbi_bmbl":   "G015",  # 井壁表面剥落
}

HTTP_SEND = {
    "url": "http://127.0.0.1:8081/api/ai/alarmevent",  # 上位机接收地址（当前本机测试端，待老师下发后替换）
    "field": "alarmevent",   # multipart 字段名（协议请求示例）
    "timeout": 15,           # 单次推送超时（秒）
    "max_retry": 1,          # 失败重试次数（总尝试 = 1 + max_retry）
}

FTP_SEND = {
    "host": "127.0.0.1",        # 回传目标（当前指向本机 FTP 验证流程，对齐后改实际地址）
    "port": 21,
    "user": "guanlong_ftp",
    "passwd": "<FTP_PASSWORD>",   # 脱敏占位：实际密码按现场 FTP 配置填写，不入公开仓库
    "remote_dir": "return",     # FTP 根下的回传目录
}

# ============ 二次质检（Qwen3-VL @ llama.cpp，本地部署） ============
# 精筛开关有三层控制，优先级从高到低：
#   1. 运行时开关文件 QC_SWITCH_FILE（on/off，热生效，控制接口写的就是它）
#   2. 本文件 QC_ENABLE（开关文件缺失时的默认策略，改后需重启服务）
#   3. 控制接口 curl -X POST http://127.0.0.1:8082/params -d '{"qc":"on"}'（等价于写开关文件）
QC_ENABLE = False         # 默认策略：默认关闭质检，按需开启（开关文件缺失/不可读时生效）
QC_SWITCH_FILE = "/data/ftp/qc_switch.txt"  # 运行时热开关：内容 on/off，
                                            # 每张图处理前读取，无需重启服务即时生效
QC_URL = "http://127.0.0.1:8080/v1/chat/completions"  # llama-server 推理接口
QC_MODE = "record"        # gate = 质检否决则不推送（当前2B模型倾向顺从确认，拦截效果差，暂不启用）
                           # record = 质检结果记入报警JSON作人工复核参考，不影响推送（当前默认）
QC_TIMEOUT = 60           # 单次质检超时（秒），混合推理实测 <10s，留足余量
QC_MAX_TOKENS = 128       # 输出上限：场景一句话 + 异常名称(编码) 列表，实测 48 会截断
QC_RESIZE = 640           # 送检图片长边缩放像素（平衡精度与 token/耗时）
QC_TEMPERATURE = 0.1      # 生成温度（0~1，越低回答越稳定，质检场景建议低温）
QC_ON_DEMAND = True       # llama-server 按需启停：精筛关闭时自动停掉该服务释放显存/内存，
                           # 精筛开启时自动拉起（首次质检需等模型加载约 30~60 秒）

# ============ 服务控制接口（统一调参入口，热生效） ============
# GET  /status 查看运行参数；POST /params 调整（如 {"qc":"off","conf_th":0.4}）
API_PORT = 8082

