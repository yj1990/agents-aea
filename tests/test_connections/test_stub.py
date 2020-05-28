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

"""This test module contains the tests for the stub connection."""

import base64
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

import aea
from aea.configurations.base import PublicId
from aea.connections.stub.connection import _process_line
from aea.mail.base import Envelope, Multiplexer
from aea.protocols.default.message import DefaultMessage
from aea.protocols.default.serialization import DefaultSerializer

from ..conftest import _make_stub_connection

SEPARATOR = ","


class TestStubConnectionReception:
    """Test that the stub connection is implemented correctly."""

    @classmethod
    def setup_class(cls):
        """Set the test up."""
        cls.cwd = os.getcwd()
        cls.tmpdir = Path(tempfile.mkdtemp())
        d = cls.tmpdir / "test_stub"
        d.mkdir(parents=True)
        cls.input_file_path = d / "input_file.csv"
        cls.output_file_path = d / "output_file.csv"
        cls.connection = _make_stub_connection(
            cls.input_file_path, cls.output_file_path
        )

        cls.multiplexer = Multiplexer([cls.connection])
        cls.multiplexer.connect()
        os.chdir(cls.tmpdir)

    def test_reception_a(self):
        """Test that the connection receives what has been enqueued in the input file."""
        msg = DefaultMessage(
            dialogue_reference=("", ""),
            message_id=1,
            target=0,
            performative=DefaultMessage.Performative.BYTES,
            content=b"hello",
        )
        expected_envelope = Envelope(
            to="any",
            sender="any",
            protocol_id=DefaultMessage.protocol_id,
            message=DefaultSerializer().encode(msg),
        )
        encoded_envelope = "{}{}{}{}{}{}{}{}".format(
            expected_envelope.to,
            SEPARATOR,
            expected_envelope.sender,
            SEPARATOR,
            expected_envelope.protocol_id,
            SEPARATOR,
            expected_envelope.message.decode("utf-8"),
            SEPARATOR,
        )
        encoded_envelope = encoded_envelope.encode("utf-8")

        with open(self.input_file_path, "ab+") as f:
            f.write(encoded_envelope)
            f.flush()

        actual_envelope = self.multiplexer.get(block=True, timeout=3.0)
        assert expected_envelope == actual_envelope

    def test_reception_b(self):
        """Test that the connection receives what has been enqueued in the input file."""
        # a message containing delimiters and newline characters
        msg = b"\x08\x02\x12\x011\x1a\x011 \x01:,\n*0x32468d\n,\nB8Ab795\n\n49B49C88DC991990E7910891,,dbd\n"
        protocol_id = PublicId.from_str("some_author/some_name:0.1.0")
        expected_envelope = Envelope(
            to="any", sender="any", protocol_id=protocol_id, message=msg,
        )
        encoded_envelope = "{}{}{}{}{}{}{}{}".format(
            expected_envelope.to,
            SEPARATOR,
            expected_envelope.sender,
            SEPARATOR,
            expected_envelope.protocol_id,
            SEPARATOR,
            expected_envelope.message.decode("utf-8"),
            SEPARATOR,
        )
        encoded_envelope = encoded_envelope.encode("utf-8")

        with open(self.input_file_path, "ab+") as f:
            f.write(encoded_envelope)
            f.flush()

        actual_envelope = self.multiplexer.get(block=True, timeout=3.0)
        assert expected_envelope == actual_envelope

    def test_reception_c(self):
        """Test that the connection receives what has been enqueued in the input file."""
        encoded_envelope = b"0x5E22777dD831A459535AA4306AceC9cb22eC4cB5,default_oef,fetchai/oef_search:0.1.0,\x08\x02\x12\x011\x1a\x011 \x01:,\n*0x32468dB8Ab79549B49C88DC991990E7910891dbd,"
        expected_envelope = Envelope(
            to="0x5E22777dD831A459535AA4306AceC9cb22eC4cB5",
            sender="default_oef",
            protocol_id=PublicId.from_str("fetchai/oef_search:0.1.0"),
            message=b"\x08\x02\x12\x011\x1a\x011 \x01:,\n*0x32468dB8Ab79549B49C88DC991990E7910891dbd",
        )
        with open(self.input_file_path, "ab+") as f:
            f.write(encoded_envelope)
            f.flush()

        actual_envelope = self.multiplexer.get(block=True, timeout=3.0)
        assert expected_envelope == actual_envelope

    def test_reception_fails(self):
        """Test the case when an error occurs during the processing of a line."""
        patch = mock.patch.object(aea.connections.stub.connection.logger, "error")
        mocked_logger_error = patch.start()
        with mock.patch(
            "aea.connections.stub.connection._decode",
            side_effect=Exception("an error."),
        ):
            _process_line(b"")
            mocked_logger_error.assert_called_with(
                "Error when processing a line. Message: an error."
            )

        patch.stop()

    @classmethod
    def teardown_class(cls):
        """Tear down the test."""
        os.chdir(cls.cwd)
        try:
            shutil.rmtree(cls.tmpdir)
        except (OSError, IOError):
            pass
        cls.multiplexer.disconnect()


