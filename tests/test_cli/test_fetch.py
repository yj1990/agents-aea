# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2018-2019 Fetch.AI Limited
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------
"""This test module contains the tests for CLI Registry fetch methods."""

from unittest import TestCase, mock

from click import ClickException
from click.testing import CliRunner

from aea.cli import cli
from aea.cli.fetch import _fetch_agent_locally, _is_version_correct

from tests.conftest import CLI_LOG_OPTION
from tests.test_cli.tools_for_testing import ContextMock, PublicIdMock


def _raise_click_exception(*args, **kwargs):
    raise ClickException("Message")


@mock.patch("builtins.open", mock.mock_open())
@mock.patch("aea.cli.fetch.os.path.join", return_value="joined-path")
@mock.patch("aea.cli.fetch.try_get_item_source_path", return_value="path")
@mock.patch("aea.cli.fetch.try_to_load_agent_config")
class FetchAgentLocallyTestCase(TestCase):
    """Test case for fetch_agent_locally method."""

    @mock.patch("aea.cli.fetch._is_version_correct", return_value=True)
    @mock.patch("aea.cli.fetch.os.path.exists", return_value=False)
    @mock.patch("aea.cli.fetch.copy_tree")
    def test_fetch_agent_locally_positive(self, copy_tree, *mocks):
        """Test for fetch_agent_locally method positive result."""
        _fetch_agent_locally(ContextMock(), PublicIdMock(), alias="some-alias")
        copy_tree.assert_called_once_with("path", "joined-path")

    @mock.patch("aea.cli.fetch._is_version_correct", return_value=True)
    @mock.patch("aea.cli.fetch.os.path.exists", return_value=True)
    @mock.patch("aea.cli.fetch.copy_tree")
    def test_fetch_agent_locally_already_exists(self, *mocks):
        """Test for fetch_agent_locally method agent already exists."""
        with self.assertRaises(ClickException):
            _fetch_agent_locally(ContextMock(), PublicIdMock())

    @mock.patch("aea.cli.fetch._is_version_correct", return_value=False)
    @mock.patch("aea.cli.fetch.os.path.exists", return_value=True)
    @mock.patch("aea.cli.fetch.copy_tree")
    def test_fetch_agent_locally_incorrect_version(self, *mocks):
        """Test for fetch_agent_locally method incorrect agent version."""
        with self.assertRaises(ClickException):
            _fetch_agent_locally(ContextMock(), PublicIdMock())

    @mock.patch("aea.cli.fetch._is_version_correct", return_value=True)
    @mock.patch("aea.cli.fetch._add_item")
    @mock.patch("aea.cli.fetch.os.path.exists", return_value=False)
    @mock.patch("aea.cli.fetch.copy_tree")
    def test__fetch_agent_locally_with_deps_positive(self, *mocks):
        """Test for fetch_agent_locally method with deps positive result."""
        public_id = PublicIdMock.from_str("author/name:0.1.0")
        ctx_mock = ContextMock(
            connections=[public_id],
            protocols=[public_id],
            skills=[public_id],
            contracts=[public_id],
        )
        _fetch_agent_locally(ctx_mock, PublicIdMock())

    @mock.patch("aea.cli.fetch._is_version_correct", return_value=True)
    @mock.patch("aea.cli.fetch.os.path.exists", return_value=False)
    @mock.patch("aea.cli.fetch.copy_tree")
    @mock.patch("aea.cli.fetch._add_item", _raise_click_exception)
    def test__fetch_agent_locally_with_deps_fail(self, *mocks):
        """Test for fetch_agent_locally method with deps ClickException catch."""
        public_id = PublicIdMock.from_str("author/name:0.1.0")
        ctx_mock = ContextMock(
            connections=[public_id],
            protocols=[public_id],
            skills=[public_id],
            contracts=[public_id],
        )
        with self.assertRaises(ClickException):
            _fetch_agent_locally(ctx_mock, PublicIdMock())


@mock.patch("aea.cli.fetch.fetch_agent")
@mock.patch("aea.cli.fetch._fetch_agent_locally")
class FetchCommandTestCase(TestCase):
    """Test case for CLI fetch command."""

    def setUp(self):
        """Set it up."""
        self.runner = CliRunner()

    def test_fetch_positive(self, *mocks):
        """Test for CLI push connection positive result."""
        self.runner.invoke(
            cli, [*CLI_LOG_OPTION, "fetch", "author/name:0.1.0"], standalone_mode=False,
        )
        self.runner.invoke(
            cli,
            [*CLI_LOG_OPTION, "fetch", "--local", "author/name:0.1.0"],
            standalone_mode=False,
        )


class IsVersionCorrectTestCase(TestCase):
    """Test case for _is_version_correct method."""

    def test__is_version_correct_positive(self):
        """Test for _is_version_correct method positive result."""
        ctx_mock = ContextMock(version="correct")
        public_id_mock = PublicIdMock()
        public_id_mock.version = "correct"
        result = _is_version_correct(ctx_mock, public_id_mock)
        self.assertTrue(result)

    def test__is_version_correct_negative(self):
        """Test for _is_version_correct method negative result."""
        ctx_mock = ContextMock(version="correct")
        public_id_mock = PublicIdMock()
        public_id_mock.version = "incorrect"
        result = _is_version_correct(ctx_mock, public_id_mock)
        self.assertFalse(result)
