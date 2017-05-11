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
    class FormatException(Exception):
        pass
    # https://msdn.microsoft.com/de-de/library/windows/desktop/bb943982(v=vs.85).aspx
    extension = 'dds'
    has_header = True
    def __init__( self, data, is_normal_map=False ):
        super().__init__( data )
        self.flags = unpack('I',data[2*4:3*4])[0]
        self.height = unpack('I',data[3*4:4*4])[0]
        self.width = unpack('I',data[4*4:5*4])[0]
        self.pitch_or_linear_size = unpack('I',data[5*4:6*4])[0]
        self.depth = unpack('I',data[6*4:7*4])[0]
        self.mip_map_count = unpack('I',data[7*4:8*4])[0]
        self.flags2 = unpack('I',data[20*4:21*4])[0]
        self.four_cc = data[21*4:22*4]
        self.rgb_bit_count = unpack('I',data[22*4:23*4])[0]
        self.red_bit_mask = unpack('I',data[23*4:24*4])[0]
        self.green_bit_mask = unpack('I',data[24*4:25*4])[0]
        self.blue_bit_mask = unpack('I',data[25*4:26*4])[0]
        self.alpha_bit_mask = unpack('I',data[26*4:27*4])[0]
        self.caps = unpack('I',data[27*4:28*4])[0]
        self.caps2 = unpack('I',data[28*4:29*4])[0]
        self.caps3 = unpack('I',data[29*4:30*4])[0]
        self.caps4 = unpack('I',data[30*4:31*4])[0]
        #self.debug_print()
        self.size = ( int(self.width), int(self.height) )
        self.is_normal_map = is_normal_map
        self.has_uncompressed_rgb_data = self.flags2 & 0x40
        self.mip_map_infos = [ (128,self.size) ]
        for mip_map_level in range(1,self.mip_map_count):
            previous_offset, previous_size = self.mip_map_infos[mip_map_level-1]
            previous_data_size = previous_size[0]*previous_size[1]
            _size = ( previous_size[0] // 2, previous_size[1] // 2 )
            self.mip_map_infos.append( (previous_offset+previous_data_size,_size ) )
        pixel_count = self.size[0] * self.size[1]
    def get_block( self, x, y, mip_map_level ):
        if self.four_cc != b'DXT5':
            raise self.FormatException()
        mip_map_offset, mip_map_size = self.mip_map_infos[mip_map_level]
        block_offset = mip_map_offset + ( mip_map_size[0]//4 * int(y) + int(x) ) * 16
        pixel_offset = int(y)*4 + int(x)
        a0 = self.data[block_offset+0]
        a1 = self.data[block_offset+1]
        pixel_alphas = sum([ self.data[block_offset+2+i] << i*8 for i in range(6) ])
        pixel_alphas = [ ( pixel_alphas & ( 7 << i*3 )) >> i*3 for i in range(16) ]
        #pixel_alphas = ( pixel_alphas & ( 7 << pixel_offset*3 )) >> pixel_offset*3
        c0 = self.data[block_offset+8:block_offset+10]
        c1 = self.data[block_offset+10:block_offset+12]
        pixel_colors = sum([ self.data[block_offset+12+i] << i*8 for i in range(4) ])
        pixel_colors = [ ( pixel_colors & ( 3 << i*2 )) >> i*2 for i in range(16) ]
        #pixel_colors = ( pixel_colors & ( 3 << pixel_offset*2 ))
        return ( a0, a1, pixel_alphas, c0, c1, pixel_colors )
    def set_block( self, x, y, mip_map_level, data, update_pallets=True ):
        if self.four_cc != b'DXT5':
            raise self.FormatException()
        mip_map_offset, mip_map_size = self.mip_map_infos[mip_map_level]
        block_offset = mip_map_offset + ( mip_map_size[0]//4 * int(y) + int(x) ) * 16
        pixel_offset = int(y)*4 + int(x)
        ( a0, a1, pixel_alphas, c0, c1, pixel_colors ) = data
        if update_pallets:
            self.data[block_offset+0] = a0
            self.data[block_offset+1] = a1
        pixel_alphas = sum([ pixel_alphas[i] << i*3 for i in range(16) ])
        #_pixel_alphas = sum([ self.data[block_offset+2+i] << i*8 for i in range(6) ])
        #pixel_alphas = ( _pixel_alphas & ( 3 << pixel_offset*3 )) | ( pixel_alphas << pixel_offset*3 )
        self.data[block_offset+2:block_offset+8] = bytes([ ( pixel_alphas & ( 0xff << i*8 ) ) >> i*8 for i in range(6) ])
        if update_pallets:
            self.data[block_offset+8:block_offset+10] = c0
            self.data[block_offset+10:block_offset+12] = c1
        pixel_colors = sum([ pixel_colors[i] << i*2 for i in range(16) ])
        #_pixel_colors = sum([ self.data[block_offset+12+i] << i*8 for i in range(4) ])
        #pixel_colors = ( _pixel_colors & ( 3 << pixel_offset*3 )) | ( pixel_colors << pixel_offset*3 )
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
    def debug_print( self ):
        print("{}x{} flags:{:08x} pitch_or_linear_size:{} depth:{} mip_map_count:{} flags2:{:08x} four_cc:{} rgb_bit_count:{} caps:{:08x} caps2:{:08x} caps3:{:08x} caps4:{:08x} red_bit_mask:{:08x} green_bit_mask:{:08x} blue_bit_mask:{:08x} alpha_bit_mask:{:08x} data_size:{}".format(self.width,self.height,self.flags,self.pitch_or_linear_size,self.depth,self.mip_map_count,self.flags2,self.four_cc,self.rgb_bit_count,self.caps,self.caps2,self.caps3,self.caps4,self.red_bit_mask,self.green_bit_mask,self.blue_bit_mask,self.alpha_bit_mask,len(self.data)))

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
