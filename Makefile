ARCH        ?= single_cycle
N_REPLICAS  ?= 5

# bash: SECONDS is a bash builtin, and it is not available in dash.
SHELL       := /bin/bash

VALID_ARCHS := single_cycle pipeline

ifeq ($(filter $(ARCH), $(VALID_ARCHS)),)
$(error Invalid ARCH='$(ARCH)'. Valid values: $(VALID_ARCHS))
endif

# Paths
SYNTH_DIR        = synthesis/$(ARCH)
RESULTS_DIR      = results/$(ARCH)
RTL_ROOT         = rtl
VERIF_COMMON_DIR = verification/cocotb/common
VERIF_ARCH_DIR   = verification/cocotb/$(ARCH)

# Project names
PROJECT_single_cycle = rv32im_single_cycle
PROJECT_pipeline     = rv32im_pipeline
PROJECT              = $(PROJECT_$(ARCH))

# Quartus tools
QUARTUS_SH  = quartus_sh.exe
QUARTUS_PGM = quartus_pgm.exe
QUARTUS_STA = quartus_sta.exe
QUARTUS_STP = quartus_stp.exe

SOF_FILE = $(SYNTH_DIR)/output_files/$(PROJECT).sof
STA_RPT  = $(SYNTH_DIR)/output_files/$(PROJECT).sta.rpt
FIT_SUMMARY = $(SYNTH_DIR)/output_files/$(PROJECT).fit.summary

# The virtualenv holds cocotb and its tools (cocotb-config).  The simulation
# makefiles need cocotb-config in the PATH, so the thesis targets prepend it.
VENV_PY = .venv/bin/python3
VENV_BIN = $(CURDIR)/.venv/bin

# Screen console artifacts.  The .mif carries the memory dump of the program
# that is loaded, so it is regenerated whenever the memory image changes.
WRITER_single_cycle = screen_writer_sc.sv
WRITER_pipeline     = screen_writer_pipeline.sv
SCREEN_MIF    = $(SYNTH_DIR)/screen.mif
SCREEN_WRITER = $(RTL_ROOT)/$(ARCH)/$(WRITER_$(ARCH)).sv

# Memory depths for synthesis - keep small for fast Quartus compilation.
# cocotb overrides these via environment variables (16384 / 8192).
IMEM_DEPTH := 2048
DMEM_DEPTH := 512

BUILD_DIR ?= build

# Results output directory for FPGA cross-validation
CROSS_VAL_DIR = results

# Entry point for the flash pipeline. Override with: make flash ELF=path/to/program.elf
ELF ?=

IMEM_MEM = $(BUILD_DIR)/imem.mem
DMEM_MEM = $(BUILD_DIR)/dmem.mem

MEM_CONFIG_VH = rtl/shared/mem_config.vh

# Always regenerate the header: it carries paths relative to the Quartus
# project directory, and any other flow (a simulation run, a previous
# architecture) may have left a header with the wrong paths behind.
$(MEM_CONFIG_VH): FORCE
	@if [ ! -f "$(IMEM_MEM)" ] || [ ! -f "$(DMEM_MEM)" ]; then \
	    echo "Error: $(IMEM_MEM) / $(DMEM_MEM) not found."; \
	    echo "Generate them first with: make mem ELF=<path/to/program.elf>"; \
	    exit 1; \
	fi
	python3 scripts/gen_mem_config.py \
		--imem $(abspath $(IMEM_MEM)) \
		--dmem $(abspath $(DMEM_MEM)) \
		--relative-to $(abspath $(SYNTH_DIR)) \
		--validate-linux-path $(abspath $(IMEM_MEM)) \
		--validate-linux-dmem $(abspath $(DMEM_MEM))

FORCE:

$(SCREEN_MIF): $(IMEM_MEM) $(DMEM_MEM) scripts/RiscVScreenV3.xlsx \
               scripts/gen_screen_mif.py scripts/gen_screen_writer.py
	IMEM=$(IMEM_MEM) DMEM=$(DMEM_MEM) bash scripts/gen_screen_artifacts.sh

$(SCREEN_WRITER): $(SCREEN_MIF)

# Default target: show help
all: help


