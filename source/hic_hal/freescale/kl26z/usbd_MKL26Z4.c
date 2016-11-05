/**
 * @file    usbd_MKL26Z4.h
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

#include "RTL.h"
#include "rl_usb.h"
#include "MKL26Z4.h"
#include "cortex_m.h"
#include "util.h"

#define __NO_USB_LIB_C
#include "usb_config.c"

typedef struct __BUF_DESC {
    uint8_t    stat;
    uint8_t    reserved;
    uint16_t   bc;
    uint32_t   buf_addr;
} BUF_DESC;

BUF_DESC __align(512) BD[(USBD_EP_NUM + 1) * 2 * 2];
uint8_t EPBuf[(USBD_EP_NUM + 1) * 2 * 2][64];
uint8_t OutEpSize[USBD_EP_NUM + 1];

uint32_t Data1              = 0x55555555;
uint32_t EvenOddLastXfer    = 0xFFFFFFFF;
uint8_t SetupBufReady       = 0;

#define BD_OWN_MASK        0x80
#define BD_DATA01_MASK     0x40
#define BD_KEEP_MASK       0x20
#define BD_NINC_MASK       0x10
#define BD_DTS_MASK        0x08
#define BD_STALL_MASK      0x04

#define TX    1
#define RX    0
#define EVEN  0
#define ODD   1
#define DATAX_BIT(Ep, dir)   (1 << (((Ep & 0x0F) * 2) + (1 * dir)))
#define EVENODD_BIT(Ep, dir) (1 << (((Ep & 0x0F) * 2) + (1 * dir)))
#define IDX(Ep, dir, Ev_Odd) ((((Ep & 0x0F) * 4) + (2 * dir) + (1 *  Ev_Odd)))

#define SETUP_TOKEN    0x0D
#define IN_TOKEN       0x09
#define OUT_TOKEN      0x01
#define TOK_PID(idx)   ((BD[idx].stat >> 2) & 0x0F)

inline static void protected_and(uint32_t *addr, uint32_t val)
{
    cortex_int_state_t state;
    state = cortex_int_get_and_disable();
    *addr = *addr & val;
    cortex_int_restore(state);
}
inline static void protected_or(uint32_t *addr, uint32_t val)
{
    cortex_int_state_t state;
    state = cortex_int_get_and_disable();
    *addr = *addr | val;
    cortex_int_restore(state);
}
inline static void protected_xor(uint32_t *addr, uint32_t val)
{
    cortex_int_state_t state;
    state = cortex_int_get_and_disable();
    *addr = *addr ^ val;
    cortex_int_restore(state);
}

/*
 *  USB Device Interrupt enable
 *   Called by USBD_Init to enable the USB Interrupt
 *    Return Value:    None
 */

void USBD_IntrEna(void)
{
    NVIC_EnableIRQ(USB0_IRQn);            /* Enable OTG interrupt               */
}


/*
 *  USB Device Initialize Function
 *   Called by the User to initialize USB
 *   Return Value:    None
 */

void USBD_Init(void)
{
    OutEpSize[0] = USBD_MAX_PACKET0;
    /* Enable all clocks needed for USB to function                             */
    /* Set USB clock to 48 MHz                                                  */
    SIM->SOPT2   |=   SIM_SOPT2_USBSRC_MASK     | /* MCGPLLCLK used as src      */
                      SIM_SOPT2_PLLFLLSEL_MASK  ; /* Select MCGPLLCLK as clock  */
#if defined(TARGET_MK20D5)
    SIM->CLKDIV2 &= ~(SIM_CLKDIV2_USBFRAC_MASK  | /* Clear CLKDIV2 FS values    */
                      SIM_CLKDIV2_USBDIV_MASK);
    SIM->CLKDIV2  =   SIM_CLKDIV2_USBDIV(0)     ; /* USB clk = (PLL*1/2)        */
    /*         = ( 48*1/1)=48     */
#endif // TARGET_MK20D5
    SIM->SCGC4   |=   SIM_SCGC4_USBOTG_MASK;      /* Enable USBOTG clock        */
    USBD_IntrEna();
    USB0->USBTRC0 |= USB_USBTRC0_USBRESET_MASK;

    while (USB0->USBTRC0 & USB_USBTRC0_USBRESET_MASK);

    USB0->BDTPAGE1 = (uint8_t)((uint32_t) BD >> 8);
    USB0->BDTPAGE2 = (uint8_t)((uint32_t) BD >> 16);
    USB0->BDTPAGE3 = (uint8_t)((uint32_t) BD >> 24);
    USB0->ISTAT   = 0xFF;                 /* clear interrupt flags              */
    /* enable interrupts                                                        */
    USB0->INTEN =                            USB_INTEN_USBRSTEN_MASK |
            USB_INTEN_TOKDNEEN_MASK |
            USB_INTEN_SLEEPEN_MASK  |
#ifdef __RTX
            ((USBD_RTX_DevTask   != 0) ? USB_INTEN_SOFTOKEN_MASK : 0) |
            ((USBD_RTX_DevTask   != 0) ? USB_INTEN_ERROREN_MASK  : 0) ;
#else
            ((USBD_P_SOF_Event   != 0) ? USB_INTEN_SOFTOKEN_MASK : 0) |
            ((USBD_P_Error_Event != 0) ? USB_INTEN_ERROREN_MASK  : 0) ;
#endif
    USB0->USBCTRL  = USB_USBCTRL_PDE_MASK;/* pull dawn on D+ and D-             */
    USB0->USBTRC0 |= (1 << 6);            /* bit 6 must be set to 1             */
}


