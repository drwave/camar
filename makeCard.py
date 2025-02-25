#!/System/Library/Frameworks/Python.framework/Versions/2.7/bin/python
# /usr/bin/python2.7
import sys, os, argparse
# the "pxr" package is part of the OpenUSD project:
# https://graphics.pixar.com/usd/docs/index.html
# https://github.com/PixarAnimationStudios/USD
#
from pxr import Tf, Sdf, Usd, UsdGeom, UsdShade, Kind
import math
from PIL import Image
'''
    Take image and turn it into a USD texture card.
    The card is oriented such that its origin is in the center bottom
    and the card is upright for a given up vector (i.e. Y-up or Z-up).
    For the card, we want to create the following scopes:
    /<Model>
    /<Model>/Material
    /<Model>/Material/Surface
    /<Model>/Material/uv2st
    /<Model>/Material/Texture
    /<Model>/Mesh
    
    A few other thoughts:
    - put a colored, diffuse-only frame around it
    - put a matte that is some % around the work
    - float the work a bit above the matte
    - make it single-sided
    - so the hierarchy should now replace:
    /<Model>/Mesh
    
    with:
    /<Model>/Frame
    /<Model>/Matte
    /<Model>/Artwork
    
    '''

def makeCard(topLevelName, imgFile, creditFile, width, height, upAxis, stage):
    cardPath = "/" + Tf.MakeValidIdentifier(topLevelName)
    cardSchema = UsdGeom.Xform.Define(stage, cardPath)
    prim = cardSchema.GetPrim()
    stage.SetDefaultPrim(prim)
    # we should also add info about the src image here as well...
    # I think we can add a "comment" which will show up
    prim.SetMetadata(Sdf.PrimSpec.KindKey, Kind.Tokens.component)
    material = makeMaterial(cardPath, imgFile, stage)
    materialBackSq = makeMaterial(cardPath, creditFile, stage)
    # we should replace the following single call with calls to
    # make 3 meshes
    frameW = 1
    makeMesh(cardPath, width, height, upAxis, material, stage)
    makeMatte(cardPath, height, width, upAxis, material, stage)
    makeFrame(cardPath, height, width, upAxis, frameW, material, stage)
    
    makeBackSq(cardPath, height, width, upAxis, frameW, materialBackSq, stage)

def makeMaterial(parentPath, imgFile, stage):
    newName = Tf.MakeValidIdentifier("Material_" + imgFile)
    mPath = os.path.join(parentPath, newName)
    mSchema = UsdShade.Material.Define(stage, mPath)
    mSurface = mSchema.CreateOutput("surface", Sdf.ValueTypeNames.Token)
    diffuseColor = createPreviewSurfaceShader(mPath, mSurface, stage)
    uv = createPrimvarShader(mPath, stage)
    createTextureShader(mPath, imgFile, diffuseColor, uv, stage)
    return Sdf.Path(mPath)

def createPreviewSurfaceShader(parentPath, materialSurface, stage):
    sPath = os.path.join(parentPath, "Surface")
    sSchema = UsdShade.Shader.Define(stage, sPath)
    # is this predefined as a token somewhere? Too fragile...
    sSchema.CreateIdAttr().Set("UsdPreviewSurface")
    sSurface = sSchema.CreateOutput("surface", Sdf.ValueTypeNames.Token)
    materialSurface.ConnectToSource(sSurface)
    sSchema.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
    sSchema.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(0)
    sSchema.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set((0, 0, 0))
    sSchema.CreateInput("clearcoat", Sdf.ValueTypeNames.Float).Set(0.0)
    sSchema.CreateInput("clearcoatRoughness", Sdf.ValueTypeNames.Float).Set(0.01)
    sSchema.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set((0, 0, 0))
    sSchema.CreateInput("displacement", Sdf.ValueTypeNames.Float).Set(0.0)
    sSchema.CreateInput("occlusion", Sdf.ValueTypeNames.Float).Set(1.0)
    sSchema.CreateInput("normal", Sdf.ValueTypeNames.Float3).Set((0, 0, 1))
    sSchema.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.5)
    sSchema.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0)
    sSchema.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.8)
    diffuseColor = sSchema.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f)
    return diffuseColor

