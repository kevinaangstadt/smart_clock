from phew import access_point, connect_to_wifi, is_connected_to_wifi, render_template, dns, server
from tm1637 import tm1637

import json
import machine
import network
import os
import ubinascii
import utime
import _thread
import uasyncio

import encrypted_file
import worldtimeapi

MACHINE_ID = ubinascii.hexlify(machine.unique_id()).decode().upper()

AP_NAME = "SmartClock " + MACHINE_ID
AP_DOMAIN = "smartclock.net"
AP_TEMPLATE_PATH = "ap_templates"
WIFI_FILE = "conf.dat"
WIFI_MAX_ATTEMPTS = 3

BTN_PIN = 18  # GPIO pin for the button
CLOCK_DATA = 21
CLOCK_CLK = 20


btn = machine.Pin(BTN_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
clock = tm1637.TM1637(clk=machine.Pin(CLOCK_CLK), dio=machine.Pin(CLOCK_DATA))
clock.write([0, 128, 0, 0])  # Initialize the clock display to 0000
clk_delta = 0
debounce = 250

brightness_options = [7, 3, 2, 1, 0]
brightness = 0  # Start with the highest brightness level

def brightness_callback(pin=None):
  global clk_delta, brightness
  if (utime.ticks_ms() - clk_delta) > debounce:
    clk_delta = utime.ticks_ms()
    brightness = (brightness + 1) % len(brightness_options)
    clock.brightness(brightness_options[brightness])  # Cycle through brightness levels

    # update the brightness in the config file
    try:
      settings = json.loads(encrypted_file.read_encrypted_file(WIFI_FILE))
      settings['brightness'] = brightness
      encrypted_file.store_encrypted_file(WIFI_FILE, json.dumps(settings))
    except Exception as e:
      print(f"Error updating brightness in config file: {e}")


# Assuming you have a function that scans and returns a list like:
# [('MyHomeWiFi', -45, True), ('NeighborNet', -75, True), ('OpenCafe', -82, False)]
# You would format it for the template like this:

def prepare_ssid_list_for_template(scanned_networks):
  ssid_list = []
  for ssid, bssid, channel, rssi, is_secure, _unused in scanned_networks:
    if len(ssid) == 0:
      continue
    ssid_list.append({
      "ssid": ssid,
      "rssi": rssi,
      "strength": 4 if rssi > -55 else 3 if rssi > -67 else 2 if rssi > -80 else 1,
      "security": is_secure > 0
    })
  return ssid_list


def machine_reset():
  utime.sleep(1)
  print("Resetting device...")
  machine.reset()


def setup_mode():
  print("Entering setup mode...")
  clock.show('conf')

  @server.route("/", methods=["GET"])
  def ap_index(request):
    if request.headers.get("host").lower() != AP_DOMAIN.lower():
      return render_template(f"{AP_TEMPLATE_PATH}/redirect.html", domain=AP_DOMAIN.lower())
    
    wlan = network.WLAN(network.STA_IF)
    MAC_ADDRESS = ubinascii.hexlify(wlan.config('mac'), ':').decode().upper()

    networks = prepare_ssid_list_for_template(wlan.scan())
    
    return render_template(f"{AP_TEMPLATE_PATH}/index.html", mac_address=MAC_ADDRESS, networks=networks)
  
  @server.route("/configure", methods=["POST"])
  def ap_configure(request):
    print("Saving wifi credentials...")

    # if both hidden_ssid and ssid are blank, redirect to index
    if not request.form.get("hidden_ssid") and not request.form.get("ssid"):
      return render_template(f"{AP_TEMPLATE_PATH}/redirect.html", domain = AP_DOMAIN)

    config = {
      'ssid': request.form.get("hidden_ssid", ""),
      'password': request.form.get("password", ""),
      'time_format': int(request.form.get("time_format", "12")),
      'brightness': 0,  # Default brightness
      'first_run': True  # Indicate that this is the first run
    }
    if not config['ssid']:
      config['ssid'] = request.form.get("ssid", "")

    encrypted_file.store_encrypted_file(WIFI_FILE, json.dumps(config))

    # Reboot from new thread after we have responded to the user.
    _thread.start_new_thread(machine_reset, ())
    return render_template(f"{AP_TEMPLATE_PATH}/configured.html", ssid=request.form["ssid"])
  
  @server.route("/scan.json", methods=["GET"])
  def ap_scan(request):
    wlan = network.WLAN(network.STA_IF)
    networks = prepare_ssid_list_for_template(wlan.scan())
    return json.dumps(networks), 200, {"Content-Type": "application/json"}
  
  @server.catchall()
  def ap_catch_all(request):
    if request.headers.get("host") != AP_DOMAIN:
      return render_template(f"{AP_TEMPLATE_PATH}/redirect.html", domain = AP_DOMAIN)

    return "Not found.", 404


  ap = access_point(AP_NAME)
  ip = ap.ifconfig()[0]
  dns.run_catchall(ip)

  server.run()


async def application_mode(time_format):

  def update_dst_settings():
    global dst_hour, dst_min, waiting_for_dst
    if timezone['dst']:
      waiting_for_dst = False
      dst_hour, dst_min = timezone['dst_until'].split("T")[1].split(":")[:2]
      dst_hour, dst_min = int(dst_hour), int(dst_min)
    else:
      waiting_for_dst = True
      dst_hour, dst_min = timezone['dst_from'].split("T")[1].split(":")[:2]
      dst_hour, dst_min = int(dst_hour), int(dst_min)

  led = machine.Pin("LED", machine.Pin.OUT)
  led.off()

  print("Syncing time with server...")
  import ntptime
  try:
    ntptime.settime()  # Set the RTC time from NTP
    valid_time = True
  except Exception:
    print("Failed to set time from NTP, using local time instead.")
    valid_time = False

  rtc = machine.RTC()

  print("Getting timezone information...")
  try:
    timezone = worldtimeapi.get_localized_time(refresh=True)
    o_hour, o_min = worldtimeapi.timezone_offset_hours_minutes()
  except Exception:
    print("Failed to get timezone information, using UTC.")
    timezone = {'dst': False, 'dst_from': '1970-01-01T01:00:00', 'dst_until': '1970-01-01T00:00:00'}
    o_hour, o_min = 0, 0
    
  update_dst_settings()

  # set up the button to change brightness
  btn.irq(trigger=machine.Pin.IRQ_FALLING, handler=brightness_callback)

  last_displayed_minute = -1

  def update_time():
    hours, minutes = (rtc.datetime()[4] + o_hour), rtc.datetime()[5] + o_min
    if time_format == 12:
      hours = hours % 12 or 12  # Convert to 12-hour format

    time_segments = clock.encode_string(f"{hours:2}{minutes:02}")
    if valid_time:
      time_segments[1] |= 0x80 # Set the colon segment
    clock.write(time_segments)  # Display current time on the clock

  print("Entering main loop...")

  while True:
    current_minute = rtc.datetime()[5]

    # ONLY update the display if the minute has changed
    if current_minute != last_displayed_minute:
      last_displayed_minute = current_minute
      update_time()

      # check if rtc matches the dst time
      if rtc.datetime()[4] == dst_hour and rtc.datetime()[5] == dst_min:
        o_hour, o_min = worldtimeapi.timezone_offset_hours_minutes(refresh=True)
        update_dst_settings()
        update_time()
      
      # if it's midnight, update the ntp time
      if current_minute == 0 and rtc.datetime()[3] == 0:
        try:
          ntptime.settime()  # Update the RTC time from NTP
          valid_time = True
          print("NTP time updated successfully.")
        except Exception as e:
          print(f"Failed to update NTP time: {e}")
          valid_time = False
   
    await uasyncio.sleep_ms(1000)


# figure out which mode to enter
try:
  os.stat(WIFI_FILE)

  settings = json.loads(encrypted_file.read_encrypted_file(WIFI_FILE))
  clock.brightness(brightness_options[min(settings.get("brightness", 0), len(brightness_options) - 1)])  # Set initial brightness

  wifi_current_attempt = 1

  # if the button is not pressed, we will try to connect to the wifi
  if btn.value() != 0:
    if settings.get("first_run", True):
      clock.show("conn")

    while (wifi_current_attempt <= WIFI_MAX_ATTEMPTS):
      ip_address = connect_to_wifi(settings["ssid"], settings["password"])

      if is_connected_to_wifi():
        print(f"Connected to wifi, IP address: {ip_address}")
        break
      else:
        wifi_current_attempt += 1
  else:
    # disconnect from wifi if the button is pressed
    print("Button pressed, resetting wifi connection...")
    os.remove(WIFI_FILE)
    machine.reset()
    
  if not is_connected_to_wifi():
    if settings.get("first_run", True):
      # Bad configuration, delete the credentials file, reboot
      # into setup mode to get new credentials from the user.
      print("Resetting wifi data...")
      os.remove(WIFI_FILE)
      machine_reset()
    else:
      # we are experiencing connection issues, so we will just sleep for a minute
      print("Failed to connect... Retrying in 60 seconds...")
      utime.sleep(60)
      machine_reset()
  

  # if we successfully connected to wifi, we will mark the first_run as False
  settings["first_run"] = False
  encrypted_file.store_encrypted_file(WIFI_FILE, json.dumps(settings))
    
except Exception as e:
  # Either no wifi configuration file found, or some other error occurred.
  print(f"Error reading wifi configuration: {e}")
  setup_mode()

uasyncio.run(application_mode(settings.get('time_format', 24)))
