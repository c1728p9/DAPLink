/**
 * @file    uart.c
 * @brief
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

#include "string.h"

#include "stm32f1xx.h"
#include "uart.h"
#include "gpio.h"
#include "util.h"

// For usart
#define CDC_UART                     USART2
#define CDC_UART_ENABLE()            __HAL_RCC_USART2_CLK_ENABLE()
#define CDC_UART_DISABLE()           __HAL_RCC_USART2_CLK_DISABLE()
#define CDC_UART_IRQn                USART2_IRQn
#define CDC_UART_IRQn_Handler        USART2_IRQHandler

#define UART_PINS_PORT_ENABLE()      __HAL_RCC_GPIOA_CLK_ENABLE()
#define UART_PINS_PORT_DISABLE()     __HAL_RCC_GPIOA_CLK_DISABLE()

#define UART_TX_PORT                 GPIOA
#define UART_TX_PIN                  GPIO_PIN_2

#define UART_RX_PORT                 GPIOA
#define UART_RX_PIN                  GPIO_PIN_3

#define UART_CTS_PORT                GPIOA
#define UART_CTS_PIN                 GPIO_PIN_0

#define UART_RTS_PORT                GPIOA
#define UART_RTS_PIN                 GPIO_PIN_1

// Size must be 2^n for using quick wrap around
#define  BUFFER_SIZE (512)

typedef struct {
    volatile uint8_t  data[BUFFER_SIZE];
    volatile uint32_t head;
    volatile uint32_t tail;
}ring_buf_t;

static ring_buf_t write_buffer, read_buffer;

static uint32_t tx_in_progress = 0;

static UART_Configuration configuration = {
    .Baudrate = 9600,
    .DataBits = UART_DATA_BITS_8,
    .Parity = UART_PARITY_NONE,
    .StopBits = UART_STOP_BITS_1,
    .FlowControl = UART_FLOW_CONTROL_NONE,
};

extern uint32_t SystemCoreClock;



static void clear_buffers(void)
{
    memset((void *)&read_buffer, 0xBB, sizeof(ring_buf_t));
    read_buffer.head = 0;
    read_buffer.tail = 0;
    memset((void *)&write_buffer, 0xBB, sizeof(ring_buf_t));
    write_buffer.head = 0;
    write_buffer.tail = 0;
}

static int16_t read_available(ring_buf_t *buffer)
{
    return ((BUFFER_SIZE + buffer->head - buffer->tail) % BUFFER_SIZE);
}

static int16_t write_free(ring_buf_t *buffer)
{
    int16_t cnt;

    cnt = (buffer->tail - buffer->head - 1);
    if(cnt < 0)
        cnt += BUFFER_SIZE;

    return cnt;
}

int32_t uart_initialize(void)
{
    uint16_t data_bits;
    uint16_t parity;
    uint16_t stop_bits;

    GPIO_InitTypeDef GPIO_InitStructure;
    USART_InitTypeDef USART_InitStructure;

    CDC_UART_ENABLE();
    UART_PINS_PORT_ENABLE();

    //TX pin
    GPIO_InitStructure.Pin = UART_TX_PIN;
    GPIO_InitStructure.Speed = GPIO_SPEED_FREQ_HIGH;
    GPIO_InitStructure.Mode = GPIO_MODE_AF_PP;
    HAL_GPIO_Init(UART_TX_PORT, &GPIO_InitStructure);
    //RX pin
    GPIO_InitStructure.Pin = UART_RX_PIN;
    GPIO_InitStructure.Speed = GPIO_SPEED_FREQ_HIGH;
    GPIO_InitStructure.Mode = GPIO_MODE_INPUT;
    GPIO_InitStructure.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(UART_RX_PORT, &GPIO_InitStructure);
    //CTS pin, input
    GPIO_InitStructure.Pin = UART_CTS_PIN;
    GPIO_InitStructure.Speed = GPIO_SPEED_FREQ_HIGH;
    GPIO_InitStructure.Mode = GPIO_MODE_INPUT;
    GPIO_InitStructure.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(UART_CTS_PORT, &GPIO_InitStructure);
    //RTS pin, output low
    HAL_GPIO_WritePin(UART_RTS_PORT, UART_RTS_PIN, GPIO_PIN_RESET);
    GPIO_InitStructure.Pin = UART_RTS_PIN;
    GPIO_InitStructure.Speed = GPIO_SPEED_FREQ_HIGH;
    GPIO_InitStructure.Mode = GPIO_MODE_OUTPUT_PP;
    HAL_GPIO_Init(UART_RTS_PORT, &GPIO_InitStructure);

    NVIC_ClearPendingIRQ(CDC_UART_IRQn);
    NVIC_EnableIRQ(CDC_UART_IRQn);

    return 1;
}

int32_t uart_uninitialize(void)
{
    CDC_UART->CR1 &= ~(USART_IT_TXE | USART_IT_RXNE);
    clear_buffers();
    return 1;
}

int32_t uart_reset(void)
{
    uart_initialize();
    tx_in_progress = 0;
    return 1;
}

int32_t uart_set_configuration(UART_Configuration *config)
{
    uint16_t data_bits;
    uint16_t parity;
    uint16_t stop_bits;
    
    UART_HandleTypeDef uart_handle;
    HAL_StatusTypeDef status;

    memset(&uart_handle, 0, sizeof(uart_handle));
    uart_handle.Instance = CDC_UART;

    // parity
    configuration.Parity = config->Parity;
    if(config->Parity == UART_PARITY_ODD) {
        uart_handle.Init.Parity = HAL_UART_PARITY_ODD;
    } else if(config->Parity == UART_PARITY_EVEN) {
        uart_handle.Init.Parity = HAL_UART_PARITY_EVEN;
    } else if(config->Parity == UART_PARITY_NONE) {
        uart_handle.Init.Parity = HAL_UART_PARITY_NONE;
    } else {   //Other not support
        uart_handle.Init.Parity = HAL_UART_PARITY_NONE;
        configuration.Parity = UART_PARITY_NONE;
    }

    // stop bits
    configuration.StopBits = config->StopBits;
    if(config->StopBits == UART_STOP_BITS_2) {
        uart_handle.Init.StopBits = UART_STOPBITS_2;
    } else if(config->StopBits == UART_STOP_BITS_1_5) {
        uart_handle.Init.StopBits = UART_STOPBITS_2;
        configuration.StopBits = UART_STOP_BITS_2;
    } else if(config->StopBits == UART_STOP_BITS_1) {
        uart_handle.Init.StopBits = UART_STOPBITS_1;
    } else {
        uart_handle.Init.StopBits = UART_STOPBITS_1;
        configuration.StopBits = UART_STOP_BITS_1;
    }

    //Only 8 bit support
    configuration.DataBits = UART_DATA_BITS_8;
    uart_handle.Init.WordLength = UART_WORDLENGTH_8B;

    // No flow control
    configuration.FlowControl = UART_FLOW_CONTROL_NONE;
    uart_handle.Init.HwFlowCtl  = UART_HWCONTROL_NONE;
    
    // Specified baudrate
    configuration.Baudrate = config->Baudrate;
    uart_handle.Init.BaudRate = config->Baudrate;

    // TX and RX
    uart_handle.Init.Mode = UART_MODE_TX_RX;
    
    // Disable uart and tx/rx interrupt
    CDC_UART->CR1 &= ~(USART_IT_TXE | USART_IT_RXNE);

    clear_buffers();

    status = HAL_UART_DeInit(&uart_handle);
    util_assert(HAL_OK == status);
    status = HAL_UART_Init(&uart_handle);
    util_assert(HAL_OK == status);
    (void)status;

    CDC_UART->CR1 |= USART_IT_RXNE;

    return 1;
}

int32_t uart_get_configuration(UART_Configuration *config)
{
    config->Baudrate = configuration.Baudrate;
    config->DataBits = configuration.DataBits;
    config->Parity   = configuration.Parity;
    config->StopBits = configuration.StopBits;
    config->FlowControl = UART_FLOW_CONTROL_NONE;

    return 1;
}

int32_t uart_write_free(void)
{
    return write_free(&write_buffer);
}

//TODO - update code to use atomic queues
int32_t uart_write_data(uint8_t *data, uint16_t size)
{
    uint32_t cnt, len;

    if(size == 0)
        return 0;

    len = write_free(&write_buffer);
    if(len > size)
        len = size;

    cnt = len;
    while(len--) {
        write_buffer.data[write_buffer.head++] = *data++;
        if(write_buffer.head >= BUFFER_SIZE)
            write_buffer.head = 0;
    }

    if(!tx_in_progress) {
        tx_in_progress = 1;
        //TODO - remove if unnecissary
        //USART_SendData(CDC_UART, write_buffer.data[write_buffer.tail++]);
        //if(write_buffer.tail >= BUFFER_SIZE)
        //    write_buffer.tail = 0;

        // Enale tx interrupt
        CDC_UART->CR1 |= USART_IT_TXE;
    }

    return cnt;
}

int32_t uart_read_data(uint8_t *data, uint16_t size)
{
    uint32_t cnt, len;

    if(size == 0) {
        return 0;
    }

    len = read_available(&read_buffer);
    if(len > size)
        len = size;

    cnt = len;
    while(len--) {
        *data++ = read_buffer.data[read_buffer.tail++];
        if(read_buffer.tail >= BUFFER_SIZE)
            read_buffer.tail = 0;
    }

    return cnt;
}

void CDC_UART_IRQn_Handler(void)
{
    uint8_t  dat;
    uint32_t cnt;
    uint32_t sr;

    sr = CDC_UART->SR;

    if (sr & USART_SR_RXNE) {
        cnt = write_free(&read_buffer);
        dat = CDC_UART->DR;
        if(cnt) {
            read_buffer.data[read_buffer.head++] = dat;
            if(read_buffer.head >= BUFFER_SIZE)
                read_buffer.head = 0;
            if(cnt == 1) {
                // for flow control, need to set RTS = 1
            }
        }
    }

    if (sr & USART_SR_TXE) {
        cnt = read_available(&write_buffer);
        if(cnt == 0) {
            CDC_UART->CR1 &= ~USART_IT_TXE;
            tx_in_progress = 0;
        }
        else {
            CDC_UART->DR = write_buffer.data[write_buffer.tail++];
            if(write_buffer.tail >= BUFFER_SIZE)
                write_buffer.tail = 0;
            tx_in_progress = 1;
        }
    }
}