def createPrimvarShader(parentPath, stage):
    sPath = os.path.join(parentPath, "uv2st")
    sSchema = UsdShade.Shader.Define(stage, sPath)
    # is this predefined as a token somewhere? Too fragile...
    sSchema.CreateIdAttr().Set("UsdPrimvarReader_float2")
    result = sSchema.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    sSchema.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    return result

def createTextureShader(parentPath, imgFile, diffuseColor, uv, stage):
    # we need to do some introspection on the imgFile, since it might
    # be only greyscale (especially for a scan)
    sPath = os.path.join(parentPath, "Texture")
    sSchema = UsdShade.Shader.Define(stage, sPath)
    # is this predefined as a token somewhere? Too fragile...
    sSchema.CreateIdAttr().Set("UsdUVTexture")
    rgb = sSchema.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    diffuseColor.ConnectToSource(rgb)
    path = Sdf.AssetPath(imgFile)
    sSchema.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(path)
    sSchema.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
    sSchema.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
    st = sSchema.CreateInput("st", Sdf.ValueTypeNames.Float2)
    st.ConnectToSource(uv)

def makeMesh(parentPath, width, height, upAxis, material, stage):
    meshPath = os.path.join(parentPath, "Artwork")
    meshSchema = UsdGeom.Mesh.Define(stage, meshPath)
    vertexCounts = [4]
    meshSchema.CreateFaceVertexCountsAttr().Set(vertexCounts)
    indices = [0, 1, 2, 3]
    meshSchema.GetFaceVertexIndicesAttr().Set(indices)
    meshSchema.GetSubdivisionSchemeAttr().Set("none")
    halfW = width/2.0
    # we want to put the origin of the card in the center 'bottom'
    # this is course depends on what the up axis is:
    if upAxis == 'y' or upAxis == 'Y':
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        points = [(-halfW, 0, 0),
                  (halfW, 0, 0),
                  (halfW, height, 0),
                  (-halfW, height, 0)]
    if upAxis == 'z' or upAxis == 'Z':
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        points = [(-halfW, 0, 0),
                  (halfW, 0, 0),
                  (halfW, 0, height),
                  (-halfW, 0, height)]
    meshSchema.CreatePointsAttr().Set(points)
    uvs = [(0, 0),
           (1, 0),
           (1, 1),
           (0, 1)]
    st = meshSchema.CreatePrimvar("st", Sdf.ValueTypeNames.Float2Array)
    st.Set(uvs)
    st.SetInterpolation(UsdGeom.Tokens.vertex)
    extent = meshSchema.ComputeExtent(points)
    meshSchema.CreateExtentAttr().Set(extent)
    prim = meshSchema.GetPrim()
    relName = "material:binding"
    rel = prim.CreateRelationship(relName)
    rel.AddTarget(material)

# we should make three new functions:
# makeFrame(), makeMatte(), and makeArtwork()

def makeMatte(parentPath, imgHeight, imgWidth, upAxis, material, stage):
    meshPath = os.path.join(parentPath, "Matte")
    meshSchema = UsdGeom.Mesh.Define(stage, meshPath)
    vertexCounts = [4]
    meshSchema.CreateFaceVertexCountsAttr().Set(vertexCounts)
    indices = [0, 1, 2, 3]
    meshSchema.GetFaceVertexIndicesAttr().Set(indices)
    meshSchema.GetSubdivisionSchemeAttr().Set("none")
    # put comment here
    offset = 0.3
    newW = (imgWidth/ 2 + offset)
    newH = imgHeight + offset
    hDiff = -offset
    # we want to put the origin of the card in the center 'bottom'
    # this is course depends on what the up axis is:
    if upAxis == 'y' or upAxis == 'Y':
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        points = [(-newW, hDiff, -offset),
                  (newW, hDiff, -offset),
                  (newW, newH, -offset),
                  (-newW, newH, -offset)]
    if upAxis == 'z' or upAxis == 'Z':
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        points = [(-halfW, -offset, hDiff),
                  (halfW, -offset, hDiff),
                  (halfW, -offset, height),
                  (-halfW, -offset, height)]
    meshSchema.CreatePointsAttr().Set(points)
    uvs = [(0, 0),
           (1, 0),
           (1, 1),
           (0, 1)]
    st = meshSchema.CreatePrimvar("st", Sdf.ValueTypeNames.Float2Array)
    st.Set(uvs)
    st.SetInterpolation(UsdGeom.Tokens.vertex)
    extent = meshSchema.ComputeExtent(points)
    meshSchema.CreateExtentAttr().Set(extent)
    meshSchema.GetDisplayColorAttr().Set( [(1, 1, 1)] )
    meshSchema.CreateDoubleSidedAttr().Set(1)

