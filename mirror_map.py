#!/usr/bin/python
# created using python 3.6

import copy
from functools import partial
import math
import os
import re
from struct import pack, unpack
import subprocess
import sys
import tempfile
from zipfile import ZipFile
from read_scmap import read_scmap, EmbeddedScMapGrayImage, EmbeddedScMapDDSImage

def main():

    from docopt import docopt
    doc = '''
    Usage:
        {name} <infile> <outfile> --supcom-gamedata=<path> --mirror-axis=<axis> [options]

    Options:
        -h, --help                 Show this screen and exit.
        --mirror-axis=<axis>       axis=x|y|xy|yx
        --imagemagick=<path>       [default: /usr/bin/convert]
        --supcom-gamedata=<path>   Directory containing env.scd
        --keep-side=<1|2>          side=1|2 [default: 1]
        --map-version=v<n>         [default: v0001]
        --not-mirror-scmap-images  Don't mirror images saved in scmap
        --not-mirror-decals        Don't mirror decals
        --not-mirror-props         Don't mirror props
        --debug-read-scmap         Debug scmap parsing
        --debug-decals-position    Debug decal fun
        --dump-scmap-images        Dump images saved in scmap
    '''.format(name=os.path.basename(sys.argv[0]))
    args = docopt(doc, sys.argv[1:])

    path_to_infile_scmap = args['<infile>']
    old_scmap_name, oldScmapExtension = os.path.splitext(os.path.basename(  path_to_infile_scmap ))
    path_to_infile_scmap_save_lua = os.path.join( os.path.dirname(  path_to_infile_scmap ), "{}_save.lua".format(old_scmap_name) )

    path_to_new_scmap = args['<outfile>']
    new_scmap_name, newScmapExtension = os.path.splitext(os.path.basename(  path_to_new_scmap ))
    new_map_directory = os.path.dirname( path_to_new_scmap )
    if args['--map-version']:
        decals_path_prefix = '/maps/{}.{}'.format( new_scmap_name, args['--map-version'] )
    else:
        decals_path_prefix = '/maps/{}'.format( new_scmap_name )
    path_to_new_scmap_save_lua = os.path.join( os.path.dirname(  path_to_new_scmap ), "{}_save.lua".format(new_scmap_name) )

    mirror_axis = args['--mirror-axis']
    mirror_keep_side = int(args['--keep-side'])
    ImageMagicConvert = args['--imagemagick']
    decals_archivePath = '{}/env.scd'.format(args['--supcom-gamedata'])
    mirror_scmap_images = not args['--not-mirror-scmap-images']
    do_mirror_decals = not args['--not-mirror-decals']
    do_mirror_props = not args['--not-mirror-props']
    debug_read_scmap = args['--debug-read-scmap']
    debug_decals_position = args['--debug-decals-position']
    dump_scmap_images = args['--dump-scmap-images']

    map_infos = read_scmap( path_to_infile_scmap, debug_print_enabled=debug_read_scmap )

    # ingame positions have width/height + 1
    # e.g. x,y in range (0,0) to (512,512)
    map_infos['ingame_map_size'] = ( map_infos['map_size'][0]+1, map_infos['map_size'][1]+1 )


    def filter_constant_pixels( pixel_coord, mirror_axis, keep_side, size ):
        if keep_side == -1:
            return False
        half_width = size[0]/2
        half_height = size[1]/2
        m = size[0] / size[1]
        x,y = pixel_coord
        if mirror_axis == 'x':
            if keep_side == 1 and x >= half_width:
                return False
            if keep_side == 2 and x < half_width:
                return False
        elif mirror_axis == 'y':
            if keep_side == 1 and y >= half_height:
                return False
            if keep_side == 2 and y < half_height:
                return False
        elif mirror_axis == 'xy':
            if keep_side == 1 and x >= y*m:
                return False
            if keep_side == 2 and x < y*m:
                return False
        elif mirror_axis == 'yx':
            if keep_side == 1 and x >= ( size[0] - 1 - (y*m) ):
                return False
            if keep_side == 2 and x < ( size[0] - 1 - (y*m) ):
                return False
        return True

    def get_mirror_position( pixel_coord, mirror_axis, size ):
        x,y = pixel_coord
        m = size[0] / size[1]
        if mirror_axis == 'x':
            return ( size[0] - 1 - x, y )
        elif mirror_axis == 'y':
            return ( x, size[1] - 1 - y )
        elif mirror_axis == 'xy':
            return ( y*m, x/m )
        elif mirror_axis == 'yx':
            return ( size[0] - 1 - (y*m), size[1] - 1 - (x/m) )

    def mirror_position3( position, axis, size ):
        new_position_2d = get_mirror_position( ( position[0], position[2] ), axis, size )
        return ( new_position_2d[0] , position[1], new_position_2d[1] )

    def get_mirror_pixel_address( pixel_coord, mirror_axis, size ):
        mirror_pixel = get_mirror_position( pixel_coord, mirror_axis, size )
        return size[0]*int(mirror_pixel[1]) + int(mirror_pixel[0])

    def mirror_gray_image( image, pixels, keep_pixels, mirror_axis, mirror_keep_side ):
        image_data = bytearray(image.data)
        mirror_source_data = bytearray(image_data)
        depth_bytes = int( int(image.depth) / 8 )
        for x,y in pixels:
            pixel_address = ( image.size[0] * y + x ) * depth_bytes
            mirror_pixel_address = get_mirror_pixel_address( (x,y), mirror_axis, image.size ) * depth_bytes
            try:
                image_data[pixel_address:pixel_address+depth_bytes] = image_data[pixel_address:pixel_address+depth_bytes] if (x,y) in keep_pixels else mirror_source_data[mirror_pixel_address:mirror_pixel_address+depth_bytes]
            except IndexError as e:
                print("IndexError for pixel {} and mirror pixel {} with image size {} for mirror axis {}".format((x,y), get_mirror_position( (x,y), mirror_axis, image.size ), image.size, mirror_axis))
                raise e
            if depth_bytes > 1:
                image_data[pixel_address+1] = image_data[pixel_address+1] if (x,y) in keep_pixels else mirror_source_data[mirror_pixel_address+1]
        image.data = image_data

    def mirror_uncompressed_dds_image( image, mirror_axis, mirror_keep_side ):
        image_data = bytearray(image.data)
        mirror_source_data = bytearray(image_data)
        depth_bytes = int( int(image.depth) / 8 )
        mip_map_size = ( image.size[0], image.size[1] )
        for mip_map_level in range(max(image.header.mip_map_count,1)):
            mip_map_info = image.mip_map_infos[mip_map_level]
            mip_map_size = mip_map_info[1]
            offset = mip_map_info[0]
            pixels = [(x,y) for x in range(mip_map_size[0]) for y in range(mip_map_size[1])]
            keep_pixels = set([ pixel for pixel in pixels if filter_constant_pixels( pixel, mirror_axis, mirror_keep_side, mip_map_size ) ])
            for x,y in pixels:
                pixel_address = offset + ( mip_map_size[0] * y + x ) * depth_bytes
                mirror_pixel_address = offset + get_mirror_pixel_address( (x,y), mirror_axis, mip_map_size ) * depth_bytes
                try:
                    image_data[pixel_address:pixel_address+depth_bytes] = image_data[pixel_address:pixel_address+depth_bytes] if (x,y) in keep_pixels else mirror_source_data[mirror_pixel_address:mirror_pixel_address+depth_bytes]
                    if image.is_normal_map:
                        normal_component = int(image_data[pixel_address+1])
                        image_data[pixel_address+1] = int(image_data[pixel_address+3])
                        image_data[pixel_address+3] = normal_component

                except IndexError as e:
                    print("IndexError for mip map {} pixel {} and mirror pixel {} with image size {} for mirror axis {}".format(mip_map_level, (x,y), get_mirror_position( (x,y), mirror_axis, mip_map_size ), mip_map_size, mirror_axis))
                    raise e
        image.data = image_data

    def mirror_compressed_dds_image( image, mirror_axis, mirror_keep_side ):
        pixels = [(x,y) for x in range(4) for y in range(4)]
        keep_pixels = set([ pixel for pixel in pixels if filter_constant_pixels( pixel, mirror_axis, mirror_keep_side, (4,4) ) ])
        old_image = EmbeddedScMapDDSImage( image.data )
        x_blocks = image.size[0] // 4
        y_blocks = image.size[1] // 4
        for mip_map_level in range(max(image.header.mip_map_count,1)):
            blocks_size = ( x_blocks, y_blocks )
            blocks = [(x,y) for x in range(blocks_size[0]) for y in range(blocks_size[1])]
            keep_blocks = set([ block for block in blocks if filter_constant_pixels( block, mirror_axis, mirror_keep_side, blocks_size ) ])
            for block in keep_blocks:
                mirror_block = get_mirror_position( block, mirror_axis, blocks_size )
                x,y = block
                mirror_x, mirror_y = mirror_block
                try:
                    block_data = list(old_image.get_block( x, y, mip_map_level ))
                    old_alpha = block_data[2]
                    old_color = block_data[5]
                    new_alpha = old_alpha[:]
                    new_color = old_color[:]
                    if block == mirror_block:
                        iter_over = keep_pixels
                    else:
                        iter_over = pixels
                    for pixel in iter_over:
                        mirror_pixel_address = get_mirror_pixel_address( pixel, mirror_axis, (4,4) )
                        pixel_address = 4*pixel[1] + pixel[0]
                        new_alpha[mirror_pixel_address] = old_alpha[pixel_address]
                        new_color[mirror_pixel_address] = old_color[pixel_address]
                    block_data[2] = new_alpha
                    block_data[5] = new_color
                    image.set_block( mirror_x, mirror_y, mip_map_level, block_data )
                except Exception as e:
                    print("x:{} y:{} mip_map_level:{}".format(x,y,mip_map_level))
                    raise(e)
            x_blocks //= 2
            y_blocks //= 2


    def mirror_image( image, mirror_axis, mirror_keep_side ):
        pixels = [(x,y) for x in range(image.size[0]) for y in range(image.size[1])]
        keep_pixels = set([ pixel for pixel in pixels if filter_constant_pixels( pixel, mirror_axis, mirror_keep_side, image.size ) ])
        if image.extension == 'gray':
            mirror_gray_image( image, pixels, keep_pixels, mirror_axis, mirror_keep_side )
        elif image.extension == 'dds':
            if image.has_uncompressed_rgb_data:
                images = image.as_grays()
                for _image in images:
                    mirror_gray_image( _image, pixels, keep_pixels, mirror_axis, mirror_keep_side )
                image.from_grays(images)
            else:
                if image.is_normal_map:
                    new_image = image.as_uncompressed()
                    mirror_uncompressed_dds_image( new_image, mirror_axis, mirror_keep_side )
                    image.__init__( new_image.data, new_image.is_normal_map )
                else:
                    mirror_compressed_dds_image( image, mirror_axis, mirror_keep_side )
        else:
            raise Exception("get_mirror_pixel_address: not implemented")

    if mirror_scmap_images:
        images = map_infos['images']
        for name in images:
            image = images[name]
            try:
                print("Mirroring scmap image {}".format(name))
                mirror_image( image, mirror_axis, mirror_keep_side )
            except EmbeddedScMapDDSImage.FormatException:
                print("Warning: skipping image {} because of unsupported format error".format(name))


    if dump_scmap_images:

        images = map_infos['images']
        for name in images:
            image = images[name]

            # build dump file path
            path_prefix = "{}/{}_{}".format( new_map_directory, new_scmap_name, name )
            raw_output_file_path = "{}.{}".format( path_prefix, image.extension )

            # dump image data
            print("Dumping scmap image {}".format(name))
            open( raw_output_file_path, 'wb' ).write( image.data )

            # build png file path
            output_file_path = "{}.{}".format( path_prefix, 'png' )

            # convert image dump to png
            if os.path.exists(ImageMagicConvert):
                cmd = [ ImageMagicConvert ]
                if image.extension == 'gray':
                    cmd += [ '-size',"{}x{}".format(*image.size),'-depth', image.depth ]
                cmd += [ raw_output_file_path, output_file_path ]
                print("running {}".format(' '.join(cmd)))
                subprocess.run( cmd )

    if mirror_axis == 'x':
        def rotate_decal(rotation):
            return ( rotation[2], math.pi/2 - rotation[1], -rotation[0] )
        def rotate_prop( rotationX, rotationY, rotationZ ):
            rad = math.acos( rotationX[0] ) + math.pi
            new_rotationX = (  math.cos(rad),  rotationX[1], math.sin(rad) )
            new_rotationY = (  rotationY[0],   rotationY[1], rotationY[2]  )
            new_rotationZ = ( -math.sin(rad),  rotationZ[1], math.cos(rad) )
            return ( new_rotationX, new_rotationY, new_rotationZ )
    elif mirror_axis == 'y':
        def rotate_decal(rotation):
            return ( rotation[2], -math.pi/2 - rotation[1], rotation[0] )
        def rotate_prop( rotationX, rotationY, rotationZ ):
            rad = math.acos( rotationX[0] ) + math.pi
            new_rotationX = (  math.cos(rad),  rotationX[1], math.sin(rad) )
            new_rotationY = (  rotationY[0],   rotationY[1], rotationY[2]  )
            new_rotationZ = ( -math.sin(rad),  rotationZ[1], math.cos(rad) )
            return ( new_rotationX, new_rotationY, new_rotationZ )
    elif mirror_axis == 'xy':
        def rotate_decal(rotation):
            return ( rotation[2], -rotation[1], -rotation[0] )
        # not really posible to mirror the mesh by rotation...
        def rotate_prop( rotationX, rotationY, rotationZ ):
            rad = math.acos( rotationX[0] ) + math.pi
            new_rotationX = (  math.cos(rad),  rotationX[1], math.sin(rad) )
            new_rotationY = (  rotationY[0],   rotationY[1], rotationY[2]  )
            new_rotationZ = ( -math.sin(rad),  rotationZ[1], math.cos(rad) )
            return ( new_rotationX, new_rotationY, new_rotationZ )
    elif mirror_axis == 'yx':
        def rotate_decal(rotation):
            return ( rotation[2], math.pi - rotation[1], -rotation[0] )
        # not really posible to mirror the mesh by rotation...
        def rotate_prop( rotationX, rotationY, rotationZ ):
            rad = math.acos( rotationX[0] ) + math.pi
            new_rotationX = (  math.cos(rad),  rotationX[1], math.sin(rad) )
            new_rotationY = (  rotationY[0],   rotationY[1], rotationY[2]  )
            new_rotationZ = ( -math.sin(rad),  rotationZ[1], math.cos(rad) )
            return ( new_rotationX, new_rotationY, new_rotationZ )
    else:
        raise Exception("IMPLEMENT ME!!!")

    def mirror_decals( map_infos, decals_archivePath, new_map_directory, decals_path_prefix ):

        def generate_mirrored_decal( decals_archive, decal_to_mirror, is_normal_map ):
            if not decal_to_mirror:
                return b''
            new_decal_path = new_map_directory + '/flop_and_rotate_90' + decal_to_mirror
            new_decal_ingame_path = '{}/flop_and_rotate_90{}'.format( decals_path_prefix, decal_to_mirror )
            if os.path.exists( new_decal_path ):
                return new_decal_ingame_path.encode()

            with decals_archive.open(decals_archive.decals_case_insensitive_lookup[decal_to_mirror[1:].lower()]) as decal_texture:
                print("Mirroring decal {}".format(decal_to_mirror))
                os.makedirs( os.path.dirname( new_decal_path ), exist_ok = True )
                image = EmbeddedScMapDDSImage(decal_texture.read())
                image.is_normal_map = is_normal_map
                #image.debug_print()
                mirror_image( image, 'xy', -1 )
                open(new_decal_path,'wb').write(image.data)

            return new_decal_ingame_path.encode()

        new_decals = []
        decals_count = len(map_infos['decals'])

        map_infos['debug_props'] = []

        with ZipFile( decals_archivePath, 'r' ) as decals_archive:
            decals_archive.decals_case_insensitive_lookup = { s.lower():s for s in decals_archive.namelist() }

            for decal in map_infos['decals']:
                (
                    decal_id,decalType,unknown15,
                    decals_texture1_path,decals_texture2_path,
                    scale,position,rotation,
                    cut_off_lod,near_cut_off_lod,remove_tick
                ) = decal

                new_position = mirror_position3( position, mirror_axis, map_infos['ingame_map_size'] )
                new_rotation = rotate_decal( rotation )

                is_normal_map = ( decalType == 2 )

                if debug_decals_position:
                    # switch normals to albedo for debugging
                    decalType = 1
                    decal[1] = 1

                    # place theta bridges at decal position with decal rotation
                    map_infos['debug_props'] += [(
                            b'/env/redrocks/props/thetabridge01_prop.bp',
                            position,
                            (-math.cos(rotation[1]),0,-math.sin(rotation[1])),
                            (0,1,0),
                            (math.sin(rotation[1]),0,-math.cos(rotation[1])),
                            (1,1,1))]
                    map_infos['debug_props'] += [(
                            b'/env/redrocks/props/thetabridge01_prop.bp',
                            new_position,
                            (-math.cos(new_rotation[1]),0,-math.sin(new_rotation[1])),
                            (0,1,0),
                            (math.sin(new_rotation[1]),0,-math.cos(new_rotation[1])),
                            (1,1,1))]

                new_decals_texture1_path = generate_mirrored_decal( decals_archive, decals_texture1_path.decode(), is_normal_map )
                new_decals_texture2_path = generate_mirrored_decal( decals_archive, decals_texture2_path.decode(), is_normal_map )

                new_decals.append([
                    decals_count+decal_id,decalType,unknown15,
                    new_decals_texture1_path,new_decals_texture2_path,
                    scale,new_position,new_rotation,
                    cut_off_lod,near_cut_off_lod,remove_tick
                ])

        map_infos['decals'] += new_decals

    def mirror_props( map_infos ):
        new_props = []
        for prop in map_infos['props']:
            (blueprintPath,position,rotationX,rotationY,rotationZ,scale) = prop
            # create mirrored parameters
            new_position = mirror_position3( position, mirror_axis, map_infos['ingame_map_size'] )
            new_rotation = rotate_prop(rotationX,rotationY,rotationZ)
            # add version with mirrored parameters to props list
            new_props.append( (blueprintPath,new_position,*new_rotation,scale) )
        map_infos['props'] += new_props


    if do_mirror_decals:
        print("Mirroring decals")
        mirror_decals( map_infos, decals_archivePath, new_map_directory, decals_path_prefix )

    if do_mirror_props:
        print("Mirroring props")
        mirror_props( map_infos )

    if 'debug_props' in map_infos:
        map_infos['props'] += map_infos['debug_props']

    write_output_scmap( path_to_infile_scmap, path_to_new_scmap, map_infos )

    if os.path.exists(path_to_infile_scmap_save_lua):
        scenario = mirror_stuff_in_save_lua( path_to_infile_scmap_save_lua, path_to_new_scmap_save_lua, map_infos, mirror_axis, mirror_position3 )
        with open(path_to_new_scmap_save_lua,'w') as newSaveLua:
            writeSaveLua( newSaveLua, scenario, first=True )
    else:
        print("Warning: {} does not exist.".format(path_to_infile_scmap_save_lua))

