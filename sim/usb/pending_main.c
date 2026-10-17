/* Host-only upstream-Lean runtime entry. No USB or durable policy lives here. */
#include <lean/lean.h>
extern lean_object *initialize_USBPendingPolicy(uint8_t builtin);
extern lean_object *lemma_usb_pending_main(lean_object *arguments);
extern char **lean_setup_args(int argc, char **argv);
static lean_object *run_pending(int argc, char **argv) {
    lean_object *arguments = lean_box(0);
    for (int i = argc; i > 1;) {
        --i;
        lean_object *node = lean_alloc_ctor(1, 2, 0);
        lean_ctor_set(node, 0, lean_mk_string(argv[i]));
        lean_ctor_set(node, 1, arguments);
        arguments = node;
    }
    return lemma_usb_pending_main(arguments);
}
int main(int argc, char **argv) {
    argv = lean_setup_args(argc, argv);
    lean_object *result = initialize_USBPendingPolicy(1);
    lean_io_mark_end_initialization();
    if (lean_io_result_is_ok(result)) {
        lean_dec_ref(result);
        lean_init_task_manager();
        result = lean_run_main(&run_pending, argc, argv);
    }
    lean_finalize_task_manager();
    if (lean_io_result_is_ok(result)) {
        int code = lean_unbox_uint32(lean_io_result_get_value(result));
        lean_dec_ref(result);
        return code;
    }
    lean_io_result_show_error(result);
    lean_dec_ref(result);
    return 1;
}
