"""Exercise release rollback with local CLI stand-ins; no infrastructure is contacted."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
STAND_IN = r"""
import json,os,sys
from pathlib import Path
tool=Path(sys.argv[0]).name
args=' '.join(sys.argv[1:])
with open(os.environ['SAQ_FAKE_LOG'],'a') as f:f.write(tool+' '+args+'\n')
if tool=='git':
    if 'rev-parse' in args:print('a'*40)
elif tool=='gcloud':
    if 'auth list' in args:print('local-test@example.test')
    elif 'json(status.traffic)' in args:
        print(json.dumps({'status':{'traffic':[{'revisionName':'old-revision','percent':100}]}}))
    elif 'value(status.url)' in args:print('https://demo-test.run.app')
    elif 'latestReadyRevisionName' in args:print('new-revision')
    elif 'indexes composite list' in args:
        rows=json.loads(Path('firestore.indexes.json').read_text())['indexes']
        values=[]
        for r in rows:
            name='projects/demo/databases/(default)/collectionGroups/'
            name+=r['collectionGroup']+'/indexes/demo'
            values.append(dict(name=name,fields=r['fields'],
                queryScope=r.get('queryScope','COLLECTION'),state='READY'))
        print(json.dumps(values))
    elif 'jobs describe' in args:sys.exit(1)
elif tool=='curl':
    if '/api/v1/me' in args:
        result=os.environ['SAQ_FAKE_AUTH']
        if result=='transport':sys.exit(7)
        print(result,end='')
    elif 'release.json' in args:print(json.dumps({'gitSha':'a'*40}))
    else:print('{}')
elif tool=='node' and '--input-type' in args:sys.stdin.read()
"""


@pytest.mark.parametrize("auth_result", ["401", "200", "transport"])
def test_release_promotes_exact_revision_and_rolls_back_failed_auth_smoke(tmp_path, auth_result):
    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "commands.txt"
    for name in ["git", "gcloud", "node", "npm", "npx", "curl"]:
        file = binary / name
        file.write_text(f"#!{sys.executable}\n" + STAND_IN)
        file.chmod(0o755)
    env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"]}
    env.update(SAQ_FAKE_AUTH=auth_result, SAQ_FAKE_LOG=str(log))
    result = subprocess.run(
        ["bash", str(ROOT / "deploy/publish-reviewed-release.sh"), SHA],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    commands = log.read_text()
    assert "--to-revisions=new-revision=100" in commands
    if auth_result == "401":
        assert result.returncode == 0, result.stderr
        assert "deploy --only hosting" in commands
        assert "Hosting SHA verified" in result.stdout
        assert "--to-revisions=old-revision=100" not in commands
    else:
        assert result.returncode != 0
        assert "--to-revisions=old-revision=100" in commands
        assert "deploy --only hosting" not in commands
