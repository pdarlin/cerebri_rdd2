"""Host checks for CH2 ownership and exceptional-path cleanup.

Run: python3 tests/test_gpio_timing.py
Requires a host C compiler (cc); no Zephyr toolchain or hardware required.
The real inline marker code is compiled against recording GPIO/kernel stubs.
"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AcquisitionPairing(unittest.TestCase):
    def test_disabled_headers_need_no_gpio_or_zephyr_symbols(self):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "Install a host C compiler to run this test")
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source = work / "disabled.c"
            source.write_text('''
#include "gpio_timing.h"
#include "imu_gpio_timing.h"
int main(void) {
    rdd2_gpio_timing_begin();
    rdd2_gpio_timing_end();
    rdd2_imu_gpio_timing_abort();
    return rdd2_gpio_timing_init();
}
''')
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                "-I", str(ROOT / "src"), str(source), "-o", str(work / "disabled"),
            ], check=True)
            subprocess.run([str(work / "disabled")], check=True)

    def test_marker_lifecycle(self):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "Install a host C compiler to run this test")
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            files = {
                "zephyr/drivers/gpio.h": """
#include <stddef.h>
#include <stdbool.h>
struct gpio_dt_spec { int unused; };
#define GPIO_DT_SPEC_GET(node, prop) {0}
#define DT_NUM_INST_STATUS_OKAY(compat) 1
#define DT_SAME_NODE(a, b) 1
extern unsigned int gpio_writes;
extern int gpio_level;
static inline int gpio_pin_set_dt(const struct gpio_dt_spec *spec, int value)
{ (void)spec; gpio_writes++; gpio_level = value; return 0; }
""",
                "zephyr/kernel.h": """
#define BUILD_ASSERT(cond) _Static_assert(cond, #cond)
static inline unsigned int irq_lock(void) { return 0; }
static inline void irq_unlock(unsigned int key) { (void)key; }
""",
                "zephyr/sys/atomic.h": """
typedef long atomic_t;
static inline long atomic_inc(atomic_t *value) { return (*value)++; }
""",
                "pairing.c": """
#include <assert.h>
#include "imu_gpio_timing.h"
struct rdd2_imu_gpio_timing_state g_rdd2_imu_gpio_timing;
unsigned int gpio_writes;
int gpio_level;
int main(void)
{
    void *request_a;
    void *request_b = (void *)99;
    /* No active acquisition: cleanup does not invent a falling edge. */
    rdd2_imu_gpio_timing_finish(NULL, false);
    rdd2_imu_gpio_timing_abort();
    assert(gpio_writes == 0);
    request_a = rdd2_imu_gpio_timing_begin();
    assert(gpio_level == 1 && gpio_writes == 1);
    /* Ignored IRQ and stale completion leave this acquisition HIGH. */
    rdd2_imu_gpio_timing_ignored();
    rdd2_imu_gpio_timing_finish(request_b, true);
    assert(gpio_level == 1 && gpio_writes == 1);
    assert(g_rdd2_imu_gpio_timing.ignored == 1);
    rdd2_imu_gpio_timing_finish(request_a, true);
    assert(gpio_level == 0 && gpio_writes == 2);
    assert(g_rdd2_imu_gpio_timing.owner == NULL);
    assert(g_rdd2_imu_gpio_timing.aborted == 0);
    /* Repeated cleanup after success must neither toggle nor abort. */
    rdd2_imu_gpio_timing_finish(request_a, false);
    assert(gpio_writes == 2 && g_rdd2_imu_gpio_timing.aborted == 0);
    /* A transfer failure clears once and invalidates the capture. */
    request_b = rdd2_imu_gpio_timing_begin();
    rdd2_imu_gpio_timing_finish(request_b, false);
    assert(gpio_level == 0 && gpio_writes == 4);
    assert(g_rdd2_imu_gpio_timing.aborted == 1);
    /* Recovery clears pending acquisition; an old completion cannot clear B. */
    request_a = rdd2_imu_gpio_timing_begin();
    rdd2_imu_gpio_timing_abort();
    assert(gpio_level == 0 && g_rdd2_imu_gpio_timing.aborted == 2);
    request_b = rdd2_imu_gpio_timing_begin();
    rdd2_imu_gpio_timing_finish(request_a, true);
    assert(gpio_level == 1 && gpio_writes == 7);
    rdd2_imu_gpio_timing_finish(request_b, true);
    assert(gpio_level == 0 && gpio_writes == 8);
    /* Normal multishot reuse still produces a distinct pulse each time. */
    request_a = request_b;
    request_b = rdd2_imu_gpio_timing_begin();
    assert(request_a != request_b);
    rdd2_imu_gpio_timing_finish(request_a, true);
    assert(gpio_writes == 9 && gpio_level == 1);
    rdd2_imu_gpio_timing_finish(request_b, true);
    assert(gpio_writes == 10 && gpio_level == 0);
    g_rdd2_imu_gpio_timing.generation = UINTPTR_MAX;
    request_a = rdd2_imu_gpio_timing_begin();
    assert(request_a != NULL);
    rdd2_imu_gpio_timing_finish(request_a, true);
    return 0;
}
""",
            }
            for name, contents in files.items():
                file = work / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(contents)
            subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-DCONFIG_RDD2_GPIO_TIMING=1", "-I", str(work),
                "-I", str(ROOT / "src"), str(work / "pairing.c"),
                "-o", str(work / "pairing"),
            ], check=True)
            subprocess.run([str(work / "pairing")], check=True)


if __name__ == "__main__":
    unittest.main()
