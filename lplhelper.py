import sublime
import sublime_plugin
import copy
import json
import os
import re
import urllib.error
import urllib.request
import zlib
from collections import OrderedDict
from urllib.parse import quote

from .lib import rdb
from .lib import serial

class LplBaseCommand:

    json_data = None
    errors = []
    warnings = []

    def get_full_region(self):
        return sublime.Region(0, self.view.size())

    def get_json_data(self):
        body = self.view.substr(self.get_full_region())
        self.json_data = json.loads(body, object_pairs_hook=OrderedDict)
        self.errors = []
        self.warnings = []

        if "items" not in self.json_data:
            msg = "No items found in file"
            self.show_status_message(msg)
            raise Exception(msg)
        print('=' * 10)
        print("Starting...")

    def update_data(self, edit):
        updated_data = json.dumps(self.json_data, indent=2, separators=(',', ': '))
        updated_data += '\n'

        self.view.replace(edit, self.get_full_region(), updated_data)

    def show_status_message(self, msg, print_to_console=True):
        if print_to_console:
            print(msg)
        sublime.status_message(msg)
        print('=' * 10)

    def show_errors(self, msg, no_error_msg=None):
        if self.errors:
            status = str(len(self.errors)) + " " + msg
            dialog = status + ":\n\n"
            dialog += "\n".join(self.errors)

            print(dialog)
            self.show_status_message(status, False)
            sublime.message_dialog(dialog)
        elif no_error_msg is not None:
            self.show_status_message(no_error_msg)

    def show_warnings(self):
        if self.warnings:
            print("Found warnings:\n")
            print('\n'.join(self.warnings))
            print('-' * 10)

    def get_current_playlist(self):
        current_file = os.path.basename(self.view.window().active_view().file_name())
        if os.path.splitext(current_file)[1] != ".lpl":
            raise Exception("Not currently viewing playlist file")
        return os.path.splitext(current_file)[0]


class LplSortCommand(LplBaseCommand, sublime_plugin.TextCommand):

    def sorter(self, value):
        return value["label"].lower()

    def run(self, edit):
        self.get_json_data()

        self.json_data["items"].sort(key=self.sorter)

        self.update_data(edit)
        self.show_status_message("Done sorting!")


class LplMissingEntriesBaseCommand(LplBaseCommand):

    missing_items = []

    def init_exclusions(self):
        settings = sublime.load_settings("LplHelper.sublime-settings")
        self.name_exclusions = settings.get("name_exclusions", [])
        self.extension_exclusions = settings.get("extension_exclusions", [])

    def find_missing(self):
        folders = set()
        existing_items = set()
        for item in self.json_data["items"]:
            folders.add(os.path.dirname(item["path"]))
            existing_items.add(item["path"])

        found_items = set()

        for folder in folders:
            current_folder = set([os.path.join(folder, f) for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))
                and f not in self.name_exclusions
                and os.path.splitext(f)[1] not in self.extension_exclusions])

            included_in_m3u = []
            for item in current_folder:
                if os.path.splitext(item)[1] != ".m3u":
                    continue
                with open(item) as file:
                    for line in file:
                        included_in_m3u.append(os.path.join(folder, line.rstrip()))

            for item in included_in_m3u:
                current_folder.remove(item)

            found_items.update(current_folder)

        self.missing_items = found_items - existing_items

    def add_missing(self):
        if not self.json_data["items"]:
            raise Exception("Need at least one existing item to be a template")
        template = copy.deepcopy(self.json_data["items"][0])
        template['crc32'] = "DETECT"

        for missing in self.missing_items:
            new_entry = copy.deepcopy(template)
            new_entry["path"] = missing
            new_entry["label"] = os.path.splitext(os.path.basename(missing))[0]
            self.json_data["items"].insert(0, new_entry)
            self.errors.append("Entry added for \'" + missing + "\'")


