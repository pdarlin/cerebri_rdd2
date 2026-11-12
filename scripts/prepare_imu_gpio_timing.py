#!/usr/bin/env python3
"""Instrument a build-local copy of the manifest-pinned ICM45686 stream driver."""

import hashlib
from pathlib import Path
import re
import sys


# west.yml: CogniPilot/zephyr bf19ff6eb2cff5aac91242af56b514273cdf9a94.
EXPECTED_SHA256 = "304c6983ac4765cdf945c9e2a78b3b46504fcf58593cea2fc04383f51ddb8422"


def instrument(source: bytes) -> str:
    # Normalize checkout line endings, but require the exact pinned source.
    source = source.replace(b"\r\n", b"\n")
    if hashlib.sha256(source).hexdigest() != EXPECTED_SHA256:
        raise ValueError("ICM45686 source differs from west.yml pin; review timing hooks before updating")
    text = source.decode("utf-8")

    def replace_once(old: str, new: str) -> None:
        nonlocal text
        if text.count(old) != 1:
            raise ValueError(f"Expected exactly one timing insertion point: {old!r}")
        text = text.replace(old, new, 1)

    replace_once('#include "icm45686_stream.h"',
                 '#include "icm45686_stream.h"\n#include "imu_gpio_timing.h"')
    # The captured token identifies this acquisition, even when multishot RTIO
    # reuses an SQE address. No-response callback userdata is otherwise unused
    # by this driver and does not change the sensor's submitted request.
    replace_once(
        '\t\tLOG_WRN("Callback triggered with no streaming submission - Disabling interrupts");',
        '\t\trdd2_imu_gpio_timing_abort();\n'
        '\t\tLOG_WRN("Callback triggered with no streaming submission - Disabling interrupts");',
    )
    replace_once(
        '\t\tLOG_WRN("Event handler triggered while a stream is in progress! Ignoring");',
        '\t\trdd2_imu_gpio_timing_ignored();\n'
        '\t\tLOG_WRN("Event handler triggered while a stream is in progress! Ignoring");',
    )
    replace_once(
        "\terr = sensor_clock_get_cycles(&cycles);",
        "\tvoid *timing_owner = rdd2_imu_gpio_timing_begin();\n\n"
        "\terr = sensor_clock_get_cycles(&cycles);",
    )
    replace_once(
        "rtio_sqe_prep_callback_no_cqe(complete_sqe, icm45686_complete_handler, (void *)dev,\n"
        "\t\t\t\t      data->stream.iodev_sqe);",
        "rtio_sqe_prep_callback_no_cqe(complete_sqe, icm45686_complete_handler, (void *)dev,\n"
        "\t\t\t\t      timing_owner);",
    )

    def clean_exits(start: str, end: str, owner: str, expected: int) -> None:
        nonlocal text
        first, last = text.index(start), text.index(end)
        body, count = re.subn(
            r"(?m)^([\t ]*)(icm45686_stream_result\(dev, [^;]+;)",
            lambda m: f"{m[1]}rdd2_imu_gpio_timing_finish({owner}, false);\n{m[1]}{m[2]}",
            text[first:last],
        )
        if count != expected:
            raise ValueError(f"Expected {expected} acquisition exits in {start}, got {count}")
        text = text[:first] + body + text[last:]

    # Finish every early failure using its own captured token, then specialize
    # the normal completion to require successful transfers and a DRDY event.
    clean_exits("static void icm45686_complete_handler", "static void icm45686_event_handler",
                "sqe->userdata", 5)
    clean_exits("static void icm45686_event_handler", "static void icm45686_gpio_callback",
                "timing_owner", 6)
    replace_once(
        "\trdd2_imu_gpio_timing_finish(sqe->userdata, false);\n"
        "\ticm45686_stream_result(dev, err);\n}\n\nstatic void icm45686_event_handler",
        "\trdd2_imu_gpio_timing_finish(sqe->userdata,\n"
        "\t\t\t\t     err == 0 && data->stream.data.events.drdy);\n"
        "\ticm45686_stream_result(dev, err);\n}\n\nstatic void icm45686_event_handler",
    )
    return text


def main() -> None:
    source, output = map(Path, sys.argv[1:])
    result = instrument(source.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    # Avoid touching the compiler input on every CMake reconfiguration.
    if not output.exists() or output.read_bytes() != result.encode("utf-8"):
        output.write_bytes(result.encode("utf-8"))


if __name__ == "__main__":
    main()
