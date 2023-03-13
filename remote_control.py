#!/usr/bin/env python3

# Copyright (c) 2018 Anki, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License in the file LICENSE.txt or at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Control Vector using a webpage on your computer.

This example lets you control Vector by Remote Control, using a webpage served by Flask.

This code has bee modified for our HRI user study.
For reference, the original code is here: https://github.com/anki/vector-python-sdk/tree/master/examples/apps/remote_control

Current known issues:
Sometimes program will immediately error out with the ListAnimations error. Must rerun program
Vector will disconnect from cube if not constantly communicating with it (automate this?)
Sometimes go_to_saved_pose doesn't work. Just run again
Sometimes vector continues driving after key release. Just press and let go of that key again
"""

import io
import json
import sys
import time
from enum import Enum
from lib import flask_helpers

import anki_vector
from anki_vector import util
from anki_vector import annotate

try:
    from flask import Flask, request
except ImportError:
    sys.exit("Cannot import from flask: Do `pip3 install --user flask` to install")

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Cannot import from PIL: Do `pip3 install --user Pillow` to install")


def create_default_image(image_width, image_height, do_gradient=False):
    """Create a place-holder PIL image to use until we have a live feed from Vector"""
    image_bytes = bytearray([0x70, 0x70, 0x70]) * image_width * image_height

    if do_gradient:
        i = 0
        for y in range(image_height):
            for x in range(image_width):
                image_bytes[i] = int(255.0 * (x / image_width))   # R
                image_bytes[i + 1] = int(255.0 * (y / image_height))  # G
                image_bytes[i + 2] = 0                                # B
                i += 3

    image = Image.frombytes('RGB', (image_width, image_height), bytes(image_bytes))
    return image


flask_app = Flask(__name__)
_default_camera_image = create_default_image(320, 240)

def remap_to_range(x, x_min, x_max, out_min, out_max):
    """convert x (in x_min..x_max range) to out_min..out_max range"""
    if x < x_min:
        return out_min
    if x > x_max:
        return out_max
    ratio = (x - x_min) / (x_max - x_min)
    return out_min + ratio * (out_max - out_min)

class Subroutines:
    def __init__(self, remote):
        self.remote = remote
        self.robot = remote.vector
        self.saved_posed = None
        self.routines = ['connect_to_cube','pick_up_cube', "drive_to_charger", "roll_cube", 'flash_cube_lights', 'save_pose', 'go_to_saved_pose', 
                         'put_cube_down']
        self.runs = 0

    def connect_to_cube(self):
        self.robot.world.connect_cube()
        
    def flash_cube_lights(self):
        self.robot.world.flash_cube_lights()

    def pick_up_cube(self):
        if self.robot.world.connected_light_cube:
            self.robot.behavior.pickup_object(
                self.robot.world.connected_light_cube,
                num_retries=3)

    def drive_to_charger(self):
        self.robot.behavior.drive_on_charger()

    def roll_cube(self):
        if self.robot.world.connected_light_cube:
            self.robot.behavior.roll_cube(
                self.robot.world.connected_light_cube,
                num_retries=3)
    
    def put_cube_down(self):
        if self.robot.world.connected_light_cube:
            self.robot.behavior.place_object_on_ground_here(num_retries=3)
    
    def save_pose(self):
        self.saved_pose = self.robot.pose
    
    def go_to_saved_pose(self):
        if self.saved_pose:
            self.robot.behavior.go_to_pose(self.saved_pose)
    
    def run_subroutine(self, key):
        try:
            print(key)
            if key == 'pick_up_cube':
                self.pick_up_cube()
            elif key == 'connect_to_cube':
                self.connect_to_cube()
            elif key == "drive_to_charger":
                self.drive_to_charger()
            elif key == "roll_cube":
                self.roll_cube()
            elif key == "flash_cube_lights":
                self.flash_cube_lights()
            elif key == "save_pose":
                self.save_pose()
            elif key == "go_to_saved_pose":
                self.go_to_saved_pose()
            elif key == "put_cube_down":
                self.put_cube_down()
            else:
                print("Warning, not mapping to a function")
        except Exception as e:
            print(e)
        finally:
            self.runs += 1
            return True

class RemoteControlVector:

    def __init__(self, robot):
        self.vector = robot

        # don't send motor messages if it matches the last setting
        self.last_lift = None
        self.last_head = None
        self.last_wheels = None

        self.drive_forwards = 0
        self.drive_back = 0
        self.turn_left = 0
        self.turn_right = 0
        self.lift_up = 0
        self.lift_down = 0
        self.head_up = 0
        self.head_down = 0

        self.go_fast = 0
        self.go_slow = 0

        self.mouse_dir = 0
        self.routines = Subroutines(self)

        #In Anki's original program, the subroutines actually mapped to Vector's animations
        #Therefore, in this program, anim refers to routines
        self.anim_names = self.routines.routines

        default_anims_for_keys = ["connect_to_cube",  # 1
                                  "flash_cube_lights",  # 2
                                  "pick_up_cube",  # 3
                                  "put_cube_down",  # 4
                                  "roll_cube",  # 5
                                  "drive_to_charger",  # 6
                                  "save_pose",  # 7
                                  "go_to_saved_pose"]  # 8
        
        self.anim_index_for_key = [0] * 8
        kI = 0
        for default_key in default_anims_for_keys:
            if default_key not in self.anim_names:
                print("Error: default_anim %s is not in the list of animations" % default_key)
            else:
                self.anim_index_for_key[kI] = self.anim_names.index(default_key)
            kI += 1

        self.action_queue = []
        self.text_to_say = "Hi I'm Vector"

    def set_anim(self, key_index, anim_index):
        self.anim_index_for_key[key_index] = anim_index   

    def update_drive_state(self, key_code, is_key_down, speed_changed):
        """Update state of driving intent from keyboard, and if anything changed then call update_driving"""
        update_driving = True
        if key_code == ord('W'):
            self.drive_forwards = is_key_down
        elif key_code == ord('S'):
            self.drive_back = is_key_down
        elif key_code == ord('A'):
            self.turn_left = is_key_down
        elif key_code == ord('D'):
            self.turn_right = is_key_down
        else:
            if not speed_changed:
                update_driving = False
        return update_driving

    def update_lift_state(self, key_code, is_key_down, speed_changed):
        """Update state of lift move intent from keyboard, and if anything changed then call update_lift"""
        update_lift = True
        if key_code == ord('R'):
            self.lift_up = is_key_down
        elif key_code == ord('F'):
            self.lift_down = is_key_down
        else:
            if not speed_changed:
                update_lift = False
        return update_lift

    def update_head_state(self, key_code, is_key_down, speed_changed):
        """Update state of head move intent from keyboard, and if anything changed then call update_head"""
        update_head = True
        if key_code == ord('T'):
            self.head_up = is_key_down
        elif key_code == ord('G'):
            self.head_down = is_key_down
        else:
            if not speed_changed:
                update_head = False
        return update_head

    def handle_key(self, key_code, is_shift_down, is_alt_down, is_key_down):
        """Called on any key press or release
           Holding a key down may result in repeated handle_key calls with is_key_down==True
        """

        # Update desired speed / fidelity of actions based on shift/alt being held
        was_go_fast = self.go_fast
        was_go_slow = self.go_slow

        self.go_fast = is_shift_down
        self.go_slow = is_alt_down

        speed_changed = (was_go_fast != self.go_fast) or (was_go_slow != self.go_slow)

        update_driving = self.update_drive_state(key_code, is_key_down, speed_changed)

        update_lift = self.update_lift_state(key_code, is_key_down, speed_changed)

        update_head = self.update_head_state(key_code, is_key_down, speed_changed)

        # Update driving, head and lift as appropriate
        if update_driving:
            self.update_mouse_driving()
        if update_head:
            self.update_head()
        if update_lift:
            self.update_lift()

        # Handle any keys being released (e.g. the end of a key-click)
        if not is_key_down:
            if ord('8') >= key_code >= ord('1'):
                anim_name = self.key_code_to_anim_name(key_code)
                self.queue_action((self.routines.run_subroutine, anim_name))
                #self.queue_action((self.vector.anim.play_animation, anim_name))
            elif key_code == ord(' '):
                self.queue_action((self.vector.behavior.say_text, self.text_to_say))

    def key_code_to_anim_name(self, key_code):
        key_num = key_code - ord('1')
        anim_num = self.anim_index_for_key[key_num]
        anim_name = self.anim_names[anim_num]
        return anim_name

    def queue_action(self, new_action):
        if len(self.action_queue) > 10:
            self.action_queue.pop(0)
        self.action_queue.append(new_action)

    def update(self):
        """Try and execute the next queued action"""
        if self.action_queue and len(self.action_queue) > 0:
            queued_action, action_args = self.action_queue[0]
            if queued_action(action_args):
                self.action_queue.pop(0)

    def pick_speed(self, fast_speed, mid_speed, slow_speed):
        if self.go_fast:
            if not self.go_slow:
                return fast_speed
        elif self.go_slow:
            return slow_speed
        return mid_speed

    def update_lift(self):
        lift_speed = self.pick_speed(8, 4, 2)
        lift_vel = (self.lift_up - self.lift_down) * lift_speed
        if self.last_lift and lift_vel == self.last_lift:
            return
        self.last_lift = lift_vel
        self.vector.motors.set_lift_motor(lift_vel)

    def update_head(self):
        head_speed = self.pick_speed(2, 1, 0.5)
        head_vel = (self.head_up - self.head_down) * head_speed
        if self.last_head and head_vel == self.last_head:
            return
        self.last_head = head_vel
        self.vector.motors.set_head_motor(head_vel)

    def update_mouse_driving(self):
        drive_dir = (self.drive_forwards - self.drive_back)

        turn_dir = (self.turn_right - self.turn_left) + self.mouse_dir
        if drive_dir < 0:
            # It feels more natural to turn the opposite way when reversing
            turn_dir = -turn_dir

        forward_speed = self.pick_speed(150, 75, 50)
        turn_speed = self.pick_speed(100, 50, 30)

        l_wheel_speed = (drive_dir * forward_speed) + (turn_speed * turn_dir)
        r_wheel_speed = (drive_dir * forward_speed) - (turn_speed * turn_dir)

        wheel_params = (l_wheel_speed, r_wheel_speed, l_wheel_speed * 4, r_wheel_speed * 4)
        if self.last_wheels and wheel_params == self.last_wheels:
            return
        self.last_wheels = wheel_params
        self.vector.motors.set_wheel_motors(*wheel_params)


def get_anim_sel_drop_down(selectorIndex):
    html_text = """<select onchange="handleDropDownSelect(this)" name="animSelector""" + str(selectorIndex) + """">"""
    selectorIndex -= 1
    i = 0
    for anim_name in flask_app.remote_control_vector.anim_names:
        is_selected_item = (i == flask_app.remote_control_vector.anim_index_for_key[selectorIndex])
        selected_text = ''' selected="selected"''' if is_selected_item else ""
        html_text += """<option value=""" + str(i) + selected_text + """>""" + anim_name + """</option>"""
        i += 1
    html_text += """</select>"""
    return html_text