def mirror_stuff_in_save_lua( path_to_infile_scmap_save_lua, path_to_new_scmap_save_lua, map_infos, mirror_axis, mirror_position3 ):

    if mirror_axis == 'x':
        unitTypeTranslation = {
            'xec8001': 'xec8003',
            'xec8002': 'xec8004',
            'xec8005': 'xec8008',
            'xec8006': 'xec8007',
            'xec8009': 'xec8012',
            'xec8010': 'xec8011',
            'xec8013': 'xec8018',
            'xec8014': 'xec8017',
            'xec8015': 'xec8016',
            'xec8019': 'xec8020',
        }
        unitPositionFix = {
            'xec8012': (-1, 0, 1), # -|
            'xec8004': ( 1, 0, 0), # ---
            'xec8008': (-1, 0, 1), #  |-
            'xec8003': ( 0, 0,-1), #  |
        }
    elif mirror_axis == 'y':
        unitTypeTranslation = {
        }
        unitPositionFix = {
        }
    elif mirror_axis == 'xy':
        unitTypeTranslation = {
            'xec8004': 'xec8003',
            'xec8003': 'xec8004',
        }
        unitPositionFix = {
        }
    elif mirror_axis == 'yx':
        unitTypeTranslation = {
        }
        unitPositionFix = {
        }
    else:
        raise Exception("IMPLEMENT ME!!!")

    def translate_unit_position( unitType, position, mirror_axis, map_size ):
        position = mirror_position3( position, mirror_axis, map_size )
        if unitType in list(unitPositionFix):
            fix = unitPositionFix[unitType]
            position = ( position[0]+fix[0], position[1]+fix[1], position[2]+fix[2] )
        return position

    def dummyUnitRotation( unitType, rotation ):
        return ( rotation[0], rotation[1], rotation[2] )

    def translateUnitType( unitTypeTranslation, unitType ):
        if unitType in list(unitTypeTranslation):
            return unitTypeTranslation[unitType]
        else:
            return unitType

    if not os.path.exists( path_to_infile_scmap_save_lua ):
        print("Couldn't find \"{}\".".format(path_to_infile_scmap_save_lua))
        return

    path_to_old_scmap_save_module, _ = os.path.splitext( path_to_infile_scmap_save_lua )

    os.chdir(os.path.dirname(path_to_infile_scmap_save_lua))

    # import map_save.lua with lupa
    import lupa
    lua = lupa.LuaRuntime(unpack_returned_tuples=False)
    lua.execute('FLOAT=function(x) return string.format("FLOAT( %.6f )",x) end')
    lua.execute('BOOLEAN=function(x) return string.format("BOOLEAN( %s )", x and "true" or "false" ) end')
    lua.execute('STRING=function(x) return string.format("STRING( \'%s\' )",x) end')
    lua.execute('VECTOR3=function(x,y,z) return "VECTOR3( "..x..", "..y..", "..z.." )" end')
    lua.execute('RECTANGLE=function(a,b,c,d) return "RECTANGLE( "..a..", "..b..", "..c..", "..d.." )" end')
    lua.execute('GROUP=function(x) return function() return x end end')
    lua.require( os.path.relpath(path_to_old_scmap_save_module) )


    scenario = lua.table_from({'Scenario': lua.eval('Scenario') })

    # mirror Mexes
    change_value_by_path_regex(
        re.compile("/Scenario/MasterChain/[^/]*/Markers"),
        partial(
            partial(duplicate_mirror_and_rotate,re.compile("/[^/]*")),
                mirror_axis,
                partial(translate_unit_position,mirror_axis=mirror_axis,map_size=map_infos['ingame_map_size']),
                dummyUnitRotation,
                partial(translateUnitType,unitTypeTranslation),
        ), scenario )

    # mirror some armies
    change_value_by_path_regex(
        re.compile("/Scenario/Armies/[^/]*/[^/]*/Units/[^/]*/Units"),
        partial(
            partial(duplicate_mirror_and_rotate,re.compile("/[^/]*")),
                mirror_axis,
                partial(translate_unit_position,mirror_axis=mirror_axis,map_size=map_infos['ingame_map_size']),
                dummyUnitRotation,
                partial(translateUnitType,unitTypeTranslation),
        ), scenario )

    return scenario

