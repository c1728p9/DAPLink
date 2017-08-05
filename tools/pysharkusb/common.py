from collections import namedtuple

USB_TYPE = set([
    "Bulk",
    "Interrupt",
    "Control"
])
USB_DIR = set([
    "Setup",
    "In",
    "Out",
    "Status"
])

USBTransfer = namedtuple("USBTransfer", "id, bus, device, endpoint, type, dir, data")
