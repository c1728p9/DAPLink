/**
 * @file    log.c
 * @brief   Implementation of log.h
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

#include <string.h>

#include "log.h"
#include "virtual_fs.h"
#include "cortex_m.h"
#include "util.h"

static const vfs_filename_t log_file_name = "LOG     TXT";
static const uint32_t log_buf_size = 1024;
static uint8_t log_buf[log_buf_size];
static uint32_t log_buf_head = 0;
static cortex_int_state_t log_isr_state;
static uint32_t log_lock_count = 0;
static bool init_done = 0;

static uint32_t read_file_log_txt(uint32_t sector_offset, uint8_t *data, uint32_t num_sectors);

void log_lock()
{
    cortex_int_state_t isr_state;
    isr_state = cortex_int_get_and_disable();
    if (0 == log_lock_count) {
        log_isr_state = isr_state;
    }
    log_lock_count++;
}

void log_unlock()
{
    log_lock_count--;
    if (0 == log_lock_count) {
        cortex_int_restore(log_isr_state);
    }
    
}

void log_write_hex8(uint8_t value)
{
    static const char nybble_chars[] = "0123456789abcdef";
    log_buf[log_buf_head] = nybble_chars[(value >> 4) & 0x0F ];
    log_buf_head = (log_buf_head + 1) % log_buf_size;
    log_buf[log_buf_head] = nybble_chars[(value >> 0) & 0x0F ];
    log_buf_head = (log_buf_head + 1) % log_buf_size;
}

void log_write_hex16(uint16_t value)
{
    log_write_hex8((value >> 8) & 0xFF);
    log_write_hex8((value >> 0) & 0xFF);
}

void log_write_hex32(uint32_t value)
{
    log_write_hex8((value >> 0x18) & 0xFF);
    log_write_hex8((value >> 0x10) & 0xFF);
    log_write_hex8((value >> 0x08) & 0xFF);
    log_write_hex8((value >> 0x00) & 0xFF);
}

void log_write_uint32(uint32_t value)
{
    static char buf[16];
    uint32_t size;
    int pos;

    size = util_write_uint32(buf, value);
    for (pos = 0; pos < size; pos++) {
        log_buf[log_buf_head] = buf[pos];
        log_buf_head = (log_buf_head + 1) % log_buf_size;
    }
}

void log_write_string(const char *data)
{
    uint32_t pos = 0;

    while (0 != data[pos]) {
        log_buf[log_buf_head] = data[pos];
        log_buf_head = (log_buf_head + 1) % log_buf_size;
        pos++;
    }
}

void log_init()
{
    memset(log_buf, ' ', sizeof(log_buf));
    init_done = 1;
}

void log_build_filesystem()
{
    vfs_file_t file_handle;
    util_assert(init_done);
    file_handle = vfs_create_file(log_file_name, read_file_log_txt, 0, log_buf_size);
    vfs_file_set_attr(file_handle, (vfs_file_attr_bit_t)0); // Remove read only attribute
}

// File callback to be used with vfs_add_file to return file contents
static uint32_t read_file_log_txt(uint32_t sector_offset, uint8_t *data, uint32_t num_sectors)
{
    uint32_t offset;
    uint32_t copy_size;

    offset = VFS_SECTOR_SIZE * sector_offset;
    copy_size = VFS_SECTOR_SIZE * num_sectors;

    if (offset >= log_buf_size) {
        // No overlap with the log
        return 0;
    }

    if (offset + copy_size > log_buf_size) {
        copy_size = log_buf_size - offset;
    }

    memcpy(data, log_buf + offset, copy_size);

    return copy_size;
}
