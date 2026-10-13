"""One-time LOCAL compose setup after make model. No hosting accounts required."""
import os
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
if not shutil.which('docker'):
    raise SystemExit('Docker with Compose is required. Install/start Docker Desktop, then rerun make bootstrap.')
for name in ('JWT_SECRET', 'ADMIN_PASSWORD', 'ADMIN_EMAIL'):
    if not os.getenv(name):
        raise SystemExit(f'Set {name} in the root .env before bootstrap. See .env.example.')


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


run('docker', 'compose', 'build')
run('docker', 'compose', 'up', '-d', 'db')
run('docker', 'compose', 'run', '--rm', 'api', 'python', '-m', 'alembic', 'upgrade', 'head')
run('docker', 'compose', 'run', '--rm', 'api', 'python', 'scripts/seed_demo.py', '--patients', '20', '--through-month', '24')
run('docker', 'compose', 'run', '--rm', 'api', 'python', 'scripts/bootstrap_admin.py', '--email', os.environ['ADMIN_EMAIL'])
if os.getenv('DEMO_PASSWORD'):
    run('docker', 'compose', 'run', '--rm', 'api', 'python', 'scripts/seed_users.py')
print('Local bootstrap complete. Run docker compose up -d; open http://localhost:8080')
