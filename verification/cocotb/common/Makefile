TOPLEVEL_LANG        = verilog
SIM                  = icarus
TOPLEVEL            ?= top_single_cycle
COCOTB_TEST_MODULES  = test_rv32i,test_rv32m,test_rv32mi,test_alu_rv32i,test_branch,test_model_vs_dut

REPO_ROOT    = $(shell git rev-parse --show-toplevel)
RTL_ROOT     = $(REPO_ROOT)/rtl
SCRIPTS_ROOT = $(REPO_ROOT)/scripts
BUILD_DIR    = $(REPO_ROOT)/build
MEM_CONFIG   = $(RTL_ROOT)/shared/mem_config.vh

VERILOG_SOURCES = \
    $(RTL_ROOT)/single_cycle/instruction_memory.sv \
    $(RTL_ROOT)/single_cycle/data_memory.sv \
    $(RTL_ROOT)/shared/register_file.sv \
    $(RTL_ROOT)/shared/alu_rv32im.sv \
    $(RTL_ROOT)/shared/branch_unit.sv \
    $(RTL_ROOT)/shared/imm_gen.sv \
    $(RTL_ROOT)/shared/perf_counter.sv \
    $(RTL_ROOT)/shared/seven_segment.sv \
    $(RTL_ROOT)/shared/csr_file.sv \
    $(RTL_ROOT)/single_cycle/control_unit.sv \
    $(RTL_ROOT)/single_cycle/pc.sv \
    $(RTL_ROOT)/single_cycle/top_single_cycle.sv

COMPILE_ARGS = -I$(RTL_ROOT)/shared

export COCOTB_PYTHONPATH := $(shell pwd):$(REPO_ROOT)/verification/reference_model
# cocotb 2.0.1 does not propagate COCOTB_PYTHONPATH to the vvp subprocess;
# we set PYTHONPATH directly so the embedded Python can import the
# reference_model package (see ADR 036).
export PYTHONPATH := $(shell pwd):$(REPO_ROOT)/verification/reference_model:$(PYTHONPATH)
export REPO_ROOT
export SCRIPTS_ROOT
export BUILD_DIR
export RTL_SHARED  = $(RTL_ROOT)/shared
export IMEM_DEPTH  = 16384
export DMEM_DEPTH  = 8192

include $(shell cocotb-config --makefiles)/Makefile.sim

sim_build/sim.vvp: $(MEM_CONFIG)

$(MEM_CONFIG): FORCE
	@FIRST_ELF=$$(ls $(BUILD_DIR)/riscv-tests/rv32ui/*.elf 2>/dev/null | head -1); \
	if [ -z "$$FIRST_ELF" ]; then \
	    echo "ERROR: No ELFs in $(BUILD_DIR)/riscv-tests/rv32ui/"; exit 1; \
	fi; \
        echo "skip" \
        python3 $(SCRIPTS_ROOT)/gen_mem_config.py --imem $(BUILD_DIR)/imem.mem --dmem $(BUILD_DIR)/dmem.mem --out $(MEM_CONFIG) \
sim: $(MEM_CONFIG)

FORCE: