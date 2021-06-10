#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2011      Nick Hall
# Copyright (C) 2011      Rob G. Healey <robhealey1@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
#-------------------------------------------------------------------------
#
# Python modules
#
#-------------------------------------------------------------------------
import os
import logging

_LOG = logging.getLogger(".libmetadata")


#-------------------------------------------------------------------------
#
# GNOME modules
#
#-------------------------------------------------------------------------
from gi.repository import Gtk
import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import GObject


#-------------------------------------------------------------------------
#
# Gramps modules
#
#-------------------------------------------------------------------------

from gramps.gui.listmodel import ListModel, NOSORT, IMAGE as COL_IMAGE
from gramps.gen.const import GRAMPS_LOCALE as glocale
_ = glocale.translation.gettext
from gramps.gen.utils.place import conv_lat_lon
from fractions import Fraction
from gramps.gen.lib import Date
from gramps.gen.datehandler import displayer
from datetime import datetime
from gramps.gui.widgets import SelectionWidget, Region

THUMBNAIL_IMAGE_SIZE = (40, 40)

def format_datetime(datestring):
    """
    Convert an exif timestamp into a string for display, using the
    standard Gramps date format.
    """
    try:
        timestamp = datetime.strptime(datestring, '%Y:%m:%d %H:%M:%S')
    except ValueError:
        return _('Invalid format')
    date_part = Date()
    date_part.set_yr_mon_day(timestamp.year, timestamp.month, timestamp.day)
    date_str = displayer.display(date_part)
    time_str = _('%(hr)02d:%(min)02d:%(sec)02d') % {'hr': timestamp.hour,
                                                    'min': timestamp.minute,
                                                    'sec': timestamp.second}
    return _('%(date)s %(time)s') % {'date': date_str, 'time': time_str}

def format_gps(raw_dms, nsew):
    """
    Convert raw degrees, minutes, seconds and a direction
    reference into a string for display.
    """
    value = 0.0
    divisor = 1.0
    for val in raw_dms.split(' '):
        try:
            num = float(val.split('/')[0]) / float(val.split('/')[1])
        except (ValueError, IndexError):
            value = None
            break
        value += num / divisor
        divisor *= 60

    if nsew == 'N':
        result = conv_lat_lon(str(value), '0', 'DEG')[0]
    elif nsew == 'S':
        result = conv_lat_lon('-' + str(value), '0', 'DEG')[0]
    elif nsew == 'E':
        result = conv_lat_lon('0', str(value), 'DEG')[1]
    elif nsew == 'W':
        result = conv_lat_lon('0', '-' + str(value), 'DEG')[1]
    else:
        result = None

    return result if result is not None else _('Invalid format')

def get_NamedRegions(self, key, metadata, image_path, mypixbuf):
    self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
    self.selection_widget.original_image_size = (self.pixbuf.get_width(),
                                        self.pixbuf.get_height())

    region_tag = 'Xmp.mwg-rs.Regions/mwg-rs:RegionList[%s]/'
    region_name = region_tag + 'mwg-rs:Name'
    region_type = region_tag + 'mwg-rs:Type'
    region_x = region_tag + 'mwg-rs:Area/stArea:x'
    region_y = region_tag + 'mwg-rs:Area/stArea:y'
    region_w = region_tag + 'mwg-rs:Area/stArea:w'
    region_h = region_tag + 'mwg-rs:Area/stArea:h'
    region_unit = region_tag + 'mwg-rs:Area/stArea:unit'
    i = 1
    while True:
        name = metadata.get(region_name % i)
        region_name_display = region_name % i
        if name is None:
            break
        try:
            x = float(metadata.get(region_x % i)) * 100
            y = float(metadata.get(region_y % i)) * 100
            w = float(metadata.get(region_w % i)) * 100
            h = float(metadata.get(region_h % i)) * 100
        except ValueError:
            x = y = 50
            w = h = 100

        rtype = metadata.get(region_type % i)
        unit = metadata.get(region_unit % i)

        # ensure region does not exceed bounds of image
        rect_p1 = x - (w / 2)
        if rect_p1 < 0:
            rect_p1 = 0
        rect_p2 = y - (h / 2)
        if rect_p2 < 0:
            rect_p2 = 0
        rect_p3 = x + (w / 2)
        if rect_p3 > 100:
            rect_p3 = 100
        rect_p4 =  y + (h / 2)
        if rect_p4 > 100:
            rect_p4 = 100

        rect = (rect_p1, rect_p2, rect_p3, rect_p4)
        coords = self.selection_widget.proportional_to_real_rect(rect)

        xmp_region = Region(*coords)

        thumbnail = get_thumbnail(self, xmp_region, THUMBNAIL_IMAGE_SIZE)
        self.model.add(['People', region_name_display, thumbnail, name])
        i += 1

