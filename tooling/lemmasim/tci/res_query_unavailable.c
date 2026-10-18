/* Host-only unsupported-DNS boundary from upstream QEMU11.1.1 Emscripten recipe.
 * Always fails; no DNS, notebook, sensor, mathematical or guest-runtime authority. */
#include <netdb.h>
int res_query(const char *name, int query_class, int type, unsigned char *dest, int len)
{ (void)name;(void)query_class;(void)type;(void)dest;(void)len;h_errno=HOST_NOT_FOUND;return -1; }
