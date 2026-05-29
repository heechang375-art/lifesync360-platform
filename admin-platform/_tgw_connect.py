"""
LifeSync VPC ↔ TGW 연결 + 01-network 스택 업데이트
1. LifeSync VPC TGW attachment 생성 (DB 서브넷 기준)
2. TGW RT에 10.0.0.0/16 경로 추가
3. LifeSync DB/App private RT에 10.4.0.0/16 → TGW 추가 (return route)
4. 01-network 스택 TransitGatewayId 업데이트 → Management RT에 10.0.0.0/16 → TGW 생성
"""
import boto3, time, sys

ec2 = boto3.client('ec2', region_name='ap-northeast-2')
cf  = boto3.client('cloudformation', region_name='ap-northeast-2')

LIFESYNC_VPC      = 'vpc-0255ad149340748d5'
TGW_ID            = 'tgw-06c57df056d40be19'
TGW_RT_ID         = 'tgw-rtb-07a323cf4d32e9add'
DB_SUBNETS        = ['subnet-0c66a3a131ef04a46', 'subnet-067d6386c745a26a7']
LIFESYNC_DB_RT    = 'rtb-07cb1c002c2a1243b'
LIFESYNC_APP_RT   = 'rtb-095b45db77535dbe3'
STACK_NAME        = 'lifesync-dev-01-network'
MGMT_VPC_CIDR     = '10.4.0.0/16'
LIFESYNC_VPC_CIDR = '10.0.0.0/16'

# ── 1. TGW VPC attachment 생성 ─────────────────────────────────────────────
print('[1/4] LifeSync VPC TGW attachment 생성...')
resp = ec2.create_transit_gateway_vpc_attachment(
    TransitGatewayId=TGW_ID,
    VpcId=LIFESYNC_VPC,
    SubnetIds=DB_SUBNETS,
    TagSpecifications=[{
        'ResourceType': 'transit-gateway-attachment',
        'Tags': [
            {'Key': 'Name', 'Value': 'lifesync-dev-lifesync-vpc-tgw-attachment'},
            {'Key': 'Project', 'Value': 'lifesync'},
        ]
    }]
)
attachment_id = resp['TransitGatewayVpcAttachment']['TransitGatewayAttachmentId']
print(f'  attachment ID: {attachment_id}')

# available 대기 (보통 30~60초)
print('  available 대기 중...')
for i in range(24):
    time.sleep(10)
    state = ec2.describe_transit_gateway_vpc_attachments(
        TransitGatewayAttachmentIds=[attachment_id]
    )['TransitGatewayVpcAttachments'][0]['State']
    print(f'  [{i*10}s] state={state}')
    if state == 'available':
        break
    if state in ('failed', 'deleted', 'rejected'):
        print(f'  ERROR: attachment {state}')
        sys.exit(1)
else:
    print('  TIMEOUT: attachment이 available이 안 됨')
    sys.exit(1)

# ── 2. TGW RT에 10.0.0.0/16 경로 추가 ────────────────────────────────────
print('[2/4] TGW RT에 10.0.0.0/16 → LifeSync attachment 추가...')
ec2.create_transit_gateway_route(
    TransitGatewayRouteTableId=TGW_RT_ID,
    DestinationCidrBlock=LIFESYNC_VPC_CIDR,
    TransitGatewayAttachmentId=attachment_id,
)
print('  완료')

# ── 3. LifeSync private RT에 return route (10.4.0.0/16 → TGW) 추가 ────────
print('[3/4] LifeSync DB/App private RT에 10.4.0.0/16 → TGW 추가...')
for rt_id in [LIFESYNC_DB_RT, LIFESYNC_APP_RT]:
    try:
        ec2.create_route(
            RouteTableId=rt_id,
            DestinationCidrBlock=MGMT_VPC_CIDR,
            TransitGatewayId=TGW_ID,
        )
        print(f'  {rt_id} ✓')
    except ec2.exceptions.from_code('RouteAlreadyExists'):
        print(f'  {rt_id} 이미 존재')
    except Exception as e:
        print(f'  {rt_id} WARN: {e}')

# ── 4. 01-network 스택 업데이트 (TransitGatewayId 설정) ──────────────────
print('[4/4] 01-network 스택 TransitGatewayId 업데이트...')
stack = cf.describe_stacks(StackName=STACK_NAME)['Stacks'][0]
params = []
for p in stack.get('Parameters', []):
    if p['ParameterKey'] == 'TransitGatewayId':
        params.append({'ParameterKey': 'TransitGatewayId', 'ParameterValue': TGW_ID})
    else:
        params.append({'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True})

template_body = open(
    r'C:\users\campus3S026\ls\Aws_iac\Aws_iac\templates\01-network.yaml',
    encoding='utf-8'
).read()

cs_name = 'add-tgw-mgmt-route'
cf.create_change_set(
    StackName=STACK_NAME,
    TemplateBody=template_body,
    Parameters=params,
    Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM'],
    ChangeSetName=cs_name,
    ChangeSetType='UPDATE',
)
print(f'  change set {cs_name} 생성 중...')
waiter = cf.get_waiter('change_set_create_complete')
waiter.wait(StackName=STACK_NAME, ChangeSetName=cs_name,
            WaiterConfig={'Delay': 5, 'MaxAttempts': 24})

changes = cf.describe_change_set(StackName=STACK_NAME, ChangeSetName=cs_name)
for c in changes.get('Changes', []):
    r = c['ResourceChange']
    print(f'  {r["Action"]} {r["ResourceType"]} {r["LogicalResourceId"]}')

cf.execute_change_set(StackName=STACK_NAME, ChangeSetName=cs_name)
print('  change set 실행 중...')

waiter2 = cf.get_waiter('stack_update_complete')
waiter2.wait(StackName=STACK_NAME, WaiterConfig={'Delay': 10, 'MaxAttempts': 36})
print('  스택 업데이트 완료')

print('\n=== 완료 ===')
print('Admin EC2 (10.4.20.96) → Aurora 경로 개통됨')
print('Aurora 연결 테스트: python _check_tables.py')
