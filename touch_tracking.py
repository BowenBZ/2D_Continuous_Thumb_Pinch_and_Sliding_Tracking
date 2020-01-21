'''
This script is used to track the touch position

It includes:
1. Call Otsu threshold to segment the hand part and get the contour of hand
2. Use Convexity Defects to get feature points from the contour
3. Calculate the middle point and use Kalman filter to correct it
4. Draw the relative movements in a drawing board
'''

import cv2
import numpy as np
from time import sleep
from enum import IntEnum
import picamera_control
from draw_board import draw_board
import segment_otsu


def _get_defect_points(img, max_contour, VALID_CNT_AREA = 0):
    """Get the two convex defect points

    Arguments:
        max_contour {cv2.contour} -- [the contour with the max area]

    Returns:
        defect_points [list] -- [left and right defect points]
    """
    # In case no contour or the contour area is too small (single fingertip)
    if max_contour is None or cv2.contourArea(max_contour) < VALID_CNT_AREA:
        return None

    # Get the convex defects
    hull = cv2.convexHull(max_contour, returnPoints=False)
    defects = cv2.convexityDefects(max_contour, hull)

    # Get the defects with the largest 2 distance
    sorted_defects = sorted(defects[:, 0], key=lambda x: x[3])
    if len(sorted_defects) < 2:
        return None

    defect_points = []
    for s, e, f, d in sorted_defects[-2:]:
        start = tuple(max_contour[s][0])
        end = tuple(max_contour[e][0])
        far = tuple(max_contour[f][0])
        defect_points.append(far)
        cv2.line(img, start, end, [0, 255, 0], 2)
        cv2.circle(img, far, 5, [0, 0, 255], -1)

    defect_points.sort(key=lambda x: x[0])

    return defect_points


def get_touch_point(img, max_contour, VALID_CNT_AREA = 0, kalman_filter=None):
    """Extract feature points with the max contour

    Arguments:
        img {np.array} -- [Target image to draw the results. The segmented image]
        max_contour {cv2.contour} -- [Parameter to generate the touch point]

    Returns:
        touchPoint [tuple] -- [The touch coordinate of the fingertips]
        defectPoints [list] -- [A list of tuple which indicate the coordinate of the defects]
    """
    defect_points = _get_defect_points(img, max_contour, VALID_CNT_AREA)
    if defect_points is None:
        return None

    # Get the touch point
    middle_point = ((defect_points[0][0] + defect_points[1][0]) / 2,
                    (defect_points[0][1] + defect_points[1][1]) / 2)

    raw_touch_point = (int(middle_point[0]), int(middle_point[1]))
    cv2.circle(img, raw_touch_point, 5, [0, 255, 0], -1)

    # Adopt kalman filter here
    if kalman_filter is not None:
        kalman_filter.correct(np.array([[np.float32(middle_point[0])], [np.float32(middle_point[1])]]))
        middle_point = kalman_filter.predict()
    touch_point = (int(middle_point[0]), int(middle_point[1]))
    cv2.circle(img, touch_point, 5, [255, 0, 0], -1)

    return touch_point


class point_type(IntEnum):
    MIN_X = 0
    MAX_X = 1
    MIN_Y = 2
    MAX_Y = 3


cur_point_type = point_type.MIN_X
base_point = [159, 347, 106, 302]


def calibrate_base_point(point):
    """Reset the old touch point

    Arguments:
        point {[type]} -- [description]
    """
    global cur_point_type, base_point
    if cur_point_type == point_type.MIN_X or cur_point_type == point_type.MAX_X:
        base_point[int(cur_point_type)] = point[0]
    else:
        base_point[int(cur_point_type)] = point[1]
    print("Store base point", cur_point_type)
    print("Current base points", base_point)
    cur_point_type = point_type((int(cur_point_type) + 1) % 4)