# duplicate 'position' and 'Position' values for tables matched by regular expression
def duplicate_mirror_and_rotate(regEx,mirror_axis,positionFunc,rotateFunc,translateUnitTypeFunc,k,v,rootTable):
    old_tables = getTablesByPathRegex( regEx, v )
    new_table = {}
    for key in old_tables:
        if key.startswith('ARMY_'):
            new_key = 'ARMY_{}'.format(int(key[5:])+1)
        else:
            new_key = '{}m{}'.format(key,mirror_axis)
        newParams = {}
        newParams.update( old_tables[key] )
        if 'type' in newParams:
            unitType = newParams['type'] = translateUnitTypeFunc( newParams['type'] )
        elif 'resource' in newParams:
            unitType = 'mass'
        else:
            unitType = 'unknown'
        if 'position' in newParams:
            newParams['position'] = mapSaveLuaVector( partial(positionFunc,unitType), newParams['position'] )
        elif 'Position' in newParams:
            newParams['Position'] = mapSaveLuaVector( partial(positionFunc,unitType), newParams['Position'] )
        if 'orientation' in newParams:
            newParams['orientation'] = mapSaveLuaVector( partial(rotateFunc,unitType), newParams['orientation'] )
        elif 'Orientation' in newParams:
            newParams['Orientation'] = mapSaveLuaVector( partial(rotateFunc,unitType), newParams['Orientation'] )
        new_table.update( {new_key: newParams} )
    for k2 in new_table:
        v[k2] = new_table[k2]
    return v