.PHONY: setup
setup:
	@echo "[$(ARCH)] Creating Quartus project..."
	@cd $(SYNTH_DIR) && $(QUARTUS_SH) -t setup.tcl
	@echo "[$(ARCH)] Project created. Run 'make build ARCH=$(ARCH)' to synthesize."


# Runs the Quartus compilation and fails the target when the flow did not
# produce a new bitstream and a new timing report.
#
# The check is on the artifacts and not only on the exit code, because
# Quartus Lite 25.1 dies with an access violation in its STA engine while
# it reads the SDC file, in the middle of Analysis & Synthesis.  The crash
# belongs to the tool, not to the design, and it is intermittent: the same
# design compiles on the next attempt.  A run is accepted only when the
# timing report and the bitstream of that run were written, so a flow that
# died halfway can never pass off a stale artifact.
#
# The run is repeated up to QUARTUS_ATTEMPTS times before giving up.
#
# Usage: $(call quartus_compile,build.tcl)  |  $(call quartus_compile,build.tcl,3)
QUARTUS_ATTEMPTS ?= 3

define quartus_compile
	before=$$(stat -c %Y $(abspath $(STA_RPT)) 2>/dev/null || echo 0); \
	sof_before=$$(stat -c %Y $(abspath $(SOF_FILE)) 2>/dev/null || echo 0); \
	attempt=1; \
	while : ; do \
		(cd $(SYNTH_DIR) && $(QUARTUS_SH) -t $(1) $(2)) ; \
		after=$$(stat -c %Y $(abspath $(STA_RPT)) 2>/dev/null || echo 0); \
		sof_after=$$(stat -c %Y $(abspath $(SOF_FILE)) 2>/dev/null || echo 0); \
		if [ -f $(abspath $(STA_RPT)) ] && [ -f $(abspath $(SOF_FILE)) ] && \
		   [ "$$after" -gt "$$before" ] && [ "$$sof_after" -gt "$$sof_before" ]; then \
			break; \
		fi; \
		if [ $$attempt -ge $(QUARTUS_ATTEMPTS) ]; then \
			echo "[$(ARCH)] Error: $(STA_RPT) and $(SOF_FILE) were not regenerated after $(QUARTUS_ATTEMPTS) attempts."; \
			exit 1; \
		fi; \
		echo "[$(ARCH)] The compilation did not finish (attempt $$attempt/$(QUARTUS_ATTEMPTS)), repeating it."; \
		attempt=$$((attempt+1)); \
		sleep 10; \
	done
endef


.PHONY: sync
sync: check-project
	@echo "[$(ARCH)] Syncing RTL source files..."
	@cd $(SYNTH_DIR) && $(QUARTUS_SH) -t sync.tcl


.PHONY: sync-all
sync-all:
	@$(MAKE) sync ARCH=single_cycle
	@$(MAKE) sync ARCH=pipeline


.PHONY: build build-only
build: check-project $(MEM_CONFIG_VH) $(SCREEN_MIF)
	@echo "[$(ARCH)] Starting synthesis..."
	@SECONDS=0; \
	$(call quartus_compile,build.tcl); \
	echo "[$(ARCH)] Synthesis completed in $$SECONDS seconds"

# Same as build but skips mem_config.vh generation - use when .mem files
# already exist and you only want to recompile RTL changes.
build-only: check-project
	@echo "[$(ARCH)] Starting synthesis (without mem refresh)..."
	@SECONDS=0; \
	$(call quartus_compile,build.tcl); \
	echo "[$(ARCH)] Synthesis completed in $$SECONDS seconds"


