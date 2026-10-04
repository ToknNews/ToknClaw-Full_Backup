#!/usr/bin/env python3
"""Root-owned, fixed-purpose Ubuntu deployment helper. No third-party imports.

Install explicitly once. SSH permits only `probe` and `deploy <full SHA>`.
Application code and tests never execute as root. This helper never installs a
new version of itself, rewrites credentials/configuration, or restores a DB.
"""

import base64
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid


REPO = 'https://github.com/ToknNews/ToknClaw-Full_Backup.git'
BRANCH = 'refs/heads/release/market-watch'
APP = Path('/opt/tokn-market-watch')
CONFIG = APP / 'config/market_watch.json'
DATABASE = Path('/var/lib/tokn-market-watch/state.sqlite3')
ENVIRONMENT = Path('/etc/tokn-market-watch.env')
STATE = Path('/var/lib/tokn-market-watch-deployment')
RELEASES = Path('/opt/tokn-market-watch-releases')
HELPER = Path('/usr/local/libexec/tokn-market-watch-deploy.py')
SUDOERS = Path('/etc/sudoers.d/tokn-market-watch-deploy')
DEPLOY_HOME = Path('/var/lib/tokn-market-watch-deployer')
USER = 'tokn-deploy'
SERVICE = 'tokn-market-watch.service'
TIMER = 'tokn-market-watch.timer'
DROPIN = Path('/etc/systemd/system/tokn-market-watch.service.d/90-managed-release.conf')
PYTHON = '/usr/bin/python3'
SAFE_ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8',
            'HOME': '/root', 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0'}


class DeployError(Exception):
    pass


def emit(status, **fields):
    print(json.dumps({'status': status, **fields}), flush=True)


def sha(value):
    if not re.fullmatch(r'[0-9a-f]{40}', value):
        raise DeployError('A full lowercase commit SHA is required.')
    return value


def ssh_command(value):
    if value == 'probe':
        return ['probe']
    match = re.fullmatch(r'deploy ([0-9a-f]{40})', value)
    if match:
        return ['start', match[1]]
    raise DeployError('Only probe and deploy <full SHA> are permitted.')


def public_key(value):
    parts = value.strip().split()
    if len(parts) not in (2, 3) or parts[0] != 'ssh-ed25519':
        raise DeployError('Paste one plain Ed25519 PUBLIC key, without key options.')
    try:
        data = base64.b64decode(parts[1], validate=True)
    except ValueError as exc:
        raise DeployError('Invalid public key.') from exc
    if len(data) != 51 or data[:19] != b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20':
        raise DeployError('Invalid Ed25519 public key.')
    return 'ssh-ed25519 ' + parts[1]


