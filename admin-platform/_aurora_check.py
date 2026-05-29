import boto3

ec2 = boto3.client('ec2', region_name='ap-northeast-2')
rds = boto3.client('rds', region_name='ap-northeast-2')

# admin 서브넷(10.4.20.0/24)이 연결된 RT 확인
rts = ec2.describe_route_tables(
    Filters=[{'Name': 'association.subnet-id', 'Values': ['subnet-0faefec7dc4b32cbe']}]
)['RouteTables']
print('=== Admin Subnet RT ===')
if rts:
    rt = rts[0]
    print('RT ID:', rt['RouteTableId'])
    for r in rt['Routes']:
        dest = r.get('DestinationCidrBlock', '')
        gw   = r.get('GatewayId', r.get('TransitGatewayId', r.get('NatGatewayId', '?')))
        print(f'  {dest} -> {gw} [{r["State"]}]')
else:
    print('  (implicit main RT)')
    # main RT 조회
    main_rts = ec2.describe_route_tables(
        Filters=[
            {'Name': 'vpc-id', 'Values': ['vpc-0f8edff72edc23913']},
            {'Name': 'association.main', 'Values': ['true']},
        ]
    )['RouteTables']
    if main_rts:
        rt = main_rts[0]
        print('Main RT:', rt['RouteTableId'])
        for r in rt['Routes']:
            dest = r.get('DestinationCidrBlock', '')
            gw   = r.get('GatewayId', r.get('TransitGatewayId', r.get('NatGatewayId', '?')))
            print(f'  {dest} -> {gw} [{r["State"]}]')

# Aurora 클러스터 서브넷 CIDR 확인
cluster = rds.describe_db_clusters(DBClusterIdentifier='auroracluster-db')['DBClusters'][0]
sg_group = cluster['DBSubnetGroup'] if 'DBSubnetGroup' in cluster else ''
subnet_group = rds.describe_db_subnet_groups(DBSubnetGroupName=cluster['DBSubnetGroup'])['DBSubnetGroups'][0]
print('\n=== Aurora Subnet Group ===')
for s in subnet_group['Subnets']:
    sid = s['SubnetIdentifier']
    sub = ec2.describe_subnets(SubnetIds=[sid])['Subnets'][0]
    print(f'  {sid}: {sub["CidrBlock"]} (VPC: {sub["VpcId"]})')