def makeFrame(parentPath, imgHeight, imgWidth, upAxis, frameW, material, stage):
    meshPath = os.path.join(parentPath, "Frame")
    meshSchema = UsdGeom.Mesh.Define(stage, meshPath)
    vertexCounts = [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4]
    meshSchema.CreateFaceVertexCountsAttr().Set(vertexCounts)
    indices = [0, 1, 5, 4, # top front
               5, 1, 2, 6, # right front
               7, 6, 2, 3, # bottom front
               0, 4, 7, 3, # left front
               9, 8, 12, 13, # bottom back
               9, 13, 14, 10, # left back
               14, 15, 11, 10, # top back
               12, 8, 11, 15, # right back
               8, 0, 3, 11,
               1, 9, 10, 2,
               8, 9, 1, 0,
               3, 2, 10, 11,
               5, 13, 12, 4, # bottom inside
               14, 6, 7, 15, # top inside
               13, 5, 6, 14, # right inside
               4, 12, 15, 7 # left inside
               ]
    meshSchema.GetFaceVertexIndicesAttr().Set(indices)
    meshSchema.GetSubdivisionSchemeAttr().Set("none")
    off1 = 0.3
    inW = (imgWidth/ 2 + off1)
    inH = imgHeight + off1
    inHDiff = -off1
    off2 = -(off1 * 2)

    outW = imgWidth /2 + frameW
    outH = imgHeight + frameW
    outHDiff = -frameW
    addZ = 0.4
    
    # we want to put the origin of the card in the center 'bottom'
    # this is course depends on what the up axis is:
    
    if upAxis == 'y' or upAxis == 'Y':
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        points = [(-outW, outHDiff, -off1 + addZ), #0
                  (outW, outHDiff, -off1 + addZ), #1
                  (outW, outH, -off1 + addZ),      #2
                  (-outW, outH, -off1 + addZ),     #3

                  (-inW, inHDiff, -off1 + addZ),   #4
                  (inW, inHDiff, -off1 + addZ),    #5
                  (inW, inH, -off1 + addZ),        #6
                  (-inW, inH, -off1 + addZ),       #7

                  (-outW, outHDiff, -off1 - off1), #8
                  (outW, outHDiff, -off1 - off1),  #9
                  (outW, outH, -off1 - off1),       #10
                  (-outW, outH, -off1 - off1),      #11

                  (-inW, inHDiff, -off1- off1),     #12
                  (inW, inHDiff, -off1 - off1),     #13
                  (inW, inH, -off1 - off1),         #14
                  (-inW, inH, -off1 - off1)]      #15
    if upAxis == 'z' or upAxis == 'Z':
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        points = [(-outW, -off1 + addZ, outHDiff), #0
                  (outW, -off1 + addZ, outHDiff), #1
                  (outW, -off1 + addZ, outH),      #2
                  (-outW, -off1 + addZ, outH),     #3
                  
                  (-inW, -off1 + addZ, inHDiff),   #4
                  (inW, -off1 + addZ, inHDiff),    #5
                  (inW,  -off1 + addZ, inH),        #6
                  (-inW,  -off1 + addZ, inH),       #7
                  
                  (-outW, -off1 - off1, outHDiff), #8
                  (outW,  -off1 - off1, outHDiff),  #9
                  (outW,  -off1 - off1, outH),       #10
                  (-outW, -off1 - off1, outH),      #11
                  
                  (-inW, -off1- off1, inHDiff),     #12
                  (inW,  -off1- off1, inHDiff),   #13
                  (inW, -off1 - off1, inH),         #14
                  (-inW, -off1 - off1, inH)]      #15
    meshSchema.CreatePointsAttr().Set(points)
    uvs = [(0, 0),
           (1, 0),
           (1, 1),
           (0, 1)]
    st = meshSchema.CreatePrimvar("st", Sdf.ValueTypeNames.Float2Array)
    st.Set(uvs)
    st.SetInterpolation(UsdGeom.Tokens.vertex)
    extent = meshSchema.ComputeExtent(points)
    meshSchema.CreateExtentAttr().Set(extent)
    meshSchema.GetDisplayColorAttr().Set( [(1, 0, 0)] )

