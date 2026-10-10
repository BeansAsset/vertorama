"""Scrolling and capturing.

Vertorama scrolls the area itself (X11), waits for the content to settle,
captures, and hands each frame to the stitcher, until scrolling no longer
moves anything. Move the mouse to stop early: you keep what was captured.

On Wayland, apps can't send scroll events to other windows without a
permission portal, so automatic scrolling is X11-only for now.
"""

import time

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402

from .stitch import Stitcher  # noqa: E402

SETTLE_EVERY = 70       # ms between checks while waiting for scrolling to stop
SETTLE_MAX = 900        # ms to wait at most
MAX_FRAMES = 400
CANCEL_DISTANCE = 12    # pixels the pointer may drift before we take it as "stop"


def grab(x, y, w, h):
    """A region of the screen in real pixels, as a PIL image (X11)."""
    root = Gdk.get_default_root_window()
    pixbuf = Gdk.pixbuf_get_from_window(root, x, y, w, h)
    if pixbuf is None:
        raise RuntimeError("couldn't read the screen")
    mode = "RGBA" if pixbuf.get_has_alpha() else "RGB"
    return Image.frombytes(mode, (pixbuf.get_width(), pixbuf.get_height()), pixbuf.get_pixels(),
                           "raw", mode, pixbuf.get_rowstride()).convert("RGB")


class Pointer:
    """Move the pointer and send scroll-wheel clicks through XTest."""

    def __init__(self):
        from Xlib import display
        from Xlib.ext import xtest
        self.X = __import__("Xlib.X", fromlist=["X"])
        self.xtest = xtest
        self.d = display.Display()
        self.root = self.d.screen().root

    def position(self):
        p = self.root.query_pointer()
        return p.root_x, p.root_y

    def move(self, x, y):
        self.root.warp_pointer(int(x), int(y))
        self.d.sync()

    def activate(self, xid):
        """Ask the window manager to raise and focus a window, the way a
        taskbar does (window managers honour that more readily than a
        request from an ordinary app)."""
        from Xlib import protocol
        atom = self.d.intern_atom("_NET_ACTIVE_WINDOW")
        event = protocol.event.ClientMessage(window=self.d.create_resource_object("window", xid),
                                             client_type=atom, data=(32, [2, 0, 0, 0, 0]))
        self.root.send_event(event, event_mask=self.X.SubstructureRedirectMask | self.X.SubstructureNotifyMask)
        self.d.sync()

    def scroll(self, clicks):
        button = 5 if clicks > 0 else 4      # 5 = wheel down, 4 = wheel up
        for _ in range(abs(clicks)):
            self.xtest.fake_input(self.d, self.X.ButtonPress, button)
            self.xtest.fake_input(self.d, self.X.ButtonRelease, button)
        self.d.sync()


def window_stack():
    """The desktop's windows, top first, as GDK windows (X11)."""
    screen = Gdk.Screen.get_default()
    stack = screen.get_window_stack() or []
    try:
        gi.require_version("GdkX11", "3.0")
        from gi.repository import GdkX11
        workspace = GdkX11.X11Screen.get_current_desktop(screen)
    except (ImportError, ValueError, AttributeError, TypeError):
        workspace = None
    out = []
    for w in reversed(stack):
        if w.get_state() & Gdk.WindowState.ICONIFIED:
            continue
        if workspace is not None and hasattr(w, "get_desktop") and w.get_desktop() not in (workspace, 0xFFFFFFFF):
            continue
        out.append(w)
    return out


def window_at(stack, x, y):
    """The topmost window in `stack` covering the point (logical pixels)."""
    for w in stack:
        r = w.get_frame_extents()
        if r.x <= x < r.x + r.width and r.y <= y < r.y + r.height:
            return w
    return None


def is_on_top(xid, x, y):
    top = window_at(window_stack(), x, y)
    return top is not None and top.get_xid() == xid