# write the output _save.lua
def writeSaveLua( oStream, luaTable, path='', first=False ):
    import lupa
    indent = "    "*(path.count('/'))
    # try to make output look more like original
    keys = orderedSaveLuaKeys( list(luaTable), path )
    # iterate over lua table keys
    for k in keys:
        newPath = '/'.join([path,str(k)])
        printPathDecorator(oStream,indent,newPath)
        if keyIsWrittenAlternativly(newPath):
            oStream.write("{}['{}'] = ".format(indent,k))
        else:
            oStream.write("{}{} = ".format(indent,k))
        v = luaTable[k]
        if lupa.lua_type(v) == 'table' or type(v) is dict:
            if list(v) == [1,2,3]:
                oStream.write("{{ {0:.6f}, {1:.6f}, {2:.6f} }}".format(v[1],v[2],v[3]))
            else:
                oStream.write("{\n")
                writeSaveLua( oStream, v, newPath )
                oStream.write("{}}}".format(indent))
        elif type(v) is str:
            if v[:5] in ['FLOAT','BOOLE','STRIN','VECTO']:
                oStream.write("{}".format(v))
            else:
                oStream.write("'{}'".format(v))
        elif type(v) is int:
            oStream.write("{}".format(v))
        elif lupa.lua_type(v) == 'function':
            oStream.write("GROUP {\n")
            writeSaveLua( oStream, v(), newPath )
            oStream.write("{}}}".format(indent))
        elif type(v) is tuple:
            oStream.write("{{ {:.6f}, {:.6f}, {:.6f} }}".format(*v))
        else:
            raise Exception("Unknown format {} at {} ".format(type(v),newPath))
        if not first:
            oStream.write(",\n")