def get_anim_sel_drop_downs():
    html_text = ""
    for i in range(8):
        # list keys 1..9,0 as that's the layout on the keyboard
        key = i + 1 #if (i < 9) else 0
        html_text += str(key) + """: """ + get_anim_sel_drop_down(key) + """<br>"""
    return html_text

def to_js_bool_string(bool_value):
    return "true" if bool_value else "false"


@flask_app.route("/")
def handle_index_page():
    return """
    <html>
        <head>
            <title>remote_control_vector.py display</title>
        </head>
        <body>
            <h1>Remote Control Vector</h1>
            <table>
                <tr>
                    <td valign = top>
                        <div id="vectorImageMicrosoftWarning" style="display: none;color: #ff9900; text-align: center;">Video feed performance is better in Chrome or Firefox due to mjpeg limitations in this browser</div>
                        <img src="vectorImage" id="vectorImageId" width=640 height=480>
                        <div id="DebugInfoId"></div>
                    </td>
                    <td width=30></td>
                    <td valign=top>
                        <h2>Controls:</h2>

                        <h3>Driving:</h3>

                        <b>W A S D</b> : Drive Forwards / Left / Back / Right<br><br>

                        <h3>Head:</h3>
                        <b>T</b> : Move Head Up<br>
                        <b>G</b> : Move Head Down<br>

                        <h3>Lift:</h3>
                        <b>R</b> : Move Lift Up<br>
                        <b>F</b>: Move Lift Down<br>
                        <h3>General:</h3>
                        <b>Shift</b> : Hold to Move Faster (Driving, Head and Lift)<br>
                        <b>Alt</b> : Hold to Move Slower (Driving, Head and Lift)<br>
                        <b>P</b> : Toggle Free Play mode: <button id="freeplayId" onClick=onFreeplayButtonClicked(this) style="font-size: 14px">Default</button><br>
                        <h3>Talk</h3>
                        <b>Space</b> : Say <input type="text" name="sayText" id="sayTextId" value=\"""" + flask_app.remote_control_vector.text_to_say + """\" onchange=handleTextInput(this)>
                    </td>
                    <td width=30></td>
                    <td valign=top>
                    <h2>Subroutines</h2>
                    <h3>Run Subroutinue</h3>
                        <b>0 .. 9</b> : Run Subroutine mapped to that key<br>
                    <h3>Subroutine key mappings:</h3>
                    """ + get_anim_sel_drop_downs() + """<br>
                    
                    </td>
                </tr>
            </table>

            <script type="text/javascript">
                var gLastClientX = -1
                var gLastClientY = -1
                var gIsFreeplayEnabled = false
                var gUserAgent = window.navigator.userAgent;
                var gIsMicrosoftBrowser = gUserAgent.indexOf('MSIE ') > 0 || gUserAgent.indexOf('Trident/') > 0 || gUserAgent.indexOf('Edge/') > 0;
                var gSkipFrame = false;

                if (gIsMicrosoftBrowser) {
                    document.getElementById("vectorImageMicrosoftWarning").style.display = "block";
                }

                function postHttpRequest(url, dataSet)
                {
                    var xhr = new XMLHttpRequest();
                    xhr.open("POST", url, true);
                    xhr.send( JSON.stringify( dataSet ) );
                }

                function updateVector()
                {
                    console.log("Updating log")
                    if (gIsMicrosoftBrowser && !gSkipFrame) {
                        // IE doesn't support MJPEG, so we need to ping the server for more images.
                        // Though, if this happens too frequently, the controls will be unresponsive.
                        gSkipFrame = true;
                        document.getElementById("vectorImageId").src="vectorImage?" + (new Date()).getTime();
                    } else if (gSkipFrame) {
                        gSkipFrame = false;
                    }
                    var xhr = new XMLHttpRequest();
                    xhr.onreadystatechange = function() {
                        if (xhr.readyState == XMLHttpRequest.DONE) {
                            document.getElementById("DebugInfoId").innerHTML = xhr.responseText
                        }
                    }

                    xhr.open("POST", "updateVector", true);
                    xhr.send( null );
                }
                setInterval(updateVector , 60);

                function updateButtonEnabledText(button, isEnabled)
                {
                    button.firstChild.data = isEnabled ? "Enabled" : "Disabled";
                }

                function onFreeplayButtonClicked(button)
                {
                    gIsFreeplayEnabled = !gIsFreeplayEnabled;
                    updateButtonEnabledText(button, gIsFreeplayEnabled);
                    isFreeplayEnabled = gIsFreeplayEnabled
                    postHttpRequest("setFreeplayEnabled", {isFreeplayEnabled})
                }

                updateButtonEnabledText(document.getElementById("freeplayId"), gIsFreeplayEnabled);

                function handleDropDownSelect(selectObject)
                {
                    selectedIndex = selectObject.selectedIndex
                    itemName = selectObject.name
                    postHttpRequest("dropDownSelect", {selectedIndex, itemName});
                }

                function handleAnimTriggerDropDownSelect(selectObject)
                {
                    animTriggerName = selectObject.value
                    postHttpRequest("animTriggerDropDownSelect", {animTriggerName});
                }

                function handleKeyActivity (e, actionType)
                {
                    var keyCode  = (e.keyCode ? e.keyCode : e.which);
                    var hasShift = (e.shiftKey ? 1 : 0)
                    var hasCtrl  = (e.ctrlKey  ? 1 : 0)
                    var hasAlt   = (e.altKey   ? 1 : 0)

                    if (actionType=="keyup")
                    {
                        if (keyCode == 80) // 'P'
                        {
                            // Simulate a click of the freeplay button
                            onFreeplayButtonClicked(document.getElementById("freeplayId"))
                        }
                    }

                    postHttpRequest(actionType, {keyCode, hasShift, hasCtrl, hasAlt})
                }


                function handleTextInput(textField)
                {
                    textEntered = textField.value
                    postHttpRequest(textField.name, {textEntered})
                }

                document.addEventListener("keydown", function(e) { handleKeyActivity(e, "keydown") } );
                document.addEventListener("keyup",   function(e) { handleKeyActivity(e, "keyup") } );

                function stopEventPropagation(event)
                {
                    if (event.stopPropagation)
                    {
                        event.stopPropagation();
                    }
                    else
                    {
                        event.cancelBubble = true
                    }
                }

                document.getElementById("sayTextId").addEventListener("keydown", function(event) {
                    stopEventPropagation(event);
                } );
                document.getElementById("sayTextId").addEventListener("keyup", function(event) {
                    stopEventPropagation(event);
                } );
            </script>

        </body>
    </html>
    """


