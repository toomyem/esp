import network
import time
import camera
import socket
from machine import Pin
from esp32 import NVS

led = Pin(2, Pin.OUT)
captured_images = 0

def sleep(n):
    time.sleep(n)
    
def blink(n, delay=1):
    for i in range(n):
        led.value(1)
        sleep(delay)
        led.value(0)
        sleep(delay)
        
def connect_wifi():
    blink(1, delay=1)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    sleep(1)
    wlan.config(dhcp_hostname="esp32camera", reconnects=-1)

    if not wlan.isconnected():
        buf = bytearray(32)
        nvs = NVS("config")
        n = nvs.get_blob("ssid", buf)
        ssid = buf[0:n].decode()
        n = nvs.get_blob("key", buf)
        key = buf[0:n].decode()
    
        print("Connecting to network...")
        wlan.connect(ssid, key)
        while not wlan.isconnected():
            blink(1)
    print("Network config:", wlan.ifconfig())

def init_camera():
    blink(2, delay=0.2)
    print("Camera initialization")
    camera.deinit()
    camera.init(0, d0=4, d1=5, d2=18, d3=19, d4=36, d5=39, d6=34, d7=35,
                format=camera.JPEG, framesize=camera.FRAME_UXGA,
                xclk_freq=camera.XCLK_20MHz, href=23, vsync=25, reset=-1,
                pwdn=-1, sioc=27, siod=26, xclk=21, fb_location=camera.PSRAM)
    camera.framesize(camera.FRAME_UXGA)
    camera.flip(1)
    camera.mirror(1)
    camera.quality(10)
    print("Camera initialized")

def capture_image():
    global captured_images
    camera.capture()
    sleep(1)
    img = camera.capture()
    captured_images += 1
    return img
    
def send_bad_request(conn, msg=""):
    conn.send(b"HTTP/1.1 400 Bad request\r\n")
    conn.send(b"Content-Type: text/plain\r\n")
    conn.send(b"\r\n")
    conn.send(b"Invalid request!\r\n")
    if msg:
        conn.send(msg)

def send_image(conn, img):
    conn.send(b"HTTP/1.1 200 OK\r\n")
    conn.send(b"Content-Type: image/jpeg\r\n")
    conn.send(b"Content-Length: " + str(len(img)).encode() + b"\r\n")
    conn.send(b"Connection: close\r\n")
    conn.send(b"\r\n")
    conn.send(img)
    
def send_metrics(conn):
    metrics = (
        "# HELP captured_images Total number of images captured",
        "# TYPE captured_images counter",
        f"captured_images {captured_images}"
    )
    conn.send(b"HTTP/1.1 200 OK\r\n")
    conn.send(b"Content-Type: text/plain\r\n")
    conn.send(b"Connection: close\r\n")
    conn.send(b"\r\n")
    for m in metrics:
        conn.send(m.encode() + b"\r\n")

def send_ok(conn):
    conn.send(b"HTTP/1.1 200 OK\r\n")
    conn.send(b"Content-Type: text/plain\r\n")
    conn.send(b"Connection: close\r\n")
    conn.send(b"\r\n")
    conn.send(b"OK\r\n")

def send_index(conn):
    conn.send(b"HTTP/1.0 200 OK\r\n")
    conn.send(b"Content-Type: text/html\r\n")
    conn.send(b"Connection: close\r\n")
    conn.send(b"\r\n")
    conn.send(b"<html><head><title>esp32camera</title></head>\r\n")
    conn.send(b"<body>\r\n")
    conn.send(b"<p>Image:</p><img src='/image'></img>\r\n")
    conn.send(b"</body>\r\n")
    conn.send(b"</html>\r\n")

def req_is(req, value):
    return len(req) > 0 and req[0].startswith(value)
    
def main_loop():
    blink(3, delay=0.2)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn = None

    while True:
        try:
            sock.bind(("0.0.0.0", 8018))
            break
        except OSError:
            print("Cannot bind. Wait for a while and try again")
            sleep(15)
    sock.listen(1)

    while True:
        print("Waiting for connection")
        try:
            conn, addr = sock.accept()
            blink(1)
            print("Connection from:", addr)
            req = conn.recv(1024).splitlines()
            if req_is(req, b"GET / "):
                print("Request for index")
                send_index(conn)
            elif req_is(req, b"GET /image "):
                print("Request for image")
                img = capture_image()
                print(f"Image nr {captured_images}, size: {len(img)}")
                send_image(conn, img)
            elif req_is(req, b"GET /metrics "):
                print("Request for metric")
                send_metrics(conn)
            elif req_is(req, b"GET /health "):
                print("Request for health")
                send_ok(conn)
            else:
                print("Invalid request:", req[0])
                send_bad_request(conn, req[0])
        except KeyboardInterrupt:
            print("Interrupted")
            sock.close()
            break
        except Exception as ex:
            print("Error:", ex)
        finally:
            if conn:
                conn.close()
            
# ============================================================================================

connect_wifi()
init_camera()
main_loop()
