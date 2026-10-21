/*
 * e2Sim - runner: operating system layer (MIT)
 *
 * Everything the runner needs from the OS: fibers, firmware library, shared blocks, memory checks, hang
 * monitor. e2sim_os_win.c (Windows: fibers, DLL, file mappings) and e2sim_os_posix.c (Linux: ucontext, dlopen,
 * mmap of files).
 */
#ifndef E2SIM_OS_H
#define E2SIM_OS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define OS_PATH_MAX 1024

typedef void (*os_fiber_fn_t)(void);

/* fibers: the calling thread is the scheduler; one application fiber at a time */
void os_fiber_init(void);
void *os_fiber_create(size_t stack_size, os_fiber_fn_t fn);
void os_fiber_to_app(void *fiber); /* scheduler -> application */
void os_fiber_to_sched(void);      /* application -> scheduler */
void os_fiber_delete(void *fiber);

/* firmware library */
void *os_lib_load(const char *path, char *err, size_t err_size);
void *os_lib_sym(void *lib, const char *name);
void os_lib_unload(void *lib);
uint64_t os_lib_base(void *lib);      /* load address */
uint64_t os_lib_link_base(void *lib); /* link address of the image (PE ImageBase, 0 for an ELF .so) */

/* shared block: file (path) or anonymous shared memory named after the process; name: what the host opens */
void *os_block_map(uint16_t idx, const char *path, size_t size, char *name, size_t name_size, bool *fresh,
                   void **handle);
void os_block_flush(void *view, size_t size, void *handle);
void os_block_release(void *handle); /* end of the process: removal of an anonymous block */

/* misc */
bool os_mem_valid(uintptr_t addr, size_t size, bool write);
uint32_t os_pid(void);
void os_full_path(char *path, size_t size);
uint32_t os_tick_ms(void);
void os_sleep_ms(uint32_t ms);
bool os_debugger_present(void);
void os_thread_start(void (*fn)(void));
void os_main_thread_init(void);                            /* called by the main thread */
unsigned os_main_stack(uint64_t *pcs, unsigned max_frames); /* stack of the main thread, from another thread */
void os_exit_now(int code);

#endif /* E2SIM_OS_H */
