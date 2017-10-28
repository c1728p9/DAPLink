/**
 * @file    swd_lock.c
 * @brief   Implementation of swd_host lock in multithreaded environment.
 *
 * Locking SWD Port prevents concurrent access that would disturb SWD operations.
 * Lock may be assigned to Task (prevents concurrency) and ongoing Operation.
 * Task Lock has higher priority over Operation Lock. Task may lock the unused port,
 * when operation takes place user marks ongoing operation with Operation Lock
 * so noone else in that task (and any other task) may use the port until Operation
 * Lock is cleared. Unlocking Operation still keeps the port locked by Task Lock.
 * Unlocking Task Lock also clears the Operation Lock. Usually Task Lock prevents
 * interrupts by other threads, while Operation Lock helps to decide function trigger.
 *
 * DAPLink Interface Firmware
 * Copyright (c) 2017, ARM Limited, All Rights Reserved
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

#include "swd_host.h"

static OS_MUT _swd_lock_mutex;
static OS_TID _swd_lock_tid;
static swd_lock_operation_t _swd_lock_operation;

/**
 * Setup mutex that will protect SWD Port lock against mutithreaded operations.
 * @return always 1.
 */
uint8_t swd_lock_mutex_init(void)
{
	rt_mut_init(&_swd_lock_mutex);
	return 1;
}

/**
 * Marks SWD Port as Task Locked by a given TID.
 * TID id the current RTX task id and may be obtained by os_tsk_self().
 * @return 1 on success, 0 on failure (may be locked already by others).
 */
uint8_t swd_lock_tid(OS_TID tid)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t locked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	if (swd_lock_check_tid(tid))
	{
		locked = 1;
	}
	else if (!swd_lock_check_tid_any())
	{
		_swd_lock_tid = tid;
		_swd_lock_operation = SWD_LOCK_OPERATION_NONE;
		locked = 1;
	}
	util_assert(locked);
	os_mut_release(&_swd_lock_mutex);
	return locked;
}

uint8_t swd_lock_tid_self(void)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t locked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	locked = swd_lock_tid(os_tsk_self());
	//util_assert(locked);
	os_mut_release(&_swd_lock_mutex);
	return locked;
}

uint8_t swd_lock_operation(swd_lock_operation_t operation)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t locked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	if (swd_lock_tid_self())
	{
		_swd_lock_operation = operation;
		locked = 1;
	}
	util_assert(locked);
	os_mut_release(&_swd_lock_mutex);
	return locked;
}

/**
 * Check if SWD Port is Task Locked and Operation Locked.
 * @return 1 if locked, 0 if free.
 */
uint8_t swd_lock_check(void)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t locked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	locked = swd_lock_check_tid_any() && swd_lock_check_operation_any();
	//util_assert(locked);
	os_mut_release(&_swd_lock_mutex);
	return locked;
}

/**
 * Verify if SWD Port is already locked for use by a given TID.
 * @tid is the value to compare against os_tsk_self().
 * @return 1 if locked, 0 if free.
 */
uint8_t swd_lock_check_tid(OS_TID tid)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t locked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	locked = (tid == _swd_lock_tid ? 1 : 0);
	//util_assert(locked);
	os_mut_release(&_swd_lock_mutex);
	return locked;
}

uint8_t swd_lock_check_tid_self(void)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t locked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	locked = (swd_lock_check_tid(os_tsk_self()));
	//util_assert(locked);
	os_mut_release(&_swd_lock_mutex);
	return locked;
}

uint8_t swd_lock_check_tid_any(void)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t locked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	locked = (0 != _swd_lock_tid ? 1 : 0);
	//util_assert(locked);
	os_mut_release(&_swd_lock_mutex);
	return locked;
}

/**
 * Verify if SWD Port is already locked by a given owner called from current task.
 * @tid is the value to compare against os_tsk_self().
 * @return 1 if locked, 0 if free.
 */
uint8_t swd_lock_check_operation(swd_lock_operation_t operation)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t locked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	locked = (operation == _swd_lock_operation ? 1 : 0) && swd_lock_check_tid_self();
	util_assert(locked);
	os_mut_release(&_swd_lock_mutex);
	return locked;
}

uint8_t swd_lock_check_operation_any(void)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t locked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	locked = (SWD_LOCK_OPERATION_NONE != _swd_lock_operation ? 1 : 0);
	//util_assert(locked);
	os_mut_release(&_swd_lock_mutex);
	return locked;
}

/**
 * Marks SWD Port as free to use by anyone.
 * @return always 1.
 */
uint8_t swd_unlock(void)
{
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	_swd_lock_tid = 0;
	_swd_lock_operation = SWD_LOCK_OPERATION_NONE;
	os_mut_release(&_swd_lock_mutex);
	return 1;
}

/**
 * Marks SWD Port as free to use. Only given tid can unlock the port.
 * @param *owner is the port owner string.
 * @return 1 on success, 0 on failure (locked already by a different owner).
 */
uint8_t swd_unlock_tid(OS_TID tid)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t unlocked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	if (swd_lock_check_tid(tid))
	{
		swd_unlock();
		unlocked = 1;
	}
	util_assert(unlocked);
	os_mut_release(&_swd_lock_mutex);
	return unlocked;
}

/**
 * Marks SWD Port as free to use. Only given tid can unlock the port.
 * @param *owner is the port owner string.
 * @return 1 on success, 0 on failure (locked already by a different owner).
 */
uint8_t swd_unlock_tid_self(void)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t unlocked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	unlocked = swd_unlock_tid(os_tsk_self());
	//util_assert(unlocked);
	os_mut_release(&_swd_lock_mutex);
	return unlocked;
}

/**
 * Marks SWD Port as free to use for owner. Only owner from locked tid can unlock the port.
 * @param *owner is the port owner string.
 * @return 1 on success, 0 on failure (locked already by a different owner).
 */
uint8_t swd_unlock_operation(swd_lock_operation_t operation)
{
	if (0 == _swd_lock_mutex) return 0;
	uint8_t unlocked = 0;
	os_mut_wait(&_swd_lock_mutex, 0xFFFF);
	if (swd_lock_check_tid_self())
	{
		_swd_lock_operation = SWD_LOCK_OPERATION_NONE;
		unlocked = 1;
	}
	util_assert(unlocked);
	os_mut_release(&_swd_lock_mutex);
	return unlocked;
}
