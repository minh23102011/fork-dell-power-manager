#define _GNU_SOURCE
#include <errno.h>
#include <linux/perf_event.h>
#include <stdint.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

int powerdeck_perf_open(uint32_t type, uint64_t config, int cpu) {
    struct perf_event_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.type = type;
    attr.size = sizeof(attr);
    attr.config = config;
    attr.disabled = 0;
    attr.exclude_kernel = 0;
    attr.exclude_hv = 0;

    return (int)syscall(
        __NR_perf_event_open,
        &attr,
        -1,
        cpu,
        -1,
        PERF_FLAG_FD_CLOEXEC
    );
}

int powerdeck_perf_read(int fd, uint64_t *value) {
    if (value == NULL) {
        errno = EINVAL;
        return -1;
    }

    const ssize_t count = read(fd, value, sizeof(*value));
    return count == (ssize_t)sizeof(*value) ? 0 : -1;
}
