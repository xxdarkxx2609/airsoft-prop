"""Mock audio implementation for desktop testing.

Attempts to play sounds via pygame.mixer when available.
Falls back to silent logging if pygame is not installed or
the sound files are missing.
"""

from pathlib import Path
from typing import Optional

from src.hal.base import AudioBase
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Try to import pygame at module level so we know early whether audio
# playback is possible.
try:
    import pygame.mixer as _mixer

    _HAS_PYGAME = True
except ImportError:
    _mixer = None  # type: ignore[assignment]
    _HAS_PYGAME = False


class MockAudio(AudioBase):
    """Mock audio that plays real sounds via pygame when possible.

    On systems where pygame-ce is installed and sound files exist in
    ``assets/sounds/``, actual WAV playback is used.  Otherwise every
    operation is silently logged.
    """

    def __init__(self) -> None:
        """Initialize mock audio state."""
        self._volume: float = 0.8
        self._playing: Optional[str] = None
        self._mixer_ready: bool = False
        self._sounds: dict[str, str] = {}
        from src.utils.paths import get_project_root
        self._project_root: Path = get_project_root()

    def init(self) -> None:
        """Initialize the audio system (pygame.mixer if available)."""
        # Build the name -> path mapping from config defaults.
        self._sounds = {
            "beep": "assets/sounds/beep.wav",
            "planted": "assets/sounds/planted.wav",
            "explosion": "assets/sounds/explosion.wav",
            "siren": "assets/sounds/siren.wav",
            "defused": "assets/sounds/defused.wav",
            "wrong": "assets/sounds/wrong.wav",
        }

        if not _HAS_PYGAME:
            logger.info("MockAudio: pygame not available — silent mode")
            return

        try:
            _mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            _mixer.set_num_channels(4)
            self._mixer_ready = True
            logger.info("MockAudio: pygame.mixer initialized — sound enabled")
        except Exception as exc:
            logger.warning("MockAudio: pygame.mixer init failed (%s) — silent mode", exc)

    def _resolve_sound_path(self, sound_name: str) -> Optional[Path]:
        """Resolve the filesystem path for a sound, checking custom/ first."""
        path_str = self._sounds.get(sound_name)
        if path_str is None:
            logger.warning("MockAudio: unknown sound '%s'", sound_name)
            return None
        filename = Path(path_str).name
        custom_path = self._project_root / "custom" / "sounds" / filename
        if custom_path.exists():
            return custom_path
        return self._project_root / path_str

    def play(self, sound_name: str) -> None:
        """Play a sound by name.

        Looks up the WAV path for *sound_name* and plays it through
        pygame.mixer. Custom sounds in custom/sounds/ take priority.

        Args:
            sound_name: Key from the sounds mapping (e.g. 'beep').
        """
        self._playing = sound_name
        full_path = self._resolve_sound_path(sound_name)
        if full_path is None:
            return

        if self._mixer_ready and full_path.exists():
            try:
                sound = _mixer.Sound(str(full_path))
                sound.set_volume(self._volume)
                sound.play()
                logger.debug("MockAudio PLAY: '%s'", sound_name)
            except Exception as exc:
                logger.warning("MockAudio: playback failed for '%s' (%s)", sound_name, exc)
        else:
            if not full_path.exists():
                logger.debug("MockAudio PLAY (no file): '%s'", sound_name)
            else:
                logger.debug("MockAudio PLAY (no mixer): '%s'", sound_name)

    def play_loop(self, sound_name: str) -> None:
        """Play a sound in an infinite loop until stop() is called.

        Args:
            sound_name: Key from the sounds mapping (e.g. 'siren').
        """
        self._playing = sound_name
        full_path = self._resolve_sound_path(sound_name)
        if full_path is None:
            return

        if self._mixer_ready and full_path.exists():
            try:
                sound = _mixer.Sound(str(full_path))
                sound.set_volume(self._volume)
                sound.play(loops=-1)  # -1 = loop forever
                logger.debug("MockAudio LOOP: '%s'", sound_name)
            except Exception as exc:
                logger.warning("MockAudio: loop failed for '%s' (%s)", sound_name, exc)
        else:
            logger.debug("MockAudio LOOP (silent): '%s'", sound_name)

    def play_file(self, file_path: str) -> None:
        """Play a specific WAV file.

        Args:
            file_path: Path to the WAV file.
        """
        self._playing = file_path
        resolved = Path(file_path)

        if self._mixer_ready and resolved.exists():
            try:
                sound = _mixer.Sound(str(resolved))
                sound.set_volume(self._volume)
                sound.play()
                logger.debug("MockAudio PLAY FILE: '%s'", file_path)
            except Exception as exc:
                logger.warning("MockAudio: playback failed for '%s' (%s)", file_path, exc)
        else:
            logger.debug("MockAudio PLAY FILE (silent): '%s'", file_path)

    def stop(self) -> None:
        """Stop all currently playing audio."""
        if self._mixer_ready:
            _mixer.stop()
        logger.debug("MockAudio STOP")
        self._playing = None

    def set_volume(self, volume: float) -> None:
        """Set master volume.

        Args:
            volume: Volume level (0.0 to 1.0).
        """
        self._volume = max(0.0, min(1.0, volume))
        logger.debug("MockAudio volume: %.1f", self._volume)

    def shutdown(self) -> None:
        """Clean up the audio system."""
        self.stop()
        if self._mixer_ready:
            _mixer.quit()
            self._mixer_ready = False
        logger.info("MockAudio shut down")
