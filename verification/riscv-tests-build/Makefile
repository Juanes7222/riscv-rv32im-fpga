# verification/riscv-tests-build/Makefile
#
# Project-local build harness for the riscv-tests submodule (ADR 027).  It lives
# outside verification/riscv-tests/ so the parent repository can track it: the
# submodule's own .gitignore excludes /Makefile and a parent commit cannot add
# files inside a submodule path.

TOOLCHAIN_PREFIX = riscv-none-elf
CC = $(TOOLCHAIN_PREFIX)-gcc

THIS_DIR  = $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT = $(abspath $(THIS_DIR)/../..)

LINK_LD        = $(THIS_DIR)link.ld
ISA_DIR        = $(REPO_ROOT)/verification/riscv-tests/isa
INCLUDE_MACROS = $(ISA_DIR)/macros/scalar
INCLUDE_ENV    = $(REPO_ROOT)/verification/riscv-tests/env/p
BUILD_DIR      = $(REPO_ROOT)/build/riscv-tests

# RV32IM_Zicsr is the base ISA the DUT implements (ADR 030). RV32MI tests
# additionally need Zicntr for the instret/zicntr tests. PMP is not
# implemented on the DUT, so pmpaddr is omitted from TESTS_RV32MI.
CFLAGS = \
    -march=rv32im_zicsr_zicntr \
    -mabi=ilp32 \
    -static \
    -nostdlib \
    -T $(LINK_LD) \
    -I $(INCLUDE_MACROS) \
    -I $(INCLUDE_ENV)

TESTS_RV32I = \
    add addi and andi auipc \
    beq bge bgeu blt bltu bne \
    jal jalr \
    lb lbu lh lhu lui lw \
    or ori \
    sb sh sll slli slt slti sltiu sltu \
    sra srai srl srli sub sw \
    xor xori

TESTS_RV32M = \
    div divu mul mulh mulhsu mulhu rem remu

# RV32MI: machine-mode tests (ECALL, EBREAK, illegal instruction, CSR,
# misaligned access). pmpaddr is omitted because the DUT does not implement
# PMP (would fail with a different reason than the test is checking for).
TESTS_RV32MI = \
    breakpoint csr illegal ma_addr ma_fetch mcsr scall sbreak shamt \
    lh-misaligned lw-misaligned sh-misaligned sw-misaligned \
    zicntr instret_overflow

ELFS_RV32I  = $(addprefix $(BUILD_DIR)/rv32ui/,  $(addsuffix .elf, $(TESTS_RV32I)))
ELFS_RV32M  = $(addprefix $(BUILD_DIR)/rv32um/,  $(addsuffix .elf, $(TESTS_RV32M)))
ELFS_RV32MI = $(addprefix $(BUILD_DIR)/rv32mi/, $(addsuffix .elf, $(TESTS_RV32MI)))

.PHONY: all rv32i rv32m rv32mi clean

all: rv32i rv32m rv32mi

rv32i: $(ELFS_RV32I)
	@echo "[riscv-tests] RV32I: $(words $(TESTS_RV32I)) tests compiled → $(BUILD_DIR)/rv32ui/"

rv32m: $(ELFS_RV32M)
	@echo "[riscv-tests] RV32M: $(words $(TESTS_RV32M)) tests compiled → $(BUILD_DIR)/rv32um/"

rv32mi: $(ELFS_RV32MI)
	@echo "[riscv-tests] RV32MI: $(words $(TESTS_RV32MI)) tests compiled → $(BUILD_DIR)/rv32mi/"

$(BUILD_DIR)/rv32ui/%.elf: $(ISA_DIR)/rv32ui/%.S
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $< -o $@

$(BUILD_DIR)/rv32um/%.elf: $(ISA_DIR)/rv32um/%.S
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $< -o $@

$(BUILD_DIR)/rv32mi/%.elf: $(ISA_DIR)/rv32mi/%.S
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $< -o $@

clean:
	rm -rf $(BUILD_DIR)/rv32ui $(BUILD_DIR)/rv32um $(BUILD_DIR)/rv32mi
	@echo "[riscv-tests] Build artifacts removed."
