# Two-channel GPIO timing

## Build; do not flash

The original marker was recovered from commit `9febcd5` on local `origin/main`,
whose parent is `5d8f389`. This extension retains the optional `gpio-timing`
snippet and CH1's pin/polarity, and narrows its endpoint to before motor output.

From this application in a populated West workspace:

```sh
west build -b mr_vmu_tropic/mimxrt1064 -d build-gpio-timing -S gpio-timing .
```

For dependencies in a separate West workspace:

```sh
cd /absolute/path/to/west-workspace
west build -b mr_vmu_tropic/mimxrt1064 -d /absolute/path/to/app/build-gpio-timing \
  -S gpio-timing /absolute/path/to/app -- -DRDD2_WORKSPACE_ROOT="$PWD"
```

Alternatively: `nix run .#build -- -S gpio-timing`.
Use a separate directory for an uninstrumented comparison build.
Outputs include `build-gpio-timing/zephyr/zephyr.elf` and `zephyr.bin`.
Building does not flash the board.

The option defaults off and is restricted to Tropic hardware with the
asynchronous ICM45686 stream, outside lockstep. Without it, application marker
calls are empty inline functions and the original Zephyr driver is compiled.

## Pin ownership and physical DRDY access

In the published rev-F schematic, the IMU interrupt net is named
`ICM42688_DRDY`. Its listed endpoints are U7 pin 4 and MCU `GPIO_EMC_32`;
there is no designated connector or test point. The pinned board DTS uses
GPIO3_IO18 for the ICM45686 interrupt, consistent with that pad.
J6 `OSD_DRDY` is a different net.

Probing internal DRDY would expose the physical assertion without GPIO-marker
overhead and include interrupt-entry delay when compared with a completion
marker. DRDY's own width is not acquisition duration. Two GPIO pulses allow
acquisition and processing widths to be measured on two channels simultaneously.

| Scope connection | Board connection | GPIO |
| --- | --- | --- |
| CH1 tip: processing | J7 AUX pin 5, AUX_RTS | GPIO_AD_B0_14 / GPIO1_IO14 |
| CH2 tip: acquisition | J7 AUX pin 4, AUX_CTS | GPIO_AD_B0_15 / GPIO1_IO15 |
| Both probe grounds | J7 pin 6 | GND |

AUX signals pass through RN5. The pinned UART4 pinctrl uses only TX/RX on
GPIO_B1_00/01; neither timing pad is claimed by another enabled peripheral in
this configuration. The snippet reserves RTS/CTS, disables UART4 hardware flow
control, and applies the GPIO mux before IMU streaming. UART4 TX/RX remain
available. Do not enable runtime flow control, remux the pads, or attach another
device driving them. No motor breakout cable is needed.

Check board revision and connector orientation: these mappings are verified for
rev F; pin 1 has a square pad. J7 pin 1 supplies **5 V**, not a timing signal or
ground. Signal levels are nominally 3.3 V.

Sources:

