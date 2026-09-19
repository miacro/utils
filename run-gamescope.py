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
            "[{}] {}".format(
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
        x=None,
        y=None,
        tags=None,
    ):
        self.name = name
        self.width = width
        self.height = height
        self.source = source
        self.x = x
        self.y = y
        self.tags = list(tags or [])

    def __repr__(self):
        return (
            "Output("
            "name={!r}, "
            "width={!r}, "
            "height={!r}, "
            "source={!r}, "
            "x={!r}, "
            "y={!r}, "
            "tags={!r}"
            ")"
        ).format(
            self.name,
            self.width,
            self.height,
            self.source,
            self.x,
            self.y,
            self.tags,
        )


RESOLUTION_ALIASES = {
    "1k": (1920, 1080),
    "2k": (2560, 1440),
    "4k": (3840, 2160),
    "8k": (7680, 4320),
    "16k": (15360, 8640),
}

WINDOW_MODE_ALIASES = {
    "f": "fullscreen",
    "fullscreen": "fullscreen",
    "b": "borderless",
    "borderless": "borderless",
    "w": "windowed",
    "windowed": "windowed",
}

HORIZONTAL_SELECTORS = frozenset(("left", "right", "center-column"))
VERTICAL_SELECTORS = frozenset(("top", "bottom", "center-row"))
SIZE_SELECTORS = frozenset(("largest", "smallest"))
DISPLAY_SELECTORS = frozenset(("center",)).union(
    HORIZONTAL_SELECTORS,
    VERTICAL_SELECTORS,
    SIZE_SELECTORS,
)

SCREEN_FILE_PATTERN = re.compile(
    r"^(\S+)\s+(\d+)x(\d+)([+-]\d+)([+-]\d+)$",
    flags=re.IGNORECASE,
)
RESOLUTION_PATTERN = re.compile(r"^(\d+)x(\d+)$", flags=re.IGNORECASE)


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
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.TimeoutExpired):
            message = "Command timed out after {}s: {}".format(
                timeout, format_command(command)
            )
        else:
            message = "Command failed with exit code {}: {}".format(
                error.returncode, format_command(command)
            )

        failure_log = log_warning if warn_on_failure else log_debug
        failure_log(message)
        for name in ("stdout", "stderr"):
            content = getattr(error, name, None)
            if content:
                log_trace("Command {}:\n{}".format(name, content.rstrip()))
        return None

    for name in ("stdout", "stderr"):
        content = getattr(result, name)
        if content:
            log_trace("Command {}:\n{}".format(name, content.rstrip()))

    return result.stdout


# ============================================================
# Desktop / session detection
# ============================================================


def get_session_type():
    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()

    if session_type in ("x11", "wayland"):
        return session_type

    # Wayland sessions commonly also export DISPLAY for
    # XWayland, so WAYLAND_DISPLAY must be checked first.
    if os.environ.get("WAYLAND_DISPLAY"):
        log_debug(
            "XDG_SESSION_TYPE is unset; detected Wayland from WAYLAND_DISPLAY"
        )
        return "wayland"

    if os.environ.get("DISPLAY"):
        log_debug("XDG_SESSION_TYPE is unset; detected X11 from DISPLAY")
        return "x11"

    log_debug("Unable to determine session type")

    return "unknown"


def desktop_name():
    return "{}:{}".format(
        os.environ.get("XDG_CURRENT_DESKTOP", ""),
        os.environ.get("XDG_SESSION_DESKTOP", ""),
    ).upper()


def is_gnome():
    return "GNOME" in desktop_name()


def is_kde():
    desktop = desktop_name()
    return "KDE" in desktop or "PLASMA" in desktop


# ============================================================
# GNOME / Mutter
# ============================================================


def variant_value(value):
    if hasattr(value, "unpack"):
        return value.unpack()

    return value


