/* Capture the upstream CRC checks without modifying the EEMBC submodule. */
#include "core_portme.h"

/* Word-sized fields make this record readable through DMEM/SignalTap. */
volatile ee_u32 coremark_validation[16];

static void capture_validation(void *result_ptr, ee_u16 seedcrc,
                               ee_s16 known_id, ee_u16 *list_crc,
                               ee_u16 *matrix_crc, ee_u16 *state_crc);

/* The hook sees the same results and expected CRC tables as upstream main. */
#define main coremark_entry
#define portable_fini(port)                                                   \
    do {                                                                     \
        capture_validation(results, seedcrc, known_id, list_known_crc,         \
                           matrix_known_crc, state_known_crc);               \
        portable_fini(port);                                                  \
    } while (0)
#include "src/core_main.c"
#undef portable_fini
#undef main

static void capture_validation(void *result_ptr, ee_u16 seedcrc,
                               ee_s16 known_id, ee_u16 *list_crc,
                               ee_u16 *matrix_crc, ee_u16 *state_crc)
{
    core_results *result = result_ptr;
    ee_u32 errors = 0;
    coremark_validation[0] = 0x434d5631; /* CMV1 */
    coremark_validation[2] = seedcrc;
    coremark_validation[3] = result->crclist;
    coremark_validation[4] = result->crcmatrix;
    coremark_validation[5] = result->crcstate;
    coremark_validation[9] = result->crc;
    coremark_validation[10] = result->iterations;
    coremark_validation[11] = result->execs;
    if (known_id < 0 || result->execs != ALL_ALGORITHMS_MASK
        || result->iterations == 0)
        errors++;
    else
    {
        coremark_validation[6] = list_crc[known_id];
        coremark_validation[7] = matrix_crc[known_id];
        coremark_validation[8] = state_crc[known_id];
        errors += result->crclist != list_crc[known_id];
        errors += result->crcmatrix != matrix_crc[known_id];
        errors += result->crcstate != state_crc[known_id];
    }
    errors += check_data_types();
    coremark_validation[12] = errors;
    /* Internal timing is unavailable. Functional success is independent of it. */
    coremark_validation[13] = 0;
    coremark_validation[1] = errors == 0 ? 1 : 2;
}

int main(void)
{
    coremark_entry();
    return coremark_validation[1] == 1 ? 0 : 1;
}
