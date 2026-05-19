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
import time
from typing import TYPE_CHECKING, Optional

import evdev
from evdev import ecodes

from src.hal.base import InputBase
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.utils.config import Config

logger = get_logger(__name__)

# Boot-time detection: some USB hubs are slow to enumerate the numpad, so
# we retry the initial scan a few times before falling through to the
# background rescan loop.
_INIT_RETRY_COUNT: int = 3
_INIT_RETRY_DELAY: float = 0.5

# Background reader thread sleeps this long between rescans while no
# device is attached (both during boot-time discovery and after a
# runtime disconnect).
_RESCAN_INTERVAL: float = 1.0

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
        """Find the USB numpad and start the reader thread.

        Retries the initial scan a few times to absorb slow USB enumeration
        on some powered hubs. The reader thread is started unconditionally
        — if no device was found, it keeps rescanning every
        ``_RESCAN_INTERVAL`` seconds so the numpad can be hot-plugged.
        """
        for attempt in range(1, _INIT_RETRY_COUNT + 1):
            device = self._find_numpad()
            if device is not None:
                self._attach(device)
                logger.info(
                    "NumpadInput initialized: %s (%s)",
                    device.name, device.path,
                )
                break
            if attempt < _INIT_RETRY_COUNT:
                logger.debug(
                    "Numpad not found (attempt %d/%d), retrying in %.1fs",
                    attempt, _INIT_RETRY_COUNT, _INIT_RETRY_DELAY,
                )
                time.sleep(_INIT_RETRY_DELAY)
        else:
            logger.warning(
                "No USB numpad found after %d attempts -- "
                "reader thread will keep scanning every %.1fs",
                _INIT_RETRY_COUNT, _RESCAN_INTERVAL,
            )

        self._running = True
        self._thread = threading.Thread(
            target=self._read_loop, daemon=True, name="NumpadInput",
        )
        self._thread.start()

    def is_connected(self) -> bool:
        """Return True if a numpad device is currently attached and grabbed."""
        return self._device is not None

    def get_key(self) -> Optional[str]:
        """Return the next buffered key, or None if the queue is empty.

        Returns:
            A key string or None.
        """
        try:
            return self._key_queue.get_nowait()
        except queue.Empty:
            return None

    def flush(self) -> None:
        """Discard all buffered key events."""
        while not self._key_queue.empty():
            try:
                self._key_queue.get_nowait()
            except queue.Empty:
                break

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

    def _attach(self, device: evdev.InputDevice) -> None:
        """Store the device and grab it exclusively.

        Used by both the boot-time ``init()`` path and the reader thread's
        runtime reconnect path so the two stay in sync. Exclusive grab
        prevents key events from leaking to the Linux console.
        """
        self._device = device
        try:
            device.grab()
            self._grabbed = True
            logger.debug("Numpad device grabbed exclusively")
        except (OSError, IOError):
            self._grabbed = False
            logger.warning("Could not grab numpad exclusively (already grabbed?)")

    def _read_loop(self) -> None:
        """Background thread: read evdev events and enqueue mapped keys."""
        while self._running:
            if self._device is None:
                device = self._find_numpad()
                if device is None:
                    time.sleep(_RESCAN_INTERVAL)
                    continue
                self._attach(device)
                logger.info(
                    "Numpad reconnected: %s (%s)",
                    self._device.name, self._device.path,
                )

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
                logger.warning("Numpad device disconnected, reconnecting...")
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