# try to make output look more like original
# by enforcing some predefined order
def orderedSaveLuaKeys( keys, path ):
    pathDepth = path.count('/')
    oldKeys = copy.copy(sorted(keys))
    new_keys = []
    if path == '/Scenario':
        for k in [
            'next_area_id','Props','Areas',
            'MasterChain','Chains',
            'next_queue_id','Orders',
            'next_platoon_id', 'Platoons',
            'next_army_id','next_group_id','next_unit_id',
            'Armies']:
            if k in oldKeys:
                oldKeys.remove(k)
                new_keys.append(k)
        new_keys += oldKeys
        return new_keys
    elif path.startswith('/Scenario/MasterChain/'):
        for k in [
            'size', 'resource', 'amount', 'color', 'editorIcon',
            'type','prop',
            'orientation','position']:
            if k in oldKeys:
                oldKeys.remove(k)
                new_keys.append(k)
        new_keys += oldKeys
        return new_keys
    elif path.startswith('/Scenario/Armies/'):
        for k in [
            'mass', 'energy',
            'personality', 'plans', 'color', 'faction', 'Economy', 'Alliances',
            'type', 'orders','platoon',
            'Units','Position','Orientation',
            'PlatoonBuilders', 'next_platoon_builder_id']:
            if k in oldKeys:
                oldKeys.remove(k)
                new_keys.append(k)
        new_keys += oldKeys
        return new_keys
    else:
        return oldKeys

