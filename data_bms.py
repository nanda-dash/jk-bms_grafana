# This script reads the data from a JB BMS over RS-485 and formats
# it for use with https://github.com/BarkinSpider/SolarShed/

import time
import sys, os, io
import struct

# Plain serial... Modbus would have been nice, but oh well. 
import serial

sleepTime = 10

try:
    bms = serial.Serial('/dev/ttyUSB0')
    bms.baudrate = 115200
    bms.timeout  = 0.2
except:
    print("BMS not found.")

# The hex string composing the command, including CRC check etc.
# See also: 
# - https://github.com/syssi/esphome-jk-bms
# - https://github.com/NEEY-electronic/JK/tree/JK-BMS
# - https://github.com/Louisvdw/dbus-serialbattery

def sendBMSCommand(cmd_string):
    cmd_bytes = bytearray.fromhex(cmd_string)
    for cmd_byte in cmd_bytes:
        hex_byte = ("{0:02x}".format(cmd_byte))
        bms.write(bytearray.fromhex(hex_byte))
    return

# This could be much better, but it works.
def readBMS(fileObj):

    # Read all command
    sendBMSCommand('4E 57 00 13 00 00 00 00 06 03 00 00 00 00 00 00 68 00 00 01 29')
    
    time.sleep(.1)

    if bms.inWaiting() >= 4 :
        if bms.read(1).hex() == '4e' : # header byte 1
            if bms.read(1).hex() == '57' : # header byte 2
                # next two bytes is the length of the data package, including the two length bytes
                length = int.from_bytes(bms.read(2),byteorder='big')
                length -= 2 # Remaining after length bytes

                # Lets wait until all the data that should be there, really is present.
                # If not, something went wrong. Flush and exit
                available = bms.inWaiting()
                if available != length:
                    time.sleep(0.1)
                    # if it's not here by now, exit
                    if available != length:
                        bms.reset_input_buffer()
                        return None
               
                # Reconstruct the header and length field
                b = bytearray.fromhex("4e57") 
                b += (length+2).to_bytes(2, byteorder='big')
                
                # Read all the data
                data = bytearray(bms.read(available))
                # And re-attach the header (needed for CRC calculation)
                data = b + data 
        
                # Calculate the CRC sum
                crc_calc = sum(data[0:-4])
                # Extract the CRC value from the data
                crc_lo = struct.unpack_from('>H', data[-2:])[0]
                
                # Exit if CRC doesn't match
                if crc_calc != crc_lo :
                    bms.reset_input_buffer()
                    return None
            
                # The actual data we need
                data = data[11:length-19] # at location 0 we have 0x79
                
                # The byte at location 1 is the length count for the cell data bytes
                # Each cell has 3 bytes representing the voltage per cell in mV
                bytecount = data[1]
                
                # We can use this number to determine the total amount of cells we have
                cellcount = int(bytecount/3)                

                # Voltages start at index 2, in groups of 3
                for i in range(cellcount):
                    voltage = struct.unpack_from('>xH', data, i * 3 + 2)[0]/1000
                    valName  = "mode=\"cell"+str(i)+"_BMS1\""
                    valName  = "{" + valName + "}"
                    dataStr  = f"JK_BMS{valName} {voltage}"
                    print(dataStr, file=fileObj)

    bms.reset_input_buffer()    
           
while True:
    file_object = open('/ramdisk/JK_BMS.prom.tmp', mode='w')
    readBMS(file_object)
    file_object.flush()
    file_object.close()
    outLine = os.system('/bin/mv /ramdisk/JK_BMS.prom.tmp /ramdisk/JK_BMS.prom')
    
    time.sleep(sleepTime)

