"""Real audio playback via pygame-ce mixer.

Loads sound files from the paths defined in ``config/default.yaml``
under ``audio.sounds`` and plays them through the system's default
audio device (USB speaker or PWM on GPIO18).

Mixer parameters (frequency, buffer size) are read from
``config/hardware.yaml`` under the ``audio`` section.  For USB
speakers use 44100 Hz / 2048 buffer; for PWM use 22050 Hz / 512.
"""

from __future__ import annotations

import array
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pygame.mixer

from src.hal.base import AudioBase
from src.utils.logger import get_logger
from src.utils.paths import get_project_root

if TYPE_CHECKING:
    from src.utils.config import Config

logger = get_logger(__name__)

# Number of times to retry mixer initialisation (USB devices may not
# be enumerated immediately after boot).
_MIXER_INIT_RETRIES: int = 3
_MIXER_RETRY_DELAY: float = 2.0


class PygameAudio(AudioBase):
    """Audio playback using pygame-ce mixer.

    Sounds are pre-loaded as ``pygame.mixer.Sound`` objects during
    ``init()`` for low-latency playback during gameplay.
    """

    def __init__(self, config: Config) -> None:
        """Prepare audio state without initializing the mixer yet.

        Args:
            config: Application configuration (reads ``audio.*``).
        """
        self._config = config
        self._volume: float = 0.8
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._project_root: Path = get_project_root()
        self._keepalive_channel: pygame.mixer.Channel | None = None

    def init(self) -> None:
        """Initialize the pygame mixer and pre-load all configured sounds.

        Retries mixer initialization up to ``_MIXER_INIT_RETRIES`` times
        to handle USB audio devices that are not yet enumerated at boot.
        """
        frequency = int(self._config.get("audio", "frequency", default=44100))
        buffer = int(self._config.get("audio", "buffer", default=1024))

        for attempt in range(_MIXER_INIT_RETRIES):
            try:
                pygame.mixer.init(
                    frequency=frequency, size=-16, channels=2, buffer=buffer,
                )
                pygame.mixer.set_num_channels(4)
                break
            except pygame.error as exc:
                if attempt < _MIXER_INIT_RETRIES - 1:
                    logger.warning(
                        "Mixer init attempt %d/%d failed: %s — retrying in %.0fs",
                        attempt + 1, _MIXER_INIT_RETRIES, exc, _MIXER_RETRY_DELAY,
                    )
                    time.sleep(_MIXER_RETRY_DELAY)
                else:
                    logger.warning(
                        "PygameAudio: mixer init failed after %d attempts: %s",
                        _MIXER_INIT_RETRIES, exc,
                    )
                    return

        # Load sounds from config mapping.
        # Custom overrides in custom/sounds/ take priority over defaults.
        custom_sounds_dir = self._project_root / "custom" / "sounds"
        sound_paths: dict[str, str] = self._config.get("audio", "sounds", default={})
        for name, rel_path in sound_paths.items():
            filename = Path(rel_path).name
            custom_path = custom_sounds_dir / filename
            if custom_path.exists():
                full_path = custom_path
            else:
                full_path = self._project_root / rel_path
            if not full_path.exists():
                logger.warning("Sound file not found: %s", full_path)
                continue
            try:
                self._sounds[name] = pygame.mixer.Sound(str(full_path))
                logger.debug("Loaded sound '%s' from %s", name, full_path)
            except pygame.error as exc:
                logger.warning("Failed to load sound '%s': %s", name, exc)

        # Start a silent keepalive loop on a dedicated channel to prevent
        # USB speakers from entering power-save mode.  Without this, the
        # first ~150ms of short sounds (like beep) are lost while the DAC
        # wakes up.
        self._start_keepalive()

        logger.info("PygameAudio initialized (%d sounds loaded)", len(self._sounds))

    def _start_keepalive(self) -> None:
        """Play an inaudible tone on a reserved channel to keep USB DACs awake.

        Uses amplitude 1 (out of 32767) instead of true silence — some USB
        DACs detect all-zero samples and enter power-save anyway.
        """
        try:
            freq, fmt, channels = pygame.mixer.get_init()
            n_samples = abs(freq)  # 1 second worth
            # Amplitude 1 is ~0.003% of max — completely inaudible but
            # keeps the DAC from seeing an all-zero stream.
            keepalive_data = array.array("h", [1, -1] * ((n_samples * channels) // 2))
            keepalive_sound = pygame.mixer.Sound(buffer=keepalive_data)
            # Reserve the last channel so normal sounds are not affected.
            self._keepalive_channel = pygame.mixer.Channel(
                pygame.mixer.get_num_channels() - 1,
            )
            self._keepalive_channel.play(keepalive_sound, loops=-1)
            logger.debug("USB keepalive started on channel %d",
                         pygame.mixer.get_num_channels() - 1)
        except (pygame.error, Exception) as exc:
            logger.warning("Failed to start USB keepalive: %s", exc)
            self._keepalive_channel = None

    def _reinit_mixer(self) -> bool:
        """Attempt to reinitialise the mixer after a device loss.

        This can happen on Pi Zero WH when a USB stick is inserted and
        the USB bus briefly re-enumerates, causing the USB speaker to
        disconnect and reconnect.

        Returns:
            True if reinitialisation succeeded.
        """
        logger.warning("Attempting mixer reinitialisation after device loss")
        try:
            pygame.mixer.quit()
        except pygame.error:
            pass

        frequency = int(self._config.get("audio", "frequency", default=44100))
        buffer = int(self._config.get("audio", "buffer", default=1024))

        for attempt in range(_MIXER_INIT_RETRIES):
            try:
                pygame.mixer.init(
                    frequency=frequency, size=-16, channels=2, buffer=buffer,
                )
                pygame.mixer.set_num_channels(4)
                # Reload all sound objects — old ones reference the dead device.
                sound_paths: dict[str, str] = self._config.get(
                    "audio", "sounds", default={}
                )
                self._sounds.clear()
                for name, rel_path in sound_paths.items():
                    full_path = self._project_root / rel_path
                    if not full_path.exists():
                        continue
                    try:
                        self._sounds[name] = pygame.mixer.Sound(str(full_path))
                    except pygame.error:
                        pass
                self._start_keepalive()
                logger.info(
                    "Mixer reinitialised successfully (%d sounds)", len(self._sounds)
                )
                return True
            except pygame.error as exc:
                if attempt < _MIXER_INIT_RETRIES - 1:
                    logger.warning(
                        "Mixer reinit attempt %d/%d failed: %s — retrying in %.0fs",
                        attempt + 1, _MIXER_INIT_RETRIES, exc, _MIXER_RETRY_DELAY,
                    )
                    time.sleep(_MIXER_RETRY_DELAY)
                else:
                    logger.error(
                        "Mixer reinit failed after %d attempts", _MIXER_INIT_RETRIES
                    )
        return False

    def play(self, sound_name: str) -> None:
        """Play a sound by name (single shot).

        Args:
            sound_name: Key from ``audio.sounds`` config mapping.
        """
        sound = self._sounds.get(sound_name)
        if sound is None:
            logger.warning("Unknown sound '%s'", sound_name)
            return
        try:
            sound.set_volume(self._volume)
            sound.play()
        except pygame.error as exc:
            logger.warning("Playback failed for '%s': %s — trying reinit", sound_name, exc)
            if self._reinit_mixer():
                sound = self._sounds.get(sound_name)
                if sound is not None:
                    try:
                        sound.set_volume(self._volume)
                        sound.play()
                    except pygame.error:
                        pass

    def play_loop(self, sound_name: str) -> None:
        """Play a sound in an infinite loop until ``stop()`` is called.

        Args:
            sound_name: Key from ``audio.sounds`` config mapping.
        """
        sound = self._sounds.get(sound_name)
        if sound is None:
            logger.warning("Unknown sound '%s'", sound_name)
            return
        try:
            sound.set_volume(self._volume)
            sound.play(loops=-1)
        except pygame.error as exc:
            logger.warning("Loop failed for '%s': %s — trying reinit", sound_name, exc)
            if self._reinit_mixer():
                sound = self._sounds.get(sound_name)
                if sound is not None:
                    try:
                        sound.set_volume(self._volume)
                        sound.play(loops=-1)
                    except pygame.error:
                        pass

    def play_file(self, file_path: str) -> None:
        """Play a specific WAV file.

        Args:
            file_path: Path to the WAV file (absolute or relative to
                project root).
        """
        resolved = Path(file_path)
        if not resolved.is_absolute():
            resolved = self._project_root / resolved
        try:
            sound = pygame.mixer.Sound(str(resolved))
            sound.set_volume(self._volume)
            sound.play()
        except (pygame.error, FileNotFoundError) as exc:
            logger.warning("play_file failed for '%s': %s", file_path, exc)

    def stop(self) -> None:
        """Stop all currently playing audio and restart the keepalive."""
        try:
            pygame.mixer.stop()
        except pygame.error:
            pass
        # Restart keepalive so the USB speaker stays awake for the next sound.
        self._start_keepalive()

    def set_volume(self, volume: float) -> None:
        """Set master volume.

        Args:
            volume: Volume level (0.0 to 1.0).
        """
        self._volume = max(0.0, min(1.0, volume))
        logger.debug("Volume set to %.1f", self._volume)

    def shutdown(self) -> None:
        """Stop all audio and quit the mixer."""
        self._keepalive_channel = None
        try:
            pygame.mixer.stop()
        except pygame.error:
            pass
        try:
            pygame.mixer.quit()
        except pygame.error:
            pass
        self._sounds.clear()
        logger.info("PygameAudio shut down")
