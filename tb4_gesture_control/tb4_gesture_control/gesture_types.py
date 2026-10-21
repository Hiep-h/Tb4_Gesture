"""Shared gesture-name constants and the /detected_gesture JSON schema.

Both nodes import this module so the gesture vocabulary and the wire
format of the std_msgs/String payload stay in one place instead of being
duplicated (and able to drift) between the recognizer and the behavior
node.
"""

# MediaPipe's bundled gesture_recognizer.task model already classifies
# these categories out of the box.
CLOSED_FIST = 'Closed_Fist'
OPEN_PALM = 'Open_Palm'
POINTING_UP = 'Pointing_Up'
VICTORY = 'Victory'
THUMB_UP = 'Thumb_Up'
THUMB_DOWN = 'Thumb_Down'
NONE_GESTURE = 'None'

# Not a MediaPipe category: detected on top of the model output from the
# wrist-position time series (see WaveDetector in gesture_recognition_node).
WAVE = 'Wave'

# The six gestures this assignment maps to robot behaviors (>= 5 required).
SUPPORTED_GESTURES = (
    WAVE,
    POINTING_UP,
    VICTORY,
    THUMB_UP,
    OPEN_PALM,
    CLOSED_FIST,
)

# JSON keys used in the std_msgs/msg/String payload published on
# /detected_gesture, e.g. {"gesture": "Open_Palm", "confidence": 0.93,
# "stamp": 1732000000.12}.
KEY_GESTURE = 'gesture'
KEY_CONFIDENCE = 'confidence'
KEY_STAMP = 'stamp'

DETECTED_GESTURE_TOPIC = '/detected_gesture'
CMD_VEL_TOPIC = '/cmd_vel'
