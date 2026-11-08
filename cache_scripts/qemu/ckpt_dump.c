/*
 * qemu-user plugin: dump the architectural state of a static rv64 Linux
 * program at given instruction counts, for cache_scripts/qemu/qemu2gem5.py to
 * turn into gem5 SE checkpoints (SimPoint checkpoints without running gem5's
 * slow atomic CPU up to every simulation point).
 *
 * Instructions are counted from the program's start exactly like bbv_roi.c,
 * so the counts SimPoint picked from its intervals can be given as they are.
 * A dump is taken at the start of the first translation block at or after
 * each count (a few instructions later at most; the real count is recorded).
 *
 * Arguments: out=<dir> at=<file: one instruction count per line, ascending>
 *            bin=<the guest ELF> [stop=0|1, default 1: exit after the last]
 *            [vdso=0|1, default 0: hide qemu's vDSO from the program, as gem5
 *            has none] [probe=1: print the initial sp and exit, no dumps]
 * Writes <dir>/dump_<k>/ for the k-th count:
 *   info.txt     icount, brk, initial and current sp, guest_base
 *   regs.txt     every register qemu exposes: name, feature, hex bytes (LE);
 *                pc is the block's address (qemu's pc register is stale
 *                inside chained blocks)
 *   regions.txt  the guest's memory areas: kind start end (hex, page aligned)
 *                kinds: elf (PT_LOAD), heap (brk), mmap, stack, vdso
 *   pages.idx    the guest address of every non-zero page, one per line
 *   pages.gz     those pages' contents, 4 KiB each, in the same order (gzip)
 *   fds.txt      open guest files: fd offset flags(octal) path
 *
 * The guest's own memory map is not visible to a plugin, so it is rebuilt:
 * PT_LOAD segments from the ELF, the heap from brk, mmap/munmap/mremap from
 * the syscalls, the stack and vdso from the host mappings that hold the
 * current sp and AT_SYSINFO_EHDR. Guest memory is read through /proc/self/mem
 * at host address guest_base + vaddr (qemu-user maps the guest linearly).
 */
#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <glib.h>
#include <qemu-plugin.h>

QEMU_PLUGIN_EXPORT int qemu_plugin_version = QEMU_PLUGIN_VERSION;

#define PAGE ((uint64_t)4096)
#define PDOWN(a) ((a) & ~(PAGE - 1))
#define PUP(a) (((a) + PAGE - 1) & ~(PAGE - 1))

enum { SYS_dup = 23, SYS_dup3 = 24, SYS_fcntl = 25, SYS_openat = 56, SYS_close = 57,
       SYS_pipe2 = 59, SYS_brk = 214, SYS_munmap = 215, SYS_mremap = 216,
       SYS_mmap = 222 };

typedef struct { uint64_t start, end; } Range;
typedef struct { Range *r; size_t n, cap; } RangeSet;   /* sorted, disjoint */

static char *out_dir;
static char *bin_path;
static int stop_after_last = 1;
static int hide_vdso = 1;
static int probe;                /* print the initial sp and exit */
static uint64_t *targets;
static size_t n_targets, next_target;

static uint64_t icount;
static int64_t guest_base;
static int have_base;
static uint64_t sp0, vdso_base;
static int started;
static uint64_t brk_start, brk_cur;
static RangeSet elf, maps;
static uint8_t fd_open[1024];
static int64_t sc_args[3];
static int memfd = -1;
static GArray *regs;
static GByteArray *regbuf;

/* ---- page ranges ---------------------------------------------------- */

static void rs_remove(RangeSet *s, uint64_t a, uint64_t b)
{
    size_t w = 0;
    Range *tmp = malloc((s->n * 2 + 1) * sizeof(Range));
    for (size_t i = 0; i < s->n; i++) {
        Range r = s->r[i];
        if (r.end <= a || r.start >= b) {
            tmp[w++] = r;
            continue;
        }
        if (r.start < a)
            tmp[w++] = (Range){ r.start, a };
        if (r.end > b)
            tmp[w++] = (Range){ b, r.end };
    }
    free(s->r);
    s->r = tmp;
    s->n = w;
    s->cap = s->n * 2 + 1;
}