/*
 *  USB Device Connect Function
 *   Called by the User to Connect/Disconnect USB Device
 *    Parameters:      con:   Connect/Disconnect
 *    Return Value:    None
 */

void USBD_Connect(uint32_t con)
{
    if (con) {
        USB0->CTL  |= USB_CTL_USBENSOFEN_MASK;            /* enable USB           */
        USB0->CONTROL = USB_CONTROL_DPPULLUPNONOTG_MASK;  /* pull up on D+        */
    } else {
        USB0->CTL  &= ~USB_CTL_USBENSOFEN_MASK;           /* disable USB          */
        USB0->CONTROL &= ~USB_CONTROL_DPPULLUPNONOTG_MASK;/* pull down on D+      */
    }
}


/*
 *  USB Device Reset Function
 *   Called automatically on USB Device Reset
 *    Return Value:    None
 */

void USBD_Reset(void)
{
    uint32_t i;

    for (i = 1; i < 16; i++) {
        USB0->ENDPOINT[i].ENDPT = 0x00;
    }

    /* EP0 control endpoint                                                     */
    BD[IDX(0, RX, EVEN)].bc       = USBD_MAX_PACKET0;
    BD[IDX(0, RX, EVEN)].buf_addr = (uint32_t) & (EPBuf[IDX(0, RX, EVEN)][0]);
    BD[IDX(0, RX, EVEN)].stat     = BD_OWN_MASK | BD_DTS_MASK;
    BD[IDX(0, RX, ODD)].bc       = USBD_MAX_PACKET0;
    BD[IDX(0, RX, ODD)].buf_addr = (uint32_t) &(EPBuf[IDX(0, RX, ODD)][0]);
    BD[IDX(0, RX, ODD)].stat     = 0;

    BD[IDX(0, TX, EVEN)].stat = 0;
    BD[IDX(0, TX, EVEN)].buf_addr = (uint32_t) &(EPBuf[IDX(0, TX, EVEN)][0]);
    BD[IDX(0, TX, ODD)].stat = 0;
    BD[IDX(0, TX, ODD)].buf_addr = (uint32_t) &(EPBuf[IDX(0, TX, ODD)][0]);

    Data1 = 0x55555555;
    EvenOddLastXfer = 0xFFFFFFFF;
    SetupBufReady = 0;
    USB0->CTL    |=  USB_CTL_ODDRST_MASK; /* Reset to the even USB buffer       */
    USB0->CTL    &=  ~USB_CTL_ODDRST_MASK;
    USB0->ISTAT   =  0xFF;                /* clear all interrupt status flags   */
    USB0->ERRSTAT =  0xFF;                /* clear all error flags              */
    USB0->ERREN   =  0xFF;                /* enable error interrupt sources     */
    USB0->ADDR    =  0x00;                /* set default address                */
    USB0->ENDPOINT[0].ENDPT = USB_ENDPT_EPHSHK_MASK | /* enable ep handshaking  */
                          USB_ENDPT_EPTXEN_MASK | /* enable TX (IN) tran.   */
                          USB_ENDPT_EPRXEN_MASK;  /* enable RX (OUT) tran.  */
}


/*
 *  USB Device Suspend Function
 *   Called automatically on USB Device Suspend
 *    Return Value:    None
 */

void USBD_Suspend(void)
{
    USB0->INTEN |= USB_INTEN_RESUMEEN_MASK;
}


