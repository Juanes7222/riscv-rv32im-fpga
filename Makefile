ARCH        ?= single_cycle
N_REPLICAS  ?= 5

VALID_ARCHS := single_cycle pipeline

# Validate ARCH
ifeq ($(filter $(ARCH), $(VALID_ARCHS)),)
$(error Invalid ARCH='$(ARCH)'. Valid values: $(VALID_ARCHS))
endif

# Paths
SYNTH_DIR        = synthesis/$(ARCH)
RESULTS_DIR      = results/$(ARCH)
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

SOF_FILE = $(SYNTH_DIR)/output_files/$(PROJECT).sof
STA_RPT  = $(SYNTH_DIR)/output_files/$(PROJECT).sta.rpt

# Default target: show help
all: help

# Project setup (run once before first build)
.PHONY: setup
setup:
	@echo "[$(ARCH)] Creating Quartus project..."
	@cd $(SYNTH_DIR) && $(QUARTUS_SH) -t setup.tcl
	@echo "[$(ARCH)] Project created. Run 'make build ARCH=$(ARCH)' to synthesize."

# Sync RTL source files into existing project (run after adding new .sv files)
.PHONY: sync
sync: check-project
	@echo "[$(ARCH)] Syncing RTL source files..."
	@cd $(SYNTH_DIR) && $(QUARTUS_SH) -t sync.tcl

.PHONY: sync-all
sync-all:
	@$(MAKE) sync ARCH=single_cycle
	@$(MAKE) sync ARCH=pipeline

# Single synthesis run
.PHONY: build
build: check-project
	@echo "[$(ARCH)] Starting synthesis..."
	@SECONDS=0; \
	cd $(SYNTH_DIR) && $(QUARTUS_SH) -t build.tcl; \
	echo "[$(ARCH)] Synthesis completed in $$SECONDS seconds"

# Replica loop for experimental protocol
.PHONY: replicas
replicas: check-project
	@echo "[$(ARCH)] Running $(N_REPLICAS) synthesis replicas..."
	@mkdir -p $(RESULTS_DIR)
	@for i in $$(seq -w 1 $(N_REPLICAS)); do \
		replica_dir=$(RESULTS_DIR)/replica_$$i; \
		if [ -d "$$replica_dir" ]; then \
			echo "[$(ARCH)] Replica $$i already exists, skipping. Use make clean-replicas to reset."; \
			continue; \
		fi; \
		echo "[$(ARCH)] --- Replica $$i / $(N_REPLICAS) ---"; \
		SECONDS=0; \
		cd $(SYNTH_DIR) && $(QUARTUS_SH) -t build.tcl; \
		cd - > /dev/null; \
		mkdir -p $$replica_dir; \
		cp $(STA_RPT) $$replica_dir/timing.rpt 2>/dev/null || \
			echo "Warning: timing report not found for replica $$i"; \
		cp $(SOF_FILE) $$replica_dir/$(PROJECT).sof 2>/dev/null || \
			echo "Warning: SOF file not found for replica $$i"; \
		python3 scripts/extract_fmax.py $$replica_dir/timing.rpt \
			> $$replica_dir/fmax.txt 2>/dev/null || \
			echo "Warning: fmax extraction failed for replica $$i"; \
		echo "[$(ARCH)] Replica $$i done ($$SECONDS seconds)"; \
	done
	@echo "[$(ARCH)] All replicas complete. Results in $(RESULTS_DIR)/"

# Program FPGA
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

# Verification
.PHONY: verify
verify:
	@echo "[$(ARCH)] Running architecture-specific cocotb tests..."
	@$(MAKE) -C $(VERIF_ARCH_DIR)

.PHONY: verify-common
verify-common:
	@echo "Running shared RV32IM instruction tests..."
	@$(MAKE) -C $(VERIF_COMMON_DIR)

.PHONY: verify-all
verify-all: verify-common verify

# Results summary
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

# Status
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

# Clean
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

# Guards
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

# Help
.PHONY: help
help:
	@echo ""
	@echo "Usage: make <target> [ARCH=single_cycle|pipeline] [N_REPLICAS=5]"
	@echo ""
	@echo "  ARCH defaults to 'single_cycle' if not specified."
	@echo ""
	@echo "Synthesis"
	@echo "  setup              Create Quartus project (run once per arch)"
	@echo "  sync               Re-register RTL source files after adding modules"
	@echo "  sync-all           Sync both architectures"
	@echo "  build              Single synthesis run"
	@echo "  replicas           Run N_REPLICAS synthesis runs, extract Fmax"
	@echo "  rebuild            Clean then build"
	@echo ""
	@echo "Programming"
	@echo "  program            Program FPGA via TCL script (no rebuild)"
	@echo "  program-direct     Program FPGA via quartus_pgm directly"
	@echo "  build-program      Build then program"
	@echo ""
	@echo "Verification"
	@echo "  verify             Run architecture-specific cocotb tests"
	@echo "  verify-common      Run shared RV32IM instruction tests"
	@echo "  verify-all         Run common and architecture-specific tests"
	@echo ""
	@echo "Results"
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