def run(args, *, timeout=180, allowed=(0,), log=None):
    try:
        result = subprocess.run(args, env=SAFE_ENV, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeployError('Command failed or timed out: ' + Path(args[0]).name) from exc
    if log:
        with log.open('ab') as output:
            output.write(result.stdout + result.stderr)
    if result.returncode not in allowed:
        raise DeployError('Command failed: ' + Path(args[0]).name)
    return result


def root_path(path, *, directory=False, private=False):
    """Refuse symlinks/writable ancestors before touching privileged paths."""
    path = Path(path)
    for part in [*reversed(path.parents), path]:
        if not part.exists() and not part.is_symlink():
            continue
        st = part.lstat()
        if part.is_symlink() or st.st_uid != 0 or st.st_mode & 0o022:
            raise DeployError('Expected a root-owned, non-writable regular path: ' + str(path))
    if path.exists() and directory != path.is_dir():
        raise DeployError('Unexpected path type: ' + str(path))
    if private and path.exists() and path.stat().st_mode & 0o077:
        raise DeployError('Expected a root-only path: ' + str(path))


def write_new(path, content, mode=0o600):
    with Path(path).open('xb') as handle:
        handle.write(content if isinstance(content, bytes) else content.encode())
        handle.flush()
        os.fsync(handle.fileno())
    Path(path).chmod(mode)


def mkdir(path, mode=0o755):
    # Explicit modes must not be narrowed by the root helper's private umask.
    missing = []
    cursor = Path(path)
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    root_path(cursor, directory=True)
    for item in reversed(missing):
        item.mkdir()
        item.chmod(mode if item == Path(path) else 0o755)


def replace_file(path, content, mode=0o600):
    """Complete atomic replacement of helper-owned files only."""
    root_path(path)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(content if isinstance(content, bytes) else content.encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def properties(unit, names):
    result = run(['/usr/bin/systemctl', 'show', unit, *['--property=' + n for n in names]])
    return dict(line.split('=', 1) for line in result.stdout.decode().splitlines() if '=' in line)


def preflight():
    if not CONFIG.is_file() or not ENVIRONMENT.is_file() or not DATABASE.is_file():
        raise DeployError('Expected the existing Market Watch config, environment and database.')
    root_path(APP, directory=True)
    root_path(CONFIG)
    root_path(ENVIRONMENT, private=True)
    cfg = json.loads(CONFIG.read_text())
    if not isinstance(cfg, dict):
        raise DeployError('Configuration must be a JSON object.')
    unit = properties(SERVICE, ['LoadState', 'DynamicUser', 'StateDirectory',
                               'WorkingDirectory', 'EnvironmentFiles', 'ExecStart'])
    if (unit.get('LoadState') != 'loaded' or unit.get('DynamicUser') != 'yes'
            or unit.get('StateDirectory') != 'tokn-market-watch'
            or str(ENVIRONMENT) not in unit.get('EnvironmentFiles', '')
            or '-m market_watch' not in unit.get('ExecStart', '')):
        raise DeployError('The existing service differs from the supported Market Watch unit.')
    working = unit.get('WorkingDirectory', '')
    if working != str(APP) and not working.startswith(str(RELEASES) + '/'):
        raise DeployError('Unexpected service working directory.')
    # Do not silently migrate a differently located archive.
    db_lines = [line.split('=', 1)[1].strip().strip('"\'')
                for line in ENVIRONMENT.read_text().splitlines()
                if line.startswith('MARKET_WATCH_DATABASE=')]
    if db_lines != [str(DATABASE)]:
        raise DeployError('MARKET_WATCH_DATABASE must name the existing canonical archive.')
    return cfg


def install():
    preflight()
    key = public_key(input('Paste the new deployment PUBLIC key (ssh-ed25519 ...): ').strip())
    for path, directory in ((HELPER, False), (SUDOERS, False), (STATE, True),
                            (DEPLOY_HOME, True), (RELEASES, True), (DROPIN, False)):
        root_path(path, directory=directory)
        if path.exists():
            raise DeployError('Installation stops rather than overwriting existing path: ' + str(path))
    try:
        pwd.getpwnam(USER)
    except KeyError:
        pass
    else:
        raise DeployError('The deployment account already exists; inspect before reinstalling.')
    for binary in ('/usr/sbin/useradd', '/usr/sbin/visudo', '/usr/bin/git',
                   '/usr/bin/systemd-run', '/usr/bin/sudo'):
        if not Path(binary).is_file():
            raise DeployError('Required Ubuntu program missing: ' + Path(binary).name)
    mkdir(STATE, 0o700)
    mkdir(DEPLOY_HOME)
    mkdir(RELEASES)
    mkdir(HELPER.parent)
    write_new(HELPER, Path(__file__).read_bytes(), 0o644)
    sudoers = (f'{USER} ALL=(root) NOPASSWD: {PYTHON} -I {HELPER} probe, '
               f'{PYTHON} -I {HELPER} start *\n')
    candidate = STATE / 'sudoers.checked'
    write_new(candidate, sudoers, 0o440)
    run(['/usr/sbin/visudo', '-cf', str(candidate)])
    run(['/usr/sbin/useradd', '--system', '--no-create-home', '--home-dir', str(DEPLOY_HOME),
         '--shell', '/bin/sh', USER])
    # A root-owned home and key file prevent this account from adding shell keys.
    keys = DEPLOY_HOME / '.ssh'
    mkdir(keys)
    forced = f'{PYTHON} -I {HELPER} gateway'
    write_new(keys / 'authorized_keys', f'restrict,command="{forced}" {key}\n', 0o644)
    write_new(SUDOERS, sudoers, 0o440)
    run(['/usr/sbin/visudo', '-cf', str(SUDOERS)])
    host = public_key(Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text())
    write_new(STATE / 'installed.json', json.dumps({'version': 1, 'public_key': key,
              'helper_sha256': hashlib.sha256(HELPER.read_bytes()).hexdigest()}) + '\n')
    emit('installed', application_changed=False, timer_changed=False)
    print('TOKN_KNOWN_HOSTS value (public host identity):', flush=True)
    print('tokn-market-watch ' + host, flush=True)


def archive_members(raw):
    """Only regular application/config files; never tar.extract(all)."""
    output = []
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or '..' in name.parts or not name.parts
                    or name.parts[0] not in {'market_watch', 'config'}):
                raise DeployError('Unsafe release archive path.')
            if member.isdir():
                continue
            if not member.isfile():
                raise DeployError('Release archives may not contain links or special files.')
            if name.parts[0] == 'config' and str(name) != 'config/market_watch.json':
                raise DeployError('Unexpected configuration file in release.')
            total += member.size
            if total > 25_000_000 or len(output) >= 1000:
                raise DeployError('Release exceeds the supported size.')
            output.append((str(name), archive.extractfile(member).read()))
    if not {'market_watch/__main__.py', 'market_watch/config.py',
            'config/market_watch.json'} <= {name for name, _ in output}:
        raise DeployError('Release is missing required application files.')
    if len(output) != len({name for name, _ in output}):
        raise DeployError('Duplicate release archive paths.')
    return output


def stage(commit, log):
    mirror = STATE / 'repository.git'
    if not mirror.exists():
        run(['/usr/bin/git', 'init', '--bare', str(mirror)], log=log)
    git = ['/usr/bin/git', '--git-dir=' + str(mirror)]
    run([*git, '-c', 'core.hooksPath=/dev/null', 'fetch', '--no-tags', '--depth=1',
         REPO, BRANCH], timeout=240, log=log)
    head = run([*git, 'rev-parse', 'FETCH_HEAD']).stdout.decode().strip()
    if head != sha(commit):
        raise DeployError('Requested commit is not the current release/market-watch head.')
    raw = run([*git, 'archive', '--format=tar', commit, 'market_watch',
               'config/market_watch.json'], timeout=120).stdout
    files = archive_members(raw)
    release = RELEASES / (commit + '-' + uuid.uuid4().hex[:8])
    mkdir(release)
    for name, content in files:
        target = release / name
        mkdir(target.parent)
        write_new(target, content, 0o644)
    return release


def sandbox_command(release, command, *, production=False):
    unit = 'tokn-market-watch-verify' if production else 'tokn-market-watch-release-tests'
    args = ['/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--collect',
            '--unit=' + unit, '--working-directory=' + str(release)]
    props = ['Type=exec', 'DynamicUser=yes', 'NoNewPrivileges=yes', 'PrivateTmp=yes',
             'ProtectSystem=strict', 'ProtectHome=yes', 'MemoryMax=256M',
             'RuntimeMaxSec=300', 'UMask=0077', 'Environment=PYTHONDONTWRITEBYTECODE=1']
    if production:
        props += ['User=tokn-market-watch', 'StateDirectory=tokn-market-watch',
                  'StateDirectoryMode=0700', 'PrivateNetwork=yes']
    else:
        props += ['PrivateNetwork=yes', 'InaccessiblePaths=/var/lib/private']
    return [*args, *['--property=' + p for p in props], PYTHON, '-B', *command]


def backup(destination):
    mkdir(destination, 0o700)
    with sqlite3.connect(DATABASE.resolve().as_uri() + '?mode=ro', uri=True) as source:
        target = destination / 'state.sqlite3'
        write_new(target, b'')
        with sqlite3.connect(target) as copy:
            source.backup(copy)
            if copy.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise DeployError('Database backup did not pass SQLite validation.')
    write_new(destination / 'market_watch.json', CONFIG.read_bytes())
    write_new(destination / 'environment', ENVIRONMENT.read_bytes())
    if DROPIN.exists():
        write_new(destination / 'previous-dropin.conf', DROPIN.read_bytes())
    unit = properties(SERVICE, ['WorkingDirectory', 'FragmentPath'])
    write_new(destination / 'previous-service.json', json.dumps(unit) + '\n')


def dropin(release):
    return ('# Managed by the explicitly installed Market Watch deployment helper.\n'
            '[Service]\nWorkingDirectory=' + str(release) + '\nExecStart=\n'
            'ExecStart=/usr/bin/python3 -m market_watch --config ' + str(CONFIG)
            + ' --database ' + str(DATABASE) + ' run $MARKET_WATCH_DELIVERY_ARGS\n')


def deploy(commit):
    commit = sha(commit)
    root_path(STATE, directory=True, private=True)
    root_path(RELEASES, directory=True)
    with (STATE / 'deployment.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DeployError('Another deployment is in progress.') from exc
        return deploy_locked(commit)


def deploy_locked(commit):
    preflight()
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8]
    log = STATE / (stamp + '.log')
    write_new(log, b'')
    emit('staging', commit=commit)
    release = stage(commit, log)
    emit('server_tests')
    run(sandbox_command(release, ['-m', 'unittest', 'discover', '-s', 'market_watch/tests']),
        timeout=330, log=log)
    timer_was_active = properties(TIMER, ['ActiveState']).get('ActiveState') == 'active'
    # A previous hard deployment failure is resumable, but an operator-paused
    # installation must not be activated implicitly.
    receipt = STATE / 'latest.json'
    old = json.loads(receipt.read_text()) if receipt.exists() else {}
    resume = timer_was_active or (old.get('status') == 'failed_after_cutover'
                                 and old.get('resume_timer') is True)
    if not resume:
        raise DeployError('Timer is paused; an operator must enable it before first deployment.')
    paused = False
    cutover = False
    snapshot = STATE / ('backup-' + stamp)
    record = {'commit': commit, 'release': str(release), 'backup': str(snapshot),
              'resume_timer': resume, 'status': 'preparing'}
    try:
        # Set before the command so a partially successful stop is handled too.
        paused = True
        run(['/usr/bin/systemctl', 'stop', TIMER, SERVICE], timeout=240, log=log)
        emit('backing_up')
        backup(snapshot)
        root_path(DROPIN)
        mkdir(DROPIN.parent)
        # Changes after this point are deliberately not rolled back over a
        # potentially migrated DB or new delivery receipts.
        cutover = True
        record['status'] = 'cutover'
        replace_file(receipt, json.dumps(record) + '\n')
        replace_file(DROPIN, dropin(release), 0o644)
        run(['/usr/bin/systemctl', 'daemon-reload'], log=log)
        run(['/usr/bin/systemctl', 'reset-failed', SERVICE], log=log)
        emit('starting_release')
        run(['/usr/bin/systemctl', 'start', SERVICE], timeout=210, log=log)
        result = properties(SERVICE, ['Result', 'ExecMainStatus'])
        if result.get('Result') != 'success' or result.get('ExecMainStatus') not in {'0', '2'}:
            raise DeployError('The new service did not complete a collection cycle.')
        health = run(sandbox_command(release, ['-m', 'market_watch', '--config', str(CONFIG),
                      '--database', str(DATABASE), 'check'], production=True),
                     allowed=(0, 2), timeout=60, log=log)
        # A primary data outage is degraded health, not a reason to stop all
        # collection. Keep the timer running, but fail CI clearly.
        run(['/usr/bin/systemctl', 'start', TIMER], log=log)
        if properties(TIMER, ['ActiveState']).get('ActiveState') != 'active':
            raise DeployError('The timer did not resume.')
        record['status'] = 'deployed' if health.returncode == 0 else 'deployed_degraded'
        replace_file(receipt, json.dumps(record) + '\n')
        emit(record['status'], commit=commit, timer='active',
             health='healthy' if health.returncode == 0 else 'needs_review')
        return 0 if health.returncode == 0 else 2
    except BaseException:
        if cutover:
            run(['/usr/bin/systemctl', 'stop', TIMER, SERVICE], timeout=240, allowed=(0, 1, 5), log=log)
            record['status'] = 'failed_after_cutover'
            replace_file(receipt, json.dumps(record) + '\n')
            emit('failed_after_cutover', timer='paused', database_restored=False)
        elif paused and timer_was_active:
            run(['/usr/bin/systemctl', 'start', TIMER], log=log)
            emit('previous_schedule_resumed')
        raise


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    os.umask(0o077)
    if args == ['gateway']:
        command = ssh_command(os.environ.get('SSH_ORIGINAL_COMMAND', ''))
        os.execv('/usr/bin/sudo', ['/usr/bin/sudo', '-n', PYTHON, '-I', str(HELPER), *command])
    if os.geteuid() != 0:
        raise DeployError('This operation requires sudo.')
    if args == ['install']:
        install()
        return 0
    if args == ['probe']:
        preflight()
        unit = properties(TIMER, ['ActiveState'])
        emit('connection_verified', timer=unit.get('ActiveState'), application_changed=False)
        return 0
    if len(args) == 2 and args[0] == 'start':
        commit = sha(args[1])
        # This root-owned worker survives an interrupted SSH client. It is not
        # a general-purpose runner and never accepts an arbitrary command.
        result = run(['/usr/bin/systemd-run', '--quiet', '--wait', '--collect',
                      '--unit=tokn-market-watch-deployment', '--property=Type=exec',
                      '--property=RuntimeMaxSec=1200', '--property=MemoryMax=512M',
                      '--property=StandardOutput=journal', '--property=StandardError=journal',
                      PYTHON, '-I', str(HELPER), 'apply', commit],
                     timeout=1230, allowed=(0, 1, 2))
        # The worker uses journald, not the SSH pipe: disconnects must not cause
        # BrokenPipeError halfway through a database migration or cutover.
        receipt = STATE / 'latest.json'
        record = json.loads(receipt.read_text()) if receipt.exists() else {}
        status = record.get('status') if record.get('commit') == commit else 'deployment_failed'
        emit(status or 'deployment_failed', commit=commit, exit_status=result.returncode)
        return result.returncode
    if len(args) == 2 and args[0] == 'apply':
        return deploy(sha(args[1]))
    raise DeployError('Unsupported deployment command.')


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise DeployError('Deployment was interrupted; inspect its saved state.')

    signal.signal(signal.SIGTERM, interrupted)
    try:
        raise SystemExit(main())
    except DeployError as exc:
        emit('operation_failed', reason=str(exc))
        raise SystemExit(1)
    except (OSError, ValueError, sqlite3.Error):
        # Do not echo arbitrary exception text, endpoints or credential values
        # into a public Actions log. Detailed child logs remain root-only.
        emit('operation_failed', help='Inspect the root-only deployment logs on the server.')
        raise SystemExit(1)
