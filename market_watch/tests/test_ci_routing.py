"""Offline contracts for Actions routing; no YAML dependency in release tests.

The small extractors accept this workflow's block-list form only. Exact section
contracts guard unsupported filters/expressions rather than pretending to be a
complete YAML or GitHub expression interpreter.
"""

import fnmatch
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/market-watch-tests.yml'
DEPLOY = ROOT / '.github/workflows/market-watch-deploy.yml'
PATHS = ['market_watch/**', 'tokn_research/**', 'research_specs/**',
         'config/market_watch.json', '.github/workflows/market-watch-tests.yml']
BRANCHES = ['main', 'release/market-watch', 'ops/market-watch-connect']


def section(text, name, indent=0):
    lines = text.splitlines()
    start = lines.index(' ' * indent + name + ':') + 1
    result = []
    for line in lines[start:]:
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        result.append(line)
    return '\n'.join(result)


def values(text, key, indent):
    return [line.strip()[2:].strip('"') for line in
            section(text, key, indent).splitlines()]


@unittest.skipUnless(WORKFLOW.is_file(), 'CI workflow is not shipped in application releases')
class CIRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text()
        cls.events = section(cls.text, 'on')

    def routes(self, event, ref, changed):
        config = section(self.events, event, 2)
        if event == 'push':
            if not ref.startswith('refs/heads/'):
                return False
            if ref.removeprefix('refs/heads/') not in values(config, 'branches', 4):
                return False
        return any(fnmatch.fnmatchcase(path, pattern)
                   for path in changed for pattern in values(config, 'paths', 4))

    def test_event_contract_preserves_paths_and_all_pr_targets(self):
        expected = '  pull_request:\n    paths:\n' + ''.join(
            f'      - "{path}"\n' for path in PATHS)
        expected += '  push:\n    branches:\n' + ''.join(
            f'      - {branch}\n' for branch in BRANCHES)
        expected += '    paths:\n' + ''.join(f'      - "{path}"\n' for path in PATHS)
        self.assertEqual(self.events, expected.rstrip())

    def test_feature_update_runs_only_pr_matrix(self):
        for branch in ('feature/research', 'feature/deployment', 'contributor/fix'):
            with self.subTest(branch=branch):
                self.assertFalse(self.routes('push', 'refs/heads/' + branch, ['market_watch/cli.py']))
                self.assertTrue(self.routes('pull_request', 'refs/pull/7/merge', ['market_watch/cli.py']))

    def test_exact_integration_pushes_and_each_path_remain_covered(self):
        for branch in BRANCHES:
            for path in ('market_watch/tests/test_ci_routing.py', 'tokn_research/data/asof.py',
                         'research_specs/M0_OFFLINE_FOUNDATION.md', 'config/market_watch.json',
                         '.github/workflows/market-watch-tests.yml'):
                with self.subTest(branch=branch, path=path):
                    self.assertTrue(self.routes('push', 'refs/heads/' + branch, [path]))
                    self.assertTrue(self.routes('pull_request', 'refs/pull/4/merge', [path]))

    def test_unrelated_paths_and_tags_do_not_schedule_matrix(self):
        for event in ('push', 'pull_request'):
            self.assertFalse(self.routes(event, 'refs/heads/main', ['signal_engine/example.py']))
        self.assertFalse(self.routes('push', 'refs/tags/v1', ['market_watch/cli.py']))

    def test_concurrency_cancels_only_same_workflow_event_and_pr_or_ref(self):
        config = section(self.text, 'concurrency')
        expression = '${{ github.workflow }}-${{ github.event_name }}-${{ github.event.pull_request.number || github.ref }}'
        self.assertEqual(config, f'  group: {expression}\n  cancel-in-progress: true')

        def group(event, ref, pr=None, workflow='Market Watch offline tests'):
            substitutions = {'github.workflow': workflow, 'github.event_name': event,
                             'github.event.pull_request.number || github.ref': str(pr or ref)}
            return re.sub(r'\$\{\{ (.*?) \}\}', lambda m: substitutions[m[1]], expression)

        first = group('pull_request', 'refs/pull/4/merge', 4)
        self.assertEqual(first, group('pull_request', 'refs/pull/4/merge', 4))
        self.assertNotEqual(first, group('pull_request', 'refs/pull/5/merge', 5))
        self.assertNotEqual(first, group('push', 'refs/heads/release/market-watch'))
        self.assertNotEqual(first, group('pull_request', 'refs/pull/4/merge', 4, 'Other workflow'))
        pushes = [group('push', 'refs/heads/' + branch) for branch in BRANCHES]
        self.assertEqual(len(set(pushes)), len(BRANCHES))
        self.assertTrue(all(key != 'market-watch-production' for key in pushes + [first]))

    def test_matrix_commands_and_release_gates_remain_intact(self):
        job = section(section(self.text, 'jobs'), 'offline-tests', 2)
        self.assertIn('    runs-on: ubuntu-22.04', job)
        self.assertIn('    timeout-minutes: 5', job)
        self.assertIn('        python-version: ["3.10", "3.12", "3.14"]', job)
        self.assertEqual(re.findall(r'^        run: (.+)$', job, re.M), [
            'python -m unittest discover -s market_watch/tests -v',
            'python -m unittest discover -s tokn_research/tests -v'])
        self.assertNotIn('continue-on-error', job)
        self.assertNotIn('    if:', job)
        self.assertEqual(section(self.text, 'permissions'), '  contents: read')
        deploy = DEPLOY.read_text()
        self.assertEqual(section(deploy, 'concurrency'),
                         '  group: market-watch-production\n  cancel-in-progress: false')
        self.assertIn('    needs: tests', deploy)
        self.assertIn('      - name: Test exact release without deployment secrets\n'
                      '        run: python -m unittest discover -s market_watch/tests -v', deploy)


if __name__ == '__main__':
    unittest.main()
