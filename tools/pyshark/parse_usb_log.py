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


FMT_CBW = "<IIIBBB"
SIZE_CBW = calcsize(FMT_CBW)
CBWTransfer = namedtuple("CBWTransfer", "signature, tag, data_transfer_length, flags, lun, length")
FMT_CSW = "<IIIB"
SIZE_CSW = calcsize(FMT_CSW)
CSWTransfer = namedtuple("CSWTransfer", "signature, tag, data_residue, status")
SCSITransfer = namedtuple("SCSITransfer", "cbw, csw, data")


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
    csw = CSWTransfer(*unpack(FMT_CSW, xfer.data[:SIZE_CSW]))
    if csw.tag != tag:
        return False
    return True


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
            cbw = CBWTransfer(*unpack(FMT_CBW, xfer.data[:SIZE_CBW]))

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
            valid_csw(xfer, cbw.tag)
            csw = CSWTransfer(*unpack(FMT_CSW, xfer.data[:SIZE_CSW]))
            scsi_list.append(SCSITransfer(cbw, csw, data))

    except StopIteration:
        pass
    return scsi_list


def main():
    xfers = pcapng_to_usb_transfers("k64f_load.pcapng")
    scsis = usb_to_scsi(xfer for xfer in xfers if xfer.endpoint == 2 and xfer.device == 10)
    for scsi in scsis:
        print("%s %s" % (scsi.cbw, scsi.csw))


if __name__ == "__main__":
    main()