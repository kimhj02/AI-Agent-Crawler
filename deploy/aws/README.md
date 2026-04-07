# AWS 배포 가이드 (Live Service)

이 디렉터리는 `user_features.live_service`를 EC2에서 상시 실행하기 위한 파일입니다.

## 1) 서버 준비

- EC2에 코드 배포
- `.env` 준비 (`deploy/aws/.env.live.example` 참고)

예시:

```bash
cp deploy/aws/.env.live.example .env
vi .env
```

## 2) systemd로 상시 실행

루트 권한으로 설치 스크립트 실행:

```bash
sudo bash deploy/aws/setup_live_service.sh \
  --repo-dir /home/ec2-user/AI-Agent-Crawler \
  --run-user ec2-user \
  --port 8000
```

상태 확인:

```bash
sudo systemctl status ai-crawler-live
curl http://127.0.0.1:8000/health
```

로그 확인:

```bash
sudo journalctl -u ai-crawler-live -f
```

## 3) Nginx(선택)

퍼블릭 노출이 필요하면 Nginx reverse proxy를 추가합니다.

```bash
sudo cp deploy/aws/nginx-live-service.conf /etc/nginx/conf.d/ai-crawler-live.conf
sudo nginx -t
sudo systemctl restart nginx
```

TLS는 ALB 또는 certbot으로 별도 구성하세요.
