# 罐笼图像检测服务 README

Jetson Orin NX 边缘检测服务：FTP 收图 → YOLO26 TensorRT fp16 推理 → Qwen3-VL-2B 大模型精筛（可开关）→ 按协议 v1.0 HTTP 推送报警。

设备：Jetson Orin NX，IP `192.168.1.112`。

---

## 一、快速上手

### 1. 服务操作

vsftpd 与 cage-detector 开机自启；llama-server 按需启停（精筛关=自动停止，开=自动拉起）。

```bash
sudo systemctl restart cage-detector          # 日常重启检测服务
systemctl is-active vsftpd cage-detector      # 应 active
systemctl is-active llama-server              # 精筛关闭时 inactive 属正常
```

### 2. 大模型精筛开关（默认关闭）

**方式一：改 config.py（默认策略，推荐）**——`config.py` 精筛段落：

```python
QC_ENABLE = False   # True=默认开启精筛，False=默认关闭（开关文件缺失时生效）
```

改后 `sudo systemctl restart cage-detector` 生效。

llama-server 随精筛状态按需启停：开启时自动拉起（首次模型加载约 1~2 分钟，期间报警
fail-open 正常推送不漏报）；关闭时自动停止，释放约 1.3GB 显存/内存。

**方式二：控制接口热调（临时，重启回退 config 值；一条命令可同时调多个参数）**：

```bash
curl http://127.0.0.1:8082/status                                            # 查看当前参数
curl -X POST http://127.0.0.1:8082/params -d '{"qc":"on"}'                   # 开精筛
curl -X POST http://127.0.0.1:8082/params -d '{"qc":"off","conf_th":0.4}'   # 关精筛 + 热调阈值
```

> 接口只监听本机 127.0.0.1，登录设备后本机执行。qc 状态持久化在
> `/data/ftp/qc_switch.txt`（直接改此文件同样即时生效，接口写的也是它）。

### 3. 快速验证链路（30 秒）

```bash
cd ~/2026/detector && python3 recv_test.py &        # ① 起本机模拟接收端（监听 8081）
curl -T 测试图.jpg ftp://192.168.1.112/images/ --user guanlong_ftp:<FTP密码>    # ② 按协议命名投图
tail -f ~/2026/detector/logs/pipeline.log           # ③ 看日志：推理→质检→推送
```

预期：`/data/ftp/results/` 出带框结果图（与原图同名）、`/data/ftp/alarms/` 出报警 JSON、
`/tmp/recv/` 收到 `原名_G0xx.jpg`（带 G 码推送图）、原图自动删除。

**核对回传报文格式**：接收端自动存档最近一次推送的完整 HTTP 请求原文（请求行、头部、
multipart 结构、文件名、响应）到 `/tmp/recv/last_request.txt`，`cat` 即可对照协议 v1.0 核对。
注意 `/tmp` 重启即清空，recv_test.py 为测试进程非服务，需手动启动。

详细步骤与排查见《报警回传测试步骤_v1.0.docx》。

---

## 二、常用速查

```bash
# 服务与日志
systemctl status cage-detector llama-server
tail -f ~/2026/detector/logs/pipeline.log

# 数据目录
/data/ftp/images/    # 原图入口（处理后自动删除）
/data/ftp/results/   # 带框结果图（与原图同名，不带 G 码）
/data/ftp/alarms/    # 报警 JSON（push_name 字段含带 G 码推送名；永久保留可补发）
/tmp/recv/           # 模拟接收端收到：带 G 码推送图 + last_request.txt 报文存档

# 修改 config.py 后生效
sudo systemctl restart cage-detector
```

**config.py 主要可调参数**（全部带中文注释，改后重启生效；带 ★ 的也可控制接口热调）：

