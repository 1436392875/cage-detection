#!/usr/bin/env python3
"""本机模拟上位机接收端（联调验证用）：
POST /api/ai/alarmevent 接收 multipart 报警图，落盘到 /tmp/recv/ 并回 code=0
"""
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RECV_DIR = "/tmp/recv"


def parse_multipart(body, boundary):
    """极简 multipart 解析：提取 filename 和文件字节"""
    parts = body.split(b"--" + boundary)
    for part in parts:
        if b"filename=" not in part:
            continue
        header, _, data = part.partition(b"\r\n\r\n")
        data = data.rsplit(b"\r\n", 1)[0]
        for line in header.split(b"\r\n"):
            if b"filename=" in line:
                fname = line.split(b"filename=")[1].strip(b'" ').decode()
                return fname, data
    return None, None


class Handler(BaseHTTPRequestHandler):
    def dump_request(self, body, boundary, fname):
        """把本次请求原文存档到 last_request.txt（图片二进制用占位符表示）"""
        lines = [f"===== 收到时间 {time.strftime('%Y-%m-%d %H:%M:%S')} =====",
                 f"{self.command} {self.path} HTTP/1.1"]
        for k, v in self.headers.items():
            lines.append(f"{k}: {v}")
        lines.append("---------- 请求体（multipart 结构） ----------")
        for part in body.split(b"--" + boundary):
            if not part.strip(b"\r\n-"):
                continue
            seg = part.lstrip(b"\r\n")
            header, _, data = seg.partition(b"\r\n\r\n")
            data = data.rstrip(b"\r\n")
            lines.append(header.decode("utf-8", "replace"))
            lines.append(f"[图片二进制 {len(data)} 字节，已省略]" if data else "")
        lines.append(f"--{boundary.decode()}--")
        lines.append("---------- 响应 ----------")
        lines.append('HTTP/1.1 200 OK')
        lines.append('Content-Type: application/json')
        lines.append('')
        lines.append('{"code": 0, "msg": "success", "data": true}')
        with open(os.path.join(RECV_DIR, "last_request.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def do_POST(self):
        if self.path != "/api/ai/alarmevent":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")
        boundary = ctype.split("boundary=")[1].encode() if "boundary=" in ctype else b"----x"
        fname, data = parse_multipart(body, boundary)
        if not fname:
            self.send_error(400)
            return
        os.makedirs(RECV_DIR, exist_ok=True)
        with open(os.path.join(RECV_DIR, fname), "wb") as f:
            f.write(data)
        self.dump_request(body, boundary, fname)
        print(f"[{time.strftime('%H:%M:%S')}] 收到报警图: {fname} ({len(data)//1024}KB)，"
              f"请求报文已存 {RECV_DIR}/last_request.txt")
        resp = b'{"code": 0, "msg": "success", "data": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *a):  # 静默默认访问日志
        pass


if __name__ == "__main__":
    print(f"模拟接收端: http://127.0.0.1:8081/api/ai/alarmevent -> {RECV_DIR}/")
    ThreadingHTTPServer(("127.0.0.1", 8081), Handler).serve_forever()
