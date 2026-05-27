# IaC 담당자 전달 — 2026-05-27

> 이전 전달분: `docs/iac-handoff-2026-05-24.md`
> 이번 전달분에서 수정된 파일 6개가 동봉됨 (CloudFormation 템플릿 3개 + admin CI/CD 파일 3개).

---

## 변경 요약

### CloudFormation 템플릿

| 파일 | 변경 내용 | 스택 상태 |
|------|-----------|-----------|
| `21-lifesync-ecs-existing-vpc.yaml` | EcsExecutionRole에 `kms:Decrypt` 추가 | **스택 적용 완료** ✓ |
| `01b-lifesync-vpc-endpoints.yaml` | KMS VPC Interface Endpoint 신규 추가 | **스택 미존재 — 신규 배포 필요** |
| `27-onprem-simulator.yaml` | OnpremSimRole 권한 + Aurora/Redis SG 인바운드 추가 | **스택 미존재 — 신규 배포 필요** |

### Admin 배포 파이프라인 (신규 구성)

| 파일 | 변경 내용 |
|------|-----------|
| `appspec.yml` | CodeDeploy 배포 스펙 신규 작성 (Windows, `C:\admin-platform`) |
| `scripts/after_install.ps1` | AfterInstall 훅 — Python 프로세스 종료 후 `start-admin.bat` 재시작 |
| `.github/workflows/admin.yml` | GitHub Actions → CodeCommit 미러링 워크플로우 |

---

## ① 21-lifesync-ecs-existing-vpc.yaml

**변경 목적**: ECS Task가 SSM SecureString 파라미터를 읽을 때 KMS 복호화 권한 없어서 실패하는 문제 해결.

**변경 위치**: `EcsExecutionRole` > `Policies` > `InlinePolicy` > `Statement` 에 아래 추가

```yaml
- Sid: KmsDecryptForSsmSecureString
  Effect: Allow
  Action: kms:Decrypt
  Resource: "*"
  Condition:
    StringEquals:
      kms:ViaService: !Sub "ssm.${AWS::Region}.amazonaws.com"
```

**스택 현황**: `lifesync-dev-21-lifesync-ecs-existing-vpc-v4` — UPDATE_COMPLETE (이미 적용됨)
**담당자 조치**: 없음 (이미 완료)

---

## ② 01b-lifesync-vpc-endpoints.yaml

**변경 목적**: ECS Task가 Private Subnet에서 KMS API를 호출할 수 있도록 VPC Interface Endpoint 추가. 위 ①의 kms:Decrypt 권한이 있어도 KMS endpoint가 없으면 Private Subnet에서 호출 불가.

**변경 위치**: `Outputs` 섹션 바로 앞에 아래 리소스 추가

```yaml
LifeSyncVpceKms:
  Type: AWS::EC2::VPCEndpoint
  Properties:
    VpcEndpointType: Interface
    PrivateDnsEnabled: true
    VpcId: !Ref LifeSyncVpcId
    ServiceName: !Sub "com.amazonaws.${AWS::Region}.kms"
    SubnetIds:
      - !Ref LifeSyncAppPrivateSubnetAId
      - !Ref LifeSyncAppPrivateSubnetBId
    SecurityGroupIds:
      - !Ref LifeSyncVpceSg
```

**스택 현황**: `lifesync-dev-01b-*` 스택이 현재 **존재하지 않음**
**담당자 조치**: 신규 스택 배포 필요
```bash
aws cloudformation create-stack \
  --stack-name lifesync-dev-01b-lifesync-vpc-endpoints \
  --template-body file://01b-lifesync-vpc-endpoints.yaml \
  --parameters ... \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-2
```

---

## ③ 27-onprem-simulator.yaml

**변경 목적**: On-Prem 시뮬레이터 Lambda가 고객조회 Lambda 호출 + DynamoDB 읽기 + Aurora/Redis 접근 가능하도록 권한/SG 인바운드 추가.

### 파라미터 3개 신규 추가

```yaml
DbSgId:
  Type: AWS::EC2::SecurityGroup::Id
  Description: Aurora DB Security Group ID

RedisSgId:
  Type: AWS::EC2::SecurityGroup::Id
  Description: Redis Security Group ID

OnpremQueryLambdaArn:
  Type: String
  Default: ""
  Description: (Optional) lifesync-onprem-customer-query Lambda ARN
```

### Condition 신규 추가

```yaml
HasOnpremQueryLambda: !Not [!Equals [!Ref OnpremQueryLambdaArn, ""]]
```

