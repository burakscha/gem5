/*
 * qemu-user plugin: basic block vectors (BBVs) of the region of interest, in
 * SimPoint's frequency-vector format, for cache_scripts/simpoint.sh.
 *
 * Instructions are counted from the program's start and cut into intervals
 * of `interval` instructions: interval k is [k * interval, (k + 1) * interval).
 * Only intervals that lie entirely between m5_work_begin and m5_work_end are
 * written, so a SimPoint index i in the .bb file is interval first_interval + i
 * of the whole run, which is where gem5 must take its checkpoint. m5ops do not
 * exist in qemu: the binary runs as a copy whose m5ops are NOPs, and the ROI is
 * recognised by executing the entry of the m5_work_begin / m5_work_end
 * functions (their addresses are passed as begin= and end=).
 *
 * Arguments: out=<prefix> interval=<n> begin=<hex pc> end=<hex pc>
 * Writes <prefix>.bb (one "T:id:count ..." line per interval, count = executed
 * instructions of the block in that interval) and <prefix>.info (key value).
 */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <qemu-plugin.h>

QEMU_PLUGIN_EXPORT int qemu_plugin_version = QEMU_PLUGIN_VERSION;

typedef struct {
    uint32_t id;       /* 1-based block id (SimPoint ids start at 1) */
    uint32_t n_insns;
} Block;

static char *out_prefix = "bbv";
static uint64_t interval = 100000000ULL;
static uint64_t begin_pc, end_pc;

static uint64_t icount;          /* instructions executed so far */
static uint64_t cur_interval;    /* index of the interval icount is in */
static int in_roi, roi_seen;
static uint64_t roi_begin = UINT64_MAX, roi_end = UINT64_MAX;
static uint64_t first_written = UINT64_MAX, written;
static int interval_clean = 1;   /* ROI covered the whole current interval */

/* block id -> instructions executed in the current interval */
static uint64_t *counts;
static uint32_t counts_cap, n_blocks;
static uint32_t *touched;        /* ids with a nonzero count this interval */
static uint32_t n_touched, touched_cap;

/* vaddr -> Block, open addressing (no glib on this host) */
static uint64_t *keys;
static Block **vals;
static uint64_t table_cap = 1 << 20, table_used;
static FILE *bb;

static Block *lookup(uint64_t vaddr, uint32_t n_insns)
{
    uint64_t key = (vaddr << 8) | (n_insns & 0xff);
    uint64_t h = (key * 0x9E3779B97F4A7C15ULL) & (table_cap - 1);
    while (keys[h] && keys[h] != key)
        h = (h + 1) & (table_cap - 1);
    if (keys[h])
        return vals[h];
    if (++table_used * 2 > table_cap) {
        fprintf(stderr, "bbv_roi: block table full\n");
        exit(1);
    }
    Block *b = malloc(sizeof(Block));
    b->id = ++n_blocks;
    b->n_insns = n_insns;
    keys[h] = key;
    vals[h] = b;
    if (n_blocks >= counts_cap) {
        counts_cap *= 2;
        counts = realloc(counts, counts_cap * sizeof(uint64_t));
        memset(counts + counts_cap / 2, 0, counts_cap / 2 * sizeof(uint64_t));
    }
    return b;
}

static void flush_interval(void)
{
    /* Write the finished interval if the ROI covered all of it. */
    if (interval_clean && in_roi && n_touched) {
        if (first_written == UINT64_MAX)
            first_written = cur_interval;
        if (cur_interval == first_written + written) {
            fputc('T', bb);
            for (uint32_t i = 0; i < n_touched; i++)
                fprintf(bb, ":%u:%" PRIu64 " ", touched[i], counts[touched[i]]);
            fputc('\n', bb);
            written++;
        }
    }
    for (uint32_t i = 0; i < n_touched; i++)
        counts[touched[i]] = 0;
    n_touched = 0;
    interval_clean = in_roi;
}

static void tb_exec(unsigned int vcpu, void *udata)
{
    Block *b = udata;
    uint64_t next = icount + b->n_insns;
    if (next / interval != cur_interval) {
        flush_interval();
        cur_interval = next / interval;
    }
    icount = next;
    if (in_roi) {
        if (counts[b->id] == 0) {
            if (n_touched == touched_cap) {
                touched_cap *= 2;
                touched = realloc(touched, touched_cap * sizeof(uint32_t));
            }
            touched[n_touched++] = b->id;
        }
        counts[b->id] += b->n_insns;
    }
}

