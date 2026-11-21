"""
Unit tests for data_loader.py (Team 1 application, tested by Team 4).

Every test writes its own small JSON file into a temporary folder, so the
real Poetry data file is not needed.
"""

import contextlib
import io
import json
import os
import runpy
import tempfile
import unittest
from unittest import mock

import data_loader
from data_loader import DataLoader
from model import Issue, State

DATA_PATH = 'ENPM611_PROJECT_DATA_PATH'

SAMPLE_ISSUES = [
    {'number': 1, 'creator': 'alice', 'state': 'open', 'labels': ['kind/bug'],
     'created_date': '2024-01-01T00:00:00Z',
     'events': [{'event_type': 'commented', 'author': 'bob',
                 'event_date': '2024-01-02T00:00:00Z'}]},
    {'number': 2, 'creator': 'bob', 'state': 'closed', 'labels': [],
     'created_date': '2024-02-01T00:00:00Z', 'events': []},
]


class DataLoaderTestCase(unittest.TestCase):

    def setUp(self):
        env_patch = mock.patch.dict(os.environ)
        env_patch.start()
        self.addCleanup(env_patch.stop)

        # The loader keeps the issues in a module-level cache
        self.addCleanup(setattr, data_loader, '_ISSUES', data_loader._ISSUES)
        data_loader._ISSUES = None

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = folder.name

    def write_file(self, content, name='issues.json') -> str:
        path = os.path.join(self.folder, name)
        with open(path, 'w') as fout:
            fout.write(content if isinstance(content, str) else json.dumps(content))
        return path

    def loader_for(self, path) -> DataLoader:
        os.environ[DATA_PATH] = path
        return DataLoader()

    @staticmethod
    def quietly(func):
        """Runs func and returns (result, printed text)."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = func()
        return result, out.getvalue()


class TestLoading(DataLoaderTestCase):

    def test_data_path_is_read_from_the_configuration(self):
        loader = self.loader_for('/some/where/issues.json')
        self.assertEqual(loader.data_path, '/some/where/issues.json')

    def test_issues_are_loaded_as_issue_objects(self):
        loader = self.loader_for(self.write_file(SAMPLE_ISSUES))
        issues, _ = self.quietly(loader.get_issues)
        self.assertEqual(len(issues), 2)
        self.assertTrue(all(isinstance(i, Issue) for i in issues))
        self.assertEqual([i.number for i in issues], [1, 2])
        self.assertEqual(issues[0].creator, 'alice')
        self.assertIs(issues[1].state, State.closed)
        self.assertEqual(issues[0].events[0].author, 'bob')

    def test_number_of_loaded_issues_is_printed(self):
        path = self.write_file(SAMPLE_ISSUES)
        _, printed = self.quietly(self.loader_for(path).get_issues)
        self.assertIn('Loaded 2 issues', printed)
        self.assertIn(path, printed)

    def test_empty_file_list_gives_no_issues(self):
        issues, printed = self.quietly(self.loader_for(self.write_file([])).get_issues)
        self.assertEqual(issues, [])
        self.assertIn('Loaded 0 issues', printed)


class TestCaching(DataLoaderTestCase):

    def test_second_call_returns_the_cached_issues(self):
        loader = self.loader_for(self.write_file(SAMPLE_ISSUES))
        first, _ = self.quietly(loader.get_issues)
        with mock.patch.object(DataLoader, '_load') as load:
            second, printed = self.quietly(loader.get_issues)
        self.assertIs(second, first)
        load.assert_not_called()
        self.assertEqual(printed, '')

    def test_cache_is_shared_between_loaders(self):
        # Documents current behaviour: once issues are loaded, a loader that
        # points to a different file still returns the first file's issues.
        first, _ = self.quietly(self.loader_for(self.write_file(SAMPLE_ISSUES)).get_issues)
        other_path = self.write_file([], name='other.json')
        second, _ = self.quietly(self.loader_for(other_path).get_issues)
        self.assertIs(second, first)


class TestInvalidInput(DataLoaderTestCase):

    def test_missing_file_raises_clear_error(self):
        path = os.path.join(self.folder, 'does_not_exist.json')
        with self.assertRaises(FileNotFoundError) as caught:
            self.loader_for(path).get_issues()
        message = str(caught.exception)
        self.assertIn('Data file not found', message)
        self.assertIn(DATA_PATH, message)
        self.assertIn('does_not_exist.json', message)

    def test_folder_instead_of_file_raises_clear_error(self):
        with self.assertRaises(FileNotFoundError):
            self.loader_for(self.folder).get_issues()

    def test_path_that_is_not_configured_raises_clear_error(self):
        with mock.patch('config.get_parameter', return_value=None):
            loader = DataLoader()
        self.assertIsNone(loader.data_path)
        with self.assertRaises(FileNotFoundError) as caught:
            loader.get_issues()
        self.assertIn('Data file not found: None', str(caught.exception))

    def test_failed_load_does_not_fill_the_cache(self):
        with self.assertRaises(FileNotFoundError):
            self.loader_for(os.path.join(self.folder, 'missing.json')).get_issues()
        self.assertIsNone(data_loader._ISSUES)

    def test_file_that_is_not_json_raises_decode_error(self):
        # Documents current behaviour: a corrupt file is reported with the
        # raw JSON parser error, not with a message naming the data file.
        loader = self.loader_for(self.write_file('{not valid json'))
        with self.assertRaises(json.JSONDecodeError):
            loader.get_issues()


class TestRunAsScript(DataLoaderTestCase):

    def test_running_the_module_loads_the_issues(self):
        os.environ[DATA_PATH] = self.write_file(SAMPLE_ISSUES)
        _, printed = self.quietly(
            lambda: runpy.run_path(data_loader.__file__, run_name='__main__'))
        self.assertIn('Loaded 2 issues', printed)


if __name__ == '__main__':
    unittest.main()
