/* SPDX-License-Identifier: Apache-2.0 */
#include "imu_gpio_timing.h"

#include <zephyr/shell/shell.h>

struct rdd2_imu_gpio_timing_state g_rdd2_imu_gpio_timing;

/* Counters are read on demand from the shell, never printed by the driver. */
static int cmd_gpio_timing_status(const struct shell *sh, size_t argc, char **argv)
{
  ARG_UNUSED(argc);
  ARG_UNUSED(argv);
  shell_print(sh, "imu_aborted=%ld imu_ignored=%ld",
              (long)atomic_get(&g_rdd2_imu_gpio_timing.aborted),
              (long)atomic_get(&g_rdd2_imu_gpio_timing.ignored));
  return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(gpio_timing_cmds,
    SHELL_CMD(status, NULL, "Read acquisition capture validity counters.",
              cmd_gpio_timing_status),
    SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(gpio_timing, &gpio_timing_cmds, "GPIO timing diagnostics.", NULL);
