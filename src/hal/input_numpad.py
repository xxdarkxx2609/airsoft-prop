"""USB numpad input via evdev on Linux.

Reads key events from a USB HID numpad (e.g. Delock 12481) by scanning
``/dev/input/event*`` for devices with numpad key capabilities.  Events
are read in a background daemon thread and mapped to the application's
standardized key strings.

Requires the ``evdev`` package and the user to be in the ``input``
group (configured by ``install.sh``).
"""

from __future__ import annotations

import queue
import select
import threading
from typing import TYPE_CHECKING, Optional

import evdev
from evdev import ecodes

from src.hal.base import InputBase
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.utils.config import Config

logger = get_logger(__name__)

# evdev keycode -> application key string
_KEY_MAP: dict[int, str] = {
    ecodes.KEY_KP0: "0",
    ecodes.KEY_KP1: "1",
    ecodes.KEY_KP2: "2",
    ecodes.KEY_KP3: "3",
    ecodes.KEY_KP4: "4",
    ecodes.KEY_KP5: "5",
    ecodes.KEY_KP6: "6",
    ecodes.KEY_KP7: "7",
    ecodes.KEY_KP8: "8",
    ecodes.KEY_KP9: "9",
    ecodes.KEY_KPENTER: "enter",
    ecodes.KEY_BACKSPACE: "backspace",
    ecodes.KEY_KPPLUS: "plus",
    ecodes.KEY_KPMINUS: "minus",
    ecodes.KEY_KPDOT: "dot",
    ecodes.KEY_NUMLOCK: "numlock",
    # Arrow keys (sent when NumLock is off on some numpads)
    ecodes.KEY_UP: "up",
    ecodes.KEY_DOWN: "down",
    ecodes.KEY_LEFT: "left",
    ecodes.KEY_RIGHT: "right",
    # Operator keys (unaffected by NumLock)
    ecodes.KEY_KPSLASH: "slash",
    ecodes.KEY_KPASTERISK: "asterisk",
}


class NumpadInput(InputBase):
    """USB numpad input using evdev on Linux.

    Runs a background daemon thread that reads key events from the
    detected numpad device.  Keys are buffered in a thread-safe queue
    so that ``get_key()`` is non-blocking.
    """

    def __init__(self, config: Config) -> None:
        """Prepare internal state without opening any device yet.

        Args:
            config: Application configuration (currently unused but
                accepted for interface consistency).
        """
        self._config = config
        self._key_queue: queue.Queue[str] = queue.Queue()
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._device: Optional[evdev.InputDevice] = None
        self._grabbed: bool = False

    def init(self) -> None:
        """Find the USB numpad, grab it, and start the reader thread."""
        self._device = self._find_numpad()
        if self._device is None:
            logger.warning("No USB numpad found -- input will be unavailable")
            return

        # Grab exclusively so keys don't leak to the Linux console.
        try:
            self._device.grab()
            self._grabbed = True
            logger.debug("Numpad device grabbed exclusively")
        except (OSError, IOError):
            logger.warning("Could not grab numpad exclusively (already grabbed?)")

        self._running = True
        self._thread = threading.Thread(
            target=self._read_loop, daemon=True, name="NumpadInput",
        )
        self._thread.start()
        logger.info(
            "NumpadInput initialized: %s (%s)", self._device.name, self._device.path,
        )

    def get_key(self) -> Optional[str]:
        """Return the next buffered key, or None if the queue is empty.

        Returns:
            A key string or None.
        """
        try:
            return self._key_queue.get_nowait()
        except queue.Empty:
            return None

    def shutdown(self) -> None:
        """Stop the reader thread and release the device."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._device is not None:
            try:
                if self._grabbed:
                    self._device.ungrab()
            except (OSError, IOError):
                pass
            try:
                self._device.close()
            except (OSError, IOError):
                pass
            self._device = None
            self._grabbed = False
        logger.info("NumpadInput shut down")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_numpad() -> Optional[evdev.InputDevice]:
        """Scan ``/dev/input/event*`` for a device with numpad capabilities.

        Returns:
            The first matching ``InputDevice``, or None.
        """
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
            except (OSError, IOError):
                continue
            caps = dev.capabilities().get(ecodes.EV_KEY, [])
            if ecodes.KEY_KP0 in caps and ecodes.KEY_KP9 in caps:
                return dev
            dev.close()
        return None

    def _read_loop(self) -> None:
        """Background thread: read evdev events and enqueue mapped keys."""
        assert self._device is not None  # noqa: S101
        while self._running:
            try:
                # Non-blocking read with 100ms timeout for clean shutdown.
                r, _, _ = select.select([self._device.fd], [], [], 0.1)
                if not r:
                    continue
                for event in self._device.read():
                    if event.type != ecodes.EV_KEY:
                        continue
                    # Accept key-down (value=1) and key-repeat (value=2).
                    # Repeat events are needed so that held keys (e.g. Enter
                    # during timed planting) keep updating _last_enter_time
                    # before HOLD_TIMEOUT expires.  Ignore key-up (value=0).
                    if event.value == 0:
                        continue
                    key_str = _KEY_MAP.get(event.code)
                    if key_str is not None:
                        self._key_queue.put(key_str)
                        logger.debug("NumpadInput key: %s", key_str)
            except (OSError, IOError):
                logger.warning("Numpad device disconnected")
                self._running = False
                break