/*
 *  USB Device Resume Function
 *   Called automatically on USB Device Resume
 *    Return Value:    None
 */

void USBD_Resume(void)
{
    USB0->INTEN &= ~USB_INTEN_RESUMEEN_MASK;
}


/*
 *  USB Device Remote Wakeup Function
 *   Called automatically on USB Device Remote Wakeup
 *    Return Value:    None
 */

void USBD_WakeUp(void)
{
    uint32_t i = 50000;

    if (USBD_DeviceStatus & USB_GETSTATUS_REMOTE_WAKEUP) {
        USB0->CTL |=  USB_CTL_RESUME_MASK;

        while (i--) {
            __nop();
        }

        USB0->CTL &= ~USB_CTL_RESUME_MASK;
    }
}


/*
 *  USB Device Remote Wakeup Configuration Function
 *    Parameters:      cfg:   Device Enable/Disable
 *    Return Value:    None
 */

void USBD_WakeUpCfg(uint32_t cfg)
{
    /* Not needed                                                               */
}


/*
 *  USB Device Set Address Function
 *    Parameters:      adr:   USB Device Address
 *    Return Value:    None
 */

void USBD_SetAddress(uint32_t  adr, uint32_t setup)
{
    if (!setup) {
        USB0->ADDR    = adr & 0x7F;
    }
}


/*
 *  USB Device Configure Function
 *    Parameters:      cfg:   Device Configure/Deconfigure
 *    Return Value:    None
 */

void USBD_Configure(uint32_t cfg)
{
}


/*
 *  Configure USB Device Endpoint according to Descriptor
 *    Parameters:      pEPD:  Pointer to Device Endpoint Descriptor
 *    Return Value:    None
 */

void USBD_ConfigEP(USB_ENDPOINT_DESCRIPTOR *pEPD)
{
    uint32_t num, val;
    num  = pEPD->bEndpointAddress;
    val  = pEPD->wMaxPacketSize;

    if (!(pEPD->bEndpointAddress & 0x80)) {
        OutEpSize[num] = val;
    }

    USBD_ResetEP(num);
}


/*
 *  Set Direction for USB Device Control Endpoint
 *    Parameters:      dir:   Out (dir == 0), In (dir <> 0)
 *    Return Value:    None
 */

void USBD_DirCtrlEP(uint32_t dir)
{
    /* Not needed                                                               */
}


/*
 *  Enable USB Device Endpoint
 *    Parameters:      EPNum: Device Endpoint Number
 *                       EPNum.0..3: Address
 *                       EPNum.7:    Dir
 *    Return Value:    None
 */

void USBD_EnableEP(uint32_t EPNum)
{
    if (EPNum & 0x80) {
        EPNum &= 0x0F;
        USB0->ENDPOINT[EPNum].ENDPT |= USB_ENDPT_EPHSHK_MASK | /*en ep handshaking*/
                                       USB_ENDPT_EPTXEN_MASK;  /*en TX (IN) tran  */
    } else {
        USB0->ENDPOINT[EPNum].ENDPT |= USB_ENDPT_EPHSHK_MASK | /*en ep handshaking*/
                                       USB_ENDPT_EPRXEN_MASK;  /*en RX (OUT) tran.*/
    }
}


/*
 *  Disable USB Endpoint
 *    Parameters:      EPNum: Endpoint Number
 *                       EPNum.0..3: Address
 *                       EPNum.7:    Dir
 *    Return Value:    None
 */

void USBD_DisableEP(uint32_t EPNum)
{
    if (EPNum & 0x80) {
        EPNum &= 0x0F;
        USB0->ENDPOINT[EPNum].ENDPT &= ~(USB_ENDPT_EPHSHK_MASK |/*dis handshaking */
                                         USB_ENDPT_EPTXEN_MASK);/*dis TX(IN) tran */
    } else {
        USB0->ENDPOINT[EPNum].ENDPT &= ~(USB_ENDPT_EPHSHK_MASK |/*dis handshaking */
                                         USB_ENDPT_EPRXEN_MASK);/*dis RX(OUT) tran*/
    }
}


/*
 *  Reset USB Device Endpoint
 *    Parameters:      EPNum: Device Endpoint Number
 *                       EPNum.0..3: Address
 *                       EPNum.7:    Dir
 *    Return Value:    None
 */

