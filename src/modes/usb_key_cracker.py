"""USB Key Cracker game mode.

The device can only be defused by inserting a USB stick containing a
``DEFUSE.KEY`` file.  Once inserted, a code-cracking animation plays:
digits cycle rapidly and lock into their correct values one by one.
Removing the USB stick during cracking cancels the process and all
progress is lost.
"""

import random
import time

from src.modes.base_mode import (
    BaseMode,
    GameContext,
    ModeResult,
    PlantingConfig,
    PlantingType,
    SetupOption,
    SetupOptionType,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _format_timer(seconds: int) -> str:
    """Format seconds as MM:SS string."""
    minutes, secs = divmod(max(seconds, 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def _center(text: str, width: int = 20) -> str:
    """Center text within the given width."""
    return text.center(width)


# Seconds between each digit being cracked.
_CRACK_INTERVAL: float = 2.5


class UsbKeyCrackerMode(BaseMode):
    """USB Key Cracker mode: insert a USB key to start code-cracking.

    Setup options:
        - Timer: countdown duration (30-5999 seconds).
        - Digits: code length (4-12), determines total cracking duration.

    The defuse sequence:
        1. Player inserts USB stick with ``DEFUSE.KEY`` file.
        2. Cracking animation starts — digits cycle randomly.
        3. Every ~2.5 s one digit locks into its correct value.
        4. All digits cracked → device defused.
        5. Removing the USB stick cancels cracking (progress lost).
    """

    name: str = "USB Key Cracker"
    description: str = "Insert USB key to crack the code"
    menu_key: str = "3"

    def get_planting_config(self) -> PlantingConfig:
        """Require holding Enter for 10 seconds to plant."""
        return PlantingConfig(
            planting_type=PlantingType.TIMED,
            duration=10,
        )

    def get_setup_options(self) -> list[SetupOption]:
        """Return timer and digit-count setup options."""
        return [
            SetupOption(
                key="timer",
                label="Timer",
                option_type=SetupOptionType.RANGE,
                default=300,
                min_val=30,
                max_val=5999,
                step=30,
                large_step=300,
            ),
            SetupOption(
                key="digits",
                label="Digits",
                option_type=SetupOptionType.RANGE,
                default=8,
                min_val=4,
                max_val=12,
                step=1,
                large_step=4,
            ),
        ]

    def on_armed(self, context: GameContext) -> None:
        """Generate the target code and initialise cracking state.

        Args:
            context: The game context for this round.
        """
        digits: int = context.setup_values.get("digits", 8)
        target = "".join(str(random.randint(0, 9)) for _ in range(digits))

        context.custom_data["target_code"] = target
        context.custom_data["cracking_active"] = False
        context.custom_data["cracking_start"] = 0.0
        context.custom_data["cracked_indices"] = []  # ordered list of cracked positions
        context.custom_data["crack_order"] = []       # random order to crack digits
        context.custom_data["last_crack_time"] = 0.0

        logger.info(
            "USB Key Cracker armed: %d digits, target=%s", digits, target
        )

    def on_input(self, key: str, context: GameContext) -> ModeResult:
        """Handle input — dot key toggles mock USB in desktop testing.

        Args:
            key: The pressed key string.
            context: The current game context.

        Returns:
            Always CONTINUE (defuse is detected via on_tick).
        """
        if key == "dot":
            usb = context.custom_data.get("usb_detector")
            if usb is not None and hasattr(usb, "toggle"):
                usb.toggle()
        return ModeResult.CONTINUE

    def on_tick(self, remaining_seconds: int, context: GameContext) -> ModeResult:
        """Poll USB key and advance cracking animation.

        Args:
            remaining_seconds: Seconds left on the timer.
            context: The current game context.

        Returns:
            DEFUSED when all digits are cracked, CONTINUE otherwise.
        """
        usb = context.custom_data.get("usb_detector")
        if usb is None:
            return ModeResult.CONTINUE

        key_present = usb.is_key_present()
        cracking = context.custom_data["cracking_active"]

        if cracking and not key_present:
            # USB removed during cracking — abort, lose progress
            logger.info("USB key removed — cracking aborted")
            context.custom_data["cracking_active"] = False
            context.custom_data["cracked_indices"] = []
            return ModeResult.CONTINUE

        if not cracking and key_present:
            # USB just inserted — start cracking
            self._start_cracking(context)
            return ModeResult.CONTINUE

        if cracking and key_present:
            # Cracking in progress — check if next digit should crack
            return self._advance_cracking(context)

        return ModeResult.CONTINUE

    def _start_cracking(self, context: GameContext) -> None:
        """Begin the cracking sequence."""
        digits = len(context.custom_data["target_code"])
        order = list(range(digits))
        random.shuffle(order)

        now = time.time()
        context.custom_data["cracking_active"] = True
        context.custom_data["cracking_start"] = now
        context.custom_data["cracked_indices"] = []
        context.custom_data["crack_order"] = order
        context.custom_data["last_crack_time"] = now
        logger.info("Cracking started, order=%s", order)

    def _advance_cracking(self, context: GameContext) -> ModeResult:
        """Crack the next digit if enough time has passed.

        Returns:
            DEFUSED when all digits are cracked.
        """
        now = time.time()
        last = context.custom_data["last_crack_time"]
        cracked = context.custom_data["cracked_indices"]
        order = context.custom_data["crack_order"]
        target = context.custom_data["target_code"]

        if now - last >= _CRACK_INTERVAL and len(cracked) < len(target):
            next_idx = order[len(cracked)]
            cracked.append(next_idx)
            context.custom_data["last_crack_time"] = now
            logger.debug(
                "Digit %d cracked (%s), %d/%d done",
                next_idx, target[next_idx], len(cracked), len(target),
            )

            if len(cracked) == len(target):
                logger.info("All digits cracked — device defused")
                return ModeResult.DEFUSED

        return ModeResult.CONTINUE

    # -- rendering ------------------------------------------------------------

    def _build_digit_display(self, context: GameContext) -> str:
        """Build the digit display string with cycling and cracked digits.

        Cracked digits show their real value.  Uncracked digits show
        a random digit (changes every render call for the cycling effect).

        Args:
            context: The current game context.

        Returns:
            Space-separated digit string, e.g. '7 3 * 2 * * * *'.
        """
        target = context.custom_data["target_code"]
        cracked = set(context.custom_data["cracked_indices"])
        parts: list[str] = []

        for i, digit in enumerate(target):
            if i in cracked:
                parts.append(digit)
            else:
                parts.append(str(random.randint(0, 9)))

        return " ".join(parts)

    def _build_progress_info(self, context: GameContext) -> tuple[str, str]:
        """Build cracking progress bar and status text.

        Returns:
            Tuple of (progress_bar_str, status_text).
        """
        target = context.custom_data["target_code"]
        cracked = context.custom_data["cracked_indices"]
        total = len(target)
        done = len(cracked)
        pct = int(done / total * 100) if total > 0 else 0

        # Simple progress bar fitting in 20 chars
        bar_width = 14
        filled = int(done / total * bar_width) if total > 0 else 0
        bar = "[" + "#" * filled + "." * (bar_width - filled) + "]"

        remaining_time = (total - done) * _CRACK_INTERVAL
        return bar + f" {pct:>2}%", f"Cracking... {int(remaining_time)}s"

    def render(self, display: object, remaining_seconds: int, context: GameContext) -> None:
        """Render the armed screen.

        Layout when waiting for USB:
            Line 0: ** {device_name} ARMED **
            Line 1: Timer
            Line 2: (empty)
            Line 3: Insert USB Key...

        Layout during cracking:
            Line 0: ** {device_name} ARMED **
            Line 1: Cracking...  Xs
            Line 2: [####........] XX%
            Line 3: 7 3 * 2 * * * *

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        dn = context.custom_data.get("device_name", "Prop").upper()
        cracking = context.custom_data.get("cracking_active", False)

        if not cracking:
            display.write_line(0, _center(f"** {dn} ARMED **"))
            display.write_line(1, _center(_format_timer(remaining_seconds)))
            display.write_line(2, _center(""))
            display.write_line(3, _center("Insert USB Key..."))
        else:
            progress_bar, status = self._build_progress_info(context)
            digits_display = self._build_digit_display(context)

            display.write_line(0, _center(f"** {dn} ARMED **"))
            display.write_line(1, _center(status))
            display.write_line(2, _center(progress_bar))
            display.write_line(3, _center(digits_display))

    def render_last_10s(self, display: object, remaining_seconds: int, context: GameContext) -> None:
        """Render during the last 10 seconds.

        Line 0 is handled by ArmedScreen (blinking timer).

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        cracking = context.custom_data.get("cracking_active", False)

        if not cracking:
            display.write_line(1, _center(""))
            display.write_line(2, _center("INSERT USB KEY!!"))
            display.write_line(3, _center(""))
        else:
            progress_bar, status = self._build_progress_info(context)
            digits_display = self._build_digit_display(context)

            display.write_line(1, _center(status))
            display.write_line(2, _center(progress_bar))
            display.write_line(3, _center(digits_display))
