# LplHelper
Sublime Text plugin to help manage LPL files.

If you have a lot of LPLs with custom entries, this has convenient utilities for things such as sorting, calculating CRC/serial, downloading missing thumbnails, etc.

Getting the serial relies on [chd-serial](https://github.com/protopizza/chd_serial). Compile it and point your user settings to it.

Sample user package settings:
```
{
    "chd_serial_path": "<path>\\chd_serial.exe",
    "macos_rom_path": "<path>/ROM/",
    "macos_core_path": "<path>/RetroArch/cores/",
    "retroarch_rdb_path": "<path>\\Retroarch\\database\\rdb",
    "retroarch_local_thumbnails_path": "<path>\\thumbnails",
    "translation_label_mapping_file": "<path>\\TranslatedRomLabelMapping.json",
    "windows_rom_path": "<path>\\ROM\\",
    "windows_core_path": "<path>\\RetroArch\\cores\\"
}
```


Sample translated ROM label mapping JSON:
```
{
    "<system name>":
    {
        "<translated name>": "<original name>"
    }
}

```
