# -*- coding: utf-8 -*-
"""生成《罐笼图像检测与报警回传通信协议》Word 文档
后续每节新增/修订后重跑本脚本即可更新文档。
"""
import subprocess

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

OUT = '/home/nvidia/2026/detector/罐笼图像检测与报警回传通信协议_V0.1.docx'
TOPO_PNG = '/home/nvidia/2026/detector/doc_assets/topology.png'


def device_ip():
    """自动探测本机 IP：在哪台设备上运行，文档里就写哪台的地址"""
    try:
        return subprocess.check_output(["hostname", "-I"]).decode().split()[0]
    except Exception:
        return "127.0.0.1"


IP = device_ip()
IP_OCTETS = IP.replace(".", ",")  # FTP 被动模式响应中的 IP 逗号格式

doc = Document()

# ---------- 全局样式 ----------
normal = doc.styles['Normal']
normal.font.name = 'Times New Roman'
normal.font.size = Pt(10.5)
normal.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
normal.paragraph_format.line_spacing = 1.3

for name, size in [('Heading 1', 16), ('Heading 2', 13), ('Heading 3', 11.5)]:
    st = doc.styles[name]
    st.font.name = 'Arial'
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = RGBColor(0, 0, 0)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')


def para(text, bold=False, size=10.5, align=None, space_after=6):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    r.font.name = 'Times New Roman'
    r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    if align:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    return p


def bullet(text, level=0):
    p = doc.add_paragraph(style='List Bullet' if level == 0 else 'List Bullet 2')
    r = p.add_run(text)
    r.font.size = Pt(10.5)
    r.font.name = 'Times New Roman'
    r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    p.paragraph_format.space_after = Pt(3)
    return p


