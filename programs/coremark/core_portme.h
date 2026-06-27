/*
 * CoreMark platform configuration for RV32IM bare-metal.
 * No OS, no stdio, no heap — everything on stack, results via tohost.
 */

#ifndef CORE_PORTME_H
#define CORE_PORTME_H

/************************/
/* Feature configuration */
/************************/
#define HAS_FLOAT         0   /* RV32IM has no FPU */
#define HAS_TIME_H        0   /* No OS time.h */
#define USE_CLOCK         0   /* No clock() function */
#define HAS_STDIO         0   /* No stdio */
#define HAS_PRINTF        0   /* We supply ee_printf (no-op stub) */

/************************/
/* Compiler identification */
/************************/
#define COMPILER_VERSION "GCC 14.2.0"
#define COMPILER_FLAGS   "-march=rv32im -mabi=ilp32 -O2 -nostdlib"
#define MEM_LOCATION     "STACK"

/************************/
/* Data types */
/************************/
typedef signed   short  ee_s16;
typedef unsigned short  ee_u16;
typedef signed   int    ee_s32;
typedef unsigned int    ee_u32;
typedef unsigned char   ee_u8;
typedef ee_u32         ee_ptr_int;
typedef ee_u32         ee_size_t;

#ifndef NULL
#define NULL ((void *)0)
#endif

#define align_mem(x) (void *)(4 + (((ee_ptr_int)(x) - 1) & ~3))

/************************/
/* Timing */
/************************/
#define CORETIMETYPE ee_u32
typedef ee_u32 CORE_TICKS;

/************************/
/* Seed method: volatile variables (no command-line args) */
/************************/
#ifndef SEED_METHOD
#define SEED_METHOD SEED_VOLATILE
#endif

/************************/
/* Memory method: stack-allocated */
/************************/
#ifndef MEM_METHOD
#define MEM_METHOD MEM_STACK
#endif

/************************/
/* Single-threaded */
/************************/
#ifndef MULTITHREAD
#define MULTITHREAD 1
#define USE_PTHREAD 0
#define USE_FORK    0
#define USE_SOCKET  0
#endif

#define MAIN_HAS_NOARGC   1
#define MAIN_HAS_NORETURN 0   /* main() returns normally, start.S handles tohost */

/************************/
/* Iterations: set via -DITERATIONS=N in Makefile.
   For FPGA performance run: N=2000 (or whatever yields ~10 secs).
   For validation/simulation: N=10. */
/************************/
#ifndef ITERATIONS
#define ITERATIONS 2000
#endif

/* Data size: defined in coremark.h as 2*1000 = 2000 (performance run). */

/* CLOCKS_PER_SEC: unused (HAS_TIME_H=0, barebones_clock returns 0). */
#define CLOCKS_PER_SEC 1

/************************/
/* Portable structure */
/************************/
extern ee_u32 default_num_contexts;

typedef struct CORE_PORTABLE_S {
    ee_u8 portable_id;
} core_portable;

void portable_init(core_portable *p, int *argc, char *argv[]);
void portable_fini(core_portable *p);

/* Stub: called by CoreMark for diagnostic output. Implemented as no-op. */
int ee_printf(const char *fmt, ...);

#endif /* CORE_PORTME_H */
