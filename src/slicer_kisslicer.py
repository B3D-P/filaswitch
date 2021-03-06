import logging
import re
from extruder import Extruder
from gcode import GCode
from layer import FirstLayer, ACT_INFILL, ACT_PASS, ACT_SWITCH, Layer

import utils
from gcode_file import SLICER_KISSLICER, GCodeFile
from settings import Settings

gcode = GCode()
log = logging.getLogger("KISSlicer")


class KISSlicerGCodeFile(GCodeFile):

    slicer_type = SLICER_KISSLICER

    # ; BEGIN_LAYER_OBJECT z=0.294 z_thickness=0.294
    LAYER_START_RE = re.compile(b" BEGIN_LAYER_OBJECT z=(\d+\.*\d*) z_thickness=(\d+\.*\d*)")
    VERSION_RE = re.compile(b"version (\d+)\.(\d+).*")
    VERSION_2_RE = re.compile(b"version 2 a (\d+)\.(\d+).*")

    def __init__(self, logger, settings: Settings):
        super().__init__(logger, settings)

    def process(self, gcode_file):
        self.open_file(gcode_file)
        self.parse_header()
        self.parse_print_settings()
        self.filter_layers()
        self.parse_perimeter_rates()
        if len(self.tools) > 1:
            self.find_tower_position()
            self.add_tool_change_gcode()
        else:
            self.log.info("No tool changes detected, skipping tool change g-code additions")
        self.print_summary()
        return self.save_new_file()

    def parse_version(self, lines):
        """
        Parse gcode file version
        :param lines: lines from gcode file
        :return:
        """
        for line in lines:
            if b"; version" in line:
                # parse version
                try:
                    comment = line.split(b";")[-1].strip()
                    m = self.VERSION_RE.match(comment)
                    if not m:
                        m = self.VERSION_2_RE.match(comment)
                        self.version = (2, int(m.groups()[0]), int(m.groups()[1]))
                    else:
                        self.version = (int(m.groups()[0]), int(m.groups()[1]))
                except Exception as e:
                    self.log.exception(e)
        if self.version is None:
            raise ValueError("KISSlicer version cannot be parsed")

    def _version_to_string(self):
        """
        Retunn version as string
        :return: version string
        """
        try:
            return "%d.%d" % self.version
        except:
            return "%d.%d.%d" % self.version

    def parse_header(self):
        """
         Parse KISS header and stuff for print settings
        :return: none
        """

        current_tool = None

        ext_re = re.compile(b".*Material Settings for Extruder (\d+)")

        for layer in self.layers:
            for cmd, comment in layer.lines:
                if cmd:
                    continue

                elif b" bed_size_x_mm =" in comment:
                    #; bed_size_x_mm = 145
                    self.settings.stroke_x = float(comment.split(b' = ')[1])
                elif b" bed_size_y_mm =" in comment:
                    #; bed_size_y_mm = 145
                    self.settings.stroke_y = float(comment.split(b' = ')[1])
                elif b" bed_offset_x_mm =" in comment:
                    #; bed_offset_x_mm = 72.5
                    self.settings.origin_offset_x = float(comment.split(b' = ')[1])
                elif b" bed_offset_y_mm =" in comment:
                    #; bed_offset_y_mm = 72.5
                    self.settings.origin_offset_y = float(comment.split(b' = ')[1])
                elif b" bed_offset_z_mm =" in comment:
                    #; bed_offset_z_mm = 0
                    self.settings.z_offset = float(comment.split(b' = ')[1])
                elif b" round_bed =" in comment:
                    # ; round_bed = 0
                    self.settings.machine_type = int(comment.split(b' = ')[1])
                elif b" travel_speed_mm_per_s =" in comment:
                    # ; travel_speed_mm_per_s = 100
                    speed = float(comment.split(b' = ')[1]) * 60
                    self.settings.travel_xy_speed = speed
                    self.settings.travel_z_speed = speed

                elif b" num_extruders = " in comment:
                    # ; num_extruders = 4
                    for t in range(int(comment.split(b' = ')[1])):
                        if t not in self.extruders:
                            self.extruders[t] = Extruder(t)
                            self.extruders[t].temperature_nr = t

                elif b" nozzle_dia" in comment:
                    # ; nozzle_dia_1 = 0.4
                    parts = comment.split(b" = ")
                    dia = float(parts[1])
                    t_num = int(parts[0].split(b"_")[2]) - 1
                    if t_num not in self.extruders:
                        self.extruders[t_num] = Extruder(t_num)
                    self.extruders[t_num].nozzle = dia

                elif b" first_layer_speed_mm_per_s =" in comment:
                    # ; first_layer_speed_mm_per_s = 25
                    self.settings.first_layer_speed = float(comment.split(b' = ')[1]) * 60

                elif b" Perimeter Speed =" in comment:
                    # ; Perimeter Speed = 32.50
                    self.settings.outer_perimeter_speed = float(comment.split(b' = ')[1]) * 60

                elif b" Loops Speed =" in comment:
                    # ; Loops Speed = 45.50
                    self.settings.default_speed = float(comment.split(b' = ')[1]) * 60

                elif b" extrusion_width =" in comment:
                    # ; extrusion_width = 0.45
                    self.settings.extrusion_width = float(comment.split(b' = ')[1])

                elif b" *** Material Settings for Extruder" in comment:
                    # ; *** Material Settings for Extruder 2 ***
                    m = ext_re.match(comment)
                    current_tool = int(m.groups()[0]) - 1

                elif current_tool is not None and b" destring_length =" in comment:
                    # ; destring_length = 3
                    self.extruders[current_tool].retract = float(comment.split(b' = ')[1])

                elif current_tool is not None and b" destring_speed_mm_per_s =" in comment:
                    # ; destring_speed_mm_per_s = 80
                    self.extruders[current_tool].retract_speed = float(comment.split(b' = ')[1]) * 60

                elif current_tool is not None and b" Z_lift_mm =" in comment:
                    # ; Z_lift_mm = 0
                    self.extruders[current_tool].z_hop = float(comment.split(b' = ')[1])

                elif current_tool is not None and b" wipe_mm =" in comment:
                    # ; wipe_mm = 5
                    self.extruders[current_tool].wipe = float(comment.split(b' = ')[1])

                elif current_tool is not None and b" flowrate_tweak =" in comment:
                    # ; flowrate_tweak = 1
                    self.extruders[current_tool].feed_rate_multiplier = float(comment.split(b' = ')[1])

                elif current_tool is not None and b" g_code_matl =" in comment:
                    # ; g_code_matl = NULL
                    self.extruders[current_tool].filament_type = comment.split(b' = ')[1]

                elif current_tool is not None and b" first_layer_C =" in comment:
                    # ; first_layer_C = 235
                    self.extruders[current_tool].temperature_setpoints[1] = int(comment.split(b' = ')[1])

                elif current_tool is not None and b" temperature_C =" in comment:
                    # ; temperature_C = 242
                    self.extruders[current_tool].temperature_setpoints[2] = int(comment.split(b' = ')[1])

                elif b" firmware_type =" in comment:
                    # ; firmware_type = 1
                    if comment.split(b' = ')[1] != b"1":
                        raise ValueError("Relative E distances not enabled! Filaswitch won't work without relative E distances")

                elif b"; force_joint_layers =" in comment:
                    # ; force_joint_layers = 0
                    if comment.split(b' = ')[1] != b"1":
                        self.log.warning("KISS joint layer division is not enabled. This might cause unexpected behaviour with tower size")

        if not self.version:
            self.log.warning("Could not detect KISSlicer version. Use at your own risk!")
        else:
            self.log.info("KISSlicer version %s" % self._version_to_string())

        for t in self.extruders:
            self.extruders[t].z_offset = self.settings.z_offset
            self.extruders[t].extrusion_width = self.settings.extrusion_width

        if self.settings.machine_type == 0:
            # fix KISS xy offsets
            self.settings.origin_offset_x = self.settings.origin_offset_x - self.settings.stroke_x/2
            self.settings.origin_offset_y = self.settings.origin_offset_y - self.settings.stroke_y/2

        # correct the layer height to value that doesn't have the z-offset
        if self.settings.z_offset != 0:
            for l in self.layers:
                l.z -= self.settings.z_offset

    def parse_print_settings(self):
        """ KISS specific settings """

        super().parse_print_settings()

        for cmd, comment, line_index in self.layers[0].read_lines():
            # find first tool change and remove it if it's T0. No need to
            # do tool change as e already have T0 active
            if line_index > self.layers[0].start_gcode_end and cmd and gcode.is_tool_change(cmd) == 0:
                self.layers[0].delete_line(line_index)
                break

    def parse_layers(self, lines):
        """
        Go through the g-code and find layer start points.
        Store each layer to list.
        :return:
        """

        current_layer = FirstLayer(1, 0.2, 0.2)
        layer_num = 0
        min_layer_height = 10
        max_z = 0
        for line in lines:
            cmd, comment = gcode.read_gcode_line(line)
            if comment:
                ret = self.check_layer_change(comment, None)
                if ret:
                    layer_z, layer_height = ret

                    if current_layer.num == 1 and layer_num == 0:
                        current_layer.z = layer_z
                        current_layer.height = layer_height
                        layer_num += 1
                    else:
                        self.layers.append(current_layer)
                        layer_num += 1
                        current_layer = Layer(layer_num, layer_z, layer_height)
            current_layer.add_line(cmd, comment)

            if current_layer.height < min_layer_height:
                min_layer_height = current_layer.height
            if current_layer.z > max_z:
                max_z = current_layer.z

        # last layer
        self.layers.append(current_layer)
        if len(self.layers) <= 1 and max_z > self.layers[0].height:
            raise ValueError("Detected only one layer, possibly an parsing error. Processing halted")
        #print(self.layers)

        self.min_layer_h = min_layer_height

    def check_layer_change(self, line, current_layer):
        """
        Check if line is layer change
        :param line: g-code line
        :param current_layer: current layer data
        :return: None or tuple of layer z and layer thickness
        """
        m = self.LAYER_START_RE.match(line)
        if m:
            return float(m.groups()[0]), float(m.groups()[1])
        return current_layer

    def parse_perimeter_rates(self):
        """
        Parses perimeter print speed and feed rate for each layer
        :return: none
        """
        last_speed = None
        last_feed_rate = None
        for layer in self.layers:
            layer.outer_perimeter_speed = self.settings.outer_perimeter_speed
            layer.outer_perimeter_feedrate = 0.05


if __name__ == "__main__":
    import logger
    logger = logger.Logger(".")
    s = KISSlicerGCodeFile(logger, PEEK, 4, "Automatic")
    print(s.check_layer_change(b" layer 1, Z = 1", None))