class LplFindMissingEntriesCommand(LplMissingEntriesBaseCommand, sublime_plugin.TextCommand):

    def run(self, edit):
        self.init_exclusions()
        self.get_json_data()
        self.find_missing()
        self.errors = self.missing_items
        self.show_errors("missing item(s) found", "No missing items found.")


class LplAddMissingEntriesCommand(LplMissingEntriesBaseCommand, sublime_plugin.TextCommand):

    def run(self, edit):
        self.init_exclusions()
        self.get_json_data()
        self.find_missing()
        if self.missing_items:
            self.add_missing()
            self.update_data(edit)
        self.show_errors("missing item(s) added", "No missing items to be added.")


class LplValidatePathsCommand(LplBaseCommand, sublime_plugin.TextCommand):

    def run(self, edit):
        self.get_json_data()

        for item in self.json_data["items"]:
            if not os.path.isfile(item["path"]):
                self.errors += [item["path"]]
            if os.path.splitext(os.path.basename(item["path"]))[0] != item["label"]:
                self.warnings.append("[LABEL] " + item["label"] + " is inconsistent with [PATH] " + os.path.splitext(os.path.basename(item["path"]))[0])

        self.show_warnings()
        self.show_errors("invalid path(s) found", "All paths valid.")


class LplCrcBaseCommand(LplBaseCommand):

    @staticmethod
    def crc32(path, offset=0):
        crc = 0

        with open(path, 'rb', 65536) as f:
            f.seek(offset)
            for x in range(int((os.stat(path).st_size / 65536)) + 1):
                crc = zlib.crc32(f.read(65536), crc)
        return '%08X' % (crc & 0xFFFFFFFF)

    def get_serial(self, path):
        settings = sublime.load_settings("LplHelper.sublime-settings")
        chd_serial_path = settings.get("chd_serial_path", "")
        return serial.get_serial(path, self.get_current_playlist(), chd_serial_path)

    def compare_crcs(self, existing_crc, file_crc, rom_crc, extension, label):
        if extension == ".nes":
            if existing_crc == file_crc:
                self.warnings.append("[COMPARE .nes] " + label + ": existing CRC (" + existing_crc + ") matches with FILE CRC (" + file_crc + ") instead of ROM CRC (" + rom_crc + ")")
                return False
            if existing_crc == rom_crc:
                return True
            return False

        return existing_crc == file_crc

    def check_for_ines_header(self, path):
        with open(path, 'rb') as f:
            header_tag = f.read(4)
            return header_tag[0] == 0x4e and header_tag[1] == 0x45 and header_tag[2] == 0x53 and header_tag[3] == 0x1a

    def validate_crcs(self, update_crcs=False):
        modified = False

        for item in self.json_data["items"]:
            extension = os.path.splitext(item["path"])[1]

            if extension == ".m3u":
                if item["crc32"] != "DETECT":
                    self.warnings.append("[.M3U] " + item["label"] + " doesn't have DETECT")
                continue

            if update_crcs == False and item["crc32"] == "DETECT":
                self.warnings.append("[CRC] " + item["label"] + " has no CRC")
                continue

            if not item["crc32"] == "DETECT" and (not item["crc32"].endswith("|crc") and not item["crc32"].endswith("|serial")):
                raise Exception("crc32 field for " + item["label"] + " is invalid")

            existing_crc = item["crc32"].split("|")[0]
            if not item["crc32"] == "DETECT":
                existing_crc_type = item["crc32"].split("|")[1]
            else:
                existing_crc_type = None

            # Handle CHD / RVZ (uses serial)
            if extension == ".chd" or extension == ".rvz":
                # These are not currently supported
                if self.get_current_playlist() == "NEC - PC-FX" or self.get_current_playlist() == "NEC - PC Engine CD - TurboGrafx-CD":
                    continue

                try:
                    serial = self.get_serial(item["path"])
                except Exception as e:
                    self.warnings.append("[SKIPPING] " + item["label"] + " could not get serial due to: " + str(e))
                    continue

                if existing_crc_type != "serial" or serial != existing_crc:
                    if existing_crc_type and existing_crc_type != "serial":
                        self.warnings.append(item["label"] + ": should have suffix \'|serial\'")

                    if update_crcs == False:
                        self.errors.append(item["label"] + ": " + existing_crc + " vs " + serial + " (existing vs calculated)")
                    else:
                        modified = True
                        item["crc32"] = serial + "|serial"
                        self.errors.append(item["label"] + ": CRC updated from " + existing_crc + " to " + item["crc32"][:-7])
                continue

            # Handle everything else with regular CRC
            file_crc = None
            rom_crc = None
            use_rom_crc = False

            # check if NES and get alternate crc32 without header
            if extension == ".nes":
                if self.check_for_ines_header(item["path"]):
                    use_rom_crc = True
                    rom_crc = LplCrcBaseCommand.crc32(item["path"], 0x10)
                else:
                    self.warnings.append("[HEADER] " + item["label"] + " has no header")
                    file_crc = LplCrcBaseCommand.crc32(item["path"])
            else:
                file_crc = LplCrcBaseCommand.crc32(item["path"])

            if existing_crc_type != "crc" or not self.compare_crcs(existing_crc, file_crc, rom_crc, extension, item["label"]):
                if use_rom_crc:
                    file_crc = rom_crc

                if existing_crc_type and existing_crc_type != "crc":
                    self.warnings.append(item["label"] + ": should have suffix \'|crc\'")

                if update_crcs == False:
                    self.errors.append(item["label"] + ": " + existing_crc + " vs " + file_crc + " (existing vs calculated)")
                else:
                    modified = True
                    item["crc32"] = file_crc + "|crc"
                    self.errors.append(item["label"] + ": CRC updated from " + existing_crc + " to " + item["crc32"][:-4])

        return modified