def makeBackSq(parentPath, imgHeight, imgWidth, upAxis, frameW, materialBackSq, stage):
    meshPath = os.path.join(parentPath, "BackSq")
    meshSchema = UsdGeom.Mesh.Define(stage, meshPath)
    vertexCounts = [4]
    meshSchema.CreateFaceVertexCountsAttr().Set(vertexCounts)
    indices = [2, 3, 0, 1]
    meshSchema.GetFaceVertexIndicesAttr().Set(indices)
    meshSchema.GetSubdivisionSchemeAttr().Set("none")
    # put comment here
    offset = -0.6
    sqSide = min(imgHeight, imgWidth)
    # we want to put the origin of the card in the center 'bottom'
    # this is course depends on what the up axis is:
    if upAxis == 'y' or upAxis == 'Y':
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
        points = [(-sqSide /2, sqSide + frameW, offset),
                  (sqSide /2, sqSide + frameW, offset),
                  (sqSide/2, frameW, offset),
                  (-sqSide /2, frameW, offset)]
    if upAxis == 'z' or upAxis == 'Z':
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        points =[(-sqSide /2, offset, sqSide + frameW),
                 (sqSide /2, offset, sqSide + frameW),
                 (sqSide/2, offset, frameW),
                 (-sqSide /2, offset, frameW)]
    meshSchema.CreatePointsAttr().Set(points)
    uvs = [(1, 1),
           (0, 1),
           (0, 0),
           (1, 0)]
    st = meshSchema.CreatePrimvar("st", Sdf.ValueTypeNames.Float2Array)
    st.Set(uvs)
    st.SetInterpolation(UsdGeom.Tokens.vertex)
    extent = meshSchema.ComputeExtent(points)
    meshSchema.CreateExtentAttr().Set(extent)
    meshSchema.GetDisplayColorAttr().Set( [(1, 1, 1)] )
    if materialBackSq != None:
        prim = meshSchema.GetPrim()
        relName = "material:binding"
        rel = prim.CreateRelationship(relName)
        rel.AddTarget(materialBackSq)

def main(argv):

    # set some reasonable defaults
    creditFile = None
    upAxis = "Y"
    artHeight = 30.0
    out = "card.usda"
    
    # setup our arguments - we need an input image, everything else is optional
    parser = argparse.ArgumentParser()
    parser.add_argument("imgFile",
                        help="image to turn into a USD card")
    parser.add_argument("-c", "--creditFile", help="image to turn into the back square credit card")
    parser.add_argument("-u", "--upAxis",
                        help="Y or Z",
                        default=upAxis)
    parser.add_argument("--height",
                        help="height of resulting card in base units (cm)",
                        default=artHeight)
    parser.add_argument( "-o", "--out", "--outputFileName",
                    help="prefix of USD file that will be generated (i.e. don't add the extension, we will)",
                        default=out)
                        
    args = parser.parse_args()
    
    if args.height != None:
        artHeight = float(args.artHeight)
    if args.upAxis != None:
        upAxis = args.upAxis
    if args.creditFile != None:
        creditFile = args.creditFile
    if args.outputFileName != None:
        out = args.outputFileName

    # should check if there is already extension on this, and only add if not
    prefix = os.path.basename(args.outputFileName)
    fileName = prefix + ".usda"
    outStage = Usd.Stage.CreateNew(fileName)
    if not outStage:
        sys.exit("Error: Could not open new USD file %s" % fileName)

    print "making USD file", fileName
    with Image.open(args.imgFile) as i:
        (pixelsWide, pixelsHigh) = i.size
        print "image: ", i
        print "image is ", pixelsWide, " x ", pixelsHigh
        aspectRatio = float(pixelsWide)/float(pixelsHigh)
        width = artHeight * aspectRatio
        makeCard(prefix, args.imgFile, creditFile, width, artHeight, upAxis, outStage)
        outStage.Save()
        exit(0)
    print "Unable to open image file ", args.imgFile
    exit(-1)

if __name__ == "__main__":
    main(sys.argv[1:])