static void rs_add(RangeSet *s, uint64_t a, uint64_t b)
{
    if (a >= b)
        return;
    rs_remove(s, a, b);
    if (s->n + 1 > s->cap) {
        s->cap = s->cap * 2 + 4;
        s->r = realloc(s->r, s->cap * sizeof(Range));
    }
    size_t i = 0;
    while (i < s->n && s->r[i].start < a)
        i++;
    memmove(s->r + i + 1, s->r + i, (s->n - i) * sizeof(Range));
    s->r[i] = (Range){ a, b };
    s->n++;
    /* merge neighbours */
    size_t w = 0;
    for (size_t j = 0; j < s->n; j++) {
        if (w && s->r[w - 1].end >= s->r[j].start) {
            if (s->r[j].end > s->r[w - 1].end)
                s->r[w - 1].end = s->r[j].end;
        } else {
            s->r[w++] = s->r[j];
        }
    }
    s->n = w;
}

/* ---- guest memory ---------------------------------------------------- */

static int read_guest(uint64_t vaddr, void *buf, size_t len)
{
    return pread(memfd, buf, len, (off_t)(vaddr + guest_base)) == (ssize_t)len ? 0 : -1;
}

/* host mapping (from /proc/self/maps) holding guest address vaddr */
static int host_region(uint64_t vaddr, uint64_t *start, uint64_t *end)
{
    FILE *f = fopen("/proc/self/maps", "r");
    char line[512];
    uint64_t h = vaddr + guest_base, a, b;
    int found = -1;
    while (f && fgets(line, sizeof(line), f)) {
        if (sscanf(line, "%" SCNx64 "-%" SCNx64, &a, &b) == 2 && h >= a && h < b) {
            *start = a - guest_base;
            *end = b - guest_base;
            found = 0;
            break;
        }
    }
    if (f)
        fclose(f);
    return found;
}

static void load_elf(void)
{
    FILE *f = fopen(bin_path, "rb");
    Elf64_Ehdr eh;
    if (!f || fread(&eh, sizeof(eh), 1, f) != 1) {
        fprintf(stderr, "ckpt_dump: cannot read %s\n", bin_path);
        exit(1);
    }
    for (int i = 0; i < eh.e_phnum; i++) {
        Elf64_Phdr ph;
        fseek(f, eh.e_phoff + (long)i * eh.e_phentsize, SEEK_SET);
        if (fread(&ph, sizeof(ph), 1, f) == 1 && ph.p_type == PT_LOAD)
            rs_add(&elf, PDOWN(ph.p_vaddr), PUP(ph.p_vaddr + ph.p_memsz));
    }
    fclose(f);
}

/* AT_SYSINFO_EHDR from the initial stack: argc, argv..., 0, envp..., 0, auxv */
static void read_auxv(void)
{
    uint64_t p = sp0, v, argc;
    if (read_guest(p, &argc, 8))
        return;
    p += 8 * (argc + 2);
    do {
        if (read_guest(p, &v, 8))
            return;
        p += 8;
    } while (v);
    for (int i = 0; i < 64; i++, p += 16) {
        uint64_t av[2];
        if (read_guest(p, av, 16) || av[0] == AT_NULL)
            return;
        if (av[0] == AT_SYSINFO_EHDR) {
            vdso_base = av[1];
            /* gem5 gives no vDSO. Hidden from glibc, the program allocates
             * and runs as under gem5: no link_map for the vDSO on the heap,
             * time calls as plain syscalls. */
            if (hide_vdso)
                *(uint64_t *)(uintptr_t)(p + guest_base) = AT_IGNORE;
        }
    }
}

/* ---- dump ------------------------------------------------------------ */

static void write_regs(const char *dir, uint64_t pc)
{
    char path[4400];
    snprintf(path, sizeof(path), "%s/regs.txt", dir);
    FILE *f = fopen(path, "w");
    for (guint i = 0; i < regs->len; i++) {
        qemu_plugin_reg_descriptor *d = &((qemu_plugin_reg_descriptor *)regs->data)[i];
        g_byte_array_set_size(regbuf, 0);
        int n = qemu_plugin_read_register(d->handle, regbuf);
        if (n <= 0)
            continue;
        if (!strcmp(d->name, "pc") && n == 8)
            memcpy(regbuf->data, &pc, 8);
        fprintf(f, "%s %s ", d->name, d->feature ? d->feature : "-");
        for (int j = 0; j < n; j++)
            fprintf(f, "%02x", regbuf->data[j]);
        fputc('\n', f);
    }
    fclose(f);
}

