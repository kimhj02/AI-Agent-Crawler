#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   sudo bash deploy/aws/setup_live_service.sh \
#     --repo-dir /home/ec2-user/AI-Agent-Crawler \
#     --run-user ec2-user \
#     --port 8000

REPO_DIR=""
RUN_USER="ec2-user"
PORT="8000"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      REPO_DIR="$2"
      shift 2
      ;;
    --run-user)
      RUN_USER="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$REPO_DIR" ]]; then
  echo "--repo-dir is required" >&2
  exit 2
fi

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repository directory not found: $REPO_DIR" >&2
  exit 2
fi

if [[ ! -f "$REPO_DIR/.env" ]]; then
  echo "Missing $REPO_DIR/.env (copy from .env.example and fill values first)" >&2
  exit 2
fi

if command -v dnf >/dev/null 2>&1; then
  dnf install -y python3 python3-pip git
elif command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip git
else
  echo "Unsupported package manager (need dnf or apt-get)" >&2
  exit 2
fi

cd "$REPO_DIR"
sudo -u "$RUN_USER" python3 -m venv .venv
sudo -u "$RUN_USER" .venv/bin/pip install --upgrade pip
sudo -u "$RUN_USER" .venv/bin/pip install -r requirements.txt

SERVICE_FILE="/etc/systemd/system/ai-crawler-live.service"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=AI Crawler Live Service
After=network.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$REPO_DIR/.env
ExecStart=$REPO_DIR/.venv/bin/python -m uvicorn user_features.live_service:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ai-crawler-live
systemctl status ai-crawler-live --no-pager

echo ""
echo "Installed and started ai-crawler-live."
echo "Health check:"
echo "  curl http://127.0.0.1:$PORT/health"
