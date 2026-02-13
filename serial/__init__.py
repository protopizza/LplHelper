import re
import subprocess

CREATE_NO_WINDOW = 0x08000000

def get_serial(path, system, chd_serial_path):
    if system == "Nintendo - GameCube":
        return __get_gc_serial(path)
    elif system == "Nintendo - Wii":
        return __get_wii_serial(path)

    elif system == "Sega - Dreamcast" or \
         system == "Sega - Mega-CD - Sega CD" or \
         system == "Sega - Saturn" or \
         system == "Sony - PlayStation 2" or \
         system == "Sony - PlayStation Portable" or \
         system == "Sony - PlayStation":
        return __get_chd_serial(chd_serial_path, path)

    raise Exception("No serial support for system " + system)


def __read_at_offset(path, offset, length):
    with open(path, 'rb') as f:
        f.seek(offset)
        data = f.read(length)
        if len(data) != length:
            raise Exception("Could not read enough data at requested offset: " + path)
        return data


def __get_disc_number(path):
    DISC_PATTERN = r"\(Disc (\d+)\)"
    m = re.search(DISC_PATTERN, path)
    if not m:
        return None
    return int(m.group(1))


def __get_disc_number_suffix(path):
    disc_number = __get_disc_number(path)
    if disc_number:
        return '-' + str(disc_number - 1)
    return ""


def __get_gc_serial(path):
    raw_serial = __read_at_offset(path, 0, 4)
    if raw_serial.startswith(b"RVZ") or raw_serial.startswith(b"WIA"):
        raw_serial = __read_at_offset(path, 0x0058, 4)

    prefixed = "DL-DOL-" + raw_serial.decode("utf-8")
    region_id = prefixed[10]

    serial = prefixed + __get_disc_number_suffix(path)

    if region_id == 'E':
        serial += "-USA"
    elif region_id == 'J':
        serial += "-JPN"
    elif region_id == 'P':
        serial += "-EUR"
    elif region_id == 'X':
        serial += "-EUR"
    elif region_id == 'Y':
        serial += "-FAH"
    elif region_id == 'D':
        serial += "-NOE"
    elif region_id == 'S':
        serial += "-ESP"
    elif region_id == 'F':
        serial += "-FRA"
    elif region_id == 'I':
        serial += "-ITA"
    elif region_id == 'H':
        serial += "-HOL"

    return serial


def __get_wii_serial(path):
    raw_serial = __read_at_offset(path, 0, 6)
    if raw_serial.startswith(b"WBFS"):
        raw_serial = __read_at_offset(path, 0x0200, 6)
    if raw_serial.startswith(b"RVZ") or raw_serial.startswith(b"WIA"):
        raw_serial = __read_at_offset(path, 0x0058, 6)

    serial = raw_serial.decode("utf-8") + __get_disc_number_suffix(path)
    return serial


def __get_chd_serial(chd_serial_path, chd_path, use_subprocess=True):
    if use_subprocess:
        try:
            result = subprocess.check_output([chd_serial_path, chd_path], universal_newlines=True, creationflags=CREATE_NO_WINDOW)
        except subprocess.CalledProcessError as e:
            print("[ERROR] Error occurred. Output was:")
            print(e.output)
            raise e

        return result.strip()
    else:
        raise Exception("Only chd_serial subprocess supported.")
