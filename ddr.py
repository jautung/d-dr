import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = ''

from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *

import enum
import math
import pick
import pygame

################
# SONG START
################

DDR_BEATS_PER_ROW = 4
DDR_BEAT_VARIANT_NONE = '0'
DDR_BEAT_VARIANT_DEFAULT = '1'
DDR_BEAT_VARIANT_HOLD_START = '2'
DDR_BEAT_VARIANT_HOLD_END = '3'
DDR_BEAT_VARIANT_MINE = 'M'

class Song:
    def __init__(self, header_data, beatmap_list):
        self._header_data = header_data
        self._beatmap_list = beatmap_list
        self._cached_beats_per_minute = None
        self._cached_stops = None

    def displayed_name(self):
        return f'{self._header_data["TITLE"]} ({self._header_data["ARTIST"]}) · {self._displayed_beats_per_minute()} BPM'

    def _displayed_beats_per_minute(self):
        if 'DISPLAYBPM' in self._header_data:
            display_bpm_data = self._header_data['DISPLAYBPM']
            if ':' not in display_bpm_data:
                return f'{int(float(display_bpm_data))}'
            display_bpm_data_split = display_bpm_data.split(':')
            assert(len(display_bpm_data_split) == 2)
            return f'{int(float(display_bpm_data_split[0]))}~{int(float(display_bpm_data_split[1]))}'
        else:
            all_beats_per_minutes = [beats_per_minute_assignment[1] for beats_per_minute_assignment in self.beats_per_minute()]
            displayed_min_beats_per_minute = int(float(min(all_beats_per_minutes)))
            displayed_max_beats_per_minute = int(float(max(all_beats_per_minutes)))
            if displayed_min_beats_per_minute == displayed_max_beats_per_minute:
                return f'{displayed_min_beats_per_minute}'
            else:
                return f'{displayed_min_beats_per_minute}~{displayed_max_beats_per_minute}'

    def music_filename(self):
        return self._header_data['MUSIC']

    def music_offset(self):
        return float(self._header_data['OFFSET'])

    def beats_per_minute(self):
        if self._cached_beats_per_minute:
            return self._cached_beats_per_minute
        beats_per_minute = self._get_beats_per_minute()
        self._cached_beats_per_minute = beats_per_minute
        return beats_per_minute

    def _get_beats_per_minute(self):
        beats_per_minute_assignments = parse_comma_separated_assignments(self._header_data['BPMS'])
        assert(len(beats_per_minute_assignments) > 0)
        assert(float(beats_per_minute_assignments[0][0]) == 0)
        return beats_per_minute_assignments

    def beats_per_measure(self):
        if 'TIMESIGNATURES' not in self._header_data:
            return 4 # This is the default if not specified
        # TODO: Handle different 'TIMESIGNATURES'
        time_signatures_data = self._header_data['TIMESIGNATURES'].split('=')
        assert(float(time_signatures_data[0]) == 0)
        assert(float(time_signatures_data[1]) == 4)
        assert(float(time_signatures_data[2]) == 4)
        return 4

    def stops(self):
        if self._cached_stops:
            return self._cached_stops
        stops = self._get_stops()
        self._cached_stops = stops
        return stops

    def _get_stops(self):
        stops_assignments = parse_comma_separated_assignments(self._header_data['STOPS'])
        return stops_assignments

    def ddr_beatmap_list(self):
        ddr_beatmap_list = [beatmap for beatmap in self._beatmap_list if beatmap.is_ddr_beatmap()]
        ddr_beatmap_list.sort(key=lambda beatmap: beatmap.difficulty_int())
        return ddr_beatmap_list

