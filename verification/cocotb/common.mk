# verification/cocotb/common.mk
#
# Shared Makefile fragment for cocotb-based RTL verification.
#
# Per-design Makefiles should include this at the end after setting:
#   TOPLEVEL, COCOTB_TEST_MODULES, VERILOG_SOURCES
# and optionally:
#   COCOTB_PYTHONPATH, PYTHONPATH

TOPLEVEL_LANG  = verilog
SIM            = icarus

REPO_ROOT    = $(shell git rev-parse --show-toplevel)
RTL_ROOT     = $(REPO_ROOT)/rtl
SCRIPTS_ROOT = $(REPO_ROOT)/scripts
BUILD_DIR    = $(REPO_ROOT)/build
MEM_CONFIG   = $(RTL_ROOT)/shared/mem_config.vh

COMPILE_ARGS ?= -I$(RTL_ROOT)/shared

SHARED_SRCS = \
    $(RTL_ROOT)/shared/register_file.sv \
    $(RTL_ROOT)/shared/alu_rv32im.sv \
    $(RTL_ROOT)/shared/branch_unit.sv \
    $(RTL_ROOT)/shared/imm_gen.sv \
    $(RTL_ROOT)/shared/perf_counter.sv \
    $(RTL_ROOT)/shared/seven_segment.sv \
    $(RTL_ROOT)/shared/csr_file.sv

SHARED_VGA_SRCS = \
    $(RTL_ROOT)/shared/vga_pll.sv \
    $(RTL_ROOT)/shared/vga_text_mode.sv \
    $(RTL_ROOT)/shared/vga_controller.sv \
    $(RTL_ROOT)/shared/vga_font_rom.sv \
    $(RTL_ROOT)/shared/video_memory.sv

export REPO_ROOT
export SCRIPTS_ROOT
export BUILD_DIR
export RTL_SHARED  = $(RTL_ROOT)/shared
export IMEM_DEPTH  ?= 16384
export DMEM_DEPTH  ?= 8192

include $(shell cocotb-config --makefiles)/Makefile.sim

sim_build/sim.vvp: $(MEM_CONFIG)

$(MEM_CONFIG): FORCE
	@FIRST_ELF=$$(ls $(BUILD_DIR)/riscv-tests/rv32ui/*.elf 2>/dev/null | head -1); \
	if [ -n "$$FIRST_ELF" ]; then \
	    python3 $(SCRIPTS_ROOT)/gen_mem_config.py \
	        --imem $(BUILD_DIR)/imem.mem \
	        --dmem $(BUILD_DIR)/dmem.mem \
	        --relative-to $(PWD) \
	        --out $(MEM_CONFIG) \
	        --validate-linux-path $(BUILD_DIR)/imem.mem \
	        --validate-linux-dmem $(BUILD_DIR)/dmem.mem; \
	else \
	    mkdir -p $$(dirname $@); \
	    touch $@; \
	fi

sim: $(MEM_CONFIG)

FORCE:
