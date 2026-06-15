# TG Forwarder VPS 部署方案

本文档以 Ubuntu/Debian VPS 为例，部署目录为 `/opt/tg-forwarder`。

## 1. 当前项目启动入口

当前项目已有统一入口 `app.py`，部署时优先使用：

```bash
python app.py
```

`app.py` 会同时启动：

- Telegram 转发主程序
- Web 管理后台

`main.py` 和 `web_admin.py` 仍可单独运行，但 VPS 长期部署推荐只用 `app.py`，再交给 systemd 管理。

默认 Web 后台监听地址和端口来自 SQLite `settings` 表：

- `web_host=127.0.0.1`
- `web_port=8080`

保持 `127.0.0.1:8080` 是推荐方式，然后用 SSH 隧道或 Nginx 反向代理访问，不要直接把 8080 暴露到公网。

## 2. 目录结构

部署后的推荐结构：

```text
/opt/tg-forwarder/
├── app.py
├── main.py
├── web_admin.py
├── init_db.py
├── db.py
├── requirements.txt
├── .env
├── tg_forwarder.session
├── storage/
│   ├── app.db
│   └── forwarder.log
├── cleaner/
├── classifier/
├── dedup/
└── sender/
```

敏感文件：

- `.env`
- `*.session`
- `storage/app.db`

这些文件不要提交到 Git。

## 3. 从 git clone 到运行

把 `<REPO_URL>` 替换为你的仓库地址。

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip sqlite3

sudo adduser --system --group --no-create-home tgforwarder
sudo install -d -m 0750 -o tgforwarder -g tgforwarder /opt/tg-forwarder

sudo git clone <REPO_URL> /opt/tg-forwarder
sudo chown -R tgforwarder:tgforwarder /opt/tg-forwarder

cd /opt/tg-forwarder
sudo -u tgforwarder python3 -m venv .venv
sudo -u tgforwarder .venv/bin/python -m pip install --upgrade pip
sudo -u tgforwarder .venv/bin/pip install -r requirements.txt

sudo -u tgforwarder mkdir -p /opt/tg-forwarder/storage
```

如果你没有 Git 仓库，可以先把本地项目上传：

```bash
scp -r ./tg-forwarder root@<VPS_IP>:/opt/tg-forwarder
sudo chown -R tgforwarder:tgforwarder /opt/tg-forwarder
```

## 4. 配置 .env

创建服务器上的 `.env`：

```bash
sudo tee /opt/tg-forwarder/.env >/dev/null <<'EOF'
API_ID=123456
API_HASH=replace_with_your_api_hash
SESSION_NAME=/opt/tg-forwarder/tg_forwarder
DB_PATH=/opt/tg-forwarder/storage/app.db
EOF

sudo chown tgforwarder:tgforwarder /opt/tg-forwarder/.env
sudo chmod 600 /opt/tg-forwarder/.env
```

不要把真实 `API_ID`、`API_HASH`、Bot Token、DeepSeek API Key 等写进代码或提交到 Git。

## 5. 初始化数据库

```bash
cd /opt/tg-forwarder
sudo -u tgforwarder .venv/bin/python init_db.py
```

如果你想沿用本地已经配置好的频道、规则和目标频道，可以把本地 `storage/app.db` 上传到 VPS：

```bash
scp ./storage/app.db root@<VPS_IP>:/opt/tg-forwarder/storage/app.db
sudo chown tgforwarder:tgforwarder /opt/tg-forwarder/storage/app.db
sudo chmod 600 /opt/tg-forwarder/storage/app.db
```

如果你要全新配置，只运行 `init_db.py` 即可，然后进入 Web 后台添加频道、目标频道和规则。

## 6. 首次 Telegram 登录

如果 VPS 上还没有 Telethon session，需要先手动登录一次。不要第一次就用 systemd 启动，因为 systemd 里无法输入 Telegram 验证码。

```bash
cd /opt/tg-forwarder
sudo -u tgforwarder -H .venv/bin/python main.py
```

按提示输入手机号、验证码、两步验证密码。看到程序已经连接并开始监听后，按 `Ctrl+C` 停止。

这一步会生成：

```text
/opt/tg-forwarder/tg_forwarder.session
```

这个 session 文件等同于登录凭据，请当作敏感文件保护。

## 7. systemd 服务

创建服务文件：

```bash
sudo tee /etc/systemd/system/tg-forwarder.service >/dev/null <<'EOF'
[Unit]
Description=Telegram Forwarder
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=tgforwarder
Group=tgforwarder
WorkingDirectory=/opt/tg-forwarder
EnvironmentFile=/opt/tg-forwarder/.env
ExecStart=/opt/tg-forwarder/.venv/bin/python /opt/tg-forwarder/app.py
Restart=always
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/opt/tg-forwarder