class Beatmap:
    def __init__(self, title_line, data):
        self._title_line = title_line
        self._data = data
        self._cached_ddr_beat_list = None

    def displayed_difficulty(self):
        return f'{self._data["DIFFICULTY"]} ({self._data["METER"]})'

    def difficulty_int(self):
        return int(self._data['METER'])

    def _type(self):
        return self._data['STEPSTYPE']

    def is_ddr_beatmap(self):
        return self._type() == 'dance-single'

    def music_offset(self):
        if 'OFFSET' in self._data and self._data['OFFSET']:
            return float(self._data['OFFSET'])
        return None

    def ddr_beat_list(self):
        if self._cached_ddr_beat_list:
            return self._cached_ddr_beat_list
        ddr_beat_list = self._get_ddr_beat_list()
        self._cached_ddr_beat_list = ddr_beat_list
        return ddr_beat_list

    def _get_ddr_beat_list(self):
        measures = self._data['NOTES'].split(',')
        ddr_beat_list = []
        for measure_index, measure in enumerate(measures):
            rows = [measure[i:i+DDR_BEATS_PER_ROW] for i in range(0, len(measure), DDR_BEATS_PER_ROW)]
            for row_index, row in enumerate(rows):
                for i in range(DDR_BEATS_PER_ROW):
                    if row[i] != DDR_BEAT_VARIANT_NONE:
                        ddr_beat_list.append(Beat(
                            measure_time=measure_index+row_index/len(rows),
                            rgb=self._get_ddr_beat_rgb(row_index, len(rows)),
                            direction=BeatDirection(i),
                            variant=row[i],
                        ))
        return ddr_beat_list

    def _get_ddr_beat_rgb(self, beat_within_measure, total_beats_in_measure):
        if (4*beat_within_measure) % total_beats_in_measure == 0:
            return RED_RGB
        elif (8*beat_within_measure) % total_beats_in_measure == 0:
            return BLUE_RGB
        elif (6*beat_within_measure) % total_beats_in_measure == 0:
            return GREEN_RGB
        elif (12*beat_within_measure) % total_beats_in_measure == 0:
            return PURPLE_RGB
        else:
            return WHITE_RGB

class Beat:
    def __init__(self, measure_time, rgb, direction, variant):
        self.measure_time = measure_time
        self.rgb = rgb
        self.direction = direction
        self.variant = variant

class BeatDirection(enum.Enum):
    LEFT = 0
    DOWN = 1
    UP = 2
    RIGHT = 3

################
# SONG END
################

################
# PARSING START
################

PYTHON_BOM_CHARACTER_ORD = 65279

def parse(lines, file_format):
    lines = strip_prefixed_bom_characters(lines)
    header_data = parse_hashtag_headered(lines)
    beatmap_list = []
    while True:
        maybe_beatmap = parse_beatmap(lines, file_format)
        if maybe_beatmap:
            beatmap_list.append(maybe_beatmap)
        else:
            break
    return Song(header_data=header_data, beatmap_list=beatmap_list)

def parse_hashtag_headered(lines):
    header_data = dict()
    while len(lines) > 0:
        line = lines.pop(0).strip('\n')
        if line == '' or line.startswith('//'):
            break
        header_label = get_hashtag_label(line)
        assert(line[len(header_label)+1] == ':' or line[len(header_label)+1] == ';')
        if line[len(header_label)+1] == ';':
            header_data[header_label] = ''
            continue
        assert(line[len(header_label)+1] == ':')
        line = line[len(header_label)+2:]
        if len(line) > 0 and line[-1] == ';':
            header_data[header_label] = line[:-1]
        else:
            while True:
                addendum_line = lines.pop(0).strip('\n')
                if len(addendum_line) > 0 and addendum_line[-1] == ';':
                    line += addendum_line[:-1]
                    break
                line += addendum_line
            header_data[header_label] = line
    return header_data

def get_hashtag_label(line):
    assert(line[0] == '#')
    line = line[1:]
    colon_index = line.find(':')
    if colon_index != -1:
        return line[:colon_index]
    semicolon_index = line.find(';')
    assert(semicolon_index != -1)
    return line[:semicolon_index]

def parse_comma_separated_assignments(line):
    sections = line.split(',')
    section_assignments = [section.split('=') for section in sections]
    for section_assignment in section_assignments:
        assert(len(section_assignment) == 2)
    return [(float(section_assignment[0]), float(section_assignment[1])) for section_assignment in section_assignments]

def parse_beatmap(lines, file_format):
    while True:
        if len(lines) == 0:
            return None
        line = lines.pop(0).strip('\n')
        if line.startswith('//----'):
            break
    beatmap_title_line = line

    beatmap_lines = []
    while len(lines) > 0:
        peek_line = lines[0].strip('\n')
        if peek_line.startswith('//----'):
            break
        line = lines.pop(0).strip('\n')
        beatmap_lines.append(strip_comments(line))

    if file_format == '.ssc':
        beatmap_data = parse_hashtag_headered(beatmap_lines)
    elif file_format == '.sm':
        beatmap_data = parse_beatmap_sm_data(beatmap_lines)
    else:
        assert(False)

    return Beatmap(title_line=parse_beatmap_title_line(beatmap_title_line), data=beatmap_data)