void USBD_ResetEP(uint32_t EPNum)
{
    util_assert(USB0->CTL & USB_CTL_TXSUSPENDTOKENBUSY_MASK);
    if (EPNum & 0x80) {
        EPNum &= 0x0F;

        BD[IDX(EPNum, TX, EVEN)].stat &= ~BD_OWN_MASK;
        BD[IDX(EPNum, TX, EVEN)].buf_addr = (uint32_t) &(EPBuf[IDX(EPNum, TX, EVEN)][0]);

        BD[IDX(EPNum, TX, ODD)].stat &= ~BD_OWN_MASK;
        BD[IDX(EPNum, TX, ODD)].buf_addr = (uint32_t) &(EPBuf[IDX(EPNum, TX, ODD)][0]);

        // Next transaction will use DATA0
        protected_and(&Data1, ~DATAX_BIT(EPNum, TX));
    } else {
        uint8_t cur_ev_odd;
        uint8_t next_ev_odd;

        next_ev_odd = (EvenOddLastXfer & EVENODD_BIT(EPNum, RX)) ? ODD : EVEN;
        BD[IDX(EPNum, RX, next_ev_odd)].bc       = OutEpSize[EPNum];
        BD[IDX(EPNum, RX, next_ev_odd)].buf_addr = (uint32_t) & (EPBuf[IDX(EPNum, RX, next_ev_odd)][0]);
        BD[IDX(EPNum, RX, next_ev_odd)].stat     = 0;

        // This transaction uses DATA0
        cur_ev_odd = (~EvenOddLastXfer & EVENODD_BIT(EPNum, RX)) ? ODD : EVEN;
        BD[IDX(EPNum, RX, cur_ev_odd)].bc       = OutEpSize[EPNum];
        BD[IDX(EPNum, RX, cur_ev_odd)].buf_addr = (uint32_t) & (EPBuf[IDX(EPNum, RX, cur_ev_odd)][0]);
        BD[IDX(EPNum, RX, cur_ev_odd)].stat     = BD_OWN_MASK | BD_DTS_MASK;

        // Next transaction will use DATA1
        protected_or(&Data1, DATAX_BIT(EPNum, RX));
    }
}

/*
 *  Set Stall for USB Device Endpoint
 *    Parameters:      EPNum: Device Endpoint Number
 *                       EPNum.0..3: Address
 *                       EPNum.7:    Dir
 *    Return Value:    None
 */

void USBD_SetStallEP(uint32_t EPNum)
{
    EPNum &= 0x0F;
    USB0->ENDPOINT[EPNum].ENDPT |= USB_ENDPT_EPSTALL_MASK;
}


/*
 *  Clear Stall for USB Device Endpoint
 *    Parameters:      EPNum: Device Endpoint Number
 *                       EPNum.0..3: Address
 *                       EPNum.7:    Dir
 *    Return Value:    None
 */

void USBD_ClrStallEP(uint32_t EPNum)
{
    USB0->ENDPOINT[EPNum & 0x0F].ENDPT &= ~USB_ENDPT_EPSTALL_MASK;
    USBD_ResetEP(EPNum);
}


/*
 *  Clear USB Device Endpoint Buffer
 *    Parameters:      EPNum: Device Endpoint Number
 *                       EPNum.0..3: Address
 *                       EPNum.7:    Dir
 *    Return Value:    None
 */

void USBD_ClearEPBuf(uint32_t EPNum)
{
}


/*
 *  Read USB Device Endpoint Data
 *    Parameters:      EPNum: Device Endpoint Number
 *                       EPNum.0..3: Address
 *                       EPNum.7:    Dir
 *                     pData: Pointer to Data Buffer
 *    Return Value:    Number of bytes read
 */

