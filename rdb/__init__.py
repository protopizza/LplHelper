import binascii
import math
import os
import sys

def __get_rdb_files(extension):
    if extension == ".zip":
        return [
                "FBNeo - Arcade Games.rdb",
                "Sega - Naomi.rdb"
                ]
    if extension == ".fds":
        return ["Nintendo - Family Computer Disk System.rdb"]
    if extension == ".gba":
        return ["Nintendo - Game Boy Advance.rdb"]
    if extension == ".gbc":
        return ["Nintendo - Game Boy Color.rdb"]
    if extension == ".gb":
        return ["Nintendo - Game Boy.rdb"]
    if extension == ".rvz":
        return [
                "Nintendo - GameCube.rdb",
                "Nintendo - Wii.rdb"
                ]
    if extension == ".z64":
        return ["Nintendo - Nintendo 64.rdb"]
    if extension == ".nds":
        return ["Nintendo - Nintendo DS.rdb"]
    if extension == ".nes":
        return ["Nintendo - Nintendo Entertainment System.rdb"]
    if extension == ".bs":
        return ["Nintendo - Satellaview.rdb"]
    if extension == ".sfc":
        return ["Nintendo - Super Nintendo Entertainment System.rdb"]
    if extension == ".vb":
        return ["Nintendo - Virtual Boy.rdb"]
    if extension == ".sms":
        return ["Sega - Master System - Mark III.rdb"]
    if extension == ".md":
        return ["Sega - Mega Drive - Genesis.rdb"]
    if extension == ".ngc":
        return ["SNK - Neo Geo Pocket Color.rdb"]
    if extension == ".pce":
        return ["NEC - PC Engine - TurboGrafx 16.rdb"]
    elif extension == ".chd":
        return [
                "Sony - PlayStation.rdb",
                "Sony - PlayStation 2.rdb",
                "Sony - PlayStation Portable.rdb",
                "Sega - Dreamcast.rdb",
                "Sega - Saturn.rdb",
                "Sega - Mega-CD - Sega CD.rdb",
                "NEC - PC-FX.rdb",
                "NEC - PC Engine CD - TurboGrafx-CD.rdb",
                "Philips - CD-i.rdb"
                ]
    raise Exception("No database for extension type " + extension)


class SearchResult:
    FOUND = 1
    CRC_MATCH_ONLY = 2
    NAME_MATCH_ONLY = 3
    NOT_FOUND = 4


def bytes_to_hex(o):
    return binascii.hexlify(o).decode("ascii")


class Game:
    name = ""
    rom_name = ""
    size = 0
    crc32 = 0
    serial = ""

    def __str__(self):
        return "name: " + self.name + \
            "; rom_name: " + self.rom_name + \
            "; size: " + str(self.size) + \
            "; crc32: " + str(self.crc32) + \
            "; serial: " + str(self.serial)


    def set_field(self, field, value):
        if field == "name":
            self.name = value.decode()
        elif field == "rom_name":
            self.rom_name = value.decode()
        elif field == "size":
            self.size = int(bytes_to_hex(value), 16)
        elif field == "crc":
            self.crc32 = str(bytes_to_hex(value)).upper()
        elif field == "serial":
            self.serial = value.decode()


class ReadResultType:
    MAP = 1
    ARRAY = 2
    STRING = 3
    BIN = 4
    BOOLEAN = 5
    SIGNED = 6
    UNSIGNED = 7
    NIL = 8


class ReadResult:
    type = None
    index = None
    value = []
    array_value = None
    map_value = None

    def add_to_array(self, item):
        self.array_value.append(item)

    def put_in_map(self, key, value):
        self.map_value[key] = value

    def decode(self):
        if self.type == ReadResultType.MAP:
            raise Exception("Decode unsupported for map")
        elif self.type == ReadResultType.ARRAY:
            raise Exception("Decode unsupported for array")

        return self.value.decode()