def parse_beatmap_title_line(beatmap_title_line):
    assert(beatmap_title_line.startswith('//'))
    beatmap_title_line = beatmap_title_line[2:]
    return beatmap_title_line.strip('-')

def parse_beatmap_sm_data(beatmap_lines):
    beatmap_data_raw = parse_hashtag_headered(beatmap_lines)
    assert('NOTES' in beatmap_data_raw)
    beatmap_data = beatmap_data_raw['NOTES'].split(':')
    assert(len(beatmap_data) == 6)
    return {
        'STEPSTYPE': beatmap_data[0].strip(),
        'DESCRIPTION': beatmap_data[1].strip(),
        'DIFFICULTY': beatmap_data[2].strip(),
        'METER': beatmap_data[3].strip(),
        'RADARVALUES': beatmap_data[4].strip(),
        'NOTES': beatmap_data[5].strip(),
    }

def strip_prefixed_bom_characters(lines):
    # https://stackoverflow.com/questions/74683953/python-keeps-adding-character-65279-to-the-beginning-of-my-file
    return [line if ord(line[0]) != PYTHON_BOM_CHARACTER_ORD else line[1:] for line in lines]

def strip_comments(line):
    comment_start = line.find('//')
    if comment_start == -1:
        return line
    return line[:comment_start].strip()

################
# PARSING END
################

################
# DISPLAY START
################

PRECOMPUTED_FPS = 300
PRECOMPUTED_ADDITIONAL_SECONDS = 3

POSITION_X = 0
POSITION_Y = 0
DISPLAY_WIDTH = 1200
DISPLAY_HEIGHT = 800

ARROW_SIZE = 100
ARROW_DIAGONAL_WIDTH = ARROW_SIZE/10
ARROW_STRAIGHT_WIDTH = ARROW_DIAGONAL_WIDTH*1.5
ARROW_TOP_MARGIN = 30
ARROW_HORIZONTAL_MARGIN = 20

HOLD_ALPHA = 0.2
OUTLINE_ALPHA = 0.8

MINE_MARGIN = ARROW_SIZE/10
MINE_EXCLAMATION_WIDTH = ARROW_STRAIGHT_WIDTH
MINE_EXCLAMATION_HEIGHT = ARROW_SIZE/3

ARROW_SPEED_PIXELS_PER_SECOND = 800 # TODO: Make this configurable
ARROW_SPEED_PIXELS_PER_FRAME = ARROW_SPEED_PIXELS_PER_SECOND / PRECOMPUTED_FPS

SONG_SPEED = 1 # TODO: Respect this and make this configurable

GLOBAL_MUSIC_OFFSET_SECONDS = 0.22 # Reasonable default for most songs
MILLISECONDS_IN_SECONDS = 1000
SECONDS_IN_MINUTE = 60

WHITE_RGB = (0.9, 0.9, 0.9)
RED_RGB = (1.0, 0.25, 0.25)
BLUE_RGB = (0.125, 0.125, 1.0)
GREEN_RGB = (0.0, 0.8, 0.1)
PURPLE_RGB = (0.5, 0.0, 0.75)
ORANGE_RGB = (1.0, 0.9, 0.75)

class DisplayedBeat:
    def __init__(self, rgb, direction, variant, position_y, position_y_hold_end):
        self.rgb = rgb
        self.direction = direction
        self.variant = variant
        self.position_y = position_y
        self.position_y_hold_end = position_y_hold_end

