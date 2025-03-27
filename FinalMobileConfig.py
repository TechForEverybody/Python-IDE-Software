fileContent = """import network
import time
import webrepl

def do_connect():
    
    # WiFi SSID and Password
    wifi_ssid = "ESP32-Access-Point-WiFi"             # YOUR WiFi SSID
    wifi_password = "12345678"     # YOUR WiFi PASSWORD

    # Wireless config : Station mode
    station = network.WLAN(network.AP_IF)
    station.active(True)
    station.config(essid=wifi_ssid, password=wifi_password)
    while station.active() == False:
        pass
    print("Connected!")
    print("My IP Address:", station.ifconfig()[0])
    


do_connect()
webrepl.start()"""

with open("MobileConfiguration.py", "w") as f:
    f.write(fileContent)
with open("mobile.py", "w") as f:
    f.write("print('Hello from ESP32!')")
with open("boot.py", "w") as f:
    f.write("""# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)
#import webrepl
#webrepl.start()
import MobileConfiguration
import mobile""")