class LplValidateCrcCommand(LplCrcBaseCommand, sublime_plugin.TextCommand):

    def run(self, edit):
        self.get_json_data()
        self.validate_crcs(update_crcs=False)
        self.show_warnings()
        self.show_errors("non-matching CRC(s) found", "All CRCs match.")


class LplUpdateCrcCommand(LplCrcBaseCommand, sublime_plugin.TextCommand):

    def run(self, edit):
        self.get_json_data()
        if self.validate_crcs(update_crcs=True):
            self.update_data(edit)
        self.show_warnings()
        self.show_errors("CRC(s) updated", "No changes to be made.")


class LplDatabaseCheckCrcCommand(LplCrcBaseCommand, sublime_plugin.TextCommand):

    def run(self, edit):
        settings = sublime.load_settings("LplHelper.sublime-settings")
        retroarch_rdb_path = settings.get("retroarch_rdb_path", "")

        if not retroarch_rdb_path:
            return

        self.get_json_data()
        current_playlist = self.get_current_playlist()

        extensions = set()
        for item in self.json_data["items"]:
            if item["crc32"] == "DETECT":
                continue
            extensions.add(os.path.splitext(item["path"])[1])

        rdbs = rdb.load_rdbs(retroarch_rdb_path, extensions)
        for item in self.json_data["items"]:
            if item["crc32"] == "DETECT":
                continue
            name = item["label"]
            crc = item["crc32"].split('|')[0]
            result = rdb.find_game_in_rdbs(rdbs, name, crc, current_playlist)
            if result[0] != rdb.SearchResult.FOUND:
                if result[0] == rdb.SearchResult.CRC_MATCH_ONLY:
                    self.warnings.append("CRC MATCH ONLY: "+ name + " with CRC " + crc + " didn't match name found in database (" + result[1] + ").")
                elif result[0] == rdb.SearchResult.NAME_MATCH_ONLY:
                    self.errors.append("NAME MATCH ONLY: " + name + " with CRC " + crc + " didn't match CRC found in database (" + result[1] + ").")
                elif "(English)" in name:
                    self.warnings.append("PATCH: " + name + " with CRC " + crc + " not found in database (English patch).")
                else:
                    self.warnings.append("MISSING: " + name + " with CRC " + crc + " not found in database.")

        self.show_warnings()
        self.show_errors("non-matching CRC(s) found", "All CRCs match with database.")


