#!/usr/bin/env python3

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

from enum import IntEnum


# ============================================================
# Logging
# ============================================================


class LogLevel(IntEnum):
    ERROR = 0
    WARNING = 1
    INFO = 2
    DEBUG = 3
    TRACE = 4


LOG_LEVEL = LogLevel.INFO


def log(level, message):
    if level <= LOG_LEVEL:
        print(
            "[{:<7}] {}".format(
                level.name,
                message,
            ),
            file=sys.stderr,
        )


def log_error(message):
    log(LogLevel.ERROR, message)


def log_warning(message):
    log(LogLevel.WARNING, message)


def log_info(message):
    log(LogLevel.INFO, message)


def log_debug(message):
    log(LogLevel.DEBUG, message)


def log_trace(message):
    log(LogLevel.TRACE, message)


# ============================================================
# Data
# ============================================================


class Output(object):
    def __init__(
        self,
        name,
        width,
        height,
        source,
    ):
        self.name = name
        self.width = width
        self.height = height
        self.source = source

    def __repr__(self):
        return (
            "Output(" "name={!r}, " "width={!r}, " "height={!r}, " "source={!r}" ")"
        ).format(
            self.name,
            self.width,
            self.height,
            self.source,
        )


RESOLUTION_ALIASES = {
    "1k": (1920, 1080),
    "2k": (2560, 1440),
    "4k": (3840, 2160),
    "8k": (7680, 4320),
    "16k": (15360, 8640),
}


# ============================================================
# Command helpers
# ============================================================


def format_command(command):
    """
    Python 3.6 compatible replacement for shlex.join().
    """
    return " ".join(shlex.quote(str(part)) for part in command)


def run_command(
    command,
    warn_on_failure=True,
    timeout=5,
):
    log_debug("Running probe command: {}".format(format_command(command)))

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
            timeout=timeout,
        )

    except FileNotFoundError:
        log_debug("Command not found: {}".format(command[0]))
        return None

    except subprocess.TimeoutExpired as error:
        message = ("Command timed out after {}s: {}").format(
            timeout,
            format_command(command),
        )

        if warn_on_failure:
            log_warning(message)
        else:
            log_debug(message)

        if error.stdout:
            log_trace("Command stdout:\n{}".format(error.stdout.rstrip()))

        if error.stderr:
            log_trace("Command stderr:\n{}".format(error.stderr.rstrip()))

        return None

    except subprocess.CalledProcessError as error:
        message = ("Command failed with exit code {}: {}").format(
            error.returncode,
            format_command(command),
        )

        if warn_on_failure:
            log_warning(message)
        else:
            log_debug(message)

        if error.stdout:
            log_trace("Command stdout:\n{}".format(error.stdout.rstrip()))

        if error.stderr:
            log_trace("Command stderr:\n{}".format(error.stderr.rstrip()))

        return None

    if result.stdout:
        log_trace("Command stdout:\n{}".format(result.stdout.rstrip()))

    if result.stderr:
        log_trace("Command stderr:\n{}".format(result.stderr.rstrip()))

    return result.stdout


# ============================================================
# Desktop / session detection
# ============================================================


def get_session_type():
    session_type = (
        os.environ.get(
            "XDG_SESSION_TYPE",
            "",
        )
        .strip()
        .lower()
    )

    if session_type in (
        "x11",
        "wayland",
    ):
        return session_type

    # Wayland sessions commonly also export DISPLAY for
    # XWayland, so WAYLAND_DISPLAY must be checked first.
    if os.environ.get("WAYLAND_DISPLAY"):
        log_debug("XDG_SESSION_TYPE is unset; " "detected Wayland from WAYLAND_DISPLAY")
        return "wayland"

    if os.environ.get("DISPLAY"):
        log_debug("XDG_SESSION_TYPE is unset; " "detected X11 from DISPLAY")
        return "x11"

    log_debug("Unable to determine session type")

    return "unknown"


def is_gnome():
    desktop = os.environ.get(
        "XDG_CURRENT_DESKTOP",
        "",
    ).upper()

    session = os.environ.get(
        "XDG_SESSION_DESKTOP",
        "",
    ).upper()

    return "GNOME" in desktop or "GNOME" in session


def is_kde():
    desktop = os.environ.get(
        "XDG_CURRENT_DESKTOP",
        "",
    ).upper()

    session = os.environ.get(
        "XDG_SESSION_DESKTOP",
        "",
    ).upper()

    return (
        "KDE" in desktop
        or "PLASMA" in desktop
        or "KDE" in session
        or "PLASMA" in session
    )


# ============================================================
# GNOME / Mutter
# ============================================================


def variant_value(value):
    if hasattr(value, "unpack"):
        return value.unpack()

    return value


def get_outputs_gnome():
    running_gnome = is_gnome()

    log_debug("Trying GNOME Mutter DisplayConfig")

    try:
        import gi

        gi.require_version(
            "Gio",
            "2.0",
        )

        from gi.repository import Gio, GLib

    except (ImportError, ValueError) as error:
        if running_gnome:
            log_warning("PyGObject/Gio is unavailable")
        else:
            log_debug("PyGObject/Gio is unavailable")

        log_trace("Gio import error: {!r}".format(error))

        return []

    try:
        bus = Gio.bus_get_sync(
            Gio.BusType.SESSION,
            None,
        )

        result = bus.call_sync(
            "org.gnome.Mutter.DisplayConfig",
            "/org/gnome/Mutter/DisplayConfig",
            "org.gnome.Mutter.DisplayConfig",
            "GetCurrentState",
            None,
            None,
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )

    except GLib.Error as error:
        if running_gnome:
            log_warning("Failed to query GNOME " "Mutter DisplayConfig")
        else:
            log_debug("GNOME Mutter DisplayConfig " "is unavailable")

        log_trace("Mutter D-Bus error: {!r}".format(error))

        return []

    try:
        state = result.unpack()

        serial = state[0]
        monitors = state[1]

        log_info("Querying displays using " "GNOME Mutter DisplayConfig")

        log_trace("Mutter configuration serial: {}".format(serial))

        log_trace("Mutter raw monitor data: {!r}".format(monitors))

        outputs = []

        for monitor in monitors:
            monitor_spec = monitor[0]
            modes = monitor[1]

            connector = monitor_spec[0]

            vendor = monitor_spec[1] if len(monitor_spec) > 1 else ""

            product = monitor_spec[2] if len(monitor_spec) > 2 else ""

            log_debug(
                "Mutter monitor: {} "
                "vendor={!r} "
                "product={!r}".format(
                    connector,
                    vendor,
                    product,
                )
            )

            current_mode = None

            for mode in modes:
                if len(mode) < 7:
                    continue

                mode_id = mode[0]
                width = int(mode[1])
                height = int(mode[2])
                refresh = float(mode[3])
                properties = mode[6]

                is_current = False

                if isinstance(
                    properties,
                    dict,
                ):
                    value = properties.get(
                        "is-current",
                        False,
                    )

                    is_current = bool(variant_value(value))

                log_trace(
                    "Mutter mode {}: "
                    "id={!r} "
                    "{}x{}@{:.3f} "
                    "current={}".format(
                        connector,
                        mode_id,
                        width,
                        height,
                        refresh,
                        is_current,
                    )
                )

                if is_current:
                    current_mode = (
                        width,
                        height,
                        refresh,
                    )
                    break

            if current_mode is None:
                log_debug("Skipping inactive GNOME " "display: {}".format(connector))
                continue

            width = current_mode[0]
            height = current_mode[1]
            refresh = current_mode[2]

            output = Output(
                name=connector,
                width=width,
                height=height,
                source="gnome-mutter",
            )

            outputs.append(output)

            log_debug(
                "Detected display: {} "
                "{}x{}@{:.3f}".format(
                    connector,
                    width,
                    height,
                    refresh,
                )
            )

        if not outputs:
            message = "GNOME Mutter returned " "no active displays"

            if running_gnome:
                log_warning(message)
            else:
                log_debug(message)

        return outputs

    except (
        IndexError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        if running_gnome:
            log_warning("Could not parse GNOME " "Mutter response")
        else:
            log_debug("Could not parse GNOME " "Mutter response")

        log_trace("Mutter parse error: {!r}".format(error))

        return []


# ============================================================
# KDE / KScreen JSON
# ============================================================


def get_outputs_kscreen_json():
    log_debug("Trying kscreen-doctor JSON output")

    text = run_command(
        [
            "kscreen-doctor",
            "-j",
        ],
        warn_on_failure=False,
    )

    if text is None:
        return None

    if not text.strip():
        log_debug("kscreen-doctor returned " "empty JSON output")
        return None

    try:
        data = json.loads(text)

    except (
        TypeError,
        ValueError,
    ) as error:
        log_debug("Could not parse " "kscreen-doctor JSON")

        log_trace("kscreen-doctor JSON parse " "error: {!r}".format(error))

        return None

    if not isinstance(
        data,
        dict,
    ):
        log_debug("kscreen-doctor JSON root " "is not an object")

        log_trace("kscreen-doctor JSON root: {!r}".format(data))

        return None

    raw_outputs = data.get(
        "outputs",
        [],
    )

    if not isinstance(
        raw_outputs,
        list,
    ):
        log_debug("kscreen-doctor JSON does not " "contain a valid outputs list")
        return None

    outputs = []

    for raw_output in raw_outputs:
        if not isinstance(
            raw_output,
            dict,
        ):
            continue

        name = raw_output.get("name")

        if not name:
            log_debug("Skipping KScreen output " "without a name")
            continue

        connected = raw_output.get(
            "connected",
            True,
        )

        enabled = raw_output.get(
            "enabled",
            False,
        )

        if not connected:
            log_debug("Skipping disconnected KDE " "display: {}".format(name))
            continue

        if not enabled:
            log_debug("Skipping disabled KDE " "display: {}".format(name))
            continue

        current_mode_id = raw_output.get("currentModeId")

        if current_mode_id is None:
            log_debug("KDE display {} has no " "currentModeId".format(name))
            continue

        modes = raw_output.get(
            "modes",
            [],
        )

        if not isinstance(
            modes,
            list,
        ):
            log_debug("KDE display {} has an " "invalid modes list".format(name))
            continue

        current_mode = None

        for mode in modes:
            if not isinstance(
                mode,
                dict,
            ):
                continue

            if str(mode.get("id")) == str(current_mode_id):
                current_mode = mode
                break

        if current_mode is None:
            log_debug(
                "Could not find current mode "
                "{} for KDE display {}".format(
                    current_mode_id,
                    name,
                )
            )
            continue

        size = current_mode.get(
            "size",
            {},
        )

        if not isinstance(
            size,
            dict,
        ):
            log_debug("Invalid current mode size " "for KDE display {}".format(name))
            continue

        try:
            width = int(size["width"])

            height = int(size["height"])

        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            log_debug(
                "Invalid current mode dimensions " "for KDE display {}".format(name)
            )
            continue

        if width <= 0 or height <= 0:
            log_debug(
                "Invalid resolution {}x{} "
                "for KDE display {}".format(
                    width,
                    height,
                    name,
                )
            )
            continue

        output = Output(
            name=name,
            width=width,
            height=height,
            source="kscreen-doctor-json",
        )

        outputs.append(output)

        refresh = current_mode.get("refreshRate")

        if refresh is not None:
            try:
                log_debug(
                    "Detected display: {} "
                    "{}x{}@{:.3f}".format(
                        name,
                        width,
                        height,
                        float(refresh),
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                log_debug(
                    "Detected display: "
                    "{} {}x{}".format(
                        name,
                        width,
                        height,
                    )
                )

        else:
            log_debug(
                "Detected display: "
                "{} {}x{}".format(
                    name,
                    width,
                    height,
                )
            )

    if not outputs:
        log_debug("kscreen-doctor JSON returned " "no active usable displays")

    return outputs


# ============================================================
# KDE / KScreen text fallback
# ============================================================


def get_outputs_kscreen_text():
    log_debug("Trying kscreen-doctor text output")

    text = run_command(
        [
            "kscreen-doctor",
            "-o",
        ],
        warn_on_failure=False,
    )

    if text is None:
        return []

    if not text.strip():
        log_debug("kscreen-doctor returned " "empty text output")
        return []

    outputs = []

    sections = re.split(
        r"(?=^Output:\s*\d+)",
        text,
        flags=re.MULTILINE,
    )

    for section in sections:
        header = re.search(
            r"^Output:\s*\d+\s+(\S+)",
            section,
            flags=re.MULTILINE,
        )

        if not header:
            continue

        name = header.group(1)

        section_lines = section.splitlines()

        first_line = section_lines[0] if section_lines else ""

        if re.search(
            r"\bdisabled\b",
            first_line,
            flags=re.IGNORECASE,
        ):
            log_debug("Skipping disabled KDE " "display: {}".format(name))
            continue

        enabled = bool(
            re.search(
                r"\benabled\b",
                first_line,
                flags=re.IGNORECASE,
            )
        )

        if not enabled:
            enabled = bool(
                re.search(
                    r"^\s*enabled\s*$",
                    section,
                    flags=(re.MULTILINE | re.IGNORECASE),
                )
            )

        if not enabled:
            log_debug(
                "Skipping KDE display with " "unknown/inactive state: {}".format(name)
            )
            continue

        # Current physical mode is marked by '*'.
        #
        # Do not use Geometry here. With fractional scaling,
        # Geometry can represent logical dimensions instead
        # of the physical display mode.
        match = re.search(
            r"\d+:(\d+)x(\d+)@[^\s]*\*",
            section,
        )

        if not match:
            log_debug(
                "Could not determine current "
                "physical mode for KDE display: {}".format(name)
            )
            continue

        width = int(match.group(1))

        height = int(match.group(2))

        if width <= 0 or height <= 0:
            log_debug(
                "Invalid physical mode {}x{} "
                "for KDE display {}".format(
                    width,
                    height,
                    name,
                )
            )
            continue

        output = Output(
            name=name,
            width=width,
            height=height,
            source="kscreen-doctor-text",
        )

        outputs.append(output)

        log_debug(
            "Detected display: "
            "{} {}x{}".format(
                output.name,
                output.width,
                output.height,
            )
        )

    if not outputs:
        log_debug("kscreen-doctor text output " "returned no active usable displays")

    return outputs


def get_outputs_kscreen():
    running_kde = is_kde()

    if not shutil.which("kscreen-doctor"):
        if running_kde:
            log_warning("kscreen-doctor is unavailable")
        else:
            log_debug("kscreen-doctor is unavailable")

        return []

    outputs = get_outputs_kscreen_json()

    if outputs:
        log_info("Querying displays using " "kscreen-doctor JSON")

        return outputs

    log_debug("Falling back to " "kscreen-doctor text output")

    outputs = get_outputs_kscreen_text()

    if outputs:
        log_info("Querying displays using " "kscreen-doctor text output")

        return outputs

    if running_kde:
        log_warning("Could not detect displays " "using kscreen-doctor")
    else:
        log_debug("Could not detect displays " "using kscreen-doctor")

    return []


# ============================================================
# wlroots
# ============================================================


def get_outputs_wlr_randr():
    if not shutil.which("wlr-randr"):
        log_debug("wlr-randr is unavailable")
        return []

    log_debug("Trying wlr-randr")

    text = run_command(
        [
            "wlr-randr",
        ],
        warn_on_failure=False,
    )

    if text is None:
        return []

    if not text.strip():
        log_debug("wlr-randr returned empty output")
        return []

    outputs = []
    current_name = None

    for line in text.splitlines():
        if line and not line[0].isspace():
            current_name = line.split()[0]
            continue

        if current_name is None:
            continue

        match = re.search(
            r"(\d+)x(\d+).*current",
            line,
            flags=re.IGNORECASE,
        )

        if match:
            output = Output(
                name=current_name,
                width=int(match.group(1)),
                height=int(match.group(2)),
                source="wlr-randr",
            )

            outputs.append(output)

            log_debug(
                "Detected display: "
                "{} {}x{}".format(
                    output.name,
                    output.width,
                    output.height,
                )
            )

            current_name = None

    if not outputs:
        log_debug("wlr-randr returned no " "active usable displays")

    return outputs


# ============================================================
# XRandR
# ============================================================


def get_outputs_xrandr():
    running_x11 = get_session_type() == "x11"

    if not shutil.which("xrandr"):
        log_debug("xrandr is unavailable")
        return []

    log_debug("Trying xrandr")

    text = run_command(
        [
            "xrandr",
            "--query",
        ],
        warn_on_failure=running_x11,
    )

    if text is None:
        return []

    if not text.strip():
        message = "xrandr returned empty output"

        if running_x11:
            log_warning(message)
        else:
            log_debug(message)

        return []

    outputs = []

    pattern = re.compile(
        r"^(\S+)\s+connected" r"(?:\s+primary)?" r"\s+(\d+)x(\d+)" r"[+-]\d+[+-]\d+",
        flags=re.MULTILINE,
    )

    for match in pattern.finditer(text):
        output = Output(
            name=match.group(1),
            width=int(match.group(2)),
            height=int(match.group(3)),
            source="xrandr",
        )

        outputs.append(output)

        log_debug(
            "Detected display: "
            "{} {}x{}".format(
                output.name,
                output.width,
                output.height,
            )
        )

    if not outputs:
        message = "xrandr returned no active " "usable displays"

        if running_x11:
            log_warning(message)
        else:
            log_debug(message)

    return outputs


# ============================================================
# Display detection
# ============================================================


def get_outputs():
    desktop = os.environ.get(
        "XDG_CURRENT_DESKTOP",
        "",
    )

    session_desktop = os.environ.get(
        "XDG_SESSION_DESKTOP",
        "",
    )

    session_type = get_session_type()

    log_debug("Desktop environment: {}".format(desktop or "unknown"))

    log_debug("Session desktop: {}".format(session_desktop or "unknown"))

    log_debug("Session type: {}".format(session_type))

    if is_gnome():
        if session_type == "x11":
            detectors = (
                (
                    "gnome-mutter",
                    get_outputs_gnome,
                ),
                (
                    "xrandr",
                    get_outputs_xrandr,
                ),
            )
        else:
            detectors = (
                (
                    "gnome-mutter",
                    get_outputs_gnome,
                ),
            )

    elif is_kde():
        if session_type == "x11":
            detectors = (
                (
                    "kscreen-doctor",
                    get_outputs_kscreen,
                ),
                (
                    "xrandr",
                    get_outputs_xrandr,
                ),
            )
        else:
            detectors = (
                (
                    "kscreen-doctor",
                    get_outputs_kscreen,
                ),
            )

    elif session_type == "x11":
        detectors = (
            (
                "xrandr",
                get_outputs_xrandr,
            ),
            (
                "kscreen-doctor",
                get_outputs_kscreen,
            ),
            (
                "gnome-mutter",
                get_outputs_gnome,
            ),
        )

    else:
        detectors = (
            (
                "wlr-randr",
                get_outputs_wlr_randr,
            ),
            (
                "kscreen-doctor",
                get_outputs_kscreen,
            ),
            (
                "gnome-mutter",
                get_outputs_gnome,
            ),
        )

    for name, detector in detectors:
        log_debug("Trying display detector: {}".format(name))

        outputs = detector()

        if outputs:
            log_info(
                "Detected {} display(s) "
                "using {}".format(
                    len(outputs),
                    name,
                )
            )

            return outputs

    log_warning("No displays could be detected")

    return []


def print_outputs(outputs):
    if not outputs:
        return

    log_info("Detected displays:")

    for index, output in enumerate(outputs):
        log_info(
            "  {}: {:<14} "
            "{}x{} [{}]".format(
                index,
                output.name,
                output.width,
                output.height,
                output.source,
            )
        )


# ============================================================
# Argument parsers
# ============================================================


def parse_window_mode(value):
    aliases = {
        "f": "fullscreen",
        "fullscreen": "fullscreen",
        "b": "borderless",
        "borderless": "borderless",
        "w": "windowed",
        "windowed": "windowed",
    }

    mode = value.strip().lower()

    if mode not in aliases:
        raise argparse.ArgumentTypeError(
            "invalid window mode: {} "
            "(expected fullscreen/f, "
            "borderless/b, or windowed/w)".format(value)
        )

    return aliases[mode]


# ============================================================
# Resolution helpers
# ============================================================


def resolution_needs_display_lookup(value):
    value_lower = value.lower()

    if value_lower in RESOLUTION_ALIASES:
        return False

    if re.fullmatch(
        r"(\d+)x(\d+)",
        value,
        flags=re.IGNORECASE,
    ):
        return False

    return True


# ============================================================
# Resolution parsing
# ============================================================


def parse_resolution(
    value,
    outputs,
):
    log_debug("Parsing resolution argument: {}".format(value))

    value_lower = value.lower()

    if value_lower in RESOLUTION_ALIASES:
        width, height = RESOLUTION_ALIASES[value_lower]

        log_info(
            "Resolution alias '{}' "
            "resolved to {}x{}".format(
                value,
                width,
                height,
            )
        )

        return (
            width,
            height,
            None,
        )

    match = re.fullmatch(
        r"(\d+)x(\d+)",
        value,
        flags=re.IGNORECASE,
    )

    if match:
        width = int(match.group(1))

        height = int(match.group(2))

        if width <= 0 or height <= 0:
            raise ValueError("invalid resolution: {}".format(value))

        log_info(
            "Using explicit resolution: "
            "{}x{}".format(
                width,
                height,
            )
        )

        return (
            width,
            height,
            None,
        )

    if value.isdigit():
        index = int(value)

        if index >= len(outputs):
            raise ValueError("display index {} " "does not exist".format(index))

        output = outputs[index]

        log_info(
            "Display index {} matched "
            "{}".format(
                index,
                output.name,
            )
        )

        log_info(
            "Using display resolution: "
            "{}x{}".format(
                output.width,
                output.height,
            )
        )

        return (
            output.width,
            output.height,
            output,
        )

    for output in outputs:
        if output.name == value:
            log_info("Matched display: {}".format(output.name))

            log_info(
                "Using display resolution: "
                "{}x{}".format(
                    output.width,
                    output.height,
                )
            )

            return (
                output.width,
                output.height,
                output,
            )

    matches = [output for output in outputs if output.name.lower() == value_lower]

    if len(matches) == 1:
        output = matches[0]

        log_info("Matched display: {}".format(output.name))

        log_info(
            "Using display resolution: "
            "{}x{}".format(
                output.width,
                output.height,
            )
        )

        return (
            output.width,
            output.height,
            output,
        )

    raise ValueError("invalid resolution or display: {}".format(value))


# ============================================================
# Main
# ============================================================


def main():
    global LOG_LEVEL

    parser = argparse.ArgumentParser(
        description=("Simplified Gamescope launcher"),
        formatter_class=(argparse.RawDescriptionHelpFormatter),
        epilog="""
Examples:

  Default fullscreen mode:

    %(prog)s -r 4K -- ./game

  Fullscreen:

    %(prog)s -w f -r 4K -- ./game
    %(prog)s --window fullscreen -r 4K -- ./game

  Borderless:

    %(prog)s -w b -r 4K -- ./game

  Windowed:

    %(prog)s -w w -r 4K -- ./game

  Resolution aliases:

    %(prog)s -r 1k -- ./game
    %(prog)s -r 2K -- ./game
    %(prog)s -r 4k -- ./game
    %(prog)s -r 8K -- ./game
    %(prog)s -r 16k -- ./game

  Explicit resolution:

    %(prog)s -r 3440x1440 -- ./game
    %(prog)s -r 3840X2160 -- ./game

  Display connector:

    %(prog)s -r DP-1 -- ./game
    %(prog)s -r dp-1 -- ./game

  Detected display index:

    %(prog)s -r 0 -- ./game

  Gamescope display-index fallback:

    %(prog)s -r DP-1 -d 1 -- ./game

  Debug logging:

    %(prog)s -l DEBUG -r DP-1 -- ./game

  Full trace:

    %(prog)s -l TRACE -r DP-1 -- ./game


Window modes:

  f / fullscreen   Gamescope -f
  b / borderless   Gamescope -b
  w / windowed     no -f or -b

  Default: fullscreen


Resolution aliases:

  1k   = 1920x1080
  2k   = 2560x1440
  4k   = 3840x2160
  8k   = 7680x4320
  16k  = 15360x8640


Notes:

  Resolution aliases, WIDTHxHEIGHT, display names,
  and window mode values are case-insensitive.

  When -r matches a detected physical display,
  its current physical resolution is used and
  Gamescope receives:

      -O <connector>

  -d/--display-index is passed directly to
  Gamescope as:

      --display-index N

  -r N uses this launcher's detected-display index.

  -d N uses Gamescope's own display-index.

  These index spaces are not assumed to be identical.
""",
    )

    parser.add_argument(
        "-r",
        "--resolution",
        required=True,
        metavar="RESOLUTION",
        help=(
            "1k, 2k, 4k, 8k, 16k, " "WIDTHxHEIGHT, or detected " "display index/name"
        ),
    )

    parser.add_argument(
        "-w",
        "--window",
        type=parse_window_mode,
        default="fullscreen",
        metavar="MODE",
        help=(
            "window mode: fullscreen/f, "
            "borderless/b, or windowed/w "
            "(default: fullscreen)"
        ),
    )

    parser.add_argument(
        "-d",
        "--display-index",
        type=int,
        metavar="INDEX",
        help=("pass --display-index INDEX " "directly to Gamescope"),
    )

    parser.add_argument(
        "-l",
        "--log-level",
        default="INFO",
        type=str.upper,
        choices=[
            "ERROR",
            "WARNING",
            "INFO",
            "DEBUG",
            "TRACE",
        ],
        metavar="LEVEL",
        help=(
            "logging level: ERROR, WARNING, " "INFO, DEBUG or TRACE " "(default: INFO)"
        ),
    )

    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help=("game command and arguments"),
    )

    args = parser.parse_args()

    LOG_LEVEL = LogLevel[args.log_level]

    log_debug("Log level: {}".format(LOG_LEVEL.name))

    if args.display_index is not None and args.display_index < 0:
        parser.error("--display-index must be >= 0")

    command = args.command

    if command and command[0] == "--":
        command = command[1:]

    if not command:
        parser.error("missing game command")

    log_debug("Game command: {}".format(format_command(command)))

    # --------------------------------------------------------
    # Display detection
    # --------------------------------------------------------

    if resolution_needs_display_lookup(args.resolution):
        outputs = get_outputs()

        if outputs:
            log_debug("Available displays:")

            for index, output in enumerate(outputs):
                log_debug(
                    "  [{}] {} "
                    "{}x{} via {}".format(
                        index,
                        output.name,
                        output.width,
                        output.height,
                        output.source,
                    )
                )

    else:
        outputs = []

        log_debug(
            "Display detection not required "
            "for resolution {}".format(args.resolution)
        )

    # --------------------------------------------------------
    # Resolution
    # --------------------------------------------------------

    try:
        (
            width,
            height,
            output,
        ) = parse_resolution(
            args.resolution,
            outputs,
        )

    except ValueError as error:
        log_error(str(error))

        print_outputs(outputs)

        return 2

    # --------------------------------------------------------
    # Gamescope command
    # --------------------------------------------------------

    gamescope_command = [
        "gamescope",
        "-w",
        str(width),
        "-h",
        str(height),
        "-W",
        str(width),
        "-H",
        str(height),
    ]

    if args.window == "fullscreen":
        gamescope_command.append("-f")

    elif args.window == "borderless":
        gamescope_command.append("-b")

    log_info("Gamescope window mode: {}".format(args.window))

    if output is not None:
        gamescope_command.extend(
            [
                "-O",
                output.name,
            ]
        )

        log_info("Gamescope preferred output: {}".format(output.name))

    if args.display_index is not None:
        gamescope_command.extend(
            [
                "--display-index",
                str(args.display_index),
            ]
        )

        log_info("Gamescope display index: {}".format(args.display_index))

    gamescope_command.extend(["--"] + command)

    # --------------------------------------------------------
    # Launch logging
    # --------------------------------------------------------

    log_info(
        "Gamescope resolution: "
        "{}x{}".format(
            width,
            height,
        )
    )

    if output is not None:
        log_info("Matched monitor: {}".format(output.name))

        log_info("Monitor detector: {}".format(output.source))

    log_info("Launching Gamescope")

    log_debug("Gamescope command: {}".format(format_command(gamescope_command)))

    log_trace("Gamescope argv: {!r}".format(gamescope_command))

    # --------------------------------------------------------
    # Replace this Python process with Gamescope
    # --------------------------------------------------------

    try:
        os.execvp(
            gamescope_command[0],
            gamescope_command,
        )

    except FileNotFoundError:
        log_error("gamescope executable not found")
        return 127

    except OSError as error:
        log_error("failed to execute gamescope: {}".format(error))
        return 126


if __name__ == "__main__":
    sys.exit(main())