class TestStubConnectionSending:
    """Test that the stub connection is implemented correctly."""

    @classmethod
    def setup_class(cls):
        """Set the test up."""
        cls.cwd = os.getcwd()
        cls.tmpdir = Path(tempfile.mkdtemp())
        d = cls.tmpdir / "test_stub"
        d.mkdir(parents=True)
        cls.input_file_path = d / "input_file.csv"
        cls.output_file_path = d / "output_file.csv"
        cls.connection = _make_stub_connection(
            cls.input_file_path, cls.output_file_path
        )

        cls.multiplexer = Multiplexer([cls.connection])
        cls.multiplexer.connect()
        os.chdir(cls.tmpdir)

    def test_connection_is_established(self):
        """Test the stub connection is established and then bad formatted messages."""
        assert self.connection.connection_status.is_connected
        msg = DefaultMessage(
            dialogue_reference=("", ""),
            message_id=1,
            target=0,
            performative=DefaultMessage.Performative.BYTES,
            content=b"hello",
        )
        encoded_envelope = "{}{}{}{}{}{}{}{}".format(
            "any",
            SEPARATOR,
            "any",
            SEPARATOR,
            DefaultMessage.protocol_id,
            SEPARATOR,
            DefaultSerializer().encode(msg).decode("utf-8"),
            SEPARATOR,
        )
        encoded_envelope = base64.b64encode(encoded_envelope.encode("utf-8"))
        envelope = _process_line(encoded_envelope)
        if envelope is not None:
            self.connection._put_envelopes([envelope])

        assert (
            self.connection.in_queue.empty()
        ), "The inbox must be empty due to bad encoded message"

    def test_send_message(self):
        """Test that the messages in the outbox are posted on the output file."""
        msg = DefaultMessage(
            dialogue_reference=("", ""),
            message_id=1,
            target=0,
            performative=DefaultMessage.Performative.BYTES,
            content=b"hello",
        )
        expected_envelope = Envelope(
            to="any",
            sender="any",
            protocol_id=DefaultMessage.protocol_id,
            message=DefaultSerializer().encode(msg),
        )

        self.multiplexer.put(expected_envelope)
        time.sleep(0.1)

        with open(self.output_file_path, "rb+") as f:
            lines = f.readlines()

        assert len(lines) == 2
        line = lines[0] + lines[1]
        to, sender, protocol_id, message, end = line.strip().split(
            "{}".format(SEPARATOR).encode("utf-8"), maxsplit=4
        )
        to = to.decode("utf-8")
        sender = sender.decode("utf-8")
        protocol_id = PublicId.from_str(protocol_id.decode("utf-8"))
        assert end in [b"", b"\n"]

        actual_envelope = Envelope(
            to=to, sender=sender, protocol_id=protocol_id, message=message
        )
        assert expected_envelope == actual_envelope

    @classmethod
    def teardown_class(cls):
        """Tear down the test."""
        os.chdir(cls.cwd)
        try:
            shutil.rmtree(cls.tmpdir)
        except (OSError, IOError):
            pass
        cls.multiplexer.disconnect()


@pytest.mark.asyncio
async def test_disconnection_when_already_disconnected():
    """Test the case when disconnecting a connection already disconnected."""
    tmpdir = Path(tempfile.mkdtemp())
    d = tmpdir / "test_stub"
    d.mkdir(parents=True)
    input_file_path = d / "input_file.csv"
    output_file_path = d / "output_file.csv"
    connection = _make_stub_connection(input_file_path, output_file_path)

    assert not connection.connection_status.is_connected
    await connection.disconnect()
    assert not connection.connection_status.is_connected


@pytest.mark.asyncio
async def test_connection_when_already_connected():
    """Test the case when connecting a connection already connected."""
    tmpdir = Path(tempfile.mkdtemp())
    d = tmpdir / "test_stub"
    d.mkdir(parents=True)
    input_file_path = d / "input_file.csv"
    output_file_path = d / "output_file.csv"
    connection = _make_stub_connection(input_file_path, output_file_path)

    assert not connection.connection_status.is_connected
    await connection.connect()
    assert connection.connection_status.is_connected
    await connection.connect()
    assert connection.connection_status.is_connected

    await connection.disconnect()


@pytest.mark.asyncio
async def test_receiving_returns_none_when_error_occurs():
    """Test that when we try to receive an envelope and an error occurs we return None."""
    tmpdir = Path(tempfile.mkdtemp())
    d = tmpdir / "test_stub"
    d.mkdir(parents=True)
    input_file_path = d / "input_file.csv"
    output_file_path = d / "output_file.csv"
    connection = _make_stub_connection(input_file_path, output_file_path)

    await connection.connect()
    with mock.patch.object(connection.in_queue, "get", side_effect=Exception):
        ret = await connection.receive()
        assert ret is None

    await connection.disconnect()
