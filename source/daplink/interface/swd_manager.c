/**
 * @file    swd_manager.c
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

#include "swd_manager.h"
#include "util.h"
#include "RTL.h"

static OS_MUT mutex;
static OS_TID mutex_owner;
static swd_user_t user;

void swd_manager_init()
{
    os_mut_init(&mutex);
    user = SWD_USER_NONE;
    mutex_owner = 0;
}

void swd_manager_lock()
{
    os_mut_wait(&mutex, 0xFFFF);
    mutex_owner = os_tsk_self();
}

void swd_manager_unlock()
{
    mutex_owner = 0;
    os_mut_release(&mutex);
}

uint8_t swd_manager_is_lock_owner()
{
    return os_tsk_self() == mutex_owner;
}

uint8_t swd_manager_start(swd_user_t operation)
{
    util_assert(swd_manager_is_lock_owner());

    user = operation;
    return 1;
}

swd_user_t swd_manager_user()
{
    util_assert(swd_manager_is_lock_owner());

    return user;
}

void swd_manager_finish(swd_user_t operation)
{
    util_assert(swd_manager_is_lock_owner());
    util_assert(operation == user);

    user = SWD_USER_NONE;
}