def get_annotated_image():
    image = flask_app.remote_control_vector.vector.camera.latest_image
    return image.raw_image


def streaming_video():
    """Video streaming generator function"""
    while True:
        if flask_app.remote_control_vector:
            image = get_annotated_image()

            img_io = io.BytesIO()
            image.save(img_io, 'PNG')
            img_io.seek(0)
            yield (b'--frame\r\n'
                   b'Content-Type: image/png\r\n\r\n' + img_io.getvalue() + b'\r\n')
        else:
            time.sleep(.1)


def serve_single_image():
    if flask_app.remote_control_vector:
        image = get_annotated_image()
        if image:
            return flask_helpers.serve_pil_image(image)

    return flask_helpers.serve_pil_image(_default_camera_image)


def is_microsoft_browser(req):
    agent = req.user_agent.string
    return 'Edge/' in agent or 'MSIE ' in agent or 'Trident/' in agent


@flask_app.route("/vectorImage")
def handle_vectorImage():
    if is_microsoft_browser(request):
        return serve_single_image()
    return flask_helpers.stream_video(streaming_video)


def handle_key_event(key_request, is_key_down):
    message = json.loads(key_request.data.decode("utf-8"))
    if flask_app.remote_control_vector:
        flask_app.remote_control_vector.handle_key(key_code=(message['keyCode']), is_shift_down=message['hasShift'],
                                                   is_alt_down=message['hasAlt'], is_key_down=is_key_down)
    return ""


