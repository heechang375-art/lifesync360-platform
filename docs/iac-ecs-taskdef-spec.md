# IaC ECS Task Definition 정합 명세 (platform + admin)

> **목적**: 현재 `lifesync360-platform/taskdef.json` / `admin-platform/taskdef.json`에 박힌 정합을 IaC(CloudFormation)에 영구 반영하기 위한 명세
> **현재 상태**: buildspec에서 임시로 `register-task-definition` 실행 중 — IaC 스택 재배포 시 덮어쓰일 수 있음
> **이 문서대로 IaC 반영 시 buildspec의 register 부분 제거 가능**

---

## 1. ECS Task Definition (platform)

```yaml
PlatformTaskDef:
  Type: AWS::ECS::TaskDefinition
  Properties:
    Family: lifesync-dev-21-lifesync-ecs-existing-vpc-v4-td
    Cpu: '512'
    Memory: '1024'
    NetworkMode: awsvpc
    RequiresCompatibilities: [FARGATE]
    ExecutionRoleArn: !GetAtt EcsTaskExecutionRole.Arn   # 또는 기존 Role 참조
    TaskRoleArn: !GetAtt EcsPlatformTaskRole.Arn
    ContainerDefinitions:
      - Name: app                                          # service LB가 기대하는 이름
        Image: !Sub '${AWS::AccountId}.dkr.ecr.${AWS::Region}.amazonaws.com/lifesync-dev-lifesync-service:latest'
        PortMappings:
          - ContainerPort: 80                              # Gunicorn binding
            Protocol: tcp
        Essential: true
        Environment:
          - { Name: AWS_REGION,           Value: !Ref AWS::Region }
          - { Name: DB_NAME,              Value: lifesync360 }
          - { Name: DYNAMO_TABLE,         Value: lifesync_customer_result }
          - { Name: REDIS_PORT,           Value: '6379' }
          - { Name: ONPREM_QUERY_LAMBDA,  Value: lifesync-onprem-customer-query }
        Secrets:
          - Name: JWT_SECRET
            ValueFrom: !Sub 'arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/lifesync360/jwt-secret'
          # 운영 전환 시 추가할 secrets (현재는 dev fallback / 미사용):
          # - { Name: AURORA_HOST, ValueFrom: 'arn:aws:secretsmanager:<region>:<account>:secret:<aurora-master-secret>:host::' }
          # - { Name: DB_USER,     ValueFrom: 'arn:aws:secretsmanager:<region>:<account>:secret:<aurora-master-secret>:username::' }
          # - { Name: DB_PASS,     ValueFrom: 'arn:aws:secretsmanager:<region>:<account>:secret:<aurora-master-secret>:password::' }
          # - { Name: REDIS_HOST,  ValueFrom: 'arn:aws:ssm:<region>:<account>:parameter/lifesync360/redis-host' }
        LogConfiguration:
          LogDriver: awslogs
          Options:
            awslogs-group: /ecs/lifesync-platform
            awslogs-region: !Ref AWS::Region
            awslogs-stream-prefix: ecs
```

## 2. ECS Task Definition (admin)

```yaml
AdminTaskDef:
  Type: AWS::ECS::TaskDefinition
  Properties:
    Family: <admin 실제 family 이름>                       # list-task-definitions로 확인 필요
    Cpu: '256'
    Memory: '512'
    NetworkMode: awsvpc
    RequiresCompatibilities: [FARGATE]
    ExecutionRoleArn: !GetAtt EcsTaskExecutionRole.Arn
    TaskRoleArn: !GetAtt EcsAdminTaskRole.Arn
    ContainerDefinitions:
      - Name: <admin service LB의 containerName>           # describe-services로 확인
        Image: !Sub '${AWS::AccountId}.dkr.ecr.${AWS::Region}.amazonaws.com/lifesync-dev-admin-service:latest'
        PortMappings:
          - ContainerPort: 80                              # 또는 admin 실제 listen port
            Protocol: tcp
        Essential: true
        Environment:
          - { Name: AWS_REGION,          Value: !Ref AWS::Region }
          - { Name: DB_NAME,             Value: lifesync360 }
          - { Name: DYNAMO_TABLE,        Value: lifesync_customer_result }
          - { Name: USE_MOCK,            Value: 'false' }
          - { Name: ONPREM_QUERY_LAMBDA, Value: lifesync-onprem-customer-query }
        Secrets:
          - Name: SECRET_KEY
            ValueFrom: !Sub 'arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/lifesync360/admin-secret-key'
          - Name: ADMIN_USER
            ValueFrom: !Sub 'arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/lifesync360/admin-user'
          - Name: ADMIN_PASSWORD
            ValueFrom: !Sub 'arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/lifesync360/admin-password'
          # Aurora secrets는 platform과 동일
        LogConfiguration:
          LogDriver: awslogs
          Options:
            awslogs-group: /ecs/lifesync-admin
            awslogs-region: !Ref AWS::Region
            awslogs-stream-prefix: ecs
```