class DDRWindow:
    def __init__(self, song, beatmap, song_music_filepath, song_custom_offset_filepath, precomputed_fps=PRECOMPUTED_FPS, position_x=POSITION_X, position_y=POSITION_Y, display_width=DISPLAY_WIDTH, display_height=DISPLAY_HEIGHT):
        self._position_x = position_x
        self._position_y = position_y
        self._display_width = display_width
        self._display_height = display_height
        self._arrow_target_position_y = display_height - ARROW_TOP_MARGIN - ARROW_SIZE
        self._arrow_left_position_x = display_width/2 - ARROW_HORIZONTAL_MARGIN/2 - ARROW_SIZE - ARROW_SIZE - ARROW_HORIZONTAL_MARGIN
        self._arrow_down_position_x = display_width/2 - ARROW_HORIZONTAL_MARGIN/2 - ARROW_SIZE
        self._arrow_up_position_x = display_width/2 + ARROW_HORIZONTAL_MARGIN/2
        self._arrow_right_position_x = display_width/2 + ARROW_HORIZONTAL_MARGIN/2 + ARROW_SIZE + ARROW_HORIZONTAL_MARGIN

        glutInit()
        glutInitDisplayMode(GLUT_RGBA)
        glutInitWindowPosition(position_x, position_y)
        glutInitWindowSize(display_width, display_height)
        self._window = glutCreateWindow("D/DR")
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_BLEND)

        pygame.mixer.init()
        pygame.mixer.music.load(song_music_filepath)

        print('⏳️ Precomputing...')
        self._precomputed_displays = self._precompute_displays(song, beatmap, precomputed_fps)
        self._beatmap_music_offset = beatmap.music_offset()
        self._song_music_offset = song.music_offset()
        self._custom_offset_filepath = song_custom_offset_filepath
        self._custom_offset = self._get_custom_offset_from_file()
        print('✅ Precomputing complete!')

        self._started = False

    # This can theoretically be optimized by using the fact that [beat_list] is sorted by [measure_time],
    # but doing so feels like over-engineering since this is a precomputing step
    def _precompute_displays(self, song, beatmap, precomputed_fps):
        beats_per_minute = song.beats_per_minute()
        beats_per_measure = song.beats_per_measure()
        stops = song.stops()
        beat_list = beatmap.ddr_beat_list()

        def measure_time_to_frame(measure_time):
            return measure_time * beats_per_measure / beats_per_minute[0][1] * SECONDS_IN_MINUTE * precomputed_fps

        def measure_time_to_position_y_at_frame(measure_time, frame):
            target_frame = measure_time_to_frame(measure_time)
            return self._arrow_target_position_y + (frame - target_frame) * ARROW_SPEED_PIXELS_PER_FRAME

        def get_last_frame_to_precompute():
            last_beat_measure_time = max([beat.measure_time for beat in beat_list])
            last_beat_frame = int(math.ceil(measure_time_to_frame(last_beat_measure_time)))
            return last_beat_frame + PRECOMPUTED_ADDITIONAL_SECONDS*PRECOMPUTED_FPS

        def get_display_for_frame(frame):
            displayed_beats_with_nones = [get_displayed_beat_for_frame(beat, beat_index, frame) for beat_index, beat in enumerate(beat_list)]
            return list(filter(lambda displayed_beat: displayed_beat, displayed_beats_with_nones))

        def get_displayed_beat_for_frame(beat, beat_index, frame):
            if beat.variant == DDR_BEAT_VARIANT_HOLD_END:
                return None # Display will be handled by the start of the hold note
            position_y = measure_time_to_position_y_at_frame(beat.measure_time, frame)
            if beat.variant == DDR_BEAT_VARIANT_HOLD_START:
                position_y_hold_end = measure_time_to_position_y_at_frame(get_beat_hold_end_for_hold_start(beat, beat_index).measure_time, frame)
            else:
                position_y_hold_end = None
            if not is_position_y_in_display(position_y, position_y_hold_end):
                return None
            return DisplayedBeat(
                rgb=beat.rgb,
                direction=beat.direction,
                variant=beat.variant,
                position_y=position_y,
                position_y_hold_end=position_y_hold_end,
            )

        def get_beat_hold_end_for_hold_start(beat, beat_index):
            assert(beat.variant == DDR_BEAT_VARIANT_HOLD_START)
            for next_beat in beat_list[beat_index+1:]:
                if next_beat.variant == DDR_BEAT_VARIANT_HOLD_END and next_beat.direction == beat.direction:
                    return next_beat
            assert(False)

        def is_position_y_in_display(position_y, position_y_hold_end):
            if position_y >= -ARROW_SIZE and position_y <= self._display_height:
                return True
            if not position_y_hold_end:
                return False
            if position_y_hold_end >= -ARROW_SIZE and position_y_hold_end <= self._display_height:
                return True
            if position_y > self._display_height and position_y_hold_end < -ARROW_SIZE:
                return True
            return False

        return [get_display_for_frame(frame) for frame in range(get_last_frame_to_precompute())]

    def start_main_loop(self):
        glutDisplayFunc(self._display_func)
        glutIdleFunc(self._display_func)
        glutKeyboardFunc(self._keyboard_func)
        glutMainLoop()

    def _start_song(self):
        pygame.mixer.music.play()
        self._started = True

    def _keyboard_func(self, key, x, y):
        if key == b' ' or key == b'\r':
            self._start_song()
        elif key == b'h' and self._started:
            self._custom_offset -= 0.01
            print(f'🔄 Custom offset: {self._custom_offset:.3f}s')
        elif key == b'j' and self._started:
            self._custom_offset -= 0.001
            print(f'🔄 Custom offset: {self._custom_offset:.3f}s')
        elif key == b'k' and self._started:
            self._custom_offset += 0.001
            print(f'🔄 Custom offset: {self._custom_offset:.3f}s')
        elif key == b'l' and self._started:
            self._custom_offset += 0.01
            print(f'🔄 Custom offset: {self._custom_offset:.3f}s')
        elif key == b'q':
            self._exit()

    def _get_custom_offset_from_file(self):
        if os.path.exists(self._custom_offset_filepath):
            with open(self._custom_offset_filepath) as f:
                try:
                    return float(f.read())
                except ValueError:
                    return 0
        else:
            return 0

    def _maybe_save_custom_offset(self):
        initial_custom_offset = self._get_custom_offset_from_file()
        if round(self._custom_offset - initial_custom_offset, 3) != 0:
            should_save = input(f'💾 Save custom offset of {self._custom_offset:.3f}s; previously {initial_custom_offset:.3f}s (y/n)? ').lower() == 'y'
            if should_save:
                with open(self._custom_offset_filepath, 'w') as f:
                    f.write(str(round(self._custom_offset, 3)))

    def _music_offset_seconds(self):
        return GLOBAL_MUSIC_OFFSET_SECONDS + (self._beatmap_music_offset if self._beatmap_music_offset else self._song_music_offset) + self._custom_offset

    def _exit(self):
        if not self._started:
            return
        pygame.mixer.music.stop()
        pygame.quit()
        glutDestroyWindow(self._window)
        self._maybe_save_custom_offset()
        # Forceful exit is unfortunately needed since there is no way to leave the GLUT main loop otherwise
        # ([sys.exit()] or [raise SystemExit] both result in segmentation faults)
        # https://www.gamedev.net/forums/topic/376112-terminating-a-glut-loop-inside-a-program/3482380/
        # https://stackoverflow.com/a/35430500
        os._exit(0)

    def _display_func(self):
        if self._started and not pygame.mixer.music.get_busy(): # Song is over!
            self._exit()
        self._display_reset()
        self._target_arrows()
        self._moving_arrows(pygame.mixer.music.get_pos() / MILLISECONDS_IN_SECONDS - self._music_offset_seconds())
        glutSwapBuffers()

    def _display_reset(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        glViewport(
            self._position_x, # x
            self._position_y, # y
            self._display_width, # width
            self._display_height, # height
        )
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()

        glOrtho(
            self._position_x, # left
            self._position_x + self._display_width, # right
            self._position_y, # bottom
            self._position_y + self._display_height, # top
            0.0, # near_val
            1.0, # far_val
        )
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def _target_arrows(self):
        self._arrow(rgb=WHITE_RGB, direction=BeatDirection.LEFT, position_y=self._arrow_target_position_y, is_outline_only=True)
        self._arrow(rgb=WHITE_RGB, direction=BeatDirection.DOWN, position_y=self._arrow_target_position_y, is_outline_only=True)
        self._arrow(rgb=WHITE_RGB, direction=BeatDirection.UP, position_y=self._arrow_target_position_y, is_outline_only=True)
        self._arrow(rgb=WHITE_RGB, direction=BeatDirection.RIGHT, position_y=self._arrow_target_position_y, is_outline_only=True)

    def _moving_arrows(self, current_time):
        current_frame = int(current_time * PRECOMPUTED_FPS)
        displayed_beats = self._precomputed_displays[current_frame] if current_frame < len(self._precomputed_displays) else []
        for displayed_beat in displayed_beats:
            if displayed_beat.variant == DDR_BEAT_VARIANT_DEFAULT:
                self._arrow(rgb=displayed_beat.rgb, direction=displayed_beat.direction, position_y=displayed_beat.position_y)
            elif displayed_beat.variant == DDR_BEAT_VARIANT_HOLD_START:
                self._hold_background(rgb=displayed_beat.rgb, direction=displayed_beat.direction, position_y=displayed_beat.position_y, position_y_hold_end=displayed_beat.position_y_hold_end)
                self._arrow(rgb=displayed_beat.rgb, direction=displayed_beat.direction, position_y=displayed_beat.position_y)
                self._arrow(rgb=displayed_beat.rgb, direction=displayed_beat.direction, position_y=displayed_beat.position_y_hold_end, is_outline_only=True)
            elif displayed_beat.variant == DDR_BEAT_VARIANT_MINE:
                self._mine(direction=displayed_beat.direction, position_y=displayed_beat.position_y)
            else:
                assert(False)

    def _arrow(self, rgb, direction, position_y, is_outline_only=False):
        position_x = self._position_x_from_direction(direction)
        rotation_angle_degrees = self._rotation_angle_degrees_from_direction(direction)

        glPushMatrix()
        glTranslatef(
            position_x + ARROW_SIZE/2, # x
            position_y + ARROW_SIZE/2, # y
            0, # z
        )
        glRotatef(
            rotation_angle_degrees, # angle
            0, # x
            0, # y
            1, # z
        )
        glTranslatef(
            -ARROW_SIZE/2, # x
            -ARROW_SIZE/2, # y
            0, # z
        )

        glColor4f(*rgb, OUTLINE_ALPHA if is_outline_only else 1.0)

        glBegin(GL_LINE_LOOP if is_outline_only else GL_POLYGON)
        glVertex2f(ARROW_DIAGONAL_WIDTH + ARROW_DIAGONAL_WIDTH/2, ARROW_SIZE/2 - ARROW_DIAGONAL_WIDTH + ARROW_DIAGONAL_WIDTH/2)
        glVertex2f(ARROW_DIAGONAL_WIDTH/2                       , ARROW_SIZE/2 - ARROW_DIAGONAL_WIDTH/2                       )
        glVertex2f(ARROW_DIAGONAL_WIDTH/2                       , ARROW_SIZE/2 + ARROW_DIAGONAL_WIDTH/2                       )
        glVertex2f(ARROW_SIZE/2                                 , ARROW_SIZE                                                  )
        glVertex2f(ARROW_SIZE/2 + ARROW_DIAGONAL_WIDTH          , ARROW_SIZE - ARROW_DIAGONAL_WIDTH                           )
        glEnd()

        glBegin(GL_LINE_LOOP if is_outline_only else GL_POLYGON)
        glVertex2f(ARROW_SIZE - ARROW_DIAGONAL_WIDTH - ARROW_DIAGONAL_WIDTH/2, ARROW_SIZE/2 - ARROW_DIAGONAL_WIDTH + ARROW_DIAGONAL_WIDTH/2)
        glVertex2f(ARROW_SIZE - ARROW_DIAGONAL_WIDTH/2                       , ARROW_SIZE/2 - ARROW_DIAGONAL_WIDTH/2                       )
        glVertex2f(ARROW_SIZE - ARROW_DIAGONAL_WIDTH/2                       , ARROW_SIZE/2 + ARROW_DIAGONAL_WIDTH/2                       )
        glVertex2f(ARROW_SIZE/2                                              , ARROW_SIZE                                                  )
        glVertex2f(ARROW_SIZE/2 - ARROW_DIAGONAL_WIDTH                       , ARROW_SIZE - ARROW_DIAGONAL_WIDTH                           )
        glEnd()

        glBegin(GL_LINE_LOOP if is_outline_only else GL_POLYGON)
        glVertex2f(ARROW_SIZE/2 - ARROW_STRAIGHT_WIDTH/2, ARROW_SIZE - ARROW_DIAGONAL_WIDTH)
        glVertex2f(ARROW_SIZE/2 + ARROW_STRAIGHT_WIDTH/2, ARROW_SIZE - ARROW_DIAGONAL_WIDTH)
        glVertex2f(ARROW_SIZE/2 + ARROW_STRAIGHT_WIDTH/2, ARROW_STRAIGHT_WIDTH/2           )
        glVertex2f(ARROW_SIZE/2                         , 0                                )
        glVertex2f(ARROW_SIZE/2 - ARROW_STRAIGHT_WIDTH/2, ARROW_STRAIGHT_WIDTH/2           )
        glEnd()

        glPopMatrix()

    def _hold_background(self, rgb, direction, position_y, position_y_hold_end):
        position_x = self._position_x_from_direction(direction)
        rotation_angle_degrees = self._rotation_angle_degrees_from_direction(direction)
        position_y_hold_end_delta = position_y_hold_end - position_y

        glPushMatrix()
        glTranslatef(
            position_x, # x
            position_y, # y
            0, # z
        )

        glColor4f(*rgb, HOLD_ALPHA)

        glBegin(GL_POLYGON)
        glVertex2f(0         , ARROW_SIZE               )
        glVertex2f(ARROW_SIZE, ARROW_SIZE               )
        glVertex2f(ARROW_SIZE, position_y_hold_end_delta)
        glVertex2f(0         , position_y_hold_end_delta)
        glEnd()

        glPopMatrix()

    def _mine(self, direction, position_y):
        position_x = self._position_x_from_direction(direction)

        glPushMatrix()
        glTranslatef(
            position_x, # x
            position_y, # y
            0, # z
        )

        glColor3f(*ORANGE_RGB)

        glBegin(GL_POLYGON)
        glVertex2f(MINE_MARGIN             , ARROW_SIZE - MINE_MARGIN)
        glVertex2f(ARROW_SIZE - MINE_MARGIN, ARROW_SIZE - MINE_MARGIN)
        glVertex2f(ARROW_SIZE - MINE_MARGIN, MINE_MARGIN             )
        glVertex2f(MINE_MARGIN             , MINE_MARGIN             )
        glEnd()

        glColor3f(*RED_RGB)

        glBegin(GL_POLYGON)
        glVertex2f(ARROW_SIZE/2 - MINE_EXCLAMATION_WIDTH/2, ARROW_SIZE/2 - MINE_EXCLAMATION_HEIGHT/2                         )
        glVertex2f(ARROW_SIZE/2 + MINE_EXCLAMATION_WIDTH/2, ARROW_SIZE/2 - MINE_EXCLAMATION_HEIGHT/2                         )
        glVertex2f(ARROW_SIZE/2 + MINE_EXCLAMATION_WIDTH/2, ARROW_SIZE/2 - MINE_EXCLAMATION_HEIGHT/2 - MINE_EXCLAMATION_WIDTH)
        glVertex2f(ARROW_SIZE/2 - MINE_EXCLAMATION_WIDTH/2, ARROW_SIZE/2 - MINE_EXCLAMATION_HEIGHT/2 - MINE_EXCLAMATION_WIDTH)
        glEnd()

        glBegin(GL_POLYGON)
        glVertex2f(ARROW_SIZE/2 - MINE_EXCLAMATION_WIDTH/2 - MINE_EXCLAMATION_WIDTH/6, ARROW_SIZE/2 + MINE_EXCLAMATION_HEIGHT/2 + MINE_EXCLAMATION_WIDTH)
        glVertex2f(ARROW_SIZE/2 + MINE_EXCLAMATION_WIDTH/2 + MINE_EXCLAMATION_WIDTH/6, ARROW_SIZE/2 + MINE_EXCLAMATION_HEIGHT/2 + MINE_EXCLAMATION_WIDTH)
        glVertex2f(ARROW_SIZE/2 + MINE_EXCLAMATION_WIDTH/2                           , ARROW_SIZE/2 - MINE_EXCLAMATION_HEIGHT/2 + MINE_EXCLAMATION_WIDTH)
        glVertex2f(ARROW_SIZE/2 - MINE_EXCLAMATION_WIDTH/2                           , ARROW_SIZE/2 - MINE_EXCLAMATION_HEIGHT/2 + MINE_EXCLAMATION_WIDTH)
        glEnd()

        glPopMatrix()

    def _position_x_from_direction(self, direction):
        match direction:
            case BeatDirection.LEFT:
                return self._arrow_left_position_x
            case BeatDirection.DOWN:
                return self._arrow_down_position_x
            case BeatDirection.UP:
                return self._arrow_up_position_x
            case BeatDirection.RIGHT:
                return self._arrow_right_position_x

    def _rotation_angle_degrees_from_direction(self, direction):
        match direction:
            case BeatDirection.LEFT:
                return 90
            case BeatDirection.DOWN:
                return 180
            case BeatDirection.UP:
                return 0
            case BeatDirection.RIGHT:
                return 270

################
# DISPLAY END
################

################
# SONG LIST START
################

SONG_MAIN_DIR_NAME = 'songs'
CUSTOM_OFFSET_FILENAME = 'custom_offset.dat'

def get_song_folder_list():
    assert(os.path.exists(SONG_MAIN_DIR_NAME))
    return [song_folder for song_folder in os.listdir(SONG_MAIN_DIR_NAME) if os.path.isdir(os.path.join(SONG_MAIN_DIR_NAME, song_folder))]

def get_song_list(song_folder):
    song_folder_filepath = os.path.join(SONG_MAIN_DIR_NAME, song_folder)
    song_list = []
    for song_dir_name in os.listdir(song_folder_filepath):
        song_dir_filepath = os.path.join(song_folder_filepath, song_dir_name)
        if not os.path.isdir(song_dir_filepath):
            continue
        song = get_song(song_dir_filepath)
        if not song:
            print(f'⚠️ Skipping "{song_dir_name}" because it is missing the .ssc/.sm file...')
            continue
        song_music_filepath = os.path.join(song_dir_filepath, song.music_filename())
        if not os.path.exists(song_music_filepath):
            print(f'⚠️ Skipping "{song_dir_name}" because it is missing the music file...')
            continue
        song_custom_offset_filepath = os.path.join(song_dir_filepath, CUSTOM_OFFSET_FILENAME)
        song_list.append((song, song_music_filepath, song_custom_offset_filepath))
    song_list.sort(key=lambda song_and_filepaths_tuple: song_and_filepaths_tuple[0].displayed_name())
    return song_list

def get_song(song_dir_filepath):
    song_ssc_filename = next(filter(lambda file: file.lower().endswith('.ssc'), os.listdir(song_dir_filepath)), None)
    song_sm_filename = next(filter(lambda file: file.lower().endswith('.sm'), os.listdir(song_dir_filepath)), None)
    if song_ssc_filename:
        song_ssc_filepath = os.path.join(song_dir_filepath, song_ssc_filename)
        with open(song_ssc_filepath) as f:
            return parse(f.readlines(), '.ssc')
    elif song_sm_filename:
        # .sm is the legacy file format (https://www.reddit.com/r/Stepmania/comments/a1arfu/difference_between_sm_and_ssc_file_types/)
        song_sm_filepath = os.path.join(song_dir_filepath, song_sm_filename)
        with open(song_sm_filepath) as f:
            return parse(f.readlines(), '.sm')
    else:
        return None

################
# SONG LIST END
################

################
# MAIN START
################

PICK_INDICATOR = '=>'

def full_select_beatmap():
    song_selected, song_selected_music_filepath = select_song()
    beatmap_selected = select_beatmap(song_selected)
    if beatmap_selected:
        return song_selected, beatmap_selected, song_selected_music_filepath
    else: # <Back>
        return full_select_beatmap()

def main():
    song_folder_selected = None
    song_selected = None
    song_selected_music_filepath = None
    song_custom_offset_filepath = None
    beatmap_selected = None

    def select_song_folder():
        song_folder_list = get_song_folder_list()
        _, song_folder_selected_index = pick.pick(options=song_folder_list, title='Choose song pack...', indicator=PICK_INDICATOR)
        nonlocal song_folder_selected
        song_folder_selected = song_folder_list[song_folder_selected_index]
        select_song()

    def select_song():
        nonlocal song_folder_selected
        song_list = get_song_list(song_folder_selected)
        song_displayed_options = [song.displayed_name() for song, _, _ in song_list]
        _, song_selected_index = pick.pick(options=song_displayed_options + ['<Back>'], title='Choose song...', indicator=PICK_INDICATOR)
        if song_selected_index == len(song_list): # <Back>
            song_folder_selected = None
            select_song_folder()
        else:
            nonlocal song_selected
            nonlocal song_selected_music_filepath
            nonlocal song_custom_offset_filepath
            song_selected, song_selected_music_filepath, song_custom_offset_filepath = song_list[song_selected_index]
            select_beatmap()

    def select_beatmap():
        nonlocal song_selected
        beatmap_list = song_selected.ddr_beatmap_list()
        beatmap_displayed_options = [beatmap.displayed_difficulty() for beatmap in beatmap_list]
        _, beatmap_selected_index = pick.pick(options=beatmap_displayed_options + ['<Back>'], title='Choose difficulty...', indicator=PICK_INDICATOR)
        if beatmap_selected_index == len(beatmap_list): # <Back>
            nonlocal song_selected_music_filepath
            nonlocal song_custom_offset_filepath
            song_selected = None
            song_selected_music_filepath = None
            song_custom_offset_filepath = None
            select_song()
        else:
            nonlocal beatmap_selected
            beatmap_selected = beatmap_list[beatmap_selected_index]

    select_song_folder()
    assert(song_folder_selected and song_selected and song_selected_music_filepath and song_custom_offset_filepath and beatmap_selected)

    print(f'🎵 {song_selected.displayed_name()} | {beatmap_selected.displayed_difficulty()}')
    ddr_window = DDRWindow(song=song_selected, beatmap=beatmap_selected, song_music_filepath=song_selected_music_filepath, song_custom_offset_filepath=song_custom_offset_filepath)
    ddr_window.start_main_loop()

################
# MAIN END
################

if __name__ == '__main__':
    main()