@flask_app.route('/setFreeplayEnabled', methods=['POST'])
def handle_setFreeplayEnabled():
    """Called from Javascript whenever freeplay mode is toggled on/off"""
    message = json.loads(request.data.decode("utf-8"))
    isFreeplayEnabled = message['isFreeplayEnabled']
    if flask_app.remote_control_vector:
        connection = flask_app.remote_control_vector.vector.conn
        if isFreeplayEnabled:
            connection.release_control()
        else:
            connection.request_control()
    return ""


@flask_app.route('/keydown', methods=['POST'])
def handle_keydown():
    """Called from Javascript whenever a key is down (note: can generate repeat calls if held down)"""
    return handle_key_event(request, is_key_down=True)


@flask_app.route('/keyup', methods=['POST'])
def handle_keyup():
    """Called from Javascript whenever a key is released"""
    return handle_key_event(request, is_key_down=False)


@flask_app.route('/dropDownSelect', methods=['POST'])
def handle_dropDownSelect():
    """Called from Javascript whenever an animSelector dropdown menu is selected (i.e. modified)"""
    message = json.loads(request.data.decode("utf-8"))

    item_name_prefix = "animSelector"
    item_name = message['itemName']

    if flask_app.remote_control_vector and item_name.startswith(item_name_prefix):
        item_name_index = int(item_name[len(item_name_prefix):])
        flask_app.remote_control_vector.set_anim(item_name_index, message['selectedIndex'])

    return ""

