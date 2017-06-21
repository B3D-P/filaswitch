#!/usr/bin/env python3.5

"""
# filaswitch

G-code post processor for adding proper purge tower for 2 extruder - one hotend setup.

Disclaimer: i'm not responsible if anything, good or bad, happens due to use of this script.

Version 0.1
"""


import logging
import os
import subprocess
import sys

#from slicer_cura import CuraPrintFile
#from slicer_kisslicer import KissPrintFile
from slicer_simplify3d import Simplify3dGCodeFile
#from slicer_slic3r import Slic3rPrintFile

import utils

dir = os.path.dirname(os.path.realpath(__file__))

fmt = logging.Formatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
filehandler = logging.FileHandler(os.path.join(dir, "filaswitch.log"))
filehandler.setFormatter(fmt)
streamhandler = logging.StreamHandler(stream=sys.stdout)
streamhandler.setFormatter(fmt)
log = logging.getLogger("filaswitch")
log.setLevel(logging.INFO)
log.addHandler(filehandler)
log.addHandler(streamhandler)


def detect_file_type(gcode_file):
    with open(gcode_file, 'r') as gf:
        line1 = gf.readline()
        if line1.startswith('; G-Code generated by Simplify3D(R)'):
            log.info("Detected Simplify3D format")
            return Simplify3dGCodeFile
        #elif line1.startswith('; KISSlicer'):
        #    log.info("Detected KISSlicer format")
        #    return KissPrintFile
        #elif line1.startswith('; CURA'):
        #    log.info("Detected Cura format")
        #    return CuraPrintFile
        #elif line1.startswith('; generated by Slic3r'):
        #    log.info("Detected Slic3r format")
        #    return Slic3rPrintFile

        else:
            log.error("No supported gcode file detected. Is comments enabled on Kisslicer or '; CURA' header added to Cura start.gcode?")
            exit(1)

if __name__ == "__main__":
    debug = False
    if len(sys.argv) < 2:
        log.error("Need argument for file to process")
        exit(1)
    #g_file = '/media/Roinaa/3DModels/_dev/3DBenchy_dc.gcode'
    g_file = sys.argv[1]
    if len(sys.argv) == 3 and sys.argv[2] == "--debug":
        debug = True

    print_type = detect_file_type(g_file)
    pf = print_type(debug=debug)
    result_file = pf.process(g_file)