def parse_outputs_gnome(state):
    serial, monitors = state[:2]
    logical_monitors = state[2] if len(state) > 2 else []
    log_trace("Mutter configuration serial: {}".format(serial))
    log_trace("Mutter raw monitor data: {!r}".format(monitors))

    positions = {}
    for logical_monitor in logical_monitors:
        if len(logical_monitor) >= 6:
            position = int(logical_monitor[0]), int(logical_monitor[1])
            for monitor_spec in logical_monitor[5]:
                if monitor_spec:
                    positions[monitor_spec[0]] = position

    outputs = []
    for monitor_spec, modes in (monitor[:2] for monitor in monitors):
        connector = monitor_spec[0]
        vendor = monitor_spec[1] if len(monitor_spec) > 1 else ""
        product = monitor_spec[2] if len(monitor_spec) > 2 else ""
        log_debug(
            "Mutter monitor: {} vendor={!r} product={!r}".format(
                connector, vendor, product
            )
        )

        current_mode = None
        for mode in modes:
            if len(mode) < 7:
                continue
            mode_id, width, height, refresh = mode[:4]
            width, height, refresh = int(width), int(height), float(refresh)
            properties = mode[6]
            is_current = isinstance(properties, dict) and bool(
                variant_value(properties.get("is-current", False))
            )
            log_trace(
                "Mutter mode {}: id={!r} {}x{}@{:.3f} current={}".format(
                    connector, mode_id, width, height, refresh, is_current
                )
            )
            if is_current:
                current_mode = width, height, refresh
                break

        if current_mode is None:
            log_debug("Skipping inactive GNOME display: {}".format(connector))
            continue

        width, height, refresh = current_mode
        x, y = positions.get(connector, (None, None))
        outputs.append(
            Output(
                name=connector,
                width=width,
                height=height,
                source="gnome-mutter",
                x=x,
                y=y,
            )
        )
        log_debug(
            "Detected display: {} {}x{}@{:.3f}".format(
                connector, width, height, refresh
            )
        )

    return outputs


def get_outputs_gnome():
    running_gnome = is_gnome()
    failure_log = log_warning if running_gnome else log_debug
    log_debug("Trying GNOME Mutter DisplayConfig")

    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
    except (ImportError, ValueError) as error:
        failure_log("PyGObject/Gio is unavailable")
        log_trace("Gio import error: {!r}".format(error))
        return []

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
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
        failure_log(
            "Failed to query GNOME Mutter DisplayConfig"
            if running_gnome
            else "GNOME Mutter DisplayConfig is unavailable"
        )
        log_trace("Mutter D-Bus error: {!r}".format(error))
        return []

    try:
        outputs = parse_outputs_gnome(result.unpack())
    except (IndexError, KeyError, TypeError, ValueError) as error:
        failure_log("Could not parse GNOME Mutter response")
        log_trace("Mutter parse error: {!r}".format(error))
        return []

    log_info("Querying displays using GNOME Mutter DisplayConfig")
    if not outputs:
        failure_log("GNOME Mutter returned no active displays")
    return outputs


# ============================================================
# KDE / KScreen JSON
# ============================================================


def parse_kscreen_json_output(raw_output):
    if not isinstance(raw_output, dict):
        return None

    name = raw_output.get("name")
    if not name:
        log_debug("Skipping KScreen output without a name")
        return None
    if not raw_output.get("connected", True):
        log_debug("Skipping disconnected KDE display: {}".format(name))
        return None
    if not raw_output.get("enabled", False):
        log_debug("Skipping disabled KDE display: {}".format(name))
        return None

    current_mode_id = raw_output.get("currentModeId")
    if current_mode_id is None:
        log_debug("KDE display {} has no currentModeId".format(name))
        return None

    modes = raw_output.get("modes", [])
    if not isinstance(modes, list):
        log_debug("KDE display {} has an invalid modes list".format(name))
        return None

    current_mode = next(
        (
            mode
            for mode in modes
            if isinstance(mode, dict)
            and str(mode.get("id")) == str(current_mode_id)
        ),
        None,
    )
    if current_mode is None:
        log_debug(
            "Could not find current mode {} for KDE display {}".format(
                current_mode_id, name
            )
        )
        return None

    size = current_mode.get("size", {})
    if not isinstance(size, dict):
        log_debug("Invalid current mode size for KDE display {}".format(name))
        return None
    try:
        width, height = int(size["width"]), int(size["height"])
    except (KeyError, TypeError, ValueError):
        log_debug("Invalid current mode dimensions for KDE display {}".format(name))
        return None
    if width <= 0 or height <= 0:
        log_debug(
            "Invalid resolution {}x{} for KDE display {}".format(
                width, height, name
            )
        )
        return None

    position = raw_output.get("pos", {})
    try:
        x, y = int(position["x"]), int(position["y"])
    except (KeyError, TypeError, ValueError):
        x, y = None, None

    refresh = current_mode.get("refreshRate")
    try:
        suffix = "@{:.3f}".format(float(refresh)) if refresh is not None else ""
    except (TypeError, ValueError):
        suffix = ""
    log_debug("Detected display: {} {}x{}{}".format(name, width, height, suffix))
    return Output(
        name=name,
        width=width,
        height=height,
        source="kscreen-doctor",
        x=x,
        y=y,
    )