@flask_app.route('/animTriggerDropDownSelect', methods=['POST'])
def handle_animTriggerDropDownSelect():
    """Called from Javascript whenever the animTriggerSelector dropdown menu is selected (i.e. modified)"""
    message = json.loads(request.data.decode("utf-8"))
    selected_anim_trigger_name = message['animTriggerName']
    flask_app.remote_control_vector.selected_anim_trigger_name = selected_anim_trigger_name
    return ""

@flask_app.route('/sayText', methods=['POST'])
def handle_sayText():
    """Called from Javascript whenever the saytext text field is modified"""
    message = json.loads(request.data.decode("utf-8"))
    if flask_app.remote_control_vector:
        flask_app.remote_control_vector.text_to_say = message['textEntered']
    return ""

@flask_app.route('/updateVector', methods=['POST'])
def handle_updateVector():
    if flask_app.remote_control_vector:
        flask_app.remote_control_vector.update()
    return ""

def run():
    args = util.parse_command_args()

    #with anki_vector.AsyncRobot(args.serial, enable_face_detection=True, enable_custom_object_detection=True) as robot:
    with anki_vector.AsyncRobot() as robot:
        flask_app.remote_control_vector = RemoteControlVector(robot)

        robot.camera.init_camera_feed()
        robot.behavior.drive_off_charger()

        flask_helpers.run_flask(flask_app)


if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt as e:
        pass
    except anki_vector.exceptions.VectorConnectionException as e:
        sys.exit("A connection error occurred: %s" % e)
