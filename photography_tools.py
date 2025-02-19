from utils import append_to_log, authorized_via_redis_token
import py3exiv2

def get_exif_metadata_from_image():
    try:
        if not authorized_via_redis_token(request, 'photography_tools'):
            return ('', 401)
        image_path = request.headers.get('imagePath')

        img = py3exiv2.Image(image_path)
        exif_data = img.read_exif()
        append_to_log('flask_logs', 'PHOTOGRAPHY', 'TRACE', 'Sent EXIF data for image at ' + image_path)
        return exif_data

    except Exception as e:
        append_to_log('flask_logs', 'PHOTOGRAPHY', 'ERROR', 'Exception thrown getting metadata from image. Error: ' + repr(e))
        return('', 500)