| 参数 | 默认 | 说明 |
|---|---|---|
| ★ QC_ENABLE / qc 开关 | False | 精筛默认策略；运行态看 qc_switch.txt / 接口 |
| ★ CONF_TH / IOU_TH | 0.35 / 0.45 | 检测置信度 / 重叠框阈值（conf_th 调高降误报） |
| ★ QC_TEMPERATURE | 0.1 | 精筛生成温度（0~1，越低越稳定） |
| ★ QC_TIMEOUT / QC_MAX_TOKENS / QC_RESIZE | 60 / 48 / 640 | 精筛超时 / 输出长度 / 送检图分辨率 |
| QC_ON_DEMAND | True | llama-server 随精筛开关按需启停 |
| HTTP_SEND["url"] | 本机测试端 | 上位机实际接收地址（唯一待切换项） |
| SEND_MODE | "http" | 回传方式：http（协议 v1.0）/ ftp（回退） |
| QC_MODE | "record" | record=仅记录 / gate=否决不推送 |
| EVENT_CODES | 15 类 | 模型类别→G 码映射，新类别加一行即接入 |

---

## 三、文档说明

| 文档 | 用途 | 给谁看 |
|---|---|---|
| 报警回传测试步骤_v1.0.docx | 两页版回传测试操作手册：准备→投图→核对→排查 | 现场/测试人员 |
| 检测服务使用说明_v1.0.docx | 服务组成、使用流程、目录结构、统一控制接口、可调整参数表 | 使用者/运维 |
| 罐笼检测服务_beta1_验证报告.md | beta1 版本验证记录：压测数据、G码映射定版、遗留事项 | 内部存档 |
| 系统使用手册_罐笼图像检测.docx | 系统级使用手册 | 交付资料 |
| 罐笼图像检测与报警回传通信协议_V0.1.docx | 自起草通信协议草案（正式协议下发前的版本，第5节以FTP为主，与正式 v1.0 的 HTTP 推送有差异） | 内部参考 |
| 项目文档_罐笼图像检测_20261012.md | 项目开发过程记录 | 内部存档 |

> 正式回传依据是《罐笼设备图像检测算法结果上传协议 v1.0》（老师下发，仅存本地 `~/2026/data/`）。
>
> **公开仓库脱敏说明**：4 份内部 docx（上表前两行 + 系统使用手册 + 协议草案）与 FTP 实际密码不入本仓库，
> 仅保留在设备本地；`ftp_secret.txt`（reboot_verify.sh 用的 FTP 密码文件）同样被 git 忽略。

## 四、注意事项

- 检测链路单线程串行、最旧优先，禁止改并发（统一内存平台易 OOM）
- 回传失败不阻断主链路，报警记录永久保留在 alarms/
- 新算法类别接入：`config.py` 的 CLASS_NAMES 与 EVENT_CODES 各加一行，换新引擎后重启服务
- 切换实际上位机地址：改 `config.py` 的 `HTTP_SEND["url"]` 后重启（当前指向本机测试端 8081）
- llama-server 按需启停依赖 `/etc/sudoers.d/llama-ondemand`（放行 systemctl start/stop llama-server 免密），换机部署需带上此配置

## 五、代码与脚本说明

| 文件 | 说明 |
|---|---|
| pipeline.py | 主服务入口：目录轮询、单线程串行调度、恢复中断文件 |
| config.py | 全部配置：路径、阈值、G码映射 EVENT_CODES、HTTP_SEND、质检参数 |
| infer.py | TensorRT 推理封装（best_fp16.engine） |
| qc.py + qc_prompt.txt | 大模型精筛：固定问答模板（16 类约束）、llama-server 按需启停逻辑 |
| api.py | 统一控制接口（8082）：参数查询与热调、qc 开关联动 llama |
| sender.py | 报警推送：HTTP multipart（协议 v1.0）/ FTP 回退，本地 JSON 兜底 |
| recv_test.py | 本机模拟接收端（仅测试用，非服务；自动存档请求报文到 last_request.txt） |
| reboot_verify.sh | 断电重启验证脚本：`./reboot_verify.sh check / reboot / verify` 三步 |
| gen_beta_docs.py | 重新生成上面两份 Word 文档（在哪台机器跑就写哪台的 IP，改完重跑即可） |
| gen_protocol_doc.py / gen_topology.py | 协议草案文档与拓扑图生成脚本 |
| engine/best_fp16.engine | TRT fp16 推理引擎（同规格设备可直接复用） |
| models/best.onnx | 引擎源模型（引擎重建用：trtexec --onnx → --saveEngine） |