### OnpremSimRole에 추가된 권한

```yaml
- Effect: Allow
  Action: lambda:InvokeFunction
  Resource: !If
    - HasOnpremQueryLambda
    - !Ref OnpremQueryLambdaArn
    - !Sub "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:lifesync-onprem-customer-query"
- Effect: Allow
  Action:
    - dynamodb:Query
    - dynamodb:GetItem
    - dynamodb:Scan
  Resource: !Sub "arn:aws:dynamodb:${AWS::Region}:${AWS::AccountId}:table/lifesync_customer_result"
```

### SG 인바운드 리소스 2개 신규 추가

```yaml
AuroraIngressFromOnpremSim:
  Type: AWS::EC2::SecurityGroupIngress
  Properties:
    GroupId: !Ref DbSgId
    IpProtocol: tcp
    FromPort: 3306
    ToPort: 3306
    SourceSecurityGroupId: !Ref OnpremSimSg
    Description: Allow Aurora access from OnpremSim Lambda

RedisIngressFromOnpremSim:
  Type: AWS::EC2::SecurityGroupIngress
  Properties:
    GroupId: !Ref RedisSgId
    IpProtocol: tcp
    FromPort: 6379
    ToPort: 6379
    SourceSecurityGroupId: !Ref OnpremSimSg
    Description: Allow Redis access from OnpremSim Lambda
```

**스택 현황**: 스택이 현재 **존재하지 않음**
**담당자 조치**: 신규 스택 배포 필요 (파라미터 `DbSgId`, `RedisSgId` 실제 SG ID로 채워서 배포)

---

## ④ Admin 배포 파이프라인 (신규 구성)

**배포 흐름**: GitHub push (`admin-platform/**`) → GitHub Actions 미러 (~60s) → CodeCommit `lifesync-admin-platform` → CodePipeline `admin-platform-pipeline` → CodeBuild → CodeDeploy → EC2 `i-0099e31b62d8a8ceb`

**배포 대상**: EC2 `i-0099e31b62d8a8ceb` (스택 `lifesync-dev-26-admin-windows-ec2`), 경로 `C:\admin-platform`

### appspec.yml (신규)

```yaml
version: 0.0
os: windows
files:
  - source: app.py
    destination: C:\admin-platform
  - source: wearable_engine.py
    destination: C:\admin-platform
  - source: templates
    destination: C:\admin-platform\templates
  - source: static
    destination: C:\admin-platform\static
file_exists_behavior: OVERWRITE
hooks:
  AfterInstall:
    - location: scripts\after_install.ps1
      timeout: 60
```

### scripts/after_install.ps1 (재작성)

기존: Flask `debug=False`로 인해 파일 변경 후 자동 리로드 안 됨 → 배포해도 반영 안 되는 문제
수정: Python 프로세스 강제 종료 후 `start-admin.bat`으로 재시작

```powershell
$ErrorActionPreference = 'Continue'
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-Process cmd -ArgumentList '/c C:\start-admin.bat' -WindowStyle Hidden
Write-Host "Flask restarted via start-admin.bat"
```

### .github/workflows/admin.yml 변경점

- `mirror-to-codecommit` job: `if: false` → `if: github.ref == 'refs/heads/main'` (미러링 활성화)
- 대상 repo: `lifesync-admin-platform`
- `git subtree split --prefix=admin-platform`으로 서브폴더만 추출해서 push

**파이프라인 트리거**: `PollForSourceChanges: true` (1분 폴링, 다른 파이프라인과 동일)

---

## 미반영 권한 이슈 현황

| # | 항목 | 상태 |
|---|------|------|
| #10 | ECS ExecutionRole `kms:Decrypt` | **IaC 반영 + 스택 적용 완료** ✓ |
| #11 | VPC KMS Interface Endpoint | IaC 반영 완료, **스택 미존재 — 01b 신규 배포 필요** |
| #22 | OnpremSimRole `lambda:InvokeFunction` | IaC 반영 완료, **스택 미존재 — 27 신규 배포 필요** |
| #24 | OnpremSimRole DynamoDB Query/GetItem/Scan | IaC 반영 완료, **스택 미존재 — 27 신규 배포 필요** |
| #26 | Aurora/Redis SG ← OnpremSim SG 인바운드 | IaC 반영 완료, **스택 미존재 — 27 신규 배포 필요** |

---

*작성일: 2026-05-27 | 담당: admin-platform 세션*
