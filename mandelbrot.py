"""
Mandelbrot Set Viewer
=====================
Controls:
  Left click + drag   — pan
  Scroll wheel        — zoom in/out
  Right click         — zoom in at cursor
  R                   — reset view
  S                   — save screenshot (mandelbrot.png)
  +/-                 — increase/decrease max iterations
  1-6                 — switch color palette
  Esc                 — quit

Requirements:
  pip install numpy pillow
  (tkinter is included with most Python distributions)
"""

import tkinter as tk
from tkinter import ttk
import numpy as np
from PIL import Image, ImageTk
import time


# ---------------------------------------------------------------------------
# Mandelbrot computation (NumPy vectorised — fast enough for interactive use)
# ---------------------------------------------------------------------------

def compute_mandelbrot(xmin, xmax, ymin, ymax, width, height, max_iter):
    x = np.linspace(xmin, xmax, width, dtype=np.float64)
    y = np.linspace(ymin, ymax, height, dtype=np.float64)
    C = x[np.newaxis, :] + 1j * y[:, np.newaxis]

    Z = np.zeros_like(C)
    M = np.zeros(C.shape, dtype=np.float32)   # smooth iteration count
    active = np.ones(C.shape, dtype=bool)

    for i in range(1, max_iter + 1):
        Z[active] = Z[active] ** 2 + C[active]
        escaped = active & (np.abs(Z) > 2.0)
        # Smooth colouring: ν = i − log₂(log₂|Z|)
        absZ = np.abs(Z[escaped])
        absZ = np.where(absZ < 1.0001, 1.0001, absZ)
        M[escaped] = i - np.log2(np.log2(absZ))
        active[escaped] = False
        if not active.any():
            break

    # Points that never escaped → iteration count 0 (will be coloured black)
    M[active] = 0
    return M


# ---------------------------------------------------------------------------
# Colour palettes
# ---------------------------------------------------------------------------

def make_palette(name, size=2048):
    t = np.linspace(0, 1, size)
    if name == "Electric":
        r = (np.sin(t * 6.28 * 1.0 + 0.0) * 127 + 128).astype(np.uint8)
        g = (np.sin(t * 6.28 * 1.5 + 2.1) * 127 + 128).astype(np.uint8)
        b = (np.sin(t * 6.28 * 2.0 + 4.2) * 127 + 128).astype(np.uint8)
    elif name == "Fire":
        r = np.clip(t * 3.0, 0, 1)
        g = np.clip(t * 3.0 - 1.0, 0, 1)
        b = np.clip(t * 3.0 - 2.0, 0, 1)
        r, g, b = (r * 255).astype(np.uint8), (g * 255).astype(np.uint8), (b * 255).astype(np.uint8)
    elif name == "Ocean":
        r = (np.sin(t * 3.14) * 80).astype(np.uint8)
        g = (t * 200 + 55).astype(np.uint8)
        b = (np.sin(t * 3.14 * 2) * 100 + 155).astype(np.uint8)
    elif name == "Pastel":
        r = (np.sin(t * 3.14 * 2.0) * 60 + 195).astype(np.uint8)
        g = (np.sin(t * 3.14 * 3.0 + 1) * 60 + 195).astype(np.uint8)
        b = (np.sin(t * 3.14 * 1.5 + 2) * 60 + 195).astype(np.uint8)
    elif name == "Greyscale":
        v = (t * 255).astype(np.uint8)
        r = g = b = v
    else:  # "Ultra"
        r = (np.sin(t * 6.28 * 0.7 + 0.5) * 100 + 155).astype(np.uint8)
        g = (np.sin(t * 6.28 * 1.3 + 1.5) * 100 + 100).astype(np.uint8)
        b = (np.sin(t * 6.28 * 2.1 + 3.0) * 100 + 155).astype(np.uint8)
    return np.stack([r, g, b], axis=1)   # shape (size, 3)


PALETTE_NAMES = ["Ultra", "Electric", "Fire", "Ocean", "Pastel", "Greyscale"]


