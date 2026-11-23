"""Write image PDFs page by page, keeping only one decoded page in memory."""
import shutil
import zlib
from pathlib import Path
from PIL import Image, ImageOps
from app.core.exceptions import DownloadError


def write_pdf(paths, target):
    offsets = {0: 0}
    pages = []
    next_profile = 3 + 4 * len(paths)
    with Path(target).open('wb') as stream:
        stream.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')

        def start(number):
            offsets[number] = stream.tell()
            stream.write(f'{number} 0 obj\n'.encode())

        def obj(number, value):
            start(number)
            stream.write(value + b'\nendobj\n')

        for index, path in enumerate(paths):
            image_id = 3 + 4 * index
            length_id, content_id, page_id = image_id + 1, image_id + 2, image_id + 3
            pages.append(page_id)
            with Image.open(path) as source:
                if source.width * source.height > 40_000_000:
                    raise DownloadError('Dimensões da imagem excedem o limite seguro de 40 megapixels.')
                # EXIF rotation requires decoding; ordinary JPEGs retain their exact bytes.
                direct = source.format == 'JPEG' and source.mode in ('RGB', 'L', 'CMYK') and source.getexif().get(274, 1) == 1
                picture = source if source.getexif().get(274, 1) == 1 else ImageOps.exif_transpose(source)
                try:
                    if not direct:
                        picture.load()
                        if 'A' in picture.getbands() or 'transparency' in picture.info:
                            with picture.convert('RGBA') as rgba:
                                flat = Image.new('RGB', picture.size, 'white')
                                with rgba.getchannel('A') as alpha:
                                    flat.paste(rgba, mask=alpha)
                        elif picture.mode in ('RGB', 'L'):
                            flat = picture
                        else:
                            flat = picture.convert('L' if picture.mode in ('1', 'L') else 'RGB')
                    else:
                        flat = picture
                    try:
                        width, height = flat.size
                        color = {'L': 'DeviceGray', 'CMYK': 'DeviceCMYK'}.get(flat.mode, 'DeviceRGB')
                        color_space = f'/{color}'
                        profile = source.info.get('icc_profile', b'')
                        signature = {'L': b'GRAY', 'CMYK': b'CMYK'}.get(flat.mode, b'RGB ')
                        if isinstance(profile, bytes) and 128 <= len(profile) <= 4 * 1024**2 and profile[16:20] == signature:
                            compressed = zlib.compress(profile)
                            components = {'L': 1, 'CMYK': 4}.get(flat.mode, 3)
                            obj(next_profile, f'<< /N {components} /Filter /FlateDecode /Length {len(compressed)} >>\nstream\n'.encode() + compressed + b'\nendstream')
                            color_space = f'[/ICCBased {next_profile} 0 R]'
                            next_profile += 1
                        filter_name = 'DCTDecode' if direct else 'FlateDecode'
                        decode = ' /Decode [1 0 1 0 1 0 1 0]' if direct and flat.mode == 'CMYK' and 'adobe' in source.info else ''
                        start(image_id)
                        stream.write((f'<< /Type /XObject /Subtype /Image /Width {width} /Height {height}'
                                      f' /ColorSpace {color_space} /BitsPerComponent 8 /Filter /{filter_name}'
                                      f'{decode} /Length {length_id} 0 R >>\nstream\n').encode())
                        begin = stream.tell()
                        if direct:
                            with Path(path).open('rb') as original:
                                shutil.copyfileobj(original, stream, 1024 * 1024)
                        else:
                            compressor = zlib.compressobj()
                            for top in range(0, height, 64):
                                with flat.crop((0, top, width, min(top + 64, height))) as strip:
                                    stream.write(compressor.compress(strip.tobytes()))
                            stream.write(compressor.flush())
                        length = stream.tell() - begin
                        stream.write(b'\nendstream\nendobj\n')
                    finally:
                        if flat is not source and flat is not picture:
                            flat.close()
                finally:
                    if picture is not source:
                        picture.close()
            obj(length_id, str(length).encode())
            scale = min(.75, 14000 / max(width, height))
            w, h = width * scale, height * scale
            content = f'q\n{w:.6f} 0 0 {h:.6f} 0 0 cm\n/Im0 Do\nQ\n'.encode()
            obj(content_id, f'<< /Length {len(content)} >>\nstream\n'.encode() + content + b'endstream')
            obj(page_id, (f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.6f} {h:.6f}]'
                          f' /Resources << /XObject << /Im0 {image_id} 0 R >> >> /Contents {content_id} 0 R >>').encode())
        obj(2, f'<< /Type /Pages /Count {len(pages)} /Kids [{" ".join(f"{p} 0 R" for p in pages)}] >>'.encode())
        obj(1, b'<< /Type /Catalog /Pages 2 0 R >>')
        position = stream.tell()
        size = len(offsets)
        stream.write(f'xref\n0 {size}\n0000000000 65535 f \n'.encode())
        for number in range(1, size):
            stream.write(f'{offsets[number]:010d} 00000 n \n'.encode())
        stream.write(f'trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{position}\n%%EOF\n'.encode())