# try to make output look more like original
# by adding theses huge comment sections
def printPathDecorator( oStream, indent, path ):
    fmt = "{0:}--[["+" "*75+"]]--\n{0:}--[[  {1: <73}]]--\n{0:}--[["+" "*75+"]]--\n"
    s = ''
    if path == '/Scenario':
        s += fmt.format( indent, "Automatically generated code (do not edit)" )
        s += fmt.format( indent, "Scenario" )
    elif path == '/Scenario/Props':
        s += fmt.format( indent, "Props" )
    elif path == '/Scenario/Areas':
        s += fmt.format( indent, "Areas" )
    elif path == '/Scenario/MasterChain':
        s += fmt.format( indent, "Markers" )
    elif path == '/Scenario/next_queue_id':
        s += fmt.format( indent, "Orders" )
    elif path == '/Scenario/next_platoon_id':
        s += fmt.format( indent, "Platoons" )
    elif path == '/Scenario/next_army_id':
        s += fmt.format( indent, "Armies" )
    elif path.startswith('/Scenario/Armies/') and path.count('/') == 3:
        s += fmt.format( indent, "Army" )
    if s:
        oStream.write(s)

# try to make output look more like original
# by alternating writings e.g. Units and ['Units']
def keyIsWrittenAlternativly(path):
    pathDepth = path.count('/')
    if path.startswith('/Scenario/MasterChain/'):
        if pathDepth != 4:
            return True
    if path.startswith('/Scenario/Chains/'):
        if pathDepth != 4:
            return True
    if path.startswith('/Scenario/Armies/'):
        if pathDepth == 3:
            return True
        if pathDepth == 4 and path.endswith('/Units'):
            return True
        if pathDepth == 6:
            return True
        if pathDepth == 8:
            return True
    return False