def iterations_to_rgb(M, palette, max_iter):
    """Map smooth iteration counts → RGB uint8 array."""
    h, w = M.shape
    img = np.zeros((h, w, 3), dtype=np.uint8)
    interior = M == 0
    exterior = ~interior
    if exterior.any():
        t = (M[exterior] % 1024) / 1024.0          # wrap period
        idx = (t * (len(palette) - 1)).astype(int)
        img[exterior] = palette[idx]
    # Interior (Mandelbrot set proper) stays black
    return img


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class MandelbrotViewer:
    DEFAULT_BOUNDS = (-2.5, 1.0, -1.25, 1.25)   # xmin, xmax, ymin, ymax
    WIDTH, HEIGHT = 900, 700

    def __init__(self, root):
        self.root = root
        self.root.title("Mandelbrot Viewer")
        self.root.configure(bg="#0e0e0e")
        self.root.resizable(True, True)

        # View state
        self.xmin, self.xmax, self.ymin, self.ymax = self.DEFAULT_BOUNDS
        self.max_iter = 256
        self.palette_idx = 0
        self.palettes = {name: make_palette(name) for name in PALETTE_NAMES}
        self._drag_start = None
        self._drag_bounds = None
        self._photo = None
        self._render_pending = False

        self._build_ui()
        self._bind_events()
        self._render()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # Top toolbar
        toolbar = tk.Frame(self.root, bg="#1a1a1a", pady=6)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        tk.Label(toolbar, text="MANDELBROT", fg="#e0e0e0",
                 bg="#1a1a1a", font=("Courier", 13, "bold")).pack(side=tk.LEFT, padx=12)

        # Palette selector
        tk.Label(toolbar, text="Palette:", fg="#888", bg="#1a1a1a",
                 font=("Courier", 10)).pack(side=tk.LEFT, padx=(20, 4))
        self.palette_var = tk.StringVar(value=PALETTE_NAMES[0])
        combo = ttk.Combobox(toolbar, textvariable=self.palette_var,
                             values=PALETTE_NAMES, width=10, state="readonly",
                             font=("Courier", 10))
        combo.pack(side=tk.LEFT)
        combo.bind("<<ComboboxSelected>>", lambda e: self._change_palette())

        # Iterations
        tk.Label(toolbar, text="Iterations:", fg="#888", bg="#1a1a1a",
                 font=("Courier", 10)).pack(side=tk.LEFT, padx=(20, 4))
        self.iter_var = tk.IntVar(value=self.max_iter)
        iter_spin = tk.Spinbox(toolbar, from_=64, to=4096, increment=64,
                               textvariable=self.iter_var, width=5,
                               font=("Courier", 10), bg="#2a2a2a", fg="#e0e0e0",
                               buttonbackground="#333",
                               command=self._change_iters)
        iter_spin.pack(side=tk.LEFT)
        iter_spin.bind("<Return>", lambda e: self._change_iters())

        # Reset button
        tk.Button(toolbar, text="Reset [R]", command=self.reset,
                  bg="#2a2a2a", fg="#e0e0e0", relief=tk.FLAT,
                  font=("Courier", 10), padx=8).pack(side=tk.LEFT, padx=16)

        # Save button
        tk.Button(toolbar, text="Save [S]", command=self.save_image,
                  bg="#2a2a2a", fg="#e0e0e0", relief=tk.FLAT,
                  font=("Courier", 10), padx=8).pack(side=tk.LEFT)

        # Canvas
        self.canvas = tk.Canvas(self.root, width=self.WIDTH, height=self.HEIGHT,
                                bg="#000", cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status = tk.Label(self.root, textvariable=self.status_var,
                          fg="#666", bg="#0e0e0e", font=("Courier", 9),
                          anchor=tk.W, padx=8)
        status.pack(fill=tk.X, side=tk.BOTTOM)

    # ---------------------------------------------------------------- Events

    def _bind_events(self):
        c = self.canvas
        c.bind("<ButtonPress-1>", self._on_drag_start)
        c.bind("<B1-Motion>", self._on_drag_move)
        c.bind("<ButtonRelease-1>", self._on_drag_end)
        c.bind("<ButtonPress-3>", self._on_right_click)
        c.bind("<MouseWheel>", self._on_scroll)        # Windows / macOS
        c.bind("<Button-4>", self._on_scroll)          # Linux scroll up
        c.bind("<Button-5>", self._on_scroll)          # Linux scroll down
        c.bind("<Configure>", lambda e: self._schedule_render())
        self.root.bind("<r>", lambda e: self.reset())
        self.root.bind("<R>", lambda e: self.reset())
        self.root.bind("<s>", lambda e: self.save_image())
        self.root.bind("<S>", lambda e: self.save_image())
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.bind("<plus>", lambda e: self._step_iters(2))
        self.root.bind("<equal>", lambda e: self._step_iters(2))
        self.root.bind("<minus>", lambda e: self._step_iters(0.5))
        for i, name in enumerate(PALETTE_NAMES, 1):
            self.root.bind(str(i), lambda e, n=name: self._set_palette(n))

    # ----------------------------------------------------------- Pan / zoom

    def _canvas_size(self):
        w = self.canvas.winfo_width() or self.WIDTH
        h = self.canvas.winfo_height() or self.HEIGHT
        return w, h

    def _pixel_to_complex(self, px, py):
        w, h = self._canvas_size()
        x = self.xmin + (self.xmax - self.xmin) * px / w
        y = self.ymin + (self.ymax - self.ymin) * py / h
        return x, y

    def _zoom(self, cx, cy, factor):
        rx = self.xmax - self.xmin
        ry = self.ymax - self.ymin
        new_rx = rx * factor
        new_ry = ry * factor
        self.xmin = cx - new_rx * (cx - self.xmin) / rx
        self.xmax = self.xmin + new_rx
        self.ymin = cy - new_ry * (cy - self.ymin) / ry
        self.ymax = self.ymin + new_ry
        self._schedule_render()

    def _on_drag_start(self, event):
        self._drag_start = (event.x, event.y)
        self._drag_bounds = (self.xmin, self.xmax, self.ymin, self.ymax)

    def _on_drag_move(self, event):
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        w, h = self._canvas_size()
        xmin0, xmax0, ymin0, ymax0 = self._drag_bounds
        span_x = xmax0 - xmin0
        span_y = ymax0 - ymin0
        self.xmin = xmin0 - dx * span_x / w
        self.xmax = xmax0 - dx * span_x / w
        self.ymin = ymin0 - dy * span_y / h
        self.ymax = ymax0 - dy * span_y / h
        self._schedule_render(delay=80)

    def _on_drag_end(self, event):
        self._drag_start = None
        self._schedule_render(delay=0)

    def _on_right_click(self, event):
        cx, cy = self._pixel_to_complex(event.x, event.y)
        self._zoom(cx, cy, 0.35)

    def _on_scroll(self, event):
        cx, cy = self._pixel_to_complex(event.x, event.y)
        if event.num == 5 or event.delta < 0:
            factor = 1.3
        else:
            factor = 1 / 1.3
        self._zoom(cx, cy, factor)

    # ------------------------------------------------------ Palette / iters

    def _change_palette(self):
        self.palette_idx = PALETTE_NAMES.index(self.palette_var.get())
        self._schedule_render(delay=0)

    def _set_palette(self, name):
        self.palette_var.set(name)
        self._change_palette()

    def _change_iters(self):
        try:
            val = int(self.iter_var.get())
            val = max(64, min(4096, val))
            self.max_iter = val
            self.iter_var.set(val)
            self._schedule_render(delay=0)
        except (ValueError, tk.TclError):
            pass

    def _step_iters(self, factor):
        self.max_iter = int(max(64, min(4096, self.max_iter * factor)))
        self.iter_var.set(self.max_iter)
        self._schedule_render(delay=0)

    # ----------------------------------------------------------------- Reset

    def reset(self):
        self.xmin, self.xmax, self.ymin, self.ymax = self.DEFAULT_BOUNDS
        self._schedule_render(delay=0)

    # --------------------------------------------------------------- Render

    def _schedule_render(self, delay=150):
        if self._render_pending:
            self.root.after_cancel(self._render_job)
        self._render_pending = True
        self._render_job = self.root.after(delay, self._render)

    def _render(self):
        self._render_pending = False
        w, h = self._canvas_size()
        if w < 10 or h < 10:
            return

        t0 = time.perf_counter()
        self.status_var.set("Rendering…")
        self.root.update_idletasks()

        M = compute_mandelbrot(self.xmin, self.xmax, self.ymin, self.ymax,
                               w, h, self.max_iter)

        palette = self.palettes[self.palette_var.get()]
        rgb = iterations_to_rgb(M, palette, self.max_iter)

        img = Image.fromarray(rgb, "RGB")
        self._photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)

        elapsed = time.perf_counter() - t0
        cx = (self.xmin + self.xmax) / 2
        cy = (self.ymin + self.ymax) / 2
        span = self.xmax - self.xmin
        self.status_var.set(
            f"centre ({cx:.6f}, {cy:.6f})  zoom ×{2.5/span:.1f}  "
            f"iter {self.max_iter}  rendered in {elapsed*1000:.0f} ms"
        )

    # -------------------------------------------------------------- Save

    def save_image(self):
        w, h = self._canvas_size()
        M = compute_mandelbrot(self.xmin, self.xmax, self.ymin, self.ymax,
                               w, h, self.max_iter)
        palette = self.palettes[self.palette_var.get()]
        rgb = iterations_to_rgb(M, palette, self.max_iter)
        path = "mandelbrot.png"
        Image.fromarray(rgb, "RGB").save(path)
        self.status_var.set(f"Saved → {path}")


# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()
    app = MandelbrotViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
