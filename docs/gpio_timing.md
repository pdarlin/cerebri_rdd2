# GPIO timing bench measurement

Build the normal Tropic hardware firmware with the optional snippet:

```sh
nix run .#build -- -p always -S gpio-timing
```

For an existing West workspace, use:

```sh
west build -b mr_vmu_tropic/mimxrt1064 -d build-gpio-timing -p always -S gpio-timing .
```

The option defaults off. Without the snippet, the marker calls compile to
empty inline functions and the normal board pin configuration is retained.
The marker is unavailable in lockstep builds.

## Wiring

Remove propellers and preferably disconnect ESC motor power. Verify the board
revision and connector orientation against its schematic before connecting.
These connector numbers follow the published rev-F Tropic pinout:

| Scope connection | Board connection |
| --- | --- |
| CH1 tip: loop marker | J7 AUX pin 5 (GPIO_AD_B0_14 / GPIO1_IO14, AUX_RTS) |
| CH2 tip: motor 1 DShot | J13 PWM_A pin 5 (EMC06 / FlexIO1 pin 6) |
| Probe ground | J7 pin 6 (GND); J13 pin 2 is also GND |

Reserve J7 pin 5 for the scope; disconnect any external device connected to it.
J7 pin 1 is a 5 V output: leave it disconnected from the scope signal and ground.
The snippet assigns AUX_RTS to GPIO and disables LPUART4 hardware flow control.
The GPIO mux is applied during main initialization, after UART initialization.
Do not enable runtime UART flow control or remux this pad during the test.
J7 UART TX/RX on pins 2/3 remain available. DShot pin configuration is unchanged.
The four active motor channels remain on EMC06, EMC07, EMC09, and EMC08.

Use high-impedance x10 probes, short ground connections, DC coupling, and a
rising-edge CH1 trigger near half the measured logic amplitude (nominal 3.3 V).
Start around 100 us/div and adjust to show several iterations.

## What the pulse means

The marker rises immediately after `rdd2_control_input_wait()` returns in
`src/main.c`. It falls at the end of `finalize_cycle()`, after metrics and
flight-state publication. Every current iteration exit calls this finalizer,
including motor tests and invalid-input paths.

- Rising-to-rising interval: processing-start cadence, nominally 625 us.
- High width: elapsed processing time through finalization, including preemption.
- CH1 rising to the first CH2 DShot edge: processing-start-to-output latency.
- Consecutive DShot frame starts: actual outgoing update interval.

The marker excludes waiting for the IMU, sample decoding, and RC acquisition
inside the input function. It does not measure physical IMU-ready-to-output
latency or exclusive CPU execution time. CH1 falls after the output is launched;
it does not mean the DShot transmission has finished.

DShot contains many rising edges per frame. Identify the first edge following
the inter-frame idle gap rather than measuring every adjacent rising edge.
Capture continuous waveforms when checking for missing or unusually close frames.

No logging, allocation, extra thread, or intentional delay is added per iteration.
There are two GPIO API writes per iteration; their overhead is included in the
instrumented result. Compare DShot captures with and without the snippet, and
record firmware revision, board revision, flight mode, arming state, tracing
configuration, workload, scope sample rate, and capture duration.
