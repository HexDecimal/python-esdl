import functools
import sys
import weakref
from typing import Any, Callable, Iterator, List, Optional

import numpy as np

import esdl.sys
from esdl.loader import ffi, lib

try:
    from numpy.typing import ArrayLike, DTypeLike
except ImportError:  # Python < 3.7, Numpy < 1.20
    from typing import Any as ArrayLike
    from typing import Any as DTypeLike

_SDL_AUDIO_MASK_BITSIZE = 0xFF
_SDL_AUDIO_MASK_DATATYPE = 1 << 8
_SDL_AUDIO_MASK_ENDIAN = 1 << 12
_SDL_AUDIO_MASK_SIGNED = 1 << 15


def _get_format(format: DTypeLike) -> int:
    """Return a SDL_AudioFormat bitfield from a NumPy dtype."""
    dt: Any = np.dtype(format)
    assert dt.fields is None
    bitsize = dt.itemsize * 8
    assert 0 < bitsize <= _SDL_AUDIO_MASK_BITSIZE
    assert dt.str[1] in "uif"
    is_signed = dt.str[1] != "u"
    is_float = dt.str[1] == "f"
    byteorder = dt.byteorder
    if byteorder == "=":
        byteorder = "<" if sys.byteorder == "little" else ">"

    return (  # type: ignore
        bitsize
        | (_SDL_AUDIO_MASK_DATATYPE * is_float)
        | (_SDL_AUDIO_MASK_ENDIAN * (byteorder == ">"))
        | (_SDL_AUDIO_MASK_SIGNED * is_signed)
    )


def _dtype_from_format(format: int) -> Any:
    """Return a dtype from a SDL_AudioFormat."""
    bitsize = format & _SDL_AUDIO_MASK_BITSIZE
    assert bitsize % 8 == 0
    bytesize = bitsize // 8
    byteorder = ">" if format & _SDL_AUDIO_MASK_ENDIAN else "<"
    if format & _SDL_AUDIO_MASK_DATATYPE:
        kind = "f"
    elif format & _SDL_AUDIO_MASK_SIGNED:
        kind = "i"
    else:
        kind = "u"
    return np.dtype(f"{byteorder}{kind}{bytesize}")


class AudioDevice:
    def __init__(
        self,
        device: Optional[str] = None,
        capture: bool = False,
        *,
        frequency: int = 44100,
        format: DTypeLike = np.float32,
        channels: int = 2,
        samples: int = 4096,
        allowed_changes: int = 0,
        callback: Optional[Callable[[np.ndarray], None]] = None,
    ):
        self.__handle = ffi.new_handle(weakref.ref(self))
        desired = ffi.new(
            "SDL_AudioSpec*",
            {
                "freq": frequency,
                "format": _get_format(format),
                "channels": channels,
                "samples": samples,
                "callback": lib._sdl_audio_callback,
                "userdata": self.__handle,
            },
        )
        obtained = ffi.new("SDL_AudioSpec*")
        self.device_id = lib.SDL_OpenAudioDevice(
            ffi.NULL if device is None else device.encode("utf-8"),
            capture,
            desired,
            obtained,
            allowed_changes,
        )
        assert self.device_id != 0, esdl.sys._get_error()
        self.frequency = obtained.freq
        self.format = _dtype_from_format(obtained.format)
        self.channels = obtained.channels
        self.silence = obtained.silence
        self.samples = obtained.samples
        self.buffer_size = obtained.size
        if callback is None:
            callback = functools.partial(self.__default_callback, silence=self.silence)
        self.callback = callback

    def pause(self) -> None:
        lib.SDL_PauseAudioDevice(self.device_id, True)

    def unpause(self) -> None:
        lib.SDL_PauseAudioDevice(self.device_id, False)

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        if not self.device_id:
            return
        lib.SDL_CloseAudioDevice(self.device_id)
        self.device_id = 0

    @staticmethod
    def __default_callback(stream: np.ndarray, silence: int) -> None:
        stream[...] = silence


class Mixer:
    def __init__(self, device: AudioDevice):
        self.device = device
        device.callback = self.on_stream
        self.device.unpause()

    def on_stream(self, stream: np.ndarray) -> None:
        stream[...] = self.device.silence


class BasicMixer(Mixer):
    def __init__(self, device: AudioDevice):
        super().__init__(device)
        self.play_buffers: List[List[np.ndarray]] = []

    def play(self, sound: ArrayLike) -> None:
        array = np.asarray(sound, dtype=self.device.format)
        assert array.size
        if len(array.shape) == 1:
            array = array[:, np.newaxis]
        chunks = np.split(array, range(0, len(array), self.device.samples)[1:])[::-1]
        self.play_buffers.append(chunks)

    def on_stream(self, stream: np.ndarray) -> None:
        super().__init__(stream)
        for chunks in self.play_buffers:
            chunk = chunks.pop()
            stream[: len(chunk)] += chunk

        self.play_buffers = [chunks for chunks in self.play_buffers if chunks]


@ffi.def_extern()  # type: ignore
def _sdl_audio_callback(userdata: Any, stream: Any, length: int) -> None:
    """Handle audio device callbacks."""
    device: Optional[AudioDevice] = ffi.from_handle(userdata)()
    assert device is not None
    array = np.frombuffer(ffi.buffer(stream, length), dtype=device.format).reshape(-1, device.channels)
    device.callback(array)


def _get_devices(capture: bool) -> Iterator[str]:
    """Get audio devices from SDL_GetAudioDeviceName."""
    device_count = lib.SDL_GetNumAudioDevices(capture)
    assert device_count >= 0, esdl.sys._get_error()
    for i in range(device_count):
        yield str(ffi.string(lib.SDL_GetAudioDeviceName(i, capture)), encoding="utf-8")


def get_devices() -> Iterator[str]:
    """Iterate over the available audio output devices."""
    yield from _get_devices(capture=False)


def get_capture_devices() -> Iterator[str]:
    """Iterate over the available audio capture devices."""
    yield from _get_devices(capture=True)
