from struct import unpack, calcsize
from collections import namedtuple
import logging
logging.basicConfig(level=logging.ERROR)

log = logging.getLogger(__name__)


CBW_FMT = "<IIIBBB16s"
CBW_SIZE = calcsize(CBW_FMT)
CBWTransfer = namedtuple("CBWTransfer", "signature, tag, data_transfer_length, flags, lun, length, cb")
CSW_FMT = "<IIIB"
CSW_SIZE = calcsize(CSW_FMT)
CSWTransfer = namedtuple("CSWTransfer", "signature, tag, data_residue, status")


ScsiCbd = namedtuple("ScsiCbd", "op, misc, lba, len, ctrl, service")


def valid_cbw(xfer):
    if xfer is None:
        return False
    if xfer.dir != "Out":
        log.error("Wrong CBW direction for packet %s: %s", xfer.id, xfer.dir)
        return False
    if len(xfer.data) != CBW_SIZE:
        log.error("Wrong CBW size for packet %s: %s", xfer.id, len(xfer.data))
        return False
    if not xfer.data.startswith(b"USBC"):
        log.error("Wrong CBW signature for packet %s: %s", xfer.id, xfer.data[:4])
        return False
    return True


def valid_csw(xfer, tag, log_error=True):
    if xfer.dir != "In":
        if log_error:
            log.error("Wrong transfer direction for packet %s in CSW stage: %s", xfer.id, xfer.dir)
        return False
    if len(xfer.data) != CSW_SIZE:
        if log_error:
            log.error("Wrong CSW packet size for packet %s: %s", xfer.id, len(xfer.data))
        return False
    if not xfer.data.startswith(b"USBS"):
        if log_error:
            log.error("Wrong CSW signature for packet %s: %s", xfer.id, xfer.data[:4])
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
    return ScsiCbd(op, (misc,), lba, length, ctrl, None)


def cb_to_cdb10(cb):
    op, misc_service, lba, misc2, length, ctrl = unpack(">BBLBHB", cb[:10])
    misc1 = (misc_service >> 5) & 0x7
    service = (misc_service >> 0) & 0x1F
    return ScsiCbd(op, (misc1, misc2), lba, length, ctrl, service)
#"op, misc, lba, len, ctrl, service"    TODO

def status_to_str(status):
    status_table = {
        0: "Pass",
        1: "Fail",
        2: "Phase Error",
    }
    return status_table[status] if status in status_table else "Reserved"


class SCSITransfer(object):

    def __init__(self, cbw, data, csw, usb_xfers):
        self.name = "Unknown"
        self.op = unpack("<B", cbw.cb[0])[0]
        self.cbw = cbw
        self.data = data
        self.csw = csw
        self.lun = cbw.lun
        self.status = csw.status
        self.additional_info = ""
        self.usb_xfers = usb_xfers
        self.time = None if usb_xfers is None else usb_xfers[0].time
        self.id = None if usb_xfers is None else usb_xfers[0].id

    def __str__(self):
        return "<SCSI op=%s(0x%02x) lun=%i %s status=%s (%i)>" % (self.name, self.op, self.lun, self.additional_info, status_to_str(self.status), self.status)


class TestUnitReady(SCSITransfer):

    def __init__(self, cbw, data, csw, usb_xfers):
        super(TestUnitReady, self).__init__(cbw, data, csw, usb_xfers)
        self.name = "TestUnitReady"
        self.cdb = cb_to_cdb6(cbw.cb)
        #assert self.op == self.cdb.op
        self.additional_info = "control=0x%x" % self.cdb.ctrl


class Read10(SCSITransfer):

    def __init__(self, cbw, data, csw, usb_xfers):
        super(Read10, self).__init__(cbw, data, csw, usb_xfers)
        self.name = "Read10"
        self.cdb = cb_to_cdb10(cbw.cb)
        self.lba = self.cdb.lba
        self.len = self.cdb.len
        self.data = data
        self.additional_info = "lba=0x%x blocks=%i" % (self.lba, self.len)


class Write10(SCSITransfer):

    def __init__(self, cbw, data, csw, usb_xfers):
        super(Write10, self).__init__(cbw, data, csw, usb_xfers)
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
    try:
        while True:
            xfers = []

            # Read until a valid CBW
            while True:
                xfer = xfer_itr.next()
                if valid_cbw(xfer):
                    xfers.append(xfer)
                    break
            cbw = CBWTransfer(*unpack(CBW_FMT, xfer.data))

            # Data stage
            data = None
            xfer = xfer_itr.next()
            xfers.append(xfer)
            if cbw.data_transfer_length > 0 and not valid_csw(xfer, cbw.tag, log_error=False):
                direction = "In" if cbw.flags & (1 << 7) else "Out"
                if direction != xfer.dir:
                    log.error("Wrong direction for packet %s in data stage - got %s, expected %s", xfer.id, xfer.dir, direction)
                data = xfer.data
                xfer = xfer_itr.next()
                xfers.append(xfer)

            # Handle CSW stage
            if not valid_csw(xfer, cbw.tag):
                continue
            csw = CSWTransfer(*unpack(CSW_FMT, xfer.data))
            opcode = bytearray(cbw.cb[0])[0]
            transfer_factory = scsi_commands.get(opcode, SCSITransfer)
            yield transfer_factory(cbw, data, csw, tuple(xfers))

    except StopIteration:
        return