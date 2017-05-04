# scmap_mirror_tool

Overview
========
[mirror_map.py](mirror_map.py) does following with a Supreme Commander map file and it's corresponding `_save.lua` 

  * Mirrors every embedded image (e.g. preview, height map, stratas, normal maps, ...)
  * Mirrors decals including albedo and normal files 
  * Mirrors props and rotate them to look somewhat more "mirrored"
  * Mirrors markers and units

Mirror refers to mirror from center along x axis or y axis or mirror along one of both diagonals. 
The script uses lupa to open `_save.lua` and ImageMagick to decode DDS format and mirror decals.

Shouts out to `HazardX` for initial reverse engineering of the scmap format, but not to forget `svenni_badbwoi` and `tokyto` for maps which needed to be mirrored and kicking off this whole thing.

Known Issues
============
  * Mirror along y axis and diagonal yx is not implemented yet for units, props and decals
    * It's easy to add, but need maps for testing
  * Mirrored preview doesn't have correct lighting on mirrored side
    * Workaround: Save mirrored version with SC map editor to get preview re-rendered 
  * Option "keep side" doesn't remove units/props/decals on mirror side prior to mirroring
    * This is intentional at least for decals as they can have origin on mirrored side and still span more of the original side
    * For units and props it's just not implemented
  * Normal maps in scmap getting some special treatment, but effect is unknown
  * Unit meshes are not getting mirrored
    * Yeah, what can I do about this?
  * Connections between nodes are not taken into account
    * You need to fix air and land pass nodes in SC map editor after mirroring

Using a Command Line Orientated Script with Windows
=================================================
I didn't use Windows while implementing this script. I did only use Windows running in a VM to make some of theses screenshots below. Thing is, Windows is bad at the command line. That's why you Windows users need a [mirror_batch_example_theta.bat](mirror_batch_example_theta.bat) file. You will have to fill in all your Python/ImageMagick/Maps pathes there, because you wouldn't want to do that in a Windows terminal. Some advice would be to create a copy of that file for every map you want to mirror. You will change this file more than once and you need to understand most of it. The file contains a usage/help text from the mirror script as reference to the mirror script command line.

Installation (Windows)
======================
  * [Download and install ImageMagick](#download-and-install-imagemagick)
  * [Find and remember ImageMagick path](#find-and-remember-imagemagick-path)
  * [Download and install Python 3.5](#download-and-install-python-35-32-bit)
  * [Find and remember Python 3.5 path](#find-and-remember-python-35-path)
  * [Find and remember SC gamedata path](#find-and-remember-sc-gamedata-path)
  * [Copy and update mirror Batch script](#copy-and-update-mirror-batch-script)
  * [Running first time](#running-first-time)

## Download and install ImageMagick
![Download page on ImageMagick website](doc/1.1-download_and_install_imagemagick.png?raw=true "Download and install ImageMagick")
## Find and remember ImageMagick path
![ImageMagick directory in Explorer window](doc/1.2-find_and_remember_imagemagick_path.png?raw=true "Find and remember ImageMagick path")
## Download and install Python 3.5 (32 Bit)
![Python website menu](doc/2.1-download_and_install_python35.png?raw=true "Download and install Python 3.5")
![Python website download page with marking for version 3.5](doc/2.2-download_and_install_python35_continued.png?raw=true "Download and install Python 3.5")
## Find and remember Python 3.5 path
![Python 3.5 directory in Explorer window](doc/2.3-find_and_remember_python_path.png?raw=true "Find and remember Python 3.5 path")
## Find and remember SC gamedata path
![Supreme Commander gamedata in Explorer window](doc/3-find_and_rembember_gamedata_path.png?raw=true "Find and remember SC gamedata path")
## Copy and update mirror Batch script
![Mirror Batch script contents](doc/4-copy_and_update_mirror_batch_script.png?raw=true "Copy and update mirror Batch script")
Put in all the pathes you remebered and maybe change `--mirror-axis` and/or add a `--keep-side=2` parameter.
## Running first time
### Lupa and docopt been installed by Python Pip
![](doc/5.1-running_batch_should_install_lupa_and_docopt.png?raw=true "")
### Mirror script doing some Magick
![](doc/5.2-running_batch_should_then_process_some_images_and_do_mirror_stuff.png?raw=true "")
![](doc/5.3-run_batch_finishes_with_pause_command.png?raw=true "Script finished")