uint32_t USBD_ReadEP(uint32_t EPNum, uint8_t *pData, uint32_t size)
{
    uint32_t n, sz, idx, idx_next;
    uint8_t last_ev_odd;
    uint8_t next_ev_odd;

    last_ev_odd = (EvenOddLastXfer & EVENODD_BIT(EPNum, RX)) ? ODD : EVEN;
    idx = IDX(EPNum, RX, last_ev_odd);
    util_assert(!(BD[idx].stat & BD_OWN_MASK));
    sz  = BD[idx].bc;

    if (size < sz) {
        util_assert(0);
        sz = size;
    }

    // Read current packet
    for (n = 0; n < sz; n++) {
        pData[n] = EPBuf[idx][n];
    }

    // Extra processing for endpoint 0
    if (0 == EPNum) {
        if (TOK_PID(idx) == SETUP_TOKEN) {
            uint32_t xfer_size = (pData[7] << 8) | (pData[6] << 0);
            if (0 == xfer_size) {
                // No data stage - next packet recieved will be SETUP (DATA0)
                protected_and(&Data1, ~DATAX_BIT(EPNum, RX));
            } else  {
                if (pData[0] & (1 << 7)) {
                    // Data IN stage - This control transfer has a
                    // data send with an IN transaction and ends with a zero
                    // length OUT packet. If a SETUP packet arrives before the
                    // OUT token has been handled this SETUP packet will
                    // be dropped. To prevent this setup the second buffer
                    // in advance so the SETUP (DATA0) packet won't be
                    // dropped.
                    BD[idx].bc = OutEpSize[EPNum];
                    BD[idx].stat  = BD_DTS_MASK;
                    BD[idx].stat |= BD_OWN_MASK;
                    SetupBufReady = 1;
                }
                protected_or(&Data1, DATAX_BIT(EPNum, RX));
            }
        } else {
            if (SetupBufReady) {
                // This is a zero length packet indicating the end
                // of a control transfer with an IN stage.
                // Next read has already been setup so there is no
                // work to do.
                util_assert(0 == sz);
                SetupBufReady = 0;
                return 0;
            }
        }
    }

    next_ev_odd = (~EvenOddLastXfer & EVENODD_BIT(EPNum, RX)) ? ODD : EVEN;
    idx_next = IDX(EPNum, RX, next_ev_odd);
    
    // Setup next packet
    BD[idx_next].bc = OutEpSize[EPNum];
    if (Data1 & DATAX_BIT(EPNum, RX)) {
        BD[idx_next].stat  = BD_DTS_MASK | BD_DATA01_MASK;
        BD[idx_next].stat |= BD_OWN_MASK;
    } else {
        BD[idx_next].stat  = BD_DTS_MASK;
        BD[idx_next].stat |= BD_OWN_MASK;
    }

    protected_xor(&Data1, DATAX_BIT(EPNum, RX));
    return (sz);
}


/*
 *  Write USB Device Endpoint Data
 *    Parameters:      EPNum: Device Endpoint Number
 *                       EPNum.0..3: Address
 *                       EPNum.7:    Dir
 *                     pData: Pointer to Data Buffer
 *                     cnt:   Number of bytes to write
 *    Return Value:    Number of bytes written
 */

uint32_t USBD_WriteEP(uint32_t EPNum, uint8_t *pData, uint32_t cnt)
{
    uint32_t idx, n;
    uint8_t cur_ev_odd;
    EPNum &= 0x0F;
    cur_ev_odd = (~EvenOddLastXfer & EVENODD_BIT(EPNum, TX)) ? ODD : EVEN;
    idx = IDX(EPNum, TX, cur_ev_odd);

    util_assert(!(BD[idx].stat & BD_OWN_MASK));
    BD[idx].bc = cnt;

    for (n = 0; n < cnt; n++) {
        EPBuf[idx][n] = pData[n];
    }

    if (Data1 & DATAX_BIT(EPNum, TX)) {
        BD[idx].stat = BD_OWN_MASK | BD_DTS_MASK | BD_DATA01_MASK;
    } else {
        BD[idx].stat = BD_OWN_MASK | BD_DTS_MASK;
    }

    protected_xor(&Data1, DATAX_BIT(EPNum, TX));
    return (cnt);
}

/*
 *  Get USB Device Last Frame Number
 *    Parameters:      None
 *    Return Value:    Frame Number
 */

uint32_t USBD_GetFrame(void)
{
    return ((USB0->FRMNUML | (USB0->FRMNUMH << 8) & 0x07FF));
}

#ifdef __RTX
U32 LastError;                          /* Last Error                         */

/*
 *  Get USB Device Last Error Code
 *    Parameters:      None
 *    Return Value:    Error Code
 */

U32 USBD_GetError(void)
{
    return (LastError);
}
#endif


/*
 *  USB Device Interrupt Service Routine
 */
void USB0_IRQHandler(void)
{
    NVIC_DisableIRQ(USB0_IRQn);
    USBD_SignalHandler();
}

/*
 *  USB Device Service Routine
 */

