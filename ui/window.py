"""Fenêtre PC qui affiche le visage (tkinter, inclus avec Python sous Windows et macOS).
Sous Linux/Raspberry Pi : sudo apt install python3-tk.  Sur le robot, un autre module enverra l'image à l'écran SPI.
Touches : Espace = réveiller le robot (comme le mot d'activation), Échap = quitter."""
import time

from PIL import ImageTk

from .face import Face


def run_window(state, audio, events, stop, scale=2, fps=30, gain=1.0, sleep_after=90.0):
    import tkinter as tk

    root = tk.Tk()
    root.title("Robot")
    root.resizable(False, False)
    label = tk.Label(root, bd=0)
    label.pack()
    face = Face(scale=scale)

    def close(_=None):
        events.put(("quit",))
        stop.set()
        root.destroy()

    root.bind("<space>", lambda e: events.put(("wake", "key")))
    root.bind("<Escape>", close)
    root.protocol("WM_DELETE_WINDOW", close)
    delay = int(1000 / fps)

    def tick():
        if stop.is_set():
            try:
                root.destroy()
            except tk.TclError:
                pass
            return
        bands = [min(1.0, b * gain) for b in audio.band_levels()]
        mode, emotion = state.view(time.time(), sleep_after)
        photo = ImageTk.PhotoImage(face.render(mode, bands, audio.out_level(), emotion))
        label.configure(image=photo)
        label.image = photo            # garde une référence, sinon l'image disparaît
        root.after(delay, tick)

    root.after(0, tick)
    root.mainloop()