class RdbReader:

    FIELD_TYPES = {
        "fix_map": 0x80,
        "map_16": 0xde,
        "map_32": 0xdf,
        "fix_array": 0x90,
        "array_16": 0xdc,
        "array_32": 0xdd,
        "fix_str": 0xa0,
        "str_8": 0xd9,
        "str_16": 0xda,
        "str_32": 0xdb,
        "bin_8": 0xc4,
        "bin_16": 0xc5,
        "bin_32": 0xc6,
        "false": 0xc2,
        "true": 0xc3,
        "int_8": 0xd0,
        "int_16": 0xd1,
        "int_32": 0xd2,
        "int_64": 0xd3,
        "uint_8": 0xcc,
        "uint_16": 0xcd,
        "uint_32": 0xce,
        "uint_64": 0xcf,
        "nil": 0xc0
    }

    MAGIC_NUMBER = "5241524348444200" # "RARCHDB"

    def __init__(self):
        self.rdb_data = None
        self.offset = 0
        self.objects = []

    def get_length_by_size(self, size):
        result = int(bytes_to_hex(self.rdb_data[self.offset : self.offset + size]), 16)
        self.offset += size
        return result

    def read_field_with_length(self, result, length):
        result.value = self.rdb_data[self.offset : self.offset + length]
        self.offset += length
        return result

    def read_array(self, result, length):
        result.type = ReadResultType.ARRAY
        result.array_value = []
        result.index = len(self.objects)
        self.objects.append(result)
        for i in range(0, length):
            result.add_to_array(self.read_at_current_offset())
        return result

    def read_map(self, result, length):
        result.type = ReadResultType.MAP
        result.map_value = {}
        result.index = len(self.objects)
        self.objects.append(result)
        for i in range(0, length):
            key = self.read_at_current_offset()
            if key.type != ReadResultType.STRING:
                raise Exception("RDB key must be a string")
            value = self.read_at_current_offset()
            result.put_in_map(key.decode(), value)
        return result

    def read_at_current_offset(self):
        result = ReadResult()
        field_type = self.rdb_data[self.offset]

        self.offset += 1

        if field_type == RdbReader.FIELD_TYPES["nil"]:
            result.type = ReadResultType.NIL
            return result

        elif field_type == RdbReader.FIELD_TYPES["false"]:
            result.type = ReadResultType.BOOLEAN
            result.bool_value = False
            return result

        elif field_type == RdbReader.FIELD_TYPES["true"]:
            result.type = ReadResultType.BOOLEAN
            result.bool_value = True
            return result

        elif field_type == RdbReader.FIELD_TYPES["str_8"]:
            result.type = ReadResultType.STRING
            return self.read_field_with_length(result, self.get_length_by_size(1))
        elif field_type == RdbReader.FIELD_TYPES["str_16"]:
            result.type = ReadResultType.STRING
            return self.read_field_with_length(result, self.get_length_by_size(2))
        elif field_type == RdbReader.FIELD_TYPES["str_32"]:
            result.type = ReadResultType.STRING
            return self.read_field_with_length(result, self.get_length_by_size(4))

        elif field_type == RdbReader.FIELD_TYPES["bin_8"]:
            result.type = ReadResultType.BIN
            return self.read_field_with_length(result, self.get_length_by_size(1))
        elif field_type == RdbReader.FIELD_TYPES["bin_16"]:
            result.type = ReadResultType.BIN
            return self.read_field_with_length(result, self.get_length_by_size(2))
        elif field_type == RdbReader.FIELD_TYPES["bin_32"]:
            result.type = ReadResultType.BIN
            return self.read_field_with_length(result, self.get_length_by_size(4))

        elif field_type == RdbReader.FIELD_TYPES["uint_8"]:
            result.type = ReadResultType.UNSIGNED
            return self.read_field_with_length(result, 1)
        elif field_type == RdbReader.FIELD_TYPES["uint_16"]:
            result.type = ReadResultType.UNSIGNED
            return self.read_field_with_length(result, 2)
        elif field_type == RdbReader.FIELD_TYPES["uint_32"]:
            result.type = ReadResultType.UNSIGNED
            return self.read_field_with_length(result, 4)
        elif field_type == RdbReader.FIELD_TYPES["uint_64"]:
            result.type = ReadResultType.UNSIGNED
            return self.read_field_with_length(result, 8)

        elif field_type == RdbReader.FIELD_TYPES["int_8"]:
            result.type = ReadResultType.SIGNED
            return self.read_field_with_length(result, 1)
        elif field_type == RdbReader.FIELD_TYPES["int_16"]:
            result.type = ReadResultType.SIGNED
            return self.read_field_with_length(result, 2)
        elif field_type == RdbReader.FIELD_TYPES["int_32"]:
            result.type = ReadResultType.SIGNED
            return self.read_field_with_length(result, 4)
        elif field_type == RdbReader.FIELD_TYPES["int_64"]:
            result.type = ReadResultType.SIGNED
            return self.read_field_with_length(result, 8)

        elif field_type == RdbReader.FIELD_TYPES["array_16"]:
            return self.read_array(result, self.get_length_by_size(2))
        elif field_type == RdbReader.FIELD_TYPES["array_32"]:
            return self.read_array(result, self.get_length_by_size(4))

        elif field_type == RdbReader.FIELD_TYPES["map_16"]:
            return self.read_map(result, self.get_length_by_size(2))
        elif field_type == RdbReader.FIELD_TYPES["map_32"]:
            return self.read_map(result, self.get_length_by_size(4))

        ###
        if field_type < RdbReader.FIELD_TYPES["fix_map"]:
            # print("A")
            result.type = ReadResultType.SIGNED
            result.value = [field_type]

        elif field_type < RdbReader.FIELD_TYPES["fix_array"]:
            # print("B")
            length = field_type - RdbReader.FIELD_TYPES["fix_map"]
            return self.read_map(result, length)

        elif field_type < RdbReader.FIELD_TYPES["fix_str"]:
            # print("C")
            length = field_type - RdbReader.FIELD_TYPES["fix_array"]
            return self.read_array(result, length)

        elif field_type < RdbReader.FIELD_TYPES["nil"]:
            # print("D")
            result.type = ReadResultType.STRING
            length = field_type - RdbReader.FIELD_TYPES["fix_str"]
            return self.read_field_with_length(result, length)

        elif field_type > RdbReader.FIELD_TYPES["map_32"]:
            # print("E")
            result.type = ReadResultType.SIGNED
            result.value = [field_type - 0xff - 1]

        return result

    '''
    Returns list of games round in the specified RDB.
    '''
    def read(self, path):
        print("Reading " + path + "...")
        with open(path, 'rb') as f:
            self.rdb_data = f.read()

        results = []

        if bytes_to_hex(self.rdb_data[0:8]) != RdbReader.MAGIC_NUMBER:
            raise Exception("Not valid RDB format.")

        self.offset = int.from_bytes(self.rdb_data[8:16], byteorder='big')
        count = sys.maxsize
        if self.offset != 0:
            metadata_result = self.read_at_current_offset()
            if metadata_result.type != ReadResultType.MAP:
                raise Exception("Error finding metadata")
            count = int.from_bytes(metadata_result.map_value["count"].value, byteorder='big')

        self.offset = 0x10

        i = 0
        while i < count and self.offset != len(self.rdb_data):
            i += 1
            current = self.read_at_current_offset()
            if current.type != ReadResultType.MAP:
                continue
            current_map = self.objects[current.index].map_value
            if self.offset == len(self.rdb_data)and len(current_map) == 1 and "count" in current_map:
                continue
            game = Game()
            for key, value in current_map.items():
                game.set_field(key, value.value)
            results.append(game)

        if count != len(results):
            print("Actual count (" + str(len(results)) + ") differs from expected count (" + str(count) + ")")
        else:
            print("RDB entry count: " + str(len(results)))

        return results


