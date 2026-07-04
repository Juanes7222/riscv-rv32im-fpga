# Single-cycle-specific cocotb tests (currently: test_cpi_one, the architectural
# invariant that cycle_count == instr_retired for every instruction except
# DIV/DIVU/REM/REMU).

TOPLEVEL             = top_single_cycle
COCOTB_TEST_MODULES  = test_cpi_one

VERILOG_SOURCES = \
    $(SHARED_SRCS) \
    $(SHARED_VGA_SRCS) \
    $(RTL_ROOT)/single_cycle/instruction_memory.sv \
    $(RTL_ROOT)/single_cycle/data_memory.sv \
    $(RTL_ROOT)/single_cycle/control_unit.sv \
    $(RTL_ROOT)/single_cycle/pc.sv \
    $(RTL_ROOT)/single_cycle/screen_writer_sc.sv \
    $(RTL_ROOT)/single_cycle/top_single_cycle.sv

# cocotb 2.0.1 VPI uses PYTHONPATH.  We need three entries so that:
#   - test_cpi_one resolves to ./test/test_cpi_one.py,
#   - tohost and conftest resolve to ../common/{tohost,conftest}.py,
#   - the existing cocotb site-packages stays reachable.
export PYTHONPATH := $(PWD)/test:$(PWD)/../common:$(PWD)/../../../.venv/lib/python3.12/site-packages:$(PYTHONPATH)
export COCOTB_PYTHONPATH := $(PWD)/test:$(PWD)/../common

include ../common.mk
