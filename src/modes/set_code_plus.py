"""Set Code+ game mode.

Like Set Code, but each digit is checked immediately on entry.
A correct digit stays (shown as *); a wrong digit is rejected and
a time penalty is applied. The secret code is never revealed.
"""

import time

from src.modes.base_mode import (
    GameContext,
    ModeResult,
    PlantingConfig,
    PlantingType,
    SetupOption,
    SetupOptionType,
)
from src.modes.set_code import SetCodeMode, _center, _format_timer
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Duration (seconds) for the "WRONG!" flash on the display.
_FLASH_DURATION: float = 0.7

# Fallback if config value is missing.
_DEFAULT_PENALTY: int = 10


class SetCodePlusMode(SetCodeMode):
    """Set Code+ mode: digit-by-digit verification with time penalty.

    The secret code is NOT displayed. Each entered digit is immediately
    compared. Correct digits are shown as ``*``, wrong digits are
    discarded and a time penalty is applied.

    Setup options are identical to Set Code (timer + secret code).
    """

    name: str = "Set Code+"
    description: str = "Each wrong digit costs time"
    menu_key: str = "5"

    def get_planting_config(self) -> PlantingConfig:
        """Require a 10-digit random activation code to plant."""
        return PlantingConfig(
            planting_type=PlantingType.CODE_ENTRY,
            code_length=10,
        )

    def on_armed(self, context: GameContext) -> None:
        """Store the secret code and initialise penalty tracking.

        Args:
            context: The game context for this round.
        """
        super().on_armed(context)
        context.custom_data["penalty_flash_until"] = 0.0
        context.custom_data["last_penalty"] = 0

    def on_input(self, key: str, context: GameContext) -> ModeResult:
        """Check each digit immediately against the secret code.

        Correct digit: appended to input (displayed as *).
        Wrong digit: rejected, time penalty applied, penalty flag set.

        Args:
            key: The pressed key string.
            context: The current game context.

        Returns:
            DEFUSED when all digits correct, DETONATED if penalty
            drops timer to zero, CONTINUE otherwise.
        """
        code: str = context.custom_data["code"]
        current_input: str = context.custom_data["input"]
        penalty: int = context.custom_data.get("penalty_seconds", _DEFAULT_PENALTY)

        # No backspace in plus mode — digits are verified immediately
        if key == "backspace":
            return ModeResult.CONTINUE

        if key in "0123456789" and len(current_input) < len(code):
            position = len(current_input)
            if key == code[position]:
                # Correct digit
                current_input += key
                context.custom_data["input"] = current_input
                logger.debug("Digit %d correct", position + 1)

                # All digits entered correctly?
                if len(current_input) == len(code):
                    logger.info("Secret code matched - device defused")
                    return ModeResult.DEFUSED
            else:
                # Wrong digit — apply time penalty
                context.remaining_seconds = max(0, context.remaining_seconds - penalty)
                context.custom_data["penalty_flash_until"] = time.time() + _FLASH_DURATION
                context.custom_data["last_penalty"] = penalty
                context.custom_data["penalty_triggered"] = True
                logger.info(
                    "Wrong digit at position %d, -%ds penalty",
                    position + 1, penalty,
                )

                if context.remaining_seconds <= 0:
                    return ModeResult.DETONATED

        return ModeResult.CONTINUE

    # -- rendering helpers ----------------------------------------------------

    def _is_flashing(self, context: GameContext) -> bool:
        """Check if the penalty flash is currently active."""
        return time.time() < context.custom_data.get("penalty_flash_until", 0.0)

    def _penalty_text(self, context: GameContext) -> str:
        """Build the penalty flash text, e.g. 'WRONG! -10s'."""
        secs = context.custom_data.get("last_penalty", _DEFAULT_PENALTY)
        return f"WRONG! -{secs}s"

    def _build_input_display(self, context: GameContext) -> str:
        """Build input display: correct digits as *, remaining as _.

        The secret code is never shown. Example for a 6-digit code
        with 3 correct entries: ``> ***___``

        Args:
            context: The current game context.

        Returns:
            Formatted input string.
        """
        code: str = context.custom_data["code"]
        current_input: str = context.custom_data["input"]
        confirmed = len(current_input)
        remaining = len(code) - confirmed
        return f"> {'*' * confirmed}{'_' * remaining}"

    # -- rendering ------------------------------------------------------------

    def render(self, display: object, remaining_seconds: int, context: GameContext) -> None:
        """Render armed screen with hidden code and penalty flash.

        Layout:
            Line 0: ** {device_name} ARMED **
            Line 1: Timer MM:SS
            Line 2: 'Enter Code:'
            Line 3: '> ***___' / 'WRONG! -Xs' during flash

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        dn = context.custom_data.get("device_name", "Prop").upper()
        display.write_line(0, _center(f"** {dn} ARMED **"))
        display.write_line(1, _center(_format_timer(remaining_seconds)))
        display.write_line(2, _center("Enter Code:"))

        if self._is_flashing(context):
            display.write_line(3, _center(self._penalty_text(context)))
        else:
            display.write_line(3, _center(self._build_input_display(context)))

    def render_last_10s(self, display: object, remaining_seconds: int, context: GameContext) -> None:
        """Render during the last 10 seconds with penalty flash support.

        Line 0 is handled by armed screen (!! MM:SS !! ARMED !!).

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        display.write_line(1, _center(""))
        display.write_line(2, _center("Enter Code:"))

        if self._is_flashing(context):
            display.write_line(3, _center(self._penalty_text(context)))
        else:
            display.write_line(3, _center(self._build_input_display(context)))
