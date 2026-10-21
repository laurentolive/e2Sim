/*
 * e2Sim - runner: operating system layer, Windows (MIT)
 */
#ifdef _WIN32

#define __USE_MINGW_ANSI_STDIO 1
#include <windows.h>

#include <stdio.h>
#include <string.h>

#include "e2sim_os.h"

static void *s_sched;
static HANDLE s_main_thread;
static os_fiber_fn_t s_fn;

/*----------------------------------------------------------------------------*/
void os_fiber_init(void)
{
    s_sched = ConvertThreadToFiber(NULL);
}

static void WINAPI fiber_entry(void *arg)
{
    ((os_fiber_fn_t)arg)();
}

void *os_fiber_create(size_t stack_size, os_fiber_fn_t fn)
{
    s_fn = fn;
    return CreateFiber(stack_size, fiber_entry, (void *)fn);
}

void os_fiber_to_app(void *fiber) { SwitchToFiber(fiber); }

void os_fiber_to_sched(void) { SwitchToFiber(s_sched); }

void os_fiber_delete(void *fiber) { DeleteFiber(fiber); }

/*----------------------------------------------------------------------------*/
void *os_lib_load(const char *path, char *err, size_t err_size)
{
    HMODULE h = LoadLibraryA(path);
    if (h == NULL)
    {
        snprintf(err, err_size, "error %lu", GetLastError());
    }
    return h;
}

void *os_lib_sym(void *lib, const char *name) { return (void *)GetProcAddress((HMODULE)lib, name); }

void os_lib_unload(void *lib) { FreeLibrary((HMODULE)lib); }

uint64_t os_lib_base(void *lib) { return (uint64_t)(uintptr_t)lib; }

uint64_t os_lib_link_base(void *lib)
{
    const uint8_t *base = lib;
    const IMAGE_DOS_HEADER *dos = (const IMAGE_DOS_HEADER *)base;
    const IMAGE_NT_HEADERS *nt = (const IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    return (uint64_t)nt->OptionalHeader.ImageBase;
}

/*----------------------------------------------------------------------------*/
typedef struct
{
    HANDLE file;
    HANDLE mapping;
} win_block_t;

void *os_block_map(uint16_t idx, const char *path, size_t size, char *name, size_t name_size, bool *fresh,
                   void **handle)
{
    static win_block_t blocks[32];
    static unsigned n;
    if (n >= 32u)
    {
        return NULL;
    }
    win_block_t *b = &blocks[n++];
    snprintf(name, name_size, "Local\\e2sim_%lu_%u", GetCurrentProcessId(), idx);
    HANDLE file = INVALID_HANDLE_VALUE;
    *fresh = true;
    if ((path != NULL) && (path[0] != '\0'))
    {
        file = CreateFileA(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                           OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (file == INVALID_HANDLE_VALUE)
        {
            return NULL;
        }
        LARGE_INTEGER cur;
        GetFileSizeEx(file, &cur);
        *fresh = ((uint64_t)cur.QuadPart < size);
    }
    b->file = (file == INVALID_HANDLE_VALUE) ? NULL : file;
    b->mapping = CreateFileMappingA(file, NULL, PAGE_READWRITE, (DWORD)((uint64_t)size >> 32), (DWORD)size, name);
    if (b->mapping == NULL)
    {
        return NULL;
    }
    *handle = b;
    return MapViewOfFile(b->mapping, FILE_MAP_ALL_ACCESS, 0, 0, size);
}

void os_block_flush(void *view, size_t size, void *handle)
{
    (void)size;
    if ((handle != NULL) && (((win_block_t *)handle)->file != NULL))
    {
        FlushViewOfFile(view, 0);
    }
}

void os_block_release(void *handle) { (void)handle; /* named mappings end with the process */ }

/*----------------------------------------------------------------------------*/
bool os_mem_valid(uintptr_t addr, size_t size, bool write)
{
    DWORD ok = write ? (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)
                     : (PAGE_READONLY | PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READ |
                        PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY);
    uintptr_t end = addr + size;
    if ((size == 0u) || (end < addr))
    {
        return false;
    }
    while (addr < end)
    {
        MEMORY_BASIC_INFORMATION mbi;
        if (VirtualQuery((const void *)addr, &mbi, sizeof(mbi)) == 0)
        {
            return false;
        }
        if ((mbi.State != MEM_COMMIT) || ((mbi.Protect & ok) == 0u) || ((mbi.Protect & PAGE_GUARD) != 0u))
        {
            return false;
        }
        addr = (uintptr_t)mbi.BaseAddress + mbi.RegionSize;
    }
    return true;
}

uint32_t os_pid(void) { return (uint32_t)GetCurrentProcessId(); }

void os_full_path(char *path, size_t size)
{
    char full[MAX_PATH];
    if (GetFullPathNameA(path, sizeof(full), full, NULL) != 0)
    {
        snprintf(path, size, "%s", full);
    }
}

uint32_t os_tick_ms(void) { return (uint32_t)GetTickCount(); }

void os_sleep_ms(uint32_t ms) { Sleep(ms); }

bool os_debugger_present(void) { return IsDebuggerPresent() != 0; }

static DWORD WINAPI thread_entry(void *arg)
{
    ((void (*)(void))arg)();
    return 0;
}

void os_thread_start(void (*fn)(void)) { CreateThread(NULL, 0, thread_entry, (void *)fn, 0, NULL); }

void os_main_thread_init(void)
{
    DuplicateHandle(GetCurrentProcess(), GetCurrentThread(), GetCurrentProcess(), &s_main_thread, 0, FALSE,
                    DUPLICATE_SAME_ACCESS);
}

unsigned os_main_stack(uint64_t *pcs, unsigned max_frames)
{
    SuspendThread(s_main_thread);
    CONTEXT ctx __attribute__((aligned(16)));
    memset(&ctx, 0, sizeof(ctx));
    ctx.ContextFlags = CONTEXT_FULL;
    unsigned n = 0;
    if (!GetThreadContext(s_main_thread, &ctx))
    {
        return 0;
    }
#if defined(__x86_64__)
    /* x64: unwind tables of the PE (the frame pointer chain is not reliable) */
    while ((n < max_frames) && (ctx.Rip != 0u))
    {
        pcs[n] = (n == 0u) ? ctx.Rip : ctx.Rip - 1u; /* return address: inside the call */
        n++;
        DWORD64 base;
        PRUNTIME_FUNCTION fn = RtlLookupFunctionEntry(ctx.Rip, &base, NULL);
        if (fn == NULL)
        {
            if (!os_mem_valid((uintptr_t)ctx.Rsp, 8u, false))
            {
                break;
            }
            ctx.Rip = *(DWORD64 *)ctx.Rsp; /* leaf function */
            ctx.Rsp += 8u;
        }
        else
        {
            PVOID handler;
            DWORD64 frame;
            RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, ctx.Rip, fn, &ctx, &handler, &frame, NULL);
        }
    }
#else
    uintptr_t fp = (uintptr_t)ctx.Ebp;
    pcs[n++] = (uintptr_t)ctx.Eip;
    while ((n < max_frames) && (fp != 0u) && os_mem_valid(fp, 2u * sizeof(void *), false))
    {
        uintptr_t ret = ((uintptr_t *)fp)[1];
        uintptr_t next = ((uintptr_t *)fp)[0];
        if (ret == 0u)
        {
            break;
        }
        pcs[n++] = ret - 1u; /* inside the call instruction */
        if (next <= fp)
        {
            break;
        }
        fp = next;
    }
#endif
    return n;
}

void os_exit_now(int code) { ExitProcess((UINT)code); }

#endif /* _WIN32 */
