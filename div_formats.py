#!/usr/bin/env python2
# coding=utf-8

from gimpfu import *
from struct import Struct
from itertools import repeat
from os.path import basename

class StructEx(Struct):
    def pack_to_file(self, file, *args):
        b = bytearray(self.size)
        self.pack_into(b, 0, *args)
        file.write(b)

    def unpack_from_file(self, file):
        b = file.read(self.size)
        if len(b) == 0:
            return None
        return self.unpack_from(b)

pal_header = StructEx("<7sB")
pal_range_header = StructEx("<BB?B")
map_header = StructEx("<7sBHHL32s")
map_n_cpoints = StructEx("<H")
map_cpoint = StructEx("<hh")
fpg_header = StructEx("<7sB")
fpg_map_header = StructEx("LL32s12sLLL")

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
    def __init__(self, w, h, palette=Pal(), cpoints=[], code=1, description='', pixels=None, filename=''):
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
        self.filename = filename

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

    def as_pixbuf(self, colormap=None, scale_size=None):
        from gtk.gdk import pixbuf_new_from_data, COLORSPACE_RGB, INTERP_BILINEAR
        if colormap is None:
            colormap = self.palette.as_colormap()
        def convert():
            for p in self.pixels:
                i = p*3
                yield colormap[i]
                yield colormap[i+1]
                yield colormap[i+2]
        pixbuf = pixbuf_new_from_data(bytes(bytearray(convert())),
            COLORSPACE_RGB, False, 8, self.width, self.height, self.width*3)
        if scale_size is not None and (self.width > scale_size[0] or self.height > scale_size[1]):
            w, h = scale_size
            if self.width > self.height:
                h = self.height * w / self.width
            else:
                w = self.width * h / self.height
            pixbuf = pixbuf.scale_simple(w, h, INTERP_BILINEAR)
        return pixbuf


class Fpg:
    def __init__(self, palette=Pal(), maps=[]):
        self.palette = palette
        maps.sort(key=lambda m: m.code)
        self.maps = maps

    @staticmethod
    def read(file, progress_update=None):
        import os
        pos = file.tell()
        file.seek(0, os.SEEK_END)
        totalsize = float(file.tell() - pos)
        file.seek(pos, os.SEEK_SET)
        magic, version = fpg_header.unpack_from_file(file)
        if magic != b"fpg\x1A\x0D\x0A\0":
            fail("Invalid FPG format")
        if version > 0:
            fail("Unsupported FPG format version: %d" % version)
        palette = Pal.read_embedded(file)
        maps = []
        pos = file.tell()
        if progress_update: progress_update(pos / totalsize)
        data = fpg_map_header.unpack_from_file(file)
        while data is not None:
            code, length, description, filename, width, height, n_cpoints = data
            try:
                description = decode_str(description)
            except:
                description = ''
            try:
                filename = decode_str(filename)
            except:
                filename = ''
            cpoints = [map_cpoint.unpack_from_file(file) for i in range(n_cpoints)]
            pixels = file.read(width*height)
            maps.append(Map(width, height, code=code, palette=palette, cpoints=cpoints, description=description, pixels=pixels, filename=filename))
            pos += length
            if progress_update: progress_update(pos / totalsize)
            file.seek(pos)
            data = fpg_map_header.unpack_from_file(file)
        return Fpg(palette=palette, maps=maps)


