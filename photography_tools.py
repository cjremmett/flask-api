from utils import append_to_log, authorized_via_redis_token
from PIL import Image, ExifTags
from flask import request

def get_exif_metadata_from_image():
    try:
        if not authorized_via_redis_token(request, 'photography_tools'):
            return ('', 401)
        image_path = request.headers.get('imagePath')

        img = Image.open(image_path)
        img_exif = img.getexif()
        # print(type(img_exif))
        # <class 'PIL.Image.Exif'>
        exif_dict = {}
        append_to_log('flask_logs', 'PHOTOGRAPHY', 'TRACE', type(img))
        append_to_log('flask_logs', 'PHOTOGRAPHY', 'TRACE', type(img_exif))
        if img_exif is None:
            append_to_log('flask_logs', 'PHOTOGRAPHY', 'TRACE', 'Sorry, image has no exif data.')
        else:
            for key, val in img_exif.items():
                append_to_log('flask_logs', 'PHOTOGRAPHY', 'TRACE', str(key) + ' ' + str(val))
                if key in ExifTags.TAGS:
                    exif_dict[ExifTags.TAGS[key]] = val
                else:
                    exif_dict[key] = val

        append_to_log('flask_logs', 'PHOTOGRAPHY', 'TRACE', 'Sent EXIF data for image at ' + image_path)
        append_to_log('flask_logs', 'PHOTOGRAPHY', 'TRACE', str(exif_dict))
        return exif_dict

    except Exception as e:
        append_to_log('flask_logs', 'PHOTOGRAPHY', 'ERROR', 'Exception thrown getting metadata from image. Error: ' + repr(e))
        return('', 500)
