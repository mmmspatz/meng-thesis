#!/usr/bin/env python3
import argparse
import cairo
import xml.etree.ElementTree as ET
import svg.path
import matplotlib.pyplot as plt
import scipy.io
import io
import scipy.ndimage
import math

namespaces = {'svg':'http://www.w3.org/2000/svg'}

def draw_filled_ellipse(cr, center, width, height, color=(0,0,0), angle=0):
    cr.save()
    cr.set_source_rgb(color[0],color[1],color[2])
    cr.translate(center.real,center.imag)
    cr.rotate(angle)
    cr.scale(width*72 / 2.0, height*72 / 2.0)
    cr.new_path()
    cr.arc(0.0, 0.0, 1.0, 0.0, 2.0 * 3.14159)
    cr.close_path()
    cr.fill()
    cr.restore()

def draw_path(ctx,path,linewidth,color=(0,0,0)):

    ctx.new_path()
    ctx.move_to(path[0].start.real,path[0].start.imag)
    for segment in path:
        if segment.__class__ == svg.path.path.CubicBezier:
            ctx.curve_to(segment.control1.real,segment.control1.imag,
                    segment.control2.real,segment.control2.imag,
                    segment.end.real,segment.end.imag)
        if segment.__class__ == svg.path.path.Line:
            pass

    ctx.close_path()
    ctx.set_source_rgb(color[0],color[1],color[2])
    ctx.set_line_width(linewidth*72)
    ctx.stroke()

def draw_centered_text(cr, cord, text, fontsize, color=(0,0,0)):
    cr.save()
    cr.set_source_rgb(color[0],color[1],color[2])
    cr.select_font_face("Courier", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(fontsize)
    (x_bearing, y_bearing, width, height, dx, dy) = cr.text_extents(text)
    cr.move_to(cord.real - width/2, cord.imag + height/2)
    cr.show_text(text)
    cr.restore()

    

def do_args():
    parser = argparse.ArgumentParser(description='Draw coil geometry from json file')
    parser.add_argument('layout_file', help='path to layout svg')
    parser.add_argument('out_file', help='output file path')
    parser.add_argument('-l','--levels_file', help='path to loop level file')
    parser.add_argument('-p','--precision',type=int,default=0, help='number of digits after the decimal point to print')
    parser.add_argument('-f','--font_size',type=int,default=20, help='font size in points')
    parser.add_argument('-c','--colorsplash_size',type=float,default=1, help='size of color splash in inches')
    parser.add_argument('-w','--line_width',type=float,default=.125, help='line width in inches')
    parser.add_argument('-m','--maxcol',type=float,default=100, help='maximum value of the colormap')
    parser.add_argument('--write_svg_idx',action='store_true', help='instead of writing loop value in its center, write the index of the loop in the input svg file')
    parser.add_argument('--write_loop_id',action='store_true', help='instead of writing loop value in its center, write loop id')

    return parser.parse_args()

class Loop:
    def find_center(self,canvasWidth,canvasHeight):
        srf = cairo.ImageSurface(cairo.FORMAT_A1,canvasWidth,canvasHeight)
        ctx = cairo.Context(srf)

        ctx.move_to(self.path[0].start.real,self.path[0].start.imag)
        for segment in self.path:
            if segment.__class__ == svg.path.path.CubicBezier:
                ctx.curve_to(segment.control1.real,segment.control1.imag,
                        segment.control2.real,segment.control2.imag,
                        segment.end.real,segment.end.imag)
        ctx.close_path()
        ctx.stroke()
        
        #cairo.ImageSurface.get_data() isn't availible in python3, use intermediate png instead
        b = io.BytesIO()
        srf.write_to_png(b)
        srf.finish()
        img = scipy.ndimage.imread(b)
        (cy,cx) = scipy.ndimage.measurements.center_of_mass(img)
        return (cx + (1j)*cy)

    def print_loop(self,ctx,linewidth,splashSize,fontsize,precision,maxcolor,write_svg_idx=False,write_loop_id=False):
        #colormap 0.0-1.0 to tuple of rgb values
        cmap = plt.get_cmap('viridis')

        #draw the black outline
        draw_path(ctx,self.path,linewidth,(0,0,0))

        #draw the color splash
        index = self.level/maxcolor
        draw_filled_ellipse(ctx, self.center, splashSize, splashSize, cmap(index))
        #draw the level as text
        val = round(self.level,precision)
        if write_svg_idx:
            draw_centered_text(ctx, self.center, str(self.svgidx),fontsize)
        elif write_loop_id:
            draw_centered_text(ctx, self.center, self.loopID,fontsize)
        else:
            draw_centered_text(ctx, self.center, '%.*f'%(precision,val),fontsize)

    def __init__(self,tag,canvasWidth,canvasHeight):
        if 'loopid' in tag.attrib:
            self.loopID = tag.attrib['loopid']
        else:
            self.loopID=None
        pathString = tag.attrib['d']
        self.path = svg.path.parse_path(pathString)
        self.center=self.find_center(canvasWidth,canvasHeight)


def main():
    args = do_args()

    #read input matlab file
    if args.levels_file:
        matlab_data = scipy.io.loadmat(args.levels_file)
        coil_names = matlab_data['coil_names']
        coil_levels = matlab_data['coil_ranks_avg'][0]
        numel = len(matlab_data['coil_names'])
        if args.maxcol:
            maxcol = args.maxcol
        else:
            maxcol = max(coil_levels)
        leveldict = dict(zip(coil_names,coil_levels))
    else:
        leveldict = {}

    #parse loop layout svg
    tree=ET.parse(args.layout_file)
    root = tree.getroot()
    (xmin, ymin, width, height) = [int(math.ceil(float(x))) for x in root.attrib['viewBox'].split()]
    pathTags = root.findall('svg:path',namespaces)

    loops = []
    loopidx = 1
    for tag in pathTags:
        loop = Loop(tag,width,height)
        loop.svgidx = loopidx
        loopidx = loopidx+1
        if loop.loopID in leveldict:
            loop.level=leveldict[loop.loopID]
        else:
            loop.level=0
        loops.append(loop)
        



    srf = cairo.SVGSurface(args.out_file,width,height)
    ctx = cairo.Context(srf)

    for loop in loops:
        loop.print_loop(ctx,args.line_width,args.colorsplash_size,args.font_size,args.precision,args.maxcol,args.write_svg_idx,args.write_loop_id)

    ctx.show_page()
    srf.finish()
            



if __name__ == "__main__":
    main()
