"""Takes the screenshot the selection is drawn on.

Vertorama reads the screen directly, which needs X11: on Wayland one app
can't scroll another's window, so there's no point capturing there yet.

The screenshot is cut down to the monitor under the pointer, with the scale
between that monitor's logical size (what windows and the page use) and its
real pixels, so HiDPI and fractional scaling line up.
"""

import os
from dataclasses import dataclass

from gi.repository import Gdk
from PIL import Image


@dataclass
class Frame:
    image: object          # PIL image of one monitor, in real pixels
    monitor: int           # GDK monitor index
    logical: tuple         # (x, y, width, height) of that monitor, logical pixels
    scale: float           # real pixels per logical pixel


def is_wayland():
    display = Gdk.Display.get_default()
    if display is not None and type(display).__name__.startswith("GdkWayland"):
        return True
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def monitor_under_pointer():
    display = Gdk.Display.get_default()
    _screen, x, y = display.get_default_seat().get_pointer().get_position()
    monitor = display.get_monitor_at_point(x, y) or display.get_primary_monitor() or display.get_monitor(0)
    index = next(i for i in range(display.get_n_monitors()) if display.get_monitor(i) == monitor)
    g = monitor.get_geometry()
    return index, (g.x, g.y, g.width, g.height)


def desktop_bounds():
    """The logical rectangle covering every monitor."""
    display = Gdk.Display.get_default()
    rects = [display.get_monitor(i).get_geometry() for i in range(display.get_n_monitors())]
    x0 = min(r.x for r in rects)
    y0 = min(r.y for r in rects)
    x1 = max(r.x + r.width for r in rects)
    y1 = max(r.y + r.height for r in rects)
    return x0, y0, x1 - x0, y1 - y0


def monitor_box(image_size, bounds, monitor):
    """Where one monitor sits inside a whole-desktop screenshot.

    image_size: (width, height) of the screenshot, in real pixels
    bounds:     (x, y, width, height) of the whole desktop, logical pixels
    monitor:    (x, y, width, height) of the monitor, logical pixels
    Returns (crop box in real pixels, real pixels per logical pixel).
    """
    bx, by, bw, _bh = bounds
    mx, my, mw, mh = monitor
    scale = image_size[0] / bw if bw else 1.0
    box = (round((mx - bx) * scale), round((my - by) * scale),
           round((mx - bx + mw) * scale), round((my - by + mh) * scale))
    return box, scale


def to_frame(full):
    """Cut a whole-desktop screenshot down to the monitor under the pointer."""
    index, monitor = monitor_under_pointer()
    box, scale = monitor_box(full.size, desktop_bounds(), monitor)
    image = full.crop(box) if box != (0, 0, full.width, full.height) else full
    return Frame(image=image, monitor=index, logical=monitor, scale=scale)


# -- X11 -------------------------------------------------------------------------

def capture_x11():
    root = Gdk.get_default_root_window()
    if root is None:
        raise RuntimeError("no root window")
    scale = root.get_scale_factor()
    w, h = root.get_width(), root.get_height()
    pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, w, h)
    if pixbuf is None:
        raise RuntimeError("couldn't read the screen")
    mode = "RGBA" if pixbuf.get_has_alpha() else "RGB"
    image = Image.frombytes(mode, (pixbuf.get_width(), pixbuf.get_height()),
                            pixbuf.get_pixels(), "raw", mode, pixbuf.get_rowstride()).convert("RGB")
    if scale > 1 and image.width == w:   # some setups hand back logical pixels
        image = image.resize((w * scale, h * scale), Image.LANCZOS)
    return image


def capture():
    """A Frame of the monitor under the pointer."""
    return to_frame(capture_x11())
