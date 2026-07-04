TOPLEVEL            ?= top_pipeline
COCOTB_TEST_MODULES  = test_pipeline_smoke,test_pipeline_debug,test_pipeline_rv32i,test_pipeline_rv32m,test_pipeline_rv32mi,test_pipeline_hazards,test_pipeline_control,test_pipeline_cpi

VERILOG_SOURCES = \
    $(SHARED_SRCS) \
    $(SHARED_VGA_SRCS) \
    $(RTL_ROOT)/pipeline/instruction_memory_pipe.sv \
    $(RTL_ROOT)/pipeline/data_memory_pipe.sv \
    $(RTL_ROOT)/pipeline/control_unit.sv \
    $(RTL_ROOT)/pipeline/if_id_register.sv \
    $(RTL_ROOT)/pipeline/id_ex_register.sv \
    $(RTL_ROOT)/pipeline/ex_mem_register.sv \
    $(RTL_ROOT)/pipeline/mem_wb_register.sv \
    $(RTL_ROOT)/pipeline/hazard_detection.sv \
    $(RTL_ROOT)/pipeline/forwarding_unit.sv \
    $(RTL_ROOT)/pipeline/pc_unit.sv \
    $(RTL_ROOT)/pipeline/screen_writer_pipeline.sv \
    $(RTL_ROOT)/pipeline/top_pipeline.sv

export COCOTB_PYTHONPATH := $(shell pwd):$(REPO_ROOT)/verification/reference_model:$(REPO_ROOT)/verification/cocotb/common
export PYTHONPATH := $(shell pwd):$(REPO_ROOT)/verification/reference_model:$(REPO_ROOT)/verification/cocotb/common:$(PYTHONPATH)

include ../common.mk