def calculate_movements(point):
    """Canculate the relative movements of current touch points to the old touch points

    Arguments:
        point {tuple} -- [current touch position]

    Returns:
        dx {float} -- [relative movement in x direction]
        dy {float}  -- [relative movement in y direction]
    """
    global base_point

    MAX_UNIT = 100

    dx = _scaler(point[0], [base_point[int(point_type.MIN_X)], -
                            MAX_UNIT], [base_point[int(point_type.MAX_X)], MAX_UNIT])
    dy = _scaler(point[1], [base_point[int(point_type.MIN_Y)], -
                            MAX_UNIT], [base_point[int(point_type.MAX_Y)], MAX_UNIT])

    return dx, dy


def _scaler(value, min_base_target, max_base_target):
    """Project value from [min_base, max_base] to [min_target, max_target]
    
    Arguments:
        value {float} -- [description]
        min_base_target {list} -- [min_base, min_target]
        max_base_target {list} -- [max_base, max_target]
    
    Returns:
        value -- [projected value]
    """
    min_base, min_target = min_base_target
    max_base, max_target = max_base_target
    return (value - min_base) / (max_base - min_base) * (max_target - min_target) + min_target


def configure_kalman_filter():
    """Configure the kalman filter
    
    Returns:
        [type] -- [description]
    """
    # State number: 4, including (x，y，dx，dy) (position and velocity)
    # Measurement number: 2, (x, y) (position)
    kalman = cv2.KalmanFilter(4, 2) 
    kalman.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float32) 
    kalman.transitionMatrix = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], np.float32) 
    kalman.processNoiseCov = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], np.float32) * 0.03 

    return kalman

if __name__ == '__main__':
    """
    This function get the frame from the camera, and use thresholding to segment the hand part
    """
    try:
        WIDTH, HEIGHT = 640, 480
        camera, rawCapture = picamera_control.configure_camera(WIDTH, HEIGHT, FRAME_RATE=50)

        kalman_filter = configure_kalman_filter()

        DR_WIDTH, DR_HEIGHT = 320, 320
        hv_board = draw_board(DR_WIDTH, DR_HEIGHT, MAX_POINTS=5)
        hor_board = draw_board(DR_WIDTH, DR_HEIGHT, MAX_POINTS=1)
        ver_board = draw_board(DR_WIDTH, DR_HEIGHT, MAX_POINTS=1)

        print("To calibrate, press 'C' and follow the order LEFT, RIGHT, UP, DOWN")

        for frame in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
            bgr_image = frame.array

            # Get the mask using the Otsu thresholding method
            mask, max_contour = segment_otsu.threshold_masking(bgr_image)

            # Apply the mask to the image
            segment = cv2.bitwise_and(bgr_image, bgr_image, mask=mask)

            # Get touch from the contour and draw points in the segment image
            touch_point = get_touch_point(segment, max_contour, VALID_CNT_AREA=100000, kalman_filter=kalman_filter)

            if touch_point is not None:
                # Track the touch point
                dx, dy = calculate_movements(touch_point)
                k = 1
                size = 10
                hor_board.draw_filled_point((-dx * k, 0), radius=size)
                ver_board.draw_filled_point((0, dy * k), radius=size)
                hv_board.draw_filled_point((-dx * k, dy * k), radius=size)

            # Display
            # cv2.imshow("original", bgr_image)
            # cv2.imshow('Mask', mask)
            cv2.imshow('Segment', segment)
            cv2.imshow('HV Board', hv_board.board)
            H_V_joint = np.concatenate(
                (hor_board.board, ver_board.board), axis=1)
            cv2.line(H_V_joint, (H_V_joint.shape[1] // 2, 0),
                     (H_V_joint.shape[1] // 2, H_V_joint.shape[0]), [255, 255, 255], 3)
            cv2.imshow('H V Movement', H_V_joint)

            # if the user pressed ESC, then stop looping
            keypress = cv2.waitKey(1) & 0xFF
            if keypress == 27:
                break
            elif keypress == ord('c'):
                calibrate_base_point(touch_point)
                hv_board.reset_board()
                hor_board.reset_board()
                ver_board.reset_board()

            rawCapture.truncate(0)

        camera.close()
        cv2.destroyAllWindows()
    except Exception as e:
        print(e)
        camera.close()
        cv2.destroyAllWindows()