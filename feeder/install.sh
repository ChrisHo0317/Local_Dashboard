#!/usr/bin/env bash
# 在雲端小主機上安裝盤中即時行情程式（.github/workflows/feeder.yml 用 SSH 呼叫，不用手動跑）
#   ~/local-dash-feeder/   feeder.py、requirements.txt、feeder.env（部署流程寫入，權限 600）、venv/
#   systemd：local-dash-feeder.timer 平日台北 08:45 啟動 local-dash-feeder.service，程式 13:36 自己結束
set -euo pipefail
DIR="$HOME/local-dash-feeder"
cd "$DIR"
chmod 600 feeder.env

if [ ! -x venv/bin/python ]; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv >/dev/null
  python3 -m venv venv
fi
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements.txt

sudo tee /etc/systemd/system/local-dash-feeder.service >/dev/null <<EOF
[Unit]
Description=Local_Dash 盤中即時行情（永豐金 Shioaji → Cloudflare 即時轉播站）
After=network-online.target
Wants=network-online.target
# 一直失敗（金鑰錯、永豐金維護）時，2 小時內最多重啟 10 次，免得一直登入永豐金（每天上限 1000 次）
StartLimitIntervalSec=2h
StartLimitBurst=10

[Service]
Type=simple
User=$USER
WorkingDirectory=$DIR
EnvironmentFile=$DIR/feeder.env
ExecStart=$DIR/venv/bin/python $DIR/feeder.py
Restart=on-failure
RestartSec=30
RuntimeMaxSec=6h
EOF

sudo tee /etc/systemd/system/local-dash-feeder.timer >/dev/null <<EOF
[Unit]
Description=平日台北 08:45 啟動盤中即時行情程式

[Timer]
OnCalendar=Mon..Fri *-*-* 08:45:00 Asia/Taipei
# 08:45 之後主機才開機也補跑；不是盤中的話程式會自己馬上結束
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now local-dash-feeder.timer >/dev/null
# 部署時剛好在盤中（平日 08:45～13:35）：直接重啟，用新版程式
now=$(TZ=Asia/Taipei date +%u%H%M)
dow=${now:0:1}; hm=${now:1:4}
if [ "$dow" -le 5 ] && [ "$hm" -ge 0845 ] && [ "$hm" -lt 1335 ]; then
  sudo systemctl restart local-dash-feeder.service
  echo "盤中部署：已重新啟動行情程式"
fi
echo "安裝完成；下次啟動：$(systemctl list-timers local-dash-feeder.timer --no-legend | awk '{print $1, $2, $3}')"
