import network
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
webrepl.start()