static void roi_marker(unsigned int vcpu, void *udata)
{
    if (udata == (void *)1 && !in_roi) {
        in_roi = 1;
        roi_seen = 1;
        roi_begin = icount;
        interval_clean = 0;        /* the ROI starts inside this interval */
    } else if (udata == (void *)2 && in_roi) {
        interval_clean = 0;        /* the ROI ends inside this interval */
        in_roi = 0;
        roi_end = icount;
        for (uint32_t i = 0; i < n_touched; i++)
            counts[touched[i]] = 0;
        n_touched = 0;
    }
}

static void tb_trans(qemu_plugin_id_t id, struct qemu_plugin_tb *tb)
{
    size_t n = qemu_plugin_tb_n_insns(tb);
    Block *b = lookup(qemu_plugin_tb_vaddr(tb), n);
    qemu_plugin_register_vcpu_tb_exec_cb(tb, tb_exec, QEMU_PLUGIN_CB_NO_REGS, b);
    for (size_t i = 0; i < n; i++) {
        struct qemu_plugin_insn *insn = qemu_plugin_tb_get_insn(tb, i);
        uint64_t pc = qemu_plugin_insn_vaddr(insn);
        if (pc == begin_pc)
            qemu_plugin_register_vcpu_insn_exec_cb(insn, roi_marker,
                                                   QEMU_PLUGIN_CB_NO_REGS, (void *)1);
        else if (pc == end_pc)
            qemu_plugin_register_vcpu_insn_exec_cb(insn, roi_marker,
                                                   QEMU_PLUGIN_CB_NO_REGS, (void *)2);
    }
}

static void plugin_exit(qemu_plugin_id_t id, void *p)
{
    if (in_roi)          /* a run that never reached m5_work_end */
        roi_end = icount;
    fclose(bb);
    char path[4096];
    snprintf(path, sizeof(path), "%s.info", out_prefix);
    FILE *f = fopen(path, "w");
    if (!f)
        return;
    fprintf(f, "interval %" PRIu64 "\n", interval);
    fprintf(f, "total_insts %" PRIu64 "\n", icount);
    fprintf(f, "roi_seen %d\n", roi_seen);
    fprintf(f, "roi_begin_inst %" PRIu64 "\n", roi_begin == UINT64_MAX ? 0 : roi_begin);
    fprintf(f, "roi_end_inst %" PRIu64 "\n", roi_end == UINT64_MAX ? 0 : roi_end);
    fprintf(f, "first_interval %" PRIu64 "\n", first_written == UINT64_MAX ? 0 : first_written);
    fprintf(f, "intervals %" PRIu64 "\n", written);
    fprintf(f, "blocks %u\n", n_blocks);
    fclose(f);
}

QEMU_PLUGIN_EXPORT int qemu_plugin_install(qemu_plugin_id_t id,
                                           const qemu_info_t *info,
                                           int argc, char **argv)
{
    for (int i = 0; i < argc; i++) {
        if (!strncmp(argv[i], "out=", 4))
            out_prefix = strdup(argv[i] + 4);
        else if (!strncmp(argv[i], "interval=", 9))
            interval = strtoull(argv[i] + 9, NULL, 0);
        else if (!strncmp(argv[i], "begin=", 6))
            begin_pc = strtoull(argv[i] + 6, NULL, 16);
        else if (!strncmp(argv[i], "end=", 4))
            end_pc = strtoull(argv[i] + 4, NULL, 16);
    }
    if (!begin_pc || !end_pc || !interval) {
        fprintf(stderr, "bbv_roi: need begin=, end= and interval=\n");
        return -1;
    }
    char path[4096];
    snprintf(path, sizeof(path), "%s.bb", out_prefix);
    bb = fopen(path, "w");
    if (!bb) {
        fprintf(stderr, "bbv_roi: cannot write %s\n", path);
        return -1;
    }
    keys = calloc(table_cap, sizeof(uint64_t));
    vals = calloc(table_cap, sizeof(Block *));
    counts_cap = 1 << 16;
    counts = calloc(counts_cap, sizeof(uint64_t));
    touched_cap = 1 << 12;
    touched = malloc(touched_cap * sizeof(uint32_t));
    qemu_plugin_register_vcpu_tb_trans_cb(id, tb_trans);
    qemu_plugin_register_atexit_cb(id, plugin_exit, NULL);
    return 0;
}
