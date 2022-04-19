#!/usr/bin/env python2
# coding=utf-8

from gimpfu import *

import pygtk
pygtk.require('2.0')

import gimpui
import gtk, gtk.gdk, gobject

from div_formats import Fpg

class FpgTool(gimpui.Dialog):

    RESPONSE_SAVE = 1
    RESPONSE_SAVE_AS = 2

    def __init__(self, label="Untitled", filepath=None, fpg=None):
        proc_name = 'plug-in-div-open-fpg'
        super(FpgTool, self).__init__(proc_name, "python-fu", None, 0, None, proc_name,
                       (gtk.STOCK_SAVE, FpgTool.RESPONSE_SAVE,
                        gtk.STOCK_SAVE_AS, FpgTool.RESPONSE_SAVE_AS,
                        gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
        self.label = label
        self.dirty = False
        self.update_title()

        if not fpg:
            if not filepath:
                self.fpg = Fpg()
            else:
                with open(filepath, "rb") as f:
                    self.fpg = Fpg.read(f)
        else:
            self.fpg = fpg
        self.filepath = filepath

        gimp.progress_init("Building preview...")
        store = gtk.ListStore(gobject.TYPE_INT, gtk.gdk.Pixbuf, gobject.TYPE_STRING)
        n = 0.0
        for m in self.fpg.maps:
            store.append((m.code, m.as_pixbuf(scale_size=(100,75)), m.description))
            n += 1.0
            pdb.gimp_progress_update(n / len(self.fpg.maps))
        pdb.gimp_progress_end()

        sw = gtk.ScrolledWindow()
        sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        sw.set_border_width(12)
        sw.set_size_request(-1, 300)
        self.vbox.pack_start(sw)

        treeview = gtk.TreeView(store)
        treeview.set_rules_hint(True)
        treeview.set_search_column(2)

        #renderer = gtk.CellRendererToggle()
        ##renderer.connect('toggled', self.fixed_toggled, model)
        #column = gtk.TreeViewColumn('Load', renderer, active=0)
        ## set this column to a fixed sizing(of 50 pixels)
        ##column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        ##column.set_fixed_width(50)
        #treeview.append_column(column)

        column = gtk.TreeViewColumn('Code', gtk.CellRendererText(), text=0)
        column.set_sort_column_id(0)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        treeview.append_column(column)

        column = gtk.TreeViewColumn('Preview', gtk.CellRendererPixbuf(), pixbuf=1)
        column.set_resizable(True)
        #column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        treeview.append_column(column)

        column = gtk.TreeViewColumn('Description', gtk.CellRendererText(), text=2)
        column.set_sort_column_id(2)
        column.set_resizable(True)
        treeview.append_column(column)

        sw.add(treeview)
        sw.show_all()

        def response(dlg, id):
            if id in (gtk.RESPONSE_CLOSE, gtk.RESPONSE_CANCEL, gtk.RESPONSE_DELETE_EVENT):
                # TODO: check if unsaved changes
                gtk.main_quit()

        self.connect("response", response)

        self.show()
        gtk.main()

    def update_title(self):
        self.set_title("FPG - " + self.label + '*' if self.dirty else '')

if __name__=='__main__':
    def add_filters(dialog):
        f = gtk.FileFilter()
        f.set_name("FPG files")
        f.add_pattern("*.fpg")
        dialog.add_filter(f)

        f = gtk.FileFilter()
        f.set_name("All files")
        f.add_pattern("*")
        dialog.add_filter(f)

    def new_fpg(*args):
        gimpui.gimp_ui_init()
        tool = FpgTool()

    def open_fpg(*args):
        gimpui.gimp_ui_init()
        dialog = gtk.FileChooserDialog(
                             title="Open FPG",
                             action=(gtk.FILE_CHOOSER_ACTION_OPEN),
                             buttons=(gtk.STOCK_CANCEL,
                                    gtk.RESPONSE_CANCEL,
                                    gtk.STOCK_OPEN,
                                    gtk.RESPONSE_OK))
        dialog.set_alternative_button_order ((gtk.RESPONSE_OK, gtk.RESPONSE_CANCEL))
        add_filters(dialog)
        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            from os.path import basename
            file = dialog.get_filename()
            dialog.destroy()
            try:
                gimp.progress_init("Loading FPG: " + file)
                with open(file, "rb") as f:
                    fpg = Fpg.read(f, pdb.gimp_progress_update)
            except:
                raise
            finally:
                pdb.gimp_progress_end()
            tool = FpgTool(label=basename(file), filepath=file, fpg=fpg)
        else:
            dialog.destroy()

    register(
        'plug-in-div-new-fpg',
        'Open a new FPG in the DIV Games Studio FPG tool',
        'Open a new FPG in the DIV Games Studio FPG tool',
        'Vii',
        'Vii',
        '2022',
        'New FPG',
        None,
        [],
        [],
        new_fpg,
        menu='<Image>/File/Create'
    )

    register(
        'plug-in-div-open-fpg',
        'Load FPG in the DIV Games Studio FPG tool',
        'Load FPG in the DIV Games Studio FPG tool',
        'Vii',
        'Vii',
        '2022',
        'Open FPG...',
        None,
        [],
        [],
        open_fpg,
        menu='<Image>/File/Open'
    )

    main()
