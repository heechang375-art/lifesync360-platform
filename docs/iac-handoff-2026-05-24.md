# IaC 변경/추가 작업 핸드오프 — 2026-05-24

IaC repo: `Aws_iac/Aws_iac/` (별도 git, ls 메인 repo의 `.gitignore`로 분리됨)
대상 계정: 354 (`354493396671`) · ap-northeast-2 · 활성 스택 12개

---

## 1. 기존 파일 수정 — diff 확인 후 commit/배포

IaC repo의 working tree에 modified 상태로 남아있음 (`git diff --stat templates/`).

| 파일 | 변경 줄 수 | 변경 요지 |
|------|-----------|-----------|
| `templates/01b-lifesync-vpc-endpoints.yaml` | 38 | (담당자 diff 검토 필요) |
| `templates/08-database.yaml` | 240 | SqlOps 관련 재구조 |
| `templates/08b-lifesync360-service-db.yaml` | 10 | (담당자 diff 검토 필요) |
| `templates/19-cicd-service-platform.yaml` | 54 | (담당자 diff 검토 필요) |
| `templates/21-lifesync-ecs-existing-vpc.yaml` | 212 | ECS ExecutionRole 안정화 |

→ 담당자가 `git diff templates/` 검토 후 commit + 배포.

---

## 2. 신규 파일 add — untracked 상태에서 신규 적용

`git status` 결과 untracked. 핵심 3개:

| 파일 | 적용 내용 |
|------|-----------|
| `templates/01-network.yaml` | Management VPC admin private subnet `10.4.20.0/24` (`AdminSubnetCidr` 파라미터), Management private RT → TGW 라우트 추가 |
| `templates/24-admin-windows-ec2.yaml` | admin EC2 신규 (Windows Server 2022). cross-VPC SG 참조 대신 `CidrIp`로 변경 — 트러블슈팅 #31 (DELETE_FAILED) 해결 |
| `templates/27-onprem-simulator.yaml` | OnpremSim EC2 (단, 3번 권한 패치 #22 / #24 / #26 추가 필요) |

> 그 외 untracked yaml 다수 (`01c/02/03/04/05/06/07/09/10/11/12/13/14a/14b/14c/16/20-foundation/22/23/25/26/28` 등) — IaC repo 차원에서 add 정책 확인 필요.

---

## 3. 권한 이슈 IaC 미반영 — 추가 패치 5건

이전 세션에서 `aws iam put-role-policy` / `aws ec2 authorize-security-group-ingress`로 **수동** 해결 → 템플릿에 안 박혀있어서 재배포 시 깨짐. IaC에 박아두기 필수.

### 3.1 #10 — ECS ExecutionRole `kms:Decrypt` 누락 (SSM SecureString fetch 실패)

**대상 파일**: `templates/21-lifesync-ecs-existing-vpc.yaml`
**위치**: ExecutionRole inline policy (현재 `ssm:GetParameters`만 있음, `:261-263` 부근)

추가 statement:
```yaml
- Effect: Allow
  Action: kms:Decrypt
  Resource: "*"
  Condition:
    StringEquals:
      kms:ViaService: !Sub "ssm.${AWS::Region}.amazonaws.com"
```

### 3.2 #11 — VPC KMS Interface Endpoint 미생성

**대상 파일**: `templates/01b-lifesync-vpc-endpoints.yaml`
**현재 상태**: s3 / ecr.api / ecr.dkr / ecs / ecs-agent / ecs-telemetry / logs / sts 만 존재. KMS 없음.

신규 추가:
```yaml
KmsVpce:
  Type: AWS::EC2::VPCEndpoint
  Properties:
    VpcEndpointType: Interface
    PrivateDnsEnabled: true
    VpcId: !Ref LifeSyncVpcId
    ServiceName: !Sub "com.amazonaws.${AWS::Region}.kms"
    SubnetIds: !Ref AppPrivateSubnetIds   # 기존 endpoints와 동일 패턴
    SecurityGroupIds: [!Ref LifeSyncEndpointsSg]
    Tags:
      - Key: Name
        Value: lifesync-vpc-endpoints-kms
```

> 3.1 + 3.2 는 짝. 둘 다 박아야 ECS task가 SSM SecureString 정상 복호화.

### 3.3 #22 — OnpremSimRole `lambda:InvokeFunction` 누락 (로그인 503)

**대상 파일**: `templates/27-onprem-simulator.yaml`
**위치**: `OnpremSimRole.Policies[0].PolicyDocument.Statement` (현재 `secretsmanager:GetSecretValue` + `s3:GetObject/ListBucket` 만 있음, `:81-93` 부근)

추가 statement:
```yaml
- Effect: Allow
  Action: lambda:InvokeFunction
  Resource: !Sub "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:lifesync-onprem-customer-query"
```

### 3.4 #24 — OnpremSimRole DynamoDB 권한 누락

**대상 파일**: `templates/27-onprem-simulator.yaml`
**위치**: 위와 동일 inline policy

추가 statement:
```yaml
- Effect: Allow
  Action:
    - dynamodb:Query
    - dynamodb:GetItem
    - dynamodb:Scan
  Resource: !Sub "arn:aws:dynamodb:${AWS::Region}:${AWS::AccountId}:table/lifesync_customer_result"
```

> 키 스키마는 `global_id HASH + update_time RANGE` — 어플리케이션은 `Query`로 호출 (`GetItem`은 ValidationException 발생).

### 3.5 #26 — Aurora/Redis SG 인바운드에 OnpremSim SG 미허용

**대상 파일**: `templates/08-database.yaml` (또는 `templates/27-onprem-simulator.yaml`에서 별도 `AWS::EC2::SecurityGroupIngress`로 분리)
**현재 상태**: `SqlSsmAccessEc2Sg` 에서만 인바운드 허용 (`08-database.yaml:187-195`). OnpremSim SG 없음.

추가 (cross-stack import 패턴 권장 — `27-onprem-simulator.yaml`에서 `08-database`의 SG ID를 Output으로 받아 별도 ingress 리소스 생성):

```yaml
# templates/27-onprem-simulator.yaml 끝에 추가
AuroraSgFromOnpremSim:
  Type: AWS::EC2::SecurityGroupIngress
  Properties:
    GroupId: !Ref DbSgId              # 08-database export 받는 파라미터
    IpProtocol: tcp
    FromPort: 3306
    ToPort: 3306
    SourceSecurityGroupId: !Ref OnpremSimSg
    Description: Aurora MySQL from onprem simulator EC2

RedisSgFromOnpremSim:
  Type: AWS::EC2::SecurityGroupIngress
  Properties:
    GroupId: !Ref RedisSgId           # 08-database export 받는 파라미터
    IpProtocol: tcp
    FromPort: 6379
    ToPort: 6379
    SourceSecurityGroupId: !Ref OnpremSimSg
    Description: Redis from onprem simulator EC2
```

---

## 4. Audit에서 발견된 보안 이슈

### 4.1 `admin123` 비밀번호 하드코딩

**파일**: `templates/24-admin-windows-ec2.yaml:226, 281, 288, 319`

현재:
```powershell
net user Administrator "admin123"
...
"set ADMIN_PASSWORD=admin123",
```

Windows 비밀번호 복잡성 기본 정책(8자 + 대/소/숫자/특수 중 3가지)에서 `admin123`은 소문자+숫자 2 카테고리 → 정책 ON 상태면 `net user` 조용히 실패 가능.

**권장**: Secrets Manager 분리.

Parameters 추가:
```yaml
AdminPasswordSecretArn:
  Type: String
  Description: lifesync/admin Secrets Manager ARN (username/password/secret_key 키 보관)
  Default: ""
```

IAM Role policy에 `secretsmanager:GetSecretValue` (`lifesync/admin-*`) 추가 + UserData 내부에서 fetch:
```powershell
$secretJson = aws secretsmanager get-secret-value --secret-id $env:AdminPasswordSecretArn --query SecretString --output text
$secret = $secretJson | ConvertFrom-Json
net user Administrator "$($secret.password)"
```

start-admin.bat의 `ADMIN_PASSWORD`도 동일 방식으로 환경변수 주입.

### 4.2 Outbound `0.0.0.0/0` (정보)

**파일**: `templates/24-admin-windows-ec2.yaml:134, 139, 144, 149`
443 / 80 / 53 TCP / 53 UDP outbound 0.0.0.0/0.

Chocolatey / Chrome / Python 패키지 다운로드 필요 → 시연 환경은 OK. 운영 단계라면 VPC Endpoint + 미러 화이트리스트로 좁히기.

---

## 5. 보류 / 별도 결정 사항

- 2026-05-22 삭제된 스택 (`15-cicd`, `25-customer-profile-sync-lambda`, `28-gcp-phz`, `17/18/19-cicd-*`, `gha-cc-*` 6개) 재배포 여부 결정 필요.
- `01-network.yaml` 스택 업데이트 → admin subnet 생성 → 그 뒤 `24-admin-windows-ec2` 신규 배포 순서.
- 트러블슈팅 #11 기록상 `SqlOpsSsmVpceSg` 에 `CidrIp: 10.0.0.0/16` 443 inbound 추가가 있었으나, 현재 코드는 `SourceSecurityGroupId: SqlSsmAccessEc2Sg` 만 허용. `CreateSqlOpsMysqlEc2=false` 운영 상태라 영향 없음 — 향후 true 복귀 시 인지 필요.

---

## 한 줄 요약

> "1번 5개 modified diff 확인 후 commit / 2번 untracked 3개(`01-network`/`24-admin-windows-ec2`/`27-onprem-simulator`) add / 3번 권한 패치 5건(`kms:Decrypt`, KMS endpoint, `lambda:InvokeFunction`, DDB, Aurora·Redis SG 인바운드) 추가 / 4번 `admin123` Secrets Manager로 분리. 안 박으면 재배포 시 다시 권한 깨짐."