class LplThumbnailsBaseCommand(LplBaseCommand):
    BOXARTS = "Named_Boxarts"
    SNAPS = "Named_Snaps"
    TITLES = "Named_Titles"
    LOGOS = "Named_Logos"

    MAX_TYPE_WIDTH = max(len(BOXARTS), len(SNAPS), len(TITLES), len(LOGOS))

    SANITIZE_REGEX = "[&\*/:`<>?\\\|\"]"

    FAN_TRANSLATION_SIGNIFIER = " (English)"

    @staticmethod
    def sanitize_label(label):
        return re.sub(LplThumbnailsBaseCommand.SANITIZE_REGEX, '_', label)

    @staticmethod
    def get_local_thumbnail_file(path, name):
        return os.path.join(path, LplThumbnailsBaseCommand.sanitize_label(name) + ".png")

    @staticmethod
    def open_remote_file(url):
        data = None
        with urllib.request.urlopen(url) as response:
            data = response.read()
        return data

    @staticmethod
    def compare_local_remote_files(local_file, remote_file):
        if len(local_file) != len(remote_file):
            return False
        return local_file == remote_file

    @staticmethod
    def save_thumbnail(remote_thumbnail, local_thumbnail_path):
        with open(local_thumbnail_path, 'wb') as f:
            f.write(remote_thumbnail)

    def get_remote_thumbnail_file(self, type, label):
        sanitized_label = LplThumbnailsBaseCommand.sanitize_label(label)
        return self.retroarch_remote_thumbnails_path + "/" + quote(self.current_playlist) + "/" + type + "/" + quote(sanitized_label) + ".png"

    def init_thumbnail_command(self, use_logos=True):
        settings = sublime.load_settings("LplHelper.sublime-settings")
        self.retroarch_local_thumbnails_path = settings.get("retroarch_local_thumbnails_path", "")
        self.retroarch_remote_thumbnails_path = settings.get("retroarch_remote_thumbnails_path", "")
        self.translation_label_mapping_file = settings.get("translation_label_mapping_file", "")
        self.current_playlist = self.get_current_playlist()
        if use_logos:
            self.thumbnail_types = [LplThumbnailsBaseCommand.BOXARTS, LplThumbnailsBaseCommand.SNAPS, LplThumbnailsBaseCommand.TITLES, LplThumbnailsBaseCommand.LOGOS]
        else:
            self.thumbnail_types = [LplThumbnailsBaseCommand.BOXARTS, LplThumbnailsBaseCommand.SNAPS, LplThumbnailsBaseCommand.TITLES]

    def get_local_thumbnail_dir(self, type):
        return os.path.join(self.retroarch_local_thumbnails_path, self.current_playlist, type)

    def get_mapped_label(self, original_label):
        if not self.translation_label_mapping_file:
            return None
        with open(self.translation_label_mapping_file) as data:
            translation_mapping = json.load(data)
        if self.current_playlist not in translation_mapping:
            return None
        if original_label not in translation_mapping[self.current_playlist]:
            return None
        return translation_mapping[self.current_playlist][original_label]

    def validate_thumbnails(self, update_thumbnails=False, add_missing_only=False):
        for item in self.json_data["items"]:
            label = item["label"]

            for thumbnail_type in self.thumbnail_types:

                # Check local thumbnail
                local_thumbnail_path = LplThumbnailsBaseCommand.get_local_thumbnail_file(self.get_local_thumbnail_dir(thumbnail_type), label)
                if os.path.isfile(local_thumbnail_path):
                    if add_missing_only:
                        continue
                    local_exists = True
                else:
                    local_exists = False

                # Get URL for remote thumbnail
                mapped_label = self.get_mapped_label(label)
                if mapped_label:
                    print("Using mapped label \'" + mapped_label + "\' for \'" + label + "\'")
                    remote_thumbnail_path = self.get_remote_thumbnail_file(thumbnail_type, mapped_label)
                elif LplThumbnailsBaseCommand.FAN_TRANSLATION_SIGNIFIER in label:
                    print("Using label without (English) suffix for \'" + label + "\'")
                    remote_thumbnail_path = self.get_remote_thumbnail_file(thumbnail_type, label.replace(LplThumbnailsBaseCommand.FAN_TRANSLATION_SIGNIFIER, ''))
                else:
                    remote_thumbnail_path = self.get_remote_thumbnail_file(thumbnail_type, label)

                # Open the remote thumbnail to check if it exists
                try:
                    remote_thumbnail = LplThumbnailsBaseCommand.open_remote_file(remote_thumbnail_path)
                except urllib.error.HTTPError as e:
                    if local_exists:
                        if e.code != 404:
                            print("Error found while trying to get remote thumbnail " + remote_thumbnail_path)
                            raise e
                        if not update_thumbnails:
                            if LplThumbnailsBaseCommand.FAN_TRANSLATION_SIGNIFIER in label:
                                self.warnings.append("[FANXLATE] [" + thumbnail_type.ljust(LplThumbnailsBaseCommand.MAX_TYPE_WIDTH) + "] \'" + label + "\' doesn't exist, but may have a different original label (FAN TRANSLATION).")
                            else:
                                self.warnings.append("[REMOTE  ] [" + thumbnail_type.ljust(LplThumbnailsBaseCommand.MAX_TYPE_WIDTH) + "] \'" + label + "\' doesn't exist.")
                    else:
                        self.warnings.append("[NOTEXIST] [" + thumbnail_type.ljust(LplThumbnailsBaseCommand.MAX_TYPE_WIDTH) + "] \'" + label + "\' thumbnails don't exist for local or remote.")
                    continue

                # Download remote to local
                if not local_exists:
                    if update_thumbnails:
                        LplThumbnailsBaseCommand.save_thumbnail(remote_thumbnail, local_thumbnail_path)
                        self.errors.append("[" + thumbnail_type.ljust(LplThumbnailsBaseCommand.MAX_TYPE_WIDTH) + "] \'" + label + "\' downloaded to " + local_thumbnail_path)
                    else:
                        self.errors.append("[LOCAL   ] [" + thumbnail_type.ljust(LplThumbnailsBaseCommand.MAX_TYPE_WIDTH) + "] \'" + label + "\' doesn't exist.")
                    continue

                # Do comparison
                local_thumbnail = None
                with open(local_thumbnail_path, 'rb') as file:
                    local_thumbnail = file.read()

                if not LplThumbnailsBaseCommand.compare_local_remote_files(local_thumbnail, remote_thumbnail):
                    if update_thumbnails:
                        LplThumbnailsBaseCommand.save_thumbnail(remote_thumbnail, local_thumbnail_path)
                        self.errors.append("[" + thumbnail_type.ljust(LplThumbnailsBaseCommand.MAX_TYPE_WIDTH) + "] \'" + label + "\' updated to " + local_thumbnail_path)
                    else:
                        self.errors.append("[MISMATCH] [" + thumbnail_type.ljust(LplThumbnailsBaseCommand.MAX_TYPE_WIDTH) + "] \'" + label + "\'  thumbnails don't match.")


