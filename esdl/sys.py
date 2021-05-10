import enum
from typing import Tuple

from esdl.loader import ffi, lib


class Subsystem(enum.IntFlag):
    TIMER = 0x1
    AUDIO = 0x10
    VIDEO = 0x20
    JOYSTICK = 0x200
    HAPTIC = 0x1000
    GAMECONTROLLER = 0x2000
    EVENTS = 0x4000
    SENSOR = 0x8000
    EVERYTHING = TIMER | AUDIO | VIDEO | JOYSTICK | HAPTIC | GAMECONTROLLER | EVENTS | SENSOR


def _check(result: int) -> int:
    if result < 0:
        raise RuntimeError(_get_error())
    return result


def init(flags: int = Subsystem.EVERYTHING) -> None:
    _check(lib.SDL_InitSubSystem(flags))


def quit(flags: int = Subsystem.EVERYTHING) -> None:
    _check(lib.SDL_QuitSubSystem(flags))


def _get_error() -> str:
    return str(ffi.string(lib.SDL_GetError()), encoding="utf-8")


class _PowerState(enum.IntEnum):
    UNKNOWN = lib.SDL_POWERSTATE_UNKNOWN
    ON_BATTERY = lib.SDL_POWERSTATE_ON_BATTERY
    NO_BATTERY = lib.SDL_POWERSTATE_NO_BATTERY
    CHARGING = lib.SDL_POWERSTATE_CHARGING
    CHARGED = lib.SDL_POWERSTATE_CHARGED


def _get_power_info() -> Tuple[_PowerState, int, int]:
    buffer = ffi.new("int[2]")
    power_state = _PowerState(lib.SDL_GetPowerInfo(buffer, buffer + 1))
    seconds_of_power = buffer[0]
    percenage = buffer[1]
    return power_state, seconds_of_power, percenage
