"""Packaging behavior checks, not model behavior or browser reliability tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('build_host_skills', ROOT / 'scripts/build_host_skills.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class HostSkillPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Canonicalize our owned temp root, not user-supplied artifact paths.
        # macOS commonly returns a /var alias through a symlinked ancestor.
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'skills' / builder.NAME
        shutil.copytree(ROOT / 'skills' / builder.NAME, self.source)

    def target(self, host='codex'):
        return self.root / builder.HOSTS[host] / 'skills' / builder.NAME

    def test_generated_adapters_are_self_contained_and_repeatable(self):
        builder.build(self.root, write=True)
        before = {host: builder.read_tree(self.target(host)) for host in builder.HOSTS}
        builder.build(self.root)
        builder.build(self.root, write=True)
        for host in builder.HOSTS:
            self.assertEqual(before[host], builder.read_tree(self.target(host)))
            manifest = json.loads(before[host][builder.MARKER])
            self.assertEqual(manifest['host'], host)
            self.assertIn('references/controlled-harness.md', before[host])
        self.assertIn('agents/openai.yaml', before['codex'])
        self.assertNotIn('agents/openai.yaml', before['claude'])

    def test_check_is_read_only_and_detects_missing_output(self):
        with self.assertRaisesRegex(ValueError, 'missing'):
            builder.build(self.root)
        self.assertFalse((self.root / '.agents').exists())

    def test_source_edits_require_regeneration(self):
        builder.build(self.root, write=True)
        with (self.source / 'SKILL.md').open('a') as stream:
            stream.write('\nA reviewed source change.\n')
        with self.assertRaisesRegex(ValueError, 'stale'):
            builder.build(self.root)
        builder.build(self.root, write=True)
        builder.build(self.root)

    def test_local_edits_are_preserved(self):
        builder.build(self.root, write=True)
        file = self.target() / 'SKILL.md'
        file.write_text('Do not overwrite my edited skill.\n')
        with self.assertRaisesRegex(ValueError, 'Local edits'):
            builder.build(self.root, write=True)
        self.assertEqual(file.read_text(), 'Do not overwrite my edited skill.\n')

    def test_unrecognized_destination_is_preserved(self):
        target = self.target('claude')
        target.mkdir(parents=True)
        (target / 'SKILL.md').write_text('Existing skill')
        with self.assertRaisesRegex(ValueError, 'Unrecognized existing'):
            builder.build(self.root, write=True)
        self.assertFalse(self.target().exists(), 'Both destinations must preflight before writing')

    def test_extra_files_are_preserved(self):
        builder.build(self.root, write=True)
        extra = self.target() / 'my-note.txt'
        extra.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'Extra or missing'):
            builder.build(self.root, write=True)
        self.assertEqual(extra.read_text(), 'keep')

    def test_source_removal_does_not_delete_output_silently(self):
        builder.build(self.root, write=True)
        (self.source / 'references/evidence.md').unlink()
        with self.assertRaisesRegex(ValueError, 'removal needs manual'):
            builder.build(self.root, write=True)
        self.assertTrue((self.target() / 'references/evidence.md').exists())

    def test_rejects_source_symlink(self):
        (self.source / 'external').symlink_to(self.root / 'outside')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            builder.build(self.root, write=True)

    def test_rejects_destination_parent_symlink(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.root / '.agents').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            builder.build(self.root, write=True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_rejects_generated_file_symlink(self):
        builder.build(self.root, write=True)
        target = self.target() / 'SKILL.md'
        target.unlink()
        target.symlink_to(self.source / 'SKILL.md')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            builder.build(self.root, write=True)


if __name__ == '__main__':
    unittest.main()
