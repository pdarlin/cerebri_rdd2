/* SPDX-License-Identifier: Apache-2.0 */
#ifndef RDD2_IMU_GPIO_TIMING_H_
#define RDD2_IMU_GPIO_TIMING_H_

#if defined(CONFIG_RDD2_GPIO_TIMING)
#include <stdint.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

/* Only the selected, single hardware IMU may drive CH2. */
BUILD_ASSERT(DT_NUM_INST_STATUS_OKAY(invensense_icm45686) == 1);
BUILD_ASSERT(DT_SAME_NODE(DT_ALIAS(imu0), DT_INST(0, invensense_icm45686)));

struct rdd2_imu_gpio_timing_state {
  const void *owner;
  uintptr_t generation;
  atomic_t aborted;
  atomic_t ignored;
};

extern struct rdd2_imu_gpio_timing_state g_rdd2_imu_gpio_timing;

static const struct gpio_dt_spec rdd2_imu_acquisition_gpio =
    GPIO_DT_SPEC_GET(DT_NODELABEL(rdd2_timing), imu_gpios);

/* Called only after the driver's ON -> BUSY transition has succeeded. */
static inline void *rdd2_imu_gpio_timing_begin(void)
{
  /* Multishot RTIO can reuse an SQE address. Give each accepted read a token
   * that survives in its callback userdata, including across stream recovery.
   * This opaque value is compared only; it is never dereferenced.
   */
  if (++g_rdd2_imu_gpio_timing.generation == 0U) {
    ++g_rdd2_imu_gpio_timing.generation;
  }
  void *owner = (void *)g_rdd2_imu_gpio_timing.generation;

  g_rdd2_imu_gpio_timing.owner = owner;
  (void)gpio_pin_set_dt(&rdd2_imu_acquisition_gpio, 1);
  return owner;
}

/* The completion callback carries the token captured when this read was submitted.
 * A stale/nonmatching completion must not lower another acquisition's pulse.
 */
static inline void rdd2_imu_gpio_timing_finish(const void *owner, bool success)
{
  if (owner != NULL && owner == g_rdd2_imu_gpio_timing.owner) {
    (void)gpio_pin_set_dt(&rdd2_imu_acquisition_gpio, 0);
    g_rdd2_imu_gpio_timing.owner = NULL;
    if (!success) {
      atomic_inc(&g_rdd2_imu_gpio_timing.aborted);
    }
  }
}

static inline void rdd2_imu_gpio_timing_ignored(void)
{
  atomic_inc(&g_rdd2_imu_gpio_timing.ignored);
}

/* Recovery is outside the normal sample path. Clear before cancellation/restart,
 * with interrupts masked so an ISR cannot start a pulse halfway through cleanup.
 */
static inline void rdd2_imu_gpio_timing_abort(void)
{
  unsigned int key = irq_lock();

  rdd2_imu_gpio_timing_finish(g_rdd2_imu_gpio_timing.owner, false);
  irq_unlock(key);
}
#else
static inline void rdd2_imu_gpio_timing_abort(void) {}
#endif

#endif /* RDD2_IMU_GPIO_TIMING_H_ */