def make_table(headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = ''
        r = cell.paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(10)
        r.font.name = 'Times New Roman'
        r._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
        # 表头底色
        shd = cell._tc.get_or_add_tcPr().makeelement(qn('w:shd'), {qn('w:val'): 'clear', qn('w:fill'): 'D9E2F3'})
        cell._tc.get_or_add_tcPr().append(shd)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ''
            r = cells[i].paragraphs[0].add_run(str(v))
            r.font.size = Pt(9.5)
            r.font.name = 'Times New Roman'
            r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    return t


# ---------- 封面区 ----------
para('罐笼图像检测与报警回传通信协议', bold=True, size=20, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
para('（草案 V0.1）', size=12, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)

make_table(['项目', '内容'], [
    ['文档名称', '罐笼图像检测与报警回传通信协议'],
    ['版本', 'V0.1（草案，持续修订中）'],
    ['编制日期', '2026-10-13'],
    ['适用系统', '罐笼巡检机器人图像检测系统（边缘检测服务器）'],
    ['状态', '待评审 / 回传目标与承载方式待对齐'],
], widths=[3.5, 12.5])

doc.add_paragraph()
para('版本变更记录', bold=True, size=11.5)
make_table(['版本', '日期', '说明'], [
    ['V0.1', '2026-10-13', '初稿全文：第 1~7 节及附录（回传目标参数待对齐、类别中文含义待算法组确认）'],
], widths=[2.2, 3.2, 10.6])

doc.add_page_break()

# ========== 第 1 节 ==========
doc.add_heading('1  目的与适用范围', level=1)

doc.add_heading('1.1  编制目的', level=2)
para('本协议规定罐笼巡检机器人图像检测系统中"图片上传 → 缺陷检测 → 报警回传"全链路的通信约定，内容包括：FTP 连接参数、账户认证、上传路径、文件命名、传输流程、完整性检查与异常处理；边缘检测服务器的处理行为与时序承诺；报警结果的回传内容、文件格式与可靠性保障。')
para('本协议编制的直接原因：')
bullet('现行《面阵相机图片传输通信协议（V1.0）》仅覆盖"相机 → 服务器"的图片上传单向链路，未定义服务器侧的检测行为与报警输出；')
bullet('现行《智慧煤矿AI边缘计算服务器消息推送接口文档（v5.20）》定义了平台侧 18 类既有算法（安全帽、火焰、皮带等）的消息推送接口，尚未包含罐笼巡检相关算法；')
bullet('本协议作为上述两个文档的扩展与衔接，填补罐笼图像检测链路的规范空白，使三方（相机端、边缘端、平台端）开发有统一依据。')

doc.add_heading('1.2  系统背景', level=2)
para('罐笼巡检机器人搭载面阵相机沿井筒升降采集图像，经本系统实现对悬吊装置、罐笼本体、平衡锤、提升钢丝绳/尾绳、井筒配套装备五大类关键对象的自动化缺陷检测。按《罐笼设备图像检测算法确认（2026-9-2）》[2]，第一批交付 7 个检测项、15 种检测算法：罐道梁异常 2 种、罐道异常 2 种、支座螺栓异常 1 种、电缆异常 2 种、风水管路异常 3 种、井底楔形罐道异常 3 种、井壁状态异常 2 种。检测能力部署于井口侧 AI 边缘计算服务器，各算法的缺陷类别编码见第 4 节。')

doc.add_heading('1.3  协议覆盖范围', level=2)
para('本协议覆盖以下三部分，超出范围的内容不在本协议约定：')
make_table(['部分', '链路方向', '内容', '对应章节'], [
    ['图片上传', 'FTP Client → 边缘检测服务器', '连接参数、命名、传输流程（沿用面帧协议 V1.0）', '第 3 节'],
    ['检测行为', '边缘检测服务器内部', '处理顺序、实时性、文件生命周期', '第 4 节'],
    ['报警回传', '边缘检测服务器 → 平台', '触发条件、报文格式、可靠性', '第 5 节'],
], widths=[2.6, 5.0, 6.0, 2.4])

doc.add_heading('1.4  参照文档', level=2)
make_table(['编号', '文档名称', '版本', '关系'], [
    ['[1]', '面阵相机图片传输通信协议', 'V1.0', '上传链路直接引用'],
    ['[2]', '罐笼设备图像检测算法确认', '2026-9-2', '类别与算法依据'],
    ['[3]', '智慧煤矿AI边缘计算服务器消息推送接口文档', 'v5.20', '回传风格参照'],
    ['[4]', '本协议', 'V0.1（草案）', '—'],
], widths=[1.4, 8.0, 2.6, 4.0])

doc.add_heading('1.5  术语与定义', level=2)
make_table(['术语', '定义'], [
    ['罐笼', '矿井提升系统中运载人员/物料的容器，本系统检测对象载体'],
    ['巡检机器人', '搭载面阵相机、沿井筒升降采集图像的机器人，本协议中的 FTP Client'],
    ['边缘检测服务器', '部署于井口侧的 AI 边缘计算服务器，兼具 FTP Server（收图）与回传 Client（报警推送）两个角色'],
    ['检测算法', '检测服务可输出的缺陷类别判定能力，第一批共 15 种'],
    ['结果图', '在原图上叠加检测框与类别标注的 JPG，与原图同名'],
    ['报警', '检出任意缺陷类别即触发，一次报警产生一份回传报文'],
    ['回传', '边缘检测服务器将报警结果推送至平台侧的动作'],
    ['原子重命名', '先以临时文件名上传、完成后 RNFR/RNTO 改名，保证接收方只见完整文件'],
], widths=[3.6, 12.4])

doc.add_heading('1.6  适用对象', level=2)
para('机器人相机端开发人员、边缘检测服务器开发与运维人员、平台接收端开发人员，以及现场联调与验收人员。')

doc.add_page_break()

# ========== 第 2 节 ==========
doc.add_heading('2  系统角色与拓扑', level=1)

doc.add_heading('2.1  通信角色', level=2)
para('本系统包含三个通信角色，各角色承载实体与职责约定如下：')
make_table(['角色', '承载实体', '主要职责'], [
    ['FTP Client\n（图片上传端）', '罐笼巡检机器人\n（面阵相机 / 图片上传工具）',
     '按文件命名规范（第 3.2 节）采集井筒及罐笼图像并上传至边缘检测服务器 /images 目录；上传采用被动模式、二进制类型，以 .uploading 临时文件名上传、完成后原子重命名'],
    ['边缘检测服务器', 'AI 边缘计算服务器\n（FTP 服务 + 检测服务）',
     '接收图片；按时间戳最旧优先、单线程串行执行 15 种检测算法；生成与原图同名的带标记结果图；检出缺陷即产生报警并回传；本地留存全部记录'],
    ['平台接收端\n（报警回传目标）', '矿方监管平台',
     '接收边缘检测服务器回传的带标记结果图与报警记录并入库展示；地址与承载方式见第 5 节（待对齐）'],
], widths=[3.4, 4.4, 8.2])
para('注：边缘检测服务器在同一设备上同时承担 FTP Server（链路①）与回传 Client（链路②）两个通信角色，两个角色相互独立、互不干扰；任一角色故障不影响另一角色既有连接。', size=9.5)

doc.add_heading('2.2  系统拓扑与数据流向', level=2)
doc.add_picture(TOPO_PNG, width=Cm(16.5))
doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
para('图 2-1  系统拓扑与数据流向', size=9, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)

para('数据流向按链路编号说明如下：')
bullet('链路①（图片上传）：相机采集图像 → 以 .uploading 临时名上传至边缘检测服务器（FTP 控制端口 21，被动模式，数据端口 30000-30100）→ RNFR/RNTO 原子重命名为最终 .jpg 文件，落入 /images 目录；')
bullet('内部处理（检测）：检测服务持续监听 /images 目录，按文件名时间戳最旧优先逐张串行处理：原图解码 → 执行 15 种检测算法 → 生成带标记结果图（与原图同名，存入 /results）；')
bullet('链路②（报警回传）：检出任意缺陷类别即触发报警，回传带标记结果图与报警记录至平台接收端；无缺陷的图片不回传（详见第 4、5 节）；')
bullet('本地留存：结果图留存于 /results，报警记录留存于 /alarms，无法解码的异常图片移入 /failed，原图在处理完成后自动清理。')

doc.add_heading('2.3  边缘检测服务器目录约定', level=2)
make_table(['目录\n（FTP 根相对路径）', '用途', '读写方', '生命周期'], [
    ['/images', '收图入口，仅存放待处理原图', '上传端写；\n检测服务读、删', '原图处理完成后自动删除，目录保持清空'],
    ['/results', '带标记结果图（与原图同名）', '检测服务写', '长期留存'],
    ['/alarms', '报警记录（JSON 格式，字段定义见第 5 节）', '检测服务写', '长期留存，作为回传兜底，支持事后补传'],
    ['/failed', '无法解码等异常图片', '检测服务写', '长期留存，待人工排查'],
    ['/return', '回传暂存区（回传承载为 FTP 方式时使用）', '检测服务写', '回传成功后留存'],
], widths=[3.2, 5.6, 3.2, 4.0])
para('注 1：/return 仅在链路②承载方式为 FTP 上传时使用；若最终采用 HTTP 推送（见第 5 节），该目录保留作本地暂存，不影响协议其他部分。', size=9.5)
para(f'注 2：服务器 IP 地址测试环境为 {IP}，现场部署 IP 以矿方网络规划为准，部署时更新本表及第 3 节参数。', size=9.5)

doc.add_page_break()

# ========== 第 3 节 ==========
doc.add_heading('3  图片上传协议', level=1)
para('本章约定链路①（FTP Client → 边缘检测服务器）的连接参数与文件规范。除 3.4 节明确的服务端容错策略外，本章内容沿用《面阵相机图片传输通信协议（V1.0）》[1]，两文档不一致时以本协议为准。')

doc.add_heading('3.1  连接参数', level=2)
make_table(['项目', '约定', '说明'], [
    ['通信角色', 'FTP Client → FTP Server', '客户端（机器人相机）主动发起连接并上传图片'],
    ['传输模式', '被动模式（PASV）', '便于客户端穿越防火墙及 NAT'],
    ['文件类型', '二进制 TYPE I', '禁止使用 ASCII 模式传输图片'],
    ['控制端口', '21', '可由配置修改'],
    ['被动数据端口', '30000-30100', '服务器防火墙需放行该端口段'],
    ['字符集', 'UTF-8', '文件名仅使用 ASCII 数字、下划线和小写扩展名'],
    ['最终扩展名', '.jpg', '大小写敏感，统一使用小写'],
    ['上传目录', '/images', 'FTP URL 中的远端逻辑目录'],
    ['用户名', 'guanlong_ftp', '专用上传账户'],
    ['密码', '<FTP密码>', '实际值见现场配置，不入公开仓库；普通 FTP 为明文传输，仅限隔离工业内网使用'],
    ['服务器地址', f'{IP}（测试环境）', '现场部署 IP 以矿方网络规划为准，部署时更新'],
    ['FTP URL', 'ftp://<服务器IP>/images', '客户端上传目标地址'],
], widths=[3.4, 5.6, 7.0])

doc.add_heading('3.2  文件命名协议', level=2)
para('最终文件名由六个业务字段组成，字段之间使用下划线分隔；除时间字段外，各字段宽度均固定，字段不足位数时在左侧补零：')
make_table(['序号', '字段', '宽度', '示例格式', '数据类型', '说明'], [
    ['1', '时间', '17', 'YYYYMMDDhhmmssSSS', 'DateTime', '本地采集时间，精确到毫秒，24 小时制'],
    ['2', 'Robot ID', '3', '001', 'int', '固定 3 位十进制数字，取值范围 000-999'],
    ['3', 'Task ID', '3', '042', 'int', '固定 3 位十进制数字，取值范围 000-999'],
    ['4', '相机角度', '4', '0900', 'int', '固定 4 位十进制数字，取值范围 0000-4500'],
    ['5', '编码器位置', '4', '1234', 'unsigned int', '实际位置×10（单位米），固定 4 位无符号整数'],
    ['6', '预留字段', '10', '固定填 0', '—', '当前版本全部为字符 0'],
], widths=[1.2, 2.6, 1.4, 3.6, 2.4, 4.8])
para('完整文件名示例：', bold=True)
p = doc.add_paragraph()
r = p.add_run('20261009143025123_007_042_0900_1234_0000000000.jpg')
r.font.name = 'Consolas'
r.font.size = Pt(10)
p.paragraph_format.space_after = Pt(6)
para('该文件表示：采集时间为 2026-10-09 14:30:25.123，Robot ID 为 007，Task ID 为 042，相机角度为 0900，编码器位置 1234，预留字段未使用。')

doc.add_heading('3.3  临时文件与原子重命名', level=2)
bullet('远端临时文件名为"<最终文件名>.uploading"；')
bullet('客户端开始上传前，尝试删除同名遗留临时文件；')
bullet('上传成功后使用 RNFR/RNTO 将临时文件重命名为最终 .jpg 文件；')
bullet('服务器业务程序只处理以 .jpg 结尾的最终文件，对 .uploading 临时文件不读取、不删除。')

doc.add_heading('3.4  服务端命名容错策略', level=2)
para('为保证不漏检，检测服务对不符合 3.2 节命名规范的 .jpg 文件采取容错处理而非拒收：')
make_table(['文件命名情况', '服务端处理策略'], [
    ['符合 3.2 节规范', '正常处理：按时间戳字段参与最旧优先排序，业务字段写入报警记录（见 5.4 节）'],
    ['不符合规范（仍为小写 .jpg）', '容错处理：照常执行检测，按文件落盘时间参与排序，报警记录中业务字段为空，并记录告警日志'],
    ['.uploading / .processing 后缀', '不处理（分别由客户端清理和服务端状态管理）'],
], widths=[6.0, 10.0])

doc.add_heading('3.5  上传会话示例与状态码', level=2)
para('请求地址：', bold=True)
p = doc.add_paragraph()
r = p.add_run('ftp://<服务器IP>/images')
r.font.name = 'Consolas'
r.font.size = Pt(10)
p.paragraph_format.space_after = Pt(6)
para('请求示例（FTP 会话命令序列，C 为客户端命令，S 为服务器响应）：', bold=True)
ftp_up = (
    'C: USER guanlong_ftp\n'
    'S: 230 Login successful.\n'
    'C: TYPE I\n'
    'S: 200 Switching to Binary mode.\n'
    'C: PASV\n'
    f'S: 227 Entering Passive Mode ({IP_OCTETS},117,48).\n'
    'C: STOR 20261009143025123_007_042_0900_1234_0000000000.jpg.uploading\n'
    'S: 226 Transfer complete.\n'
    'C: RNFR 20261009143025123_007_042_0900_1234_0000000000.jpg.uploading\n'
    'S: 350 Ready for RNTO.\n'
    'C: RNTO 20261009143025123_007_042_0900_1234_0000000000.jpg\n'
    'S: 250 Rename successful.\n'
    'C: QUIT\n'
    'S: 221 Goodbye.'
)
p = doc.add_paragraph()
r = p.add_run(ftp_up)
r.font.name = 'Consolas'
r.font.size = Pt(9)
p.paragraph_format.space_after = Pt(8)
para('响应状态码约定：', bold=True)
make_table(['状态码', '含义', '出现环节'], [
    ['230', '用户登录成功', 'USER/PASS 认证后'],
    ['200', '命令成功（如切换二进制模式）', 'TYPE I'],
    ['227', '进入被动模式，返回数据端口', 'PASV'],
    ['226', '数据传输完成，连接关闭', 'STOR 上传完成'],
    ['350', '重命名源文件就绪，等待 RNTO', 'RNFR'],
    ['250', '重命名成功，最终文件生效', 'RNTO'],
    ['221', '会话正常关闭', 'QUIT'],
    ['530', '认证失败（账号/密码错误）', '登录环节'],
    ['425', '无法打开数据连接（防火墙未放行被动端口段）', 'PASV 后数据传输'],
    ['550', '操作被拒绝（目录/权限异常）', 'STOR/RNTO'],
], widths=[2.2, 8.2, 5.6])
para('上传成功判定：STOR 返回 226 且 RNTO 返回 250。仅完成 STOR 未完成 RNTO 的文件保留为 .uploading 临时文件，检测服务不处理。', size=9.5)

doc.add_page_break()

# ========== 第 4 节 ==========
doc.add_heading('4  检测服务行为约定', level=1)

doc.add_heading('4.1  处理顺序', level=2)
bullet('最旧优先：待处理文件按文件名时间戳字段（3.2 节字段 1）升序处理，时间戳缺失时按文件落盘时间回退排序；')
bullet('单线程串行：同一时刻仅处理一张图片，处理完成后再取下一张；不做并发处理，以保证边缘设备资源占用平稳、行为可预期。')

doc.add_heading('4.2  实时性', level=2)
make_table(['指标', '约定', '说明'], [
    ['触发延迟', '≤ 1 秒', '新 .jpg 文件出现至开始处理的时间间隔（服务轮询周期 ≤ 1 秒）'],
    ['端到端延迟', '≤ 1 秒', '文件落盘至报警回传完成的时间间隔（当前实测约 0.6 秒，含推理与回传）'],
    ['单张处理时长', '≤ 2 秒', '从读取原图至生成结果图完成（含解码、推理、标注）'],
], widths=[3.4, 3.0, 9.6])

doc.add_heading('4.3  文件生命周期', level=2)
make_table(['输入文件', '去向', '触发条件'], [
    ['原图（/images/*.jpg）', '处理完成后自动删除', '每张图片处理完成（无论是否检出缺陷）'],
    ['带标记结果图', '/results/<同名>.jpg', '每张图片处理完成均生成'],
    ['报警记录', '/alarms/<同名>.json，并回传（见第 5 节）', '检出任意缺陷类别'],
    ['异常图片', '/failed/<原名>.jpg', '原图无法解码或读取失败，不参与检测'],
], widths=[5.4, 6.6, 4.0])

doc.add_heading('4.4  缺陷类别与报警判定', level=2)
para('第一批共 15 种检测算法，全部类别检出即触发报警（无缺陷的图片不回传）。类别编码为检测服务输出使用的标识符，在报警记录（5.4 节）的 detections[].class 字段中原样出现：')
make_table(['序号', '类别编码', '监测对象', '含义（待算法组最终确认）'], [
    ['1', 'jingbi_hntlw', '井壁', '混凝土裂纹'],
    ['2', 'jingbi_bmbl', '井壁', '表面剥落'],
    ['3', 'guandao_dl', '罐道（竖）', '断裂'],
    ['4', 'guandao_qs', '罐道（竖）', '缺失'],
    ['5', 'guandao_gdjtl', '罐道（竖）', '罐道接头异常'],
    ['6', 'dianlan_dlkl', '电缆', '断裂开裂'],
    ['7', 'liang_wq', '罐道梁（横）', '弯曲变形'],
    ['8', 'liang_bx', '罐道梁（横）', '变形'],
    ['9', 'liang_ps', '罐道梁（横）', '压板/破损'],
    ['10', 'shu_sd', '井底楔形罐道', '断裂/缺失'],
    ['11', 'shu_bx', '井底楔形罐道', '变形'],
    ['12', 'shu_ps', '井底楔形罐道', '固定件破损'],
    ['13', 'luoshuan_qs', '罐道梁支座螺栓', '缺失'],
    ['14', 'fengshui_glbx', '风水管路', '管路变形'],
    ['15', 'fengshui_glds', '风水管路', '管路滴水'],
], widths=[1.2, 4.2, 4.2, 6.4])
para('注：类别编码与监测对象的对应关系为当前版本约定，中文含义以算法组最终确认为准，确认后仅更新本表，不影响编码本身。', size=9.5)

doc.add_page_break()

# ========== 第 5 节 ==========
doc.add_heading('5  报警回传协议', level=1)
para('本章约定链路②（边缘检测服务器 → 平台接收端）的回传规则。当前版本承载方式为 FTP 上传（与链路①同风格）；若平台侧最终要求按《消息推送接口文档 v5.20》[3] 的 HTTP 推送方式接入，将在后续版本扩展 5.3 节参数与请求/响应示例，其余小节不受影响。')

doc.add_heading('5.1  回传触发条件', level=2)
bullet('检出 4.4 节任意类别（置信度 ≥ 0.35）即触发报警；')
bullet('一次报警回传一份报文，包含 2 个文件：带标记结果图 1 张 + 报警记录 1 份；')
bullet('同一张图片检出多个缺陷时，合并为一次回传，缺陷明细在报警记录 detections 数组中并列；')
bullet('无缺陷的图片不回传、不产生报警记录（无回执机制）。')

doc.add_heading('5.2  回传文件命名', level=2)
make_table(['序号', '中文名称', '文件命名', '说明'], [
    ['1', '带标记结果图', '<原文件名>.jpg', '与上传原图完全同名（含六字段业务信息），在原图上叠加检测框与类别标注'],
    ['2', '报警记录', '<原文件名>.json', '与原图同名，扩展名为 .json，结构化缺陷明细（见 5.4 节）'],
    ['3', '临时文件', '<文件名>.uploading', '上传中间态，完成后 RNFR/RNTO 原子重命名，与链路①约定一致'],
], widths=[1.2, 3.0, 5.4, 6.4])

doc.add_heading('5.3  回传目标参数（待对齐）', level=2)
make_table(['项目', '约定', '说明'], [
    ['承载方式', 'FTP 上传（当前版本）', '被动模式、二进制、临时文件 + 原子重命名，与链路①同风格'],
    ['服务器地址', '（待填）', '回传目标服务器 IP，平台侧提供后填入'],
    ['控制端口', '（待填，默认 21）', '—'],
    ['用户名 / 密码', '（待填）', '回传专用账户，建议与上传账户分离'],
    ['回传目录', '（待填）', 'FTP 根下的回传目录，不存在时服务端自动创建'],
    ['回传成功判定', '两个文件均重命名完成', '以 STOR + RNTO 成功为准，无应用层响应报文'],
], widths=[3.4, 4.6, 8.0])

doc.add_heading('5.4  报警记录 JSON 报文格式', level=2)
para('报警记录为 UTF-8 编码的 JSON 文件，字段定义如下：')
make_table(['序号', '中文名称', '参数名称', '数据类型', '约束', '说明'], [
    ['1', '处理时刻', 'time', 'string', '必选', '检测服务器完成处理的本地时间，格式 YYYY-MM-DD hh:mm:ss'],
    ['2', '原文件名', 'filename', 'string', '必选', '触发报警的上传原图文件名（六字段命名）'],
    ['3', '业务元数据', 'meta', 'object', '必选', '文件名六字段的解析回显；命名不合规时为空对象'],
    ['3.1', '采集时间戳', 'meta.timestamp', 'string', '条件必选', '17 位毫秒时间戳，同文件名字段 1'],
    ['3.2', '机器人编号', 'meta.robot_id', 'string', '条件必选', '同文件名字段 2'],
    ['3.3', '任务编号', 'meta.task_id', 'string', '条件必选', '同文件名字段 3'],
    ['3.4', '相机角度', 'meta.camera_angle', 'string', '条件必选', '同文件名字段 4'],
    ['3.5', '编码器位置', 'meta.encoder_pos', 'string', '条件必选', '同文件名字段 5'],
    ['3.6', '预留字段', 'meta.reserved', 'string', '条件必选', '同文件名字段 6'],
    ['3.7', '采集时间', 'meta.time_str', 'string', '条件必选', '可读格式 YYYY-MM-DD hh:mm:ss.SSS'],
    ['4', '缺陷明细', 'detections', 'array', '必选', '检出对象数组，至少 1 个元素'],
    ['4.1', '缺陷类别', 'detections[].class', 'string', '必选', '4.4 节类别编码'],
    ['4.2', '置信度', 'detections[].conf', 'float', '必选', '0~1，保留 3 位小数'],
    ['4.3', '检测框', 'detections[].box', 'int[4]', '必选', '原图像素坐标 [x1, y1, x2, y2]，左上为原点'],
    ['5', '结果图引用', 'result_image', 'string', '必选', '带标记结果图在检测服务器上的存储路径'],
], widths=[1.1, 2.6, 4.0, 1.8, 1.7, 4.8])

doc.add_heading('5.5  回传可靠性', level=2)
bullet('回传失败不阻塞检测主链路：单次回传失败仅记录错误日志，后续图片照常检测；')
bullet('本地永久暂存：全部报警记录（/alarms）与结果图（/results）在检测服务器长期留存，与是否回传成功无关；')
bullet('支持补传：留存记录可作为补传数据源，补传方式由双方运维约定（人工拷贝或批量工具）。')

doc.add_heading('5.6  回传会话示例与状态码（FTP 承载，当前版本）', level=2)
para('请求地址：', bold=True)
p = doc.add_paragraph()
r = p.add_run('ftp://<回传服务器IP>/<回传目录>')
r.font.name = 'Consolas'
r.font.size = Pt(10)
p.paragraph_format.space_after = Pt(6)
para('请求示例（一次报警回传两个文件的 FTP 会话命令序列）：', bold=True)
ftp_rt = (
    'C: USER <回传账户>\n'
    'S: 230 Login successful.\n'
    'C: TYPE I\n'
    'S: 200 Switching to Binary mode.\n'
    'C: PASV\n'
    'S: 227 Entering Passive Mode (h1,h2,h3,h4,p1,p2).\n'
    '# 文件 1/2：带标记结果图\n'
    'C: STOR 20261009143025123_007_042_0900_1234_0000000000.jpg.uploading\n'
    'S: 226 Transfer complete.\n'
    'C: RNFR 20261009143025123_007_042_0900_1234_0000000000.jpg.uploading\n'
    'S: 350 Ready for RNTO.\n'
    'C: RNTO 20261009143025123_007_042_0900_1234_0000000000.jpg\n'
    'S: 250 Rename successful.\n'
    '# 文件 2/2：报警记录\n'
    'C: STOR 20261009143025123_007_042_0900_1234_0000000000.json.uploading\n'
    'S: 226 Transfer complete.\n'
    'C: RNFR 20261009143025123_007_042_0900_1234_0000000000.json.uploading\n'
    'S: 350 Ready for RNTO.\n'
    'C: RNTO 20261009143025123_007_042_0900_1234_0000000000.json\n'
    'S: 250 Rename successful.\n'
    'C: QUIT\n'
    'S: 221 Goodbye.'
)
p = doc.add_paragraph()
r = p.add_run(ftp_rt)
r.font.name = 'Consolas'
r.font.size = Pt(9)
p.paragraph_format.space_after = Pt(8)
para('响应状态码与 3.5 节约定一致。回传成功判定：两个文件均完成 STOR(226) + RNTO(250)；任一文件失败按 5.5 节可靠性约定处理。', size=9.5)

doc.add_heading('5.7  HTTP 推送承载预留（格式模板，待平台确认后启用）', level=2)
para('若平台侧要求按《消息推送接口文档 v5.20》[3] 的 HTTP 推送方式接入，回传链路②按以下模板定义（端点与编码以平台侧最终定义为准）：')
para('请求地址：', bold=True)
p = doc.add_paragraph()
r = p.add_run('HTTP://<平台IP>:<端口>/api/ai/cage（预留，端点待平台定义）')
r.font.name = 'Consolas'
r.font.size = Pt(10)
p.paragraph_format.space_after = Pt(6)
para('请求示例：', bold=True)
http_req = (
    'POST /api/ai/cage HTTP/1.1\n'
    'Host: <平台IP>:<端口>\n'
    'Content-Type: multipart/form-data; boundary=----WebKitFormBoundaryJVpKw2XlPggKaD87\n'
    '\n'
    '------WebKitFormBoundaryJVpKw2XlPggKaD87\n'
    'Content-Disposition: form-data; name="cage"; filename="20261009143025123_007_042_0900_1234_0000000000.jpg"\n'
    'Content-Type: image/jpeg\n'
    '\n'
    '<带标记结果图二进制数据>\n'
    '------WebKitFormBoundaryJVpKw2XlPggKaD87\n'
    'Content-Disposition: form-data; name="alarm"; filename="20261009143025123_007_042_0900_1234_0000000000.json"\n'
    'Content-Type: application/json\n'
    '\n'
    '<报警记录 JSON 数据>\n'
    '------WebKitFormBoundaryJVpKw2XlPggKaD87--'
)
p = doc.add_paragraph()
r = p.add_run(http_req)
r.font.name = 'Consolas'
r.font.size = Pt(9)
p.paragraph_format.space_after = Pt(8)
para('响应示例：', bold=True)
http_resp = (
    'HTTP/1.1 200 OK\n'
    '{\n'
    '  "code": 0,\n'
    '  "msg": "success",\n'
    '  "data": true\n'
    '}'
)
p = doc.add_paragraph()
r = p.add_run(http_resp)
r.font.name = 'Consolas'
r.font.size = Pt(9)
p.paragraph_format.space_after = Pt(8)
make_table(['项目', '约定'], [
    ['推送内容', 'multipart 表单：name="cage" 带标记结果图（file）+ name="alarm" 报警记录 JSON（file）'],
    ['文件命名', '与 5.2 节一致（沿用本系统命名规范，不改用 v5.20 的编码拼接规则）'],
    ['推送成功判定', 'HTTP 200 且响应 code = 0；否则按 5.5 节可靠性约定处理'],
    ['时间延迟要求', '检出至推送完成 ≤ 1 秒（本系统实测约 0.6 秒，满足 v5.20 的 ≤ 300 秒要求）'],
    ['图片大小上限', '单张 ≤ 10M（对齐 v5.20 约定）'],
], widths=[3.4, 12.6])
para('注：本节为预留模板，启用时由双方确认端点、字段名后升版修订，届时 5.3/5.6 节 FTP 参数保留作回退方案。', size=9.5)

doc.add_page_break()

# ========== 第 6 节 ==========
doc.add_heading('6  异常处理', level=1)
make_table(['异常场景', '处理约定', '责任方'], [
    ['上传中断，遗留 .uploading 临时文件', '检测服务不读取；客户端下次上传同名文件前自行清理', '客户端'],
    ['上传完成但文件名不符合 3.2 节规范', '按 3.4 节容错策略照常检测，记录告警日志', '服务端'],
    ['原图无法解码 / 读取失败', '移入 /failed 留存，不参与检测，不产生报警；由人工排查后决定是否重新上传', '服务端'],
    ['检测服务进程异常退出', '系统守护机制自动重启（3 秒内拉起），重启后恢复处理遗留的处理中文件', '服务端'],
    ['设备断电重启', '开机后收图与检测服务自动拉起（实测 16 秒内链路就绪），断电前未完成的图片按上述规则恢复或重新上传', '服务端/客户端'],
    ['回传目标不可达', '按 5.5 节执行：本地留存、记录错误日志、不阻塞检测；目标恢复后补传', '服务端'],
    ['重复上传同一文件名', '服务端按新文件处理（覆盖处理顺序按时间戳），平台侧按文件名去重', '双方'],
], widths=[5.2, 8.2, 2.6])

# ========== 第 7 节 附录 ==========
doc.add_heading('附录A  报警记录完整示例', level=1)
para('文件名：20261009143025123_007_042_0900_1234_0000000000.json')
json_sample = (
    '{\n'
    '  "time": "2026-10-12 15:27:42",\n'
    '  "filename": "20261009143025123_007_042_0900_1234_0000000000.jpg",\n'
    '  "meta": {\n'
    '    "timestamp": "20261009143025123",\n'
    '    "robot_id": "007",\n'
    '    "task_id": "042",\n'
    '    "camera_angle": "0900",\n'
    '    "encoder_pos": "1234",\n'
    '    "reserved": "0000000000",\n'
    '    "time_str": "2026-10-09 14:30:25.123"\n'
    '  },\n'
    '  "detections": [\n'
    '    {\n'
    '      "class": "guandao_dl",\n'
    '      "conf": 0.667,\n'
    '      "box": [1623, 250, 2125, 1082]\n'
    '    }\n'
    '  ],\n'
    '  "result_image": "/data/ftp/results/20261009143025123_007_042_0900_1234_0000000000.jpg"\n'
    '}'
)
p = doc.add_paragraph()
r = p.add_run(json_sample)
r.font.name = 'Consolas'
r.font.size = Pt(9)
p.paragraph_format.space_after = Pt(10)

doc.add_heading('附录B  边缘检测服务器目录结构总览', level=1)
tree = (
    '/data/ftp/\n'
    '├── images/    收图入口（处理后自动清空）\n'
    '├── results/   带标记结果图（与原图同名，长期留存）\n'
    '├── alarms/    报警记录 JSON（长期留存，回传兜底）\n'
    '├── failed/    异常图片（待人工排查）\n'
    '└── return/    回传暂存区（FTP 承载方式时使用）'
)
p = doc.add_paragraph()
r = p.add_run(tree)
r.font.name = 'Consolas'
r.font.size = Pt(9.5)

doc.save(OUT)
print('OK ->', OUT)
