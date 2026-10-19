# -*- coding: utf-8 -*-
"""生成协议文档第2节系统拓扑图（协议文档配图，随文档维护）"""
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

FP_REG = FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
FP_MED = FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc')
FP_BOLD = FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc')

fig, ax = plt.subplots(figsize=(12.5, 4.6), dpi=200)
ax.set_xlim(0, 12.5)
ax.set_ylim(0, 4.6)
ax.axis('off')

C_ROBOT = '#D6E4F0'
C_EDGE  = '#FDF2D0'
C_PLAT  = '#DDEBD8'
C_TXT   = '#1a1a1a'

def box(x, y, w, h, fc, lw=1.4):
    b = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.08,rounding_size=0.12',
                       fc=fc, ec='#4a4a4a', lw=lw)
    ax.add_patch(b)

def arrow(x1, y1, x2, y2, color):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle='-|>', mutation_scale=22,
                        lw=2.0, color=color, shrinkA=2, shrinkB=2)
    ax.add_patch(a)

# 三个角色盒子
box(0.25, 1.55, 2.5, 1.7, C_ROBOT)
ax.text(1.5, 2.82, '罐笼巡检机器人', ha='center', fontsize=13, fontproperties=FP_BOLD, color=C_TXT)
ax.text(1.5, 2.38, 'FTP Client', ha='center', fontsize=11, fontproperties=FP_MED, color='#333333')
ax.text(1.5, 1.98, '（面阵相机 / 上传工具）', ha='center', fontsize=9, fontproperties=FP_REG, color='#555555')

box(4.35, 0.55, 3.8, 3.6, C_EDGE)
ax.text(6.25, 3.78, '边缘检测服务器', ha='center', fontsize=13, fontproperties=FP_BOLD, color=C_TXT)
ax.text(6.25, 3.42, 'AI 边缘计算服务器', ha='center', fontsize=10, fontproperties=FP_MED, color='#333333')
ax.text(6.25, 3.08, 'FTP 服务 + 检测服务', ha='center', fontsize=10, fontproperties=FP_MED, color='#333333')
ax.plot([4.75, 7.75], [2.86, 2.86], color='#999999', lw=0.8, ls='--')
dirs = [('images/', '收图入口（处理后清空）'),
        ('results/', '带标记结果图（与原图同名）'),
        ('alarms/', '报警记录（长期留存）'),
        ('failed/', '异常图片（待人工排查）')]
for i, (d, desc) in enumerate(dirs):
    ax.text(4.85, 2.42 - i * 0.42, d, ha='left', fontsize=10, fontproperties=FP_MED, color='#005a9e')
    ax.text(6.05, 2.42 - i * 0.42, desc, ha='left', fontsize=8.5, fontproperties=FP_REG, color='#555555')

box(9.75, 1.55, 2.5, 1.7, C_PLAT)
ax.text(11.0, 2.82, '平台接收端', ha='center', fontsize=13, fontproperties=FP_BOLD, color=C_TXT)
ax.text(11.0, 2.38, '矿方监管平台', ha='center', fontsize=11, fontproperties=FP_MED, color='#333333')
ax.text(11.0, 1.98, '（回传目标，待对齐）', ha='center', fontsize=9, fontproperties=FP_REG, color='#555555')

# 链路箭头
arrow(2.85, 2.6, 4.25, 2.6, '#2e6da4')
ax.text(3.55, 3.05, '链路①', ha='center', fontsize=11, fontproperties=FP_BOLD, color='#2e6da4')
ax.text(3.55, 1.95, '图片上传\nFTP·被动模式\n端口 21', ha='center', fontsize=8, fontproperties=FP_REG, color='#2e6da4')

arrow(8.25, 2.6, 9.65, 2.6, '#3c8b3c')
ax.text(8.95, 3.05, '链路②', ha='center', fontsize=11, fontproperties=FP_BOLD, color='#3c8b3c')
ax.text(8.95, 1.95, '报警回传\n带标记结果图\n+ 报警记录', ha='center', fontsize=8, fontproperties=FP_REG, color='#3c8b3c')

# 底部说明
ax.text(6.25, 0.18, '检测行为约定（最旧优先 / 串行处理 / 仅报警回传）详见第 4 节；链路②承载方式与报文格式详见第 5 节',
        ha='center', fontsize=8.5, fontproperties=FP_REG, color='#777777')

plt.savefig('/home/nvidia/2026/detector/doc_assets/topology.png', dpi=200, bbox_inches='tight', facecolor='white')
print('OK topology.png')