static void dump_pages(const char *dir, RangeSet *all)
{
    char path[4400], cmd[4400];
    snprintf(path, sizeof(path), "%s/pages.idx", dir);
    FILE *idx = fopen(path, "w");
    snprintf(cmd, sizeof(cmd), "gzip -1 > '%s/pages.gz'", dir);
    FILE *gz = popen(cmd, "w");
    static uint64_t buf[PAGE / 8];
    for (size_t i = 0; i < all->n; i++) {
        for (uint64_t a = all->r[i].start; a < all->r[i].end; a += PAGE) {
            if (read_guest(a, buf, PAGE))
                continue;               /* not readable (guard page): absent */
            int zero = 1;
            for (size_t j = 0; j < PAGE / 8 && zero; j++)
                zero = buf[j] == 0;
            if (zero)
                continue;               /* gem5 maps zero pages lazily */
            fprintf(idx, "%" PRIx64 "\n", a);
            fwrite(buf, PAGE, 1, gz);
        }
    }
    fclose(idx);
    if (pclose(gz) != 0) {
        fprintf(stderr, "ckpt_dump: gzip failed for %s\n", dir);
        exit(1);
    }
}

static void write_fds(const char *dir)
{
    char path[4400];
    snprintf(path, sizeof(path), "%s/fds.txt", dir);
    FILE *f = fopen(path, "w");
    for (int fd = 0; fd < 1024; fd++) {
        if (fd > 2 && !fd_open[fd])
            continue;
        char link[64], target[4096], info[64], line[256];
        snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
        ssize_t n = readlink(link, target, sizeof(target) - 1);
        if (n < 0)
            continue;
        target[n] = 0;
        uint64_t pos = 0;
        unsigned flags = 0;
        snprintf(info, sizeof(info), "/proc/self/fdinfo/%d", fd);
        FILE *fi = fopen(info, "r");
        while (fi && fgets(line, sizeof(line), fi)) {
            sscanf(line, "pos: %" SCNu64, &pos);
            sscanf(line, "flags: %o", &flags);
        }
        if (fi)
            fclose(fi);
        fprintf(f, "%d %" PRIu64 " %o %s\n", fd, pos, flags, target);
    }
    fclose(f);
}

static void dump(size_t k, uint64_t pc)
{
    char dir[4096], tmp[4200], path[4300];
    snprintf(dir, sizeof(dir), "%s/dump_%02zu", out_dir, k);
    snprintf(tmp, sizeof(tmp), "%s.tmp", dir);
    mkdir(tmp, 0775);

    uint64_t sp = 0, st_lo = 0, st_hi = 0, vd_lo = 0, vd_hi = 0;
    write_regs(tmp, pc);
    /* sp is x2: the third register of the cpu feature */
    for (guint i = 0; i < regs->len; i++) {
        qemu_plugin_reg_descriptor *d = &((qemu_plugin_reg_descriptor *)regs->data)[i];
        if (!strcmp(d->name, "sp")) {
            g_byte_array_set_size(regbuf, 0);
            if (qemu_plugin_read_register(d->handle, regbuf) == 8)
                memcpy(&sp, regbuf->data, 8);
        }
    }
    RangeSet all = { 0 };
    for (size_t i = 0; i < elf.n; i++)
        rs_add(&all, elf.r[i].start, elf.r[i].end);
    if (brk_cur > brk_start)
        rs_add(&all, PDOWN(brk_start), PUP(brk_cur));
    for (size_t i = 0; i < maps.n; i++)
        rs_add(&all, maps.r[i].start, maps.r[i].end);
    if (host_region(sp, &st_lo, &st_hi) == 0)
        rs_add(&all, st_lo, st_hi);
    if (vdso_base && host_region(vdso_base, &vd_lo, &vd_hi) == 0)
        rs_add(&all, vd_lo, vd_hi);

    snprintf(path, sizeof(path), "%s/regions.txt", tmp);
    FILE *f = fopen(path, "w");
    for (size_t i = 0; i < elf.n; i++)
        fprintf(f, "elf %" PRIx64 " %" PRIx64 "\n", elf.r[i].start, elf.r[i].end);
    if (brk_cur > brk_start)
        fprintf(f, "heap %" PRIx64 " %" PRIx64 "\n", PDOWN(brk_start), PUP(brk_cur));
    for (size_t i = 0; i < maps.n; i++)
        fprintf(f, "mmap %" PRIx64 " %" PRIx64 "\n", maps.r[i].start, maps.r[i].end);
    if (st_hi)
        fprintf(f, "stack %" PRIx64 " %" PRIx64 "\n", st_lo, st_hi);
    if (vd_hi)
        fprintf(f, "vdso %" PRIx64 " %" PRIx64 "\n", vd_lo, vd_hi);
    fclose(f);

    dump_pages(tmp, &all);
    free(all.r);
    write_fds(tmp);

    snprintf(path, sizeof(path), "%s/info.txt", tmp);
    f = fopen(path, "w");
    fprintf(f, "target %" PRIu64 "\nicount %" PRIu64 "\nbrk_start %" PRIx64 "\n"
            "brk %" PRIx64 "\nsp0 %" PRIx64 "\nsp %" PRIx64 "\nguest_base %" PRIx64 "\n",
            targets[k], icount, brk_start, brk_cur, sp0, sp, (uint64_t)guest_base);
    fclose(f);
    rename(tmp, dir);
    fprintf(stderr, "ckpt_dump: dump %zu at %" PRIu64 " instructions\n", k, icount);
}

