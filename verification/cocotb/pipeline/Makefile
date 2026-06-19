TOPLEVEL_LANG        = verilog
SIM                  = icarus
TOPLEVEL            ?= top_pipeline
COCOTB_TEST_MODULES  = test_pipeline_smoke,test_pipeline_debug,test_pipeline_rv32i,test_pipeline_rv32m,test_pipeline_rv32mi

REPO_ROOT    = $(shell git rev-parse --show-toplevel)
RTL_ROOT     = $(REPO_ROOT)/rtl
SCRIPTS_ROOT = $(REPO_ROOT)/scripts
BUILD_DIR    = $(REPO_ROOT)/build
MEM_CONFIG   = $(RTL_ROOT)/shared/mem_config.vh

# RTL sources: shared modules + the pipeline.
# The shared instruction_memory is loaded with the program via mem_config.vh
# (which points to build/imem.mem); the test preloads imem by writing
# dut.u_imem.mem[k] directly before stepping the clock.
VERILOG_SOURCES = \
    $(RTL_ROOT)/shared/instruction_memory.sv \
    $(RTL_ROOT)/shared/data_memory.sv \
    $(RTL_ROOT)/shared/register_file.sv \
    $(RTL_ROOT)/shared/alu_rv32im.sv \
    $(RTL_ROOT)/shared/branch_unit.sv \
    $(RTL_ROOT)/shared/imm_gen.sv \
    $(RTL_ROOT)/shared/perf_counter.sv \
    $(RTL_ROOT)/shared/seven_segment.sv \
    $(RTL_ROOT)/shared/csr_file.sv \
    $(RTL_ROOT)/pipeline/control_unit.sv \
    $(RTL_ROOT)/pipeline/if_id_register.sv \
    $(RTL_ROOT)/pipeline/id_ex_register.sv \
    $(RTL_ROOT)/pipeline/ex_mem_register.sv \
    $(RTL_ROOT)/pipeline/mem_wb_register.sv \
    $(RTL_ROOT)/pipeline/hazard_detection.sv \
    $(RTL_ROOT)/pipeline/forwarding_unit.sv \
    $(RTL_ROOT)/pipeline/pc_unit.sv \
    $(RTL_ROOT)/pipeline/top_pipeline.sv

COMPILE_ARGS = -I$(RTL_ROOT)/shared

export COCOTB_PYTHONPATH := $(shell pwd):$(REPO_ROOT)/verification/reference_model:$(REPO_ROOT)/verification/cocotb/common
export PYTHONPATH := $(shell pwd):$(REPO_ROOT)/verification/reference_model:$(REPO_ROOT)/verification/cocotb/common:$(PYTHONPATH)
export REPO_ROOT
export SCRIPTS_ROOT
export BUILD_DIR
export RTL_SHARED  = $(RTL_ROOT)/shared
export IMEM_DEPTH  = 16384
export DMEM_DEPTH  = 8192

include $(shell cocotb-config --makefiles)/Makefile.sim

# Generate mem_config for the riscv-tests pipeline run. The
# test_pipeline_rv32i/rv32m/rv32mi tests invoke gen_mem_config.py
# themselves (via tohost.generate_mem_for_elf) for each ELF; this target
# just ensures the file exists for the make-level dependency.
sim_build/sim.vvp: $(MEM_CONFIG)

$(MEM_CONFIG):
	@mkdir -p $(dir $@)
	@touch $@

FORCE:
