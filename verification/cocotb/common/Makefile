TOPLEVEL_LANG = verilog
SIM           = icarus
TOPLEVEL     ?= top_single_cycle
MODULE        = tests.test_rv32i tests.test_rv32m

REPO_ROOT    = $(shell git rev-parse --show-toplevel)
RTL_ROOT     = $(REPO_ROOT)/rtl
SCRIPTS_ROOT = $(REPO_ROOT)/scripts
BUILD_DIR    = $(REPO_ROOT)/build

VERILOG_SOURCES = \
    $(RTL_ROOT)/shared/instruction_memory.sv \
    $(RTL_ROOT)/shared/data_memory.sv \
    $(RTL_ROOT)/shared/register_file.sv \
    $(RTL_ROOT)/shared/alu_rv32im.sv \
    $(RTL_ROOT)/shared/branch_unit.sv \
    $(RTL_ROOT)/shared/imm_gen.sv \
    $(RTL_ROOT)/shared/perf_counter.sv \
    $(RTL_ROOT)/single_cycle/control_unit.sv \
    $(RTL_ROOT)/single_cycle/pc_unit.sv \
    $(RTL_ROOT)/single_cycle/top_single_cycle.sv

COMPILE_ARGS  = -I$(RTL_ROOT)/shared

export REPO_ROOT
export SCRIPTS_ROOT
export BUILD_DIR
export RTL_SHARED = $(RTL_ROOT)/shared

$(RTL_ROOT)/shared/mem_config.vh:
    python3 $(SCRIPTS_ROOT)/gen_mem_config.py \
        --imem $(BUILD_DIR)/imem.mem \
        --dmem $(BUILD_DIR)/dmem.mem

pre-sim: $(RTL_ROOT)/shared/mem_config.vh

include $(shell cocotb-config --makefiles)/Makefile.sim