# 해커톤 검증용 공개 페이지

사용자 요청에 따른 임시 무인증 공개다. 운영 배포가 아니며 공개 방문자도
로컬 담당자와 같은 시연 실행/사건/설정을 공유한다. 영상 시연 시작과 등록 변경은
API 사용량이나 저장 데이터를 변경할 수 있다. 검증이 끝나면 서비스를 중지한다.

## 연결

공개 HTTPS → Cloudflare Quick Tunnel → Nginx `127.0.0.1:18865`
→ 기존 관제 `127.0.0.1:8765`.

- 로그인, 검증 코드, IP 제한을 추가하지 않는다.
- 모든 화면과 영상/사건/등록/실행/전화 기록을 제공한다.
- 실제 전화 발신 `/api/phone/test`, `/api/phone/calls`는 외부에서만 403이다.
  발신까지 공개하는 별도 승인이 없으므로 전화 화면 열람과 실제 발신을 구분한다.
  기존 로컬 담당자 페이지의 발신은 변경하지 않는다.
- 환경 파일/숨김 경로는 404다. Nginx에 작업공간 전체, 키, DB를 마운트하지 않는다.
- HTTP Range와 API 응답을 그대로 전달하고 응답 버퍼링을 끈다.
- 자동 전화 설정은 false를 유지한다. 이를 켜면 공개 시연도 자동 사건 발신을
  유발할 수 있으므로 이 공개 구성에서 켜지 않는다.
- 기존 카탈로그 터널, Tailscale, CVAT, 관제 서비스는 변경하지 않는다.

## 설치 기록

Docker 공식 Nginx stable-alpine 이미지를 아래 digest로 고정했다.
컨테이너는 UID 101, 읽기 전용 루트, capability 없음, 임시 디렉터리만 쓰기 가능하다.

```bash
docker create --name chemiguard-public-nginx --network host --read-only \
  --tmpfs /tmp:size=64m --cap-drop ALL --security-opt no-new-privileges \
  --user 101:101 \
  --mount "type=bind,src=$PWD/deploy/nginx-public.conf,dst=/etc/nginx/nginx.conf,readonly" \
  --entrypoint nginx \
  nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94 \
  -g 'daemon off;'
```

`chemiguard-monitor-public.service`는 `~/.config/systemd/user/`에 설치했다.
실행 파일은 기존 `~/.local/bin/cloudflared`다. 사용자 서비스로 실행하되
임시 공개이므로 부팅 자동 시작(enable)은 설정하지 않았다.

```bash
systemctl --user start chemiguard-monitor-public
journalctl --user -u chemiguard-monitor-public --no-pager -o cat
systemctl --user stop chemiguard-monitor-public
```

마지막 명령은 터널과 전용 Nginx 컨테이너만 중지한다. 관제/카탈로그는 계속 실행된다.
Nginx 설정 변경 시 `docker restart chemiguard-public-nginx`로 bind 파일과 설정을
다시 읽는다. 터널을 재시작할 필요는 없다.

Quick Tunnel의 임의 URL은 터널 재시작 시 바뀔 수 있다. 서버와 서비스가 실행 중이어야
하며 정식 가용성 보장은 없다. 현재 URL과 실제 화면 캡처는 공개 Git이 아닌
`.data/public-demo/`에 보존한다.

구성 근거: [Nginx proxy](https://nginx.org/en/docs/http/ngx_http_proxy_module.html),
[Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
