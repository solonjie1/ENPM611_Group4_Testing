"""
Unit tests for config.py (Team 1 application, tested by Team 4).

White-box tests: every branch of get_parameter, convert_to_typed_value,
set_parameter, overwrite_from_args and the config.json lookup is exercised.
No real data file is needed.
"""

import argparse
import json
import os
import tempfile
import unittest
from unittest import mock

import config


class ConfigTestCase(unittest.TestCase):
    """
    Isolates every test: the cached config is cleared and all changes to
    environment variables and the working directory are undone afterwards.
    """

    def setUp(self):
        env_patch = mock.patch.dict(os.environ)
        env_patch.start()
        self.addCleanup(env_patch.stop)

        self.addCleanup(setattr, config, '_config', config._config)
        config._config = None

        self.addCleanup(os.chdir, os.getcwd())

    def use_config_file(self, content: dict, subfolder: str = None) -> str:
        """
        Writes a config.json into a temporary folder and makes that folder
        (or a subfolder of it) the working directory.
        """
        original_cwd = os.getcwd()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with open(os.path.join(folder.name, 'config.json'), 'w') as fout:
            json.dump(content, fout)
        workdir = folder.name
        if subfolder:
            workdir = os.path.join(folder.name, subfolder)
            os.makedirs(workdir)
        os.chdir(workdir)
        self.addCleanup(os.chdir, original_cwd)
        return folder.name


class TestConfigFileLookup(ConfigTestCase):

    def test_reads_parameter_from_config_json_in_working_directory(self):
        self.use_config_file({'MY_SETTING': 'from file'})
        self.assertEqual(config.get_parameter('MY_SETTING'), 'from file')

    def test_finds_config_json_in_a_parent_directory(self):
        self.use_config_file({'MY_SETTING': 'from parent'}, subfolder=os.path.join('a', 'b'))
        self.assertEqual(config.get_parameter('MY_SETTING'), 'from parent')

    def test_default_path_points_to_the_config_file(self):
        folder = self.use_config_file({})
        self.assertEqual(os.path.realpath(config._get_default_path()),
                         os.path.realpath(os.path.join(folder, 'config.json')))

    def test_no_config_file_anywhere_gives_empty_config(self):
        with mock.patch('os.path.isfile', return_value=False):
            self.assertIsNone(config._get_default_path())
            self.assertIsNone(config.get_parameter('MY_SETTING'))
        self.assertEqual(config._config, {})

    def test_config_file_is_only_read_once(self):
        self.use_config_file({'MY_SETTING': 'first'})
        self.assertEqual(config.get_parameter('MY_SETTING'), 'first')
        # A different config.json is ignored because the first one is cached
        self.use_config_file({'MY_SETTING': 'second'})
        self.assertEqual(config.get_parameter('MY_SETTING'), 'first')


class TestGetParameter(ConfigTestCase):

    def setUp(self):
        super().setUp()
        self.use_config_file({'IN_FILE': 'file value', 'SHARED': 'file value'})

    def test_environment_variable_wins_over_config_file(self):
        os.environ['SHARED'] = 'env value'
        self.assertEqual(config.get_parameter('SHARED'), 'env value')

    def test_environment_variable_used_when_not_in_file(self):
        os.environ['ONLY_ENV'] = 'env value'
        self.assertEqual(config.get_parameter('ONLY_ENV'), 'env value')

    def test_json_prefix_is_removed_and_value_parsed(self):
        os.environ['A_LIST'] = 'json:[1, 2, 3]'
        self.assertEqual(config.get_parameter('A_LIST'), [1, 2, 3])

    def test_environment_values_are_converted_to_their_type(self):
        os.environ['A_NUMBER'] = '42'
        os.environ['A_FLAG'] = 'true'
        self.assertEqual(config.get_parameter('A_NUMBER'), 42)
        self.assertIs(config.get_parameter('A_FLAG'), True)

    def test_missing_parameter_returns_none(self):
        self.assertIsNone(config.get_parameter('DOES_NOT_EXIST'))

    def test_missing_parameter_returns_default(self):
        self.assertEqual(config.get_parameter('DOES_NOT_EXIST', default='fallback'), 'fallback')

    def test_default_is_ignored_when_parameter_exists(self):
        self.assertEqual(config.get_parameter('IN_FILE', default='fallback'), 'file value')

    def test_missing_parameter_returns_falsy_default(self):
        """
        DEFECT: a default of 0, False or '' is dropped and None is returned,
        because get_parameter checks `if default:` instead of
        `if default is not None:`.
        """
        self.assertEqual(config.get_parameter('DOES_NOT_EXIST', default=0), 0)
        self.assertIs(config.get_parameter('DOES_NOT_EXIST', default=False), False)
        self.assertEqual(config.get_parameter('DOES_NOT_EXIST', default=''), '')


