import boto3
import os
import sys

REPO = 'lifesync-lifesync-service-admin'
BRANCH = 'main'
REGION = 'ap-northeast-2'
TARGET_DIR = r'C:\admin-platform'

def get_all_files(cc, commit_id, folder_path=''):
    resp = cc.get_folder(
        repositoryName=REPO,
        commitSpecifier=commit_id,
        folderPath=folder_path
    )
    files = [f['absolutePath'] for f in resp.get('files', [])]
    for sub in resp.get('subFolders', []):
        files.extend(get_all_files(cc, commit_id, sub['absolutePath']))
    return files

def main():
    cc = boto3.client('codecommit', region_name=REGION)

    branch = cc.get_branch(repositoryName=REPO, branchName=BRANCH)
    commit_id = branch['branch']['commitId']
    print('Commit:', commit_id[:12])

    all_files = get_all_files(cc, commit_id)
    prefix = 'admin-platform/'
    target_files = [f for f in all_files if f.startswith(prefix)]
    print('Files to deploy:', len(target_files))

    for file_path in target_files:
        relative = file_path[len(prefix):]
        local_path = os.path.join(TARGET_DIR, relative.replace('/', os.sep))
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        resp = cc.get_file(
            repositoryName=REPO,
            commitSpecifier=commit_id,
            filePath=file_path
        )
        with open(local_path, 'wb') as fh:
            fh.write(resp['fileContent'])

    print('Deploy complete:', len(target_files), 'files written to', TARGET_DIR)

if __name__ == '__main__':
    main()
