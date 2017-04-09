# USB notes

## USB problems when porting a new driver
* Invalid handling of back-to-back control IN requests.
    You must take special care to ensure software handles back-to-back control IN requests correctly. The USB specification allows you to delay the transmission of IN and OUT data packets by responding with a NAK. This mechanism allows USB transfers to be reliable, even with bad processing latency. The problem with control transfers is that SETUP packets must always be acknowledged and thus cannot be delayed with NAKs. For control transfers with either no data stage or an OUT data stage, this isn't a problem because the transfer ends with an IN request. The device can use the IN request (via NAKs) to delay further transfers until the device's RX buffer is ready for the next SETUP packet. The problem arises when the previous transfer was a control IN transfer because this kind of transfer ends with a data OUT stage. Typically, a device uses its RX buffer for both OUT and SETUP packets. This means that after the device receives the OUT packet, the device must immediately prepare this same buffer for s SETUP packet. Even if there is 1 ms delay in preparing this buffer after receiving the OUT packet, this may not be fast enough, leading to either clobbered OUT data or a dropped SETUP packet. This has affected all supported interfaces. You can find the fixes for the [k20/kl26 here](https://github.com/mbedmicro/DAPLink/commit/167c36c6c89f57b29d41701ff0d803fc0bf3b61d), the [atsam3u here](https://github.com/mbedmicro/DAPLink/commit/2bb5379717dcf67119165734f35a8a193cc35d51) and the [lpc11u35 here](https://github.com/mbedmicro/DAPLink/commit/0d5c577382fcb92b8dac756cb1ecc2cd45f417a4).

    Example of problematic control IN request:

    ```
        PC              DEV     Notes
        ------------------------------------------------------------
        SETUP   ->
                <-      IN
        OUT     ->              Host acknowledges the control request
                                with a zero length status OUT packet.
                                Device's RX buffer now contains OUT data
        SETUP   ->              Next SETUP packet arrives and either
                                clobbers previous RX buffer/flags (lpc11u35, atsam3u)
                                or the SETUP packet is dropped (k20, kl26).
    ```
                       
* Out of order processing on an endpoint
    Due to the architecture of the Keil v4 USB stack, IN endpoints are always listening for data, regardless of whether data is expected. This in itself is not a problem but can lead to problems if both an IN and OUT occur and the device processes them in the wrong order. On USB hardware with TX and RX complete interrupt bits rather than a FIFO, there is no way to determine whether the RX or TX occurred first if both are set. To prevent problems, *you must always process the TX interrupt before RX* if both are pending.

    Example of a SCSI transfer in which RX and TX are pending at the same time:

    ```
    PC              DEV         INTERRUPT       Notes
    ------------------------------------------------------------------------
    CBW     ->                  RX              RX interrupt is processed, cleared
                                                and RX prepared for new data. TX data
                                                is prepared for transfer
            <-      DATA        TX              TX interrupt is processed and cleared.
                                                TX CSW is prepared for transfer
            <-      CSW         TX              CSW is sent so TX interrupt is pending
    CBW     ->                  TX,RX           PC starts next SCSI command by sending CBW.
                                                Both TX and RX are pending at the same time.
    ```

    To correctly handle both TX and RX pending at the same time, make sure the code *processes TX before RX*:

    ```
    if (endpoint & TX_PENDING) {
        // do some endpoint processing
    }
    if (endpoint & RX_PENDING) {
        // do some endpoint processing
    }
    ```

## Existing USB quirks
* K20 and KL26
    * When sharing a hub with other full-speed USB devices, *corrupt data is occasionally sent*, leading to a USB re-enumeration. To mitigate this problem, either use this device on its own hub or use a multi-TT hub to isolate the full-speed traffic.
    * USB hardware has a four-entry FIFO that can overflow - mitigated [here](https://github.com/mbedmicro/DAPLink/commit/255bcb8986b3064ab940d29095e10a8225e965c5) - but it can still occur if interrupt latency is bad enough.
    * Because double buffering is not enabled, there is the device can drop a SETUP packet if the previous transfer was a control IN transfer. We mitigated this problem [here](https://github.com/mbedmicro/DAPLink/commit/167c36c6c89f57b29d41701ff0d803fc0bf3b61d), but it can still occur if interrupt latency is bad enough.
* ATSAM3U
    * With back-to-back control IN requests, the SETUP packet of the next request can overwrite the zero length status OUT of the first request. Because of this, the status OUT interrupt is lost. This is not a problem though because the USB stack does not use status OUT. For the change allowing the atsam3u driver to gracefully handle this scenario, see [here](https://github.com/mbedmicro/DAPLink/commit/2bb5379717dcf67119165734f35a8a193cc35d51).
* lpc11u35
    * Because the reception of a SETUP packet sets all the same interrupt flags as an OUT packet (and more), there is no way to tell whether an OUT packet preceded a SETUP packet, even though there is a dedicated buffer for each. To overcome this, the code keeps track of the type of control request and uses this information to determine whether the control request ends with a status OUT packet. The change that does this is [here](https://github.com/mbedmicro/DAPLink/commit/0d5c577382fcb92b8dac756cb1ecc2cd45f417a4).     

## Referenced PRs
* [Kinetis- Reduce chances of dropped setup packets](https://github.com/mbedmicro/DAPLink/commit/167c36c6c89f57b29d41701ff0d803fc0bf3b61d).
* [Kinetis - Prevent USB FIFO overflow](https://github.com/mbedmicro/DAPLink/commit/255bcb8986b3064ab940d29095e10a8225e965c5).
* [atsam3u - Prevent dropped USB SETUP packets](https://github.com/mbedmicro/DAPLink/commit/2bb5379717dcf67119165734f35a8a193cc35d51).
* [lpc11u35 - Prevent dropped USB SETUP packets](https://github.com/mbedmicro/DAPLink/commit/0d5c577382fcb92b8dac756cb1ecc2cd45f417a4).
* [Fix USB hang on lpc11u35 some MSD transfers](https://github.com/mbedmicro/DAPLink/commit/e0ca66880290216df298011a352af162f3fd1595).