"""    
    gimp.progress_init("Loading FPG...")
    with open(filename, "rb") as f:
        fpg = Fpg.read(f, pdb.gimp_progress_update)
    pdb.gimp_progress_end()

    import pygtk
    pygtk.require('2.0')

    import gimpui
    import gtk, gtk.gdk, gobject

    gimp.progress_init("Building preview...")
    gimpui.gimp_ui_init()
    proc_name = "file-div-fpg-load"
    dialog = gimpui.Dialog(proc_name, "python-fu", None, 0, None, proc_name,
                           (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                            gtk.STOCK_OK, gtk.RESPONSE_OK))
    dialog.set_transient()
    dialog.set_title("Load images from FPG")

    store = gtk.ListStore(gobject.TYPE_BOOLEAN, gobject.TYPE_INT, gtk.gdk.Pixbuf, gobject.TYPE_STRING)
    n = 0.0
    for map in fpg.maps:
        store.append((False, map.code, map.as_pixbuf(scale_size=(100,75)), map.description))
        n += 1.0
        pdb.gimp_progress_update(n / len(fpg.maps))
    pdb.gimp_progress_end()

    sw = gtk.ScrolledWindow()
    sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
    sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
    sw.set_border_width(12)
    sw.set_size_request(-1, 300)
    dialog.vbox.pack_start(sw)

    treeview = gtk.TreeView(store)
    treeview.set_rules_hint(True)
    treeview.set_search_column(2)

    renderer = gtk.CellRendererToggle()
    #renderer.connect('toggled', self.fixed_toggled, model)
    column = gtk.TreeViewColumn('Load', renderer, active=0)
    # set this column to a fixed sizing(of 50 pixels)
    #column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
    #column.set_fixed_width(50)
    treeview.append_column(column)

    column = gtk.TreeViewColumn('Code', gtk.CellRendererText(), text=1)
    column.set_sort_column_id(1)
    column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
    treeview.append_column(column)

    column = gtk.TreeViewColumn('Preview', gtk.CellRendererPixbuf(), pixbuf=2)
    column.set_resizable(True)
    #column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
    treeview.append_column(column)

    column = gtk.TreeViewColumn('Description', gtk.CellRendererText(), text=3)
    column.set_sort_column_id(3)
    column.set_resizable(True)
    treeview.append_column(column)

    sw.add(treeview)
    sw.show_all()

    def response(dlg, id):
        if id == gtk.RESPONSE_OK:
            dlg.set_response_sensitive(gtk.RESPONSE_OK, False)
            dlg.set_response_sensitive(gtk.RESPONSE_CANCEL, False)
            try:
                # hacer cosas...
                dialog.res = 1 # resultado
            except CancelError: # si hace falta
                pass
            except Exception:
                # mensaje de error y volvemos
                dlg.set_response_sensitive(gtk.RESPONSE_OK, True)
                dlg.set_response_sensitive(gtk.RESPONSE_CANCEL, True)
                raise
            else:
                # todo ha ido bien
                pass
        gtk.main_quit()

    dialog.connect("response", response)

    dialog.show()
    gtk.main()

    if hasattr(dialog, "res"):
        res = dialog.res
        dialog.destroy()
        return res
    else:
        dialog.destroy()
        raise CancelError
"""

if __name__=='__main__':
    def load_map(filename, raw_filename):    
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

    def import_pal(palette, filename):
        from gimpcolor import RGB
        with open(filename,"rb") as f:
            pal = Pal.read(f)
        name = pdb.gimp_palette_new(basename(filename))
        pdb.gimp_palette_set_columns(name, 16)
        for i in range(0, 768, 3):
            r, g, b = iter(pal.colors[i:i+3])
            colorname = "#%02x%02x%02x" % (r<<2|r>>4, g<<2|g>>4, b<<2|b>>4)
            color = RGB(r/63.0, g/63.0, b/63.0)
            pdb.gimp_palette_add_entry(name, colorname, color)
        pdb.gimp_context_set_palette(name)
        return name

    def register_load_handlers():
        gimp.register_load_handler('file-div-map-load', 'map', '')
        pdb['gimp-register-file-handler-mime']('file-div-map-load', 'image/x-div-map')
    #    gimp.register_load_handler('file-div-fpg-load', 'fpg', '')
    #    pdb['gimp-register-file-handler-mime']('file-div-fpg-load', 'image/x-div-fpg')

    def register_save_handlers():
        gimp.register_save_handler('file-div-map-save', 'map', '')

    #register(
    #    'file-div-fpg-load', # name
    #    'Load maps from a DIV Games Studio .fpg file', # description
    #    'Load maps from a DIV Games Studio .fpg file',
    #    'Vii', # author
    #    'Vii', # copyright
    #    '2022', # year
    #    "DIV Games Studio FPG", # menu
    #    None, # image type
    #    [   #input args. Format (type, name, description, default [, extra])
    #        (PF_STRING, 'filename', 'The name of the file to load', None),
    #        (PF_STRING, 'raw-filename', 'The name entered', None),
    #    ],
    #    [(PF_IMAGE, 'image', 'Output image')], #results. Format (type, name, description)
    #    load_fpg, # callback
    ##    on_query = register_load_handlers,
    #    menu = '<Load>'
    #)

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

    register(
        'plug-in-div-palette-import-pal',
        'Import palette in DIV Games Studio PAL format',
        'Import palette in DIV Games Studio PAL format',
        'Vii',
        'Vii',
        '2022',
        'Import _PAL...',
        '',
        [
            (PF_STRING, 'palette', 'Dummy parameter', None),
            (PF_FILE, 'file', 'PAL file to import', ''),
        ],
        [(PF_PALETTE, "new-palette", "Result")],
        import_pal,
        menu = '<Palettes>'
    )

    main()