def get_outputs_kscreen_json():
    log_debug("Trying kscreen-doctor JSON output")
    text = run_command(["kscreen-doctor", "-j"], warn_on_failure=False)
    if text is None:
        return None
    if not text.strip():
        log_debug("kscreen-doctor returned empty JSON output")
        return None

    try:
        data = json.loads(text)
    except (TypeError, ValueError) as error:
        log_debug("Could not parse kscreen-doctor JSON")
        log_trace("kscreen-doctor JSON parse error: {!r}".format(error))
        return None

    if not isinstance(data, dict):
        log_debug("kscreen-doctor JSON root is not an object")
        log_trace("kscreen-doctor JSON root: {!r}".format(data))
        return None
    raw_outputs = data.get("outputs", [])
    if not isinstance(raw_outputs, list):
        log_debug("kscreen-doctor JSON does not contain a valid outputs list")
        return None

    outputs = []
    for raw_output in raw_outputs:
        output = parse_kscreen_json_output(raw_output)
        if output is not None:
            outputs.append(output)

    if not outputs:
        log_debug("kscreen-doctor JSON returned no active usable displays")
    return outputs


# ============================================================
# KDE / KScreen text fallback
# ============================================================


def get_outputs_kscreen_text():
    log_debug("Trying kscreen-doctor text output")
    text = run_command(["kscreen-doctor", "-o"], warn_on_failure=False)

    if text is None:
        return []
    if not text.strip():
        log_debug("kscreen-doctor returned empty text output")
        return []

    outputs = []
    sections = re.split(r"(?=^Output:\s*\d+)", text, flags=re.MULTILINE)

    for section in sections:
        header = re.search(r"^Output:\s*\d+\s+(\S+)", section, flags=re.MULTILINE)
        if not header:
            continue

        name = header.group(1)
        section_lines = section.splitlines()
        first_line = section_lines[0] if section_lines else ""

        if re.search(r"\bdisabled\b", first_line, flags=re.IGNORECASE):
            log_debug("Skipping disabled KDE display: {}".format(name))
            continue

        enabled = re.search(r"\benabled\b", first_line, flags=re.IGNORECASE)
        enabled = enabled or re.search(
            r"^\s*enabled\s*$", section, flags=(re.MULTILINE | re.IGNORECASE)
        )
        if not enabled:
            log_debug(
                "Skipping KDE display with unknown/inactive state: {}".format(name)
            )
            continue

        # Current physical mode is marked by '*'.
        #
        # Do not use Geometry here. With fractional scaling,
        # Geometry can represent logical dimensions instead
        # of the physical display mode.
        match = re.search(r"\d+:(\d+)x(\d+)@[^\s]*\*", section)
        if not match:
            log_debug(
                "Could not determine current "
                "physical mode for KDE display: {}".format(name)
            )
            continue

        width, height = int(match.group(1)), int(match.group(2))
        if width <= 0 or height <= 0:
            log_debug(
                "Invalid physical mode {}x{} for KDE display {}".format(
                    width, height, name
                )
            )
            continue

        geometry = re.search(
            r"\bGeometry:\s*(-?\d+)\s*,\s*(-?\d+)",
            section,
            flags=re.IGNORECASE,
        )

        x = int(geometry.group(1)) if geometry else None
        y = int(geometry.group(2)) if geometry else None
        output = Output(
            name=name,
            width=width,
            height=height,
            source="kscreen-doctor",
            x=x,
            y=y,
        )
        outputs.append(output)
        log_debug("Detected display: {} {}x{}".format(name, width, height))

    if not outputs:
        log_debug("kscreen-doctor text output returned no active usable displays")

    return outputs