def server_time(gdk_window):
    """The X server's current time, for focus requests. Only pass one of
    Vertorama's own windows: it waits for an event that other apps' windows
    never send us."""
    try:
        gi.require_version("GdkX11", "3.0")
        from gi.repository import GdkX11
        return GdkX11.x11_get_server_time(gdk_window)
    except (ImportError, ValueError, TypeError):
        return Gdk.CURRENT_TIME


def same_image(a, b):
    return ImageChops.difference(a, b).getbbox() is None


class Unroller:
    """Scroll and capture a region (real pixels) on the GLib main loop.
    on_done(image, reason) where reason is "end", "stopped", "limit" or
    "lost" (the content jumped in a way that couldn't be matched)."""

    def __init__(self, region, on_done, on_progress=None, target=None, point=None):
        """target: the X id of the window to scroll, raised first if something
        else covers it; point: a spot inside the region, in logical pixels."""
        self.x, self.y, self.w, self.h = (int(v) for v in region)
        self.target, self.point = target, point
        self.tries = 0
        self.on_done, self.on_progress = on_done, on_progress
        self.pointer = Pointer()
        self.stitcher = Stitcher()
        self.clicks = 3
        self.still = 0
        self.frames = 0
        self.home = None
        self.original = None

    def start(self):
        if self.target is None or is_on_top(self.target, *self.point):
            self._begin()
        else:
            self.pointer.activate(self.target)
            GLib.timeout_add(120, self._wait_on_top)

    def _wait_on_top(self):
        self.tries += 1
        if is_on_top(self.target, *self.point):
            GLib.timeout_add(150, lambda: (self._begin(), False)[1])   # let it repaint
            return False
        if self.tries == 6:
            self.pointer.activate(self.target)
        if self.tries >= 12:
            self._begin()        # do our best with whatever is there
            return False
        return True

    def _begin(self):
        self.original = self.pointer.position()
        self.home = (self.x + self.w // 2, self.y + self.h // 2)
        self.pointer.move(*self.home)
        GLib.timeout_add(150, self._first)

    def _first(self):
        self.stitcher.add(grab(self.x, self.y, self.w, self.h))
        self._scroll()
        return False

    def _moved_by_user(self):
        px, py = self.pointer.position()
        return abs(px - self.home[0]) > CANCEL_DISTANCE or abs(py - self.home[1]) > CANCEL_DISTANCE

    def _scroll(self):
        if self._moved_by_user():
            self._finish("stopped")
            return
        self.pointer.scroll(self.clicks)
        self._settle_started = time.monotonic()
        self._previous = None
        GLib.timeout_add(SETTLE_EVERY, self._settle)

    def _settle(self):
        """Wait until two captures in a row are identical (scrolling stopped)."""
        frame = grab(self.x, self.y, self.w, self.h)
        waited = (time.monotonic() - self._settle_started) * 1000
        if self._previous is None or (not same_image(frame, self._previous) and waited < SETTLE_MAX):
            self._previous = frame
            return True
        self._take(frame)
        return False

    def _take(self, frame):
        self.frames += 1
        shift = self.stitcher.add(frame)
        body = self.h - self.stitcher.header - self.stitcher.footer
        if shift is None:
            if self.clicks > 1:
                # Probably scrolled too far for any overlap: go back and take smaller steps.
                self.pointer.scroll(-self.clicks)
                self.clicks = 1
                GLib.timeout_add(SETTLE_MAX // 2, lambda: (self._scroll(), False)[1])
                return
            self._finish("lost")
            return
        if shift == 0:
            self.still += 1
            if self.still >= 2:
                self._finish("end")
                return
        else:
            self.still = 0
            # Aim for each step to move about half the visible area.
            if shift > body * 0.7 and self.clicks > 1:
                self.clicks -= 1
            elif shift < body * 0.3 and self.clicks < 12:
                self.clicks += 1
        if self.on_progress:
            self.on_progress(self.stitcher.height, self.frames)
        if self.stitcher.full or self.frames >= MAX_FRAMES:
            self._finish("limit")
            return
        self._scroll()

    def _finish(self, reason):
        if reason != "stopped" and self.original:
            self.pointer.move(*self.original)
        self.on_done(self.stitcher.result(), reason)