# Build with SignalTap II for FPGA validation.
# Prerequisite: run 'python scripts/fpga_validate.py --elf <path> --fpga-only' first
# to generate .mem files and mem_config.vh for the validation program.
# Usage: make build-fpga ARCH=pipeline
.PHONY: build-fpga
build-fpga: check-project $(MEM_CONFIG_VH) $(SCREEN_MIF)
	@echo "[$(ARCH)] Building with SignalTap II for FPGA validation..."
	@echo "[$(ARCH)] Using mem_config.vh: $$(grep 'IMEM_FILE\|DMEM_FILE' $(MEM_CONFIG_VH) | tr -d '\n')"
	@echo "[$(ARCH)] Generating .stp file..."
	@cd $(SYNTH_DIR) && $(QUARTUS_SH) -t ../../scripts/create_stp.tcl $(ARCH) || \
		echo "[$(ARCH)] Warning: create_stp.tcl failed. Using existing .stp file if any."
	@echo "[$(ARCH)] Starting SignalTap compilation..."
	@SECONDS=0; \
	$(QUARTUS_SH) -t scripts/build_fpga.tcl $(ARCH) || exit 1; \
	echo "[$(ARCH)] SignalTap build completed in $$SECONDS seconds"


# Capture SignalTap data from the programmed FPGA.
# Requires the FPGA to be programmed with a SignalTap-enabled .sof.
# Usage: make capture ARCH=pipeline
.PHONY: capture
capture:
	@echo "[$(ARCH)] Running SignalTap capture..."
	@mkdir -p $(CROSS_VAL_DIR) 2>/dev/null || true
	$(QUARTUS_STP) -t scripts/run_capture.tcl $(ARCH) $(CROSS_VAL_DIR)


# Parse captured SignalTap data and compare with cocotb results.
# Usage: make cross-validate ARCH=pipeline COCOTB_CSV=results/cocotb_pipeline.csv
.PHONY: cross-validate
cross-validate:
	@echo "[$(ARCH)] Cross-validating FPGA vs cocotb..."
	@.venv/bin/python3 scripts/parse_stp_csv.py \
		$(CROSS_VAL_DIR)/capture_$(ARCH).csv \
		$(if $(COCOTB_CSV),--cocotb-csv $(COCOTB_CSV)) \
		--output-dir $(CROSS_VAL_DIR)
	@echo "[$(ARCH)] Cross-validation complete. See $(CROSS_VAL_DIR)/cross_validation_$(ARCH).csv"


# Full pipeline: ELF -> .bin -> .mem -> mem_config.vh -> screen.mif ->
# synthesis -> program FPGA.  The mem target carries the .mif generation, so
# the VGA console shows the program that is being loaded.
.PHONY: flash
flash: check-elf check-project mem $(MEM_CONFIG_VH)
	@echo "[$(ARCH)] Flashing program: $(ELF)"
	@SECONDS=0; \
	$(call quartus_compile,build.tcl); \
	echo "[$(ARCH)] Synthesis completed in $$SECONDS seconds"
	@cd $(SYNTH_DIR) && $(QUARTUS_SH) -t program.tcl
	@echo "[$(ARCH)] Flash complete: $(ELF)"


# One synthesis replica.  The fitter seed is the replica index, so every
# replica is an independent place-and-route of the same design.
REPLICA ?= 1
REPLICA_DIR = $(RESULTS_DIR)/replica_$(REPLICA)

.PHONY: replica
replica: check-project
	@mkdir -p $(REPLICA_DIR)
	@echo "[$(ARCH)] --- Replica $(REPLICA) (SEED=$(REPLICA)) ---"
	@SECONDS=0; \
	$(call quartus_compile,build.tcl,$(REPLICA)); \
	cp $(STA_RPT) $(REPLICA_DIR)/timing.rpt 2>/dev/null || \
		echo "Warning: timing report not found for replica $(REPLICA)"; \
	cp $(FIT_SUMMARY) $(REPLICA_DIR)/fit.summary 2>/dev/null || \
		echo "Warning: fitter summary not found for replica $(REPLICA)"; \
	cp $(SOF_FILE) $(REPLICA_DIR)/$(PROJECT).sof 2>/dev/null || \
		echo "Warning: SOF file not found for replica $(REPLICA)"; \
	python3 scripts/extract_fmax.py $(REPLICA_DIR)/timing.rpt \
		> $(REPLICA_DIR)/fmax.txt 2>/dev/null || \
		echo "Warning: fmax extraction failed for replica $(REPLICA)"; \
	echo "[$(ARCH)] Replica $(REPLICA) done ($$SECONDS seconds)"


