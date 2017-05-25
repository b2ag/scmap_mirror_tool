from collections import namedtuple
from struct import pack, unpack, calcsize
import math

SCMAPMAGIC = b'\x4d\x61\x70\x1a'
DDSMAGIC = b'DDS '

def read_c_string(f):
    buf = b''
    while True:
        b = f.read(1)
        if b is None or b == b'\0':
            return buf
        else:
            buf += b

class EmbeddedScMapImage( object ):
    extension = 'bin'
    has_header = False
    def __init__( self, data ):
        self.data = bytearray(data)

class EmbeddedScMapGrayImage( EmbeddedScMapImage ):
    extension = 'gray'
    def __init__( self, data, size, depth ):
        super().__init__( data )
        self.size = size
        self.depth = depth

class EmbeddedScMapDDSImage( EmbeddedScMapImage ):
    DDSMAGIC = b'DDS '
    FLAGS = {
        'DDSD_CAPS': 0x1,
        'DDSD_HEIGHT': 0x2,
        'DDSD_WIDTH': 0x4,
        'DDSD_PITCH': 0x8,
        'DDSD_PIXELFORMAT': 0x1000,
        'DDSD_MIPMAPCOUNT': 0x20000,
        'DDSD_LINEARSIZE': 0x80000,
        'DDSD_DEPTH': 0x800000,
    }
    PPF_FLAGS = {
        'DDPF_ALPHAPIXELS': 0x1,
        'DDPF_ALPHA': 0x2,
        'DDPF_FOURCC': 0x4,
        'DDPF_RGB': 0x40,
        'DDPF_YUV': 0x200,
        'DDPF_LUMINANCE': 0x20000,
    }
    CAPS = {
        'DDSCAPS_COMPLEX': 0x8,
        'DDSCAPS_MIPMAP': 0x400000,
        'DDSCAPS_TEXTURE': 0x1000,
        'DDSCAPS2_CUBEMAP': 0x200,
    }
    CAPS2 = {
        'DDSCAPS2_CUBEMAP_POSITIVEX': 0x400,
        'DDSCAPS2_CUBEMAP_NEGATIVEX': 0x800,
        'DDSCAPS2_CUBEMAP_POSITIVEY': 0x1000,
        'DDSCAPS2_CUBEMAP_NEGATIVEY': 0x2000,
        'DDSCAPS2_CUBEMAP_POSITIVEZ': 0x4000,
        'DDSCAPS2_CUBEMAP_NEGATIVEZ': 0x8000,
        'DDSCAPS2_VOLUME': 0x200000,
    }
    HEADER_FIELDS = [
            'header_size',
            'flags',
            'height',
            'width',
            'pitch_or_linear_size',
            'depth',
            'mip_map_count',
            'reserved1_1','reserved1_2','reserved1_3','reserved1_4','reserved1_5','reserved1_6','reserved1_7','reserved1_8','reserved1_9','reserved1_10','reserved1_11',
            'ppf_header_size',
            'ppf_flags',
            'ppf_four_cc',
            'ppf_rgb_bit_count',
            'ppf_red_bit_mask',
            'ppf_green_bit_mask',
            'ppf_blue_bit_mask',
            'ppf_alpha_bit_mask',
            'caps',
            'caps2',
            'caps3',
            'caps4',
            'reserved2'
            ]
    class FormatException(Exception):
        pass
    # https://msdn.microsoft.com/de-de/library/windows/desktop/bb943982(v=vs.85).aspx
    extension = 'dds'
    has_header = True
    def __init__( self, data, is_normal_map=False ):
        super().__init__( data )
        self.magic = data[0:4]
        assert( self.magic == self.DDSMAGIC )
        Header = namedtuple( 'Header', self.HEADER_FIELDS )
        self.header = Header._make(unpack('31I',data[1*4:32*4]))
        self.size = ( int(self.header.width), int(self.header.height) )
        self.is_normal_map = is_normal_map
        self.has_uncompressed_rgb_data = self.header.ppf_flags & self.PPF_FLAGS['DDPF_RGB']
        self.is_DXT5 = self.header.ppf_four_cc == 894720068
        self.mip_map_infos = [ (128,self.size) ]
        if self.has_uncompressed_rgb_data:
            self.depth = self.header.ppf_rgb_bit_count
            pixel_bytes = self.depth//8
        else:
            pixel_bytes = 1
        for mip_map_level in range(1,self.header.mip_map_count):
            previous_offset, previous_size = self.mip_map_infos[mip_map_level-1]
            previous_data_size = previous_size[0]*previous_size[1]*pixel_bytes
            _size = ( previous_size[0] // 2, previous_size[1] // 2 )
            self.mip_map_infos.append( (previous_offset+previous_data_size,_size ) )

    def get_block( self, x, y, mip_map_level ):
        if not self.is_DXT5:
            raise self.FormatException()
        mip_map_offset, mip_map_size = self.mip_map_infos[mip_map_level]
        block_offset = mip_map_offset + ( mip_map_size[0]//4 * int(y) + int(x) ) * 16
        pixel_offset = int(y)*4 + int(x)
        a0 = self.data[block_offset+0]
        a1 = self.data[block_offset+1]
        pixel_alphas = sum([ self.data[block_offset+2+i] << i*8 for i in range(6) ])
        pixel_alphas = [ ( pixel_alphas & ( 7 << i*3 )) >> i*3 for i in range(16) ]
        c0 = self.data[block_offset+8:block_offset+10]
        c1 = self.data[block_offset+10:block_offset+12]
        pixel_colors = sum([ self.data[block_offset+12+i] << i*8 for i in range(4) ])
        pixel_colors = [ ( pixel_colors & ( 3 << i*2 )) >> i*2 for i in range(16) ]
        return ( a0, a1, pixel_alphas, c0, c1, pixel_colors )
    def set_block( self, x, y, mip_map_level, data, update_pallets=True ):
        if not self.is_DXT5:
            raise self.FormatException()
        mip_map_offset, mip_map_size = self.mip_map_infos[mip_map_level]
        block_offset = mip_map_offset + ( mip_map_size[0]//4 * int(y) + int(x) ) * 16
        pixel_offset = int(y)*4 + int(x)
        ( a0, a1, pixel_alphas, c0, c1, pixel_colors ) = data
        if update_pallets:
            self.data[block_offset+0] = a0
            self.data[block_offset+1] = a1
        pixel_alphas = sum([ pixel_alphas[i] << i*3 for i in range(16) ])
        self.data[block_offset+2:block_offset+8] = bytes([ ( pixel_alphas & ( 0xff << i*8 ) ) >> i*8 for i in range(6) ])
        if update_pallets:
            self.data[block_offset+8:block_offset+10] = c0
            self.data[block_offset+10:block_offset+12] = c1
        pixel_colors = sum([ pixel_colors[i] << i*2 for i in range(16) ])
        self.data[block_offset+12:block_offset+16] = bytes([ ( pixel_colors & ( 0xff << i*8 ) ) >> i*8 for i in range(4) ])
    def as_grays( self ):
        if not self.has_uncompressed_rgb_data:
            raise self.FormatException()
        pixel_count = self.size[0] * self.size[1]
        channels = [ bytearray(pixel_count) for _ in range(4) ]
        for i in range( pixel_count ):
            pixel = self.data[128+i*4:128+i*4+5]
            for ch in range(4):
                channels[ch][i] = pixel[ch]
        grays = []
        for ch in range(4):
            grays.append( EmbeddedScMapGrayImage( channels[ch], self.size, '8' ) )
        return tuple(grays)
    def from_grays( self, grays ):
        assert( self.has_uncompressed_rgb_data )
        for gray in grays:
         assert( gray.size == self.size and gray.depth == '8' )
        pixel_count = self.size[0] * self.size[1]
        channels = [ bytearray(pixel_count) for _ in range(4) ]
        for i in range( pixel_count ):
            pixel = bytearray(4)
            for ch in range(4):
                pixel[ch] = grays[ch].data[i]
            self.data[128+i*4:128+i*4+5] = pixel
    def as_uncompressed( self ):
        assert( self.is_DXT5 )
        mip_map_count = self.header.mip_map_count
        pixel_bytes = 4
        new_size = self.size[0] * self.size[1] * pixel_bytes + 128
        last_size = self.size[0] * self.size[1] * pixel_bytes
        new_offsets = [128]
        for mip_map_level in range(1,max(mip_map_count,1)):
            new_offsets.append( new_size )
            last_size = last_size // 4
            new_size += last_size
        new_data = bytearray( new_size )
        x_blocks = self.size[0] // 4
        y_blocks = self.size[1] // 4
        in_block_iter = [(x,y) for x in range(4) for y in range(4)]
        for mip_map_level in range(max(mip_map_count,1)):
            blocks_size = ( x_blocks, y_blocks )
            blocks = [(x,y) for x in range(blocks_size[0]) for y in range(blocks_size[1])]
            current_offset = new_offsets[ mip_map_level ]
            mip_map_size = ( x_blocks*4, y_blocks*4 )
            for block in blocks:
                block_pos_x, block_pos_y = block
                block_data = list(self.get_block( block_pos_x, block_pos_y, mip_map_level ))
                pixels_color = EmbeddedScMapDDSImage.unpack_color( block_data )
                pixels_alpha = EmbeddedScMapDDSImage.unpack_alpha( block_data )
                for in_x, in_y in in_block_iter:
                    x = in_x + block_pos_x * 4
                    y = in_y + block_pos_y * 4
                    if x >= mip_map_size[0] or y >= mip_map_size[1]:
                        # TODO FIXME remove print
                        print("skip pixel {}x{}".format(x,y))
                        continue
                    absolute_pixel_address = mip_map_size[0] * y * pixel_bytes + x * pixel_bytes + current_offset
                    block_pixel_index = in_y*4 + in_x
                    pixel_color = pixels_color[block_pixel_index]
                    pixel_alpha = pixels_alpha[block_pixel_index]
                    if pixel_bytes == 4:
                        new_data[absolute_pixel_address:absolute_pixel_address+4] = [
                            round(pixel_color[2]),
                            round(pixel_color[1]),
                            round(pixel_color[0]),
                            round(pixel_alpha),
                            ]
                    else:
                        assert(False)

            x_blocks //= 2
            y_blocks //= 2
        # magic, header size
        new_data[0:8] = self.data[0:8]
        # flags: ['DDSD_CAPS', 'DDSD_HEIGHT', 'DDSD_WIDTH', 'DDSD_PITCH', 'DDSD_PIXELFORMAT']
        new_data[8:12] = pack('I', 135183 )
        # height, width
        new_data[12:20] = self.data[12:20]
        # pitch_or_linear_size
        new_data[20:24] = pack('I', self.header.width * pixel_bytes )
        # mip_map_count
        new_data[28:32] = pack('I', mip_map_count )
        # ppf_header_size
        new_data[76:80] = pack('I', 32 )
        # ppf_flags: ['DDPF_ALPHAPIXELS', 'DDPF_RGB']
        new_data[80:84] = pack('I', 65 )
        # ppf_rgb_bit_count
        new_data[88:92] = pack('I', 32 )
        # ppf_red_bit_mask
        new_data[92:96] = pack('I', 255 << 16 )
        # ppf_green_bit_mask
        new_data[96:100] = pack('I', 255 << 8 )
        # ppf_blue_bit_mask
        new_data[100:104] = pack('I', 255 << 0 )
        # ppf_alpha_bit_mask
        new_data[104:108] = pack('I', 255 << 24 )
        # caps
        new_data[108:112] = self.data[108:112]

        new_image = EmbeddedScMapDDSImage( new_data, self.is_normal_map )
        return new_image

    def debug_print( self ):
        def get_active_keys( keys_value_map, bitmap ):
            l=[]
            for k in keys_value_map:
                if bitmap & keys_value_map[k]:
                    l.append(k)
            return l
        print(self.header)
        print("flags: {}".format( get_active_keys( self.FLAGS, self.header.flags )))
        print("ppf_flags: {}".format( get_active_keys( self.PPF_FLAGS, self.header.ppf_flags )))
        print("caps: {}".format( get_active_keys( self.CAPS, self.header.caps )))
        print("caps2: {}".format( get_active_keys( self.CAPS2, self.header.caps2 )))

    def unpack_alpha( block ):
        alpha_pixels = []
        a0, a1 = block[0:2]
        for idx in block[2]:
            if idx == 0:
                alpha_pixels.append( a0 )
            elif idx == 1:
                alpha_pixels.append( a1 )
            elif idx == 2:
                alpha_pixels.append( ((4*a0+1*a1)/5) if a0 <= a1 else ((6*a0+1*a1)/7) )
            elif idx == 3:
                alpha_pixels.append( ((3*a0+2*a1)/5) if a0 <= a1 else ((5*a0+2*a1)/7) )
            elif idx == 4:
                alpha_pixels.append( ((2*a0+3*a1)/5) if a0 <= a1 else ((4*a0+3*a1)/7) )
            elif idx == 5:
                alpha_pixels.append( ((1*a0+4*a1)/5) if a0 <= a1 else ((3*a0+4*a1)/7) )
            elif idx == 6:
                alpha_pixels.append( 0 if a0 <= a1 else ((2*a0+5*a1)/7) )
            elif idx == 7:
                alpha_pixels.append( 255 if a0 <= a1 else ((1*a0+6*a1)/7) )
            else:
                raise Exception("Some wired stuff happend")
        return alpha_pixels
    def unpack_color( block ):
        color_pixels = []
        c0, c1 = ( unpack('H',block[3])[0], unpack('H',block[4])[0] )
        r0, r1 = ( ( c0 >> 11 ) & 31, ( c1 >> 11 ) & 31 )
        g0, g1 = ( ( c0 >> 5 ) & 63, ( c1 >> 5 ) & 63 )
        b0, b1 = ( c0 & 31, c1 & 31 )
        # normalize to 8 bit
        r0, r1 = ( r0*8, r1*8 )
        g0, g1 = ( g0*4, g1*4 )
        b0, b1 = ( b0*8, b1*8 )
        for idx in block[5]:
            if idx == 0:
                color_pixels.append( [r0, g0, b0] )
            elif idx == 1:
                color_pixels.append( [r1, g1, b1] )
            elif idx == 2:
                color_pixels.append(
                    [
                        (r0+r1)/2,
                        (g0+g1)/2,
                        (b0+b1)/2
                    ] if ( r0, g0, b0 ) <= ( r1, g1, b1 ) else
                    [
                        (2*r0+1*r1)/3,
                        (2*g0+1*g1)/3,
                        (2*b0+1*b1)/3
                    ] )
            elif idx == 3:
                color_pixels.append(
                    [
                        0,
                        0,
                        0
                    ] if ( r0, g0, b0 ) <= ( r1, g1, b1 ) else
                    [
                        (1*r0+2*r1)/3,
                        (1*g0+2*g1)/3,
                        (1*b0+2*b1)/3
                    ] )
            else:
                raise Exception("Some wired stuff happend")
        return color_pixels
    def pack_alpha( pixels ):
        try:
            new_a0 = min([ color for color in pixels if color != 0 ])
            new_a1 = max([ color for color in pixels if color != 0 and color != 255 ])
        except ValueError as e:
            new_a0 = 0
            new_a1 = 0
        packed_pixels = []
        pallet = [
            new_a0,
            new_a1,
            ((4*new_a0+1*new_a1)/5),
            ((3*new_a0+2*new_a1)/5),
            ((2*new_a0+3*new_a1)/5),
            ((1*new_a0+4*new_a1)/5) ]
        for color in pixels:
            if color == 0:
                packed_pixels.append(6)
            elif color == 255:
                packed_pixels.append(7)
            else:
                min_diff = 1024
                closest_match = -1
                for idx in range(len(pallet)):
                    diff = abs(color-pallet[idx])
                    if diff <= min_diff:
                        closest_match = idx
                        min_diff = diff
                if closest_match == -1:
                    raise Exception("Some wired stuff happend")
                packed_pixels.append( closest_match )
        return ( int(new_a0), int(new_a1), packed_pixels )
    def pack_color( pixels ):
        packed_color_pixels = []
        new_c0 = min(pixels)
        new_c1 = max(pixels)
        pallet = [
            new_c0,
            new_c1,
            (
                (2*new_c0[0]+1*new_c1[0])/3,
                (2*new_c0[1]+1*new_c1[1])/3,
                (2*new_c0[2]+1*new_c1[2])/3,
            ),
            (
                (1*new_c0[0]+2*new_c1[0])/3,
                (1*new_c0[1]+2*new_c1[1])/3,
                (1*new_c0[2]+2*new_c1[2])/3,
            ) if new_c0 > new_c1 else ( 0, 0, 0 )
            ]
        for color in pixels:
            min_diff = 65536
            closest_match = -1
            for idx in range(len(pallet)):
                prioritize_green_factor = 1
                diff = abs(color[0]-pallet[idx][0]) + abs(color[1]-pallet[idx][1])*prioritize_green_factor + abs(color[2]-pallet[idx][2])
                if diff <= min_diff:
                    closest_match = idx
                    min_diff = diff
            if closest_match == -1:
                raise Exception("Some wired stuff happend")
            packed_color_pixels.append( closest_match )
        return (
            pack('H',
                ( int(new_c0[0]/4) & 31 ) << 11 |
                ( int(new_c0[1]/4) & 63 ) << 5 |
                ( int(new_c0[2]/4) & 31 )
            ),
            pack('H',
                ( int(new_c1[0]/4) & 31 ) << 11 |
                ( int(new_c1[1]/4) & 63 ) << 5 |
                ( int(new_c1[2]/4) & 31 )
            ),
            packed_color_pixels
            )

def read_scmap( scmap_path, debug_print_enabled=False ):

    def debug_print( label, text ):
        if debug_print_enabled:
            print("{}: {}".format(label,text))

    infos = {'offsets': {}, 'images': {}}
    listOfDebugProps = []
    with open( scmap_path, 'rb' ) as scmap:

        scmapMagic = scmap.read(4)
        if scmapMagic != SCMAPMAGIC:
            raise MapParsingException( "file magic", scmap )

        fileVersionMajor = unpack('I', scmap.read(4) )[0]
        if not fileVersionMajor:
            raise MapParsingException( "file major version", scmap )
        debug_print( "fileVersionMajor", fileVersionMajor )

        # always 0xbeeffeed and other always 2
        (unknown3,unknown4) = ( scmap.read(4), scmap.read(4) )
        debug_print( "unknown3", unknown3 )
        debug_print( "unknown4", unknown4 )

        (scaledMapWidth,scaledMapHeight) = unpack('ff', scmap.read(calcsize('ff')) )
        if not scaledMapWidth or not scaledMapHeight:
            raise MapParsingException( "scaled map size", scmap )
        debug_print( "scaledMapWidth", scaledMapWidth )
        debug_print( "scaledMapHeight", scaledMapHeight )

        # always 0
        (unknown5,unknown6) = ( scmap.read(4), scmap.read(2) )
        debug_print( "unknown5", unknown5 )
        debug_print( "unknown6", unknown6 )

        #######################################################################
        ### Preview Image
        #######################################################################

        infos['offsets']['preview_start'] = scmap.tell()
        infos['offsets']['preview_length_prefix'] = True
        preview_data_length = unpack('I', scmap.read(4) )[0]
        if not preview_data_length:
            raise MapParsingException( "preview image data length", scmap )
        preview_data = scmap.read(preview_data_length)
        infos['offsets']['preview_end'] = scmap.tell()
        infos['images']['preview'] = EmbeddedScMapDDSImage( preview_data )
        if len(preview_data) != preview_data_length:
            raise MapParsingException( "preview image data ({} bytes)".format(preview_data_length), scmap )
        debug_print( "preview_data_length", "{} bytes".format(preview_data_length) )
        debug_print( "preview_dataMagic", preview_data[0:4].decode( ))
        if preview_data[0:4] != DDSMAGIC:
            raise MapParsingException( "wrong magic bytes in preview data", scmap )

        #######################################################################
        ### File Version
        #######################################################################

        file_version_minor = unpack('I', scmap.read(4) )[0]
        if not file_version_minor:
            raise MapParsingException( "file minor version", scmap )
        debug_print( "file_version_minor", file_version_minor )

        if file_version_minor not in [60, 59, 56, 53]:
            raise MapParsingException( "unsupported file minor version", scmap )

        #######################################################################

        map_size = (map_width,map_height) = unpack('II', scmap.read(8) )
        if not map_width or not map_height:
            raise MapParsingException( "map size", scmap )
        debug_print( "map_width", map_width )
        debug_print( "map_height", map_height )
        infos['map_size'] = map_size
        half_map_size = (int(map_size[0]/2),int(map_size[1]/2))

        #######################################################################
        ### Height Map
        #######################################################################

        # Height Scale, usually 1/128
        heightScale = unpack('f', scmap.read(4) )[0]
        debug_print( "heightScale", heightScale )

        height_map_data_length = ( map_height + 1 ) * ( map_width + 1 ) * calcsize('h')
        infos['offsets']['height_map_start'] = scmap.tell()
        infos['offsets']['height_map_length_prefix'] = False
        height_map_data = scmap.read(height_map_data_length)
        infos['offsets']['height_map_end'] = scmap.tell()

        infos['images']['height_map'] = EmbeddedScMapGrayImage( height_map_data, (map_width+1,map_height+1), '16' )

        #######################################################################
        ### Some Shader
        #######################################################################

        if file_version_minor >= 56:
            unknown7 = read_c_string(scmap)
            debug_print( "unknown7", unknown7 )

        terrain = read_c_string(scmap)
        debug_print( "terrain", terrain )

        texPathBackground = read_c_string(scmap)
        debug_print( "texPathBackground", texPathBackground )

        texPathSkyCubemap = read_c_string(scmap)
        debug_print( "texPathSkyCubemap", texPathSkyCubemap )

        if file_version_minor < 56:

            texPathEnvCubemap = read_c_string(scmap)
            debug_print( "texPathEnvCubemap", texPathEnvCubemap )

        elif file_version_minor >= 56:

            environmentLookupTexturesCount = unpack('I', scmap.read(4) )[0]
            debug_print( "environmentLookupTexturesCount", environmentLookupTexturesCount )

            for i in range(environmentLookupTexturesCount):
                environmentLookupTexturesLabel = read_c_string(scmap)
                debug_print( "environmentLookupTexturesLabel", environmentLookupTexturesLabel )
                environmentLookupTexturesFile = read_c_string(scmap)
                debug_print( "environmentLookupTexturesFile", environmentLookupTexturesFile )

        #######################################################################
        ### Render Settings
        #######################################################################

        lightingMultiplier = unpack('f', scmap.read(4) )[0]
        debug_print( "lightingMultiplier", lightingMultiplier )

        lightDirection = unpack('fff', scmap.read(12) )
        debug_print( "lightDirection", lightDirection )

        ambienceLightColor = unpack('fff', scmap.read(12) )
        debug_print( "ambienceLightColor", ambienceLightColor )

        lightColor = unpack('fff', scmap.read(12) )
        debug_print( "lightColor", lightColor )

        shadowFillColor = unpack('fff', scmap.read(12) )
        debug_print( "shadowFillColor", shadowFillColor )

        specularColor = unpack('ffff', scmap.read(16) )
        debug_print( "specularColor", specularColor )

        bloom = unpack('f', scmap.read(4) )[0]
        debug_print( "bloom", bloom )

        fogColor = unpack('fff', scmap.read(12) )
        debug_print( "fogColor", fogColor )

        fogStart = unpack('f', scmap.read(4) )[0]
        debug_print( "fogStart", fogStart )

        fogEnd = unpack('f', scmap.read(4) )[0]
        debug_print( "fogEnd", fogEnd )

        hasWater = unpack('c', scmap.read(1) )[0]
        debug_print( "hasWater", hasWater )

        waterElevation = unpack('f', scmap.read(4) )[0]
        debug_print( "waterElevation", waterElevation )

        waterElevationDeep = unpack('f', scmap.read(4) )[0]
        debug_print( "waterElevationDeep", waterElevationDeep )

        waterElevationAbyss = unpack('f', scmap.read(4) )[0]
        debug_print( "waterElevationAbyss", waterElevationAbyss )


        surfaceColor = unpack('fff', scmap.read(12) )
        debug_print( "surfaceColor", surfaceColor )

        colorLerpMin = unpack('f', scmap.read(4) )[0]
        debug_print( "colorLerpMin", colorLerpMin )

        colorLerpMax = unpack('f', scmap.read(4) )[0]
        debug_print( "colorLerpMax", colorLerpMax )

        refraction = unpack('f', scmap.read(4) )[0]
        debug_print( "refraction", refraction )

        fresnelBias = unpack('f', scmap.read(4) )[0]
        debug_print( "fresnelBias", fresnelBias )

        fresnelPower = unpack('f', scmap.read(4) )[0]
        debug_print( "fresnelPower", fresnelPower )

        reflectionUnit = unpack('f', scmap.read(4) )[0]
        debug_print( "reflectionUnit", reflectionUnit )

        reflectionSky = unpack('f', scmap.read(4) )[0]
        debug_print( "reflectionSky", reflectionSky )

        sunShininess = unpack('f', scmap.read(4) )[0]
        debug_print( "sunShininess", sunShininess )

        sunStrength = unpack('f', scmap.read(4) )[0]
        debug_print( "sunStrength", sunStrength )

        sunGlow = unpack('f', scmap.read(4) )[0]
        debug_print( "sunGlow", sunGlow )

        unknown8 = unpack('f', scmap.read(4) )[0]
        debug_print( "unknown8", unknown8 )

        unknown9 = unpack('f', scmap.read(4) )[0]
        debug_print( "unknown9", unknown9 )

        sunColor = unpack('fff', scmap.read(12) )
        debug_print( "sunColor", sunColor )

        reflectionSun = unpack('f', scmap.read(4) )[0]
        debug_print( "reflectionSun", reflectionSun )

        unknown10 = unpack('f', scmap.read(4) )[0]
        debug_print( "unknown10", unknown10 )

        ### Texture Maps

        texPathWaterCubemap = read_c_string(scmap)
        debug_print( "texPathWaterCubemap", texPathWaterCubemap )

        texPathWaterRamp = read_c_string(scmap)
        debug_print( "texPathWaterRamp", texPathWaterRamp )

        for i in range(4):
            debug_print( "waveTexture", i )
            normalsFrequency = unpack('f', scmap.read(4) )[0]
            debug_print( "normalsFrequency", normalsFrequency )

        for i in range(4):
            debug_print( "waveTexture", i )
            waveTextureScaleX = unpack('f', scmap.read(4) )[0]
            debug_print( "waveTextureScaleX", waveTextureScaleX )
            waveTextureScaleY = unpack('f', scmap.read(4) )[0]
            debug_print( "waveTextureScaleY", waveTextureScaleY )
            waveTexturePath = read_c_string(scmap)
            debug_print( "waveTexturePath", waveTexturePath )

        waveGeneratorCount = unpack('I', scmap.read(4) )[0]
        debug_print( "waveGeneratorCount", waveGeneratorCount )
        for i in range(waveGeneratorCount):
            debug_print( "waveGenerator", i )
            textureName = read_c_string(scmap)
            debug_print( "textureName", textureName )
            rampName = read_c_string(scmap)
            debug_print( "rampName", rampName )
            position = unpack('fff', scmap.read(12) )
            debug_print( "position", position )
            rotation = unpack('f', scmap.read(4) )[0]
            debug_print( "rotation", rotation )
            velocity = unpack('fff', scmap.read(12) )
            debug_print( "velocity", velocity )
            lifetimeFirst = unpack('f', scmap.read(4) )[0]
            debug_print( "lifetimeFirst", lifetimeFirst )
            lifetimeSecond = unpack('f', scmap.read(4) )[0]
            debug_print( "lifetimeSecond", lifetimeSecond )
            periodFirst = unpack('f', scmap.read(4) )[0]
            debug_print( "periodFirst", periodFirst )
            periodSecond = unpack('f', scmap.read(4) )[0]
            debug_print( "periodSecond", periodSecond )
            scaleFirst = unpack('f', scmap.read(4) )[0]
            debug_print( "scaleFirst", scaleFirst )
            scaleSecond = unpack('f', scmap.read(4) )[0]
            debug_print( "scaleSecond", scaleSecond )
            frameCount = unpack('f', scmap.read(4) )[0]
            debug_print( "frameCount", frameCount )
            frameRateFirst = unpack('f', scmap.read(4) )[0]
            debug_print( "frameRateFirst", frameRateFirst )
            frameRateSecond = unpack('f', scmap.read(4) )[0]
            debug_print( "frameRateSecond", frameRateSecond )
            stripCount = unpack('f', scmap.read(4) )[0]
            debug_print( "stripCount", stripCount )

        if file_version_minor >= 59:
            unkownData12 = scmap.read(28)
            debug_print( "unkownData12", unkownData12.hex( ))
        elif file_version_minor > 53:
            unkownData12 = scmap.read(24)
            debug_print( "unkownData12", unkownData12.hex( ))
        else:
            noTileset = read_c_string(scmap)
            debug_print( "noTileset", noTileset )


        if file_version_minor > 53:

            strata = ['LowerStratum','Stratum1','Stratum2','Stratum3','Stratum4','Stratum5','Stratum6','Stratum7','Stratum8','UpperStratum']
            debug_print( "strata", strata )

            for stratum in strata:
                debug_print( "stratum", stratum )
                albedoFile = read_c_string(scmap)
                debug_print( "albedoFile", albedoFile )
                albedoScale = unpack('f', scmap.read(4) )[0]
                debug_print( "albedoScale", albedoScale )

            for stratum in strata:
                # fucking special cases
                if stratum == 'UpperStratum':
                    # no Normal for UpperStratum
                    continue
                debug_print( "stratum", stratum )
                normalFile = read_c_string(scmap)
                debug_print( "normalFile", normalFile )
                normalScale = unpack('f', scmap.read(4) )[0]
                debug_print( "normalScale", normalScale )

        else:

            strataCount = unpack('I', scmap.read(4) )[0]
            debug_print( "strataCount", strataCount )
            for stratum in range(strataCount):
                debug_print( "stratum", stratum )
                albedoFile = read_c_string(scmap)
                debug_print( "albedoFile", albedoFile )
                normalFile = read_c_string(scmap)
                debug_print( "normalFile", normalFile )
                albedoScale = unpack('f', scmap.read(4) )[0]
                debug_print( "albedoScale", albedoScale )
                normalScale = unpack('f', scmap.read(4) )[0]
                debug_print( "normalScale", normalScale )

        unknown13 = unpack('I', scmap.read(4) )[0]
        debug_print( "unknown13", unknown13 )

        unknown14 = unpack('I', scmap.read(4) )[0]
        debug_print( "unknown14", unknown14 )

        #######################################################################
        ### Decals
        #######################################################################

        infos['offsets']['decals_start'] = scmap.tell()

        decalsCount = unpack('I', scmap.read(4) )[0]
        debug_print( "decalsCount", decalsCount )

        decals = []
        for decalIndex in range(decalsCount):

            decalId = unpack('I', scmap.read(4) )[0]
            debug_print( "decalId", decalId )

            # albedo(1), normals(2)
            decalType = unpack('I', scmap.read(4) )[0]
            debug_print( "decalType", decalType )

            unknown15 = unpack('I', scmap.read(4) )[0]
            debug_print( "unknown15", unknown15 )

            decalsTexture1PathLength = unpack('I', scmap.read(4) )[0]
            debug_print( "decalsTexture1PathLength", decalsTexture1PathLength )

            if decalsTexture1PathLength > 1024:
                raise MapParsingException( "decalsTexture1PathLength", scmap )

            decalsTexture1Path = scmap.read(decalsTexture1PathLength)
            debug_print( "decalsTexture1Path", decalsTexture1Path )

            decalsTexture2PathLength = unpack('I', scmap.read(4) )[0]
            debug_print( "decalsTexture2PathLength", decalsTexture2PathLength )

            if decalsTexture2PathLength > 1024:
                raise MapParsingException( "decalsTexture2PathLength", scmap )

            if decalsTexture2PathLength > 0:
                decalsTexture2Path = scmap.read(decalsTexture2PathLength)
                debug_print( "decalsTexture2Path", decalsTexture2Path )
            else:
                decalsTexture2Path = b''

            scale = unpack('fff', scmap.read(12) )
            debug_print( "scale", scale )

            position = unpack('fff', scmap.read(12) )
            debug_print( "position", position )

            rotation = unpack('fff', scmap.read(12) )
            debug_print( "rotation", rotation )

            cutOffLOD = unpack('f', scmap.read(4) )[0]
            debug_print( "cutOffLOD", cutOffLOD )

            nearCutOffLOD = unpack('f', scmap.read(4) )[0]
            debug_print( "nearCutOffLOD", nearCutOffLOD )

            removeTick = unpack('I', scmap.read(4) )[0]
            debug_print( "removeTick", removeTick )

            decal = [
                decalId,decalType,unknown15,
                decalsTexture1Path,decalsTexture2Path,
                scale,position,rotation,
                cutOffLOD,nearCutOffLOD,removeTick
                ]

            decals.append(decal)

        infos['decals'] = decals

        infos['offsets']['decals_end'] = scmap.tell()

        decalGroupsCount = unpack('I', scmap.read(4) )[0]
        debug_print( "decalGroupsCount", decalGroupsCount )
        for decalGroupIndex in range(decalGroupsCount):
            decalGroupId = unpack('I', scmap.read(4) )[0]
            debug_print( "decalGroupId", decalGroupId )
            decalGroupName = read_c_string(scmap)
            debug_print( "decalGroupName", decalGroupName )
            decalGroupEntriesCount = unpack('I', scmap.read(4) )[0]
            debug_print( "decalGroupEntriesCount", decalGroupEntriesCount )
            for i in range(decalGroupEntriesCount):
                decalGroupEntry = unpack('I', scmap.read(4) )[0]
                debug_print( "decalGroupEntry", decalGroupEntry )

        #######################################################################
        ### Some DDS files
        #######################################################################

        (unknown19Width,unknown19Height) = unpack('II', scmap.read(8) )
        debug_print( "unknown19Width", unknown19Width )
        debug_print( "unknown19Height", unknown19Height )

        # most often 1, sometimes 4
        normalMapsCount = unpack('I', scmap.read(4) )[0]
        debug_print( "normalMapsCount", normalMapsCount )
        for normalMapIndex in range(normalMapsCount):
            name = 'normal_map_{}'.format(normalMapIndex)
            infos['offsets']['{}_start'.format(name)] = scmap.tell()
            infos['offsets']['{}_length_prefix'.format(name)] = True
            normal_map_data_length = unpack('I', scmap.read(4) )[0]
            normal_map_data = scmap.read(normal_map_data_length)
            infos['offsets']['{}_end'.format(name)] = scmap.tell()
            infos['images'][name] = EmbeddedScMapDDSImage( normal_map_data, is_normal_map=True )
            debug_print( "normal_map_data_length", normal_map_data_length )
            debug_print( "normal_map_data", "{}...".format(normal_map_data[:4]) )

        if file_version_minor < 56:
            unknown20 = unpack('I', scmap.read(4) )[0]
            debug_print( "unknown20", unknown20 )

        # Stratum1 to Stratum4
        infos['offsets']['stratum_1to4_start'] = scmap.tell()
        infos['offsets']['stratum_1to4_length_prefix'] = True
        stratum_1to4_data_length = unpack('I', scmap.read(4) )[0]
        debug_print( "stratum_1to4_data_length", stratum_1to4_data_length )
        stratum_1to4_data = scmap.read(stratum_1to4_data_length)
        infos['offsets']['stratum_1to4_end'] = scmap.tell()
        infos['images']['stratum_1to4'] = EmbeddedScMapDDSImage( stratum_1to4_data )
        debug_print( "stratum_1to4_data", "{}...".format(stratum_1to4_data[:4]) )

        if file_version_minor < 56:
            unknown21 = unpack('I', scmap.read(4) )[0]
            debug_print( "unknown21", unknown21 )

        # Stratum5 to Stratum8
        infos['offsets']['stratum_5to8_start'] = scmap.tell()
        infos['offsets']['stratum_5to8_length_prefix'] = True
        stratum_5to8_data_length = unpack('I', scmap.read(4) )[0]
        debug_print( "stratum_5to8_data_length", stratum_5to8_data_length )
        stratum_5to8_data = scmap.read(stratum_5to8_data_length)
        infos['offsets']['stratum_5to8_end'] = scmap.tell()
        infos['images']['stratum_5to8'] = EmbeddedScMapDDSImage( stratum_5to8_data )
        debug_print( "stratum_5to8_data", "dds{}...".format(stratum_5to8_data[:4]) )

        if file_version_minor > 53:
            unknown22 = unpack('I', scmap.read(4) )[0]
            debug_print( "unknown22", unknown22 )

            infos['offsets']['water_brush_start'] = scmap.tell()
            infos['offsets']['water_brush_length_prefix'] = True
            water_brush_data_length = unpack('I', scmap.read(4) )[0]
            water_brush_data = scmap.read(water_brush_data_length)
            infos['offsets']['water_brush_end'] = scmap.tell()
            infos['images']['water_brush'] = EmbeddedScMapDDSImage( water_brush_data )
            debug_print( "water_brush_data_length", water_brush_data_length )
            debug_print( "water_brush_data", "{}...".format(water_brush_data[:4]) )

        someWaterMapLength = int( (map_width / 2) * (map_height / 2) )

        infos['offsets']['water_foam_map_start'] = scmap.tell()
        infos['offsets']['water_foam_map_length_prefix'] = False
        water_foam_map_data = scmap.read(someWaterMapLength)
        infos['offsets']['water_foam_map_end'] = scmap.tell()
        infos['images']['water_foam_map'] = EmbeddedScMapGrayImage( water_foam_map_data, half_map_size, '8' )
        debug_print( "water_foam_map_data", "{}...".format(water_foam_map_data[:4]) )

        infos['offsets']['water_flatness_map_start'] = scmap.tell()
        infos['offsets']['water_flatness_map_length_prefix'] = False
        water_flatness_map_data = scmap.read(someWaterMapLength)
        infos['offsets']['water_flatness_map_end'] = scmap.tell()
        infos['images']['water_flatness_map'] = EmbeddedScMapGrayImage( water_flatness_map_data, half_map_size, '8' )
        debug_print( "water_flatness_map_data", "{}...".format(water_flatness_map_data[:4]) )

        infos['offsets']['water_depth_bias_map_start'] = scmap.tell()
        infos['offsets']['water_depth_bias_map_length_prefix'] = False
        water_depth_bias_map_data = scmap.read(someWaterMapLength)
        infos['offsets']['water_depth_bias_map_end'] = scmap.tell()
        infos['images']['water_depth_bias_map'] = EmbeddedScMapGrayImage( water_depth_bias_map_data, half_map_size, '8' )
        debug_print( "water_depth_bias_map_data", "{}...".format(water_depth_bias_map_data[:4]) )

        terrain_type_data_length = map_width * map_height
        infos['offsets']['terrain_type_start'] = scmap.tell()
        infos['offsets']['terrain_type_length_prefix'] = False
        terrain_type_data = scmap.read(terrain_type_data_length)
        infos['offsets']['terrain_type_end'] = scmap.tell()
        infos['images']['terrain_type'] = EmbeddedScMapGrayImage( terrain_type_data, map_size, '8' )
        debug_print( "terrain_type_data_length", "{}...".format(terrain_type_data_length) )
        debug_print( "terrain_type_data", "{}...".format(terrain_type_data[:4]) )

        if file_version_minor < 53:
            unknown24 = unpack('h', scmap.read(2) )[0]
            debug_print( "unknown24", unknown24 )


        if file_version_minor >= 59:
            unknown25 = scmap.read(64)
            debug_print( "unknown25", unknown25[:4] )
            unknown26String = read_c_string(scmap)
            debug_print( "unknown26String", unknown26String )
            unknown27String = read_c_string(scmap)
            debug_print( "unknown27String", unknown27String )
            unknown28 = unpack('I', scmap.read(4) )[0]
            debug_print( "unknown28", unknown28 )
            unknown28MagicFactor = 40
            if unknown28 > 0:
                unknown29 = scmap.read( unknown28 * unknown28MagicFactor )
                debug_print( "unknown29", unknown29[:4] )
            unknown30 = scmap.read(19)
            debug_print( "unknown30", unknown30 )
            unknown31String = read_c_string(scmap)
            debug_print( "unknown31String", unknown31String )

            unknown31 = scmap.read(88)
            debug_print( "unknown31", unknown31[:4] )

        propsBlockStartOffset = scmap.tell()
        infos["propsBlockStartOffset"] = propsBlockStartOffset
        infos['offsets']['props_start'] = scmap.tell()

        props_count = unpack('I', scmap.read(4) )[0]
        debug_print( "props_count", props_count )

        props = []
        for i in range( props_count ):
            blueprintPath = read_c_string(scmap)
            debug_print( "blueprintPath", blueprintPath )
            position = unpack('fff', scmap.read(12) )
            debug_print( "position", position )
            rotationX = unpack('fff', scmap.read(12) )
            debug_print( "rotationX", rotationX )
            rotationY = unpack('fff', scmap.read(12) )
            debug_print( "rotationY", rotationY )
            rotationZ = unpack('fff', scmap.read(12) )
            debug_print( "rotationZ", rotationZ )
            scale = unpack('fff', scmap.read(12) )
            debug_print( "scale", scale )
            # add this prop to prop to props list
            props.append( [ blueprintPath,position,rotationX,rotationY,rotationZ,scale ] )

        infos["props"] = props + listOfDebugProps

    return infos
