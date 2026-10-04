"""Exercise the Actions SSH client with fake secrets and no network access."""

import ast
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch


WORKFLOW = Path(__file__).resolve().parents[2] / '.github/workflows/market-watch-deploy.yml'


@unittest.skipUnless(WORKFLOW.is_file(), 'Workflow is checked in CI, not shipped to the application release')
class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        block = textwrap.dedent(WORKFLOW.read_text().split('        run: |\n', 1)[1])
        cls.script = block.split('\n', 1)[1].rsplit('\nPY', 1)[0]
        tree = ast.parse(cls.script, feature_version=(3, 10))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'ssh_failure')
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<classifier>', 'exec'), namespace)
        cls.classify = staticmethod(namespace['ssh_failure'])

    def exercise(self, *, key='PRIVATE_FIXTURE', key_valid=True, alias_valid=True,
                 code=0, stderr=b'', ref='refs/heads/ops/market-watch-connect'):
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args[0] == 'ssh-keygen':
                valid = key_valid if '-y' in args else alias_valid
                return subprocess.CompletedProcess(args, 0 if valid else 1, b'PUBLIC_FIXTURE', b'')
            self.assertEqual(args[0], 'ssh')
            return subprocess.CompletedProcess(args, code, b'', stderr)

        with tempfile.TemporaryDirectory() as tmp:
            environment = {'TOKN_SSH_HOST': 'server.example', 'TOKN_SSH_PORT': '22',
                           'TOKN_SSH_KEY': key, 'TOKN_KNOWN_HOSTS': 'HOST_IDENTITY_FIXTURE',
                           'GITHUB_REF': ref, 'GITHUB_SHA': 'a' * 40,
                           'GITHUB_STEP_SUMMARY': str(Path(tmp) / 'summary')}
            output = io.StringIO()
            with patch.dict(os.environ, environment, clear=True), \
                    patch('subprocess.run', side_effect=fake_run), contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as caught:
                    exec(compile(self.script, '<workflow>', 'exec'), {})
            return caught.exception.code, output.getvalue(), calls

    def test_classification_never_echoes_sensitive_diagnostics(self):
        for message in (b'Host key verification failed', b'Permission denied (publickey)',
                        b'Load key invalid format', b'Could not resolve hostname',
                        b'Connection timed out', b'Connection refused', b'Connection reset',
                        b'Unexpected error'):
            guidance = self.classify(message + b' server.example PRIVATE_FIXTURE HOST_IDENTITY_FIXTURE')
            self.assertNotIn('server.example', guidance)
            self.assertNotIn('PRIVATE_FIXTURE', guidance)
            self.assertNotIn('HOST_IDENTITY_FIXTURE', guidance)
            self.assertTrue(guidance)

    def test_probe_command_remains_readonly_and_host_verification_strict(self):
        code, output, calls = self.exercise()
        self.assertEqual(code, 0)
        self.assertEqual(calls[-1][-1], 'probe')
        self.assertIn('StrictHostKeyChecking=yes', calls[-1])
        self.assertIn('HostKeyAlias=tokn-market-watch', calls[-1])
        self.assertNotIn('PRIVATE_FIXTURE', output)

    def test_public_key_or_fingerprint_never_reaches_ssh(self):
        for key in ('ssh-ed25519 PUBLIC_FIXTURE', 'SHA256:FINGERPRINT_FIXTURE'):
            with self.subTest(key=key):
                code, output, calls = self.exercise(key=key)
                self.assertIn('public key or fingerprint', code)
                self.assertEqual(calls, [])

    def test_corrupt_or_encrypted_key_has_specific_guidance(self):
        code, output, calls = self.exercise(key_valid=False)
        self.assertIn('not a readable unencrypted private key', code)
        self.assertEqual(len(calls), 1)

    def test_missing_host_alias_is_identified_before_connecting(self):
        code, output, calls = self.exercise(alias_valid=False)
        self.assertIn('entire line beginning tokn-market-watch ssh-ed25519', code)
        self.assertEqual(len(calls), 2)

    def test_authentication_failure_reports_category_without_endpoints(self):
        code, output, calls = self.exercise(code=255, stderr=b'tokn-deploy@server.example: Permission denied (publickey).')
        self.assertEqual(code, 255)
        self.assertIn('rejected the deployment key', output)
        self.assertNotIn('server.example', output)

    def test_unexpected_branch_cannot_connect(self):
        code, output, calls = self.exercise(ref='refs/heads/untrusted')
        self.assertIn('not authorized', code)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