.PHONY: replicas
replicas: check-project
	@echo "[$(ARCH)] Running $(N_REPLICAS) synthesis replicas..."
	@mkdir -p $(RESULTS_DIR)
	@for i in $$(seq 1 $(N_REPLICAS)); do \
		replica_dir=$(RESULTS_DIR)/replica_$$i; \
		if [ -d "$$replica_dir" ]; then \
			echo "[$(ARCH)] Replica $$i already exists, skipping. Use make clean-replicas to reset."; \
			continue; \
		fi; \
		$(MAKE) replica ARCH=$(ARCH) REPLICA=$$i || exit 1; \
	done
	@echo "[$(ARCH)] All replicas complete. Results in $(RESULTS_DIR)/"


.PHONY: program
program: check-sof
	@echo "[$(ARCH)] Programming FPGA..."
	@cd $(SYNTH_DIR) && $(QUARTUS_SH) -t program.tcl


.PHONY: program-direct
program-direct: check-sof
	@echo "[$(ARCH)] Programming FPGA directly..."
	$(QUARTUS_PGM) -c "DE-SoC" -m JTAG -o "P;$(SOF_FILE)@2"


.PHONY: build-program
build-program: build program


.PHONY: verify
verify:
	@echo "[$(ARCH)] Running architecture-specific cocotb tests..."
	@$(MAKE) -C $(VERIF_ARCH_DIR)


.PHONY: verify-common
verify-common:
	@echo "Running shared RV32IM instruction tests (ARCH=[$(ARCH)])..."
	@$(MAKE) -C $(VERIF_COMMON_DIR) TOPLEVEL=$(if $(filter pipeline,$(ARCH)),top_pipeline,top_single_cycle)


.PHONY: verify-all
verify-all: verify-common verify

.PHONY: verify-all-sc
verify-all-sc:
	@$(MAKE) verify-common ARCH=single_cycle
	@$(MAKE) verify ARCH=single_cycle

.PHONY: verify-all-pipe
verify-all-pipe:
	@$(MAKE) verify ARCH=pipeline

.PHONY: verify-full
verify-full: verify-all-sc verify-all-pipe
	@echo "All verification tests completed."

.PHONY: report
report:
	@echo ""
	@echo "=== Generating Results Report ==="
	@echo ""
	@echo "Running all verification tests..."
	@$(MAKE) verify-full
	@echo ""
	@echo "Collecting results and generating report..."
	@.venv/bin/python3 scripts/collect_results.py --markdown --latex --csv
	@echo ""
	@echo "Report generated:"
	@echo "  results/results_report.md     (Markdown report)"
	@echo "  results/results_latex.tex     (LaTeX tables for thesis)"
	@echo "  results/results_verification.csv  (Verification data as CSV)"
	@echo "  results/results_synthesis.csv     (Synthesis data as CSV)"
	@echo ""

.PHONY: report-quick
report-quick:
	@echo ""
	@echo "=== Generating Quick Results Report (no test re-run) ==="
	@.venv/bin/python3 scripts/collect_results.py --markdown --latex --csv
	@echo ""
	@echo "Report generated:"
	@echo "  results/results_report.md     (Markdown report)"
	@echo "  results/results_latex.tex     (LaTeX tables for thesis)"
	@echo "  results/results_verification.csv  (Verification data as CSV)"
	@echo "  results/results_synthesis.csv     (Synthesis data as CSV)"
	@echo ""


.PHONY: results
results:
	@echo "=== Results: $(ARCH) ==="
	@if [ ! -d "$(RESULTS_DIR)" ]; then \
		echo "No results found. Run 'make replicas ARCH=$(ARCH)' first."; \
		exit 0; \
	fi; \
	for replica_dir in $(RESULTS_DIR)/replica_*/; do \
		replica=$$(basename $$replica_dir); \
		fmax_file=$$replica_dir/fmax.txt; \
		if [ -f "$$fmax_file" ]; then \
			fmax=$$(cat $$fmax_file); \
			echo "  $$replica: $$fmax"; \
		else \
			echo "  $$replica: fmax not available"; \
		fi; \
	done


.PHONY: results-all
results-all:
	@$(MAKE) results ARCH=single_cycle
	@$(MAKE) results ARCH=pipeline


