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

    def displayed_name(self):
        return f'{self._header_data["TITLE"]} ({self._header_data["ARTIST"]}) · {self._displayed_beats_per_minute()} BPM'

    def _displayed_beats_per_minute(self):
        if 'DISPLAYBPM' in self._header_data:
            return int(self._header_data['DISPLAYBPM'])
        return int(self.beats_per_minute())

    def music_filename(self):
        return self._header_data['MUSIC']

    def music_offset(self):
        return float(self._header_data['OFFSET'])

    def beats_per_minute(self):
        # TODO: Handle within-song changing BPMS
        bpms_data = self._header_data['BPMS'].split('=')
        assert(float(bpms_data[0]) == 0)
        return float(bpms_data[1])

    def beats_per_measure(self):
        # TODO: Handle different 'TIMESIGNATURES'
        time_signatures_data = self._header_data['TIMESIGNATURES'].split('=')
        assert(float(time_signatures_data[0]) == 0)
        assert(float(time_signatures_data[1]) == 4)
        assert(float(time_signatures_data[2]) == 4)
        return 4

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

def parse(lines):
    header_data = parse_hashtag_headered(lines)
    beatmap_list = []
    while True:
        maybe_beatmap = parse_beatmap(lines)
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
    assert(colon_index != -1)
    return line[:colon_index]

def parse_beatmap(lines):
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
        beatmap_lines.append(line)
    return Beatmap(title_line=parse_beatmap_title_line(beatmap_title_line), data=parse_hashtag_headered(beatmap_lines))

def parse_beatmap_title_line(beatmap_title_line):
    assert(beatmap_title_line.startswith('//'))
    beatmap_title_line = beatmap_title_line[2:]
    return beatmap_title_line.strip('-')

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

GLOBAL_MUSIC_OFFSET_SECONDS = 0.22 # TODO: I wonder why we need this manual offset
MILLISECONDS_IN_SECONDS = 1000

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
    def __init__(self, song, beatmap, song_music_filepath, precomputed_fps=PRECOMPUTED_FPS, position_x=POSITION_X, position_y=POSITION_Y, display_width=DISPLAY_WIDTH, display_height=DISPLAY_HEIGHT):
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
        self._music_offset = (beatmap.music_offset() if beatmap.music_offset() else song.music_offset()) + GLOBAL_MUSIC_OFFSET_SECONDS

        print('⏳️ Precomputing...')
        self._precomputed_displays = self._precompute_displays(song, beatmap, precomputed_fps)
        print('✅ Precomputing complete!')

        pygame.mixer.music.play()

    # This can theoretically be optimized by using the fact that [beat_list] is sorted by [measure_time],
    # but doing so feels like over-engineering since this is a precomputing step
    def _precompute_displays(self, song, beatmap, precomputed_fps):
        beats_per_minute = song.beats_per_minute()
        beats_per_measure = song.beats_per_measure()
        beat_list = beatmap.ddr_beat_list()

        def measure_time_to_frame(measure_time):
            return measure_time * beats_per_measure / beats_per_minute * 60 * precomputed_fps

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

    def run(self):
        glutDisplayFunc(self._display_func)
        glutIdleFunc(self._display_func)
        glutMainLoop()

    def _display_func(self):
        self._display_reset()
        self._target_arrows()
        self._moving_arrows(pygame.mixer.music.get_pos() / MILLISECONDS_IN_SECONDS - self._music_offset)
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
        if current_frame >= len(self._precomputed_displays): # Song is over!
            # TODO: Find out why this keeps segfaulting and maybe find a more graceful way to exit
            glutDestroyWindow(self._window)
        precomputed_display = self._precomputed_displays[current_frame]
        for displayed_beat in precomputed_display:
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

def get_song_list():
    assert(SONG_MAIN_DIR_NAME in os.listdir())
    song_list = []
    for song_dir_name in os.listdir(SONG_MAIN_DIR_NAME):
        song_dir_filepath = os.path.join(SONG_MAIN_DIR_NAME, song_dir_name)
        if not os.path.isdir(song_dir_filepath):
            continue
        song_ssc_filename = next(filter(lambda file: file.endswith('.ssc'), os.listdir(song_dir_filepath)), None)
        if not song_ssc_filename:
            continue
        song_ssc_filepath = os.path.join(song_dir_filepath, song_ssc_filename)
        with open(song_ssc_filepath) as f:
            song = parse(f.readlines())
        song_music_filepath = os.path.join(song_dir_filepath, song.music_filename())
        if not os.path.exists(song_music_filepath):
            continue
        song_list.append((song, song_music_filepath))
    song_list.sort(key=lambda song_and_song_music_filepath_pair: song_and_song_music_filepath_pair[0].displayed_name())
    return song_list

################
# SONG LIST END
################

################
# MAIN START
################

PICK_INDICATOR = '=>'

def select_song():
    song_list = get_song_list()
    song_displayed_options = [song.displayed_name() for song, _ in song_list]
    _, song_selected_index = pick.pick(options=song_displayed_options, title='Choose song...', indicator=PICK_INDICATOR)
    return song_list[song_selected_index]

def select_beatmap(song_selected):
    beatmap_list = song_selected.ddr_beatmap_list()
    beatmap_displayed_options = [beatmap.displayed_difficulty() for beatmap in beatmap_list]
    _, beatmap_selected_index = pick.pick(options=beatmap_displayed_options + ['<Back>'], title='Choose difficulty...', indicator=PICK_INDICATOR)
    if beatmap_selected_index == len(beatmap_list): # <Back>
        return None
    else:
        return beatmap_list[beatmap_selected_index]

def full_select_beatmap():
    song_selected, song_selected_music_filepath = select_song()
    beatmap_selected = select_beatmap(song_selected)
    if beatmap_selected:
        return song_selected, beatmap_selected, song_selected_music_filepath
    else: # <Back>
        return full_select_beatmap()

def main():
    song_selected, beatmap_selected, song_selected_music_filepath = full_select_beatmap()
    print(f'🎵 {song_selected.displayed_name()} | {beatmap_selected.displayed_difficulty()}')
    ddr_window = DDRWindow(song=song_selected, beatmap=beatmap_selected, song_music_filepath=song_selected_music_filepath)
    ddr_window.run()

################
# MAIN END
################

if __name__ == '__main__':
    main()
