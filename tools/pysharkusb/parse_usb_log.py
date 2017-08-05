from struct import unpack, calcsize
from pcapng import FileScanner
from collections import namedtuple
from usbpcap import pcap_to_usb
import logging
logging.basicConfig(level=logging.ERROR)

log = logging.getLogger(__name__)


# Defined by pcapng - https://www.winpcap.org/ntar/draft/PCAP-DumpFileFormat.html
PCAPNG_BLOCK = {
    "INTERFACE_DESC": 0x00000001,
    "ENHANCED_PACKET": 0x00000006,
    "SECTION_HEADER": 0x0A0D0D0A
}



# Event
    # Start (read size, write data) and stop event (status, read data, write size)
# Transfer
    # How to handle a failed transfer? - filter them out
    # How should control requests look?
# Protocol
    # SCSI
    # HID
    # CMSIS
    # CDC
    # MSD
        # Read after write
        # OOO fat chain
        # OOO file write
        # FAT filesystem


PCAPNG_LINK = {
    249: pcap_to_usb
    #220:
}


def pcapng_to_usb_transfers(filename):
    with open(filename, "rb") as fp:
        scanner = FileScanner(fp)
        interfaces = None
        index = None
        usb_transfers = []
        for block in scanner:
            if block.magic_number == PCAPNG_BLOCK["SECTION_HEADER"]:
                interfaces = []
                index = 1
            elif block.magic_number == PCAPNG_BLOCK["INTERFACE_DESC"]:
                print("Link type: %s" % block)
                if block.link_type in PCAPNG_LINK:
                    interfaces.append(PCAPNG_LINK[block.link_type])
                else:
                    log.error("Skipping interface!")
            elif block.magic_number == PCAPNG_BLOCK["ENHANCED_PACKET"]:
                usb_transfers.append(interfaces[block.interface_id](block.packet_data, index))
                index += 1
    return usb_transfers


CBW_FMT = "<IIIBBB16s"
CBW_SIZE = calcsize(CBW_FMT)
CBWTransfer = namedtuple("CBWTransfer", "signature, tag, data_transfer_length, flags, lun, length, cb")
CSW_FMT = "<IIIB"
CSW_SIZE = calcsize(CSW_FMT)
CSWTransfer = namedtuple("CSWTransfer", "signature, tag, data_residue, status")



# op
# lba
# OPERATION CODE
# LOGICAL BLOCK ADDRESS

#TRANSFER LENGTH
#PARAMETER LIST LENGTH
#ALLOCATION LENGTH

#CONTROL

ScsiCmd = namedtuple("ScsiCmd", "op, misc, lba, len, ctrl, service")#TODO - renmae to CDB

def valid_cbw(xfer):
    if xfer is None:
        return False
    if xfer.dir != "Out":
        log.error("Wrong CBW direction for packet %s: %s", xfer.id, xfer.dir)
        return False
    if len(xfer.data) != 31:
        log.error("Wrong CBW size for packet %s: %s", xfer.id, len(xfer.data))
        return False
    if xfer.data[:4] != "USBC":
        log.error("Wrong CBW signature for packet %s: %s", xfer.id, xfer.data[:4])
        return False
    return True


def valid_csw(xfer, tag, log_error=True):
    if xfer.dir != "In":
        if log_error:
            log.error("Wrong transfer direction for packet %s in CSW stage: %s", xfer.id, xfer.dir)
        return False
    elif len(xfer.data) != 13:
        if log_error:
            log.error("Wrong CSW packet size for packet %s: %s", xfer.id, len(xfer.data))
        return False
    csw = CSWTransfer(*unpack(CSW_FMT, xfer.data[:CSW_SIZE]))
    if csw.tag != tag:
        return False
    return True


def cb_to_cdb6(cb):
    op, misc_lba_hi, lba_lo, length, ctrl = unpack("<BBHBB", cb[:6])
    misc = (misc_lba_hi >> 5) & 0x7
    lba_hi =  ((misc_lba_hi >> 0) & 0x1F)
    lba = (lba_hi << 16) | (lba_lo << 0)
    return ScsiCmd(op, (misc,), lba, length, ctrl, None)


def cb_to_cdb10(cb):
    op, misc_service, lba, misc2, length, ctrl = unpack(">BBLBHB", cb[:10])
    misc1 = (misc_service >> 5) & 0x7
    service = (misc_service >> 0) & 0x1F
    return ScsiCmd(op, (misc1, misc2), lba, length, ctrl, service)
#"op, misc, lba, len, ctrl, service"    TODO

