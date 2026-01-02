"""Simple holder for the currently-generated image surface.
Screens read from this module to render the latest image.
"""
_current_image = None

def set_image(surf):
    global _current_image
    _current_image = surf

def get_image():
    return _current_image
