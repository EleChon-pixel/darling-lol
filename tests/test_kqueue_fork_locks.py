"""Offline contracts for kqueue lock state across fork/posix_spawn.

libkqueue's objects are linked into both libSystem and libsystem_kernel.
libSystem's fork handlers call kqueue_atfork, which binds to libSystem's own
(unused) copy, so the live copy in libsystem_kernel kept locks that other
parent threads held at fork. A posix_spawn child then hung forever in
kqueue_dup during its dup2 file actions: the Riot Client's Chromium renderer
never started and the window showed only its border.
"""
import unittest

from test_riot_client_142_remaining import added_lines, patch_section

FORK = 'darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/impl/process/fork.c'


class KqueueForkLocks(unittest.TestCase):
    def test_sys_fork_child_resets_kernel_copy_first(self):
        fork = added_lines(patch_section('patches/xnu.patch', FORK))
        self.assertIn('kqueue_postfork_child_reset_locks();', fork)
        # Before the guard table closes descriptors, and not in dyld's copy,
        # which links no kqueue objects.
        section = patch_section('patches/xnu.patch', FORK)
        child = section.split('// in the child', 1)[1]
        self.assertLess(child.index('kqueue_postfork_child_reset_locks();'),
                        child.index('guard_table_postfork_child();'))
        guarded = fork.split('#ifndef VARIANT_DYLD', 1)[1].split('#endif', 1)[0]
        self.assertIn('kqueue_postfork_child_reset_locks();', guarded)

    def test_reset_is_lock_only(self):
        # malloc's zones are still locked when sys_fork's child runs.
        kq = added_lines(patch_section('patches/libkqueue.patch', 'src/common/kqueue.c'))
        body = kq.split('void kqueue_postfork_child_reset_locks(void)', 1)[1].split('\n}', 1)[0]
        self.assertIn('pthread_mutex_init(&kq_mtx, NULL);', body)
        self.assertIn('map_foreach(kqmap, _kqueue_reset_lock_postfork_cb, NULL);', body)
        self.assertIn('__darling_kqueue_listen_registry_postfork_child();', body)
        for call in ('free(', 'malloc(', 'kqueue_delref(', 'close('):
            self.assertNotIn(call, body)
        cb = kq.split('_kqueue_reset_lock_postfork_cb(int kqfd', 1)[1].split('\n}', 1)[0]
        self.assertIn('tracing_mutex_init(&kq->kq_mtx, NULL);', cb)
        self.assertNotIn('delref', cb)

    def test_listen_registry_sizes_are_in_elements(self):
        reg = added_lines(patch_section('patches/libkqueue.patch', 'src/darling/listenregistry.c'))
        self.assertIn('malloc(REGISTRY_VECTOR_INITIAL_CAPACITY * sizeof(*registry_vector))', reg)
        self.assertIn('realloc(registry_vector, registry_vector_capacity * 2 * sizeof(*registry_vector))',
                      reg)
        self.assertIn('pthread_mutex_init(&registry_mtx, NULL);', reg)


if __name__ == '__main__':
    unittest.main()