def status_to_str(status):
    status_table = {
        0: "Pass",
        1: "Fail",
        2: "Phase Error",
    }
    return status_table[status] if status in status_table else "Reserved"


class SCSITransfer(object):

    def __init__(self, cbw, data, csw):
        self.name = "Unknown"
        self.op = unpack("<B", cbw.cb[0])[0]
        self.cbw = cbw
        self.data = data
        self.csw = csw
        self.lun = cbw.lun
        self.status = csw.status
        self.additional_info = ""

    def __str__(self):
        return "<SCSI op=%s(0x%02x) lun=%i %s status=%s (%i)>" % (self.name, self.op, self.lun, self.additional_info, status_to_str(self.status), self.status)


class TestUnitReady(SCSITransfer):

    def __init__(self, cbw, data, csw):
        super(TestUnitReady, self).__init__(cbw, data, csw)
        self.name = "TestUnitReady"
        self.cdb = cb_to_cdb6(cbw.cb)
        #assert self.op == self.cdb.op
        self.additional_info = "control=0x%x" % self.cdb.ctrl


class Read10(SCSITransfer):

    def __init__(self, cbw, data, csw):
        super(Read10, self).__init__(cbw, data, csw)
        self.name = "Read10"
        self.cdb = cb_to_cdb10(cbw.cb)
        self.lba = self.cdb.lba
        self.len = self.cdb.len
        self.data = data
        self.additional_info = "lba=0x%x blocks=%i" % (self.lba, self.len)


class Write10(SCSITransfer):

    def __init__(self, cbw, data, csw):
        super(Write10, self).__init__(cbw, data, csw)
        self.name = "Write10"
        self.cdb = cb_to_cdb10(cbw.cb)
        self.lba = self.cdb.lba
        self.len = self.cdb.len
        self.data = data
        self.additional_info = "lba=0x%x blocks=%i" % (self.lba, self.len)


scsi_commands = {
    0x00: TestUnitReady,
    # 0x03: RequestSense, #6
    # 0x12: Inquiry, #6
    # 0x1a: ModeSense6
    # #0x1e:
    # #0x23:
    # 0x25: ReadCapacity10,
    0x28: Read10,
    0x2a: Write10,
}


def usb_to_scsi(xfers):
    xfer_itr = iter(xfers)
    scsi_list = []
    try:
        while True:

            # Read until a valid CBW
            while True:
                xfer = xfer_itr.next()
                if valid_cbw(xfer):
                    break
            cbw = CBWTransfer(*unpack(CBW_FMT, xfer.data))

            # Data stage
            data = None
            xfer = xfer_itr.next()
            if cbw.data_transfer_length > 0 and not valid_csw(xfer, cbw.tag, log_error=False):
                direction = "In" if cbw.flags & (1 << 7) else "Out"
                if direction != xfer.dir:
                    log.error("Wrong direction for packet %s in data stage - got %s, expected %s", xfer.id, xfer.dir, direction)
                data = xfer.data
                xfer = xfer_itr.next()

            # Handle CSW stage
            if not valid_csw(xfer, cbw.tag):
                continue
            csw = CSWTransfer(*unpack(CSW_FMT, xfer.data))
            # unpack("<B", cdb[0])[0], csw.status, data,
            transfer_factory = scsi_commands.get(bytearray(cbw.cb[0])[0], SCSITransfer)
            scsi_list.append(transfer_factory(cbw, data, csw))

    except StopIteration:
        pass
    return scsi_list

# Conditions to detect:
# -Read after write
# -Out of order file transfer
# -Non-sequential cluster chain

# Features
# -Extract write sequence and timing
# -Extract read-only FS
# -Extract FS before remount

def main():
    xfers = pcapng_to_usb_transfers("k64f_load.pcapng")
    scsis = usb_to_scsi(xfer for xfer in xfers if xfer.endpoint == 2 and xfer.device == 10)
    ops = set()
    with open("test_fs.img", "wb") as f:
        for scsi in scsis:
            #print("%s %s" % (scsi.cbw, scsi.csw))
            if scsi.op == 0x28:
                pass
                #f.write(scsi.data)
            if scsi.op in (0x2a, 0x28):
                print(scsi)
                f.seek(512 * scsi.lba)
                f.write(scsi.data)
            if scsi.op == 0x00 and scsi.status != 0:
                print(scsi)
                break

            ops.add(scsi.op)

    # print("Op list:")
    # for op in sorted(list(ops)):
    #     print("  0x%x" % op)
    #controls = [xfer for xfer in xfers if xfer.endpoint == 0]
    #for control in controls:
    #    print("Control: %s" % (control,))


if __name__ == "__main__":
    main()