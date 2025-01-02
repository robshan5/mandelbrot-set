from PIL import Image
import colorsys
import math
import os

width = 1000
x = 0
y = 0
numRange = 2.3
aspectRatio = 4/3
precision = 500

height = round( width/aspectRatio )
minx = x-numRange
maxx = x+numRange
miny = y-numRange
maxy = y+numRange

img = Image.new('RGB', (width, height), color = "black")
pixels = img.load()


