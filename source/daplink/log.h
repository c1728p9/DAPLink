/**
 * @file    log.h
 * @brief   methods to get information about the board
 *
 * DAPLink Interface Firmware
 * Copyright (c) 2016, ARM Limited, All Rights Reserved
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

#ifndef LOG_H
#define LOG_H

#include "stdbool.h"
#include "stdint.h"

#ifdef __cplusplus
extern "C" {
#endif

void log_lock(void);
void log_unlock(void);
void log_write_hex8(uint8_t value);
void log_write_hex16(uint16_t value);
void log_write_hex32(uint32_t value);
void log_write_uint32(uint32_t value);
void log_write_string(const char *data);
void log_init(void);
void log_build_filesystem(void);

#ifdef __cplusplus
}
#endif

#endif