class TestConvertToTypedValue(unittest.TestCase):

    def test_none_stays_none(self):
        self.assertIsNone(config.convert_to_typed_value(None))

    def test_json_strings_are_parsed(self):
        self.assertEqual(config.convert_to_typed_value('5'), 5)
        self.assertEqual(config.convert_to_typed_value('1.5'), 1.5)
        self.assertIs(config.convert_to_typed_value('false'), False)
        self.assertEqual(config.convert_to_typed_value('{"a": [1]}'), {'a': [1]})

    def test_plain_text_stays_a_string(self):
        self.assertEqual(config.convert_to_typed_value('kind/bug'), 'kind/bug')
        self.assertEqual(config.convert_to_typed_value(''), '')

    def test_non_string_values_are_returned_unchanged(self):
        value = [1, 2]
        self.assertIs(config.convert_to_typed_value(value), value)
        self.assertEqual(config.convert_to_typed_value(7), 7)


class TestSetParameter(ConfigTestCase):

    def setUp(self):
        super().setUp()
        self.use_config_file({})

    def test_string_is_stored_unchanged_in_environment(self):
        config.set_parameter('label', 'kind/bug')
        self.assertEqual(os.environ['label'], 'kind/bug')
        self.assertEqual(config.get_parameter('label'), 'kind/bug')

    def test_non_string_is_stored_as_json(self):
        config.set_parameter('feature', 2)
        self.assertEqual(os.environ['feature'], 'json:2')
        self.assertEqual(config.get_parameter('feature'), 2)

    def test_list_and_dict_round_trip(self):
        config.set_parameter('a_list', ['a', 'b'])
        config.set_parameter('a_dict', {'k': 1})
        self.assertEqual(config.get_parameter('a_list'), ['a', 'b'])
        self.assertEqual(config.get_parameter('a_dict'), {'k': 1})

    def test_set_parameter_overrides_config_file(self):
        config._config = {'label': 'from file'}
        config.set_parameter('label', 'from code')
        self.assertEqual(config.get_parameter('label'), 'from code')


class TestOverwriteFromArgs(ConfigTestCase):

    def setUp(self):
        super().setUp()
        self.use_config_file({})
        for name in ('feature', 'user', 'label'):
            os.environ.pop(name, None)

    def test_arguments_become_parameters(self):
        args = argparse.Namespace(feature=2, user='abn', label=None)
        config.overwrite_from_args(args)
        self.assertEqual(config.get_parameter('feature'), 2)
        self.assertEqual(config.get_parameter('user'), 'abn')

    def test_arguments_that_are_none_are_not_set(self):
        args = argparse.Namespace(feature=1, user=None, label=None)
        config.overwrite_from_args(args)
        self.assertNotIn('user', os.environ)
        self.assertNotIn('label', os.environ)
        self.assertIsNone(config.get_parameter('label'))

    def test_arguments_overwrite_existing_parameters(self):
        config.set_parameter('label', 'old')
        config.overwrite_from_args(argparse.Namespace(label='new'))
        self.assertEqual(config.get_parameter('label'), 'new')

    def test_python2_style_arguments_are_supported(self):
        # The first loop uses dict.iteritems(), which only exists in Python 2.
        # An argument object whose attributes offer iteritems() exercises it.
        class Python2Dict(dict):
            def iteritems(self):
                return iter(self.items())

        args = argparse.Namespace()
        args.__dict__ = Python2Dict(user='abn', label=None)
        config.overwrite_from_args(args)
        self.assertEqual(config.get_parameter('user'), 'abn')
        self.assertNotIn('label', os.environ)

    def test_invalid_args_object_is_ignored(self):
        # vars(None) raises a TypeError, which must not reach the caller
        config.overwrite_from_args(None)


if __name__ == '__main__':
    unittest.main()
