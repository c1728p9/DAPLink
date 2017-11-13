/**
 * @file    swd_manager.h
 * @brief   Manager for shared access to SWD
 *
 * DAPLink Interface Firmware
 * Copyright (c) 2017-2017, ARM Limited, All Rights Reserved
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

#ifndef SWD_MANAGER_H
#define SWD_MANAGER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    SWD_USER_NONE,
    SWD_USER_SETUP,
    SWD_USER_RESET_BUTTON,
    SWD_USER_TARGET_FLASH,
    SWD_USER_CMSIS_DAP,
    SWD_USER_CDC_BREAK
} swd_user_t;

/**
 * Initialize the swd manager
 */
void swd_manager_init(void);

/**
 * Acquire exclusive access to the swd manager
 *
 * @note this lock must be held when performing any swd operation
 */
void swd_manager_lock(void);

/**
 * Release exclusive access of the swd manager
 */
void swd_manager_unlock(void);

/**
 * Check if the current thread is the owner of the swd manager lock
 *
 * @return 1 if the current thread is the owner otherwise 0
 */
uint8_t swd_manager_is_lock_owner(void);

/**
 * Start an operation which uses SWD
 *
 * @param operation The operation being started
 * @return 1 if the operation is allowed otherwise 0
 * @note the thread calling this function must have locked the swd
 * manager by calling ::swd_manager_lock.
 */
uint8_t swd_manager_start(swd_user_t operation);

/**
 * Check the operation being performed with SWD
 *
 * @return The ongoing operation or SWD_USER_NONE if there is no
 * active operation
 * @note the thread calling this function must have locked the swd
 * manager by calling ::swd_manager_lock.
 */
swd_user_t swd_manager_user(void);

/**
 * Finish an operation which uses SWD
 *
 * @param operation The operation being finished
 * @note the thread calling this function must have locked the swd
 * manager by calling ::swd_manager_lock.
 * @note the operation must have already been started with ::swd_manager_start
 */
void swd_manager_finish(swd_user_t operation);

#ifdef __cplusplus
}
#endif

#endif
