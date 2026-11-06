/* SPDX-License-Identifier: Apache-2.0 */
#ifndef RDD2_GPIO_TIMING_H_
#define RDD2_GPIO_TIMING_H_

#if defined(CONFIG_RDD2_GPIO_TIMING)
#include <errno.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/pinctrl.h>

#define RDD2_TIMING_NODE DT_NODELABEL(rdd2_timing)
PINCTRL_DT_DEFINE(RDD2_TIMING_NODE);
static const struct gpio_dt_spec rdd2_timing_gpio =
    GPIO_DT_SPEC_GET(RDD2_TIMING_NODE, gpios);

static inline int rdd2_gpio_timing_init(void)
{
  int rc;

  if (!gpio_is_ready_dt(&rdd2_timing_gpio)) {
    return -ENODEV;
  }
  rc = pinctrl_apply_state(PINCTRL_DT_DEV_CONFIG_GET(RDD2_TIMING_NODE),
                           PINCTRL_STATE_DEFAULT);
  if (rc != 0) {
    return rc;
  }
  return gpio_pin_configure_dt(&rdd2_timing_gpio, GPIO_OUTPUT_INACTIVE);
}

static inline void rdd2_gpio_timing_begin(void)
{
  (void)gpio_pin_set_dt(&rdd2_timing_gpio, 1);
}

static inline void rdd2_gpio_timing_end(void)
{
  (void)gpio_pin_set_dt(&rdd2_timing_gpio, 0);
}
#else
static inline int rdd2_gpio_timing_init(void) { return 0; }
static inline void rdd2_gpio_timing_begin(void) {}
static inline void rdd2_gpio_timing_end(void) {}
#endif

#endif /* RDD2_GPIO_TIMING_H_ */
