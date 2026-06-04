# LifeSync360 문서 가이드 (팀 공유용)

> 프로젝트는 **종료**되었습니다. 이 문서는 팀 인계를 위한 **문서 지도**입니다.
> 추가 클라우드 배포/온프레미스 재구축 계획은 없으며, 아래 분류의 **상태 배지**로 각 문서가 "지금도 참조하는 자료"인지 "완료된 작업의 기록"인지 구분했습니다.
>
> - 📖 **상시 레퍼런스** — 시스템 이해/운영에 계속 참조
> - ✅ **완료 이력** — 해당 작업이 끝남, 재현·참고용 기록
> - 📦 **작성완료·미실행** — 문서는 완성됐으나 전체 배포는 실행 안 됨 (배포하려면 참조)

---

## 1. 시스템 레퍼런스 📖 (먼저 볼 것)

| 문서 | 내용 |
|------|------|
| [`../README.md`](../README.md) | 프로젝트 개요 + AWS/GCP 아키텍처 구성도 |
| [`../schema_reference.md`](../schema_reference.md) | 온프레미스 MySQL 스키마 (고객·PII·동의) |
| [`../Aurora_Schema_Reference.md`](../Aurora_Schema_Reference.md) | AWS Aurora 스키마 (추천·상품·캠페인) |
| [`../sql-reference.md`](../sql-reference.md) | SQL / DynamoDB 쿼리 모음 |
| [`private-api.md`](private-api.md) | On-Prem PrivateAPI 엔드포인트 명세 (21개) |
| [`admin-api.md`](admin-api.md) | Admin Dashboard API 명세 (23개) |
| [`admin-data-flow.md`](admin-data-flow.md) | Admin 데이터 흐름 (Read API ↔ Write 적재) — 최신·정확 |
| [`lifesync360-platform-app-guide.md`](lifesync360-platform-app-guide.md) | platform `app.py` 구조 (JWT·추천 엔진) |
| [`admin-platform-app-guide.md`](admin-platform-app-guide.md) | admin `app.py` 구조 (초기화·헬퍼·라우트) |
| [`../troubleshooting.md`](../troubleshooting.md) | **트러블슈팅 통합 허브** — 온프레미스 인프라 + 플랫폼/앱 증상별 해결 (CI/CD는 `cicd-troubleshooting-and-iac-tasks.md`) |

## 2. 구축 이력 ✅ (완료 — 재현·참고용)

| 문서 | 내용 |
|------|------|
| [`../온프렘_서버_세팅가이드.md`](../온프렘_서버_세팅가이드.md) | 온프레미스 VM 3대 구축 (VirtualBox·netplan·MySQL/nginx) |
| [`../project-progress.md`](../project-progress.md) | 전체 진행 기록 + 온프레미스 구축 Runbook |
| [`../pii-encryption-guide.md`](../pii-encryption-guide.md) | PII 암호화 적용 (Fernet·Ansible Vault) |
| [`../aws-vpn-setup.md`](../aws-vpn-setup.md) | Site-to-Site VPN 구축 (BGP·StrongSwan) |

## 3. 배포 · IaC 📦 (작성완료, 전체 스택 배포는 미실행)

| 문서 | 내용 |
|------|------|
| [`../cloud-deploy-procedure.md`](../cloud-deploy-procedure.md) | CloudFormation 스택 배포 순서 |
| [`../ecs-cicd-guide.md`](../ecs-cicd-guide.md) | ECS CI/CD 파이프라인 구성 가이드 |
| [`control-node-deploy-guide.md`](control-node-deploy-guide.md) | Ansible Control Node 배포 (14a/14b/14c) |
| [`ecs-taskdef-redeploy.md`](ecs-taskdef-redeploy.md) | ECS Task Definition 재등록·재배포 |
| [`iac-ecs-taskdef-spec.md`](iac-ecs-taskdef-spec.md) | ECS Task Definition 정합 명세 (platform+admin) |
| [`iac-consent-filter-lambda.md`](iac-consent-filter-lambda.md) | consent_filter Lambda 배포 + 온프렘 네트워크 연동 |
| [`lambda-onprem-query-deploy.md`](lambda-onprem-query-deploy.md) | onprem-customer-query Lambda 배포 |
| [`glue-emr-consent-spec.md`](glue-emr-consent-spec.md) | Glue/EMR 동의 고객 필터 연동 스펙 |
| [`iac-handoff-2026-05-24.md`](iac-handoff-2026-05-24.md) | IaC 변경/추가 핸드오프 (5-24, 작업지시 원문) |
| [`iac-handoff-2026-05-27.md`](iac-handoff-2026-05-27.md) | IaC 담당자 전달 (5-27, 진행상황 갱신) |
| [`cicd-troubleshooting-and-iac-tasks.md`](cicd-troubleshooting-and-iac-tasks.md) | Platform CI/CD 트러블슈팅 모음 |
| [`../cloud-infra-todo.md`](../cloud-infra-todo.md) | 클라우드 운영 강화 과제 (Lambda 인증·DLQ·알람 등, 미실행) |
| [`../lambda-to-onprem-network.md`](../lambda-to-onprem-network.md) | ⚠️ 옛 구조(Service DB/Data VPC) 기준 — 상단 경고 참조 |

### 관련 설정 파일
- `new-taskdef.json` / `new-taskdef-admin.json` — ECS Task Definition
- `codebuild-role-policy.json` — CodeBuild IAM 정책

## 4. 운영 · 분석

| 문서 | 내용 |
|------|------|
| [`cost-analysis.md`](cost-analysis.md) | 100만명 기준 월 비용 분석 |
| [`../admin-platform-query-audit-2026-05-23.md`](../admin-platform-query-audit-2026-05-23.md) | admin 쿼리·스키마 정합 감사 |
| [`demo-removed-items-rollout.md`](demo-removed-items-rollout.md) | 시연용 제거 항목 + 운영 전환 가이드 |
| [`update-checklist.md`](update-checklist.md) | 문서/설계서 현행화 체크리스트 |

## 5. 프로젝트 관리

| 문서 | 내용 |
|------|------|
| [`../HANDOFF.md`](../HANDOFF.md) | 세션별 인수인계 (최신 상태·남은 작업) |
| [`../project-progress.md`](../project-progress.md) | 전체 진행 기록 (현황표·세션 이력) |
