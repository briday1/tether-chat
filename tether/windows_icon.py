"""Render the existing horizon mark at native resolution for every icon size."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import struct

ICON_SIZES = (16, 20, 24, 28, 32, 40, 48, 56, 64, 96, 128, 192, 256)


def _curve(start, control, end, count=100):
    return [((1-t)**2*start[0]+2*(1-t)*t*control[0]+t*t*end[0],
             (1-t)**2*start[1]+2*(1-t)*t*control[1]+t*t*end[1])
            for t in (i/count for i in range(count+1))]


@lru_cache(maxsize=24)
def raster(size):
    """Supersample the same three hills as the SVG; preserve transparent padding."""
    from PIL import Image, ImageDraw
    if not isinstance(size, int) or not 8 <= size <= 1024:
        raise ValueError('Icon size must be between 8 and 1024 pixels')
    work=max(256,size*4)
    scale=work/64
    image=Image.new('RGBA',(work,work),(201,217,198,255))
    draw=ImageDraw.Draw(image)
    for start,control,end,second,end2,color in [
        ((2,31),(21,23),(34,31),(47,39),(62,29),(140,171,150,255)),
        ((2,39),(23,29),(35,39),(47,49),(62,36),(93,134,108,255)),
        ((2,49),(28,38),(42,47),(56,56),(62,42),(40,77,62,255)),
    ]:
        points=_curve(start,control,end)+_curve(end,second,end2)[1:]+[(62,64),(2,64)]
        draw.polygon([(x*scale,y*scale) for x,y in points],fill=color)
    mask=Image.new('L',(work,work),0)
    # A small transparent inset avoids caption/tray clipping at 125–300% DPI.
    ImageDraw.Draw(mask).ellipse((4*scale,4*scale,60*scale,60*scale),fill=255)
    image.putalpha(mask)
    image=image.resize((size,size),Image.Resampling.LANCZOS)
    # Remove ringing at the canvas edge; Windows can otherwise crop the halo.
    alpha=image.getchannel('A')
    edge=ImageDraw.Draw(alpha);edge.rectangle((0,0,size-1,size-1),outline=0,width=1)
    image.putalpha(alpha)
    buffer=BytesIO();image.save(buffer,format='PNG')
    return buffer.getvalue()


def create_icon(path):
    """Write a multi-frame ICO including intermediate Windows display scales."""
    images=[raster(n) for n in ICON_SIZES]
    offset=6+16*len(images);entries=[]
    for size,png in zip(ICON_SIZES,images):
        dimension=0 if size==256 else size
        entries.append(struct.pack('<BBBBHHII',dimension,dimension,0,0,1,32,len(png),offset))
        offset+=len(png)
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(struct.pack('<HHH',0,1,len(images))+b''.join(entries)+b''.join(images))
    return target


if __name__=='__main__':
    import sys
    create_icon(sys.argv[1])