def mapSaveLuaVector( mirrorFunc, value ):
    import lupa
    if lupa.lua_type(value) == 'table':
        if list(value) == [1,2,3]:
            value = mirrorFunc((value[1],value[2],value[3]))
    elif value.startswith('VECTOR3'):
        value = eval(value[7:])
        value = mirrorFunc(value)
        return "VECTOR3( {}, {}, {} )".format(*value)
    return value

# helper function to traverse lua data by regular expression
def getTablesByPathRegex( regEx, luaTable, path='' ):
    import lupa
    ret = {}
    for key in list(luaTable):
        v = luaTable[key]
        newPath = '/'.join([path,str(key)])
        if regEx.match( newPath ):
            ret.update({key:v})
        elif lupa.lua_type(v) == 'table':
            ret.update(getTablesByPathRegex( regEx, v, newPath ))
    return ret

# update values for tables matched by regular expression
def change_value_by_path_regex( regEx, func, luaTable, rootTable=None, path='' ):
    import lupa
    if not rootTable: rootTable = luaTable
    for key in list(luaTable):
        v = luaTable[key]
        newPath = '/'.join([path,str(key)])
        if regEx.match( newPath ):
            luaTable[key] = func( key, v, rootTable )
        elif lupa.lua_type(v) == 'table':
            change_value_by_path_regex( regEx, func, v, rootTable, newPath )
        elif lupa.lua_type(v) == 'function':
            change_value_by_path_regex( regEx, func, v(), rootTable, newPath )

