# CoreMark build for RV32IM bare-metal.
# Usage:
#   make                   # build with default ITERATIONS=2000
#   make ITERATIONS=10     # build with small iteration count (simulation)
#   make VALIDATION_RUN=1  # validation run (seeds fixed, CRC-checked output)
#   make PROFILE_RUN=1     # profile run (smaller data set)

# Toolchain
RISCV_GCC      ?= riscv-none-elf-gcc
RISCV_OBJCOPY  ?= riscv-none-elf-objcopy
RISCV_OBJDUMP  ?= riscv-none-elf-objdump
RISCV_SIZE     ?= riscv-none-elf-size

# Architecture
MARCH  ?= rv32im
MABI   ?= ilp32

# Build mode: PERFORMANCE_RUN (default), VALIDATION_RUN, or PROFILE_RUN
RUN_MODE ?= PERFORMANCE_RUN

# Iterations (default 2000 for performance run, override for sim)
ITERATIONS ?= 2000

# Directories
SRC_DIR     := src
BUILD_DIR   := ../../build/coremark
OBJ_DIR     := $(BUILD_DIR)/obj

# CoreMark source files (from the EEMBC submodule)
COREMARK_SRCS := \
    $(SRC_DIR)/core_list_join.c \
    $(SRC_DIR)/core_main.c \
    $(SRC_DIR)/core_matrix.c \
    $(SRC_DIR)/core_state.c \
    $(SRC_DIR)/core_util.c

# Platform porting files
PORT_SRCS := \
    core_portme.c

# Startup and linker
START_S   := start.S
LINK_SCRIPT := link.ld

# Objects
COREMARK_OBJS := $(COREMARK_SRCS:$(SRC_DIR)/%.c=$(OBJ_DIR)/%.o)
PORT_OBJS     := $(PORT_SRCS:%.c=$(OBJ_DIR)/%.o)
START_OBJ     := $(OBJ_DIR)/start.o
ALL_OBJS      := $(COREMARK_OBJS) $(PORT_OBJS) $(START_OBJ)

# Output
ELF          := $(BUILD_DIR)/coremark.elf
MEM          := $(BUILD_DIR)/coremark.mem
MAP          := $(BUILD_DIR)/coremark.map

# Compiler flags
CFLAGS  := -march=$(MARCH) -mabi=$(MABI) -O2
CFLAGS  += -nostdlib -nostartfiles -ffreestanding
CFLAGS  += -msmall-data-limit=0          # No GP-relative small data
CFLAGS  += -I. -I$(SRC_DIR)
CFLAGS  += -D$(RUN_MODE) -DITERATIONS=$(ITERATIONS)
TOTAL_DATA_SIZE ?= 2000
CFLAGS  += -DTOTAL_DATA_SIZE=$(TOTAL_DATA_SIZE)
CFLAGS  += -Wall -Wextra -Werror

LDFLAGS := -nostdlib -nostartfiles -ffreestanding
LDFLAGS += -T $(LINK_SCRIPT)
LDFLAGS += -Wl,-Map=$(MAP)
LDFLAGS += -Wl,--gc-sections

.PHONY: all clean size mem

all: $(ELF) mem

# CoreMark source objects
$(OBJ_DIR)/%.o: $(SRC_DIR)/%.c core_portme.h | $(OBJ_DIR)
	$(RISCV_GCC) $(CFLAGS) -c -o $@ $<

# Porting layer objects
$(OBJ_DIR)/%.o: %.c core_portme.h | $(OBJ_DIR)
	$(RISCV_GCC) $(CFLAGS) -c -o $@ $<

# Startup object
$(OBJ_DIR)/start.o: $(START_S) | $(OBJ_DIR)
	$(RISCV_GCC) $(CFLAGS) -c -o $@ $<

# Link
$(ELF): $(ALL_OBJS) $(LINK_SCRIPT)
	$(RISCV_GCC) $(LDFLAGS) -o $@ $(ALL_OBJS) -lgcc

# Generate .mem files for RTL simulation
mem: $(ELF)
	$(RISCV_OBJCOPY) -O verilog --verilog-data-width=4 $(ELF) $(MEM)
	@# Rename the memory initialization section to match RTL expectations
	@if [ -f "$(BUILD_DIR)/coremark.elf.mem" ]; then \
	    mv "$(BUILD_DIR)/coremark.elf.mem" "$(MEM)"; \
	fi
	@echo "CoreMark .mem: $(MEM)"

# Size report
size: $(ELF)
	$(RISCV_SIZE) $(ELF)
	@echo ""
	@echo "Section sizes:"
	$(RISCV_OBJDUMP) -h $(ELF) | grep -E "\.text|\.rodata|\.data|\.bss|\.tohost"

# Disassembly (debug)
disasm: $(ELF)
	$(RISCV_OBJDUMP) -d $(ELF) > $(BUILD_DIR)/coremark.dis

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

clean:
	rm -rf $(BUILD_DIR)
