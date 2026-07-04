# verification/cocotb/single_cycle/Makefile
#
# Single-cycle-specific cocotb tests (currently: test_cpi_one, the architectural
# invariant that cycle_count == instr_retired for every instruction except
# DIV/DIVU/REM/REMU).
#
# Mirrors verification/cocotb/common/Makefile but with:
#   - COCOTB_TEST_MODULES = test_cpi_one (only this file's tests)
#   - COCOTB_PYTHONPATH   = $PWD/test:$PWD/../common
#                            so that the test can do `from tohost import ...`
#                            and `from conftest import ...` against the shared
#                            modules in ../../common/.

TOPLEVEL_LANG        = verilog
SIM                  = icarus
TOPLEVEL             = top_single_cycle
COCOTB_TEST_MODULES  = test_cpi_one

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
    $(RTL_ROOT)/shared/vga_pll.sv \
    $(RTL_ROOT)/shared/vga_text_mode.sv \
    $(RTL_ROOT)/shared/vga_controller.sv \
    $(RTL_ROOT)/shared/vga_font_rom.sv \
    $(RTL_ROOT)/shared/video_memory.sv \
    $(RTL_ROOT)/single_cycle/control_unit.sv \
    $(RTL_ROOT)/single_cycle/pc.sv \
    $(RTL_ROOT)/single_cycle/screen_writer_sc.sv \
    $(RTL_ROOT)/single_cycle/top_single_cycle.sv

COMPILE_ARGS = -I$(RTL_ROOT)/shared

# The cocotb VPI (libcocotb.so) reads `PYTHONPATH` (not `COCOTB_PYTHONPATH`)
# to set up the embedded Python's module search path. We need three entries
# so that:
#   - the test module `test_cpi_one` resolves to ./test/test_cpi_one.py,
#   - `tohost` and `conftest` resolve to ../../common/{tohost,conftest}.py,
#   - the cocotb installation itself stays importable (it's already in
#     sys.path from PYGPI_PYTHON_BIN's site-packages, but we include it
#     for safety).
export PYTHONPATH := $(PWD)/test:$(PWD)/../common:$(PWD)/../../../.venv/lib/python3.12/site-packages:$(PYTHONPATH)
export COCOTB_PYTHONPATH := $(PWD)/test:$(PWD)/../common
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
	python3 $(SCRIPTS_ROOT)/gen_mem_config.py \
	    --imem $(BUILD_DIR)/imem.mem \
	    --dmem $(BUILD_DIR)/dmem.mem \
	    --relative-to $(PWD) \
	    --out $(MEM_CONFIG) \
	    --validate-linux-path $(BUILD_DIR)/imem.mem \
	    --validate-linux-dmem $(BUILD_DIR)/dmem.mem
sim: $(MEM_CONFIG)

FORCE:
