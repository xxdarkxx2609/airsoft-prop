"""Tests for src.hal.input_mock — keyboard queue behaviour.

These tests use the ``external_key_queue`` constructor argument to
inject keys without starting the background reader thread (which would
put the test terminal into raw mode).
"""

import queue

from src.hal.input_mock import MockInput


class TestGetKey:
    """Keys come out in FIFO order via the external queue."""

    def test_keys_returned_in_fifo_order(self) -> None:
        ext: queue.Queue[str] = queue.Queue()
        mock = MockInput(external_key_queue=ext)
        for k in ("1", "2", "enter"):
            ext.put(k)
        assert mock.get_key() == "1"
        assert mock.get_key() == "2"
        assert mock.get_key() == "enter"

    def test_get_key_returns_none_when_empty(self) -> None:
        mock = MockInput(external_key_queue=queue.Queue())
        assert mock.get_key() is None


class TestFlush:
    """``flush`` drains both the external and internal queues."""

    def test_flush_drains_queue(self) -> None:
        ext: queue.Queue[str] = queue.Queue()
        mock = MockInput(external_key_queue=ext)
        for k in ("1", "2", "3"):
            ext.put(k)
        mock.flush()
        assert mock.get_key() is None