- [Rev-F schematic](https://github.com/NXP-Robotics/MR-VMU-TROPIC/blob/main/schematics_and_production_files/tropic_rev_F/SPF-94468_F.pdf)
- [Connector mapping](https://github.com/NXP-Robotics/MR-VMU-TROPIC/blob/main/pinout.yaml)
- [Pinned board DTS](https://github.com/CogniPilot/zephyr_boards/blob/a21d0040d455e3520816e1a64335ae4a9b740cab/boards/nxp/mr_vmu_tropic/mr_vmu_tropic.dts)
- [Pinned board pinctrl](https://github.com/CogniPilot/zephyr_boards/blob/a21d0040d455e3520816e1a64335ae4a9b740cab/boards/nxp/mr_vmu_tropic/mr_vmu_tropic-pinctrl.dtsi)

## CH1: processing

HIGH is the first statement after `rdd2_control_input_wait()` returns.
Each path lowers CH1 before motor output and `finalize_cycle()`:

| Path | LOW location | Work included |
| --- | --- | --- |
| Normal ACRO / AUTO_LEVEL | Immediately after `rdd2_mix_quad_x()` | Status/arming checks, estimator when due, resets, setpoints/throttle, rate controller, mixer |
| Disarmed, valid inputs | Same as normal | Existing calculations; output still enforces disarmed behavior |
| Normalized motor test | After test getter succeeds | Common checks/estimator/reset and test selection/copy; no rate PID or mixer |
| Raw motor test | After raw-test getter succeeds | Common work and both test checks; no rate PID or mixer |
| Invalid IMU / stale RC | At the invalid-input branch | Common work and test checks; no rate PID or mixer |

CH1 excludes input waiting/decoding/RC copying inside the input function,
output conversion/publication/triggering, latency statistics, and final
flight-state publication. It measures elapsed wall time including preemption,
not exclusive CPU time. Decimated estimator iterations have different widths.

## CH2: acquisition and pairing

HIGH follows successful `ON -> BUSY` acceptance in the pinned driver's
`icm45686_event_handler()`, called from `icm45686_gpio_callback()`. It precedes
timestamping and the chained asynchronous status/data reads.

LOW occurs in `icm45686_complete_handler()` after read completions are checked
and the encoded header finalized, before publishing the result to RTIO.
The callback's captured `sqe->userdata` must match the accepted acquisition
token. Each accepted read gets a new token, even if RTIO reuses an SQE address.
Success requires successful transfers and DRDY. This includes driver completion
bookkeeping, excludes application wakeup/decoding/RC copying, and excludes
physical DRDY-to-ISR delay.

The existing driver accepts one acquisition at a time. Ignored interrupts
neither toggle CH2 nor replace its owner. A nonmatching completion cannot lower
another owner's pulse. Errors, non-DRDY completions, cancellation and recovery
clear affected pulses and count them as aborted. An error pulse may look like
a valid short pulse: do not include it in successful-acquisition statistics.

Run `gpio_timing status` before and after each capture, outside its time window.
It reads cumulative `imu_aborted` and `imu_ignored` counters. Use only windows
where neither changes; discard windows crossing errors, restarts, cancellation,
or ignored interrupts. No logging is added to the ISR/control loop; existing
firmware error logs remain.

Pairing identifies an accepted driver read, not a hardware sample sequence
number. Live registers are read without FIFO buffering: if a later sensor update
overtakes the acquisition, timing alone cannot prove historical sample identity.
Sensor settings and scheduling are deliberately unchanged.

## Reproducible driver integration

`west.yml` retains Zephyr pin `bf19ff6eb2cff5aac91242af56b514273cdf9a94`.
With timing enabled, `cmake/ImuGpioTiming.cmake` runs
`scripts/prepare_imu_gpio_timing.py`. It checks the pinned stream source SHA-256
(normalizing CRLF), inserts checked hooks, and writes
`generated/gpio-timing/icm45686_stream.c` in the build directory.

CMake replaces exactly that translation unit on the existing driver target,
retaining its flags/includes and other sources. It does not edit the dependency
checkout or compile a second driver. Source/hash/insertion-point changes fail
configuration. Reconfiguration tracks both source and script. Review hooks/hash
when deliberately updating the Zephyr pin.

Both outputs initialize LOW before streaming. Normal operation adds one GPIO
set/clear per channel with inline helpers, no allocation, extra thread, delay,
or additional sensor transaction. Exceptional paths update validity counters.
The pinned MCUX GPIO driver uses the RT1064's atomic DR_SET/DR_CLEAR registers,
so ISR updates of CH2 do not clobber CH1 on the same GPIO bank. GPIO writes and
ownership bookkeeping add a small observer cost.

## Oscilloscope capture

Use high-impedance x10 probes, short grounds, and DC coupling. Start around
100 us/div and trigger on CH2 rising near half the logic amplitude. Enable
positive pulse-width measurements on both channels and persistence/histograms
for min/max, mean, standard deviation and peak-to-peak spread. The nominal
rising-edge repetition interval is 625 us at 1600 Hz.

```text
CH2  ____| acquisition |________________________________
CH1  ______________________| processing |_______________
          accepted IRQ  ^    ^          ^
                       |    |          calculations ready
              data ready    input_wait returned
```

The CH2-falling to CH1-rising gap includes application delivery/decoding and RC
acquisition. Neither width includes it. Do not label the sum of pulse widths
physical DRDY-to-motor latency. These are independent acquisition and processing
measurements, with no motor-signal instrumentation. RTIO may queue completions;
adjacent edges on different channels do not establish sample pairing during a
backlog. The CH2 token pairs the two edges of its own acquisition pulse.

Record firmware/board revisions, mode, arm/test state, workload, tracing state,
scope sample rate, capture duration, and validity-counter deltas.

## Verification

The hardware firmware was successfully built for `mr_vmu_tropic/mimxrt1064`
with the `gpio-timing` snippet, Zephyr SDK 1.0.1 (GCC 14.3.0), and the manifest
pins above. The compile database contains exactly one IMU stream translation
unit, using the generated instrumented copy; the dependency source is unchanged.
No board was flashed and electrical timing has not been validated on hardware.

`python3 tests/test_gpio_timing.py` passes two host checks: accepted-acquisition
token pairing/error/recovery handling (including reused requests and wraparound),
and compilation of disabled helpers without GPIO or Zephyr symbols. The host
tests require `cc`. Driver preparation also rejects changed dependency contents
and accepts either LF or CRLF checkouts.
