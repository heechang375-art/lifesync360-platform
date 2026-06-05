# ECS CI/CD 파이프라인 구성 가이드

## 전체 흐름

```
개발자 → GitHub push (main)
    ↓
GitHub Actions (ci.yml)
  - 테스트 / 보안 스캔 / Docker 빌드 검증
  - CodeCommit으로 미러링
    ↓
CodePipeline (AWS, CodeCommit push로 자동 트리거)
  ├── Source: CodeCommit
  ├── Build:  CodeBuild (buildspec.yml → Docker 빌드 → ECR push)
  └── Deploy: CodeDeploy Blue/Green → ECS 서비스 업데이트
```

---

## 대상 파이프라인 2개

| 파이프라인 | 소스 레포 | ECS 서비스 | ECR 레포 | 배포 방식 |
|-----------|----------|-----------|---------|---------|
| lifesync-pipeline-platform | lifesync360-platform | lifesync-platform-service | lifesync360-platform | Blue/Green (CodeDeploy) |
| lifesync-pipeline-admin    | lifesync360-admin    | lifesync-admin-service    | lifesync360-admin    | Rolling (ECS)           |

---

## 1단계 — GitHub Secrets 등록

두 레포 모두 동일하게 등록:

```
GitHub 레포 → Settings → Secrets and variables → Actions → New repository secret
```

| Secret 이름 | 값 |
|------------|-----|
| AWS_ACCESS_KEY_ID | IAM 사용자 액세스 키 |
| AWS_SECRET_ACCESS_KEY | IAM 사용자 시크릿 키 |

> IAM 사용자에 필요한 권한: `codecommit:GitPush`, `codecommit:GetRepository`

---

## 2단계 — AWS Parameter Store 등록

CodeBuild가 buildspec.yml에서 ECR URI를 읽어오는 용도.

```
AWS 콘솔 → Systems Manager → Parameter Store → Create parameter
```

| 파라미터 이름 | 값 |
|-------------|-----|
| `/lifesync360/ecr-uri`       | `<ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/lifesync360-platform` |
| `/lifesync360/ecr-uri-admin` | `<ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/lifesync360-admin`    |

---

## 3단계 — ECR 레포지토리 생성 (IaC or 콘솔)

```
AWS 콘솔 → ECR → Create repository
```

| 레포 이름 | 설정 |
|----------|------|
| lifesync360-platform | Private, Mutable |
| lifesync360-admin    | Private, Mutable |

---

## 4단계 — CodeCommit 레포지토리 생성 (IaC or 콘솔)

```
AWS 콘솔 → CodeCommit → Create repository
```

| 레포 이름 |
|----------|
| lifesync360-platform |
| lifesync360-admin    |

> 생성 후 GitHub Actions ci.yml의 CodeCommit URL과 일치하는지 확인

---

## 5단계 — CodeBuild 프로젝트 생성 (IaC)

각 플랫폼별로 생성. 공통 설정:

| 항목 | 값 |
|------|-----|
| Source | CodeCommit (해당 레포) |
| Branch | main |
| 환경 이미지 | aws/codebuild/standard:7.0 |
| 권한 | Privileged (Docker 빌드 필수) |
| Service Role | CodeBuildServiceRole |
| Buildspec | 레포 루트의 buildspec.yml |

CodeBuild Service Role 추가 권한:
- `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`
- `ssm:GetParameters` (Parameter Store 읽기)

---

## 6단계 — CodeDeploy 앱 + 배포그룹 생성 (IaC)

Blue/Green 배포를 위한 설정.

| 항목 | platform | admin |
|------|---------|-------|
| App 이름 | lifesync-platform-app | lifesync-admin-app |
| 배포그룹 | lifesync-platform-dg | lifesync-admin-dg |
| 배포 유형 | Blue/Green | Blue/Green |
| ECS Cluster | lifesync-cluster | lifesync-cluster |
| ECS Service | lifesync-platform-service | lifesync-admin-service |
| ALB | platform-alb | admin-alb (내부) |
| 리스너 포트 | 80 (Blue), 8080 (Green 테스트) | 80 (Blue), 8080 (Green 테스트) |

---

## 7단계 — CodePipeline 생성 (IaC)

각 플랫폼별로 생성.

**스테이지 구성:**

```
[Source]  CodeCommit → 브랜치: main
    ↓
[Build]   CodeBuild 프로젝트 (buildspec.yml 실행)
    ↓
[Deploy]  CodeDeploy Blue/Green
          - appspec.yaml
          - taskdef.json
          - imagedefinitions.json
```

---

## 8단계 — Secrets Manager 등록

| Secret 이름 | 키 | 용도 |
|------------|-----|------|
| `lifesync/aurora` | host, user, password | Aurora 접속 정보 |
| `lifesync/jwt`    | secret | JWT 서명 키 |
| `lifesync/redis`  | host | ElastiCache 엔드포인트 |
| `lifesync/admin`  | secret_key, username, password | 어드민 로그인 정보 |

---

## 최초 1회 — ECR 부트스트랩

별도 작업 불필요.

`ecs-platform.yaml` / `ecs-admin.yaml`의 초기 Task Definition은 `public.ecr.aws/docker/library/python:3.11-slim`을 직접 참조한다.
`DesiredCount: 0`이므로 이미지 pull은 실제로 일어나지 않고, Private ECR도 비어 있어도 된다.

GitHub main 브랜치에 push → CodePipeline 첫 실행 시:
1. CodeBuild가 실제 앱 이미지를 빌드해 Private ECR에 push
2. buildspec.yml의 `update-service --desired-count 1` 실행
3. CodeDeploy가 `taskdef.json`의 `<IMAGE1_NAME>`을 Private ECR URI로 치환해 새 Task Definition 등록 및 배포

---

## 배포 검증 순서

```bash
# 1. GitHub push → Actions 탭에서 ci.yml 성공 확인
# 2. AWS CodePipeline 콘솔에서 파이프라인 진행 상태 확인
# 3. CodeBuild 로그: Docker 빌드 + ECR 푸시 확인
# 4. CodeDeploy: Blue/Green 트래픽 전환 확인
# 5. ECS 서비스: Running task 수 정상 확인

# health check
curl https://platform.lifesync360.com/health
curl https://admin.lifesync360.com/health
```

---

## 현재 진행 상태

### lifesync360-platform
- [x] GitHub Actions ci.yml (test + mirror)
- [x] Dockerfile
- [x] buildspec.yml
- [x] appspec.yaml
- [x] taskdef.json
- [ ] ECR 레포 생성 (IaC)
- [ ] CodeBuild 프로젝트 (IaC)
- [ ] CodeDeploy 앱/배포그룹 (IaC)
- [ ] CodePipeline (IaC)
- [ ] Secrets Manager 값 입력

### lifesync360-admin
- [x] GitHub Actions ci.yml (test + mirror)
- [x] Dockerfile
- [x] buildspec.yml  ← 오늘 추가
- [x] appspec.yaml  ← 오늘 추가
- [x] taskdef.json  ← 오늘 추가
- [ ] ECR 레포 생성 (IaC)
- [ ] CodeBuild 프로젝트 (IaC)
- [ ] CodeDeploy 앱/배포그룹 (IaC)
- [ ] CodePipeline (IaC)
- [ ] Secrets Manager 값 입력
