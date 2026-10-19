#!/bin/bash
# =============================================================
# 罐笼检测服务 断电重启验证脚本（beta1 发运前必测项）
# 用法：
#   ./reboot_verify.sh check    # 第一步：重启前，检查自启配置
#   ./reboot_verify.sh reboot   # 第二步：执行重启（等效于断电再上电）
#   ./reboot_verify.sh verify   # 第三步：重启回来后，全链路验证
#                                #   FTP 收图 -> TRT 推理 -> 大模型质检 -> HTTP 推送
# =============================================================
set -u

# FTP 账户密码脱敏：优先环境变量，其次脚本同目录 ftp_secret.txt（git 忽略，不入公开仓库）
FTP_USER="${FTP_USER:-guanlong_ftp}"
FTP_PASSWD="${FTP_PASSWD:-$(cat "$(dirname "$0")/ftp_secret.txt" 2>/dev/null || true)}"

TEST_SRC="/home/nvidia/2026/detector/data_in/testset/liang_20261009000726.jpg"  # 真实缺陷图,期望 G002
TS="$(date +%Y%m%d%H%M%S)123"
FNAME="${TS}_007_042_0900_1234_0000000000.jpg"
WATCH_DIR="/data/ftp/images"
RESULT_DIR="/data/ftp/results"
ALARM_DIR="/data/ftp/alarms"
RECV_DIR="/tmp/recv"
LOG="/home/nvidia/2026/detector/logs/pipeline.log"

ok()   { echo "  [PASS] $1"; }
bad()  { echo "  [FAIL] $1"; FAIL=1; }

wait_active() {  # $1=服务名 $2=最长等待秒
    local i=0
    while [ $i -lt $(( $2 * 2 )) ]; do
        [ "$(systemctl is-active "$1")" = "active" ] && return 0
        sleep 5; i=$((i+1))
    done
    return 1
}

case "${1:-}" in

check)
    echo "== 重启前自启配置检查 =="
    FAIL=0
    for s in vsftpd llama-server cage-detector; do
        [ "$(systemctl is-enabled $s 2>/dev/null)" = "enabled" ] \
            && ok "$s 已设置开机自启" || bad "$s 未设置自启!"
    done
    # 启动顺序：llama-server 必须先于 cage-detector（GPU 大块内存先分配）
    b=$(systemctl show -p Before llama-server --value 2>/dev/null)
    echo "$b" | grep -q cage-detector \
        && ok "启动顺序: llama-server 先于 cage-detector" || bad "启动顺序配置缺失!"
    [ -f "$TEST_SRC" ] && ok "测试图存在: $(basename $TEST_SRC)" || bad "测试图缺失: $TEST_SRC"
    if [ $FAIL -eq 0 ]; then
        echo "全部就绪，执行: ./reboot_verify.sh reboot（或直接断电再上电）"
    else
        echo "存在问题，先修复再重启验证！"
    fi
    exit $FAIL
    ;;

reboot)
    echo "3 秒后重启设备（等效断电再上电）..."
    sleep 3
    sudo reboot
    ;;

verify)
    echo "== 重启后全链路验证 =="
    echo "本次开机时长: $(uptime -p)"
    FAIL=0

    echo "-- 1/5 服务拉起（llama-server 可能因显存释放重启数次，耐心等待）--"
    wait_active llama-server 300 \
        && ok "llama-server active" || bad "llama-server 5 分钟内未拉起"
    wait_active cage-detector 120 \
        && ok "cage-detector active" || bad "cage-detector 未拉起"
    [ "$(systemctl is-active vsftpd)" = "active" ] \
        && ok "vsftpd active" || bad "vsftpd 未运行"

    echo "-- 2/5 大模型服务健康 --"
    curl -sf http://127.0.0.1:8080/health | grep -q ok \
        && ok "llama-server /health 正常" || bad "llama-server 健康检查失败"

    echo "-- 3/5 启动本机模拟接收端(8081) --"
    if ! ss -tln | grep -q "127.0.0.1:8081"; then
        cd /home/nvidia/2026/detector && nohup python3 recv_test.py >/tmp/recv_test.log 2>&1 &
        sleep 2
    fi
    ss -tln | grep -q "127.0.0.1:8081" \
        && ok "接收端 8081 就绪" || bad "接收端启动失败(不影响主链路判定,改查日志推送记录)"

    echo "-- 4/5 FTP 投图: $FNAME --"
    rm -f "$RECV_DIR/${FNAME%.jpg}_G002.jpg"
    cp "$TEST_SRC" "/tmp/$FNAME"
    [ -n "$FTP_PASSWD" ] || { bad "FTP 密码未配置（环境变量 FTP_PASSWD 或 ftp_secret.txt）"; exit 1; }
    curl -sf -T "/tmp/$FNAME" "ftp://127.0.0.1/images/" --user "$FTP_USER:$FTP_PASSWD" \
        && ok "FTP 上传成功" || { bad "FTP 上传失败"; exit 1; }
    rm -f "/tmp/$FNAME"

    echo "-- 5/5 等待处理（推理+质检约 10s，最长等 120s）--"
    t0=$(date +%s)
    while [ $(( $(date +%s) - t0 )) -lt 120 ]; do
        [ ! -f "$WATCH_DIR/$FNAME" ] && [ ! -f "$WATCH_DIR/$FNAME.processing" ] && break
        sleep 2
    done
    [ ! -f "$WATCH_DIR/$FNAME" ] && [ ! -f "$WATCH_DIR/$FNAME.processing" ] \
        && ok "原图已处理并删除 (耗时 $(( $(date +%s) - t0 )) 秒)" \
        || bad "120s 未处理完成"

    sleep 1
    [ -f "$RESULT_DIR/$FNAME" ] \
        && ok "结果图已生成 results/$FNAME" || bad "结果图缺失"
    [ -f "$ALARM_DIR/${FNAME%.jpg}.json" ] \
        && ok "报警记录已生成 alarms/${FNAME%.jpg}.json" || bad "报警记录缺失"
    if [ -f "$RECV_DIR/${FNAME%.jpg}_G002.jpg" ]; then
        ok "接收端收到推送: ${FNAME%.jpg}_G002.jpg"
    elif grep -q "已推送.*${FNAME%.jpg}.*G002" "$LOG"; then
        ok "日志确认已推送 _G002（接收端未开不影响）"
    else
        bad "未确认 HTTP 推送"
    fi
    echo ""
    echo "可用内存: $(free -m | awk '/内存/{print $7}')MB"
    if [ $FAIL -eq 0 ]; then
        echo "====== 断电重启验证 全部通过，具备发运条件 ======"
    else
        echo "====== 存在失败项，查看日志: journalctl -u cage-detector -u llama-server --since today ======"
    fi
    exit $FAIL
    ;;

*)
    echo "用法: $0 {check|reboot|verify}"
    echo "  check   重启前:检查自启配置"
    echo "  reboot  执行重启(等效断电再上电)"
    echo "  verify  重启后:全链路验证"
    exit 1
    ;;
esac
