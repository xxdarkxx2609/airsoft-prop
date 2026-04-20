"""Mock input implementation for desktop testing.

Reads keyboard input from stdin in a background thread and maps
standard keyboard keys to the numpad key names used by the application.

Platform support:
- Windows: uses msvcrt for non-blocking key reading.
- Linux/macOS: uses select + termios for raw terminal input.
"""

import platform
import queue
import sys
import threading
from typing import Optional

from src.hal.base import InputBase
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MockInput(InputBase):
    """Keyboard-based mock of the USB numpad input.

    Runs a background daemon thread that reads keypresses and maps them
    to the standardized key strings expected by the application. Keys are
    buffered in a thread-safe queue so that ``get_key()`` is non-blocking.

    An optional shared ``external_key_queue`` can be provided (e.g. from
    ``PygameDisplay``) so that key events from the graphical window are
    also consumed by ``get_key()``.

    Key mapping:
        0-9         -> '0'-'9'
        Enter       -> 'enter'
        Backspace   -> 'backspace'
        Arrow keys  -> 'up'/'down'/'left'/'right'
        +/-         -> 'plus'/'minus'
        .           -> 'dot'
    """

    def __init__(
        self,
        external_key_queue: Optional["queue.Queue[str]"] = None,
    ) -> None:
        """Initialize internal state (not yet reading keys).

        Args:
            external_key_queue: Optional queue shared with an external input
                source such as ``PygameDisplay``. Keys placed in this queue
                are returned by ``get_key()`` alongside terminal keyboard
                events.
        """
        self._key_queue: queue.Queue[str] = queue.Queue()
        self._external_key_queue: Optional[queue.Queue[str]] = external_key_queue
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

    def init(self) -> None:
        """Start the background key-reading thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._read_loop, daemon=True, name="MockInput"
        )
        self._thread.start()
        logger.info("MockInput initialized (keyboard reader started)")

    def get_key(self) -> Optional[str]:
        """Return the next buffered key, or None if both queues are empty.

        Checks the external key queue (e.g. pygame window) first, then
        the internal terminal keyboard queue.

        Returns:
            A key string or None.
        """
        if self._external_key_queue is not None:
            try:
                return self._external_key_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            return self._key_queue.get_nowait()
        except queue.Empty:
            return None

    def flush(self) -> None:
        """Discard all buffered key events."""
        for q in (self._external_key_queue, self._key_queue):
            if q is None:
                continue
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

    def shutdown(self) -> None:
        """Stop the background reader thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        logger.info("MockInput shut down")

    # ------------------------------------------------------------------
    # Platform-specific key reading
    # ------------------------------------------------------------------

    def _read_loop(self) -> None:
        """Main loop for the background reader thread.

        Delegates to the platform-specific implementation.
        """
        system = platform.system()
        if system == "Windows":
            self._read_loop_windows()
        else:
            self._read_loop_unix()

    def _read_loop_windows(self) -> None:
        """Read keys on Windows using msvcrt."""
        import msvcrt  # noqa: WPS433 (import inside function for platform guard)

        while self._running:
            if msvcrt.kbhit():
                raw = msvcrt.getch()

                # Extended / special keys start with 0x00 or 0xE0
                if raw in (b"\x00", b"\xe0"):
                    ext = msvcrt.getch()
                    key = self._map_windows_extended(ext)
                else:
                    key = self._map_char(raw)

                if key is not None:
                    self._enqueue(key)
            else:
                # Small sleep to avoid busy-waiting
                import time
                time.sleep(0.02)

    def _read_loop_unix(self) -> None:
        """Read keys on Linux/macOS using raw terminal mode."""
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while self._running:
                # Wait up to 50ms for input
                ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                if ready:
                    raw = sys.stdin.read(1)
                    if raw == "\x1b":
                        # Escape sequence (arrow keys, etc.)
                        key = self._read_escape_sequence()
                    else:
                        key = self._map_char(raw.encode("latin-1"))
                    if key is not None:
                        self._enqueue(key)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _read_escape_sequence(self) -> Optional[str]:
        """Parse a Unix escape sequence into a key name.

        Assumes the leading ESC (``\\x1b``) has already been consumed.

        Returns:
            A mapped key string or None if the sequence is unrecognized.
        """
        import select

        # Check for the '[' bracket within a short timeout
        ready, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not ready:
            return None
        bracket = sys.stdin.read(1)
        if bracket != "[":
            return None

        ready, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not ready:
            return None
        code = sys.stdin.read(1)

        arrow_map: dict[str, str] = {
            "A": "up",
            "B": "down",
            "C": "right",
            "D": "left",
        }
        return arrow_map.get(code)

    # ------------------------------------------------------------------
    # Key mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_char(raw: bytes) -> Optional[str]:
        """Map a single raw byte to a key name.

        Args:
            raw: A single byte read from stdin.

        Returns:
            The mapped key string or None if unmapped.
        """
        char_map: dict[bytes, str] = {
            b"\r": "enter",
            b"\n": "enter",
            b"\x08": "backspace",  # Backspace (BS)
            b"\x7f": "backspace",  # Delete (DEL, typical on Unix terminals)
            b"+": "plus",
            b"-": "minus",
            b".": "dot",
            b"*": "asterisk",
            b"/": "slash",
        }
        if raw in char_map:
            return char_map[raw]

        # Digit keys
        try:
            ch = raw.decode("ascii")
        except (UnicodeDecodeError, ValueError):
            return None
        if ch.isdigit():
            return ch
        return None

    @staticmethod
    def _map_windows_extended(ext: bytes) -> Optional[str]:
        """Map a Windows extended key code to a key name.

        Args:
            ext: The second byte of an extended key sequence.

        Returns:
            The mapped key string or None if unmapped.
        """
        ext_map: dict[bytes, str] = {
            b"H": "up",
            b"P": "down",
            b"K": "left",
            b"M": "right",
        }
        return ext_map.get(ext)

    def _enqueue(self, key: str) -> None:
        """Add a key to the queue and log it.

        Args:
            key: The mapped key string.
        """
        self._key_queue.put(key)
        logger.debug("MockInput key: %s", key)
