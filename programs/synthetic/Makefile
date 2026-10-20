# Build the synthetic stress benchmarks for RV32IM.
#
# Each program is a tight loop that stresses one microarchitectural effect
# (RAW dependencies, control hazards, load-use hazards, M-extension latency)
# and writes 1 to tohost when it finishes, so the cocotb harness can detect
# the end of the run.
#
# The tohost symbol is placed at 0x708, the same address the riscv-tests use,
# so a single FPGA build (TOHOST_ADDR = 0x708) detects the end of every
# benchmark.

RISCV_GCC ?= riscv-none-elf-gcc
RISCV_OBJCOPY ?= riscv-none-elf-objcopy

MARCH ?= rv32im
MABI  ?= ilp32

BUILD_DIR ?= ../../build/synthetic
LINKER_SCRIPT ?= link.ld

PROGRAMS := raw_stress branch_stress load_use_stress m_ext_stress

CFLAGS := -march=$(MARCH) -mabi=$(MABI) -O2 -nostdlib -nostartfiles \
          -ffreestanding -T $(LINKER_SCRIPT)

.PHONY: all clean
all: $(addprefix $(BUILD_DIR)/,$(addsuffix .elf,$(PROGRAMS)))

$(BUILD_DIR)/%.elf: %.S $(LINKER_SCRIPT)
	@mkdir -p $(BUILD_DIR)
	$(RISCV_GCC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(BUILD_DIR)/*.elf
