import contextlib
from typing import Any, Iterator, List, Optional

from esdl.sdl2 import lib, ffi


@contextlib.contextmanager
def _audio_scope() -> Iterator[None]:
    """Ensure SDL audio is initilizaed for the duration of this context."""
    assert lib.SDL_InitSubSystem(lib.SDL_INIT_AUDIO) == 0, ffi.string(
        lib.SDL_GetError()
    ).decode("utf-8")
    try:
        yield
    finally:
        lib.SDL_QuitSubSystem(lib.SDL_INIT_AUDIO)


def _get_devices(capture: bool = False) -> Optional[List[str]]:
    """Parse devices from SDL_GetNumAudioDevices.

    https://wiki.libsdl.org/SDL_GetNumAudioDevices
    """
    with _audio_scope():
        device_count = lib.SDL_GetNumAudioDevices(capture)
        if device_count < 0:
            return None  # Unknown number of devices.
        return [
            ffi.string(lib.SDL_GetAudioDeviceName(i, capture)).decode("utf-8")
            for i in range(device_count)
        ]


def get_output_devices() -> Optional[List[str]]:
    """Return the names of all available audio output devices.

    None will be returned if it can't be deterimend how many devices there
    are.  This isn't the same is there being no devices.

        >>> import esdl.audio
        >>> esdl.audio.get_output_devices() or []
        [...]
    """
    return _get_devices(capture=False)


def get_capture_devices() -> Optional[List[str]]:
    """Return the names of all available audio recording devices.

    Can return None for the same reasons as get_output_devices.

        >>> import esdl.audio
        >>> esdl.audio.get_capture_devices() or []
        [...]
    """
    return _get_devices(capture=True)


def _get_drivers() -> List[str]:
    """Return a list of the available system audio drivers.

        >>> _get_drivers()
        [...]

    https://wiki.libsdl.org/SDL_GetNumAudioDrivers
    """
    return [
        ffi.string(lib.SDL_GetAudioDriver(i)).decode("utf-8")
        for i in range(lib.SDL_GetNumAudioDrivers())
    ]
