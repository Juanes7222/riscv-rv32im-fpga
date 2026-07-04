TOPLEVEL            ?= top_single_cycle
COCOTB_TEST_MODULES  = test_rv32i,test_rv32m,test_rv32mi,test_alu_rv32i,test_branch,test_model_vs_dut

VERILOG_SOURCES = \
    $(SHARED_SRCS) \
    $(SHARED_VGA_SRCS) \
    $(RTL_ROOT)/single_cycle/instruction_memory.sv \
    $(RTL_ROOT)/single_cycle/data_memory.sv \
    $(RTL_ROOT)/single_cycle/control_unit.sv \
    $(RTL_ROOT)/single_cycle/pc.sv \
    $(RTL_ROOT)/single_cycle/screen_writer_sc.sv \
    $(RTL_ROOT)/single_cycle/top_single_cycle.sv

export COCOTB_PYTHONPATH := $(shell pwd):$(REPO_ROOT)/verification/reference_model
export PYTHONPATH := $(shell pwd):$(REPO_ROOT)/verification/reference_model:$(PYTHONPATH)

include ../common.mk