/* ---- callbacks ------------------------------------------------------- */

typedef struct { uint64_t n_insns, pc; } TB;

static void tb_exec(unsigned int vcpu, void *udata)
{
    TB *tb = udata;
    if (!started) {
        started = 1;
        for (guint i = 0; i < regs->len; i++) {
            qemu_plugin_reg_descriptor *d = &((qemu_plugin_reg_descriptor *)regs->data)[i];
            if (!strcmp(d->name, "sp")) {
                g_byte_array_set_size(regbuf, 0);
                if (qemu_plugin_read_register(d->handle, regbuf) == 8)
                    memcpy(&sp0, regbuf->data, 8);
            }
        }
        read_auxv();
        if (probe) {
            printf("sp0 %" PRIx64 "\n", sp0);
            fflush(stdout);
            _exit(0);
        }
    }
    while (next_target < n_targets && icount >= targets[next_target]) {
        dump(next_target++, tb->pc);
        if (next_target == n_targets && stop_after_last) {
            fflush(NULL);
            _exit(0);
        }
    }
    icount += tb->n_insns;
}

static void tb_trans(qemu_plugin_id_t id, struct qemu_plugin_tb *tb)
{
    size_t n = qemu_plugin_tb_n_insns(tb);
    if (!have_base && n) {
        struct qemu_plugin_insn *insn = qemu_plugin_tb_get_insn(tb, 0);
        guest_base = (int64_t)(uintptr_t)qemu_plugin_insn_haddr(insn) -
                     (int64_t)qemu_plugin_insn_vaddr(insn);
        have_base = 1;
    }
    /* The pc register reads stale inside chained blocks (qemu 9.0 updates it
     * only when leaving them), so a block's own address is the pc. */
    TB *t = malloc(sizeof(TB));
    t->n_insns = n;
    t->pc = qemu_plugin_tb_vaddr(tb);
    qemu_plugin_register_vcpu_tb_exec_cb(tb, tb_exec, QEMU_PLUGIN_CB_R_REGS, t);
}

static void vcpu_init(qemu_plugin_id_t id, unsigned int vcpu)
{
    regs = qemu_plugin_get_registers();
    regbuf = g_byte_array_new();
}

static void syscall_in(qemu_plugin_id_t id, unsigned int vcpu, int64_t num,
                       uint64_t a1, uint64_t a2, uint64_t a3, uint64_t a4,
                       uint64_t a5, uint64_t a6, uint64_t a7, uint64_t a8)
{
    sc_args[0] = a1;
    sc_args[1] = a2;
    sc_args[2] = a3;
}

