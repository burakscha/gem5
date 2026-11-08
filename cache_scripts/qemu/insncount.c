/* Counts guest instructions; writes the total to the file named by out=. */
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <qemu-plugin.h>

QEMU_PLUGIN_EXPORT int qemu_plugin_version = QEMU_PLUGIN_VERSION;

static struct qemu_plugin_scoreboard *sb;
static qemu_plugin_u64 count;
static const char *out_path = "insncount.txt";

static void tb_trans(qemu_plugin_id_t id, struct qemu_plugin_tb *tb)
{
    qemu_plugin_register_vcpu_tb_exec_inline_per_vcpu(
        tb, QEMU_PLUGIN_INLINE_ADD_U64, count, qemu_plugin_tb_n_insns(tb));
}

static void plugin_exit(qemu_plugin_id_t id, void *p)
{
    FILE *f = fopen(out_path, "w");
    if (f) {
        fprintf(f, "%" PRIu64 "\n", qemu_plugin_u64_sum(count));
        fclose(f);
    }
}

QEMU_PLUGIN_EXPORT int qemu_plugin_install(qemu_plugin_id_t id,
                                           const qemu_info_t *info,
                                           int argc, char **argv)
{
    for (int i = 0; i < argc; i++)
        if (strncmp(argv[i], "out=", 4) == 0)
            out_path = strdup(argv[i] + 4);
    sb = qemu_plugin_scoreboard_new(sizeof(uint64_t));
    count = qemu_plugin_scoreboard_u64(sb);
    qemu_plugin_register_vcpu_tb_trans_cb(id, tb_trans);
    qemu_plugin_register_atexit_cb(id, plugin_exit, NULL);
    return 0;
}