[Install]
WantedBy=multi-user.target
EOF
```

启动并设置开机自启：

```bash
sudo systemctl daemon-reload
sudo systemctl enable tg-forwarder
sudo systemctl start tg-forwarder
```

常用命令：

```bash
sudo systemctl status tg-forwarder
sudo systemctl restart tg-forwarder
sudo systemctl stop tg-forwarder
sudo journalctl -u tg-forwarder -f -n 100
```

以后你只需要一个命令重启项目：

```bash
sudo systemctl restart tg-forwarder
```

SSH 断开后，服务仍会继续运行。VPS 重启后，systemd 会自动拉起服务。进程崩溃后，systemd 会按 `Restart=always` 自动重启。

## 8. Web 后台访问方式

### 方式 A：只本地管理，推荐

保持 Web 后台只监听 VPS 本机：

```text
web_host=127.0.0.1
web_port=8080
```

本地电脑用 SSH 隧道访问：

```bash
ssh -L 8080:127.0.0.1:8080 root@<VPS_IP>
```

然后浏览器打开：

```text
http://127.0.0.1:8080
```

这种方式不需要开放 8080 端口。

### 方式 B：公网域名访问，必须加认证和 HTTPS

安装 Nginx 和 Basic Auth 工具：

```bash
sudo apt install -y nginx apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd-tg-forwarder admin
```

创建 Nginx 配置，把 `<ADMIN_DOMAIN>` 替换为你的域名：

```bash
sudo tee /etc/nginx/sites-available/tg-forwarder-admin >/dev/null <<'EOF'
server {
    listen 80;
    server_name <ADMIN_DOMAIN>;

    auth_basic "TG Forwarder Admin";
    auth_basic_user_file /etc/nginx/.htpasswd-tg-forwarder;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/tg-forwarder-admin /etc/nginx/sites-enabled/tg-forwarder-admin
sudo nginx -t
sudo systemctl reload nginx
```

配置 HTTPS：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <ADMIN_DOMAIN>
```

完成后用：

```text
https://<ADMIN_DOMAIN>
```

访问后台。

不要直接开放 `8080` 到公网。公网访问建议只开放 `80/443`，由 Nginx 代理到本机 `127.0.0.1:8080`。

## 9. UFW 防火墙建议

SSH 必须保留：

```bash
sudo ufw allow 22/tcp
```

如果只用 SSH 隧道访问 Web 后台：

```bash
sudo ufw enable
sudo ufw status verbose
```

如果使用 Nginx + 域名 + HTTPS：

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

不建议开放：

```bash
sudo ufw allow 8080/tcp
```

`3389` 是 Windows 远程桌面端口。Linux VPS 通常不需要开放。如果你的 VPS 不是 Windows 远程桌面环境，不要开放 3389。

## 10. 常见问题排查

### 服务没有启动

```bash
sudo systemctl status tg-forwarder
sudo journalctl -u tg-forwarder -n 200 --no-pager
```

重点看是否缺少：

- `API_ID`
- `API_HASH`
- `.env`
- Python 依赖
- Telegram session

### 日志提示需要 Telegram 登录

先停止 systemd：

```bash
sudo systemctl stop tg-forwarder
```

手动登录：

```bash
cd /opt/tg-forwarder
sudo -u tgforwarder -H .venv/bin/python main.py
```

登录成功后按 `Ctrl+C` 停止，再启动服务：

```bash
sudo systemctl start tg-forwarder
```

### SQLite readonly 或无法写入

检查权限：

```bash
sudo chown -R tgforwarder:tgforwarder /opt/tg-forwarder
sudo chmod 700 /opt/tg-forwarder/storage
sudo chmod 600 /opt/tg-forwarder/.env
```

### Web 后台访问不到

先确认本机服务是否正常：

```bash
curl -i http://127.0.0.1:8080/api/state
sudo journalctl -u tg-forwarder -n 100 --no-pager
```

如果 Nginx 返回 502：

```bash
sudo systemctl status tg-forwarder
sudo systemctl status nginx
sudo nginx -t
```

### 端口被占用

```bash
sudo ss -lntp | grep -E ':80|:443|:8080'
```

### 消息没有转发

检查：

- Telegram 账号是否加入了来源频道
- Telegram 账号是否有目标频道发言权限
- SQLite 中来源频道是否启用
- 目标频道是否配置了对应分类
- Web 后台分类规则是否把消息分到了没有目标频道的分类
- 日志中是否出现去重、清洗丢弃、无目标频道等提示

查看日志：

```bash
sudo journalctl -u tg-forwarder -f -n 100
```

### 提示已有 main.py 在运行

说明旧进程或 systemd 服务还在：

```bash
sudo systemctl stop tg-forwarder
ps aux | grep -E 'app.py|main.py'
```

停止旧进程后再启动：

```bash
sudo systemctl start tg-forwarder
```
