/**
 * @file    swd_host.h
 * @brief   Host driver for accessing the DAP
 *
 * DAPLink Interface Firmware
 * Copyright (c) 2009-2016, ARM Limited, All Rights Reserved
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may
 * not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef SWDHOST_CM_H
#define SWDHOST_CM_H

#include "util.h"
#include "tasks.h"
#include "RTL.h"
#include "flash_blob.h"
#include "target_reset.h"
#ifdef TARGET_MCU_CORTEX_A
#include "debug_ca.h"
#else
#include "debug_cm.h"
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef enum swd_lock_operation_t {
	SWD_LOCK_OPERATION_NONE = 0,
	SWD_LOCK_OPERATION_HIC,
	SWD_LOCK_OPERATION_HID,
	SWD_LOCK_OPERATION_UMS,
	SWD_LOCK_OPERATION_CDC,
	SWD_LOCK_OPERATION_RESET,
	SWD_LOCK_OPERATION_SETSTATE,
	SWD_LOCK_OPERATION_FLASH,
} swd_lock_operation_t;

uint8_t swd_init(void);
uint8_t swd_off(void);
uint8_t swd_init_debug(void);
uint8_t swd_read_dp(uint8_t adr, uint32_t *val);
uint8_t swd_write_dp(uint8_t adr, uint32_t val);
uint8_t swd_read_ap(uint32_t adr, uint32_t *val);
uint8_t swd_write_ap(uint32_t adr, uint32_t val);
uint8_t swd_read_memory(uint32_t address, uint8_t *data, uint32_t size);
uint8_t swd_write_memory(uint32_t address, uint8_t *data, uint32_t size);
uint8_t swd_flash_syscall_exec(const program_syscall_t *sysCallParam, uint32_t entry, uint32_t arg1, uint32_t arg2, uint32_t arg3, uint32_t arg4);
void swd_set_target_reset(uint8_t asserted);
uint8_t swd_set_target_state_hw(TARGET_RESET_STATE state);
uint8_t swd_set_target_state_sw(TARGET_RESET_STATE state);

uint8_t swd_lock_mutex_init(void);
uint8_t swd_lock_tid(OS_TID tid);
uint8_t swd_lock_tid_self(void);
uint8_t swd_lock_operation(swd_lock_operation_t operation);
uint8_t swd_lock_check(void);
uint8_t swd_lock_check_tid(OS_TID tid);
uint8_t swd_lock_check_tid_self(void);
uint8_t swd_lock_check_tid_any(void);
uint8_t swd_lock_check_operation(swd_lock_operation_t operation);
uint8_t swd_lock_check_operation_any(void);
uint8_t swd_unlock(void);
uint8_t swd_unlock_tid(OS_TID tid);
uint8_t swd_unlock_tid_self(void);
uint8_t swd_unlock_operation(swd_lock_operation_t operation);

#ifdef __cplusplus
}
#endif

#endif
