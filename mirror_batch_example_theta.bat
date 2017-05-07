SET PYTHON=C:\Users\local_admin\AppData\Local\Programs\Python\Python35-32
SET MIRRORSCRIPT=mirror_map.py
SET IMAGEMAGICKEXE=C:\Program Files\ImageMagick-7.0.5-Q8\magick.exe
SET GAMEDATA=C:\your_supcom_gamedata
SET INFILE=F:\Maps\2v2 sand box.v0001\2v2 sand box.scmap
SET OUTFILE=F:\Maps\2v2 sand box.v0001 - mirror\2v2 sand box.scmap
SET OUT_VERSION=v0001
SET MIRROR="xy"

: Install lupa and docopt
"%PYTHON%\Scripts\pip.exe" install "https://github.com/FAForever/python-wheels/releases/download/1.0.2/lupa-1.3-cp35-cp35m-win32.whl"
"%PYTHON%\Scripts\pip.exe" install docopt

: Run mirror script
"%PYTHON%\python.exe" "%MIRRORSCRIPT%" "%INFILE%" "%OUTFILE%" --map-version %OUT_VERSION% --supcom-gamedata="%GAMEDATA%" --imagemagick="%IMAGEMAGICKEXE%" --mirror-axis=%MIRROR%

: Help text of mirror script
:   Usage:
:      {name} <infile> <outfile> --supcom-gamedata=<path> --mirror-axis=<axis> [options]
:
:   Options:
:       -h, --help                 Show this screen and exit.
:       --mirror-axis=<axis>       axis=x|y|xy|yx
:       --imagemagick=<path>       [default: /usr/bin/convert]
:       --supcom-gamedata=<path>   Directory containing env.scd
:       --keep-side=<1|2>          side=1|2 [default: 1]
:       --map-version=v<n>         [default: v0001]
:       --not-mirror-scmap-images  Don't mirror images saved in scmap
:       --debug-read-scmap         Debug scmap parsing
:       --debug-decals-position    Debug decal fun
:       --dump-scmap-images        Dump images saved in scmap

pause