## 3. Task Execution Role (공용)

```yaml
EcsTaskExecutionRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Principal:
            Service: ecs-tasks.amazonaws.com
          Action: sts:AssumeRole
    ManagedPolicyArns:
      - arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
    Policies:
      - PolicyName: SSMParameterAccess
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            - Effect: Allow
              Action:
                - ssm:GetParameters
              Resource: !Sub 'arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/lifesync360/*'
      # 운영 전환 시 (Aurora secrets 사용할 때) 추가:
      # - PolicyName: SecretsManagerAccess
      #   PolicyDocument:
      #     Version: '2012-10-17'
      #     Statement:
      #       - Effect: Allow
      #         Action: secretsmanager:GetSecretValue
      #         Resource: '<Aurora 자동 시크릿 ARN>'
```

## 4. Task Role (platform — 애플리케이션이 사용)

```yaml
EcsPlatformTaskRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Principal:
            Service: ecs-tasks.amazonaws.com
          Action: sts:AssumeRole
    Policies:
      - PolicyName: DynamoDBAccess
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            - Effect: Allow
              Action:
                - dynamodb:GetItem
                - dynamodb:Query
                - dynamodb:Scan
                - dynamodb:PutItem
                - dynamodb:UpdateItem
              Resource:
                - !Sub 'arn:aws:dynamodb:${AWS::Region}:${AWS::AccountId}:table/lifesync_customer_result'
      - PolicyName: LambdaInvoke
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            - Effect: Allow
              Action: lambda:InvokeFunction
              Resource:
                - !Sub 'arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:lifesync-onprem-customer-query'
```

## 5. Task Role (admin)

```yaml
EcsAdminTaskRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Principal:
            Service: ecs-tasks.amazonaws.com
          Action: sts:AssumeRole
    Policies:
      - PolicyName: DynamoDBReadOnly                       # admin은 보통 읽기만
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            - Effect: Allow
              Action:
                - dynamodb:GetItem
                - dynamodb:Query
                - dynamodb:Scan
              Resource:
                - !Sub 'arn:aws:dynamodb:${AWS::Region}:${AWS::AccountId}:table/lifesync_customer_result'
      - PolicyName: LambdaInvoke
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            - Effect: Allow
              Action: lambda:InvokeFunction
              Resource: !Sub 'arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:lifesync-onprem-customer-query'
```

## 6. SSM Parameter Store 사전 등록 (현재 상태)

| Parameter Name | Type | 용도 | 현재 상태 |
|---|---|---|---|
| `/lifesync360/jwt-secret` | String 또는 SecureString | JWT 서명 키 | ✅ 존재 |
| `/lifesync360/ecr-uri` | String | platform ECR URI | ✅ 존재 |
| `/lifesync360/ecr-uri-admin` | String | admin ECR URI | ⚠️ 추가 필요 (`docs/lambda-onprem-query-deploy.md` 참고) |

운영 전환 시 추가 필요:
| `/lifesync360/redis-host` | String | ElastiCache 엔드포인트 | 운영 전환 시 |
| `/lifesync360/admin-secret-key` | SecureString | admin Flask 세션 | 운영 전환 시 |
| `/lifesync360/admin-user` | String | admin 로그인 ID | 운영 전환 시 |
| `/lifesync360/admin-password` | SecureString | admin 로그인 비번 | 운영 전환 시 |