def get_thumbnail(self, region, thumbnail_size):
    """
    Returns the thumbnail of the given region.
    """
    w = region.x2 - region.x1
    h = region.y2 - region.y1
    if w >= 1 and h >= 1 and self.pixbuf:
        subpixbuf = self.pixbuf.new_subpixbuf(region.x1, region.y1, w, h)
        size = resize_keep_aspect(w, h, *thumbnail_size)
        return subpixbuf.scale_simple(size[0], size[1],
                                      GdkPixbuf.InterpType.BILINEAR)
    else:
        return None

def resize_keep_aspect(orig_x, orig_y, target_x, target_y):
    """
    Calculates the dimensions of the rectangle obtained from
    the rectangle orig_x * orig_y by scaling to fit
    target_x * target_y keeping the aspect ratio.
    """
    orig_aspect = orig_x / orig_y
    target_aspect = target_x / target_y
    if orig_aspect > target_aspect:
        return (target_x, target_x * orig_y // orig_x)
    else:
        return (target_y * orig_x // orig_y, target_y)

DESCRIPTION = _('Description')
DATE = _('Description')
IMAGEX = _('Image')
CAMERA = _('Camera')
GPS = _('GPS')
ADVANCED = _('Advanced')
XMP = _('XMP')
DIGIKAM = _('digiKam')
MSPHOTO = _('Microsoft Photo Schema')
ADOBELR = _('Lightroom Schema')
ACDSEE = _('ACDSee Schema')
IPTC = _('IPTC')
EXIF = _('EXIF')
PEOPLE = _('People')
RIGHTS = _('Rights')
TAGGING = _('Tagging')


TAGS = [(DESCRIPTION, 'Exif.Image.ImageDescription', None, None, None),
        (DESCRIPTION, 'Exif.Image.XPSubject', None, None, None),
        (DESCRIPTION, 'Exif.Image.XPComment', None, None, None),
        (DESCRIPTION, 'Exif.Image.Rating', None, None, None),
        (DESCRIPTION, 'Xmp.dc.title', None, None, None),
        (DESCRIPTION, 'Xmp.dc.description', None, None, None),
        (DESCRIPTION, 'Xmp.dc.subject', None, None, None),
        (DESCRIPTION, 'Xmp.acdsee.caption', None, None, None),
        (DESCRIPTION, 'Xmp.acdsee.notes', None, None, None),

        (DESCRIPTION, 'Iptc.Application2.Caption', None, None, None),
        (DESCRIPTION, 'Exif.Photo.UserComment', None, None, None),
        (DATE, 'Exif.Photo.DateTimeOriginal', None, format_datetime, None),
        (DATE, 'Exif.Photo.DateTimeDigitized', None, format_datetime, None),
        (DATE, 'Exif.Image.DateTime', None, format_datetime, None),
        (DATE, 'Exif.Image.TimeZoneOffset', None, None, None),
        (PEOPLE, 'Xmp.mwg-rs.Regions/mwg-rs:RegionList[1]/mwg-rs:Name', None, None, get_NamedRegions),
        (PEOPLE, 'Xmp.iptcExt.PersonInImage', None, None, None),
        (GPS, 'Exif.GPSInfo.GPSLatitude',  'Exif.GPSInfo.GPSLatitudeRef', format_gps, None),
        (GPS, 'Exif.GPSInfo.GPSLongitude', 'Exif.GPSInfo.GPSLongitudeRef', format_gps, None),
        (GPS, 'Exif.GPSInfo.GPSAltitude', 'Exif.GPSInfo.GPSAltitudeRef', None, None),
        (GPS, 'Exif.GPSInfo.GPSTimeStamp', None, None, None),
        (GPS, 'Exif.GPSInfo.GPSSatellites', None, None, None),
        (TAGGING, 'Exif.Image.XPKeywords', None, None, None),
        (TAGGING, 'Iptc.Application2.Keywords', None, None, None),
        (TAGGING, 'Xmp.mwg-kw.Hierarchy', None, None, None),
        (TAGGING, 'Xmp.mwg-kw.Keywords', None, None, None),
        (TAGGING, 'Xmp.digiKam.TagsList', None, None, None),
        (TAGGING, 'Xmp.MicrosoftPhoto.LastKeywordXMP', None, None, None),
        (TAGGING, 'Xmp.MicrosoftPhoto.LastKeywordIPTC', None, None, None),
        (TAGGING, 'Xmp.lr.hierarchicalSubject', None, None, None),
        (TAGGING, 'Xmp.acdsee.categories', None, None, None),
        (IMAGEX, 'Exif.Image.DocumentName', None, None, None),
        (IMAGEX, 'Exif.Photo.PixelXDimension', None, None, None),
        (IMAGEX, 'Exif.Photo.PixelYDimension', None, None, None),
        (IMAGEX, 'Exif.Image.XResolution', 'Exif.Image.ResolutionUnit', None, None),
        (IMAGEX, 'Exif.Image.YResolution', 'Exif.Image.ResolutionUnit', None, None),
        (IMAGEX, 'Exif.Image.Orientation', None, None, None),
        (IMAGEX, 'Exif.Photo.ColorSpace', None, None, None),
        (IMAGEX, 'Exif.Image.YCbCrPositioning', None, None, None),
        (IMAGEX, 'Exif.Photo.ComponentsConfiguration', None, None, None),
        (IMAGEX, 'Exif.Image.Compression', None, None, None),
        (IMAGEX, 'Exif.Photo.CompressedBitsPerPixel', None, None, None),
        (IMAGEX, 'Exif.Image.PhotometricInterpretation', None, None, None),
        (RIGHTS, 'Exif.Image.Copyright', None, None, None),
        (RIGHTS, 'Exif.Image.Artist', None, None, None),
        (CAMERA, 'Exif.Image.Make', None, None, None),
        (CAMERA, 'Exif.Image.Model', None, None, None),
        (CAMERA, 'Exif.Photo.FNumber', None, None, None),
        (CAMERA, 'Exif.Photo.ExposureTime', None, None, None),
        (CAMERA, 'Exif.Photo.ISOSpeedRatings', None, None, None),
        (CAMERA, 'Exif.Photo.FocalLength', None, None, None),
        (CAMERA, 'Exif.Photo.FocalLengthIn35mmFilm', None, None, None),
        (CAMERA, 'Exif.Photo.MaxApertureValue', None, None, None),
        (CAMERA, 'Exif.Photo.MeteringMode', None, None, None),
        (CAMERA, 'Exif.Photo.ExposureProgram', None, None, None),
        (CAMERA, 'Exif.Photo.ExposureBiasValue', None, None, None),
        (CAMERA, 'Exif.Photo.Flash', None, None, None),
        (CAMERA, 'Exif.Image.FlashEnergy', None, None, None),
        (CAMERA, 'Exif.Image.SelfTimerMode', None, None, None),
        (CAMERA, 'Exif.Image.SubjectDistance', None, None, None),
        (CAMERA, 'Exif.Photo.Contrast', None, None, None),
        (CAMERA, 'Exif.Photo.LightSource', None, None, None),
        (CAMERA, 'Exif.Photo.Saturation', None, None, None),
        (CAMERA, 'Exif.Photo.Sharpness', None, None, None),
        (CAMERA, 'Exif.Photo.WhiteBalance', None, None, None),
        (CAMERA, 'Exif.Photo.DigitalZoomRatio', None, None, None),
        (ADVANCED, 'Exif.Image.Software', None, None, None),
        (ADVANCED, 'Exif.Photo.ImageUniqueID', None, None, None),
        (ADVANCED, 'Exif.Image.CameraSerialNumber', None, None, None),
        (ADVANCED, 'Exif.Photo.ExifVersion', None, None, None),
        (ADVANCED, 'Exif.Photo.FlashpixVersion', None, None, None),
        (ADVANCED, 'Exif.Image.ExifTag', None, None, None),
        (ADVANCED, 'Exif.Image.GPSTag', None, None, None),
        (ADVANCED, 'Exif.Image.BatteryLevel', None, None, None)]

class MetadataView(Gtk.TreeView):

    def __init__(self):
        Gtk.TreeView.__init__(self)
        self.sections = {}
        titles = [(_('Section'), 0, 100),
                  (_('Key'), 1, 235),
                  (_('Thumbnail'), NOSORT, 50, COL_IMAGE),
                  (_('Value'), 3, 325)]
        self.model = ListModel(self, titles, list_mode="list")

    def display_exif_tags(self, image_path):
        """
        Display the exif tags.
        """
        self.sections = {}
        self.model.clear()
        self.selection_widget = SelectionWidget()
        if not os.path.exists(image_path):
            return False

        retval = False
        with open(image_path, 'rb') as fd:
            try:
                buf = fd.read()
                metadata = GExiv2.Metadata()
                metadata.open_buf(buf)
                mypixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
                get_human = metadata.get_tag_interpreted_string

                for section, key, key2, func, func2 in TAGS:
                    if not key in metadata.get_exif_tags() + metadata.get_xmp_tags() + metadata.get_iptc_tags():
                        continue

                    if func is not None and func2 is not None:
                        continue

                    if func2 is not None:
                        func2(self, metadata[key], metadata, image_path, mypixbuf)
                        continue

                    if func is not None:
                        if key2 is None:
                            human_value = func(metadata[key])
                        else:
                            if key2 in metadata.get_exif_tags() + metadata.get_xmp_tags() + metadata.get_iptc_tags():
                                human_value = func(metadata[key], metadata[key2])
                            else:
                                human_value = func(metadata[key], None)
                    else:
                        human_value = get_human(key)
                        if key2 in metadata.get_exif_tags() + metadata.get_xmp_tags() + metadata.get_iptc_tags():
                            human_value += ' ' + get_human(key2)

                    label = metadata.get_tag_label(key)
                    #node = self.__add_section(section)
                    if human_value is None:
                        human_value = ''
                    thumbnail = None
                    self.model.add([section, key, thumbnail, human_value])

                    self.model.tree.expand_all()
                    retval = self.model.count > 0
            except:
                pass

        return retval

    def __add_section(self, section):
        """
        Add the section heading node to the model.
        """
        if section not in self.sections:
            node = self.model.add([section, ''])
            self.sections[section] = node
        else:
            node = self.sections[section]
        return node

    def get_has_data(self, image_path):
        """
        Return True if the gramplet has data, else return False.
        """
        if not os.path.exists(image_path):
            return False
        with open(image_path, 'rb') as fd:
            retval = False
            try:
                buf = fd.read()
                metadata = GExiv2.Metadata()
                metadata.open_buf(buf)
                for tag in TAGS:
                    if tag in metadata.get_exif_tags() + metadata.get_xmp_tags() + metadata.get_iptc_tags():
                        retval = True
                        break
            except:
                pass

        return retval
