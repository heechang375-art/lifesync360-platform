# LifeSync360 (2조 · Antique Archive)

AWS·GCP·온프레미스를 잇는 하이브리드 멀티클라우드 고객 데이터 플랫폼.
클라우드에서 온프레미스 고객 DB를 조회해 고객 프로파일·건강점수·교차판매 추천을 처리한다.

## 아키텍처

### AWS (Hybrid + Multi Cloud)

![AWS 아키텍처 구성도](docs/architecture.png)

- **AWS** — ECS(Flask 앱) · Aurora · DynamoDB · Lambda(온프렘 연동/집계) · VPC·TGW·VPN
- **On-Prem** — 고객 원천 DB(MySQL)·토큰화/마스킹 서버, Site-to-Site VPN으로 AWS와 연동

### GCP

![GCP 아키텍처 구성도](docs/architecture-gcp.png)

- **데이터 파이프라인** — GCS Bucket → Dataflow → BigQuery → Vertex AI(배치 예측)
- **연동** — Storage Transfer Service로 AWS S3 적재, Cloud VPN으로 AWS와 연결

---

## 팀 전달 / 온보딩

이 저장소가 전체 인계 패키지입니다 — 코드(platform · admin · Service-DB · lambda · onprem-prod-repo) + 문서 + 아키텍처 구성도.

```bash
git clone https://github.com/heechang375-art/lifesync360-platform.git
```

먼저 **[`docs/README.md`](docs/README.md)** 를 여세요 — 전체 문서를 상태별(📖 상시 레퍼런스 / ✅ 완료 이력 / 📦 작성완료·미실행)로 분류한 지도입니다.

> ℹ️ 프로젝트는 종료된 상태입니다. 구축·코드는 완료, 전체 CloudFormation 스택 실배포는 미실행으로 마감됐습니다.

### 별도 수령 필요 (보안 채널)

민감정보는 `.gitignore`로 저장소에서 제외돼 있습니다. 실제 구동·배포 시 아래 값을 **보안 채널로 별도 수령**하세요:

- Ansible Vault 패스워드 · Fernet PII 키 · MySQL 비밀번호
- Secrets Manager 값 (`lifesync/aurora` · `lifesync/jwt` · `lifesync/redis` · `lifesync/admin`)