.PHONY: status
status:
	@echo "=== Project Status ==="
	@for arch in $(VALID_ARCHS); do \
		echo ""; \
		echo "  Architecture: $$arch"; \
		sof=synthesis/$$arch/output_files/$(PROJECT_$$arch).sof; \
		if [ -f "$$sof" ]; then \
			echo "  SOF : found ($$(ls -lh $$sof | awk '{print $$5}'))"; \
		else \
			echo "  SOF : not found"; \
		fi; \
		replica_count=$$(ls -d results/$$arch/replica_* 2>/dev/null | wc -l | tr -d ' '); \
		echo "  Replicas completed: $$replica_count / $(N_REPLICAS)"; \
	done
	@echo ""


.PHONY: clean
clean:
	@echo "[$(ARCH)] Cleaning synthesis artifacts..."
	@rm -rf $(SYNTH_DIR)/db \
	        $(SYNTH_DIR)/incremental_db \
	        $(SYNTH_DIR)/output_files \
	        $(SYNTH_DIR)/simulation
	@find $(SYNTH_DIR) -maxdepth 1 \
		\( -name "*.rpt" -o -name "*.summary" -o -name "*.qws" \
		-o -name "*.jdi" -o -name "*.pin" -o -name "*.done" \
		-o -name "*.qdf" \) -delete
	@echo "[$(ARCH)] Clean complete."


.PHONY: clean-all
clean-all:
	@$(MAKE) clean ARCH=single_cycle
	@$(MAKE) clean ARCH=pipeline


.PHONY: clean-replicas
clean-replicas:
	@echo "[$(ARCH)] Removing replica results..."
	@rm -rf $(RESULTS_DIR)/replica_*
	@echo "[$(ARCH)] Replica results removed."


.PHONY: clean-replicas-all
clean-replicas-all:
	@$(MAKE) clean-replicas ARCH=single_cycle
	@$(MAKE) clean-replicas ARCH=pipeline


.PHONY: rebuild
rebuild: clean build


.PHONY: mem
mem: $(BUILD_DIR)/imem.mem $(BUILD_DIR)/dmem.mem $(SCREEN_MIF)

# Regenerate the VGA console artifacts on their own: the video-memory images
# (.mif), the field maps and the two screen writers.
.PHONY: screen
screen: $(IMEM_MEM) $(DMEM_MEM)
	IMEM=$(IMEM_MEM) DMEM=$(DMEM_MEM) bash scripts/gen_screen_artifacts.sh

# The binary is rebuilt whenever an ELF is given.  Timestamps alone are not
# enough: two different programs can carry the same mtime, and the resulting
# bitstream would silently hold the previous program.
ifneq ($(ELF),)
$(BUILD_DIR)/program.bin: FORCE
	@mkdir -p $(BUILD_DIR)
	riscv-none-elf-objcopy -O binary $(ELF) $@
endif

$(BUILD_DIR)/imem.mem: $(BUILD_DIR)/program.bin
	python3 scripts/elf_to_mem.py $< $(IMEM_DEPTH) $@

$(BUILD_DIR)/dmem.mem: $(BUILD_DIR)/program.bin
	python3 scripts/elf_to_mem.py $< $(DMEM_DEPTH) $@


.PHONY: check-elf
check-elf:
	@if [ -z "$(ELF)" ]; then \
		echo "Error: ELF is not set."; \
		echo "Usage: make flash ELF=path/to/program.elf"; \
		exit 1; \
	fi
	@if [ ! -f "$(ELF)" ]; then \
		echo "Error: ELF file not found: $(ELF)"; \
		exit 1; \
	fi


.PHONY: check-sof
check-sof:
	@if [ ! -f "$(SOF_FILE)" ]; then \
		echo "Error: SOF not found at $(SOF_FILE)"; \
		echo "Run 'make build ARCH=$(ARCH)' first."; \
		exit 1; \
	fi


.PHONY: check-project
check-project:
	@if [ ! -f "$(SYNTH_DIR)/$(PROJECT).qpf" ]; then \
		echo "Error: Quartus project not found at $(SYNTH_DIR)/$(PROJECT).qpf"; \
		echo "Run 'make setup ARCH=$(ARCH)' first."; \
		exit 1; \
	fi


