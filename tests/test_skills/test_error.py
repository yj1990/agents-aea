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

"""The test error skill module contains the tests of the error skill."""

import logging
import os
from pathlib import Path
from threading import Thread

from aea.aea import AEA
from aea.crypto.fetchai import FetchAICrypto
from aea.crypto.ledger_apis import LedgerApis
from aea.crypto.wallet import Wallet
from aea.identity.base import Identity
from aea.mail.base import Envelope, InBox, Multiplexer
from aea.protocols.default.message import DefaultMessage
from aea.protocols.default.serialization import DefaultSerializer
from aea.registries.resources import Resources
from aea.skills.base import SkillContext
from aea.skills.error.handlers import ErrorHandler

from packages.fetchai.protocols.fipa.message import FipaMessage
from packages.fetchai.protocols.fipa.serialization import FipaSerializer

from tests.common.utils import wait_for_condition

from ..conftest import CUR_PATH, _make_dummy_connection


logger = logging.getLogger(__file__)


class InboxWithHistory(InBox):
    """Inbox with history of all messages every fetched."""

    def __init__(self, multiplexer: Multiplexer):
        """Inin inbox."""
        super().__init__(multiplexer)
        self._history = []  # type: ignore

    def get(self, *args, **kwargs) -> Envelope:
        """Get envelope."""
        item = super().get(*args, **kwargs)
        self._history.append(item)
        return item


class TestSkillError:
    """Test the skill: Error."""

    def setup(self):
        """Test the initialisation of the AEA."""
        private_key_path = os.path.join(CUR_PATH, "data", "fet_private_key.txt")
        self.wallet = Wallet({FetchAICrypto.identifier: private_key_path})
        self.ledger_apis = LedgerApis({}, FetchAICrypto.identifier)
        self.agent_name = "Agent0"

        self.connection = _make_dummy_connection()
        self.connections = [self.connection]
        self.identity = Identity(
            self.agent_name, address=self.wallet.addresses[FetchAICrypto.identifier]
        )
        self.address = self.identity.address
        self.my_aea = AEA(
            self.identity,
            self.connections,
            self.wallet,
            self.ledger_apis,
            timeout=0.1,
            resources=Resources(str(Path(CUR_PATH, "data/dummy_aea"))),
        )

        self.my_aea._inbox = InboxWithHistory(self.my_aea.multiplexer)
        self.skill_context = SkillContext(self.my_aea._context)
        logger_name = "aea.{}.skills.{}.{}".format(
            self.my_aea._context.agent_name, "fetchai", "error"
        )
        self.skill_context._logger = logging.getLogger(logger_name)
        self.my_error_handler = ErrorHandler(
            name="error", skill_context=self.skill_context
        )
        self.t = Thread(target=self.my_aea.start)
        self.t.start()
        wait_for_condition(
            lambda: self.my_aea._main_loop and self.my_aea._main_loop.is_running, 10
        )

    def test_error_handler_handle(self):
        """Test the handle function."""
        msg = FipaMessage(
            message_id=1,
            dialogue_reference=(str(0), ""),
            target=0,
            performative=FipaMessage.Performative.ACCEPT,
        )
        msg.counterparty = "a_counterparty"
        self.my_error_handler.handle(message=msg)

    def test_error_skill_unsupported_protocol(self):
        """Test the unsupported error message."""
        self.my_aea._inbox._history = []
        msg = FipaMessage(
            message_id=1,
            dialogue_reference=(str(0), ""),
            target=0,
            performative=FipaMessage.Performative.ACCEPT,
        )
        msg_bytes = FipaSerializer().encode(msg)
        envelope = Envelope(
            to=self.address,
            sender=self.address,
            protocol_id=FipaMessage.protocol_id,
            message=msg_bytes,
        )

        self.my_error_handler.send_unsupported_protocol(envelope)

        wait_for_condition(lambda: len(self.my_aea._inbox._history) >= 1, timeout=5)
        envelope = self.my_aea._inbox._history[-1]
        msg = DefaultSerializer().decode(envelope.message)
        assert msg.performative == DefaultMessage.Performative.ERROR
        assert msg.error_code == DefaultMessage.ErrorCode.UNSUPPORTED_PROTOCOL

    def test_error_decoding_error(self):
        """Test the decoding error."""
        self.my_aea._inbox._history = []
        msg = FipaMessage(
            message_id=1,
            dialogue_reference=(str(0), ""),
            target=0,
            performative=FipaMessage.Performative.ACCEPT,
        )
        msg_bytes = FipaSerializer().encode(msg)
        envelope = Envelope(
            to=self.address,
            sender=self.address,
            protocol_id=DefaultMessage.protocol_id,
            message=msg_bytes,
        )

        self.my_error_handler.send_decoding_error(envelope)
        wait_for_condition(lambda: len(self.my_aea._inbox._history) >= 1, timeout=5)
        envelope = self.my_aea._inbox._history[-1]

        msg = DefaultSerializer().decode(envelope.message)
        assert msg.performative == DefaultMessage.Performative.ERROR
        assert msg.error_code == DefaultMessage.ErrorCode.DECODING_ERROR

    def test_error_unsupported_skill(self):
        """Test the unsupported skill."""
        msg = FipaMessage(
            message_id=1,
            dialogue_reference=(str(0), ""),
            target=0,
            performative=FipaMessage.Performative.ACCEPT,
        )
        msg_bytes = FipaSerializer().encode(msg)
        envelope = Envelope(
            to=self.address,
            sender=self.address,
            protocol_id=DefaultMessage.protocol_id,
            message=msg_bytes,
        )

        self.my_error_handler.send_unsupported_skill(envelope=envelope)

        wait_for_condition(lambda: len(self.my_aea._inbox._history) >= 1, timeout=5)
        envelope = self.my_aea._inbox._history[-1]

        msg = DefaultSerializer().decode(envelope.message)
        assert msg.performative == DefaultMessage.Performative.ERROR
        assert msg.error_code == DefaultMessage.ErrorCode.UNSUPPORTED_SKILL

    def teardown(self):
        """Teardown method."""
        self.my_aea.stop()
        self.t.join()
