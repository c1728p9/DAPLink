"""
 mbed CMSIS-DAP debugger
 Copyright (c) 2006-2015 ARM Limited

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""

import pyOCD
from pyOCD.board import MbedBoard

FLASH_ACR = 0x40022000
FLASH_KEYR = 0x40022004
FLASH_OPTKEYR = 0x40022008
FLASH_SR = 0x4002200C
FLASH_CR = 0x40022010
FLASH_AR = 0x40022014
FLASH_OBR = 0x4002201c
FLASH_WRPR = 0x40022020

FLASH_SR_BSY = (1 << 0)
FLASH_SR_EOP = (1 << 5)

FLASH_OBR_NRST_STDBY = (1 << 4)
FLASH_OBR_NRST_STOP = (1 << 3)
FLASH_OBR_WDG_SW = (1 << 2)
FLASH_OBR_RDPRT = (1 << 1)
FLASH_OBR_OPTERR = (1 << 0)

FLASH_CR_OPTWRE = (1 << 9)
FLASH_CR_LOCK = (1 << 7)
FLASH_CR_STRT = (1 << 6)
FLASH_CR_OPTER = (1 << 5)
FLASH_CR_OPTPG = (1 << 4)


RDPRT_KEY = 0x00A5
KEY1 = 0x45670123
KEY2 = 0xCDEF89AB

OPTION_BYTE_ADDR = 0x1FFFF800

def unlock(target):
        target.writeMemory(FLASH_OPTKEYR, KEY1)
        target.writeMemory(FLASH_OPTKEYR, KEY2)
        
        # Erase user option
        cr = target.readMemory(FLASH_CR)
        cr |= FLASH_CR_OPTER
        target.writeMemory(FLASH_CR, cr)
        cr |= FLASH_CR_STRT
        target.writeMemory(FLASH_CR, cr)
        while True:
            sr = target.readMemory(FLASH_SR)
            if sr & FLASH_SR_BSY:
                print("Operation in progress")
            else:
                break
        print("Operation done")
        
        # Write user option
        cr = target.readMemory(FLASH_CR)
        cr &= ~FLASH_CR_OPTER
        cr |= FLASH_CR_OPTPG
        target.writeMemory(FLASH_CR, cr)
        print("CR: 0x%x" % target.readMemory(FLASH_CR))
        print("SR: 0x%x" % target.readMemory(FLASH_SR))
        
        # Clear status register
        sr = target.readMemory(FLASH_SR)
        target.writeMemory(FLASH_SR, sr)
        print("SR: 0x%x" % target.readMemory(FLASH_SR))
        
        target.writeMemory(OPTION_BYTE_ADDR, 0x5AA5, 16)
        while True:
            sr = target.readMemory(FLASH_SR)
            if sr & FLASH_SR_BSY:
                print("Operation in progress")
            else:
                break
        print("Operation done")
        print("SR: 0x%x" % target.readMemory(FLASH_SR))


def main():
    with MbedBoard.chooseBoard(target_override="cortex_m", frequency=1000000) as board:
        target = board.target

        target.writeMemory(FLASH_KEYR, KEY1)
        target.writeMemory(FLASH_KEYR, KEY2)
        

        
        cr = target.readMemory(FLASH_CR)
        if cr & FLASH_CR_LOCK:
            print("FPEC locked")
        else:
            print("FPEC unlocked")
        if cr & FLASH_CR_OPTWRE:
            print("Option byte write enable")
        else:
            print("Option byte write disable")
        
        obr = target.readMemory(FLASH_OBR)
        if obr & FLASH_OBR_RDPRT:
            print("Read protect on")
        else:
            print("Read protect off")
        
        sr = target.readMemory(FLASH_SR)
        if sr & FLASH_SR_BSY:
            print("Flash busy")
        else:
            print("Flash not busy")
        
        print("Option byte: 0x%x" % obr)
        

        unlock(target)
        

        #FLASH_CR_STRT
        options = target.readMemory(OPTION_BYTE_ADDR)
        print("Options: 0x%x" % options)
        
        
        addr = 0x08000000
        size = 128 * 1024
        #addr = 0x20000000
        #size = 16*1024
        block = target.readBlockMemoryUnaligned8(addr, size)
        block = bytearray(block)
        with open("dump.bin", "wb") as f:
            f.write(block)

        #flash.flashBinary(binary_file, addr_bin)


if __name__ == "__main__":
    main()
