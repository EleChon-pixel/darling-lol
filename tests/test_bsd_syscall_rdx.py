"""Offline contract: BSD syscalls return %rdx = 0 like XNU's rv[1].

Chromium's net::SendtoAndDetectBogusReturnValue treats a nonzero %rdx after
sendto() as a macOS kernel bug; SocketPosix::DoWrite then fails the write with
ERR_NETWORK_CHANGED. Darling's handlers are C functions that leave %rdx
undefined, so every Chromium socket write failed: the Riot Client's own UI
page (http://127.0.0.1) never loaded and the window stayed white.
"""
import unittest

from test_riot_client_142_remaining import patch_section

TRAMPOLINE = 'darling/src/libsystem_kernel/emulation/src/xnu_syscall/bsd/bsd_syscall.S'


def new_side(section):
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line[:1] in (' ', '+') and not line.startswith('+++'))


class BsdSyscallRdx(unittest.TestCase):
    def setUp(self):
        # The x86_64 trampoline is the only hunk in this file.
        self.x86 = new_side(patch_section('patches/xnu.patch', TRAMPOLINE))
        self.assertIn('darling-lol: keep the syscall number', self.x86)

    def test_rdx_is_zeroed_after_the_handler(self):
        after = self.x86.split('call\t*%r10', 1)[1].split('Lexit_hook:', 1)[0]
        self.assertIn('xorl\t%edx, %edx', after)
        # Syscalls whose stubs consume %rdx keep it.
        for number in ('$2,', '$42,', '$66,', '$116,'):
            self.assertIn('cmpq\t' + number + ' %r10', after)
        self.assertLess(after.index('cmpq\t$116, %r10'), after.index('xorl\t%edx, %edx'))

    def test_stack_arguments_and_parity_are_preserved(self):
        body = self.x86.split('jz\t\t.no_sys', 1)[1].split('call\t*%r10', 1)[0]
        # Eight slots keep the register arguments for the call trace and two keep the
        # syscall number; both are even, so the handlers' stack parity is unchanged and
        # the 7th and 8th arguments move from 24(%rsp) to 104(%rsp).
        self.assertIn('subq\t$16, %rsp', body)
        for register in ('%r9', '%r8', '%rcx', '%rdx', '%rsi', '%rdi'):
            self.assertEqual(body.count('pushq\t' + register), 1)
        self.assertEqual(body.count('pushq\t%rax'), 2)
        self.assertEqual(body.count('movq\t104(%rsp), %r11'), 2)
        self.assertNotIn('movq\t24(%rsp), %r11', body)
        self.assertNotIn('movq\t40(%rsp), %r11', body)
        after = self.x86.split('call\t*%r10', 1)[1].split('Lexit_hook:', 1)[0]
        self.assertEqual(after.count('addq\t$64, %rsp'), 1)

    def test_call_trace_is_one_flag_test_when_off(self):
        after = self.x86.split('call\t*%r10', 1)[1].split('Lexit_hook:', 1)[0]
        trace = after.split('cmpl\t$0, ___darling_call_trace_state(%rip)', 1)[1].split('.no_trace:', 1)[0]
        self.assertTrue(trace.lstrip().startswith('je\t\t.no_trace'))
        # The trace call leaves every register as the handler left it (the pipe stub
        # stores through %rdi after the call), on an even number of slots, and sees
        # the saved arguments and the caller's stack.
        for register in ('%rax', '%rdx', '%rcx', '%rsi', '%rdi', '%r8', '%r9', '%r10'):
            self.assertEqual(trace.count('pushq\t' + register), 1)
            self.assertEqual(trace.count('popq\t' + register), 1)
        self.assertEqual(trace.count('pushq\t%r11'), 2)
        self.assertEqual(trace.count('popq\t%r11'), 2)
        self.assertIn('leaq\t80(%rsp), %rsi', trace)
        self.assertIn('leaq\t144(%rsp), %rcx', trace)
        self.assertLess(after.index('.no_trace:'), after.index('cmpq\t$2, %r10'))

if __name__ == '__main__':
    unittest.main()
