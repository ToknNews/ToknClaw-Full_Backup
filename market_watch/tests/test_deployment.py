"""Deployment tests use temporary files and a fake systemd boundary only."""

import base64
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from market_watch.ops import deploy as d


COMMIT = 'a' * 40


def archive(entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as output:
        for name, kind, value in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            if kind == tarfile.REGTYPE:
                info.size = len(value)
                output.addfile(info, io.BytesIO(value))
            else:
                info.linkname = value
                output.addfile(info)
    return data.getvalue()


BASE = [(name, tarfile.REGTYPE, b'example') for name in (
    'market_watch/__main__.py', 'market_watch/config.py', 'config/market_watch.json')]


class BoundaryTests(unittest.TestCase):
    def test_ssh_only_accepts_exact_commands_and_full_sha(self):
        self.assertEqual(d.ssh_command('probe'), ['probe'])
        self.assertEqual(d.ssh_command('deploy ' + COMMIT), ['start', COMMIT])
        for command in ('bash', 'probe\n', 'probe; id', 'deploy HEAD', 'deploy ' + 'A' * 40,
                        'deploy ' + COMMIT + '\n', 'deploy ' + COMMIT + ' extra',
                        'deploy $(id)', 'sftp', 'scp -t file', ''):
            with self.subTest(command=command), self.assertRaises(d.DeployError):
                d.ssh_command(command)

    def test_key_rejects_private_keys_and_authorized_key_options(self):
        blob = base64.b64encode(b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20' + b'x' * 32).decode()
        self.assertEqual(d.public_key('ssh-ed25519 ' + blob + ' comment'), 'ssh-ed25519 ' + blob)
        for key in ('-----BEGIN OPENSSH PRIVATE KEY-----', 'ssh-rsa ' + blob,
                    'ssh-ed25519 invalid!', 'command="sh" ssh-ed25519 ' + blob,
                    'ssh-ed25519 ' + blob + '\nssh-ed25519 ' + blob):
            with self.subTest(key=key[:20]), self.assertRaises(d.DeployError):
                d.public_key(key)

    def test_archive_regular_files_only(self):
        self.assertEqual(len(d.archive_members(archive(BASE))), 3)
        invalid = [('market_watch/../../etc/passwd', tarfile.REGTYPE, b'x'),
                   ('/etc/passwd', tarfile.REGTYPE, b'x'),
                   ('market_watch/link', tarfile.SYMTYPE, '/etc/shadow'),
                   ('market_watch/link', tarfile.LNKTYPE, '/etc/shadow'),
                   ('market_watch/pipe', tarfile.FIFOTYPE, ''),
                   ('config/other.json', tarfile.REGTYPE, b'x'),
                   ('unrelated/file', tarfile.REGTYPE, b'x'), BASE[0]]
        for entry in invalid:
            with self.subTest(entry=entry[0]), self.assertRaises(d.DeployError):
                d.archive_members(archive(BASE + [entry]))
        with self.assertRaises(d.DeployError):
            d.archive_members(archive(BASE[:1]))

    def test_ref_must_match_current_release_head(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(d, 'STATE', Path(tmp)), \
                patch.object(d, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, ('b' * 40 + '\n').encode(), b'')
            with self.assertRaises(d.DeployError):
                d.stage(COMMIT, None)
            calls = [call.args[0] for call in run.call_args_list]
            self.assertTrue(any(d.BRANCH in args for args in calls))
            self.assertFalse(any('archive' in args for args in calls))

    def test_files_are_exclusive_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'file'
            d.write_new(path, 'first')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                d.write_new(path, 'second')
            self.assertEqual(path.read_text(), 'first')

    def test_release_directories_readable_despite_private_umask(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(d, 'root_path'):
            previous = os.umask(0o077)
            try:
                path = Path(tmp) / 'release' / 'market_watch'
                d.mkdir(path)
                self.assertEqual(path.stat().st_mode & 0o777, 0o755)
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o755)
            finally:
                os.umask(previous)

    def test_application_and_tests_run_unprivileged_without_secrets(self):
        for production in (False, True):
            args = d.sandbox_command('/opt/release', ['-m', 'market_watch'], production=production)
            self.assertIn('--property=DynamicUser=yes', args)
            self.assertIn('--property=NoNewPrivileges=yes', args)
            self.assertIn('--property=PrivateNetwork=yes', args)
            self.assertFalse(any('EnvironmentFile=' in arg for arg in args))
            self.assertNotIn('User=root', ' '.join(args))

    def test_root_path_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'link'
            path.symlink_to('/etc/passwd')
            with self.assertRaises(d.DeployError):
                d.root_path(path)

    def test_worker_logs_are_not_tied_to_ssh_client_pipe(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(d, 'STATE', Path(tmp)), \
                patch.object(d.os, 'geteuid', return_value=0), patch.object(d, 'emit'), \
                patch.object(d, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 1, b'', b'')
            self.assertEqual(d.main(['start', COMMIT]), 1)
            args = run.call_args.args[0]
            self.assertNotIn('--pipe', args)
            self.assertIn('--property=StandardOutput=journal', args)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for name, relative in [('STATE', 'state'), ('RELEASES', 'releases'),
                               ('CONFIG', 'config.json'), ('ENVIRONMENT', 'settings.env'),
                               ('DATABASE', 'archive.sqlite3'), ('DROPIN', 'systemd/90-managed.conf')]:
            self.stack.enter_context(patch.object(d, name, root / relative))
        d.STATE.mkdir()
        d.RELEASES.mkdir()
        d.CONFIG.write_text('{"setup_enabled": false}\n')
        d.ENVIRONMENT.write_text('PRIVATE_FIXTURE=never_publish\n')
        with sqlite3.connect(d.DATABASE) as db:
            db.execute('CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)')
            db.execute('INSERT INTO evidence VALUES (1, "preserved")')
        self.release = d.RELEASES / COMMIT
        self.release.mkdir()
        self.stack.enter_context(patch.object(d, 'root_path'))
        self.stack.enter_context(patch.object(d, 'preflight', return_value={}))
        self.stack.enter_context(patch.object(d, 'stage', return_value=self.release))
        self.stack.enter_context(patch.object(d, 'emit'))
        self.stack.enter_context(patch.object(d, 'properties', side_effect=self.properties))
        self.stack.enter_context(patch.object(d, 'run', side_effect=self.fake_run))
        self.calls = []
        self.active = True
        self.fail_tests = False
        self.fail_start = False
        self.health = 0

    def properties(self, unit, names):
        if unit == d.TIMER:
            return {'ActiveState': 'active' if self.active else 'inactive'}
        return {'WorkingDirectory': '/opt/tokn-market-watch', 'FragmentPath': '/test/unit',
                'Result': 'success', 'ExecMainStatus': '0'}

    def fake_run(self, args, **kwargs):
        self.calls.append(args)
        if 'unittest' in args and self.fail_tests:
            raise d.DeployError('Offline tests failed.')
        if args[:2] == ['/usr/bin/systemctl', 'stop']:
            self.active = False
        if args == ['/usr/bin/systemctl', 'start', d.SERVICE] and self.fail_start:
            # Simulate migration and a receipt written before the crash.
            with sqlite3.connect(d.DATABASE) as db:
                db.execute('INSERT INTO evidence VALUES (2, "new receipt")')
            raise d.DeployError('Service failed.')
        if args == ['/usr/bin/systemctl', 'start', d.TIMER]:
            self.active = True
        code = self.health if args[-1] == 'check' else 0
        return subprocess.CompletedProcess(args, code, b'{}', b'')

    def receipt(self):
        return json.loads((d.STATE / 'latest.json').read_text())

    def test_success_backs_up_exact_settings_preserves_db_and_activates_release(self):
        self.assertEqual(d.deploy_locked(COMMIT), 0)
        saved = self.receipt()
        self.assertEqual(saved['status'], 'deployed')
        snapshot = Path(saved['backup'])
        self.assertEqual((snapshot / 'market_watch.json').read_bytes(), d.CONFIG.read_bytes())
        self.assertEqual((snapshot / 'environment').read_bytes(), d.ENVIRONMENT.read_bytes())
        with sqlite3.connect(snapshot / 'state.sqlite3') as db:
            self.assertEqual(db.execute('SELECT value FROM evidence').fetchall(), [('preserved',)])
        self.assertIn(str(self.release), d.DROPIN.read_text())
        self.assertIn(str(d.CONFIG), d.DROPIN.read_text())
        self.assertIn('$MARKET_WATCH_DELIVERY_ARGS', d.DROPIN.read_text())
        self.assertTrue(self.active)

    def test_failed_tests_never_stop_the_existing_service(self):
        self.fail_tests = True
        with self.assertRaises(d.DeployError):
            d.deploy_locked(COMMIT)
        self.assertTrue(self.active)
        self.assertFalse(d.DROPIN.exists())
        self.assertFalse(any('stop' in args for args in self.calls))

    def test_failed_backup_resumes_previous_schedule_without_switching_code(self):
        with patch.object(d, 'backup', side_effect=d.DeployError('Backup failed.')):
            with self.assertRaises(d.DeployError):
                d.deploy_locked(COMMIT)
        self.assertTrue(self.active)
        self.assertFalse(d.DROPIN.exists())

    def test_hard_failure_keeps_new_receipts_and_pauses_timer(self):
        self.fail_start = True
        with self.assertRaises(d.DeployError):
            d.deploy_locked(COMMIT)
        self.assertFalse(self.active)
        self.assertEqual(self.receipt()['status'], 'failed_after_cutover')
        with sqlite3.connect(d.DATABASE) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM evidence').fetchone()[0], 2)

    def test_data_outage_fails_health_but_keeps_collection_running(self):
        self.health = 2
        self.assertEqual(d.deploy_locked(COMMIT), 2)
        self.assertEqual(self.receipt()['status'], 'deployed_degraded')
        self.assertTrue(self.active)

    def test_operator_paused_timer_is_not_implicitly_enabled(self):
        self.active = False
        with self.assertRaises(d.DeployError):
            d.deploy_locked(COMMIT)
        self.assertFalse(self.active)
        self.assertFalse(any('stop' in args for args in self.calls))

    def test_prior_hard_failure_can_be_fixed_with_a_forward_release(self):
        self.active = False
        (d.STATE / 'latest.json').write_text(json.dumps({
            'status': 'failed_after_cutover', 'resume_timer': True}))
        self.assertEqual(d.deploy_locked(COMMIT), 0)
        self.assertTrue(self.active)


if __name__ == '__main__':
    unittest.main()