static void syscall_ret(qemu_plugin_id_t id, unsigned int vcpu, int64_t num, int64_t ret)
{
    int ok = ret >= 0 || ret < -4095;
    switch (num) {
    case SYS_brk:
        if (!brk_start)
            brk_start = ret;
        brk_cur = ret;
        break;
    case SYS_mmap:
        if (ok)
            rs_add(&maps, PDOWN((uint64_t)ret), PUP((uint64_t)ret + sc_args[1]));
        break;
    case SYS_munmap:
        if (ret == 0)
            rs_remove(&maps, PDOWN(sc_args[0]), PUP(sc_args[0] + sc_args[1]));
        break;
    case SYS_mremap:
        if (ok) {
            rs_remove(&maps, PDOWN(sc_args[0]), PUP(sc_args[0] + sc_args[1]));
            rs_add(&maps, PDOWN((uint64_t)ret), PUP((uint64_t)ret + sc_args[2]));
        }
        break;
    case SYS_openat:
    case SYS_dup:
    case SYS_dup3:
        if (ret >= 0 && ret < 1024)
            fd_open[ret] = 1;
        break;
    case SYS_fcntl:   /* F_DUPFD, F_DUPFD_CLOEXEC */
        if ((sc_args[1] == 0 || sc_args[1] == 1030) && ret >= 0 && ret < 1024)
            fd_open[ret] = 1;
        break;
    case SYS_close:
        if (ret == 0 && sc_args[0] < 1024)
            fd_open[sc_args[0]] = 0;
        break;
    case SYS_pipe2:
        if (ret == 0)
            fprintf(stderr, "ckpt_dump: warning: pipe2 used, pipes are not dumped\n");
        break;
    }
}

QEMU_PLUGIN_EXPORT int qemu_plugin_install(qemu_plugin_id_t id,
                                           const qemu_info_t *info,
                                           int argc, char **argv)
{
    char *at = NULL;
    for (int i = 0; i < argc; i++) {
        if (!strncmp(argv[i], "out=", 4))
            out_dir = strdup(argv[i] + 4);
        else if (!strncmp(argv[i], "at=", 3))
            at = strdup(argv[i] + 3);
        else if (!strncmp(argv[i], "bin=", 4))
            bin_path = strdup(argv[i] + 4);
        else if (!strncmp(argv[i], "stop=", 5))
            stop_after_last = atoi(argv[i] + 5);
        else if (!strncmp(argv[i], "vdso=", 5))
            hide_vdso = !atoi(argv[i] + 5);
        else if (!strncmp(argv[i], "probe=", 6))
            probe = atoi(argv[i] + 6);
    }
    if (probe && !at)
        at = "/dev/null";
    if (!out_dir)
        out_dir = probe ? "/dev/null" : NULL;
    if (!out_dir || !at || !bin_path) {
        fprintf(stderr, "ckpt_dump: need out=, at= and bin=\n");
        return -1;
    }
    FILE *f = fopen(at, "r");
    uint64_t v;
    size_t cap = 0;
    while (f && fscanf(f, "%" SCNu64, &v) == 1) {
        if (n_targets == cap) {
            cap = cap * 2 + 16;
            targets = realloc(targets, cap * sizeof(uint64_t));
        }
        targets[n_targets++] = v;
    }
    if (f)
        fclose(f);
    if (!n_targets && !probe) {
        fprintf(stderr, "ckpt_dump: no instruction counts in %s\n", at);
        return -1;
    }
    memfd = open("/proc/self/mem", O_RDONLY);
    if (memfd < 0) {
        fprintf(stderr, "ckpt_dump: cannot open /proc/self/mem\n");
        return -1;
    }
    if (!probe)
        mkdir(out_dir, 0775);
    load_elf();
    for (int fd = 0; fd < 3; fd++)
        fd_open[fd] = 1;
    qemu_plugin_register_vcpu_init_cb(id, vcpu_init);
    qemu_plugin_register_vcpu_tb_trans_cb(id, tb_trans);
    qemu_plugin_register_vcpu_syscall_cb(id, syscall_in);
    qemu_plugin_register_vcpu_syscall_ret_cb(id, syscall_ret);
    return 0;
}