class LplCountThumbnailsCommand(LplThumbnailsBaseCommand, sublime_plugin.TextCommand):

    def check_folder(self, thumbnail_type, expected_count):
        folder = self.get_local_thumbnail_dir(thumbnail_type)
        if not os.path.isdir(folder):
            self.warnings.append(folder + " doesn't exist.")
        else:
            found_count = len(os.listdir(folder))
            if expected_count != found_count:
                self.warnings.append("Expected count: " + str(expected_count) + ", " + thumbnail_type + " count: " + str(found_count))

    def run(self, edit):
        self.init_thumbnail_command()
        self.get_json_data()

        for item in self.json_data["items"]:
            label = item["label"]

            for thumbnail_type in self.thumbnail_types:
                folder_path = self.get_local_thumbnail_dir(thumbnail_type)
                if not os.path.isdir(folder_path):
                    # Should be caught by later folder validation
                    continue
                expected_path = LplThumbnailsBaseCommand.get_local_thumbnail_file(folder_path, label)
                if not os.path.isfile(expected_path):
                    self.warnings.append(expected_path + " doesn't exist.")

        expected_count = len(self.json_data["items"])

        for thumbnail_type in self.thumbnail_types:
            self.check_folder(thumbnail_type, expected_count)

        self.show_warnings()
        self.show_status_message(str(len(self.warnings)) + " warnings found.")


