
class NVS():
    def __init__(self, name):
        self.values = {}

    def get_i32(self, key):
        return self.values.get(key)
    
    def get_blob(self, key, buf : bytearray):
        v = self.values.get(key)
        for b in v:
          buf.append(ord(b))
        return len(v)