void USBD_Handler(void)
{
    uint32_t istr, num, dir, ev_odd, stat;
    uint8_t setup;
    istr  = USB0->ISTAT;
    stat  = USB0->STAT;
    USB0->ISTAT = istr;
    istr &= USB0->INTEN;
    setup = 0;

    /* reset interrupt                                                            */
    if (istr & USB_ISTAT_USBRST_MASK) {
        USBD_Reset();
        usbd_reset_core();
#ifdef __RTX

        if (USBD_RTX_DevTask) {
            isr_evt_set(USBD_EVT_RESET, USBD_RTX_DevTask);
        }

#else

        if (USBD_P_Reset_Event) {
            USBD_P_Reset_Event();
        }

#endif
    }

    /* suspend interrupt                                                          */
    if (istr & USB_ISTAT_SLEEP_MASK) {
        USBD_Suspend();
#ifdef __RTX

        if (USBD_RTX_DevTask) {
            isr_evt_set(USBD_EVT_SUSPEND, USBD_RTX_DevTask);
        }

#else

        if (USBD_P_Suspend_Event) {
            USBD_P_Suspend_Event();
        }

#endif
    }

    /* resume interrupt                                                           */
    if (istr & USB_ISTAT_RESUME_MASK) {
        USBD_Resume();
#ifdef __RTX

        if (USBD_RTX_DevTask) {
            isr_evt_set(USBD_EVT_RESUME, USBD_RTX_DevTask);
        }

#else

        if (USBD_P_Resume_Event) {
            USBD_P_Resume_Event();
        }

#endif
    }

    /* Start Of Frame                                                             */
    if (istr & USB_ISTAT_SOFTOK_MASK) {
#ifdef __RTX

        if (USBD_RTX_DevTask) {
            isr_evt_set(USBD_EVT_SOF, USBD_RTX_DevTask);
        }

#else

        if (USBD_P_SOF_Event) {
            USBD_P_SOF_Event();
        }

#endif
    }

    /* Error interrupt                                                            */
    if (istr == USB_ISTAT_ERROR_MASK) {
#ifdef __RTX
        LastError = USB0->ERRSTAT;

        if (USBD_RTX_DevTask) {
            isr_evt_set(USBD_EVT_ERROR, USBD_RTX_DevTask);
        }

#else

        if (USBD_P_Error_Event) {
            USBD_P_Error_Event(USB0->ERRSTAT);
        }

#endif
        USB0->ERRSTAT = 0xFF;
    }

    /* token interrupt                                                            */
    if (istr & USB_ISTAT_TOKDNE_MASK) {
        num    = (stat >> 4) & 0x0F;
        dir    = (stat >> 3) & 0x01;
        ev_odd = (stat >> 2) & 0x01;

        /* set the odd/even bit of the last packet                                    */
        if (ODD == ev_odd) {
            protected_or(&EvenOddLastXfer, EVENODD_BIT(num, dir));
        } else {
            protected_and(&EvenOddLastXfer, ~EVENODD_BIT(num, dir));
        }

        /* setup packet                                                               */
        if ((num == 0) && (TOK_PID((IDX(num, dir, ev_odd))) == SETUP_TOKEN)) {
            setup = 1;
            Data1 |= DATAX_BIT(0, TX);
            BD[IDX(0, TX, ODD)].stat  &= ~BD_OWN_MASK;
            BD[IDX(0, TX, EVEN)].stat &= ~BD_OWN_MASK;
            SetupBufReady = 0;
#ifdef __RTX

            if (USBD_RTX_EPTask[num]) {
                isr_evt_set(USBD_EVT_SETUP, USBD_RTX_EPTask[num]);
            }

#else

            if (USBD_P_EP[num]) {
                USBD_P_EP[num](USBD_EVT_SETUP);
            }

#endif

        } else {
            /* OUT packet                                                                 */
            if (TOK_PID((IDX(num, dir, ev_odd))) == OUT_TOKEN) {
#ifdef __RTX

                if (USBD_RTX_EPTask[num]) {
                    isr_evt_set(USBD_EVT_OUT, USBD_RTX_EPTask[num]);
                }

#else

                if (USBD_P_EP[num]) {
                    USBD_P_EP[num](USBD_EVT_OUT);
                }

#endif
            }

            /* IN packet                                                                  */
            if (TOK_PID((IDX(num, dir, ev_odd))) == IN_TOKEN) {
#ifdef __RTX

                if (USBD_RTX_EPTask[num]) {
                    isr_evt_set(USBD_EVT_IN,  USBD_RTX_EPTask[num]);
                }

#else

                if (USBD_P_EP[num]) {
                    USBD_P_EP[num](USBD_EVT_IN);
                }

#endif
            }
        }
    }

    if (setup) {
        USB0->CTL &= ~USB_CTL_TXSUSPENDTOKENBUSY_MASK;
    }
    NVIC_EnableIRQ(USB0_IRQn);
}
