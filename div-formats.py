#!/usr/bin/env python2
# coding=utf-8

# TODO: FPG

from gimpfu import *
from struct import Struct
from itertools import repeat

class StructEx(Struct):
    def pack_to_file(self, file, *args):
        b = bytearray(self.size)
        self.pack_into(b, 0, *args)
        file.write(b)

    def unpack_from_file(self, file):
        b = file.read(self.size)
        return self.unpack_from(b)

pal_header = StructEx("<7sB")
pal_range_header = StructEx("<BB?B")
map_header = StructEx("<7sBHHL32s")
map_n_cpoints = StructEx("<H")
map_cpoint = StructEx("<hh")

def decode_str(raw_str, encoding="CP850"):
    return raw_str.partition('\0')[0].decode(encoding)

def encode_str(s, width, encoding="CP850"):
    return s.encode(encoding)[:width].ljust(width,'\0')

class Pal:
    class Range:
        DIRECT = 0
        EDIT1 = 1
        EDIT2 = 2
        EDIT4 = 4
        EDIT8 = 8

        def __init__(self, n_colors=16, type=0, fixed=False, black=0, colors = None):
            if colors == None:
                self.colors = bytearray([x if x<16 else 0 for x in range(32)])
            else:
                self.colors = bytearray(colors)
            self.n_colors = n_colors
            self.type = type
            self.fixed = fixed
            self.black = black

        @staticmethod
        def read(file):
            n_colors, type, fixed, black = pal_range_header.unpack_from_file(file)
            colors = bytearray(file.read(32))
            return Pal.Range(n_colors, type, fixed, black, colors)

        def write(self, file):
            pal_range_header.pack_to_file(file, self.n_colors, self.type, self.fixed, self.black)
            file.write(self.colors)

    def __init__(self, colors=None, ranges=None):
        self.version = 0
        if ranges == None:
            self.ranges = [Pal.Range(colors=[i * 16 + x if x<16 else 0 for x in range(32)]) for i in range(16)]
        else:
            self.ranges = ranges
        if colors == None:
            self.colors = bytearray(repeat(0, 256*3))
        else:
            assert len(colors) == 256*3
            self.colors = bytearray(colors)

    @staticmethod
    def read(file):
        magic, version = pal_header.unpack_from_file(file)
        if magic != b'pal\x1A\x0D\x0A\0':
            fail("Invalid PAL format")
        if version > 0:
            fail("Unsupported PAL format")
        return Pal.read_embedded(file)

    @staticmethod
    def read_embedded(file):
        colors = file.read(256*3)
        ranges = [Pal.Range.read(file) for i in range(16)]
        return Pal(colors=colors, ranges=ranges)

    def write(self, file):
        pal_header.pack_to_file(file, b'pal\x1A\x0D\x0A\0', 0)
        self.write_embedded(file)

    def write_embedded(self, file):
        file.write(self.colors)
        for r in [self.ranges[i] for i in range(16)]:
            r.write(file)

    @staticmethod
    def from_colormap(colormap):
        colors = bytearray([ord(x)>>2 for x in colormap[:768]]).ljust(768,b'\0')
        return Pal(colors=colors)

    def as_colormap(self):
        return bytes(bytearray([x<<2|x>>4 for x in self.colors]))


class Map:
    def __init__(self, w, h, palette=Pal(), cpoints=[], code=1, description='', pixels=None):
        assert w > 0 and h > 0
        if pixels != None:
            self.pixels = bytearray(pixels)
            assert len(self.pixels) == w*h
        else:
            self.pixels = bytearray(repeat(0,w*h))
        self.width = w
        self.height = h
        self.palette = palette
        self.cpoints = cpoints
        self.code = code
        self.description = description
        self.version = 0

    @staticmethod
    def read(file):
        magic, version, w, h, code, description = map_header.unpack_from_file(file)
        if magic != b"map\x1A\x0D\x0A\0":
            fail("Invalid MAP format")
        if version > 0:
            fail("Unsupported MAP format version: %d" % version)
        palette = Pal.read_embedded(file)
        n_cpoints, = map_n_cpoints.unpack_from_file(file)
        cpoints = [map_cpoint.unpack_from_file(file) for i in range(n_cpoints)]
        pixels = file.read(w*h)
        try:
            description = decode_str(description)
        except:
            description = ''
        return Map(w, h, code=code, palette=palette, cpoints=cpoints, description=description, pixels=pixels)

    def write(self, file):
        map_header.pack_to_file(file, b"map\x1A\x0D\x0A\0", 0, self.width, self.height,
            self.code, encode_str(self.description, 32))
        self.palette.write_embedded(file)
        map_n_cpoints.pack_to_file(file, len(self.cpoints))
        for cpoint in self.cpoints:
            map_cpoint.pack_to_file(file, *cpoint)
        file.write(self.pixels)

    def as_image(self, layername=None):
        img = gimp.Image(self.width, self.height, INDEXED)
        img.colormap = self.palette.as_colormap()
        layer = gimp.Layer(img, layername if layername else self.description,
            self.width, self.height, INDEXED_IMAGE, 100, NORMAL_MODE)
        pdb.gimp_image_insert_layer(img, layer, None, 0)
        rgn = layer.get_pixel_rgn(0, 0, self.width, self.height)
        rgn[:,:] = bytes(self.pixels)
        layer.flush()
        return img

    @staticmethod
    def from_drawable(drawable):
        palette = Pal.from_colormap(drawable.image.colormap)
        rgn = drawable.get_pixel_rgn(0, 0, drawable.width, drawable.height)
        return Map(drawable.width, drawable.height, palette=palette, pixels=rgn[:,:])

