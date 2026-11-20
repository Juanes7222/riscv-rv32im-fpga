"""Precise fault metadata, suppressed side effects, and an older trap vs DIV."""
import cocotb
from cocotb.triggers import RisingEdge, Timer
from conftest import start_clock, apply_reset
from tohost import monitor_tohost, REPO_ROOT


def addi(rd, rs1, immediate):
    return ((immediate & 0xfff) << 20) | (rs1 << 15) | (rd << 7) | 0x13


def csr(rd, address, rs1=0, operation=2):
    return (address << 20) | (rs1 << 15) | (operation << 12) | (rd << 7) | 0x73


def store(rs2, immediate):
    return ((immediate >> 5) << 25) | (rs2 << 20) | (2 << 12) | ((immediate & 31) << 7) | 0x23


def data_word(dut, address):
    index = address // 4
    return sum(int(getattr(dut.u_dmem, 'mem_b' + str(lane))[index].value) << (8 * lane)
               for lane in range(4))


def _case(name, fault, cause, value, younger_div=False, host_redirect=False):
    @cocotb.test(name='test_precise_' + name)
    async def test(dut):
        await start_clock(dut)
        dut.rst_n.value = 0
        if hasattr(dut, 'key_load'):
            dut.key_load.value = 1
        if hasattr(dut, 'sw'):
            dut.sw.value = 0
        # All programs place the fault at PC=16 and the handler at 128.
        words = [addi(1, 0, 128), csr(0, 0x305, 1, 1),
                 addi(5, 0, 77), addi(6, 0, 55), fault]
        if host_redirect:
            words.append(store(6, 0x708))
        if younger_div:
            words.append((1 << 25) | (5 << 20) | (6 << 15) | (4 << 12) | (21 << 7) | 0x33)
        words += [addi(20, 0, 99), store(6, 256), csr(0, 0x340, 6, 1), 0x0000006f]
        words += [0x00000013] * (32 - len(words))
        words += [csr(10, 0x342), csr(11, 0x341), csr(12, 0x343), addi(13, 0, 1)]
        if host_redirect:
            words.append(store(13, 0x708))
        words.append(0x0000006f)
        for index, word in enumerate(words):
            dut.u_imem.mem[index].value = word
        for address in [0, 256, 0x708]:
            for lane in range(4):
                getattr(dut.u_dmem, 'mem_b' + str(lane))[address // 4].value = (0x44332211 >> (8 * lane)) & 255
        await apply_reset(dut)
        if host_redirect:
            # This ELF supplies only the mailbox symbol to the shared monitor.
            # The program under test is the raw sequence loaded above.
            result = await monitor_tohost(dut, REPO_ROOT / 'build/synthetic/raw_stress.elf', 180)
            assert result == 'pass', 'Monitor accepted the cancelled younger mailbox store'
        for _ in range(180):
            await RisingEdge(dut.clk)
        await Timer(1, unit='ns')
        regs = dut.u_rf.regs
        assert int(regs[13].value) == 1, 'Handler did not complete'
        assert int(regs[10].value) == cause, 'Wrong mcause'
        assert int(regs[11].value) == 16, 'Wrong mepc'
        assert int(regs[12].value) == value, 'Wrong mtval'
        assert int(regs[5].value) == 77, 'Faulting instruction wrote its destination'
        assert int(regs[20].value) == 0, 'Younger register write committed'
        assert int(dut.u_csr.mscratch.value) == 0, 'Younger CSR write committed'
        assert data_word(dut, 0) == 0x44332211, 'Faulting store modified memory'
        assert data_word(dut, 256) == 0x44332211, 'Younger store modified memory'
    return test


CASES = [('illegal', 0x00000000, 2, 0, False),
         ('shift_encoding', 0x02029293, 2, 0, False),
         ('breakpoint', 0x00100073, 3, 16, False),
         ('ecall', 0x00000073, 11, 0, False),
         ('load_alignment', (1 << 20) | (2 << 12) | (5 << 7) | 0x03, 4, 1, False),
         ('store_alignment', store(6, 1), 6, 1, False),
         ('jump_alignment', (1 << 21) | (5 << 7) | 0x6f, 0, 18, False),
         ('trap_before_divider', 0x00100073, 3, 16, True)]
for _name, _fault, _cause, _value, _div in CASES:
    globals()['test_precise_' + _name] = _case(_name, _fault, _cause, _value, _div)

test_precise_cancelled_mailbox_store = _case('cancelled_mailbox_store', 0x00100073, 3, 16,
                                           host_redirect=True)