Aurora 마스터 시크릿은 RDS 자동 생성 (`aws rds describe-db-clusters --query 'DBClusters[].MasterUserSecret.SecretArn'`)

---

## 7. CodeBuild Role 권한 (현재 buildspec이 register-task-definition 실행 중인 동안 필요)

IaC 정합 후 buildspec의 register 부분 제거하면 이 권한 불필요. 단 현재는 임시 우회용:

```yaml
CodeBuildRole:
  Type: AWS::IAM::Role
  Properties:
    AssumeRolePolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Principal:
            Service: codebuild.amazonaws.com
          Action: sts:AssumeRole
    Policies:
      - PolicyName: EcsRegisterAndDeploy
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            - Effect: Allow
              Action:
                - ecs:RegisterTaskDefinition
                - ecs:UpdateService
                - ecs:DescribeServices
                - ecs:DescribeTaskDefinition
              Resource: '*'
            - Effect: Allow
              Action: iam:PassRole
              Resource:
                - !GetAtt EcsTaskExecutionRole.Arn
                - !GetAtt EcsPlatformTaskRole.Arn
                - !GetAtt EcsAdminTaskRole.Arn
      # 기존 권한 유지 (ECR push, SSM read, application-autoscaling 등)
      - ...
```

---

## 8. ECS Service (참고 — 이미 IaC에 있을 가능성)

Service의 LoadBalancer 설정이 새 Task Definition과 정합 맞아야:

```yaml
PlatformService:
  Type: AWS::ECS::Service
  Properties:
    Cluster: lifesync-service-ecs
    TaskDefinition: !Ref PlatformTaskDef
    DesiredCount: 1
    LaunchType: FARGATE
    NetworkConfiguration:
      AwsvpcConfiguration:
        Subnets: [...]
        SecurityGroups: [...]
    LoadBalancers:
      - ContainerName: app                                 # PlatformTaskDef와 동일
        ContainerPort: 80                                  # PlatformTaskDef와 동일
        TargetGroupArn: !Ref AppTargetGroup
```

---

## 9. 적용 체크리스트

- [ ] 1번 — PlatformTaskDef에 7개 env + JWT_SECRET secret 추가 (또는 기존 리소스 업데이트)
- [ ] 2번 — AdminTaskDef 동일 패턴 (admin family/container name 확인 후)
- [ ] 3번 — EcsTaskExecutionRole에 SSM Parameter Access 정책
- [ ] 4번 — EcsPlatformTaskRole에 DynamoDB + Lambda Invoke
- [ ] 5번 — EcsAdminTaskRole에 DynamoDB ReadOnly + Lambda Invoke
- [ ] 6번 — SSM Parameter (jwt-secret + ecr-uri-admin 등) 등록
- [ ] 7번 — CodeBuild Role 권한 (또는 buildspec의 register 부분 제거 후 불필요)
- [ ] 8번 — Service의 LoadBalancer ContainerName/Port 정합 확인

## 10. IaC 반영 후 buildspec 정리

IaC 정합 완료 시 `lifesync360-platform/deploy/buildspec.yml`의 post_build에서 다음 부분 제거 가능:

```yaml
# 제거 대상 (IaC가 처리하면 불필요)
- sed "s|<IMAGE1_NAME>|$ECR_URI:$IMAGE_TAG|" taskdef.json > /tmp/td.json
- NEW_TD=$(aws ecs register-task-definition --cli-input-json file:///tmp/td.json ...)
- aws ecs update-service --cluster ... --task-definition $NEW_TD --force-new-deployment ...
```

남는 흐름:
- imagedefinitions.json만 생성 → CodePipeline Deploy stage가 image URI만 교체
- IaC가 Task Definition 자체 관리

---

## 관련 문서

- `docs/lambda-onprem-query-deploy.md` — Lambda + VPN 배포
- `docs/ecs-taskdef-redeploy.md` — ECS register/force-deploy 수동 가이드 (시연용)
- `docs/demo-removed-items-rollout.md` — 시연용 제거 항목 + 운영 전환
- `lifesync360-platform/taskdef.json` / `admin-platform/taskdef.json` — 실제 정합 박힌 파일
