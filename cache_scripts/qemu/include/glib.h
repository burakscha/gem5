/*
 * The few glib declarations qemu-plugin.h and the plugins in cache_scripts/qemu
 * need (this host has no glib headers). The functions themselves come from the
 * libglib-2.0 that qemu-riscv64 is linked against.
 */
#ifndef CACHE_SCRIPTS_MIN_GLIB_H
#define CACHE_SCRIPTS_MIN_GLIB_H
typedef char gchar;
typedef unsigned int guint;
typedef unsigned char guint8;
typedef struct _GArray { gchar *data; guint len; } GArray;
typedef struct _GByteArray { guint8 *data; guint len; } GByteArray;
GByteArray *g_byte_array_new(void);
GByteArray *g_byte_array_set_size(GByteArray *array, guint length);
#endif