def __find_game(games, name, crc32):
    result = (SearchResult.NOT_FOUND, 0)

    for game in games:
        if crc32 == game.crc32 or (game.serial and crc32 == game.serial):
            if name == game.name:
                return (SearchResult.FOUND, 1)
            else:
                result = (SearchResult.CRC_MATCH_ONLY, game.name)
        elif name == game.name:
            if result[0] != SearchResult.CRC_MATCH_ONLY:
                result = (SearchResult.NAME_MATCH_ONLY, game.crc32)

    return result


def __least_severe_result(result1, result2):
    return result1 if result1 <= result2 else result2


def load_rdbs(rdb_dir, extensions):
    result = {}
    for extension in extensions:
        rdb_files = __get_rdb_files(extension)
        for rdb_file in rdb_files:
            key = rdb_file[:-4]
            if key not in result:
                path = os.path.join(rdb_dir, rdb_file)
                reader = RdbReader()
                result[key] = reader.read(path)
    return result

'''
    Returns tuple of SearchResult and:
        - 0 if not found
        - 1 if found in database with exact name match
        - name if found but specified name doesn't match
'''
def find_game_in_rdbs(rdbs, name, crc32, preferred_system=None):
    result = (SearchResult.NOT_FOUND, 0)
    if preferred_system and preferred_system in rdbs:
        result = __least_severe_result(result, __find_game(rdbs[preferred_system], name, crc32))
        if result[0] == SearchResult.FOUND:
            return result

    for key in rdbs:
        if key == preferred_system:
            continue
        result = __least_severe_result(result, __find_game(rdbs[key], name, crc32))
        if result[0] == SearchResult.FOUND:
            break

    return result