def load_map(filename, raw_filename):
    from os.path import basename
    with open(filename, "rb") as f:
        map = Map.read(f)
    return map.as_image(basename(filename))

def save_map(image, drawable, filename, raw_filename):
    if image.base_type != INDEXED:
        fail("MAP format allows indexed images only")
    if len(image.layers) != 1 or image.layers[0].bpp != 1:
        img2 = image.duplicate()
        img2.flatten()
        layer = img2.layers[0]
    else:
        img2 = None
        layer = image.layers[0]
    try:
        map = Map.from_drawable(layer)
        with open(filename, "wb") as f:
            map.write(f)
    finally:
        if img2:
            gimp.delete(img2)

def export_pal(palette, dirname, filename):
    from os.path import join
    num_colors, colors = pdb.gimp_palette_get_colors(palette)
    def add_color_bin(a,c):
        return a+chr(int(round(c.r*63)))+chr(int(round(c.g*63)))+chr(int(round(c.b*63)))
    cols = reduce(add_color_bin, colors, b'')
    pal = Pal(colors=cols[:768].ljust(768,b'\0'))
    with open(join(dirname,filename), "wb") as f:
        pal.write(f)

def register_load_handlers():
    gimp.register_load_handler('file-div-map-load', 'map', '')
    pdb['gimp-register-file-handler-mime']('file-div-map-load', 'image/div-map')

def register_save_handlers():
    gimp.register_save_handler('file-div-map-save', 'map', '')

register(
    'file-div-map-save', #name
    'Save a DIV Games Studio .map file', #description
    'Save a DIV Games Studio .map file',
    'Vii', #author
    'Vii', #copyright
    '2022', #year
    'DIV Games Studio MAP',
    'INDEXED',
    [   #input args. Format (type, name, description, default [, extra])
        (PF_IMAGE, "image", "Input image", None),
        (PF_DRAWABLE, "drawable", "Input drawable", None),
        (PF_STRING, "filename", "The name of the file", None),
        (PF_STRING, "raw-filename", "The name of the file", None),
    ],
    [], #results. Format (type, name, description)
    save_map, #callback
    on_query = register_save_handlers,
    menu = '<Save>'
)

register(
    'file-div-map-load', # name
    'Load a DIV Games Studio .map file', # description
    'Load a DIV Games Studio .map file',
    'Vii', # author
    'Vii', # copyright
    '2022', # year
    "DIV Games Studio MAP", # menu
    None, # image type
    [   #input args. Format (type, name, description, default [, extra])
        (PF_STRING, 'filename', 'The name of the file to load', None),
        (PF_STRING, 'raw-filename', 'The name entered', None),
    ],
    [(PF_IMAGE, 'image', 'Output image')], #results. Format (type, name, description)
    load_map, # callback
    on_query = register_load_handlers,
    menu = '<Load>'
)

register(
    'plug-in-div-palette-export-pal',
    'Export palette in DIV Games Studio PAL format',
    'Export palette in DIV Games Studio PAL format',
    'Vii',
    'Vii',
    '2022',
    '_DIV Games Studio PAL...',
    '',
    [
        (PF_STRING, 'palette', 'Name of palette to export', None),
        (PF_DIRNAME, 'dirname', 'Folder for the output file', ''),
        (PF_STRING, 'string', 'The name of the file to create', 'palette.pal'),
    ],
    [],
    export_pal,
    menu = '<Palettes>/Export as'
)

main()
