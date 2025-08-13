
JPEG = 1
FRAME_UXGA = 2
XCLK_20MHz = 3
XCLK_10MHz = 4
PSRAM = 5

def deinit():
    pass

def init(id, **dict):
    pass

def framesize(size):
    pass

def flip(flag):
    pass

def mirror(flag):
    pass

def quality(value):
    pass


def capture():
    f = open("sample.jpg", "rb")
    img = f.read()
    f.close()
    return img