.PHONY: thesis
thesis:
	@echo "[thesis] Experimental campaign: preflight, synthesis, verification, benchmarks, artifacts"
	@PATH="$(VENV_BIN):$$PATH" $(VENV_PY) scripts/run_experiment.py

# Same campaign without the synthesis replicas: it reuses the replicas that
# are already in results/ and refreshes everything else.
.PHONY: thesis-quick
thesis-quick:
	@echo "[thesis] Experimental campaign without the synthesis replicas"
	@PATH="$(VENV_BIN):$$PATH" $(VENV_PY) scripts/run_experiment.py \
		--stages preflight verify benchmarks artifacts

# Programs the DE1-SoC with every benchmark and prints the values that the
# console must show, for the photographs of the hardware evidence.
.PHONY: thesis-hardware
thesis-hardware:
	@echo "[thesis] Hardware validation on the DE1-SoC"
	@PATH="$(VENV_BIN):$$PATH" $(VENV_PY) scripts/run_experiment.py --stages hardware

.PHONY: help
help:
	@echo ""
	@echo "Usage: make <target> [ARCH=single_cycle|pipeline] [N_REPLICAS=5] [ELF=path]"
	@echo ""
	@echo "  ARCH defaults to 'single_cycle' if not specified."
	@echo ""
	@echo "Synthesis & Flash"
	@echo "  flash ELF=<path>   Full pipeline: ELF --> .mem --> synthesis --> program FPGA"
	@echo "  setup              Create Quartus project (run once per arch)"
	@echo "  sync               Re-register RTL source files after adding new modules"
	@echo "  sync-all           Sync both architectures"
	@echo "  build              Single synthesis run (requires .mem files)"
	@echo "  build-fpga         Build with SignalTap II for FPGA validation"
	@echo "  replicas           Run N_REPLICAS synthesis runs, extract Fmax"
	@echo "  rebuild            Clean then build"
	@echo ""
	@echo "FPGA Validation"
	@echo "  capture            Capture SignalTap data from programmed FPGA"
	@echo "  cross-validate     Parse captured data and compare vs cocotb"
	@echo "                     (set COCOTB_CSV=path to cocotb results CSV)"
	@echo ""
	@echo "Programming"
	@echo "  program            Program FPGA via TCL script (no rebuild)"
	@echo "  program-direct     Program FPGA via quartus_pgm directly"
	@echo "  build-program      Build then program"
	@echo ""
	@echo "Memory"
	@echo "  mem ELF=<path>     Generate .mem files from ELF without synthesizing"
	@echo "  screen             Regenerate the VGA console artifacts (.mif, writers)"
	@echo ""
	@echo "Verification"
	@echo "  verify             Run architecture-specific cocotb tests"
	@echo "  verify-common      Run shared RV32IM instruction tests"
	@echo "  verify-all         Run common and architecture-specific tests"
	@echo "  verify-all-sc      Run ALL single-cycle tests (common + arch)"
	@echo "  verify-all-pipe    Run ALL pipeline tests"
	@echo "  verify-full        Run ALL tests for both architectures"
	@echo ""
	@echo "Results"
	@echo "  report             Run all tests, then generate report + LaTeX tables"
	@echo "  report-quick       Generate report from existing results (no re-run)"
	@echo "  results            Show Fmax per replica for ARCH"
	@echo "  results-all        Show Fmax for both architectures"
	@echo "  status             Show build and replica status for all archs"
	@echo ""
	@echo "Cleaning"
	@echo "  clean              Remove synthesis artifacts for ARCH"
	@echo "  clean-all          Remove synthesis artifacts for both archs"
	@echo "  clean-replicas     Remove replica results for ARCH"
	@echo "  clean-replicas-all Remove replica results for both archs"
	@echo ""
	@echo "Thesis"
	@echo "  thesis             Full experimental campaign (synthesis, verification,"
	@echo "                     benchmarks, tables, figures, protocol, chapter)"
	@echo "  thesis-quick       Same campaign reusing the existing replicas"
	@echo "  thesis-hardware    Program the DE1-SoC and print the photo checklist"
	@echo ""