class MapParsingException(Exception):
    def __init__( self, subject, fileObject ):
        self.offset = fileObject.tell()
        self.message = "Couldn't parse {} before offset {} ".format( subject, self.offset )
        super(Exception, self).__init__( self.message )

def write_output_scmap( path_to_old_scmap, path_to_new_scmap, infos ):
    with open(path_to_old_scmap,'rb') as scmap:
        with open(path_to_new_scmap,'wb') as new_scmap:
            decals_written = False

            scmap.seek( 0, os.SEEK_END )
            old_scmap_file_size = scmap.tell()
            scmap.seek( 0 )

            image_sections = list(infos['images'])
            while len(image_sections) > 0:

                # find image section with lowest start offset
                read_cursor = scmap.tell()
                min_start_offset = old_scmap_file_size
                min_start_offset_image_name = 'invalid'
                for image_name in image_sections:
                    start_offset = infos['offsets']['{}_start'.format(image_name)]
                    if start_offset < min_start_offset:
                        min_start_offset = start_offset
                        min_start_offset_image_name = image_name

                assert( min_start_offset_image_name != 'invalid' )
                image_sections.remove( min_start_offset_image_name )

                image_name = min_start_offset_image_name

                start_offset = infos['offsets']['{}_start'.format(image_name)]
                has_length_prefix = infos['offsets']['{}_length_prefix'.format(image_name)]
                end_offset = infos['offsets']['{}_end'.format(image_name)]
                image = infos['images'][image_name]
                want_seek = start_offset

                while scmap.tell() < want_seek:
                    # fill in decals
                    if not decals_written and want_seek > infos['offsets']['decals_start']:
                        new_scmap.write( scmap.read( infos['offsets']['decals_start'] - scmap.tell() ))
                        write_decals( new_scmap, infos['decals'] )
                        decals_written = True
                        scmap.seek(infos['offsets']['decals_end'])
                        continue
                    else:
                        new_scmap.write( scmap.read( want_seek - scmap.tell() ))
                        break
                if has_length_prefix:
                    new_scmap.write(pack('I',len(image.data)))
                new_scmap.write( image.data )
                scmap.seek( end_offset )

            write_props( new_scmap, infos['props'] )

def write_decals( new_scmap, decalsList ):
    new_scmap.write(pack('I',len(decalsList)))
    for decal in decalsList:
        (
            decal_id,decalType,unknown15,
            decals_texture1_path,decals_texture2_path,
            scale,position,rotation,
            cut_off_lod,near_cut_off_lod,remove_tick
        ) = decal
        decalRaw = pack('IIII',decal_id,decalType,unknown15,len(decals_texture1_path))
        decalRaw += decals_texture1_path
        decalRaw += pack('I',len(decals_texture2_path))
        if decals_texture2_path:
            decalRaw += decals_texture2_path
        decalRaw += pack('fffffffff',*scale,*position,*rotation)
        decalRaw += pack('ffI',cut_off_lod,near_cut_off_lod,remove_tick)
        new_scmap.write(decalRaw)

def write_props( new_scmap, propsList ):
    new_scmap.write(pack('I',len(propsList)))
    for prop in propsList:
        (blueprintPath,position,rotationX,rotationY,rotationZ,scale) = prop
        new_scmap.write(blueprintPath)
        new_scmap.write(b'\0')
        new_scmap.write(pack('fffffffffffffff',*(*position,*rotationX,*rotationY,*rotationZ,*scale)))

if __name__ == '__main__':
    main()

