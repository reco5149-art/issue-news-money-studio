"""Conservative photo finishing: no generated faces or reconstructed event details."""
import io
from PIL import Image,ImageOps,ImageEnhance,ImageFilter,ImageStat

def sharpness(data):
    with Image.open(io.BytesIO(data)) as im:
        im=ImageOps.grayscale(im);im.thumbnail((640,640))
        return ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).var[0]

def finish(data):
    with Image.open(io.BytesIO(data)) as image:
        im=ImageOps.exif_transpose(image).convert('RGB')
    original=im.size
    mean=ImageStat.Stat(ImageOps.grayscale(im)).mean[0]
    if mean<65:im=ImageEnhance.Brightness(im).enhance(1.05)
    elif mean>190:im=ImageEnhance.Brightness(im).enhance(.98)
    im=ImageEnhance.Contrast(im).enhance(1.035)
    im=ImageEnhance.Color(im).enhance(1.04)
    # 4K master for sufficiently detailed originals; never claim new optical detail.
    target=3840 if max(original)>=1920 else 2560
    scale=min(2.0,target/max(original))
    if scale!=1:im=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS)
    im=im.filter(ImageFilter.UnsharpMask(radius=1.0,percent=65,threshold=4))
    output=io.BytesIO();im.save(output,format='JPEG',quality=96,subsampling=0)
    return output.getvalue(),{'method':'natural-finish-v1','source_size':list(original),'output_size':list(im.size),
                              'upscaled':scale>1,'generative_reconstruction':False,'note':'원본 기반 보간 확대·약한 밝기/색감/선명도 보정. 실제 촬영 해상도 증가 아님.'}