class LplValidateThumbnailsCommand(LplThumbnailsBaseCommand,  sublime_plugin.TextCommand):

     def run(self, edit):
        self.init_thumbnail_command()
        self.get_json_data()
        self.validate_thumbnails(update_thumbnails=False)
        self.show_warnings()
        self.show_errors("non-matching thumbnail(s) found", "All thumbnails match.")


class LplUpdateThumbnailsCommand(LplThumbnailsBaseCommand,  sublime_plugin.TextCommand):

     def run(self, edit):
        self.init_thumbnail_command()
        self.get_json_data()
        self.validate_thumbnails(update_thumbnails=True)
        self.show_warnings()
        self.show_errors("thumbnail(s) updated", "No changes to be made.")


class LplAddMissingThumbnailsCommand(LplThumbnailsBaseCommand,  sublime_plugin.TextCommand):

     def run(self, edit):
        self.init_thumbnail_command()
        self.get_json_data()
        self.validate_thumbnails(update_thumbnails=True, add_missing_only=True)
        self.show_warnings()
        self.show_errors("thumbnail(s) updated", "No changes to be made.")


class LplConvertPathsBaseCommand(LplBaseCommand):
    path_separator = "!"
    core_extension = ".?"
    rom_path = ""
    core_path = ""

    def convert_paths(self):
        if not self.rom_path:
            raise Exception("rom_path is not specified")

        if not self.core_path:
            raise Exception("core_path is not specified")

        if not self.rom_path.endswith(self.path_separator):
            self.rom_path += self.path_separator

        if not self.core_path.endswith(self.path_separator):
            self.core_path += self.path_separator

        self.json_data['default_core_path'] = self.convert_core_path(self.json_data['default_core_path'])

        for item in self.json_data["items"]:
            item['path'] = self.convert_rom_path(item['path'])
            item['core_path'] = self.convert_core_path(item['core_path'])


    def convert_rom_path(self, path):
        filename = os.path.split(path)[1]
        rom_folder_name = os.path.split(os.path.split(path)[0])[1]
        return self.rom_path + rom_folder_name + self.path_separator + filename

    def convert_core_path(self, path):
        basename = os.path.splitext(os.path.basename(path))[0]
        return self.core_path + basename + self.core_extension


class LplConvertPathsForWindowsCommand(LplConvertPathsBaseCommand,  sublime_plugin.TextCommand):
    path_separator = "\\"
    core_extension = ".dll"

    def run(self, edit):
        settings = sublime.load_settings("LplHelper.sublime-settings")
        self.rom_path = settings.get("windows_rom_path", "")
        self.core_path = settings.get("windows_core_path", "")

        self.get_json_data()
        self.convert_paths()
        self.update_data(edit)
        self.show_status_message("Done converting for Windows!")


class LplConvertPathsForMacosCommand(LplConvertPathsBaseCommand,  sublime_plugin.TextCommand):
    path_separator = "/"
    core_extension = ".dylib"

    def run(self, edit):
        settings = sublime.load_settings("LplHelper.sublime-settings")
        self.rom_path = settings.get("macos_rom_path", "")
        self.core_path = settings.get("macos_core_path", "")

        self.get_json_data()
        self.convert_paths()
        self.update_data(edit)
        self.show_status_message("Done converting for MacOS!")
