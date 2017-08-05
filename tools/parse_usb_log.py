from pysharkusb import pcapng_to_usb_transfers, usb_to_scsi

# Conditions to detect:
# -Read after write
# -Out of order file transfer
# -Non-sequential cluster chain

# Features
# -Extract write sequence and timing
# -Extract read-only FS
# -Extract FS before remount

# Auto decode
# -Device stream - Break into segments based on enumeration
# -Segment
#   - Detect mass storage endpoints (Bulk, "USBC"/"USBS")
#   - Detect hid endpoints or interface (Most or all commands should be recognized)
#   - Detect CDC interface (Baudrate change)
#   -

# TODO - SCSI timestamps

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