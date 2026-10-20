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

# Simulation memory images.  They live in build/sim/ because the FPGA flow
# owns build/imem.mem and build/dmem.mem (generated at the synthesis depths).
# The paths are injected from the command line so the simulation never has to
# write rtl/shared/mem_config.vh, which belongs to the Quartus build.
SIM_MEM_DIR  = $(BUILD_DIR)/sim
SIM_IMEM     = $(SIM_MEM_DIR)/imem.mem
SIM_DMEM     = $(SIM_MEM_DIR)/dmem.mem
SIM_TEST_ELF = $(firstword $(wildcard $(BUILD_DIR)/riscv-tests/rv32ui/*.elf))

COMPILE_ARGS ?= -I$(RTL_ROOT)/shared
COMPILE_ARGS += -DIMEM_FILE=\"$(abspath $(SIM_IMEM))\"
COMPILE_ARGS += -DDMEM_FILE=\"$(abspath $(SIM_DMEM))\"
COMPILE_ARGS += -DFONT_ROM_FILE=\"$(abspath $(RTL_ROOT)/shared/vga_font_rom.hex)\"

# The waveform dump is off unless it is asked for: a long benchmark run
# writes gigabytes and becomes I/O bound.
ifneq ($(DUMP_VCD),1)
COMPILE_ARGS += -DNO_VCD
endif

SHARED_SRCS = \
    $(RTL_ROOT)/shared/register_file.sv \
    $(RTL_ROOT)/shared/alu_rv32im.sv \
    $(RTL_ROOT)/shared/branch_unit.sv \
    $(RTL_ROOT)/shared/imm_gen.sv \
    $(RTL_ROOT)/shared/perf_counter.sv \
    $(RTL_ROOT)/shared/step_mode.sv \
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

# The simulation images only need to exist when the simulator starts; each
# test regenerates them for the ELF it exercises.
$(SIM_IMEM): $(SIM_TEST_ELF)
	@mkdir -p $(SIM_MEM_DIR)
	python3 $(SCRIPTS_ROOT)/elf_to_mem.py $< $(IMEM_DEPTH) $@

$(SIM_DMEM): $(SIM_TEST_ELF)
	@mkdir -p $(SIM_MEM_DIR)
	python3 $(SCRIPTS_ROOT)/elf_to_mem.py $< $(DMEM_DEPTH) $@

sim_build/sim.vvp: $(SIM_IMEM) $(SIM_DMEM)