def get_outputs_kscreen():
    running_kde = is_kde()
    failure_log = log_warning if running_kde else log_debug

    if not shutil.which("kscreen-doctor"):
        failure_log("kscreen-doctor is unavailable")
        return []

    outputs = get_outputs_kscreen_json()
    if outputs:
        log_info("Querying displays using kscreen-doctor JSON")
        return outputs

    log_debug("Falling back to kscreen-doctor text output")
    outputs = get_outputs_kscreen_text()
    if outputs:
        log_info("Querying displays using kscreen-doctor text output")
        return outputs

    failure_log("Could not detect displays using kscreen-doctor")
    return []


# ============================================================
# wlroots
# ============================================================


def get_outputs_wlr_randr():
    if not shutil.which("wlr-randr"):
        log_debug("wlr-randr is unavailable")
        return []

    log_debug("Trying wlr-randr")

    text = run_command(["wlr-randr"], warn_on_failure=False)

    if text is None:
        return []
    if not text.strip():
        log_debug("wlr-randr returned empty output")
        return []

    outputs = []
    sections = re.split(r"(?=^\S)", text, flags=re.MULTILINE)

    for section in sections:
        header = re.match(r"^(\S+)", section)
        if not header:
            continue

        name = header.group(1)
        match = re.search(r"(\d+)x(\d+).*current", section, flags=re.IGNORECASE)
        if not match:
            continue

        position = re.search(
            r"^\s*Position:\s*(-?\d+)\s*,\s*(-?\d+)",
            section,
            flags=(re.MULTILINE | re.IGNORECASE),
        )
        output = Output(
            name=name,
            width=int(match.group(1)),
            height=int(match.group(2)),
            source="wlr-randr",
            x=int(position.group(1)) if position else None,
            y=int(position.group(2)) if position else None,
        )
        outputs.append(output)
        log_debug(
            "Detected display: {} {}x{}".format(
                output.name, output.width, output.height
            )
        )
    if not outputs:
        log_debug("wlr-randr returned no active usable displays")

    return outputs


# ============================================================
# XRandR
# ============================================================


def get_outputs_xrandr():
    running_x11 = get_session_type() == "x11"
    failure_log = log_warning if running_x11 else log_debug

    if not shutil.which("xrandr"):
        log_debug("xrandr is unavailable")
        return []

    log_debug("Trying xrandr")

    text = run_command(["xrandr", "--query"], warn_on_failure=running_x11)

    if text is None:
        return []

    if not text.strip():
        failure_log("xrandr returned empty output")
        return []

    outputs = []

    pattern = re.compile(
        r"^(\S+)\s+connected"
        r"(?:\s+primary)?"
        r"\s+(\d+)x(\d+)"
        r"([+-]\d+)([+-]\d+)",
        flags=re.MULTILINE,
    )

    for match in pattern.finditer(text):
        output = Output(
            name=match.group(1),
            width=int(match.group(2)),
            height=int(match.group(3)),
            source="xrandr",
            x=int(match.group(4)),
            y=int(match.group(5)),
        )

        outputs.append(output)

        log_debug(
            "Detected display: {} {}x{}".format(
                output.name, output.width, output.height
            )
        )

    if not outputs:
        failure_log("xrandr returned no active usable displays")

    return outputs


# ============================================================
# Display detection
# ============================================================


def get_outputs_file(filename):
    outputs = []
    names = set()

    try:
        with open(filename, "r", encoding="utf-8-sig") as screen_file:
            lines = screen_file.readlines()
    except OSError as error:
        raise ValueError(
            "could not read screens file '{}': {}".format(filename, error)
        )

    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = SCREEN_FILE_PATTERN.fullmatch(line)
        if not match:
            raise ValueError(
                "invalid screens file entry at {}:{}: {!r}".format(
                    filename,
                    line_number,
                    line,
                )
            )

        name, width, height, x, y = match.groups()
        width, height = int(width), int(height)
        if width <= 0 or height <= 0:
            raise ValueError(
                "invalid screen size at {}:{}: {}x{}".format(
                    filename, line_number, width, height
                )
            )

        name_key = name.lower()
        if name_key in names:
            raise ValueError(
                "duplicate screen name at {}:{}: {}".format(
                    filename,
                    line_number,
                    name,
                )
            )

        names.add(name_key)

        outputs.append(
            Output(
                name=name,
                width=width,
                height=height,
                source="file",
                x=int(x),
                y=int(y),
            )
        )

    return outputs


def middle_position(positions):
    if len(positions) % 2:
        return positions[len(positions) // 2]
    return None


def assign_output_tags(outputs):
    if not outputs:
        return

    areas = [output.width * output.height for output in outputs]
    largest_area, smallest_area = max(areas), min(areas)
    positioned_outputs = [
        output
        for output in outputs
        if output.x is not None and output.y is not None
    ]
    x_positions = sorted(set(output.x for output in positioned_outputs))
    y_positions = sorted(set(output.y for output in positioned_outputs))
    position_rules = []

    if positioned_outputs:
        center_x = middle_position(x_positions)
        center_y = middle_position(y_positions)
        position_rules = [
            ("left", "x", x_positions[0]),
            ("right", "x", x_positions[-1]),
            ("center-column", "x", center_x),
            ("top", "y", y_positions[0]),
            ("bottom", "y", y_positions[-1]),
            ("center-row", "y", center_y),
        ]

    for output in outputs:
        tags = [
            tag
            for tag, axis, position in position_rules
            if position is not None and getattr(output, axis) == position
        ]
        area = output.width * output.height

        if area == largest_area:
            tags.append("largest")
        if area == smallest_area:
            tags.append("smallest")
        output.tags = tags


def get_outputs(screen_file=None):
    if screen_file is not None:
        outputs = get_outputs_file(screen_file)
        assign_output_tags(outputs)

        log_info(
            "Loaded {} display(s) from {}".format(
                len(outputs),
                screen_file,
            )
        )

        return outputs

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    session_desktop = os.environ.get("XDG_SESSION_DESKTOP", "")
    session_type = get_session_type()
    log_debug("Desktop environment: {}".format(desktop or "unknown"))
    log_debug("Session desktop: {}".format(session_desktop or "unknown"))
    log_debug("Session type: {}".format(session_type))

    if is_gnome():
        detectors = [("gnome-mutter", get_outputs_gnome)]
        if session_type == "x11":
            detectors.append(("xrandr", get_outputs_xrandr))
    elif is_kde():
        detectors = [("kscreen-doctor", get_outputs_kscreen)]
        if session_type == "x11":
            detectors.append(("xrandr", get_outputs_xrandr))
    elif session_type == "x11":
        detectors = [
            ("xrandr", get_outputs_xrandr),
            ("kscreen-doctor", get_outputs_kscreen),
            ("gnome-mutter", get_outputs_gnome),
        ]
    else:
        detectors = [
            ("wlr-randr", get_outputs_wlr_randr),
            ("kscreen-doctor", get_outputs_kscreen),
            ("gnome-mutter", get_outputs_gnome),
        ]

    for name, detector in detectors:
        log_debug("Trying display detector: {}".format(name))
        outputs = detector()
        if outputs:
            assign_output_tags(outputs)
            log_info(
                "Detected {} display(s) using {}".format(len(outputs), name)
            )
            return outputs

    log_warning("No displays could be detected")

    return []


def print_outputs(
    outputs,
    heading="Detected displays:",
    show_empty=False,
):
    if not outputs and not show_empty:
        return

    log_info(heading)

    log_info(
        "  {:<5} {:<14} {:<11} {:<16} {:<18} {}".format(
            "INDEX",
            "NAME",
            "RESOLUTION",
            "POSITION",
            "SOURCE",
            "TAGS",
        )
    )

    for index, output in enumerate(outputs):
        position = (
            "unknown"
            if output.x is None or output.y is None
            else "{},{}".format(output.x, output.y)
        )

        log_info(
            "  {:<5} {:<14} {:<11} {:<16} {:<18} {}".format(
                index,
                output.name,
                "{}x{}".format(output.width, output.height),
                position,
                output.source,
                ",".join(output.tags) if output.tags else "-",
            )
        )


# ============================================================
# Argument parsers
# ============================================================


def parse_window_mode(value):
    mode = WINDOW_MODE_ALIASES.get(value.strip().lower())
    if mode is None:
        raise argparse.ArgumentTypeError(
            "invalid window mode: {} "
            "(expected fullscreen/f, "
            "borderless/b, or windowed/w)".format(value)
        )

    return mode


# ============================================================
# Screen selectors
# ============================================================


def parse_display_selectors(value):
    selectors = tuple(
        selector.strip()
        for selector in re.split(r"[+,]", value.strip().lower())
    )
    return selectors if all(selector in DISPLAY_SELECTORS for selector in selectors) else None


def normalize_selector_tags(selectors):
    selector_tags = set(selectors)

    if "center" not in selector_tags:
        return selector_tags

    horizontal_selected = not selector_tags.isdisjoint(HORIZONTAL_SELECTORS)
    vertical_selected = not selector_tags.isdisjoint(VERTICAL_SELECTORS)

    selector_tags.remove("center")

    if vertical_selected and not horizontal_selected:
        selector_tags.add("center-column")
    elif horizontal_selected and not vertical_selected:
        selector_tags.add("center-row")
    else:
        selector_tags.update(("center-column", "center-row"))

    return selector_tags


def filter_outputs_by_constraints(
    selectors,
    outputs,
):
    selector_tags = normalize_selector_tags(selectors)
    return [
        output
        for output in outputs
        if selector_tags.issubset(set(output.tags))
    ]


# ============================================================
# Screen and resolution parsing
# ============================================================


def filter_outputs_for_screen(
    value,
    outputs,
):
    value_lower = value.lower()

    if value.isdigit():
        return []

    selectors = parse_display_selectors(value)

    if selectors is not None:
        return filter_outputs_by_constraints(
            selectors,
            outputs,
        )

    exact_matches = [output for output in outputs if output.name == value]

    if exact_matches:
        return exact_matches

    return [
        output
        for output in outputs
        if output.name.lower() == value_lower
    ]


def select_screen(
    value,
    outputs,
):
    if value.isdigit():
        raise ValueError(
            "detected-screen indexes are not supported; "
            "use a screen selector or connector name"
        )

    selectors = parse_display_selectors(value)
    matches = filter_outputs_for_screen(
        value,
        outputs,
    )

    if len(matches) == 1:
        output = matches[0]
        if selectors is None:
            log_info("Matched screen: {}".format(output.name))
        else:
            log_info("Screen selector '{}' matched {}".format(value, output.name))
        return output

    if not matches:
        if selectors is None:
            raise ValueError("invalid or unavailable screen: {}".format(value))
        if not outputs:
            raise ValueError(
                "screen selector '{}' cannot be used because "
                "no displays were detected".format(value)
            )
        raise ValueError(
            "screen selector '{}' did not match any screen".format(value)
        )

    raise ValueError(
        "{} '{}' matched multiple {}: {}".format(
            "screen" if selectors is None else "screen selector",
            value,
            "displays" if selectors is None else "screens",
            ", ".join(output.name for output in matches),
        )
    )


def parse_resolution(value):
    log_debug("Parsing resolution argument: {}".format(value))

    resolution = RESOLUTION_ALIASES.get(value.lower())
    if resolution is not None:
        width, height = resolution
        log_info(
            "Resolution alias '{}' resolved to {}x{}".format(value, width, height)
        )
        return width, height

    match = RESOLUTION_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("invalid resolution: {}".format(value))

    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        raise ValueError("invalid resolution: {}".format(value))

    log_info("Using explicit resolution: {}x{}".format(width, height))
    return width, height


def resolve_resolution(value=None, output=None):
    if value is not None:
        return parse_resolution(value)
    if output is not None:
        return output.width, output.height
    return None, None


def run_pretend(args):
    outputs = get_outputs(args.screen_file)
    print_outputs(outputs, heading="Detected displays:", show_empty=True)

    matched = (
        outputs
        if args.screen is None
        else filter_outputs_for_screen(args.screen, outputs)
    )
    print_outputs(
        matched,
        heading="Matched displays ({}):".format(len(matched)),
        show_empty=True,
    )

    output = matched[0] if args.screen is not None and len(matched) == 1 else None
    width, height = resolve_resolution(args.resolution, output)
    resolution = (
        "undetermined"
        if width is None or height is None
        else "{}x{}".format(width, height)
    )
    log_info("Resolution: {}".format(resolution))
    return 0


def parse_launch_args(parser, args):
    try:
        args.window = parse_window_mode(args.window)
    except argparse.ArgumentTypeError as error:
        parser.error("argument -w/--window: {}".format(error))

    if args.display_index is not None:
        try:
            args.display_index = int(args.display_index)
        except ValueError:
            parser.error(
                "argument -d/--display-index: "
                "invalid int value: {!r}".format(args.display_index)
            )
        if args.display_index < 0:
            parser.error("--display-index must be >= 0")

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("missing game command")
    return command


def select_launch_output(args):
    if args.screen is None:
        return None

    outputs = get_outputs(args.screen_file)
    if outputs:
        log_debug("Available displays:")
        for index, output in enumerate(outputs):
            log_debug(
                "  [{}] {} {}x{} via {}".format(
                    index, output.name, output.width, output.height, output.source
                )
            )

    try:
        return select_screen(args.screen, outputs)
    except ValueError:
        print_outputs(outputs)
        raise


def build_gamescope_command(args, command, output, width, height):
    gamescope = [
        "gamescope",
        "-w", str(width), "-h", str(height),
        "-W", str(width), "-H", str(height),
    ]
    if args.window == "fullscreen":
        gamescope.append("-f")
    elif args.window == "borderless":
        gamescope.append("-b")
    log_info("Gamescope window mode: {}".format(args.window))

    if output is not None:
        gamescope.extend(["-O", output.name])
        log_info("Gamescope preferred output: {}".format(output.name))
    if args.display_index is not None:
        gamescope.extend(["--display-index", str(args.display_index)])
        log_info("Gamescope display index: {}".format(args.display_index))

    return gamescope + ["--"] + command


# ============================================================
# Argument parser
# ============================================================


FULL_HELP_EPILOG = """
Examples:

  Detect and print displays without launching Gamescope:

    %(prog)s -p
    %(prog)s --pretend
    %(prog)s --print
    %(prog)s -p -s largest+left
    %(prog)s -p -s largest -r 4K
    %(prog)s -p --screen-file screens.txt

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

  Screen connector:

    %(prog)s -s DP-1 -- ./game
    %(prog)s -s dp-1 -- ./game
    %(prog)s -s DP-1 --screen-file screens.txt -- ./game

  Screen selectors:

    %(prog)s -s largest -- ./game
    %(prog)s -s left -- ./game
    %(prog)s -s top+center -- ./game
    %(prog)s -s left+center -- ./game
    %(prog)s -s largest+left -- ./game
    %(prog)s -s top+left+largest -- ./game

  Gamescope display-index fallback:

    %(prog)s -s DP-1 -d 1 -- ./game

  Debug logging:

    %(prog)s -l DEBUG -s DP-1 -- ./game

  Full trace:

    %(prog)s -l TRACE -s DP-1 -- ./game


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


Screens file:

  One screen per line using NAME WIDTHxHEIGHT+X+Y geometry:

    DP-1 3840x2160+0+0
    HDMI-A-2 2880x1800+3840+360
    HDMI-A-1 1920x1080-1920+0

  Blank lines and lines beginning with '#' are ignored.


Screen selectors:

  largest / smallest
  left / right / top / bottom
  center / center-column / center-row

  Size selectors compare resolution width * height (pixel area).
  Position selectors compare display order, not pixel distance.
  center-column and center-row can be used directly. If exactly one axis is
  already constrained, 'center' constrains the other axis. Otherwise,
  it expands to both center-column and center-row. A center position exists
  only when that axis has an odd number of arranged positions.

  Selectors can be combined with '+'. Their order does not matter.
  Hyphens are part of selector and connector names, not separators.
  Selectors are matched directly against each screen's calculated tags.
  Launching requires all constraints to match exactly one display.


Notes:

  -p/--pretend/--print only detects and prints displays. It does not
  require a resolution or game command, and does not launch Gamescope.
  With -s, it prints every matching physical display; zero or multiple
  matches are not errors in pretend mode. It also prints the resolved
  resolution when one can be determined. Display rows include position
  and size tags calculated from the complete detected layout.

  Resolution aliases, WIDTHxHEIGHT, screen selectors,
  connector names, and window mode values are case-insensitive.

  -sf/--screen-file replaces automatic display detection. Tags are calculated
  from the complete layout in the file; SOURCE is shown as 'file'.

  -r/--resolution only sets the Gamescope resolution. If omitted,
  the resolution is taken from the screen selected by -s/--screen.

  When -s selects a physical display, Gamescope receives:

      -O <connector>

  -d/--display-index is passed directly to
  Gamescope as:

      --display-index N

  -d N uses Gamescope's own display-index.
"""


def build_parser():
    parser = argparse.ArgumentParser(
        description="Simplified Gamescope launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    class FullHelpAction(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            parser.epilog = FULL_HELP_EPILOG
            parser.print_help()
            parser.exit()

    add = parser.add_argument
    add(
        "-hf",
        "--help-full",
        action=FullHelpAction,
        nargs=0,
        help="show full help with examples and exit",
    )
    add(
        "-p",
        "--pretend",
        "--print",
        action="store_true",
        help="detect and print displays without launching Gamescope",
    )
    add(
        "-r",
        "--resolution",
        metavar="RESOLUTION",
        help="1k, 2k, 4k, 8k, 16k, or WIDTHxHEIGHT",
    )
    add(
        "-s",
        "--screen",
        metavar="SCREEN",
        help="screen selector or connector name",
    )
    add(
        "-sf",
        "--screen-file",
        metavar="FILE",
        help="read detected screens from FILE",
    )
    add(
        "-w",
        "--window",
        default="fullscreen",
        metavar="MODE",
        help=(
            "window mode: fullscreen/f, "
            "borderless/b, or windowed/w "
            "(default: fullscreen)"
        ),
    )
    add(
        "-d",
        "--display-index",
        metavar="INDEX",
        help="pass --display-index INDEX directly to Gamescope",
    )
    add(
        "-l",
        "--log-level",
        default="INFO",
        type=str.upper,
        choices=["ERROR", "WARNING", "INFO", "DEBUG", "TRACE"],
        metavar="LEVEL",
        help="logging level: ERROR, WARNING, INFO, DEBUG or TRACE (default: INFO)",
    )
    add("command", nargs=argparse.REMAINDER, help="game command and arguments")

    return parser


# ============================================================
# Main
# ============================================================


def main():
    global LOG_LEVEL

    parser = build_parser()
    args = parser.parse_args()

    LOG_LEVEL = LogLevel[args.log_level]
    log_debug("Log level: {}".format(LOG_LEVEL.name))

    if args.pretend:
        try:
            return run_pretend(args)
        except ValueError as error:
            log_error(str(error))
            return 2

    command = parse_launch_args(parser, args)
    log_debug("Game command: {}".format(format_command(command)))

    try:
        output = select_launch_output(args)
        width, height = resolve_resolution(args.resolution, output)
    except ValueError as error:
        log_error(str(error))
        return 2

    if args.resolution is None and output is not None:
        log_info(
            "Using selected screen resolution: {}x{}".format(width, height)
        )
    if width is None or height is None:
        log_error(
            "resolution could not be determined; "
            "use -r/--resolution or -s/--screen"
        )
        return 2

    gamescope_command = build_gamescope_command(
        args, command, output, width, height
    )
    log_info("Gamescope resolution: {}x{}".format(width, height))
    if output is not None:
        log_info("Matched monitor: {}".format(output.name))
        log_info("Monitor detector: {}".format(output.source))
    log_info("Launching Gamescope")
    log_debug("Gamescope command: {}".format(format_command(gamescope_command)))
    log_trace("Gamescope argv: {!r}".format(gamescope_command))

    try:
        os.execvp(gamescope_command[0], gamescope_command)
    except FileNotFoundError:
        log_error("gamescope executable not found")
        return 127
    except OSError as error:
        log_error("failed to execute gamescope: {}".format(error))
        return 126


if __name__ == "__main__":
    sys.exit(main())
