import network
import time
import camera
import socket
import select
import sys
from machine import Pin
from esp32 import NVS

led = Pin(2, Pin.OUT)
captured_images = 0

def sleep(n):
    time.sleep(n)

def led_on():
    led.value(1)
    sleep(1)

def led_off():
    led.value(0)
    sleep(1)

def init_camera():
    led_on()
    print("Camera initialization")
    camera.deinit()
    camera.init(0, d0=4, d1=5, d2=18, d3=19, d4=36, d5=39, d6=34, d7=35,
                format=camera.JPEG,
                framesize=camera.FRAME_UXGA,
                xclk_freq=camera.XCLK_10MHz, href=23, vsync=25, reset=-1,
                pwdn=-1, sioc=27, siod=26, xclk=21, fb_location=camera.PSRAM)
    camera.flip(1)
    camera.mirror(1)
    camera.quality(10)
    print("Camera initialized")
    led_off()

def connect_wifi():
    led_on()
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
            sleep(1)
    print("Network config:", wlan.ifconfig())
    led_off()
    
def make_sock():
    led_on()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            sock.bind(("0.0.0.0", 8018))
            break
        except OSError:
            print("Cannot bind. Will try again...")
            sleep(10)
    sock.listen(5)
    led_off()
    return sock

def capture_image():
    global captured_images
    camera.capture()
    sleep(1)
    img = camera.capture()
    captured_images += 1
    return img
    
def metrics():
    body = "# HELP captured_images Total number of images captured\r\n" + \
        "# TYPE captured_images counter\r\n" + \
        "captured_images " + str(captured_images) + "\r\n"
    return body

def index_page():
    body = f"""
    <html><head><title>esp32camera</title></head>
    <body>
    <p>Image:</p><img src='/image'></img>
    </body></html>
    """
    return body

def resp_ok(body, media_type="text/plain", headers={}):
    if type(body) == str: body = body.encode()
    resp = "HTTP/1.1 200 OK\r\n" + \
        "Content-Type: " + media_type + "\r\n" + \
        "Content-Length: " + str(len(body)) + "\r\n" + \
        "".join([f"{key}: {value}\r\n" for (key, value) in headers.items()]) + \
        "\r\n"
    return resp.encode() + body

def resp_not_found(body, media_type="text/plain"):
    if type(body) == str: body = body.encode()
    resp = "HTTP/1.1 404 Not found\r\n" + \
        "Content-Type: " + media_type + "\r\n" + \
        "Content-Length: " + str(len(body)) + "\r\n" + \
        "\r\n"
    return resp.encode() + body

def resp_error(body, media_type="text/plain"):
    if type(body) == str: body = body.encode()
    resp = "HTTP/1.1 400 Invalid request\r\n" + \
        "Content-Type: " + media_type + "\r\n" + \
        "Content-Length: " + str(len(body)) + "\r\n" + \
        "\r\n"
    return resp.encode() + body

class Buf():
    def __init__(self, fn):
        self.fn = fn
        self.req = b""
        self.resp = b""

    def __repr__(self):
        return f"Buf({self.fn},{self.req},{len(self.resp)})"
    
    def recv(self, conn):
        buf = conn.read()
        if len(buf) > 0:
            print(f"Got from {self.fn}: <{buf}>")
            self.req += buf
            return True
        return False
    
    def send(self, conn):
        if len(self.resp) > 0:
            n = conn.send(self.resp)
            self.resp = self.resp[n:]
            print(f"Sent {n} bytes to {self.fn}, {len(self.resp)} bytes left")

    def handle(self):
        n = self.req.find(b"\r\n\r\n")
        if n == -1: return
        req = self.req[:n].decode()
        self.req = self.req[n+4:]
        
        if req.startswith("GET /health "):
            resp = resp_ok("OK\r\n")
        elif req.startswith("GET /image "):
            img = capture_image()
            resp = resp_ok(img, "image/jpeg",
                           headers={"Content-Disposition": "inline; filename=image.jpg"})
            del img
        elif req.startswith("GET /metrics "):
            resp = resp_ok(metrics())
        elif req.startswith("GET / "):
            resp = resp_ok(index_page(), "text/html")
        elif req.startswith("GET "):
            resp = resp_not_found("Not found\r\n")
        else:
            resp = b"HTTP/1.1 400 Invalid request\r\n\r\n"
            
        self.resp += resp
        
def main_loop(sock):
    poll = select.poll()
    poll.register(sock, select.POLLIN)
    data = {}
    print(f"Ready for connections")
    
    while True:
        try:
            for p in poll.poll():
                conn, ev = p[:2]
                fn = conn.fileno()
                if ev & (select.POLLERR | select.POLLHUP):
                    print(f"Closing connection: {fn} {ev}")
                    conn.close()
                    poll.unregister(conn)
                    continue
                
                if conn == sock:
                    conn, addr = sock.accept()
                    conn.setblocking(False)
                    fn = conn.fileno()
                    print(f"Registering {fn} from {addr}")
                    poll.register(conn, select.POLLIN | select.POLLOUT)
                    data[fn] = Buf(fn)
                    continue

                buf = data[fn]
                
                if ev & select.POLLIN:
                    if buf.recv(conn):
                        buf.handle()
                    else:
                        print(f"Closing connection: {fn}")
                        conn.close()
                        poll.unregister(conn)
                    continue

                if ev & select.POLLOUT:
                    buf.send(conn)
                    continue
                
        except Exception as ex:
            print("Error:", ex)
            sys.print_exception(ex)
        except KeyboardInterrupt:
            print("Interrupted")
            sock.close()
            break
            
# ============================================================================================

init_camera()
connect_wifi()
sock = make_sock()
main_loop(sock)

